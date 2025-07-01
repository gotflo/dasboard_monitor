#!/usr/bin/env python3
"""
Module Dashboard - Backend pour la page d'accueil
Gestion des données agrégées et coordination des modules
"""

from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
import logging
import os
import json
from pathlib import Path

# Créer le blueprint pour ce module
dashboard_bp = Blueprint(
    'dashboard_module',
    __name__,
    url_prefix='/api/dashboard'
)

logger = logging.getLogger(__name__)


class DashboardModule:
    """Module de gestion du dashboard principal"""
    
    def __init__(self, app, websocket_manager):
        self.app = app
        self.websocket_manager = websocket_manager
        
        # État des modules
        self.modules_status = {
            'polar': {'connected': False, 'active': False, 'last_update': None},
            'neurosity': {'connected': False, 'active': False, 'last_update': None},
            'thermal_camera': {'connected': False, 'active': False, 'last_update': None},
            'gazepoint': {'connected': False, 'active': False, 'last_update': None},
            'thought_capture': {'connected': False, 'active': False, 'last_update': None}
        }
        
        # Statistiques globales
        self.global_stats = {
            'data_points': 0,
            'session_start': None,
            'storage_used': 0,
            'active_modules': 0
        }
        
        # Buffer des événements récents
        self.activity_log = []
        self.max_activity_log = 50
        
        logger.info("Module Dashboard initialisé")
    
    def update_module_status(self, module_name, status, data=None):
        """Met à jour le statut d'un module"""
        if module_name in self.modules_status:
            self.modules_status[module_name].update({
                'connected': status.get('connected', False),
                'active': status.get('active', False),
                'last_update': datetime.now().isoformat()
            })
            
            if data:
                self.modules_status[module_name]['data'] = data
            
            # Calculer le nombre de modules actifs
            self.global_stats['active_modules'] = sum(
                1 for m in self.modules_status.values()
                if m.get('active', False)
            )
            
            # Émettre la mise à jour via WebSocket
            self.websocket_manager.emit_to_module('dashboard', 'module_status_update', {
                'module': module_name,
                'status': self.modules_status[module_name],
                'timestamp': datetime.now().isoformat()
            })
    
    def add_activity_log(self, module, message, level='info'):
        """Ajoute un événement au log d'activité"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'module': module,
            'message': message,
            'level': level
        }
        
        self.activity_log.insert(0, event)
        
        # Limiter la taille du log
        if len(self.activity_log) > self.max_activity_log:
            self.activity_log = self.activity_log[:self.max_activity_log]
        
        # Émettre l'événement
        self.websocket_manager.emit_to_module('dashboard', 'activity_log', event)
    
    def get_dashboard_summary(self):
        """Récupère un résumé complet pour le dashboard"""
        summary = {
            'modules_status': self.modules_status,
            'global_stats': self.global_stats,
            'recent_activity': self.activity_log[:10],
            'timestamp': datetime.now().isoformat()
        }
        
        # Calculer la durée de session si active
        if self.global_stats['session_start']:
            start = datetime.fromisoformat(self.global_stats['session_start'])
            duration = datetime.now() - start
            summary['global_stats']['session_duration'] = str(duration)
        
        return summary
    
    def start_global_collection(self):
        """Démarre la collecte globale de données"""
        self.global_stats['session_start'] = datetime.now().isoformat()
        self.global_stats['data_points'] = 0
        
        self.add_activity_log('Système', 'Démarrage de la collecte globale', 'success')
        
        # Notifier tous les modules de démarrer
        self.websocket_manager.broadcast('global_collection_start', {
            'timestamp': datetime.now().isoformat()
        })
        
        return {'success': True, 'message': 'Collecte globale démarrée'}
    
    def stop_global_collection(self):
        """Arrête la collecte globale de données"""
        if self.global_stats['session_start']:
            # Calculer la durée totale
            start = datetime.fromisoformat(self.global_stats['session_start'])
            duration = datetime.now() - start
            
            self.add_activity_log(
                'Système',
                f'Arrêt de la collecte après {duration}',
                'info'
            )
        
        self.global_stats['session_start'] = None
        
        # Notifier tous les modules d'arrêter
        self.websocket_manager.broadcast('global_collection_stop', {
            'timestamp': datetime.now().isoformat()
        })
        
        return {'success': True, 'message': 'Collecte globale arrêtée'}
    
    def calculate_storage_used(self):
        """Calcule l'espace de stockage utilisé"""
        total_size = 0
        
        # Parcourir les dossiers de données
        data_dirs = [
            'recordings/neurosity',
            'recordings/thermal',
            'static/audio_recordings'
        ]
        
        for dir_path in data_dirs:
            full_path = Path(self.app.root_path) / dir_path
            if full_path.exists():
                for file in full_path.rglob('*'):
                    if file.is_file():
                        total_size += file.stat().st_size
        
        # Convertir en MB
        self.global_stats['storage_used'] = round(total_size / (1024 * 1024), 2)
        return self.global_stats['storage_used']


