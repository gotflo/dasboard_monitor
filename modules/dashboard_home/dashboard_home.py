#!/usr/bin/env python3
"""
Module Dashboard Enhanced - Backend amélioré pour la page d'accueil
Gestion avancée des données avec analytics en temps réel et système d'alertes
"""

from flask import Blueprint, jsonify, request, send_file
from datetime import datetime, timedelta
import logging
import os
import json
import numpy as np
import pandas as pd
from pathlib import Path
from collections import deque, defaultdict
import threading
import time
from typing import Dict, List, Tuple, Optional
import io
import zipfile

# Créer le blueprint pour ce module
dashboard_bp = Blueprint(
    'dashboard_module',
    __name__,
    url_prefix='/api/dashboard'
)

logger = logging.getLogger(__name__)


class DataBuffer:
    """Buffer circulaire pour stocker les données en mémoire"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.buffers = defaultdict(lambda: deque(maxlen=max_size))
        self._lock = threading.Lock()
    
    def add(self, module: str, data: dict):
        """Ajouter des données au buffer"""
        with self._lock:
            timestamp = datetime.now()
            self.buffers[module].append({
                'timestamp': timestamp.isoformat(),
                'data': data
            })
    
    def get_recent(self, module: str, count: int = 100) -> List[dict]:
        """Récupérer les données récentes"""
        with self._lock:
            buffer = self.buffers.get(module, [])
            return list(buffer)[-count:]
    
    def get_all(self) -> Dict[str, List[dict]]:
        """Récupérer toutes les données"""
        with self._lock:
            return {k: list(v) for k, v in self.buffers.items()}


class AlertSystem:
    """Système d'alertes intelligent"""
    
    def __init__(self):
        self.alert_rules = {
            'heart_rate': {
                'min': 40,
                'max': 180,
                'rapid_change': 30  # Changement de plus de 30 BPM en 1 minute
            },
            'temperature': {
                'min': 35.5,
                'max': 37.5,
                'fever_threshold': 37.8
            },
            'stress_level': {
                'high_threshold': 0.8,
                'duration': 300  # 5 minutes
            },
            'eeg': {
                'seizure_pattern': {
                    'gamma_spike': 50,
                    'duration': 10
                }
            }
        }
        
        self.active_alerts = {}
        self.alert_history = deque(maxlen=100)
        self._lock = threading.Lock()
    
    def check_heart_rate(self, current_hr: float, history: List[float]) -> Optional[dict]:
        """Vérifier les alertes de fréquence cardiaque"""
        rules = self.alert_rules['heart_rate']
        
        # Vérifier les limites
        if current_hr < rules['min']:
            return {
                'type': 'heart_rate_low',
                'severity': 'warning',
                'message': f'Fréquence cardiaque basse: {current_hr} BPM',
                'value': current_hr
            }
        elif current_hr > rules['max']:
            return {
                'type': 'heart_rate_high',
                'severity': 'critical',
                'message': f'Fréquence cardiaque élevée: {current_hr} BPM',
                'value': current_hr
            }
        
        # Vérifier les changements rapides
        if len(history) >= 2:
            recent_avg = np.mean(history[-5:]) if len(history) >= 5 else history[-1]
            change = abs(current_hr - recent_avg)
            if change > rules['rapid_change']:
                return {
                    'type': 'heart_rate_rapid_change',
                    'severity': 'warning',
                    'message': f'Changement rapide de FC: {change:.1f} BPM',
                    'value': current_hr,
                    'change': change
                }
        
        return None
    
    def check_temperature(self, temps: Dict[str, float]) -> Optional[dict]:
        """Vérifier les alertes de température"""
        rules = self.alert_rules['temperature']
        avg_temp = np.mean(list(temps.values()))
        
        if avg_temp > rules['fever_threshold']:
            return {
                'type': 'fever_detected',
                'severity': 'critical',
                'message': f'Fièvre détectée: {avg_temp:.1f}°C',
                'value': avg_temp,
                'details': temps
            }
        elif avg_temp > rules['max']:
            return {
                'type': 'temperature_high',
                'severity': 'warning',
                'message': f'Température élevée: {avg_temp:.1f}°C',
                'value': avg_temp
            }
        elif avg_temp < rules['min']:
            return {
                'type': 'temperature_low',
                'severity': 'warning',
                'message': f'Température basse: {avg_temp:.1f}°C',
                'value': avg_temp
            }
        
        return None
    
    def process_alert(self, module: str, alert: dict):
        """Traiter et enregistrer une alerte"""
        with self._lock:
            alert_id = f"{module}_{alert['type']}"
            alert['module'] = module
            alert['timestamp'] = datetime.now().isoformat()
            alert['id'] = alert_id
            
            self.active_alerts[alert_id] = alert
            self.alert_history.append(alert)
            
            return alert
    
    def get_active_alerts(self) -> List[dict]:
        """Récupérer toutes les alertes actives"""
        with self._lock:
            return list(self.active_alerts.values())
    
    def clear_alert(self, alert_id: str):
        """Supprimer une alerte"""
        with self._lock:
            if alert_id in self.active_alerts:
                del self.active_alerts[alert_id]


