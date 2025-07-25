#!/usr/bin/env python3
"""
Module Dashboard Home - Backend pour la vue d'ensemble en temps réel
Gère l'agrégation et la synchronisation des données de tous les modules
Version complète avec intégration Polar, Neurosity, Thermal et Gazepoint
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import threading
from collections import deque
import time

logger = logging.getLogger(__name__)


class DashboardHomeModule:
    """Module Dashboard Home pour la vue d'ensemble centralisée"""
    
    def __init__(self, app, websocket_manager):
        self.app = app
        self.websocket_manager = websocket_manager
        
        # État des appareils connectés
        self.devices_state = {
            'polar': {
                'h10': {'connected': False, 'last_data': None, 'device_info': None},
                'verity': {'connected': False, 'last_data': None, 'device_info': None}
            },
            'neurosity': {
                'connected': False,
                'last_data': None,
                'device_info': None,
                'battery': None,
                'charging': False
            },
            'thermal': {
                'connected': False,
                'last_data': None,
                'capturing': False
            },
            'gazepoint': {
                'connected': False,
                'last_data': None,
                'device_info': None,
                'calibrated': False,
                'tracking_status': 'none'
            }
        }
        
        # Buffers de données pour graphiques (garder les 60 derniers points)
        self.data_buffers = {
            # Buffers Polar
            'bpm': deque(maxlen=60),
            'rr': deque(maxlen=60),
            'breathing': deque(maxlen=60),
            # Buffers Neurosity
            'focus': deque(maxlen=60),
            'calm': deque(maxlen=60),
            'alpha': deque(maxlen=60),
            'delta': deque(maxlen=60),
            'theta': deque(maxlen=60),
            'beta': deque(maxlen=60),
            'gamma': deque(maxlen=60),
            # Buffers Thermal
            'thermal_nez': deque(maxlen=60),
            'thermal_bouche': deque(maxlen=60),
            'thermal_oeil_gauche': deque(maxlen=60),
            'thermal_oeil_droit': deque(maxlen=60),
            'thermal_joue_gauche': deque(maxlen=60),
            'thermal_joue_droite': deque(maxlen=60),
            'thermal_front': deque(maxlen=60),
            'thermal_menton': deque(maxlen=60),
            # Buffers Gazepoint
            'gaze_x': deque(maxlen=60),
            'gaze_y': deque(maxlen=60),
            'pupil_left': deque(maxlen=60),
            'pupil_right': deque(maxlen=60),
            'fixation_duration': deque(maxlen=60),
            'blink_rate': deque(maxlen=60)
        }
        
        # Statistiques de session
        self.session_stats = {
            'start_time': None,
            'total_samples': 0,
            'devices_active': 0
        }
        
        # État de la collecte globale
        self.collection_state = {
            'is_collecting': False,
            'start_time': None,
            'session_id': None
        }
        
        # Références aux autres modules (seront définies par app.py)
        self.polar_module = None
        self.neurosity_module = None
        self.thermal_module = None
        self.gazepoint_module = None
        
        # Thread de mise à jour périodique
        self._running = True
        self._update_thread = None
        
        logger.info("Module Dashboard Home initialisé")
    
    def set_module_references(self, polar_module=None, neurosity_module=None, thermal_module=None,
                              gazepoint_module=None):
        """Définit les références aux autres modules"""
        self.polar_module = polar_module
        self.neurosity_module = neurosity_module
        self.thermal_module = thermal_module
        self.gazepoint_module = gazepoint_module
        logger.info("Références aux modules définies dans Dashboard Home")
    
    def start_periodic_updates(self):
        """Démarre les mises à jour périodiques"""
        if not self._update_thread or not self._update_thread.is_alive():
            self._update_thread = threading.Thread(target=self._periodic_update_loop)
            self._update_thread.daemon = True
            self._update_thread.start()
            logger.info("Thread de mise à jour périodique démarré")
    
    def _periodic_update_loop(self):
        """Boucle de mise à jour périodique"""
        while self._running:
            try:
                # Émettre l'état actuel toutes les secondes
                self.emit_dashboard_state()
                time.sleep(1)
            except Exception as e:
                logger.error(f"Erreur dans la boucle de mise à jour: {e}")
                time.sleep(5)
    
    # === GESTION DES DONNÉES POLAR ===
    
    def handle_polar_data(self, device_type: str, data: Dict[str, Any]):
        """Traite les données reçues du module Polar"""
        try:
            # Mettre à jour l'état de l'appareil
            if device_type in ['h10', 'verity']:
                self.devices_state['polar'][device_type]['connected'] = True
                self.devices_state['polar'][device_type]['last_data'] = data
                
                # Extraire les métriques importantes
                if data.get('heart_rate'):
                    self.data_buffers['bpm'].append({
                        'value': data['heart_rate'],
                        'timestamp': datetime.now().isoformat()
                    })
                
                # RR intervals
                metrics = data.get('real_time_metrics', {})
                rr_metrics = metrics.get('rr_metrics', {})
                if rr_metrics.get('last_rr'):
                    self.data_buffers['rr'].append({
                        'value': rr_metrics['last_rr'],
                        'rmssd': rr_metrics.get('rmssd', 0),
                        'timestamp': datetime.now().isoformat()
                    })
                
                # Respiration RSA
                breathing_metrics = metrics.get('breathing_metrics', {})
                if breathing_metrics.get('frequency', 0) > 0:
                    self.data_buffers['breathing'].append({
                        'value': breathing_metrics['frequency'],
                        'amplitude': breathing_metrics.get('amplitude', 0),
                        'quality': breathing_metrics.get('quality', 'unknown'),
                        'timestamp': datetime.now().isoformat()
                    })
                
                # Incrémenter les compteurs
                self.session_stats['total_samples'] += 1
                
                # Émettre la mise à jour via WebSocket
                self.emit_polar_update(device_type, data)
        
        except Exception as e:
            logger.error(f"Erreur traitement données Polar {device_type}: {e}")
    
    def handle_polar_connected(self, device_type: str, device_info: Dict[str, Any]):
        """Gère la connexion d'un appareil Polar"""
        try:
            if device_type in ['h10', 'verity']:
                self.devices_state['polar'][device_type]['connected'] = True
                self.devices_state['polar'][device_type]['device_info'] = device_info
                
                # Mettre à jour le compteur d'appareils actifs
                self._update_active_devices_count()
                
                # Notifier le frontend
                self.websocket_manager.emit_to_module('home', 'device_connected', {
                    'module': 'polar',
                    'device_type': device_type,
                    'device_info': device_info,
                    'timestamp': datetime.now().isoformat()
                })
                
                logger.info(f"Appareil Polar {device_type} connecté dans Dashboard Home")
        
        except Exception as e:
            logger.error(f"Erreur gestion connexion Polar {device_type}: {e}")
    
    def handle_polar_disconnected(self, device_type: str):
        """Gère la déconnexion d'un appareil Polar"""
        try:
            if device_type in ['h10', 'verity']:
                self.devices_state['polar'][device_type]['connected'] = False
                self.devices_state['polar'][device_type]['last_data'] = None
                
                # Mettre à jour le compteur d'appareils actifs
                self._update_active_devices_count()
                
                # Notifier le frontend
                self.websocket_manager.emit_to_module('home', 'device_disconnected', {
                    'module': 'polar',
                    'device_type': device_type,
                    'timestamp': datetime.now().isoformat()
                })
                
                logger.info(f"Appareil Polar {device_type} déconnecté dans Dashboard Home")
        
        except Exception as e:
            logger.error(f"Erreur gestion déconnexion Polar {device_type}: {e}")
    
    # === GESTION DES DONNÉES NEUROSITY ===
    
    def handle_neurosity_data(self, data_type: str, data: Dict[str, Any]):
        """Traite les données du module Neurosity selon leur type"""
        try:
            self.devices_state['neurosity']['connected'] = True
            self.devices_state['neurosity']['last_data'] = data
            
            # Traiter selon le type de données
            if data_type == 'calm':
                value = data.get('calm', data.get('percentage', 0))
                if isinstance(value, (int, float)):
                    self.data_buffers['calm'].append({
                        'value': value,
                        'timestamp': datetime.now().isoformat()
                    })
            
            elif data_type == 'focus':
                value = data.get('focus', data.get('percentage', 0))
                if isinstance(value, (int, float)):
                    self.data_buffers['focus'].append({
                        'value': value,
                        'timestamp': datetime.now().isoformat()
                    })
            
            elif data_type == 'brainwaves':
                # Traiter toutes les ondes cérébrales
                for wave in ['delta', 'theta', 'alpha', 'beta', 'gamma']:
                    if wave in data:
                        values = data[wave]
                        if isinstance(values, list) and len(values) == 8:
                            # Calculer la moyenne des 8 électrodes
                            avg_value = sum(values) / len(values)
                            self.data_buffers[wave].append({
                                'value': avg_value,
                                'timestamp': datetime.now().isoformat()
                            })
            
            elif data_type == 'battery':
                self.devices_state['neurosity']['battery'] = data.get('level', 0)
                self.devices_state['neurosity']['charging'] = data.get('charging', False)
            
            # Incrémenter les statistiques
            self.session_stats['total_samples'] += 1
            
            # Émettre la mise à jour
            self.emit_neurosity_update(data_type, data)
        
        except Exception as e:
            logger.error(f"Erreur traitement données Neurosity {data_type}: {e}")
    
    def handle_neurosity_connected(self, data: Dict[str, Any]):
        """Gère la connexion du casque Neurosity"""
        try:
            self.devices_state['neurosity']['connected'] = True
            self.devices_state['neurosity']['device_info'] = data.get('device_status', {})
            
            # Mettre à jour le compteur d'appareils actifs
            self._update_active_devices_count()
            
            # Notifier le frontend
            self.websocket_manager.emit_to_module('home', 'device_connected', {
                'module': 'neurosity',
                'device_info': data.get('device_status', {}),
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info("Casque Neurosity connecté dans Dashboard Home")
        
        except Exception as e:
            logger.error(f"Erreur gestion connexion Neurosity: {e}")
    
    def handle_neurosity_disconnected(self, data: Dict[str, Any]):
        """Gère la déconnexion du casque Neurosity"""
        try:
            self.devices_state['neurosity']['connected'] = False
            self.devices_state['neurosity']['last_data'] = None
            self.devices_state['neurosity']['device_info'] = None
            self.devices_state['neurosity']['battery'] = None
            self.devices_state['neurosity']['charging'] = False
            
            # Mettre à jour le compteur d'appareils actifs
            self._update_active_devices_count()
            
            # Notifier le frontend
            self.websocket_manager.emit_to_module('home', 'device_disconnected', {
                'module': 'neurosity',
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info("Casque Neurosity déconnecté dans Dashboard Home")
        
        except Exception as e:
            logger.error(f"Erreur gestion déconnexion Neurosity: {e}")
    
    # === GESTION DES DONNÉES THERMAL ===
    
    def handle_thermal_data(self, data: Dict[str, Any]):
        """Traite les données thermiques reçues"""
        try:
            # Mettre à jour l'état
            self.devices_state['thermal']['connected'] = True
            self.devices_state['thermal']['capturing'] = True
            self.devices_state['thermal']['last_data'] = data
            
            # Extraire les températures
            temperatures = data.get('temperatures', {})
            
            # Mapper les noms des points thermiques
            point_mapping = {
                'Nez': 'thermal_nez',
                'Bouche': 'thermal_bouche',
                'Œil_Gauche': 'thermal_oeil_gauche',
                'Œil_Droit': 'thermal_oeil_droit',
                'Joue_Gauche': 'thermal_joue_gauche',
                'Joue_Droite': 'thermal_joue_droite',
                'Front': 'thermal_front',
                'Menton': 'thermal_menton'
            }
            
            # Stocker chaque température dans son buffer
            for point, buffer_name in point_mapping.items():
                temp = temperatures.get(point)
                if temp is not None:
                    self.data_buffers[buffer_name].append({
                        'value': temp,
                        'timestamp': datetime.now().isoformat()
                    })
            
            # Incrémenter les statistiques
            self.session_stats['total_samples'] += 1
            
            # Émettre la mise à jour
            self.emit_thermal_update(data)
        
        except Exception as e:
            logger.error(f"Erreur traitement données thermiques: {e}")
    
    def handle_thermal_connected(self):
        """Gère la connexion du module thermique"""
        try:
            self.devices_state['thermal']['connected'] = True
            self.devices_state['thermal']['capturing'] = True
            
            # Mettre à jour le compteur d'appareils actifs
            self._update_active_devices_count()
            
            # Notifier le frontend
            self.websocket_manager.emit_to_module('home', 'device_connected', {
                'module': 'thermal',
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info("Module thermique connecté dans Dashboard Home")
        
        except Exception as e:
            logger.error(f"Erreur gestion connexion thermique: {e}")
    
    def handle_thermal_disconnected(self):
        """Gère la déconnexion du module thermique"""
        try:
            self.devices_state['thermal']['connected'] = False
            self.devices_state['thermal']['capturing'] = False
            self.devices_state['thermal']['last_data'] = None
            
            # Vider les buffers thermiques
            for point in ['thermal_nez', 'thermal_bouche', 'thermal_oeil_gauche', 'thermal_oeil_droit',
                          'thermal_joue_gauche', 'thermal_joue_droite', 'thermal_front', 'thermal_menton']:
                self.data_buffers[point].clear()
            
            # Mettre à jour le compteur d'appareils actifs
            self._update_active_devices_count()
            
            # Notifier le frontend
            self.websocket_manager.emit_to_module('home', 'device_disconnected', {
                'module': 'thermal',
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info("Module thermique déconnecté dans Dashboard Home")
        
        except Exception as e:
            logger.error(f"Erreur gestion déconnexion thermique: {e}")
    
    # === GESTION DES DONNÉES GAZEPOINT ===
    
    def handle_gazepoint_data(self, data_type: str, data: Dict[str, Any]):
        """Traite les données du module Gazepoint selon leur type"""
        try:
            self.devices_state['gazepoint']['connected'] = True
            self.devices_state['gazepoint']['last_data'] = data
            
            # Traiter selon le type de données
            if data_type == 'gaze':
                # Position du regard
                if 'gaze_data' in data and data['gaze_data']:
                    gaze_data = data['gaze_data']
                    if 'FPOGX' in gaze_data and 'FPOGY' in gaze_data:
                        x = float(gaze_data['FPOGX'])
                        y = float(gaze_data['FPOGY'])
                        self.data_buffers['gaze_x'].append({
                            'value': x,
                            'timestamp': datetime.now().isoformat()
                        })
                        self.data_buffers['gaze_y'].append({
                            'value': y,
                            'timestamp': datetime.now().isoformat()
                        })
            
            elif data_type == 'eye':
                # Données oculaires
                if 'eye_data' in data and data['eye_data']:
                    eye_data = data['eye_data']
                    # Taille des pupilles
                    if 'LPUPILD' in eye_data:
                        self.data_buffers['pupil_left'].append({
                            'value': float(eye_data['LPUPILD']),
                            'timestamp': datetime.now().isoformat()
                        })
                    if 'RPUPILD' in eye_data:
                        self.data_buffers['pupil_right'].append({
                            'value': float(eye_data['RPUPILD']),
                            'timestamp': datetime.now().isoformat()
                        })
                    
                    # Taux de clignement (calculé côté client, on peut stocker un état)
                    if 'LEYEOPENESS' in eye_data and 'REYEOPENESS' in eye_data:
                        left_open = float(eye_data['LEYEOPENESS']) > 0.5
                        right_open = float(eye_data['REYEOPENESS']) > 0.5
                        both_closed = not left_open and not right_open
                        # On pourrait calculer le taux de clignement ici
            
            elif data_type == 'fixation':
                # Données de fixation
                if 'fixation_data' in data and data['fixation_data']:
                    fix_data = data['fixation_data']
                    if 'FPOGD' in fix_data:
                        duration = float(fix_data['FPOGD'])
                        self.data_buffers['fixation_duration'].append({
                            'value': duration,
                            'timestamp': datetime.now().isoformat()
                        })
            
            # Incrémenter les statistiques
            self.session_stats['total_samples'] += 1
            
            # Émettre la mise à jour
            self.emit_gazepoint_update(data_type, data)
        
        except Exception as e:
            logger.error(f"Erreur traitement données Gazepoint {data_type}: {e}")
    
    def handle_gazepoint_connected(self, data: Dict[str, Any]):
        """Gère la connexion du Gazepoint"""
        try:
            self.devices_state['gazepoint']['connected'] = True
            self.devices_state['gazepoint']['device_info'] = data.get('device_info', {})
            self.devices_state['gazepoint']['calibrated'] = data.get('calibrated', False)
            self.devices_state['gazepoint']['tracking_status'] = 'active'
            
            # Mettre à jour le compteur d'appareils actifs
            self._update_active_devices_count()
            
            # Notifier le frontend
            self.websocket_manager.emit_to_module('home', 'device_connected', {
                'module': 'gazepoint',
                'device_info': data.get('device_info', {}),
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info("Gazepoint connecté dans Dashboard Home")
        
        except Exception as e:
            logger.error(f"Erreur gestion connexion Gazepoint: {e}")
    
    def handle_gazepoint_disconnected(self, data: Dict[str, Any]):
        """Gère la déconnexion du Gazepoint"""
        try:
            self.devices_state['gazepoint']['connected'] = False
            self.devices_state['gazepoint']['last_data'] = None
            self.devices_state['gazepoint']['device_info'] = None
            self.devices_state['gazepoint']['calibrated'] = False
            self.devices_state['gazepoint']['tracking_status'] = 'none'
            
            # Vider les buffers Gazepoint
            for buffer_name in ['gaze_x', 'gaze_y', 'pupil_left', 'pupil_right',
                                'fixation_duration', 'blink_rate']:
                if buffer_name in self.data_buffers:
                    self.data_buffers[buffer_name].clear()
            
            # Mettre à jour le compteur d'appareils actifs
            self._update_active_devices_count()
            
            # Notifier le frontend
            self.websocket_manager.emit_to_module('home', 'device_disconnected', {
                'module': 'gazepoint',
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info("Gazepoint déconnecté dans Dashboard Home")
        
        except Exception as e:
            logger.error(f"Erreur gestion déconnexion Gazepoint: {e}")
    
    # === ÉMISSION DES MISES À JOUR ===
    
    def emit_polar_update(self, device_type: str, data: Dict[str, Any]):
        """Émet une mise à jour Polar vers le frontend"""
        try:
            # Préparer les données pour le frontend
            update_data = {
                'device_type': device_type,
                'heart_rate': data.get('heart_rate', 0),
                'battery_level': data.get('battery_level', 0),
                'timestamp': datetime.now().isoformat()
            }
            
            # Ajouter les métriques temps réel
            metrics = data.get('real_time_metrics', {})
            
            # BPM metrics
            bpm_metrics = metrics.get('bpm_metrics', {})
            update_data['bpm'] = {
                'current': bpm_metrics.get('current_bpm', 0),
                'min': bpm_metrics.get('session_min', 0),
                'max': bpm_metrics.get('session_max', 0),
                'avg': bpm_metrics.get('mean_bpm', 0)
            }
            
            # RR metrics
            rr_metrics = metrics.get('rr_metrics', {})
            update_data['rr'] = {
                'last': rr_metrics.get('last_rr', 0),
                'rmssd': rr_metrics.get('rmssd', 0),
                'mean': rr_metrics.get('mean_rr', 0)
            }
            
            # Breathing metrics
            breathing_metrics = metrics.get('breathing_metrics', {})
            update_data['breathing'] = {
                'rate': breathing_metrics.get('frequency', 0),
                'amplitude': breathing_metrics.get('amplitude', 0),
                'quality': breathing_metrics.get('quality', 'unknown')
            }
            
            # Graphiques - derniers points
            update_data['graphs'] = {
                'bpm': list(self.data_buffers['bpm'])[-20:],  # 20 derniers points
                'rr': list(self.data_buffers['rr'])[-20:]
            }
            
            # Émettre vers le module home
            self.websocket_manager.emit_to_module('home', 'polar_data_update', update_data)
        
        except Exception as e:
            logger.error(f"Erreur émission mise à jour Polar: {e}")
    
    def emit_neurosity_update(self, data_type: str, data: Dict[str, Any]):
        """Émet une mise à jour Neurosity vers le frontend"""
        try:
            update_data = {
                'data_type': data_type,
                'timestamp': datetime.now().isoformat()
            }
            
            if data_type == 'calm':
                value = data.get('calm', data.get('percentage', 0))
                update_data['calm'] = value * 100 if value <= 1 else value
                update_data['calm_history'] = list(self.data_buffers['calm'])[-20:]
            
            elif data_type == 'focus':
                value = data.get('focus', data.get('percentage', 0))
                update_data['focus'] = value * 100 if value <= 1 else value
                update_data['focus_history'] = list(self.data_buffers['focus'])[-20:]
            
            elif data_type == 'brainwaves':
                # Envoyer toutes les ondes cérébrales
                brainwaves_data = {}
                brainwaves_history = {}
                
                for wave in ['delta', 'theta', 'alpha', 'beta', 'gamma']:
                    if wave in data:
                        values = data[wave]
                        if isinstance(values, list) and len(values) == 8:
                            avg_value = sum(values) / len(values)
                            brainwaves_data[wave] = avg_value
                            brainwaves_history[wave] = list(self.data_buffers[wave])[-20:]
                
                update_data['brainwaves'] = brainwaves_data
                update_data['brainwaves_history'] = brainwaves_history
            
            elif data_type == 'battery':
                update_data['battery'] = data.get('level', 0)
                update_data['charging'] = data.get('charging', False)
            
            # Émettre vers le module home
            self.websocket_manager.emit_to_module('home', 'neurosity_data_update', update_data)
        
        except Exception as e:
            logger.error(f"Erreur émission mise à jour Neurosity: {e}")
    
    def emit_thermal_update(self, data: Dict[str, Any]):
        """Émet une mise à jour thermique vers le frontend"""
        try:
            update_data = {
                'temperatures': data.get('temperatures', {}),
                'timestamp': datetime.now().isoformat()
            }
            
            # Ajouter l'historique des températures pour le graphique
            thermal_history = {}
            for point in ['Nez', 'Bouche', 'Œil_Gauche', 'Œil_Droit',
                          'Joue_Gauche', 'Joue_Droite', 'Front', 'Menton']:
                buffer_name = f"thermal_{point.lower().replace('_', '_').replace('œ', 'oe')}"
                if buffer_name in self.data_buffers:
                    thermal_history[point] = list(self.data_buffers[buffer_name])[-20:]
            
            update_data['thermal_history'] = thermal_history
            
            # Émettre vers le module home
            self.websocket_manager.emit_to_module('home', 'thermal_data_update', update_data)
        
        except Exception as e:
            logger.error(f"Erreur émission mise à jour thermique: {e}")
    
    def emit_gazepoint_update(self, data_type: str, data: Dict[str, Any]):
        """Émet une mise à jour Gazepoint vers le frontend"""
        try:
            update_data = {
                'data_type': data_type,
                'timestamp': datetime.now().isoformat()
            }
            
            if data_type == 'gaze':
                # Extraire les données de regard
                if 'gaze_data' in data and data['gaze_data']:
                    gaze_data = data['gaze_data']
                    update_data['gaze'] = {
                        'x': float(gaze_data.get('FPOGX', 0)),
                        'y': float(gaze_data.get('FPOGY', 0)),
                        'validity': gaze_data.get('FPOGV', 0)
                    }
                    update_data['gaze_history'] = {
                        'x': list(self.data_buffers['gaze_x'])[-20:],
                        'y': list(self.data_buffers['gaze_y'])[-20:]
                    }
            
            elif data_type == 'eye':
                # Extraire les données oculaires
                if 'eye_data' in data and data['eye_data']:
                    eye_data = data['eye_data']
                    update_data['eye'] = {
                        'left_pupil': float(eye_data.get('LPUPILD', 0)),
                        'right_pupil': float(eye_data.get('RPUPILD', 0)),
                        'left_open': float(eye_data.get('LEYEOPENESS', 0)) > 0.5,
                        'right_open': float(eye_data.get('REYEOPENESS', 0)) > 0.5,
                        'left_gaze_x': float(eye_data.get('LEYEGAZEX', 0.5)),
                        'left_gaze_y': float(eye_data.get('LEYEGAZEY', 0.5)),
                        'right_gaze_x': float(eye_data.get('REYEGAZEX', 0.5)),
                        'right_gaze_y': float(eye_data.get('REYEGAZEY', 0.5))
                    }
                    update_data['pupil_history'] = {
                        'left': list(self.data_buffers['pupil_left'])[-20:],
                        'right': list(self.data_buffers['pupil_right'])[-20:]
                    }
            
            elif data_type == 'fixation':
                # Extraire les données de fixation
                if 'fixation_data' in data and data['fixation_data']:
                    fix_data = data['fixation_data']
                    update_data['fixation'] = {
                        'duration': float(fix_data.get('FPOGD', 0)),
                        'x': float(fix_data.get('FPOGX', 0)),
                        'y': float(fix_data.get('FPOGY', 0))
                    }
                    update_data['fixation_history'] = list(self.data_buffers['fixation_duration'])[-20:]
            
            # Émettre vers le module home
            self.websocket_manager.emit_to_module('home', 'gazepoint_data_update', update_data)
        
        except Exception as e:
            logger.error(f"Erreur émission mise à jour Gazepoint: {e}")
    
    def emit_dashboard_state(self):
        """Émet l'état complet du dashboard"""
        try:
            state = {
                'devices': self._get_devices_summary(),
                'session': {
                    'is_collecting': self.collection_state['is_collecting'],
                    'duration': self._get_session_duration(),
                    'total_samples': self.session_stats['total_samples']
                },
                'timestamp': datetime.now().isoformat()
            }
            
            self.websocket_manager.emit_to_module('home', 'dashboard_state', state)
        
        except Exception as e:
            logger.error(f"Erreur émission état dashboard: {e}")
    
    def _get_devices_summary(self) -> Dict[str, Any]:
        """Récupère un résumé de l'état des appareils"""
        summary = {
            'polar': {
                'connected': any(dev['connected'] for dev in self.devices_state['polar'].values()),
                'devices': []
            },
            'neurosity': {
                'connected': self.devices_state['neurosity']['connected'],
                'battery': self.devices_state['neurosity'].get('battery'),
                'charging': self.devices_state['neurosity'].get('charging', False)
            },
            'thermal': {
                'connected': self.devices_state['thermal']['connected'],
                'capturing': self.devices_state['thermal']['capturing']
            },
            'gazepoint': {
                'connected': self.devices_state['gazepoint']['connected'],
                'calibrated': self.devices_state['gazepoint'].get('calibrated', False),
                'tracking_status': self.devices_state['gazepoint'].get('tracking_status', 'none')
            }
        }
        
        # Détails des appareils Polar connectés
        for device_type, state in self.devices_state['polar'].items():
            if state['connected']:
                summary['polar']['devices'].append(device_type)
        
        return summary
    
    def _update_active_devices_count(self):
        """Met à jour le compteur d'appareils actifs"""
        count = 0
        
        # Compter les appareils Polar
        for device in self.devices_state['polar'].values():
            if device['connected']:
                count += 1
        
        # Autres appareils
        if self.devices_state['neurosity']['connected']:
            count += 1
        if self.devices_state['thermal']['connected']:
            count += 1
        if self.devices_state['gazepoint']['connected']:
            count += 1
        
        self.session_stats['devices_active'] = count
    
    def _get_session_duration(self) -> float:
        """Calcule la durée de la session en secondes"""
        if self.collection_state['is_collecting'] and self.collection_state['start_time']:
            return (datetime.now() - self.collection_state['start_time']).total_seconds()
        return 0
    
    # === GESTION DE LA COLLECTE ===
    
    def start_collection(self):
        """Démarre la collecte globale"""
        try:
            if self.collection_state['is_collecting']:
                logger.warning("Collecte déjà en cours")
                return False
            
            # Démarrer l'enregistrement CSV sur tous les modules
            results = {}
            
            # Module Polar
            if self.polar_module:
                csv_files = self.polar_module.start_csv_recording()
                results['polar'] = {'success': bool(csv_files), 'files': csv_files}
            
            # Module Neurosity
            if self.neurosity_module and self.neurosity_module.is_connected:
                result = self.neurosity_module.start_recording()
                results['neurosity'] = result
            
            # Module Thermal
            if self.thermal_module and self.thermal_module.is_running:
                result = self.thermal_module.start_recording()
                results['thermal'] = {'success': result}
            
            # Module Gazepoint
            if self.gazepoint_module and hasattr(self.gazepoint_module,
                                                 'is_connected') and self.gazepoint_module.is_connected:
                if hasattr(self.gazepoint_module, 'start_recording'):
                    result = self.gazepoint_module.start_recording()
                    results['gazepoint'] = {'success': result}
            
            # Mettre à jour l'état
            self.collection_state['is_collecting'] = True
            self.collection_state['start_time'] = datetime.now()
            self.collection_state['session_id'] = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Réinitialiser les stats
            self.session_stats['start_time'] = self.collection_state['start_time']
            self.session_stats['total_samples'] = 0
            
            # Notifier le frontend
            self.websocket_manager.emit_to_module('home', 'collection_started', {
                'session_id': self.collection_state['session_id'],
                'results': results,
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info(f"Collecte globale démarrée: {self.collection_state['session_id']}")
            return True
        
        except Exception as e:
            logger.error(f"Erreur démarrage collecte: {e}")
            return False
    
    def stop_collection(self):
        """Arrête la collecte globale"""
        try:
            if not self.collection_state['is_collecting']:
                logger.warning("Aucune collecte en cours")
                return False
            
            # Arrêter l'enregistrement sur tous les modules
            results = {}
            
            # Module Polar
            if self.polar_module:
                stats = self.polar_module.stop_csv_recording()
                results['polar'] = stats
            
            # Module Neurosity
            if self.neurosity_module and self.neurosity_module.is_recording:
                result = self.neurosity_module.stop_recording()
                results['neurosity'] = result
            
            # Module Thermal
            if self.thermal_module and self.thermal_module.is_recording:
                result = self.thermal_module.stop_recording()
                results['thermal'] = {'success': result}
            
            # Module Gazepoint
            if self.gazepoint_module and hasattr(self.gazepoint_module,
                                                 'is_recording') and self.gazepoint_module.is_recording:
                if hasattr(self.gazepoint_module, 'stop_recording'):
                    result = self.gazepoint_module.stop_recording()
                    results['gazepoint'] = {'success': result}
            
            # Calculer la durée totale
            duration = self._get_session_duration()
            
            # Mettre à jour l'état
            self.collection_state['is_collecting'] = False
            session_id = self.collection_state['session_id']
            
            # Notifier le frontend
            self.websocket_manager.emit_to_module('home', 'collection_stopped', {
                'session_id': session_id,
                'duration': duration,
                'results': results,
                'total_samples': self.session_stats['total_samples'],
                'timestamp': datetime.now().isoformat()
            })
            
            # Réinitialiser
            self.collection_state['start_time'] = None
            self.collection_state['session_id'] = None
            
            logger.info(f"Collecte globale arrêtée: {session_id}, durée: {duration:.1f}s")
            return True
        
        except Exception as e:
            logger.error(f"Erreur arrêt collecte: {e}")
            return False
    
    async def get_aggregated_data(self) -> Dict[str, Any]:
        """Récupère les données agrégées de tous les modules"""
        data = {
            'devices': self._get_devices_summary(),
            'session': {
                'is_collecting': self.collection_state['is_collecting'],
                'duration': self._get_session_duration(),
                'total_samples': self.session_stats['total_samples'],
                'devices_active': self.session_stats['devices_active']
            },
            'latest_data': {},
            'timestamp': datetime.now().isoformat()
        }
        
        # Ajouter les dernières données si disponibles
        for device_type in ['h10', 'verity']:
            if self.devices_state['polar'][device_type]['last_data']:
                data['latest_data'][f'polar_{device_type}'] = self.devices_state['polar'][device_type]['last_data']
        
        if self.devices_state['neurosity']['last_data']:
            data['latest_data']['neurosity'] = self.devices_state['neurosity']['last_data']
        
        if self.devices_state['thermal']['last_data']:
            data['latest_data']['thermal'] = self.devices_state['thermal']['last_data']
        
        if self.devices_state['gazepoint']['last_data']:
            data['latest_data']['gazepoint'] = self.devices_state['gazepoint']['last_data']
        
        return data
    
    def cleanup(self):
        """Nettoie les ressources du module"""
        logger.info("Nettoyage du module Dashboard Home...")
        
        self._running = False
        
        # Attendre la fin du thread
        if self._update_thread and self._update_thread.is_alive():
            self._update_thread.join(timeout=2)
        
        # Arrêter la collecte si active
        if self.collection_state['is_collecting']:
            self.stop_collection()
        
        logger.info("Module Dashboard Home nettoyé")


# ===== FONCTION D'INITIALISATION =====

def init_dashboard_home_module(app, websocket_manager):
    """Initialise le module Dashboard Home"""
    dashboard_module = DashboardHomeModule(app, websocket_manager)
    
    # Démarrer les mises à jour périodiques
    dashboard_module.start_periodic_updates()
    
    logger.info("Module Dashboard Home initialisé avec succès")
    
    return dashboard_module


# ===== ENREGISTREMENT DES ÉVÉNEMENTS WEBSOCKET =====

def register_dashboard_home_websocket_events(websocket_manager, dashboard_module, polar_module=None,
                                             gazepoint_module=None):
    """Enregistre les événements WebSocket pour le module Dashboard Home"""
    
    # S'abonner aux broadcasts des autres modules
    def subscribe_to_broadcasts():
        """S'abonne aux événements broadcast des autres modules"""
        
        # Événements Polar
        @websocket_manager.socketio.on('polar_h10_data')
        def handle_polar_h10_data(data):
            dashboard_module.handle_polar_data('h10', data.get('data', {}))
        
        @websocket_manager.socketio.on('polar_verity_data')
        def handle_polar_verity_data(data):
            dashboard_module.handle_polar_data('verity', data.get('data', {}))
        
        @websocket_manager.socketio.on('polar_h10_connected')
        def handle_polar_h10_connected(data):
            dashboard_module.handle_polar_connected('h10', data.get('device_info', {}))
        
        @websocket_manager.socketio.on('polar_verity_connected')
        def handle_polar_verity_connected(data):
            dashboard_module.handle_polar_connected('verity', data.get('device_info', {}))
        
        @websocket_manager.socketio.on('polar_h10_disconnected')
        def handle_polar_h10_disconnected(data):
            dashboard_module.handle_polar_disconnected('h10')
        
        @websocket_manager.socketio.on('polar_verity_disconnected')
        def handle_polar_verity_disconnected(data):
            dashboard_module.handle_polar_disconnected('verity')
        
        # Événements Neurosity
        @websocket_manager.socketio.on('neurosity_calm_data')
        def handle_neurosity_calm_data(data):
            dashboard_module.handle_neurosity_data('calm', data)
        
        @websocket_manager.socketio.on('neurosity_focus_data')
        def handle_neurosity_focus_data(data):
            dashboard_module.handle_neurosity_data('focus', data)
        
        @websocket_manager.socketio.on('neurosity_brainwaves_data')
        def handle_neurosity_brainwaves_data(data):
            dashboard_module.handle_neurosity_data('brainwaves', data)
        
        @websocket_manager.socketio.on('neurosity_battery_data')
        def handle_neurosity_battery_data(data):
            dashboard_module.handle_neurosity_data('battery', data)
        
        @websocket_manager.socketio.on('neurosity_connected')
        def handle_neurosity_connected_event(data):
            dashboard_module.handle_neurosity_connected(data)
        
        @websocket_manager.socketio.on('neurosity_disconnected')
        def handle_neurosity_disconnected_event(data):
            dashboard_module.handle_neurosity_disconnected(data)
        
        # Événements Thermal
        @websocket_manager.socketio.on('thermal_temperature_data')
        def handle_thermal_temperature_data(data):
            dashboard_module.handle_thermal_data(data)
        
        @websocket_manager.socketio.on('capture_started')
        def handle_thermal_capture_started(data):
            dashboard_module.handle_thermal_connected()
        
        @websocket_manager.socketio.on('capture_stopped')
        def handle_thermal_capture_stopped(data):
            dashboard_module.handle_thermal_disconnected()
        
        # Événements Gazepoint
        @websocket_manager.socketio.on('gazepoint_gaze_data')
        def handle_gazepoint_gaze_data(data):
            dashboard_module.handle_gazepoint_data('gaze', data)
        
        @websocket_manager.socketio.on('gazepoint_eye_data')
        def handle_gazepoint_eye_data(data):
            dashboard_module.handle_gazepoint_data('eye', data)
        
        @websocket_manager.socketio.on('gazepoint_fixation_data')
        def handle_gazepoint_fixation_data(data):
            dashboard_module.handle_gazepoint_data('fixation', data)
        
        @websocket_manager.socketio.on('gazepoint_connected')
        def handle_gazepoint_connected_event(data):
            dashboard_module.handle_gazepoint_connected(data)
        
        @websocket_manager.socketio.on('gazepoint_disconnected')
        def handle_gazepoint_disconnected_event(data):
            dashboard_module.handle_gazepoint_disconnected(data)
        
        logger.info("Dashboard Home abonné aux événements broadcast")
    
    # Événements propres au module Home
    def handle_request_dashboard_state(data):
        """Demande l'état actuel du dashboard"""
        dashboard_module.emit_dashboard_state()
    
    def handle_start_collection(data):
        """Démarre la collecte globale"""
        success = dashboard_module.start_collection()
        return {'success': success}
    
    def handle_stop_collection(data):
        """Arrête la collecte globale"""
        success = dashboard_module.stop_collection()
        return {'success': success}
    
    def handle_get_aggregated_data(data):
        """Récupère les données agrégées"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        aggregated_data = loop.run_until_complete(dashboard_module.get_aggregated_data())
        websocket_manager.emit_to_module('home', 'aggregated_data', aggregated_data)
    
    # Enregistrer les événements du module
    home_events = {
        'request_dashboard_state': handle_request_dashboard_state,
        'start_collection': handle_start_collection,
        'stop_collection': handle_stop_collection,
        'get_aggregated_data': handle_get_aggregated_data
    }
    
    websocket_manager.register_module_events('home', home_events)
    
    # S'abonner aux broadcasts
    subscribe_to_broadcasts()
    
    logger.info("Événements WebSocket du module Dashboard Home enregistrés")