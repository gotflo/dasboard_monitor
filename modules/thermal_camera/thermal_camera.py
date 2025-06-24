#!/usr/bin/env python3
"""
Module Caméra Thermique - Backend
Gestion de la caméra thermique et analyse faciale
Enregistre TOUS les 478 points FaceMesh (468 landmarks + 10 iris) dans le CSV
"""

import cv2
import mediapipe as mp
import numpy as np
import csv
import json
import base64
import threading
import time
import os
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ThermalCameraModule:
    """Module de gestion de la caméra thermique avec détection faciale"""
    
    def __init__(self, app, websocket_manager):
        self.app = app
        self.websocket_manager = websocket_manager
        self.is_running = False
        self.is_recording = False
        self.capture_thread = None
        self.cap = None
        self.current_recording_file = None
        self.recording_line_count = 0
        
        # Configuration
        self.camera_index = 1  # Index de la caméra thermique
        self.recordings_dir = Path('recordings/thermal')
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        
        # MediaPipe FaceMesh
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        # Points d'intérêt du visage
        self.landmark_points = {
            "Nez": 2,
            "Bouche": 13,
            "Œil_Gauche": 159,
            "Œil_Droit": 386,
            "Joue_Gauche": 234,
            "Joue_Droite": 454,
            "Front": 10,
            "Menton": 152
        }
        
        # CSV headers
        self.csv_headers = None
        self.header_written = False
        
        # Enregistrer les routes
        self._register_routes()
        
        logger.info("Module Caméra Thermique initialisé")
    
    def _register_routes(self):
        """Enregistrer les routes API"""
        
        @self.app.route('/api/thermal/download/<filename>')
        def download_thermal_recording(filename):
            """Télécharger un fichier d'enregistrement"""
            from flask import send_file, abort
            
            file_path = self.recordings_dir / filename
            if not file_path.exists() or not file_path.is_file():
                abort(404)
            
            return send_file(
                file_path,
                as_attachment=True,
                download_name=filename,
                mimetype='text/csv'
            )
    
    def centikelvin_to_celsius(self, t):
        """Convertir centikelvin en celsius"""
        return (t - 27315) / 100
    
    def start_capture(self):
        """Démarrer la capture thermique"""
        if self.is_running:
            logger.warning("La capture est déjà en cours")
            return False
        
        # Ouvrir la caméra
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            logger.error("Impossible d'ouvrir la caméra thermique")
            self.websocket_manager.broadcast('thermal_error', {
                'error': 'Impossible d\'ouvrir la caméra thermique',
                'timestamp': datetime.now().isoformat()
            })
            return False
        
        # MODE DEV : Si pas de caméra, décommenter les lignes suivantes
        # self.cap = None  # Pas de vraie caméra
        # self.dev_mode = True
        # logger.info("Mode développement activé - Données simulées")
        
        self.is_running = True
        self.capture_thread = threading.Thread(target=self._capture_loop)
        self.capture_thread.daemon = True
        self.capture_thread.start()
        
        logger.info("Capture thermique démarrée")
        return True
    
    def stop_capture(self):
        """Arrêter la capture thermique"""
        if not self.is_running:
            return False
        
        # Signaler l'arrêt
        self.is_running = False
        
        # Arrêter l'enregistrement si actif
        if self.is_recording:
            self.stop_recording()
        
        # Attendre la fin du thread
        if self.capture_thread:
            self.capture_thread.join(timeout=2)
            self.capture_thread = None
        
        # Libérer la caméra
        if self.cap:
            self.cap.release()
            self.cap = None
        
        # Réinitialiser le mode dev
        if hasattr(self, 'dev_mode'):
            self.dev_mode = False
        
        logger.info("Capture thermique arrêtée")
        return True
    
    def start_recording(self):
        """Démarrer l'enregistrement CSV"""
        if self.is_recording:
            return False
        
        # Créer le nom de fichier
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"thermal_recording_{timestamp}.csv"
        self.current_recording_file = self.recordings_dir / filename
        
        # Réinitialiser les headers pour le nouveau fichier
        self.csv_headers = None
        self.header_written = False
        self.recording_line_count = 0
        self.is_recording = True
        
        # Notifier le client
        self.websocket_manager.broadcast('thermal_recording_started', {
            'filename': filename,
            'timestamp': datetime.now().isoformat()
        })
        
        logger.info(f"Enregistrement démarré: {filename}")
        return True
    
    def stop_recording(self):
        """Arrêter l'enregistrement CSV"""
        if not self.is_recording:
            return False
        
        self.is_recording = False
        self.header_written = False
        filename = self.current_recording_file.name if self.current_recording_file else "unknown"
        
        # Notifier le client
        self.websocket_manager.broadcast('thermal_recording_stopped', {
            'filename': filename,
            'lines': self.recording_line_count,
            'timestamp': datetime.now().isoformat()
        })
        
        self.current_recording_file = None
        logger.info(f"Enregistrement arrêté: {filename} ({self.recording_line_count} lignes)")
        return True
    
    def _capture_loop(self):
        """Boucle de capture principale"""
        frame_count = 0
        last_emit_time = time.time()
        emit_interval = 0.1  # Émettre toutes les 100ms
        
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                logger.error("Erreur de lecture vidéo")
                break
            
            # MODE DEV : Si pas de caméra, décommenter ce bloc
            # if hasattr(self, 'dev_mode') and self.dev_mode:
            #     # Créer une image noire avec du texte
            #     frame = np.zeros((480, 640, 3), dtype=np.uint8)
            #     cv2.putText(frame, "MODE DEV - Pas de camera", (150, 240),
            #                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            #     ret = True
            
            # Redimensionner l'image
            frame = cv2.resize(frame, None, fx=4, fy=4)
            ih, iw, _ = frame.shape
            
            # Conversion en RGB pour MediaPipe
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(img_rgb)
            
            # Simuler les données thermiques (à remplacer par de vraies données)
            thermal_ck = np.random.randint(28000, 31000, size=(ih, iw)).astype(np.uint16)
            
            # Données de température à envoyer
            temperature_data = {}
            
            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    # Dessiner les landmarks
                    mp.solutions.drawing_utils.draw_landmarks(
                        frame,
                        face_landmarks,
                        self.mp_face_mesh.FACEMESH_TESSELATION,
                        landmark_drawing_spec=None,
                        connection_drawing_spec=mp.solutions.drawing_styles.get_default_face_mesh_tesselation_style()
                    )
                    
                    # Préparer les données pour l'enregistrement
                    timestamp = datetime.now()
                    row_data = [timestamp]
                    
                    # Si on enregistre et qu'on n'a pas encore construit les headers
                    if self.is_recording and not self.header_written:
                        # Initialiser les headers avec Timestamp et points d'intérêt
                        self.csv_headers = ["Timestamp"] + list(self.landmark_points.keys())
                    
                    # 1. D'abord les points d'intérêt
                    for label, idx in self.landmark_points.items():
                        lm = face_landmarks.landmark[idx]
                        x, y = int(lm.x * iw), int(lm.y * ih)
                        
                        # Dessiner le point
                        cv2.circle(frame, (x, y), 5, (0, 255, 0), -1)
                        
                        # Calculer la température
                        if 0 <= y < ih and 0 <= x < iw:
                            temp = round(float(self.centikelvin_to_celsius(thermal_ck[y, x])), 2)
                        else:
                            temp = None
                        
                        temperature_data[label] = temp
                        row_data.append(temp)
                    
                    # 2. Ensuite TOUS les autres landmarks
                    landmarks_added = 0
                    for i, lm in enumerate(face_landmarks.landmark):
                        # Éviter les doublons (points déjà inclus dans landmark_points)
                        if i in self.landmark_points.values():
                            continue
                        
                        x, y = int(lm.x * iw), int(lm.y * ih)
                        if 0 <= y < ih and 0 <= x < iw:
                            temp = round(float(self.centikelvin_to_celsius(thermal_ck[y, x])), 2)
                        else:
                            temp = None
                        
                        row_data.append(temp)
                        landmarks_added += 1
                        
                        # Ajouter au header si on n'a pas encore écrit les headers
                        if self.is_recording and not self.header_written:
                            self.csv_headers.append(f"L{i}")
                    
                    # Écrire l'entête une seule fois
                    if self.is_recording and not self.header_written and self.current_recording_file:
                        with open(self.current_recording_file, mode='w', newline='') as file:
                            writer = csv.writer(file, delimiter=';')
                            writer.writerow(self.csv_headers)
                        self.header_written = True
                        
                        # Log du nombre total de points
                        total_points = len(self.landmark_points) + landmarks_added
                        logger.info(f"Headers écrits : {len(self.csv_headers)} colonnes")
                        logger.info(
                            f"Enregistrement de {total_points} points au total (8 points d'intérêt + {landmarks_added} landmarks)")
                    
                    # Écrire la ligne de données
                    if self.is_recording and self.header_written and self.current_recording_file:
                        with open(self.current_recording_file, mode='a', newline='') as file:
                            writer = csv.writer(file, delimiter=';')
                            writer.writerow(row_data)
                        self.recording_line_count += 1
            
            # Émettre les données périodiquement
            current_time = time.time()
            if current_time - last_emit_time >= emit_interval:
                # Encoder l'image en JPEG
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                
                # Émettre l'image
                self.websocket_manager.emit_to_module('thermal_camera', 'thermal_frame', {
                    'image': frame_base64,
                    'timestamp': datetime.now().isoformat()
                })
                
                # Émettre les données de température
                self.websocket_manager.emit_to_module('thermal_camera', 'thermal_temperature_data', {
                    'temperatures': temperature_data,
                    'recording_lines': self.recording_line_count if self.is_recording else 0,
                    'timestamp': datetime.now().isoformat()
                })
                
                last_emit_time = current_time
            
            frame_count += 1
            
            # Limiter le FPS
            time.sleep(0.033)  # ~30 FPS
        
        logger.info("Boucle de capture terminée")
    
    def _write_csv_row(self, row_data):
        """Écrire une ligne dans le fichier CSV"""
        if not self.current_recording_file:
            return
        
        # Écrire les headers lors de la première ligne
        if self.recording_line_count == 0 and self.csv_headers:
            with open(self.current_recording_file, 'w', newline='') as file:
                writer = csv.writer(file, delimiter=';')
                writer.writerow(self.csv_headers)
        
        # Écrire la ligne de données
        with open(self.current_recording_file, 'a', newline='') as file:
            writer = csv.writer(file, delimiter=';')
            writer.writerow(row_data)
        
        self.recording_line_count += 1
    
    def get_recordings_list(self):
        """Obtenir la liste des enregistrements"""
        recordings = []
        
        for file_path in self.recordings_dir.glob("*.csv"):
            file_stat = file_path.stat()
            recordings.append({
                'filename': file_path.name,
                'size': self._format_file_size(file_stat.st_size),
                'date': datetime.fromtimestamp(file_stat.st_mtime).strftime('%d/%m/%Y %H:%M')
            })
        
        # Trier par date de modification (plus récent en premier)
        recordings.sort(key=lambda x: x['date'], reverse=True)
        
        return recordings
    
    def delete_recording(self, filename):
        """Supprimer un enregistrement"""
        file_path = self.recordings_dir / filename
        
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
            logger.info(f"Enregistrement supprimé: {filename}")
            return True
        
        return False
    
    def _format_file_size(self, size):
        """Formater la taille du fichier"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


def register_thermal_websocket_events(websocket_manager, thermal_module):
    """Enregistrer les événements WebSocket pour le module thermique"""
    
    def handle_start_capture(data):
        """Démarrer la capture"""
        success = thermal_module.start_capture()
        if success:
            websocket_manager.emit_to_module('thermal_camera', 'capture_started', {
                'status': 'capturing',
                'timestamp': datetime.now().isoformat()
            })
    
    def handle_stop_capture(data):
        """Arrêter la capture"""
        success = thermal_module.stop_capture()
        if success:
            websocket_manager.emit_to_module('thermal_camera', 'capture_stopped', {
                'status': 'idle',
                'timestamp': datetime.now().isoformat()
            })
    
    def handle_start_recording(data):
        """Démarrer l'enregistrement"""
        thermal_module.start_recording()
    
    def handle_stop_recording(data):
        """Arrêter l'enregistrement"""
        thermal_module.stop_recording()
    
    def handle_get_recordings(data):
        """Obtenir la liste des enregistrements"""
        logger.info("Demande de liste des enregistrements reçue")
        recordings = thermal_module.get_recordings_list()
        websocket_manager.emit_to_current_client('thermal_recordings_list', {
            'recordings': recordings,
            'count': len(recordings),
            'timestamp': datetime.now().isoformat()
        })
        logger.info(f"{len(recordings)} enregistrements trouvés")
    
    def handle_delete_recording(data):
        """Supprimer un enregistrement"""
        filename = data.get('filename')
        if filename:
            success = thermal_module.delete_recording(filename)
            if success:
                # Renvoyer la liste mise à jour
                recordings = thermal_module.get_recordings_list()
                websocket_manager.emit_to_current_client('thermal_recordings_list', {
                    'recordings': recordings,
                    'timestamp': datetime.now().isoformat()
                })
    
    # Enregistrer les événements
    thermal_events = {
        'start_capture': handle_start_capture,
        'stop_capture': handle_stop_capture,
        'start_recording': handle_start_recording,
        'stop_recording': handle_stop_recording,
        'get_recordings': handle_get_recordings,
        'delete_recording': handle_delete_recording
    }
    
    websocket_manager.register_module_events('thermal_camera', thermal_events)
    logger.info("Événements WebSocket du module thermique enregistrés")


def init_thermal_module(app, websocket_manager):
    """Initialiser le module thermique"""
    thermal_module = ThermalCameraModule(app, websocket_manager)
    return thermal_module