class Analytics:
    """Moteur d'analyse en temps réel"""
    
    def __init__(self, data_buffer: DataBuffer):
        self.data_buffer = data_buffer
    
    def calculate_correlation(self, module1: str, module2: str,
                              metric1: str, metric2: str) -> float:
        """Calculer la corrélation entre deux métriques"""
        data1 = self.data_buffer.get_recent(module1, 100)
        data2 = self.data_buffer.get_recent(module2, 100)
        
        if not data1 or not data2:
            return 0.0
        
        # Extraire les valeurs
        values1 = [d['data'].get(metric1, 0) for d in data1]
        values2 = [d['data'].get(metric2, 0) for d in data2]
        
        # Aligner les données par timestamp
        min_len = min(len(values1), len(values2))
        if min_len < 2:
            return 0.0
        
        values1 = values1[-min_len:]
        values2 = values2[-min_len:]
        
        # Calculer la corrélation
        return np.corrcoef(values1, values2)[0, 1]
    
    def detect_patterns(self, module: str) -> Dict[str, any]:
        """Détecter des patterns dans les données"""
        data = self.data_buffer.get_recent(module, 200)
        if not data:
            return {}
        
        patterns = {
            'trend': self._calculate_trend(data),
            'periodicity': self._detect_periodicity(data),
            'anomalies': self._detect_anomalies(data)
        }
        
        return patterns
    
    def _calculate_trend(self, data: List[dict]) -> str:
        """Calculer la tendance (montante, descendante, stable)"""
        if len(data) < 10:
            return 'insufficient_data'
        
        # Utiliser une régression linéaire simple
        values = [d['data'].get('value', 0) for d in data[-20:]]
        x = np.arange(len(values))
        
        if len(set(values)) == 1:  # Toutes les valeurs sont identiques
            return 'stable'
        
        slope = np.polyfit(x, values, 1)[0]
        
        if abs(slope) < 0.1:
            return 'stable'
        elif slope > 0:
            return 'increasing'
        else:
            return 'decreasing'
    
    def _detect_periodicity(self, data: List[dict]) -> Optional[float]:
        """Détecter la périodicité dans les données"""
        if len(data) < 50:
            return None
        
        # Extraire les valeurs
        values = [d['data'].get('value', 0) for d in data]
        
        # Utiliser l'autocorrélation pour détecter la périodicité
        autocorr = np.correlate(values, values, mode='full')
        autocorr = autocorr[len(autocorr) // 2:]
        
        # Trouver les pics
        peaks = []
        for i in range(10, len(autocorr) - 10):
            if autocorr[i] > autocorr[i - 1] and autocorr[i] > autocorr[i + 1]:
                peaks.append(i)
        
        if peaks:
            return float(peaks[0])  # Retourner la première période détectée
        
        return None
    
    def _detect_anomalies(self, data: List[dict]) -> List[dict]:
        """Détecter les anomalies dans les données"""
        if len(data) < 20:
            return []
        
        values = [d['data'].get('value', 0) for d in data]
        
        # Calculer les statistiques
        mean = np.mean(values)
        std = np.std(values)
        
        # Détecter les outliers (> 3 écarts-types)
        anomalies = []
        for i, value in enumerate(values):
            if abs(value - mean) > 3 * std:
                anomalies.append({
                    'index': i,
                    'value': value,
                    'deviation': (value - mean) / std,
                    'timestamp': data[i]['timestamp']
                })
        
        return anomalies
    
    def generate_insights(self) -> List[dict]:
        """Générer des insights basés sur l'analyse globale"""
        insights = []
        
        # Analyse de corrélation FC-Stress
        hr_stress_corr = self.calculate_correlation(
            'polar', 'neurosity', 'heart_rate', 'stress_level'
        )
        
        if abs(hr_stress_corr) > 0.7:
            insights.append({
                'type': 'correlation',
                'title': 'Corrélation FC-Stress',
                'message': f'Forte corrélation détectée entre fréquence cardiaque et niveau de stress ({hr_stress_corr:.2f})',
                'severity': 'info',
                'recommendation': 'Considérer des techniques de relaxation lors de stress élevé'
            })
        
        # Analyse des patterns
        for module in ['polar', 'neurosity', 'thermal_camera']:
            patterns = self.detect_patterns(module)
            if patterns.get('trend') == 'increasing' and module == 'polar':
                insights.append({
                    'type': 'trend',
                    'title': 'Tendance FC',
                    'message': 'Fréquence cardiaque en augmentation constante',
                    'severity': 'warning',
                    'recommendation': 'Surveiller l\'évolution et considérer une pause'
                })
        
        return insights


class DashboardModule:
    """Module de gestion du dashboard principal amélioré"""
    
    def __init__(self, app, websocket_manager):
        self.app = app
        self.websocket_manager = websocket_manager
        
        # État des modules
        self.modules_status = {
            'polar': {
                'connected': False,
                'active': False,
                'last_update': None,
                'metrics': {
                    'heart_rate': None,
                    'rr_interval': None,
                    'hrv': None
                }
            },
            'neurosity': {
                'connected': False,
                'active': False,
                'last_update': None,
                'metrics': {
                    'calm': None,
                    'focus': None,
                    'stress_level': None
                }
            },
            'thermal_camera': {
                'connected': False,
                'active': False,
                'last_update': None,
                'metrics': {
                    'avg_temperature': None,
                    'max_temperature': None
                }
            },
            'gazepoint': {
                'connected': False,
                'active': False,
                'last_update': None,
                'metrics': {
                    'pupil_diameter': None,
                    'fixation_duration': None
                }
            },
            'thought_capture': {
                'connected': False,
                'active': False,
                'last_update': None,
                'metrics': {
                    'is_recording': False,
                    'audio_level': None
                }
            }
        }
        
        # Statistiques globales
        self.global_stats = {
            'data_points': 0,
            'session_start': None,
            'storage_used': 0,
            'active_modules': 0,
            'total_alerts': 0,
            'session_quality': 100  # Score de qualité de session
        }
        
        # Composants du système
        self.data_buffer = DataBuffer(max_size=1000)
        self.alert_system = AlertSystem()
        self.analytics = Analytics(self.data_buffer)
        
        # Buffer des événements récents
        self.activity_log = deque(maxlen=100)
        
        # Thread de monitoring
        self.monitoring_thread = None
        self.monitoring_active = False
        
        # Configuration
        self.config = {
            'auto_export': False,
            'export_interval': 300,  # 5 minutes
            'alert_notifications': True,
            'performance_monitoring': True
        }
        
        logger.info("Module Dashboard Enhanced initialisé")
        
        # Démarrer le monitoring
        self.start_monitoring()
    
    def start_monitoring(self):
        """Démarrer le thread de monitoring"""
        if not self.monitoring_active:
            self.monitoring_active = True
            self.monitoring_thread = threading.Thread(target=self._monitoring_loop)
            self.monitoring_thread.daemon = True
            self.monitoring_thread.start()
            logger.info("Thread de monitoring démarré")
    
    def stop_monitoring(self):
        """Arrêter le thread de monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join()
            logger.info("Thread de monitoring arrêté")
    
    def _monitoring_loop(self):
        """Boucle principale de monitoring"""
        last_export = time.time()
        
        while self.monitoring_active:
            try:
                # Calculer les métriques de performance
                self._update_performance_metrics()
                
                # Vérifier les alertes
                self._check_all_alerts()
                
                # Export automatique si configuré
                if self.config['auto_export']:
                    if time.time() - last_export > self.config['export_interval']:
                        self._auto_export_data()
                        last_export = time.time()
                
                # Nettoyer les anciennes alertes
                self._cleanup_old_alerts()
                
                time.sleep(1)  # Vérification toutes les secondes
            
            except Exception as e:
                logger.error(f"Erreur dans la boucle de monitoring: {e}")
    
    def update_module_status(self, module_name: str, status: dict, data: dict = None):
        """Met à jour le statut d'un module avec analyse"""
        if module_name not in self.modules_status:
            return
        
        # Mise à jour basique
        self.modules_status[module_name].update({
            'connected': status.get('connected', False),
            'active': status.get('active', False),
            'last_update': datetime.now().isoformat()
        })
        
        # Mise à jour des métriques
        if data:
            if 'metrics' not in self.modules_status[module_name]:
                self.modules_status[module_name]['metrics'] = {}
            
            self.modules_status[module_name]['metrics'].update(data)
            
            # Ajouter au buffer de données
            self.data_buffer.add(module_name, data)
            
            # Vérifier les alertes spécifiques au module
            self._check_module_alerts(module_name, data)
            
            # Incrémenter les points de données
            self.global_stats['data_points'] += 1
        
        # Calculer le nombre de modules actifs
        self.global_stats['active_modules'] = sum(
            1 for m in self.modules_status.values()
            if m.get('active', False)
        )
        
        # Calculer la qualité de session
        self._update_session_quality()
        
        # Émettre la mise à jour via WebSocket
        self.websocket_manager.emit_to_module('dashboard', 'module_status_update', {
            'module': module_name,
            'status': self.modules_status[module_name],
            'timestamp': datetime.now().isoformat()
        })
    
    def _check_module_alerts(self, module_name: str, data: dict):
        """Vérifier les alertes pour un module spécifique"""
        alert = None
        
        if module_name == 'polar' and 'heart_rate' in data:
            # Récupérer l'historique
            history_data = self.data_buffer.get_recent('polar', 20)
            history = [d['data'].get('heart_rate', 0) for d in history_data]
            alert = self.alert_system.check_heart_rate(data['heart_rate'], history)
        
        elif module_name == 'thermal_camera' and 'temperatures' in data:
            alert = self.alert_system.check_temperature(data['temperatures'])
        
        if alert:
            processed_alert = self.alert_system.process_alert(module_name, alert)
            self._emit_alert(processed_alert)
            self.global_stats['total_alerts'] += 1
    
    def _emit_alert(self, alert: dict):
        """Émettre une alerte via WebSocket"""
        self.websocket_manager.emit_to_module('dashboard', 'alert', alert)
        self.add_activity_log(
            alert['module'],
            f"Alerte: {alert['message']}",
            alert['severity']
        )
    
    def _update_session_quality(self):
        """Calculer le score de qualité de session"""
        quality = 100
        
        # Réduire pour chaque module déconnecté
        disconnected = sum(1 for m in self.modules_status.values() if not m['connected'])
        quality -= disconnected * 10
        
        # Réduire pour les alertes actives
        active_alerts = len(self.alert_system.get_active_alerts())
        quality -= active_alerts * 5
        
        # Bonus pour la durée de session stable
        if self.global_stats['session_start']:
            session_duration = (datetime.now() - datetime.fromisoformat(self.global_stats['session_start'])).seconds
            if session_duration > 600:  # Plus de 10 minutes
                quality += 10
        
        self.global_stats['session_quality'] = max(0, min(100, quality))
    
    def emit_module_summary(self):
        """Émet un résumé périodique vers les clients"""
        summary = self.get_dashboard_summary()
        self.websocket_manager.emit_to_module('dashboard', 'summary_update', summary)
    
    def handle_module_data_request(self, module_name):
        """Gère les demandes de données spécifiques d'un module"""
        if module_name in self.modules_status:
            return {
                'success': True,
                'data': self.modules_status[module_name]
            }
        return {'success': False, 'error': 'Module not found'}
    
    
    def _update_performance_metrics(self):
        """Mettre à jour les métriques de performance"""
        # Calculer le taux de données
        if hasattr(self, '_last_data_points'):
            data_rate = self.global_stats['data_points'] - self._last_data_points
            self.websocket_manager.emit_to_module('dashboard', 'performance_metrics', {
                'data_rate': data_rate,
                'buffer_sizes': {k: len(v) for k, v in self.data_buffer.buffers.items()},
                'active_alerts': len(self.alert_system.get_active_alerts()),
                'timestamp': datetime.now().isoformat()
            })
        
        self._last_data_points = self.global_stats['data_points']
    
    def _check_all_alerts(self):
        """Vérifier toutes les alertes système"""
        # Vérifier la cohérence des données entre modules
        correlations = self.analytics.generate_insights()
        for insight in correlations:
            if insight['severity'] in ['warning', 'critical']:
                self._emit_alert({
                    'type': 'insight',
                    'module': 'system',
                    **insight
                })
    
    def _cleanup_old_alerts(self):
        """Nettoyer les alertes anciennes"""
        # Supprimer les alertes de plus de 30 minutes
        cutoff_time = datetime.now() - timedelta(minutes=30)
        
        for alert_id, alert in list(self.alert_system.active_alerts.items()):
            alert_time = datetime.fromisoformat(alert['timestamp'])
            if alert_time < cutoff_time:
                self.alert_system.clear_alert(alert_id)
    
    def add_activity_log(self, module: str, message: str, level: str = 'info'):
        """Ajoute un événement au log d'activité avec métadonnées"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'module': module,
            'message': message,
            'level': level,
            'session_time': self._get_session_duration()
        }
        
        self.activity_log.append(event)
        
        # Émettre l'événement
        self.websocket_manager.emit_to_module('dashboard', 'activity_log', event)
    
    def _get_session_duration(self) -> str:
        """Calculer la durée de session"""
        if not self.global_stats['session_start']:
            return "00:00:00"
        
        duration = datetime.now() - datetime.fromisoformat(self.global_stats['session_start'])
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60
        seconds = duration.seconds % 60
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def get_dashboard_summary(self) -> dict:
        """Récupère un résumé complet enrichi pour le dashboard"""
        summary = {
            'modules_status': self.modules_status,
            'global_stats': self.global_stats,
            'recent_activity': list(self.activity_log)[:20],
            'active_alerts': self.alert_system.get_active_alerts(),
            'analytics': {
                'correlations': self._get_key_correlations(),
                'insights': self.analytics.generate_insights()[:5],
                'trends': self._get_module_trends()
            },
            'session_info': {
                'duration': self._get_session_duration(),
                'quality_score': self.global_stats['session_quality'],
                'data_rate': self._calculate_data_rate()
            },
            'timestamp': datetime.now().isoformat()
        }
        
        return summary
    
    def _get_key_correlations(self) -> dict:
        """Obtenir les corrélations clés entre modules"""
        correlations = {}
        
        # FC vs Stress
        correlations['heart_stress'] = self.analytics.calculate_correlation(
            'polar', 'neurosity', 'heart_rate', 'stress_level'
        )
        
        # Température vs FC
        correlations['temp_heart'] = self.analytics.calculate_correlation(
            'thermal_camera', 'polar', 'avg_temperature', 'heart_rate'
        )
        
        return correlations
    
    def _get_module_trends(self) -> dict:
        """Obtenir les tendances pour chaque module"""
        trends = {}
        for module in self.modules_status.keys():
            patterns = self.analytics.detect_patterns(module)
            trends[module] = patterns.get('trend', 'unknown')
        
        return trends
    
    def _calculate_data_rate(self) -> float:
        """Calculer le taux de données par seconde"""
        if not hasattr(self, '_data_rate_buffer'):
            self._data_rate_buffer = deque(maxlen=10)
        
        # Calculer le taux actuel
        current_rate = getattr(self, '_last_data_rate', 0)
        self._data_rate_buffer.append(current_rate)
        
        # Moyenne mobile
        return np.mean(self._data_rate_buffer) if self._data_rate_buffer else 0
    
    def start_global_collection(self) -> dict:
        """Démarre la collecte globale de données avec configuration"""
        self.global_stats['session_start'] = datetime.now().isoformat()
        self.global_stats['data_points'] = 0
        self.global_stats['total_alerts'] = 0
        
        # Réinitialiser les buffers
        self.data_buffer = DataBuffer(max_size=1000)
        self.alert_system.active_alerts.clear()
        
        self.add_activity_log('Système', 'Démarrage de la collecte globale', 'success')
        
        # Configuration de session
        session_config = {
            'session_id': f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'modules': list(self.modules_status.keys()),
            'sampling_rates': {
                'polar': 130,  # Hz
                'neurosity': 256,  # Hz
                'thermal_camera': 30,  # FPS
                'gazepoint': 60,  # Hz
                'thought_capture': 44100  # Hz (audio)
            }
        }
        
        # Notifier tous les modules de démarrer avec config
        self.websocket_manager.broadcast('global_collection_start', {
            'timestamp': datetime.now().isoformat(),
            'config': session_config
        })
        
        return {
            'success': True,
            'message': 'Collecte globale démarrée',
            'session_config': session_config
        }
    
    def stop_global_collection(self) -> dict:
        """Arrête la collecte globale avec rapport"""
        if not self.global_stats['session_start']:
            return {'success': False, 'message': 'Aucune session active'}
        
        # Calculer les statistiques de session
        session_duration = datetime.now() - datetime.fromisoformat(self.global_stats['session_start'])
        
        session_report = {
            'duration': str(session_duration),
            'total_data_points': self.global_stats['data_points'],
            'total_alerts': self.global_stats['total_alerts'],
            'quality_score': self.global_stats['session_quality'],
            'modules_data': {
                module: len(self.data_buffer.buffers.get(module, []))
                for module in self.modules_status.keys()
            },
            'insights': self.analytics.generate_insights()
        }
        
        self.add_activity_log(
            'Système',
            f'Arrêt de la collecte après {session_duration}',
            'info'
        )
        
        # Sauvegarder le rapport de session
        self._save_session_report(session_report)
        
        self.global_stats['session_start'] = None
        
        # Notifier tous les modules d'arrêter
        self.websocket_manager.broadcast('global_collection_stop', {
            'timestamp': datetime.now().isoformat(),
            'report': session_report
        })
        
        return {
            'success': True,
            'message': 'Collecte globale arrêtée',
            'report': session_report
        }
    
    def _save_session_report(self, report: dict):
        """Sauvegarder le rapport de session"""
        reports_dir = Path(self.app.root_path) / 'session_reports'
        reports_dir.mkdir(exist_ok=True)
        
        filename = f"session_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = reports_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"Rapport de session sauvegardé: {filename}")
    
    def calculate_storage_used(self) -> float:
        """Calcule l'espace de stockage utilisé avec détails"""
        storage_details = {}
        total_size = 0
        
        # Parcourir les dossiers de données
        data_dirs = {
            'neurosity': 'recordings/neurosity',
            'thermal': 'recordings/thermal',
            'audio': 'static/audio_recordings',
            'reports': 'session_reports'
        }
        
        for category, dir_path in data_dirs.items():
            full_path = Path(self.app.root_path) / dir_path
            category_size = 0
            
            if full_path.exists():
                for file in full_path.rglob('*'):
                    if file.is_file():
                        size = file.stat().st_size
                        category_size += size
                        total_size += size
            
            storage_details[category] = round(category_size / (1024 * 1024), 2)
        
        # Convertir en MB
        self.global_stats['storage_used'] = round(total_size / (1024 * 1024), 2)
        self.global_stats['storage_details'] = storage_details
        
        return self.global_stats['storage_used']
    
    def export_session_data(self, format: str = 'json') -> tuple:
        """Exporter toutes les données de session"""
        export_data = {
            'session_info': {
                'export_time': datetime.now().isoformat(),
                'duration': self._get_session_duration(),
                'quality_score': self.global_stats['session_quality']
            },
            'modules_data': self.data_buffer.get_all(),
            'alerts': list(self.alert_system.alert_history),
            'analytics': {
                'correlations': self._get_key_correlations(),
                'insights': self.analytics.generate_insights()
            },
            'activity_log': list(self.activity_log)
        }
        
        if format == 'json':
            return self._export_json(export_data)
        elif format == 'csv':
            return self._export_csv(export_data)
        elif format == 'zip':
            return self._export_zip(export_data)
        else:
            raise ValueError(f"Format non supporté: {format}")
    
    def _export_json(self, data: dict) -> tuple:
        """Exporter en JSON"""
        json_str = json.dumps(data, indent=2)
        buffer = io.BytesIO(json_str.encode())
        filename = f"biomedical_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        return buffer, filename
    
    def _export_csv(self, data: dict) -> tuple:
        """Exporter en CSV (un fichier par module)"""
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Exporter chaque module
            for module, module_data in data['modules_data'].items():
                if module_data:
                    df = pd.DataFrame(module_data)
                    csv_buffer = io.StringIO()
                    df.to_csv(csv_buffer, index=False)
                    zipf.writestr(f"{module}_data.csv", csv_buffer.getvalue())
            
            # Exporter les alertes
            if data['alerts']:
                alerts_df = pd.DataFrame(data['alerts'])
                csv_buffer = io.StringIO()
                alerts_df.to_csv(csv_buffer, index=False)
                zipf.writestr("alerts.csv", csv_buffer.getvalue())
        
        zip_buffer.seek(0)
        filename = f"biomedical_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        return zip_buffer, filename
    
    def _export_zip(self, data: dict) -> tuple:
        """Exporter toutes les données dans un ZIP"""
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # JSON principal
            zipf.writestr("complete_data.json", json.dumps(data, indent=2))
            
            # Rapport de session
            report = {
                'session_summary': data['session_info'],
                'insights': data['analytics']['insights'],
                'correlations': data['analytics']['correlations']
            }
            zipf.writestr("session_report.json", json.dumps(report, indent=2))
            
            # Données par module en CSV
            for module, module_data in data['modules_data'].items():
                if module_data:
                    df = pd.DataFrame(module_data)
                    csv_buffer = io.StringIO()
                    df.to_csv(csv_buffer, index=False)
                    zipf.writestr(f"data/{module}_data.csv", csv_buffer.getvalue())
        
        zip_buffer.seek(0)
        filename = f"biomedical_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        return zip_buffer, filename
    
    def _auto_export_data(self):
        """Export automatique des données"""
        try:
            buffer, filename = self.export_session_data('zip')
            
            # Sauvegarder dans le dossier exports
            exports_dir = Path(self.app.root_path) / 'auto_exports'
            exports_dir.mkdir(exist_ok=True)
            
            filepath = exports_dir / filename
            with open(filepath, 'wb') as f:
                f.write(buffer.read())
            
            logger.info(f"Export automatique réussi: {filename}")
            self.add_activity_log('Système', f'Export automatique: {filename}', 'success')
        
        except Exception as e:
            logger.error(f"Erreur lors de l'export automatique: {e}")
    
    def get_realtime_analytics(self) -> dict:
        """Obtenir les analyses en temps réel"""
        return {
            'correlations': {
                'heart_stress': self.analytics.calculate_correlation(
                    'polar', 'neurosity', 'heart_rate', 'stress_level'
                ),
                'temp_heart': self.analytics.calculate_correlation(
                    'thermal_camera', 'polar', 'avg_temperature', 'heart_rate'
                ),
                'focus_gaze': self.analytics.calculate_correlation(
                    'neurosity', 'gazepoint', 'focus', 'fixation_duration'
                )
            },
            'patterns': {
                module: self.analytics.detect_patterns(module)
                for module in ['polar', 'neurosity', 'thermal_camera']
            },
            'insights': self.analytics.generate_insights(),
            'performance': {
                'data_rate': self._calculate_data_rate(),
                'buffer_usage': {
                    module: len(buffer) / self.data_buffer.max_size * 100
                    for module, buffer in self.data_buffer.buffers.items()
                }
            },
            'timestamp': datetime.now().isoformat()
        }


def init_dashboard_module(app, websocket_manager):
    """Initialise le module dashboard amélioré"""
    dashboard_module = DashboardModule(app, websocket_manager)
    
    # Enregistrer le blueprint
    app.register_blueprint(dashboard_bp)
    
    # Routes API améliorées
    @dashboard_bp.route('/summary')
    def get_dashboard_summary():
        """Récupère le résumé complet du dashboard"""
        return jsonify(dashboard_module.get_dashboard_summary())
    
    @dashboard_bp.route('/modules/status')
    def get_modules_status():
        """Récupère le statut détaillé de tous les modules"""
        return jsonify({
            'modules': dashboard_module.modules_status,
            'timestamp': datetime.now().isoformat()
        })
    
    @dashboard_bp.route('/analytics/realtime')
    def get_realtime_analytics():
        """Récupère les analyses en temps réel"""
        return jsonify(dashboard_module.get_realtime_analytics())
    
    @dashboard_bp.route('/alerts')
    def get_alerts():
        """Récupère toutes les alertes actives"""
        return jsonify({
            'active': dashboard_module.alert_system.get_active_alerts(),
            'history': list(dashboard_module.alert_system.alert_history)[:50],
            'timestamp': datetime.now().isoformat()
        })
    
    @dashboard_bp.route('/alerts/<alert_id>', methods=['DELETE'])
    def clear_alert(alert_id):
        """Supprimer une alerte"""
        dashboard_module.alert_system.clear_alert(alert_id)
        return jsonify({'success': True})
    
    @dashboard_bp.route('/start-collection', methods=['POST'])
    def start_collection():
        """Démarre la collecte globale avec configuration"""
        config = request.json or {}
        dashboard_module.config.update(config)
        result = dashboard_module.start_global_collection()
        return jsonify(result)
    
    @dashboard_bp.route('/stop-collection', methods=['POST'])
    def stop_collection():
        """Arrête la collecte globale avec rapport"""
        result = dashboard_module.stop_global_collection()
        return jsonify(result)
    
    @dashboard_bp.route('/export/<format>')
    def export_data(format):
        """Exporter les données dans différents formats"""
        try:
            buffer, filename = dashboard_module.export_session_data(format)
            return send_file(
                buffer,
                as_attachment=True,
                download_name=filename,
                mimetype='application/octet-stream'
            )
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
    
    @dashboard_bp.route('/storage')
    def get_storage_info():
        """Récupère les informations détaillées de stockage"""
        storage_mb = dashboard_module.calculate_storage_used()
        return jsonify({
            'storage_used_mb': storage_mb,
            'storage_used_formatted': f"{storage_mb} MB",
            'storage_details': dashboard_module.global_stats.get('storage_details', {}),
            'timestamp': datetime.now().isoformat()
        })
    
    @dashboard_bp.route('/activity-log')
    def get_activity_log():
        """Récupère le log d'activité enrichi"""
        return jsonify({
            'events': list(dashboard_module.activity_log)[:50],
            'total_events': len(dashboard_module.activity_log),
            'timestamp': datetime.now().isoformat()
        })
    
    @dashboard_bp.route('/config', methods=['GET', 'POST'])
    def handle_config():
        """Gérer la configuration du dashboard"""
        if request.method == 'POST':
            new_config = request.json
            dashboard_module.config.update(new_config)
            return jsonify({
                'success': True,
                'config': dashboard_module.config
            })
        else:
            return jsonify(dashboard_module.config)
    
    @dashboard_bp.route('/insights')
    def get_insights():
        """Récupère les insights générés par l'IA"""
        insights = dashboard_module.analytics.generate_insights()
        return jsonify({
            'insights': insights,
            'count': len(insights),
            'timestamp': datetime.now().isoformat()
        })
    
    return dashboard_module


def register_dashboard_websocket_events(websocket_manager, dashboard_module):
    """Enregistre les événements WebSocket améliorés pour le dashboard"""
    
    def handle_request_summary(data):
        """Envoie le résumé complet du dashboard"""
        summary = dashboard_module.get_dashboard_summary()
        websocket_manager.emit_to_current_client('dashboard_summary', summary)
    
    def handle_request_analytics(data):
        """Envoie les analyses en temps réel"""
        analytics = dashboard_module.get_realtime_analytics()
        websocket_manager.emit_to_current_client('realtime_analytics', analytics)
    
    def handle_module_status_request(data):
        """Envoie le statut détaillé d'un module"""
        module_name = data.get('module')
        if module_name in dashboard_module.modules_status:
            status = dashboard_module.modules_status[module_name]
            
            # Ajouter les analyses spécifiques au module
            patterns = dashboard_module.analytics.detect_patterns(module_name)
            
            websocket_manager.emit_to_current_client('module_status', {
                'module': module_name,
                'status': status,
                'patterns': patterns,
                'buffer_size': len(dashboard_module.data_buffer.buffers.get(module_name, []))
            })
    
    def handle_start_global_collection(data):
        """Démarre la collecte globale avec configuration"""
        config = data.get('config', {})
        dashboard_module.config.update(config)
        result = dashboard_module.start_global_collection()
        websocket_manager.emit_to_current_client('collection_started', result)
    
    def handle_stop_global_collection(data):
        """Arrête la collecte globale et envoie le rapport"""
        result = dashboard_module.stop_global_collection()
        websocket_manager.emit_to_current_client('collection_stopped', result)
    
    def handle_module_update(data):
        """Reçoit les mises à jour d'état des autres modules"""
        module_name = data.get('module')
        status = data.get('status', {})
        module_data = data.get('data')
        
        if module_name:
            dashboard_module.update_module_status(module_name, status, module_data)
    
    def handle_clear_alert(data):
        """Supprimer une alerte"""
        alert_id = data.get('alert_id')
        if alert_id:
            dashboard_module.alert_system.clear_alert(alert_id)
            websocket_manager.emit_to_current_client('alert_cleared', {
                'alert_id': alert_id,
                'success': True
            })
    
    def handle_export_request(data):
        """Gérer une demande d'export"""
        format = data.get('format', 'json')
        try:
            buffer, filename = dashboard_module.export_session_data(format)
            # En WebSocket, on envoie juste une notification
            websocket_manager.emit_to_current_client('export_ready', {
                'filename': filename,
                'format': format,
                'size': buffer.getbuffer().nbytes
            })
        except Exception as e:
            websocket_manager.emit_to_current_client('export_error', {
                'error': str(e)
            })
    
    def handle_config_update(data):
        """Mettre à jour la configuration"""
        new_config = data.get('config', {})
        dashboard_module.config.update(new_config)
        websocket_manager.emit_to_current_client('config_updated', {
            'config': dashboard_module.config,
            'success': True
        })
    
    # Enregistrer tous les événements
    dashboard_events = {
        'request_summary': handle_request_summary,
        'request_analytics': handle_request_analytics,
        'request_module_status': handle_module_status_request,
        'start_global_collection': handle_start_global_collection,
        'stop_global_collection': handle_stop_global_collection,
        'module_update': handle_module_update,
        'clear_alert': handle_clear_alert,
        'export_data': handle_export_request,
        'update_config': handle_config_update
    }
    
    websocket_manager.register_module_events('dashboard', dashboard_events)
    logger.info("Événements WebSocket améliorés du dashboard enregistrés")