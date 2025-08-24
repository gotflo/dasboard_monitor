#!/usr/bin/env python3
"""
Module Caméra Thermique - Backend Amélioré
Gestion de la caméra thermique avec tracking CSRT et analyse faciale
Avec filtres Kalman 2D et EMA pour stabilisation
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


class KalmanFilter2D:
    """Filtre de Kalman 2D pour stabiliser les positions des points faciaux"""
    
    def __init__(self):
        # Initialisation du filtre de Kalman OpenCV
        self.kf = cv2.KalmanFilter(4, 2)  # 4 états (x, y, vx, vy), 2 mesures (x, y)
        
        # Matrice de transition d'état
        self.kf.transitionMatrix = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ], dtype=np.float32)
        
        # Matrice de mesure
        self.kf.measurementMatrix = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ], dtype=np.float32)
        
        # Bruit de processus (réduit pour plus de stabilité)
        self.kf.processNoiseCov = np.eye(4, dtype=np.float32) * 0.005
        
        # Bruit de mesure (réduit pour plus de précision)
        self.kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * 0.05
        
        # État initial
        self.initialized = False
    
    def update(self, x, y):
        """Mettre à jour le filtre avec une nouvelle mesure"""
        measurement = np.array([[x], [y]], dtype=np.float32)
        
        if not self.initialized:
            # Initialiser l'état avec la première mesure
            self.kf.statePre = np.array([[x], [y], [0], [0]], dtype=np.float32)
            self.kf.statePost = np.array([[x], [y], [0], [0]], dtype=np.float32)
            self.initialized = True
        
        # Prédiction
        prediction = self.kf.predict()
        
        # Correction
        self.kf.correct(measurement)
        
        # Retourner la position filtrée
        return int(prediction[0]), int(prediction[1])
    
    def reset(self):
        """Réinitialiser le filtre"""
        self.initialized = False


class EMAFilter:
    """Filtre de moyenne mobile exponentielle pour lisser les températures"""
    
    def __init__(self, alpha=0.3):
        self.alpha = alpha  # Facteur de lissage (0 < alpha < 1)
        self.value = None
    
    def update(self, new_value):
        """Mettre à jour le filtre avec une nouvelle valeur"""
        if new_value is None:
            return self.value
        
        if self.value is None:
            self.value = new_value
        else:
            self.value = self.alpha * new_value + (1 - self.alpha) * self.value
        
        return self.value
    
    def reset(self):
        """Réinitialiser le filtre"""
        self.value = None


class FaceTracker:
    """Gestionnaire de tracking de visage avec CSRT"""
    
    def __init__(self):
        self.tracker = None
        self.is_tracking = False
        self.bbox = None
        self.confidence_threshold = 0.5
        self.lost_track_frames = 0
        self.max_lost_frames = 30  # Plus tolérant avant de perdre le tracking
    
    def init_tracker(self, frame, bbox):
        """Initialiser le tracker avec une bounding box"""
        try:
            # Créer un nouveau tracker CSRT avec des paramètres optimisés
            self.tracker = cv2.TrackerCSRT_create()
            
            # Configurer les paramètres du tracker pour plus de stabilité
            # Note: Ces paramètres peuvent nécessiter OpenCV 4.5+
            try:
                params = cv2.TrackerCSRT_Params()
                params.use_gray = False  # Utiliser la couleur
                params.use_channel_weights = True
                params.filter_lr = 0.02  # Learning rate plus faible pour plus de stabilité
                params.weights_lr = 0.02
                params.num_hog_channels_used = 18
                params.admm_iterations = 4
                params.histogram_bins = 16
                params.histogram_lr = 0.04
                params.background_ratio = 2
                params.number_of_scales = 33
                params.scale_sigma_factor = 0.25
                params.scale_model_max_area = 512
                params.scale_lr = 0.025
                params.scale_step = 1.02
                # Recréer le tracker avec les nouveaux paramètres
                self.tracker = cv2.TrackerCSRT_create(params)
            except:
                # Si les paramètres ne sont pas disponibles, utiliser le tracker par défaut
                pass
            
            # S'assurer que la bbox est valide et dans les limites
            x, y, w, h = bbox
            ih, iw = frame.shape[:2]
            
            # Vérifier les limites
            x = int(max(0, min(x, iw - 10)))
            y = int(max(0, min(y, ih - 10)))
            w = int(min(w, iw - x))
            h = int(min(h, ih - y))
            
            # Vérifier la taille minimale
            if w < 30 or h < 30:
                logger.warning(f"Bounding box trop petite: {w}x{h}")
                return False
            
            bbox = (x, y, w, h)
            
            # Initialiser le tracker
            success = self.tracker.init(frame, bbox)
            if success:
                self.bbox = bbox
                self.is_tracking = True
                self.lost_track_frames = 0
                logger.info(f"Tracker CSRT initialisé avec succès - bbox: {bbox}")
                return True
            else:
                logger.error("Échec de l'initialisation du tracker")
                self.reset()
                return False
        
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du tracker: {e}")
            self.reset()
            return False
    
    def update(self, frame):
        """Mettre à jour le tracker"""
        if not self.is_tracking or self.tracker is None:
            return False, None
        
        try:
            # Mettre à jour le tracker
            success, bbox = self.tracker.update(frame)
            
            if success and bbox is not None:
                # Vérifier que la bbox est valide
                x, y, w, h = bbox
                if w > 10 and h > 10:  # Taille minimale
                    self.bbox = bbox
                    self.lost_track_frames = 0
                    return True, bbox
                else:
                    # Bbox invalide
                    self.lost_track_frames += 1
            else:
                self.lost_track_frames += 1
            
            # Si on a perdu le tracking trop longtemps, réinitialiser
            if self.lost_track_frames > self.max_lost_frames:
                logger.info(f"Tracking perdu depuis {self.lost_track_frames} frames, réinitialisation")
                self.reset()
            
            return False, self.bbox  # Retourner la dernière bbox connue
        
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du tracker: {e}")
            self.reset()
            return False, None
    
    def reset(self):
        """Réinitialiser le tracker"""
        self.tracker = None
        self.is_tracking = False
        self.bbox = None
        self.lost_track_frames = 0
        logger.info("Tracker réinitialisé")


class ThermalCameraModule:
    """Module de gestion de la caméra thermique avec détection faciale et tracking CSRT"""
    
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
        
        # Tracking
        self.face_tracker = FaceTracker()
        self.tracking_mode = "detection"  # "detection" ou "tracking"
        self.last_face_landmarks = None
        self.face_detection_interval = 150  # 5 secondes à 30 FPS pour recalibrage
        
        # Optimisation GPU
        self.use_gpu = self._check_gpu_availability()
        
        # MediaPipe FaceMesh avec configuration optimisée
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.3,  # Plus sensible pour ne pas perdre le visage
            min_tracking_confidence=0.3  # Plus sensible pour maintenir le tracking
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
        
        # Filtres de stabilisation
        self.kalman_filters = {}  # Un filtre Kalman par point facial
        self.ema_filters = {}  # Un filtre EMA par point pour la température
        
        # Initialiser les filtres pour chaque point d'intérêt
        for label in self.landmark_points:
            self.kalman_filters[label] = KalmanFilter2D()
            self.ema_filters[label] = EMAFilter(alpha=0.3)
        
        # Initialiser aussi les filtres pour tous les autres landmarks
        for i in range(478):  # 468 landmarks + 10 iris
            if i not in self.landmark_points.values():
                key = f"L{i}"
                self.kalman_filters[key] = KalmanFilter2D()
                self.ema_filters[key] = EMAFilter(alpha=0.3)
        
        # CSV headers
        self.csv_headers = None
        self.header_written = False
        
        # Optimisation des performances
        cv2.setNumThreads(4)  # Utiliser plusieurs threads pour OpenCV
        cv2.setUseOptimized(True)  # Activer les optimisations CPU
        
        # Enregistrer les routes
        self._register_routes()
        
        logger.info(f"Module Caméra Thermique initialisé (GPU: {self.use_gpu})")
    
    def _check_gpu_availability(self):
        """Vérifier si un GPU est disponible pour l'accélération"""
        try:
            # Vérifier CUDA pour OpenCV
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                logger.info("GPU CUDA détecté pour OpenCV")
                return True
        except:
            pass
        
        # Sinon, utiliser le CPU optimisé
        logger.info("Utilisation du CPU optimisé")
        return False
    
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
    
    def _get_face_bounding_box(self, landmarks, image_shape):
        """Calculer la bounding box du visage à partir des landmarks"""
        ih, iw = image_shape[:2]
        
        # Obtenir les coordonnées x et y de tous les landmarks
        x_coords = [int(lm.x * iw) for lm in landmarks]
        y_coords = [int(lm.y * ih) for lm in landmarks]
        
        # Calculer la bounding box avec une marge généreuse
        margin = 50  # Marge plus importante pour ne pas perdre le visage
        x_min = max(0, min(x_coords) - margin)
        y_min = max(0, min(y_coords) - margin)
        x_max = min(iw, max(x_coords) + margin)
        y_max = min(ih, max(y_coords) + margin)
        
        # S'assurer que la bbox a une taille minimale
        min_size = 100
        width = x_max - x_min
        height = y_max - y_min
        
        if width < min_size:
            center_x = (x_min + x_max) // 2
            x_min = max(0, center_x - min_size // 2)
            x_max = min(iw, center_x + min_size // 2)
        
        if height < min_size:
            center_y = (y_min + y_max) // 2
            y_min = max(0, center_y - min_size // 2)
            y_max = min(ih, center_y + min_size // 2)
        
        # Retourner au format (x, y, width, height)
        return (x_min, y_min, x_max - x_min, y_max - y_min)
    
    def _interpolate_landmarks(self, current_bbox, previous_landmarks, image_shape):
        """Interpoler les positions des landmarks basées sur le déplacement de la bbox"""
        if previous_landmarks is None or current_bbox is None:
            return None
        
        # Calculer le décalage de la bbox
        x, y, w, h = current_bbox
        cx = x + w / 2
        cy = y + h / 2
        
        # Créer des landmarks interpolés (simplifiés pour la démo)
        # Dans une vraie implémentation, on pourrait utiliser une transformation plus sophistiquée
        return previous_landmarks
    
    def centikelvin_to_celsius(self, t):
        """Convertir centikelvin en celsius"""
        return (t - 27315) / 100
    
    def get_thermal_zone_average(self, thermal_ck, x, y, zone_size=5):
        """
        Calculer la température moyenne d'une zone autour d'un point
        zone_size : taille de la zone (5 pour une zone 5x5)
        """
        ih, iw = thermal_ck.shape
        half_size = zone_size // 2
        
        # Définir les limites de la zone
        x_min = max(0, x - half_size)
        x_max = min(iw - 1, x + half_size)
        y_min = max(0, y - half_size)
        y_max = min(ih - 1, y + half_size)
        
        # Extraire la zone et calculer la moyenne
        zone = thermal_ck[y_min:y_max + 1, x_min:x_max + 1]
        
        if zone.size > 0:
            avg_ck = np.mean(zone)
            return self.centikelvin_to_celsius(avg_ck)
        else:
            return None
    
    def start_capture(self):
        """Démarrer la capture thermique"""
        if self.is_running:
            logger.warning("La capture est déjà en cours")
            return False
        
        # Ouvrir la caméra avec configuration optimisée
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            logger.error("Impossible d'ouvrir la caméra thermique")
            self.websocket_manager.broadcast('thermal_error', {
                'error': 'Impossible d\'ouvrir la caméra thermique',
                'timestamp': datetime.now().isoformat()
            })
            return False
        
        # Configuration optimisée de la caméra
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Réduire le buffer pour moins de latence
        self.cap.set(cv2.CAP_PROP_FPS, 30)  # Fixer le FPS
        
        self.is_running = True
        self.capture_thread = threading.Thread(target=self._capture_loop)
        self.capture_thread.daemon = True
        self.capture_thread.start()
        
        logger.info("Capture thermique démarrée avec tracking CSRT")
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
        
        # Réinitialiser les filtres et le tracker
        self.face_tracker.reset()
        self.last_face_landmarks = None
        self.tracking_mode = "detection"
        
        for kf in self.kalman_filters.values():
            kf.reset()
        for ef in self.ema_filters.values():
            ef.reset()
        
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
        """Boucle de capture principale avec tracking CSRT et stabilisation"""
        frame_count = 0
        last_emit_time = time.time()
        last_fps_time = time.time()
        fps = 0
        emit_interval = 0.033  # ~30 FPS pour plus de fluidité
        last_detection_frame = 0  # Pour le recalibrage périodique
        recalibration_interval = 150  # 5 secondes à 30 FPS
        total_frames = 0  # Compteur total de frames
        
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                logger.error("Erreur de lecture vidéo")
                break
            
            # Redimensionner l'image (optimisé)
            frame = cv2.resize(frame, None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
            ih, iw, _ = frame.shape
            
            # Simuler les données thermiques (à remplacer par de vraies données)
            thermal_ck = np.random.randint(28000, 31000, size=(ih, iw)).astype(np.uint16)
            
            # Données de température à envoyer
            temperature_data = {}
            face_landmarks = None
            need_detection = False
            
            # LOGIQUE DE TRACKING AMÉLIORÉE
            
            # Vérifier si on doit faire un recalibrage périodique
            if self.face_tracker.is_tracking and (total_frames - last_detection_frame) > recalibration_interval:
                need_detection = True
                logger.debug(f"Recalibrage périodique après {recalibration_interval} frames")
            
            # Mode 1: Tracking actif avec CSRT
            if self.face_tracker.is_tracking and not need_detection:
                success, bbox = self.face_tracker.update(frame)
                
                if success and bbox is not None:
                    # Le tracking fonctionne, dessiner la bbox
                    x, y, w, h = [int(v) for v in bbox]
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.putText(frame, "TRACKING ACTIF", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    # Utiliser les derniers landmarks connus
                    if self.last_face_landmarks:
                        face_landmarks = self.last_face_landmarks
                else:
                    # Le tracking a échoué, repasser en mode détection
                    logger.info("Tracking perdu, retour en mode détection")
                    self.face_tracker.reset()
                    need_detection = True
            else:
                need_detection = True
            
            # Mode 2: Détection avec MediaPipe (seulement si nécessaire)
            if need_detection:
                # Conversion en RGB pour MediaPipe
                img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self.face_mesh.process(img_rgb)
                
                if results.multi_face_landmarks:
                    face_landmarks = results.multi_face_landmarks[0]
                    self.last_face_landmarks = face_landmarks
                    last_detection_frame = total_frames
                    
                    # Calculer la bounding box
                    bbox = self._get_face_bounding_box(face_landmarks.landmark, frame.shape)
                    
                    # Initialiser ou réinitialiser le tracker
                    if not self.face_tracker.is_tracking or need_detection:
                        # Réinitialiser le tracker même s'il était actif (pour recalibrage)
                        self.face_tracker.reset()
                        if self.face_tracker.init_tracker(frame, bbox):
                            logger.info("Tracker CSRT (ré)initialisé avec succès")
                            cv2.putText(frame, "VISAGE VERROUILLE!", (10, 60),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                else:
                    # Pas de visage détecté
                    face_landmarks = None
                    if not self.face_tracker.is_tracking:
                        cv2.putText(frame, "RECHERCHE VISAGE...", (10, 30),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # TRAITEMENT DES LANDMARKS (si disponibles)
            if face_landmarks:
                # Dessiner le mesh facial de manière stable
                # Toujours dessiner si on a des landmarks valides
                mp.solutions.drawing_utils.draw_landmarks(
                    frame,
                    face_landmarks,
                    self.mp_face_mesh.FACEMESH_TESSELATION,
                    landmark_drawing_spec=mp.solutions.drawing_styles.DrawingSpec(
                        color=(0, 255, 0), thickness=1, circle_radius=2
                    ),
                    connection_drawing_spec=mp.solutions.drawing_styles.DrawingSpec(
                        color=(221, 221, 221), thickness=1
                    )
                )
                
                # Préparer les données pour l'enregistrement
                timestamp = datetime.now()
                row_data = [timestamp]
                
                # Si on enregistre et qu'on n'a pas encore construit les headers
                if self.is_recording and not self.header_written:
                    # Initialiser les headers avec Timestamp et points d'intérêt
                    self.csv_headers = ["Timestamp"] + list(self.landmark_points.keys())
                
                # 1. D'abord les points d'intérêt avec stabilisation
                for label, idx in self.landmark_points.items():
                    lm = face_landmarks.landmark[idx]
                    x_raw, y_raw = int(lm.x * iw), int(lm.y * ih)
                    
                    # Appliquer le filtre de Kalman pour stabiliser la position
                    x_filtered, y_filtered = self.kalman_filters[label].update(x_raw, y_raw)
                    
                    # Dessiner le point stabilisé
                    cv2.circle(frame, (x_filtered, y_filtered), 5, (0, 255, 0), -1)
                    
                    # Calculer la température moyenne de la zone 5x5
                    if 0 <= y_filtered < ih and 0 <= x_filtered < iw:
                        temp_raw = self.get_thermal_zone_average(thermal_ck, x_filtered, y_filtered, zone_size=5)
                        if temp_raw is not None:
                            # Appliquer le filtre EMA pour lisser la température
                            temp_filtered = self.ema_filters[label].update(temp_raw)
                            temp = round(float(temp_filtered), 2)
                        else:
                            temp = None
                    else:
                        temp = None
                    
                    temperature_data[label] = temp
                    row_data.append(temp)
                
                # 2. Ensuite TOUS les autres landmarks avec stabilisation (optionnel, pour performance)
                if self.is_recording:  # Seulement si on enregistre
                    landmarks_added = 0
                    for i, lm in enumerate(face_landmarks.landmark):
                        # Éviter les doublons
                        if i in self.landmark_points.values():
                            continue
                        
                        x_raw, y_raw = int(lm.x * iw), int(lm.y * ih)
                        
                        # Clé pour ce landmark
                        key = f"L{i}"
                        
                        # Appliquer le filtre de Kalman
                        x_filtered, y_filtered = self.kalman_filters[key].update(x_raw, y_raw)
                        
                        # Calculer la température avec zone moyenne et filtre EMA
                        if 0 <= y_filtered < ih and 0 <= x_filtered < iw:
                            temp_raw = self.get_thermal_zone_average(thermal_ck, x_filtered, y_filtered, zone_size=5)
                            if temp_raw is not None:
                                temp_filtered = self.ema_filters[key].update(temp_raw)
                                temp = round(float(temp_filtered), 2)
                            else:
                                temp = None
                        else:
                            temp = None
                        
                        row_data.append(temp)
                        landmarks_added += 1
                        
                        # Ajouter au header si nécessaire
                        if self.is_recording and not self.header_written:
                            self.csv_headers.append(key)
                    
                    # Écrire l'entête une seule fois
                    if self.is_recording and not self.header_written and self.current_recording_file:
                        with open(self.current_recording_file, mode='w', newline='') as file:
                            writer = csv.writer(file, delimiter=';')
                            writer.writerow(self.csv_headers)
                        self.header_written = True
                        
                        # Log du nombre total de points
                        total_points = len(self.landmark_points) + landmarks_added
                        logger.info(f"Headers écrits : {len(self.csv_headers)} colonnes")
                        logger.info(f"Enregistrement de {total_points} points stabilisés")
                    
                    # Écrire la ligne de données
                    if self.is_recording and self.header_written and self.current_recording_file:
                        with open(self.current_recording_file, mode='a', newline='') as file:
                            writer = csv.writer(file, delimiter=';')
                            writer.writerow(row_data)
                        self.recording_line_count += 1
            
            # Calculer le FPS réel
            current_time = time.time()
            if current_time - last_fps_time >= 1.0:
                fps = frame_count / (current_time - last_fps_time)
                last_fps_time = current_time
                frame_count = 0
            
            # Afficher le mode actuel et les FPS avec plus d'informations
            
            # Afficher le statut du tracking
            if self.face_tracker.is_tracking:
                status_color = (0, 255, 0)  # Vert
                mode_text = "TRACKING CSRT ACTIF"
            else:
                status_color = (0, 165, 255)  # Orange
                mode_text = "DETECTION MEDIAPIPE"
            
            # Zone d'information en haut
            cv2.rectangle(frame, (0, 0), (350, 90), (0, 0, 0), -1)
            cv2.putText(frame, mode_text, (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
            
            # Afficher le temps avant recalibrage
            if self.face_tracker.is_tracking:
                frames_until_recalib = max(0, recalibration_interval - (total_frames - last_detection_frame))
                seconds_until_recalib = frames_until_recalib / 30.0
                cv2.putText(frame, f"Recalibrage dans: {seconds_until_recalib:.1f}s", (10, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # FPS et compteur de frames total
            cv2.putText(frame, f"FPS: {int(fps)}", (10, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Émettre les données périodiquement
            emit_current_time = time.time()
            if emit_current_time - last_emit_time >= emit_interval:
                # Encoder l'image en JPEG (qualité optimisée pour performance)
                encode_param = [cv2.IMWRITE_JPEG_QUALITY, 75]
                _, buffer = cv2.imencode('.jpg', frame, encode_param)
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                
                # Émettre l'image avec le masque facial
                self.websocket_manager.emit_to_module('thermal_camera', 'thermal_frame', {
                    'image': frame_base64,
                    'tracking_mode': 'csrt' if self.face_tracker.is_tracking else 'detection',
                    'timestamp': datetime.now().isoformat()
                })
                
                # Émettre les données de température stabilisées
                self.websocket_manager.emit_to_module('thermal_camera', 'thermal_temperature_data', {
                    'temperatures': temperature_data,
                    'recording_lines': self.recording_line_count if self.is_recording else 0,
                    'timestamp': datetime.now().isoformat()
                })
                
                last_emit_time = emit_current_time
            
            frame_count += 1
            total_frames += 1
            
            # Limiter le FPS pour économiser les ressources
            time.sleep(0.025)  # ~40 FPS max
        
        logger.info("Boucle de capture terminée")
    
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