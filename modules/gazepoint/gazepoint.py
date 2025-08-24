#!/usr/bin/env python3
"""
Module Gazepoint - Backend
Gestion du tracking oculaire avec Gazepoint
Version complète avec analyses avancées et enregistrement robuste
"""

import socket
import xml.etree.ElementTree as ET
import threading
import time
import csv
import json
import os
import math
from datetime import datetime
from pathlib import Path
import logging
from collections import deque

logger = logging.getLogger(__name__)


class GazepointModule:
    """Module de gestion du tracking oculaire Gazepoint avec analyses avancées"""
    
    def __init__(self, app, websocket_manager):
        self.app = app
        self.websocket_manager = websocket_manager
        self.is_connected = False
        self.is_recording = False
        self.is_tracking = False
        self.socket = None
        self.receive_thread = None
        self.recording_file = None
        self.recording_writer = None
        self.recording_line_count = 0
        
        # Configuration réseau
        self.host = '127.0.0.1'  # Par défaut localhost
        self.port = 4242
        
        # Répertoire des enregistrements
        self.recordings_dir = Path('recordings/gazepoint')
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration complète des données à recevoir
        self.data_config = {
            # Données essentielles
            'ENABLE_SEND_DATA': '1',  # Activer l'envoi de données
            'ENABLE_SEND_COUNTER': '1',  # Compteur de frames
            'ENABLE_SEND_TIME': '1',  # Timestamp en secondes
            'ENABLE_SEND_TIME_TICK': '1',  # Timestamp haute résolution
            
            # Points de regard (POG = Point Of Gaze)
            'ENABLE_SEND_POG_FIX': '1',  # Point de regard fixe (fixations)
            'ENABLE_SEND_POG_LEFT': '1',  # Point de regard œil gauche
            'ENABLE_SEND_POG_RIGHT': '1',  # Point de regard œil droit
            'ENABLE_SEND_POG_BEST': '1',  # Meilleur point de regard (moyenne)
            
            # Données pupillaires
            'ENABLE_SEND_PUPIL_LEFT': '1',  # Diamètre pupille gauche
            'ENABLE_SEND_PUPIL_RIGHT': '1',  # Diamètre pupille droite
            
            # Position 3D des yeux
            'ENABLE_SEND_EYE_LEFT': '1',  # Position 3D œil gauche
            'ENABLE_SEND_EYE_RIGHT': '1',  # Position 3D œil droit
            
            # Données additionnelles
            'ENABLE_SEND_CURSOR': '1',  # Position du curseur souris
            'ENABLE_SEND_BLINK': '1',  # Détection de clignements
            'ENABLE_SEND_USER_DATA': '1'  # Données utilisateur
        }
        
        # Paramètres de configuration du tracker
        self.tracking_config = {
            'SET_TRACKER_SCREEN_SIZE': '1920x1080',  # Résolution d'écran
            'SET_CALIBRATION_POINTS': '9',  # Nombre de points de calibration
            'SET_CALIBRATION_SPEED': 'MEDIUM',  # Vitesse de calibration
            'SET_FILTER_LEVEL': 'MEDIUM',  # Niveau de filtrage
            'SET_GAZE_BOUNDARY': 'SCREEN'  # Limites du regard
        }
        
        # Données actuelles avec structure complète
        self.current_data = {
            'gaze_x': 0.5,
            'gaze_y': 0.5,
            'gaze_valid': False,
            'left_eye': {
                'x': 0, 'y': 0, 'pupil': 0, 'valid': False, 'closed': False,
                'position_3d': {'x': 0, 'y': 0, 'z': 0}
            },
            'right_eye': {
                'x': 0, 'y': 0, 'pupil': 0, 'valid': False, 'closed': False,
                'position_3d': {'x': 0, 'y': 0, 'z': 0}
            },
            'fixation': {
                'x': 0.5, 'y': 0.5, 'duration': 0, 'id': 0, 'valid': False
            },
            'cursor': {'x': 0, 'y': 0, 'state': 0},
            'timestamp': 0,
            'counter': 0,
            'interpupillary_distance': 0,
            'convergence_angle': 0,
            'gaze_velocity': 0,
            'movement_type': 'unknown',
            'data_quality': 0
        }
        
        # Buffer pour calculs de vélocité et analyse
        self.data_buffer = {
            'gaze_positions': deque(maxlen=60),  # 1 seconde à 60Hz
            'blink_buffer': deque(maxlen=300),  # 5 secondes pour taux de clignement
            'fixation_buffer': deque(maxlen=100),  # Historique des fixations
            'last_timestamp': 0
        }
        
        # Statistiques en temps réel
        self.realtime_stats = {
            'saccade_count': 0,
            'average_fixation_duration': 0,
            'blink_rate': 0,  # Clignements par minute
            'data_quality': 1.0,  # Qualité globale des données (0-1)
            'tracking_ratio': 1.0,  # Ratio de frames valides
            'calibration_accuracy': {},  # Précision de calibration par point
            'total_fixations': 0
        }
        
        # Zones d'intérêt (AOI) avec temps cumulé
        self.aoi_zones = {
            'top_left': {'x': 0, 'y': 0, 'width': 0.33, 'height': 0.33, 'time': 0},
            'top_center': {'x': 0.33, 'y': 0, 'width': 0.34, 'height': 0.33, 'time': 0},
            'top_right': {'x': 0.67, 'y': 0, 'width': 0.33, 'height': 0.33, 'time': 0},
            'center_left': {'x': 0, 'y': 0.33, 'width': 0.33, 'height': 0.34, 'time': 0},
            'center': {'x': 0.33, 'y': 0.33, 'width': 0.34, 'height': 0.34, 'time': 0},
            'center_right': {'x': 0.67, 'y': 0.33, 'width': 0.33, 'height': 0.34, 'time': 0},
            'bottom_left': {'x': 0, 'y': 0.67, 'width': 0.33, 'height': 0.33, 'time': 0},
            'bottom_center': {'x': 0.33, 'y': 0.67, 'width': 0.34, 'height': 0.33, 'time': 0},
            'bottom_right': {'x': 0.67, 'y': 0.67, 'width': 0.33, 'height': 0.33, 'time': 0}
        }
        
        self.current_aoi = None
        self.last_aoi_update = time.time()
        
        # Calibration
        self.calibration_points = []
        self.is_calibrating = False
        
        # Historique pour calcul de vélocité
        self.last_gaze_position = None
        self.last_gaze_time = None
        
        # Enregistrer les routes API
        self._register_routes()
        
        logger.info(f"Module Gazepoint initialisé (serveur par défaut: {self.host}:{self.port})")
    
    def _register_routes(self):
        """Enregistrer les routes API Flask"""
        
        @self.app.route('/api/gazepoint/status')
        def get_gazepoint_status():
            """Obtenir le statut complet du module"""
            return json.dumps({
                'connected': self.is_connected,
                'tracking': self.is_tracking,
                'recording': self.is_recording,
                'current_data': self.current_data,
                'statistics': self.realtime_stats,
                'aoi_zones': self.aoi_zones,
                'timestamp': datetime.now().isoformat()
            })
        
        @self.app.route('/api/gazepoint/download/<filename>')
        def download_gazepoint_recording(filename):
            """Télécharger un fichier d'enregistrement CSV"""
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
    
    def connect(self, host=None, port=None):
        """Se connecter au serveur Gazepoint avec configuration complète"""
        if self.is_connected:
            logger.warning("Déjà connecté au serveur Gazepoint")
            return False
        
        # Utiliser les paramètres fournis ou les valeurs par défaut
        if host:
            self.host = host
        if port:
            self.port = port
        
        try:
            logger.info(f"Tentative de connexion à Gazepoint sur {self.host}:{self.port}")
            
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            
            self.socket.connect((self.host, self.port))
            
            logger.info(f"Socket connecté au serveur Gazepoint {self.host}:{self.port}")
            
            # Attendre un peu pour stabiliser la connexion
            time.sleep(0.2)
            
            # Configurer les paramètres de tracking
            for config, value in self.tracking_config.items():
                command = f'<SET ID="{config}" STATE="{value}" />'
                logger.debug(f"Configuration tracking: {command}")
                self._send_command(command)
                time.sleep(0.05)
            
            # Configurer les données à recevoir
            for config, state in self.data_config.items():
                command = f'<SET ID="{config}" STATE="{state}" />'
                logger.debug(f"Configuration données: {command}")
                self._send_command(command)
                time.sleep(0.05)
            
            # Demander les informations du tracker
            self._send_command('<GET ID="TRACKER_INFO" />')
            self._send_command('<GET ID="CALIBRATION_STATUS" />')
            self._send_command('<GET ID="SCREEN_SIZE" />')
            
            self.is_connected = True
            
            # Démarrer le thread de réception
            self.receive_thread = threading.Thread(target=self._receive_loop)
            self.receive_thread.daemon = True
            self.receive_thread.start()
            
            logger.info("Connexion Gazepoint établie avec succès")
            
            # Notifier le client avec les infos de configuration
            self.websocket_manager.broadcast('gazepoint_connected', {
                'status': 'connected',
                'config': {
                    'host': self.host,
                    'port': self.port,
                    'sampling_rate': '60Hz',
                    'data_channels': list(self.data_config.keys())
                },
                'timestamp': datetime.now().isoformat()
            })
            
            return True
        
        except socket.timeout:
            error_msg = "Timeout de connexion - Vérifiez que Gazepoint Control est lancé"
            logger.error(error_msg)
            self.websocket_manager.broadcast('gazepoint_error', {
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            })
            return False
        
        except ConnectionRefusedError:
            error_msg = "Connexion refusée - Vérifiez que le serveur Gazepoint est activé dans Gazepoint Control"
            logger.error(error_msg)
            self.websocket_manager.broadcast('gazepoint_error', {
                'error': error_msg,
                'timestamp': datetime.now().isoformat()
            })
            return False
        
        except Exception as e:
            logger.error(f"Erreur de connexion Gazepoint: {e}")
            self.websocket_manager.broadcast('gazepoint_error', {
                'error': f"Erreur de connexion: {str(e)}",
                'timestamp': datetime.now().isoformat()
            })
            return False
    
    def disconnect(self):
        """Se déconnecter proprement du serveur Gazepoint"""
        if not self.is_connected:
            return False
        
        self.is_connected = False
        
        # Arrêter l'enregistrement si actif
        if self.is_recording:
            self.stop_recording()
        
        # Fermer le socket
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        # Attendre la fin du thread de réception
        if self.receive_thread:
            self.receive_thread.join(timeout=2)
            self.receive_thread = None
        
        logger.info("Déconnecté du serveur Gazepoint")
        
        # Notifier le client
        self.websocket_manager.broadcast('gazepoint_disconnected', {
            'status': 'disconnected',
            'timestamp': datetime.now().isoformat()
        })
        
        return True
    
    def start_tracking(self):
        """Démarrer le tracking oculaire"""
        if not self.is_connected:
            logger.error("Non connecté au serveur Gazepoint")
            return False
        
        if self.is_tracking:
            return True
        
        # Activer l'envoi de données
        self._send_command('<SET ID="ENABLE_SEND_DATA" STATE="1" />')
        self.is_tracking = True
        
        logger.info("Tracking oculaire démarré")
        
        # Notifier le client
        self.websocket_manager.broadcast('gazepoint_tracking_started', {
            'status': 'tracking',
            'timestamp': datetime.now().isoformat()
        })
        
        return True
    
    def stop_tracking(self):
        """Arrêter le tracking oculaire"""
        if not self.is_tracking:
            return False
        
        # Désactiver l'envoi de données
        self._send_command('<SET ID="ENABLE_SEND_DATA" STATE="0" />')
        self.is_tracking = False
        
        logger.info("Tracking oculaire arrêté")
        
        # Notifier le client
        self.websocket_manager.broadcast('gazepoint_tracking_stopped', {
            'status': 'stopped',
            'timestamp': datetime.now().isoformat()
        })
        
        return True
    
    def start_recording(self):
        """Démarrer l'enregistrement CSV avec headers améliorés"""
        if self.is_recording:
            return False
        
        if not self.is_tracking:
            self.start_tracking()
        
        # Créer le fichier CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gazepoint_recording_{timestamp}.csv"
        self.recording_file = self.recordings_dir / filename
        
        # Ouvrir le fichier et écrire l'en-tête amélioré
        file_handle = open(self.recording_file, 'w', newline='', encoding='utf-8')
        self.recording_writer = csv.writer(file_handle, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        
        # En-tête complet avec descriptions
        headers = [
            'Timestamp',  # ISO format timestamp
            'Counter',  # Frame counter from Gazepoint
            'Time',  # Time in seconds from Gazepoint
            
            # Best Point of Gaze (average of both eyes)
            'GazeX',  # Normalized X coordinate (0-1)
            'GazeY',  # Normalized Y coordinate (0-1)
            'GazeValid',  # 1=valid, 0=invalid
            
            # Left eye data
            'LeftEyeX',  # Left eye gaze X (0-1)
            'LeftEyeY',  # Left eye gaze Y (0-1)
            'LeftPupilDiameter',  # Left pupil diameter in pixels
            'LeftEyeValid',  # 1=valid, 0=invalid
            
            # Right eye data
            'RightEyeX',  # Right eye gaze X (0-1)
            'RightEyeY',  # Right eye gaze Y (0-1)
            'RightPupilDiameter',  # Right pupil diameter in pixels
            'RightEyeValid',  # 1=valid, 0=invalid
            
            # Fixation data
            'FixationX',  # Fixation point X (0-1)
            'FixationY',  # Fixation point Y (0-1)
            'FixationDuration',  # Duration in seconds
            'FixationID',  # Unique fixation identifier
            'FixationValid',  # 1=valid fixation, 0=invalid
            
            # 3D eye position (in cm from tracker)
            'LeftEye3DX',  # Left eye X position in 3D space
            'LeftEye3DY',  # Left eye Y position in 3D space
            'LeftEye3DZ',  # Left eye Z position (distance)
            'RightEye3DX',  # Right eye X position in 3D space
            'RightEye3DY',  # Right eye Y position in 3D space
            'RightEye3DZ',  # Right eye Z position (distance)
            
            # Additional data
            'CursorX',  # Mouse cursor X (if enabled)
            'CursorY',  # Mouse cursor Y (if enabled)
            'CursorState',  # Mouse click state
            
            # Analysis data
            'CurrentAOI',  # Current Area of Interest
            'EyeDistance',  # Distance between eye gaze points
            'GazeVelocity',  # Gaze movement velocity
            'BlinkDetected',  # 1=blink detected, 0=no blink
            'MovementType',  # fixation/saccade/smooth_pursuit
            'DataQuality'  # Overall data quality (0-1)
        ]
        
        # Écrire les headers
        self.recording_writer.writerow(headers)
        
        self.is_recording = True
        self.recording_line_count = 0
        
        logger.info(f"Enregistrement démarré: {filename}")
        
        # Notifier le client
        self.websocket_manager.broadcast('gazepoint_recording_started', {
            'filename': filename,
            'timestamp': datetime.now().isoformat()
        })
        
        return True
    
    def stop_recording(self):
        """Arrêter l'enregistrement CSV"""
        if not self.is_recording:
            return False
        
        self.is_recording = False
        
        if self.recording_writer:
            # Fermer le fichier proprement
            self.recording_writer = None
        
        filename = self.recording_file.name if self.recording_file else "unknown"
        logger.info(f"Enregistrement arrêté: {filename} ({self.recording_line_count} lignes)")
        
        # Notifier le client
        self.websocket_manager.broadcast('gazepoint_recording_stopped', {
            'filename': filename,
            'lines': self.recording_line_count,
            'timestamp': datetime.now().isoformat()
        })
        
        self.recording_file = None
        return True
    
    def start_calibration(self):
        """Démarrer la procédure de calibration"""
        if not self.is_connected:
            return False
        
        self._send_command('<SET ID="CALIBRATE_SHOW" STATE="1" />')
        time.sleep(0.1)
        self._send_command('<SET ID="CALIBRATE_START" STATE="1" />')
        
        self.is_calibrating = True
        logger.info("Calibration démarrée")
        
        return True
    
    def _send_command(self, command):
        """Envoyer une commande au serveur Gazepoint"""
        if self.socket:
            try:
                full_command = f"{command}\r\n"
                logger.debug(f"Envoi commande: {repr(full_command)}")
                self.socket.sendall(full_command.encode('utf-8'))
                return True
            except Exception as e:
                logger.error(f"Erreur envoi commande: {e}")
                return False
        return False
    
    def _receive_loop(self):
        """Boucle de réception des données"""
        buffer = ""
        last_emit_time = time.time()
        emit_interval = 0.05  # Émettre toutes les 50ms
        
        while self.is_connected:
            try:
                # Recevoir des données
                data = self.socket.recv(4096)
                if not data:
                    break
                
                buffer += data.decode('utf-8', errors='ignore')
                
                # Traiter les lignes complètes
                while '\r\n' in buffer:
                    line, buffer = buffer.split('\r\n', 1)
                    if line.strip():
                        self._process_data(line)
                
                # Émettre périodiquement les données
                current_time = time.time()
                if current_time - last_emit_time >= emit_interval:
                    self._emit_current_data()
                    last_emit_time = current_time
            
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Erreur réception données: {e}")
                break
        
        logger.info("Boucle de réception terminée")
    
    def _process_data(self, data):
        """Traiter les données reçues du tracker"""
        try:
            # Parser le XML
            root = ET.fromstring(data)
            
            if root.tag == 'REC':
                # Enregistrement de données de tracking
                self._process_rec_data(root.attrib)
            elif root.tag == 'CAL':
                # Données de calibration
                self._process_cal_data(root.attrib)
            elif root.tag == 'ACK':
                # Accusé de réception
                logger.debug(f"ACK reçu: {root.attrib}")
        
        except Exception as e:
            logger.error(f"Erreur traitement données XML: {e}")
            logger.debug(f"Données problématiques: {data}")
    
    def _process_rec_data(self, data):
        """Traiter les données d'enregistrement avec analyses avancées"""
        
        # Mettre à jour les buffers pour analyses
        self._update_data_buffer(data)
        
        # Extraire et valider les données principales
        try:
            # Point de regard principal (Best POG)
            if 'BPOGX' in data and 'BPOGY' in data:
                self.current_data['gaze_x'] = self._clamp_coordinate(float(data.get('BPOGX', 0.5)))
                self.current_data['gaze_y'] = self._clamp_coordinate(float(data.get('BPOGY', 0.5)))
                self.current_data['gaze_valid'] = data.get('BPOGV', '0') == '1'
            
            # Œil gauche avec validation
            if 'LPOGX' in data:
                left_x = self._clamp_coordinate(float(data.get('LPOGX', 0)))
                left_y = self._clamp_coordinate(float(data.get('LPOGY', 0)))
                left_pupil = float(data.get('LPD', 0))
                left_valid = data.get('LPOGV', '0') == '1'
                
                self.current_data['left_eye'] = {
                    'x': left_x,
                    'y': left_y,
                    'pupil': left_pupil,
                    'valid': left_valid,
                    'closed': self._is_eye_closed(left_pupil, left_valid)
                }
                
                # Position 3D si disponible
                if 'LEYEX' in data:
                    self.current_data['left_eye']['position_3d'] = {
                        'x': float(data.get('LEYEX', 0)),
                        'y': float(data.get('LEYEY', 0)),
                        'z': float(data.get('LEYEZ', 0))
                    }
            
            # Œil droit avec validation
            if 'RPOGX' in data:
                right_x = self._clamp_coordinate(float(data.get('RPOGX', 0)))
                right_y = self._clamp_coordinate(float(data.get('RPOGY', 0)))
                right_pupil = float(data.get('RPD', 0))
                right_valid = data.get('RPOGV', '0') == '1'
                
                self.current_data['right_eye'] = {
                    'x': right_x,
                    'y': right_y,
                    'pupil': right_pupil,
                    'valid': right_valid,
                    'closed': self._is_eye_closed(right_pupil, right_valid)
                }
                
                # Position 3D si disponible
                if 'REYEX' in data:
                    self.current_data['right_eye']['position_3d'] = {
                        'x': float(data.get('REYEX', 0)),
                        'y': float(data.get('REYEY', 0)),
                        'z': float(data.get('REYEZ', 0))
                    }
            
            # Données de fixation avec analyse
            if 'FPOGX' in data:
                fix_x = self._clamp_coordinate(float(data.get('FPOGX', 0)))
                fix_y = self._clamp_coordinate(float(data.get('FPOGY', 0)))
                fix_duration = float(data.get('FPOGD', 0))
                fix_id = int(data.get('FPOGID', 0))
                fix_valid = data.get('FPOGV', '0') == '1'
                
                # Détecter nouvelle fixation
                if fix_valid and fix_id != self.current_data['fixation'].get('id', -1):
                    self._handle_new_fixation(fix_x, fix_y, fix_duration, fix_id)
                
                self.current_data['fixation'] = {
                    'x': fix_x,
                    'y': fix_y,
                    'duration': fix_duration,
                    'id': fix_id,
                    'valid': fix_valid
                }
            
            # Timestamp et compteur
            self.current_data['timestamp'] = float(data.get('TIME', 0))
            self.current_data['counter'] = int(data.get('CNT', 0))
            
            # Données additionnelles
            if 'CX' in data:  # Position curseur
                self.current_data['cursor'] = {
                    'x': float(data.get('CX', 0)),
                    'y': float(data.get('CY', 0)),
                    'state': int(data.get('CS', 0))
                }
            
            # Calculer les métriques dérivées
            self._calculate_derived_metrics(data)
            
            # Mettre à jour les AOI
            self._update_aoi()
            
            # Enregistrer si nécessaire
            if self.is_recording and self.recording_writer:
                self._write_recording_data(data)
                
                # Log périodique du statut d'enregistrement
                if self.recording_line_count % 600 == 0:  # Toutes les 10 secondes à 60Hz
                    logger.info(f"Enregistrement en cours: {self.recording_line_count} lignes")
        
        except Exception as e:
            logger.error(f"Erreur traitement données: {e}")
            logger.debug(f"Données problématiques: {data}")
    
    def _process_cal_data(self, data):
        """Traiter les données de calibration"""
        cal_id = data.get('ID', '')
        
        if cal_id == 'CALIB_START_PT':
            # Point de calibration démarré
            pt = data.get('PT', '')
            x = data.get('CALX', '')
            y = data.get('CALY', '')
            logger.info(f"Point de calibration {pt}: ({x}, {y})")
            
            self.websocket_manager.broadcast('gazepoint_calibration_point', {
                'point': pt,
                'x': x,
                'y': y,
                'status': 'start'
            })
        
        elif cal_id == 'CALIB_RESULT':
            # Résultat de calibration
            logger.info("Calibration terminée")
            self.is_calibrating = False
            
            # Stocker les résultats de calibration
            if 'AVE_ERROR' in data:
                self.realtime_stats['calibration_accuracy'] = {
                    'average_error': float(data.get('AVE_ERROR', 0)),
                    'max_error': float(data.get('MAX_ERROR', 0))
                }
            
            self.websocket_manager.broadcast('gazepoint_calibration_complete', {
                'status': 'complete',
                'data': data
            })
    
    def _update_data_buffer(self, data):
        """Mettre à jour les buffers pour analyses avancées"""
        current_time = float(data.get('TIME', 0))
        
        # Buffer des positions de regard
        if 'BPOGX' in data and 'BPOGY' in data:
            gaze_point = {
                'x': float(data.get('BPOGX', 0)),
                'y': float(data.get('BPOGY', 0)),
                'time': current_time,
                'valid': data.get('BPOGV', '0') == '1'
            }
            self.data_buffer['gaze_positions'].append(gaze_point)
        
        # Buffer de clignements
        left_valid = data.get('LPOGV', '0') == '1'
        right_valid = data.get('RPOGV', '0') == '1'
        lpd = float(data.get('LPD', 0))
        rpd = float(data.get('RPD', 0))
        
        blink_detected = (not left_valid and not right_valid) or (lpd < 10 and rpd < 10)
        self.data_buffer['blink_buffer'].append({
            'time': current_time,
            'blink': blink_detected
        })
        
        # Calculer les statistiques
        self._calculate_realtime_stats()
    
    def _calculate_realtime_stats(self):
        """Calculer les statistiques en temps réel"""
        # Calculer le taux de clignements (par minute)
        if len(self.data_buffer['blink_buffer']) > 10:
            blinks = sum(1 for b in self.data_buffer['blink_buffer'] if b['blink'])
            time_span = self.data_buffer['blink_buffer'][-1]['time'] - self.data_buffer['blink_buffer'][0]['time']
            if time_span > 0:
                self.realtime_stats['blink_rate'] = (blinks / time_span) * 60
        
        # Calculer la qualité des données
        if len(self.data_buffer['gaze_positions']) > 0:
            valid_count = sum(1 for g in self.data_buffer['gaze_positions'] if g['valid'])
            self.realtime_stats['tracking_ratio'] = valid_count / len(self.data_buffer['gaze_positions'])
        
        # Détecter les saccades (mouvements rapides)
        if len(self.data_buffer['gaze_positions']) >= 2:
            last_pos = self.data_buffer['gaze_positions'][-2]
            current_pos = self.data_buffer['gaze_positions'][-1]
            
            if last_pos['valid'] and current_pos['valid']:
                distance = ((current_pos['x'] - last_pos['x']) ** 2 +
                            (current_pos['y'] - last_pos['y']) ** 2) ** 0.5
                time_diff = current_pos['time'] - last_pos['time']
                
                if time_diff > 0:
                    velocity = distance / time_diff
                    # Saccade si vélocité > seuil
                    if velocity > 2.0:  # Seuil en unités normalisées/seconde
                        self.realtime_stats['saccade_count'] += 1
    
    def _clamp_coordinate(self, value):
        """Limiter les coordonnées entre 0 et 1"""
        return max(0.0, min(1.0, value))
    
    def _is_eye_closed(self, pupil_diameter, is_valid):
        """Déterminer si l'œil est fermé"""
        # Œil fermé si : non valide OU pupille très petite
        return not is_valid or pupil_diameter < 10.0
    
    def _handle_new_fixation(self, x, y, duration, fix_id):
        """Gérer une nouvelle fixation détectée"""
        # Ajouter à l'historique des fixations
        fixation_data = {
            'id': fix_id,
            'x': x,
            'y': y,
            'duration': duration,
            'timestamp': self.current_data['timestamp'],
            'aoi': self._get_aoi_for_position(x, y)
        }
        
        if len(self.data_buffer['fixation_buffer']) > 0:
            # Calculer la durée de la fixation précédente
            last_fixation = self.data_buffer['fixation_buffer'][-1]
            last_fixation['final_duration'] = fixation_data['timestamp'] - last_fixation['timestamp']
        
        self.data_buffer['fixation_buffer'].append(fixation_data)
        
        # Mettre à jour les statistiques
        self.realtime_stats['total_fixations'] += 1
        self._update_fixation_stats()
    
    def _calculate_derived_metrics(self, data):
        """Calculer les métriques dérivées des données brutes"""
        
        # Distance interpupillaire (convergence)
        if self.current_data['left_eye']['valid'] and self.current_data['right_eye']['valid']:
            ipd = ((self.current_data['right_eye']['x'] - self.current_data['left_eye']['x']) ** 2 +
                   (self.current_data['right_eye']['y'] - self.current_data['left_eye']['y']) ** 2) ** 0.5
            self.current_data['interpupillary_distance'] = ipd
            
            # Convergence (angle entre les yeux)
            if 'position_3d' in self.current_data['left_eye'] and 'position_3d' in self.current_data['right_eye']:
                left_z = self.current_data['left_eye']['position_3d']['z']
                right_z = self.current_data['right_eye']['position_3d']['z']
                avg_z = (left_z + right_z) / 2
                
                if avg_z > 0:
                    convergence_angle = math.atan(ipd / avg_z) * 180 / math.pi
                    self.current_data['convergence_angle'] = convergence_angle
        
        # Vélocité du regard
        if len(self.data_buffer['gaze_positions']) >= 2:
            velocity = self._calculate_gaze_velocity()
            self.current_data['gaze_velocity'] = velocity
            
            # Classification du mouvement
            if velocity < 0.5:
                self.current_data['movement_type'] = 'fixation'
            elif velocity < 2.0:
                self.current_data['movement_type'] = 'smooth_pursuit'
            else:
                self.current_data['movement_type'] = 'saccade'
        
        # Qualité des données
        data_quality = self._calculate_data_quality(data)
        self.current_data['data_quality'] = data_quality
    
    def _calculate_gaze_velocity(self):
        """Calculer la vélocité du regard en degrés/seconde"""
        if len(self.data_buffer['gaze_positions']) < 2:
            return 0.0
        
        # Prendre les deux dernières positions valides
        positions = [p for p in self.data_buffer['gaze_positions'] if p['valid']]
        if len(positions) < 2:
            return 0.0
        
        p1 = positions[-2]
        p2 = positions[-1]
        
        # Distance en coordonnées normalisées
        distance = ((p2['x'] - p1['x']) ** 2 + (p2['y'] - p1['y']) ** 2) ** 0.5
        
        # Temps écoulé
        time_diff = p2['time'] - p1['time']
        if time_diff <= 0:
            return 0.0
        
        # Convertir en degrés/seconde (approximation)
        # Supposons qu'1 unité normalisée = ~30 degrés visuels
        velocity_deg_per_sec = (distance * 30) / time_diff
        
        return velocity_deg_per_sec
    
    def _calculate_data_quality(self, data):
        """Calculer un score de qualité des données (0-1)"""
        quality_factors = []
        
        # Validité des points de regard
        if 'BPOGV' in data:
            quality_factors.append(1.0 if data['BPOGV'] == '1' else 0.0)
        
        # Validité des yeux
        if 'LPOGV' in data and 'RPOGV' in data:
            left_valid = 1.0 if data['LPOGV'] == '1' else 0.0
            right_valid = 1.0 if data['RPOGV'] == '1' else 0.0
            quality_factors.append((left_valid + right_valid) / 2)
        
        # Taille des pupilles (normaliser entre 0 et 1)
        if 'LPD' in data and 'RPD' in data:
            lpd = float(data.get('LPD', 0))
            rpd = float(data.get('RPD', 0))
            # Supposons que les pupilles normales sont entre 20 et 80 pixels
            lpd_quality = max(0, min(1, (lpd - 20) / 60))
            rpd_quality = max(0, min(1, (rpd - 20) / 60))
            quality_factors.append((lpd_quality + rpd_quality) / 2)
        
        # Calculer la qualité moyenne
        if quality_factors:
            return sum(quality_factors) / len(quality_factors)
        return 0.0
    
    def _get_aoi_for_position(self, x, y):
        """Obtenir la zone d'intérêt pour une position donnée"""
        for zone_name, zone in self.aoi_zones.items():
            if (zone['x'] <= x <= zone['x'] + zone['width'] and
                    zone['y'] <= y <= zone['y'] + zone['height']):
                return zone_name
        return None
    
    def _update_aoi(self):
        """Mettre à jour la zone d'intérêt actuelle et le temps cumulé"""
        gaze_x = self.current_data['gaze_x']
        gaze_y = self.current_data['gaze_y']
        
        current_zone = self._get_aoi_for_position(gaze_x, gaze_y)
        
        # Mettre à jour le temps dans la zone
        current_time = time.time()
        if current_zone:
            if self.current_aoi == current_zone:
                # Toujours dans la même zone
                elapsed = current_time - self.last_aoi_update
                self.aoi_zones[current_zone]['time'] += elapsed
            else:
                # Nouvelle zone
                self.current_aoi = current_zone
        else:
            self.current_aoi = None
        
        self.last_aoi_update = current_time
    
    def _update_fixation_stats(self):
        """Mettre à jour les statistiques de fixation"""
        if len(self.data_buffer['fixation_buffer']) > 0:
            # Calculer la durée moyenne des fixations
            durations = [f.get('final_duration', f['duration'])
                         for f in self.data_buffer['fixation_buffer']
                         if 'final_duration' in f or f['duration'] > 0]
            
            if durations:
                self.realtime_stats['average_fixation_duration'] = sum(durations) / len(durations)
    
    def _write_recording_data(self, data):
        """Écrire une ligne dans le fichier d'enregistrement avec validation des données"""
        
        def safe_get(key, default='', formatter=None):
            """Récupérer une valeur de manière sûre avec formatage optionnel"""
            value = data.get(key, default)
            if value == '' or value is None:
                return default
            try:
                if formatter == 'float':
                    return f"{float(value):.6f}"
                elif formatter == 'int':
                    return str(int(value))
                elif formatter == 'bool':
                    return '1' if value == '1' else '0'
                else:
                    return str(value)
            except (ValueError, TypeError):
                return default
        
        # Construire la ligne de données avec validation
        row = [
            # Métadonnées temporelles
            datetime.now().isoformat(),
            safe_get('CNT', '0', 'int'),
            safe_get('TIME', '0.0', 'float'),
            
            # Best Point of Gaze (moyenne des deux yeux)
            safe_get('BPOGX', '0.5', 'float'),
            safe_get('BPOGY', '0.5', 'float'),
            safe_get('BPOGV', '0', 'bool'),
            
            # Œil gauche - Point de regard
            safe_get('LPOGX', '0.0', 'float'),
            safe_get('LPOGY', '0.0', 'float'),
            safe_get('LPD', '0.0', 'float'),  # Diamètre pupille gauche
            safe_get('LPOGV', '0', 'bool'),  # Validité
            
            # Œil droit - Point de regard
            safe_get('RPOGX', '0.0', 'float'),
            safe_get('RPOGY', '0.0', 'float'),
            safe_get('RPD', '0.0', 'float'),  # Diamètre pupille droite
            safe_get('RPOGV', '0', 'bool'),  # Validité
            
            # Données de fixation
            safe_get('FPOGX', '0.0', 'float'),
            safe_get('FPOGY', '0.0', 'float'),
            safe_get('FPOGD', '0.0', 'float'),  # Durée de fixation
            safe_get('FPOGID', '0', 'int'),  # ID de fixation
            safe_get('FPOGV', '0', 'bool'),  # Validité fixation
            
            # Position 3D des yeux (si disponible)
            safe_get('LEYEX', '0.0', 'float'),
            safe_get('LEYEY', '0.0', 'float'),
            safe_get('LEYEZ', '0.0', 'float'),
            safe_get('REYEX', '0.0', 'float'),
            safe_get('REYEY', '0.0', 'float'),
            safe_get('REYEZ', '0.0', 'float'),
            
            # Données additionnelles
            safe_get('CX', '0.0', 'float'),  # Position curseur X (si activé)
            safe_get('CY', '0.0', 'float'),  # Position curseur Y (si activé)
            safe_get('CS', '0', 'int'),  # État curseur (clic)
            
            # Zone d'intérêt actuelle
            self.current_aoi or 'none',
            
            # Métriques calculées
            f"{self.current_data.get('interpupillary_distance', 0):.6f}",
            f"{self.current_data.get('gaze_velocity', 0):.6f}",
            self._is_blink_detected(data),
            self.current_data.get('movement_type', 'unknown'),
            f"{self.current_data.get('data_quality', 0):.3f}"
        ]
        
        try:
            self.recording_writer.writerow(row)
            self.recording_line_count += 1
        except Exception as e:
            logger.error(f"Erreur écriture CSV: {e}")
    
    def _is_blink_detected(self, data):
        """Détecter un clignement basé sur la validité et la taille des pupilles"""
        try:
            lpv = data.get('LPOGV', '0') == '1'
            rpv = data.get('RPOGV', '0') == '1'
            lpd = float(data.get('LPD', 0))
            rpd = float(data.get('RPD', 0))
            
            # Clignement si les deux yeux sont invalides ou pupilles très petites
            if (not lpv and not rpv) or (lpd < 10 and rpd < 10):
                return "1"
            return "0"
        except:
            return "0"
    
    def _emit_current_data(self):
        """Émettre les données actuelles via WebSocket avec toutes les métriques"""
        # Déterminer l'état des yeux
        left_eye_closed = self.current_data['left_eye']['closed']
        right_eye_closed = self.current_data['right_eye']['closed']
        
        emit_data = {
            'gaze': {
                'x': self.current_data['gaze_x'],
                'y': self.current_data['gaze_y'],
                'valid': self.current_data['gaze_valid']
            },
            'eyes': {
                'left': {
                    'x': self.current_data['left_eye']['x'],
                    'y': self.current_data['left_eye']['y'],
                    'pupil': self.current_data['left_eye']['pupil'],
                    'valid': self.current_data['left_eye']['valid'],
                    'closed': left_eye_closed
                },
                'right': {
                    'x': self.current_data['right_eye']['x'],
                    'y': self.current_data['right_eye']['y'],
                    'pupil': self.current_data['right_eye']['pupil'],
                    'valid': self.current_data['right_eye']['valid'],
                    'closed': right_eye_closed
                }
            },
            'fixation': self.current_data['fixation'],
            'aoi': {
                'current': self.current_aoi,
                'zones': self.aoi_zones
            },
            'metrics': {
                'velocity': self.current_data['gaze_velocity'],
                'movement_type': self.current_data['movement_type'],
                'data_quality': self.current_data['data_quality'],
                'blink_rate': self.realtime_stats['blink_rate'],
                'total_fixations': self.realtime_stats['total_fixations']
            },
            'recording': {
                'active': self.is_recording,
                'lines': self.recording_line_count
            },
            'timestamp': self.current_data['timestamp']
        }
        
        self.websocket_manager.emit_to_module('gazepoint', 'gazepoint_data', emit_data)
        
        # AJOUT : Émettre les événements spécifiques en broadcast pour le dashboard home
        # Données de regard
        gaze_broadcast_data = {
            'gaze_data': {
                'FPOGX': str(self.current_data['gaze_x']),
                'FPOGY': str(self.current_data['gaze_y']),
                'FPOGV': '1' if self.current_data['gaze_valid'] else '0',
                'BPOGX': str(self.current_data['gaze_x']),
                'BPOGY': str(self.current_data['gaze_y']),
                'BPOGV': '1' if self.current_data['gaze_valid'] else '0'
            },
            'timestamp': datetime.now().isoformat()
        }
        self.websocket_manager.broadcast('gazepoint_gaze_data', gaze_broadcast_data)
        
        # Données oculaires
        eye_broadcast_data = {
            'eye_data': {
                'LPUPILD': str(self.current_data['left_eye']['pupil']),
                'RPUPILD': str(self.current_data['right_eye']['pupil']),
                'LEYEOPENESS': '0' if left_eye_closed else '1',
                'REYEOPENESS': '0' if right_eye_closed else '1',
                'LEYEGAZEX': str(self.current_data['left_eye']['x']),
                'LEYEGAZEY': str(self.current_data['left_eye']['y']),
                'REYEGAZEX': str(self.current_data['right_eye']['x']),
                'REYEGAZEY': str(self.current_data['right_eye']['y'])
            },
            'timestamp': datetime.now().isoformat()
        }
        self.websocket_manager.broadcast('gazepoint_eye_data', eye_broadcast_data)
        
        # Données de fixation
        if self.current_data['fixation']['valid']:
            fixation_broadcast_data = {
                'fixation_data': {
                    'FPOGX': str(self.current_data['fixation']['x']),
                    'FPOGY': str(self.current_data['fixation']['y']),
                    'FPOGD': str(self.current_data['fixation']['duration']),
                    'FPOGID': str(self.current_data['fixation']['id']),
                    'FPOGV': '1'
                },
                'timestamp': datetime.now().isoformat()
            }
            self.websocket_manager.broadcast('gazepoint_fixation_data', fixation_broadcast_data)
    
    def get_recordings_list(self):
        """Obtenir la liste des enregistrements CSV"""
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
            try:
                file_path.unlink()
                logger.info(f"Enregistrement supprimé: {filename}")
                return True
            except Exception as e:
                logger.error(f"Erreur suppression fichier {filename}: {e}")
                return False
        
        return False
    
    def _format_file_size(self, size):
        """Formater la taille du fichier"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def cleanup(self):
        """Nettoyer les ressources du module"""
        logger.info("Nettoyage du module Gazepoint...")
        
        # Arrêter l'enregistrement
        if self.is_recording:
            self.stop_recording()
        
        # Se déconnecter
        if self.is_connected:
            self.disconnect()
        
        logger.info("Module Gazepoint nettoyé")


def register_gazepoint_websocket_events(websocket_manager, gazepoint_module):
    """Enregistrer les événements WebSocket pour le module Gazepoint"""
    
    def handle_connect(data):
        """Connecter au serveur Gazepoint"""
        # Extraire les paramètres de connexion si fournis
        host = data.get('host') if data else None
        port = data.get('port') if data else None
        
        success = gazepoint_module.connect(host, port)
        if success:
            # Démarrer automatiquement le tracking
            gazepoint_module.start_tracking()
    
    def handle_disconnect(data):
        """Déconnecter du serveur Gazepoint"""
        gazepoint_module.disconnect()
    
    def handle_start_tracking(data):
        """Démarrer le tracking"""
        gazepoint_module.start_tracking()
    
    def handle_stop_tracking(data):
        """Arrêter le tracking"""
        gazepoint_module.stop_tracking()
    
    def handle_start_recording(data):
        """Démarrer l'enregistrement"""
        gazepoint_module.start_recording()
    
    def handle_stop_recording(data):
        """Arrêter l'enregistrement"""
        gazepoint_module.stop_recording()
    
    def handle_start_calibration(data):
        """Démarrer la calibration"""
        gazepoint_module.start_calibration()
    
    def handle_get_recordings(data):
        """Obtenir la liste des enregistrements"""
        recordings = gazepoint_module.get_recordings_list()
        websocket_manager.emit_to_current_client('gazepoint_recordings_list', {
            'recordings': recordings,
            'timestamp': datetime.now().isoformat()
        })
    
    def handle_delete_recording(data):
        """Supprimer un enregistrement"""
        filename = data.get('filename')
        if filename:
            success = gazepoint_module.delete_recording(filename)
            if success:
                # Renvoyer la liste mise à jour
                recordings = gazepoint_module.get_recordings_list()
                websocket_manager.emit_to_current_client('gazepoint_recordings_list', {
                    'recordings': recordings,
                    'timestamp': datetime.now().isoformat()
                })
    
    # Enregistrer les événements
    gazepoint_events = {
        'connect': handle_connect,
        'disconnect': handle_disconnect,
        'start_tracking': handle_start_tracking,
        'stop_tracking': handle_stop_tracking,
        'start_recording': handle_start_recording,
        'stop_recording': handle_stop_recording,
        'start_calibration': handle_start_calibration,
        'get_recordings': handle_get_recordings,
        'delete_recording': handle_delete_recording
    }
    
    websocket_manager.register_module_events('gazepoint', gazepoint_events)
    logger.info("Événements WebSocket du module Gazepoint enregistrés")


def init_gazepoint_module(app, websocket_manager):
    """Initialiser le module Gazepoint"""
    gazepoint_module = GazepointModule(app, websocket_manager)
    return gazepoint_module


def register_gazepoint_routes(app):
    """Enregistrer les routes Flask pour Gazepoint"""
    # Les routes sont déjà enregistrées dans la classe GazepointModule
    pass