def init_dashboard_module(app, websocket_manager):
    """Initialise le module dashboard"""
    dashboard_module = DashboardModule(app, websocket_manager)
    
    # Enregistrer le blueprint
    app.register_blueprint(dashboard_bp)
    
    # Routes API
    @dashboard_bp.route('/summary')
    def get_dashboard_summary():
        """Récupère le résumé du dashboard"""
        return jsonify(dashboard_module.get_dashboard_summary())
    
    @dashboard_bp.route('/modules/status')
    def get_modules_status():
        """Récupère le statut de tous les modules"""
        return jsonify({
            'modules': dashboard_module.modules_status,
            'timestamp': datetime.now().isoformat()
        })
    
    @dashboard_bp.route('/start-collection', methods=['POST'])
    def start_collection():
        """Démarre la collecte globale"""
        result = dashboard_module.start_global_collection()
        return jsonify(result)
    
    @dashboard_bp.route('/stop-collection', methods=['POST'])
    def stop_collection():
        """Arrête la collecte globale"""
        result = dashboard_module.stop_global_collection()
        return jsonify(result)
    
    @dashboard_bp.route('/storage')
    def get_storage_info():
        """Récupère les informations de stockage"""
        storage_mb = dashboard_module.calculate_storage_used()
        return jsonify({
            'storage_used_mb': storage_mb,
            'storage_used_formatted': f"{storage_mb} MB",
            'timestamp': datetime.now().isoformat()
        })
    
    @dashboard_bp.route('/activity-log')
    def get_activity_log():
        """Récupère le log d'activité"""
        return jsonify({
            'events': dashboard_module.activity_log[:20],
            'total_events': len(dashboard_module.activity_log),
            'timestamp': datetime.now().isoformat()
        })
    
    return dashboard_module


def register_dashboard_websocket_events(websocket_manager, dashboard_module):
    """Enregistre les événements WebSocket pour le dashboard"""
    
    def handle_request_summary(data):
        """Envoie le résumé du dashboard"""
        summary = dashboard_module.get_dashboard_summary()
        websocket_manager.emit_to_current_client('dashboard_summary', summary)
    
    def handle_module_status_request(data):
        """Envoie le statut d'un module spécifique"""
        module_name = data.get('module')
        if module_name in dashboard_module.modules_status:
            websocket_manager.emit_to_current_client('module_status', {
                'module': module_name,
                'status': dashboard_module.modules_status[module_name]
            })
    
    def handle_start_global_collection(data):
        """Démarre la collecte globale via WebSocket"""
        result = dashboard_module.start_global_collection()
        websocket_manager.emit_to_current_client('collection_started', result)
    
    def handle_stop_global_collection(data):
        """Arrête la collecte globale via WebSocket"""
        result = dashboard_module.stop_global_collection()
        websocket_manager.emit_to_current_client('collection_stopped', result)
    
    # Écouter les mises à jour des autres modules
    def handle_module_update(data):
        """Reçoit les mises à jour d'état des autres modules"""
        module_name = data.get('module')
        status = data.get('status', {})
        module_data = data.get('data')
        
        if module_name:
            dashboard_module.update_module_status(module_name, status, module_data)
            dashboard_module.add_activity_log(
                module_name,
                f"État mis à jour: {status.get('connected', False) and 'Connecté' or 'Déconnecté'}"
            )
    
    # Enregistrer les événements
    dashboard_events = {
        'request_summary': handle_request_summary,
        'request_module_status': handle_module_status_request,
        'start_global_collection': handle_start_global_collection,
        'stop_global_collection': handle_stop_global_collection,
        'module_update': handle_module_update
    }
    
    websocket_manager.register_module_events('dashboard', dashboard_events)
    logger.info("Événements WebSocket du dashboard enregistrés")