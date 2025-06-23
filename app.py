#!/usr/bin/env python3
"""
BioMedical Hub - Application Flask Refactorisée
Application Flask simplifiée utilisant le gestionnaire WebSocket modulaire
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime
import logging
import os
import webbrowser
import threading
import time

# Import du gestionnaire WebSocket
from websocket_manager import websocket_manager
from module_registry import ModuleRegistry
from modules.thought.thought_capture import init_module as init_thought_capture
from modules.thought.thought_capture import register_websocket_events as register_thought_capture_events

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialisation de l'application
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'biomedical-hub-secret-key-2025')
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
init_thought_capture(app)
logger.info("Module Thought Capture initialisé")

# Initialisation du gestionnaire WebSocket
websocket_manager.init_app(app)

# Initialisation du registre des modules
module_registry = ModuleRegistry()


# ========================
# FONCTION POUR OUVRIR LE NAVIGATEUR
# ========================

def open_browser(port):
    """Ouvrir le navigateur après un court délai"""
    
    def _open():
        time.sleep(1.5)  # Attendre que le serveur démarre
        url = f'http://localhost:{port}'
        logger.info(f"Ouverture du navigateur: {url}")
        webbrowser.open(url)
    
    thread = threading.Thread(target=_open)
    thread.daemon = True
    thread.start()


# ========================
# ROUTES PRINCIPALES
# ========================

@app.route('/')
def index():
    """Page principale du dashboard"""
    return render_template('base.html', modules=module_registry.get_all_modules())


@app.route('/health')
def health_check():
    """Endpoint de vérification de santé"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0',
        'modules_available': module_registry.get_modules_count(),
        'websocket': {
            'connected_clients': websocket_manager.get_connected_clients_count(),
            'active_modules': websocket_manager.get_active_modules_count()
        }
    })


# ========================
# API ENDPOINTS - MODULES
# ========================

@app.route('/api/modules')
def get_modules():
    """Récupérer la liste de tous les modules"""
    return jsonify({
        'modules': module_registry.get_all_modules(),
        'total': module_registry.get_modules_count(),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/modules/<module_name>')
def get_module_info(module_name):
    """Récupérer les informations d'un module spécifique"""
    module_data = module_registry.get_module(module_name)
    
    if not module_data:
        return jsonify({'error': f'Module "{module_name}" not found'}), 404
    
    # Ajouter les informations WebSocket
    module_data = module_data.copy()
    module_data['websocket'] = {
        'connected_clients': len(websocket_manager.get_module_clients(module_name)),
        'is_active': len(websocket_manager.get_module_clients(module_name)) > 0
    }
    module_data['timestamp'] = datetime.now().isoformat()
    
    return jsonify({
        'module': module_name,
        'data': module_data
    })


@app.route('/api/modules/<module_name>/status')
def get_module_status(module_name):
    """Récupérer le statut d'un module"""
    if not module_registry.module_exists(module_name):
        return jsonify({'error': f'Module "{module_name}" not found'}), 404
    
    module_data = module_registry.get_module(module_name)
    connected_clients = websocket_manager.get_module_clients(module_name)
    
    return jsonify({
        'module': module_name,
        'status': module_data.get('status', 'unknown'),
        'enabled': module_data.get('enabled', False),
        'websocket': {
            'connected_clients': len(connected_clients),
            'client_ids': connected_clients,
            'is_active': len(connected_clients) > 0
        },
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/modules/<module_name>/activate', methods=['POST'])
def activate_module(module_name):
    """Activer un module"""
    if not module_registry.module_exists(module_name):
        return jsonify({'error': f'Module "{module_name}" not found'}), 404
    
    # Activer le module dans le registre
    success = module_registry.activate_module(module_name)
    
    if success:
        # Notifier via WebSocket
        websocket_manager.broadcast('module_activated', {
            'module': module_name,
            'timestamp': datetime.now().isoformat()
        })
        
        logger.info(f"Module {module_name} activé")
        
        return jsonify({
            'success': True,
            'module': module_name,
            'status': 'activated',
            'timestamp': datetime.now().isoformat()
        })
    else:
        return jsonify({'error': f'Failed to activate module "{module_name}"'}), 500


@app.route('/api/modules/<module_name>/deactivate', methods=['POST'])
def deactivate_module(module_name):
    """Désactiver un module"""
    if not module_registry.module_exists(module_name):
        return jsonify({'error': f'Module "{module_name}" not found'}), 404
    
    # Désactiver le module dans le registre
    success = module_registry.deactivate_module(module_name)
    
    if success:
        # Notifier via WebSocket
        websocket_manager.broadcast('module_deactivated', {
            'module': module_name,
            'timestamp': datetime.now().isoformat()
        })
        
        logger.info(f"Module {module_name} désactivé")
        
        return jsonify({
            'success': True,
            'module': module_name,
            'status': 'deactivated',
            'timestamp': datetime.now().isoformat()
        })
    else:
        return jsonify({'error': f'Failed to deactivate module "{module_name}"'}), 500


# ========================
# API ENDPOINTS - WEBSOCKET
# ========================

@app.route('/api/websocket/status')
def get_websocket_status():
    """Récupérer le statut des WebSockets"""
    return jsonify({
        'connected_clients': websocket_manager.get_connected_clients_count(),
        'active_modules': websocket_manager.get_active_modules_count(),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/websocket/clients')
def get_websocket_clients():
    """Récupérer la liste des clients connectés (informations limitées)"""
    clients_info = []
    
    for client_id, info in websocket_manager.connected_clients.items():
        clients_info.append({
            'client_id': client_id[:8] + '...',  # ID tronqué pour la sécurité
            'connected_at': info.get('connected_at'),
            'subscriptions': info.get('subscriptions', []),
            'ip': info.get('ip', 'Unknown')[:10] + '...'  # IP tronquée
        })
    
    return jsonify({
        'clients': clients_info,
        'total': len(clients_info),
        'timestamp': datetime.now().isoformat()
    })


# ========================
# ENREGISTREMENT DES ÉVÉNEMENTS WEBSOCKET DES MODULES
# ========================

def register_module_websocket_events():
    """Enregistrer les événements WebSocket spécifiques aux modules"""
    
    # Événements pour le module Dashboard
    dashboard_events = {
        'request_dashboard_data': handle_dashboard_data_request,
        'update_dashboard_config': handle_dashboard_config_update
    }
    websocket_manager.register_module_events('dashboard', dashboard_events)
    
    # Événements pour le module Polar
    polar_events = {
        'start_monitoring': handle_polar_start_monitoring,
        'stop_monitoring': handle_polar_stop_monitoring,
        'get_hrv_data': handle_polar_hrv_request
    }
    websocket_manager.register_module_events('polar', polar_events)
    
    # Événements pour le module EEG
    eeg_events = {
        'start_recording': handle_eeg_start_recording,
        'stop_recording': handle_eeg_stop_recording,
        'get_brain_waves': handle_eeg_brain_waves_request
    }
    websocket_manager.register_module_events('eeg_crown', eeg_events)
    
    # Événements pour le module Caméra Thermique
    thermal_events = {
        'start_capture': handle_thermal_start_capture,
        'stop_capture': handle_thermal_stop_capture,
        'get_temperature_map': handle_thermal_temperature_request
    }
    websocket_manager.register_module_events('thermal_camera', thermal_events)
    
    # Événements pour le module Gazepoint
    gazepoint_events = {
        'start_tracking': handle_gazepoint_start_tracking,
        'stop_tracking': handle_gazepoint_stop_tracking,
        'get_gaze_data': handle_gazepoint_data_request
    }
    websocket_manager.register_module_events('gazepoint', gazepoint_events)
    
    # Événements pour le module Capture de la Pensée
    thought_events = {
        'start_thought_capture': handle_thought_start_capture,
        'stop_thought_capture': handle_thought_stop_capture,
        'decode_intention': handle_thought_decode_intention
    }
    websocket_manager.register_module_events('thought_capture', thought_events)


register_thought_capture_events(websocket_manager)


# ========================
# HANDLERS D'ÉVÉNEMENTS WEBSOCKET
# ========================

def handle_dashboard_data_request(data):
    """Gérer une demande de données du dashboard"""
    websocket_manager.emit_to_current_client('dashboard_data', {
        'modules': module_registry.get_all_modules(),
        'websocket_status': {
            'connected_clients': websocket_manager.get_connected_clients_count(),
            'active_modules': websocket_manager.get_active_modules_count()
        },
        'timestamp': datetime.now().isoformat()
    })


def handle_dashboard_config_update(data):
    """Gérer une mise à jour de configuration du dashboard"""
    # Traitement de la mise à jour de configuration
    logger.info(f"Configuration dashboard mise à jour: {data}")
    websocket_manager.emit_to_current_client('config_updated', {
        'success': True,
        'timestamp': datetime.now().isoformat()
    })


def handle_polar_start_monitoring(data):
    """Démarrer le monitoring Polar"""
    logger.info("Démarrage du monitoring Polar")
    websocket_manager.emit_to_module('polar', 'monitoring_started', {
        'status': 'active',
        'timestamp': datetime.now().isoformat()
    })


def handle_polar_stop_monitoring(data):
    """Arrêter le monitoring Polar"""
    logger.info("Arrêt du monitoring Polar")
    websocket_manager.emit_to_module('polar', 'monitoring_stopped', {
        'status': 'inactive',
        'timestamp': datetime.now().isoformat()
    })


def handle_polar_hrv_request(data):
    """Gérer une demande de données HRV"""
    # Simuler des données HRV (à remplacer par de vraies données)
    fake_hrv_data = {
        'hrv_score': 45.2,
        'rmssd': 38.7,
        'heart_rate': 72,
        'timestamp': datetime.now().isoformat()
    }
    websocket_manager.emit_to_current_client('polar_hrv_data', fake_hrv_data)


def handle_eeg_start_recording(data):
    """Démarrer l'enregistrement EEG"""
    logger.info("Démarrage de l'enregistrement EEG")
    websocket_manager.emit_to_module('eeg_crown', 'recording_started', {
        'status': 'recording',
        'timestamp': datetime.now().isoformat()
    })


def handle_eeg_stop_recording(data):
    """Arrêter l'enregistrement EEG"""
    logger.info("Arrêt de l'enregistrement EEG")
    websocket_manager.emit_to_module('eeg_crown', 'recording_stopped', {
        'status': 'idle',
        'timestamp': datetime.now().isoformat()
    })


def handle_eeg_brain_waves_request(data):
    """Gérer une demande de données d'ondes cérébrales"""
    # Simuler des données d'ondes cérébrales
    fake_brain_waves = {
        'alpha': 12.5,
        'beta': 8.3,
        'theta': 6.1,
        'delta': 2.8,
        'focus_level': 0.75,
        'timestamp': datetime.now().isoformat()
    }
    websocket_manager.emit_to_current_client('eeg_brain_waves', fake_brain_waves)


def handle_thermal_start_capture(data):
    """Démarrer la capture thermique"""
    logger.info("Démarrage de la capture thermique")
    websocket_manager.emit_to_module('thermal_camera', 'capture_started', {
        'status': 'capturing',
        'timestamp': datetime.now().isoformat()
    })


def handle_thermal_stop_capture(data):
    """Arrêter la capture thermique"""
    logger.info("Arrêt de la capture thermique")
    websocket_manager.emit_to_module('thermal_camera', 'capture_stopped', {
        'status': 'idle',
        'timestamp': datetime.now().isoformat()
    })


def handle_thermal_temperature_request(data):
    """Gérer une demande de carte de température"""
    # Simuler des données de température
    fake_thermal_data = {
        'average_temp': 36.7,
        'max_temp': 37.2,
        'min_temp': 35.8,
        'thermal_map': 'base64_image_data_here',
        'timestamp': datetime.now().isoformat()
    }
    websocket_manager.emit_to_current_client('thermal_temperature_data', fake_thermal_data)


def handle_gazepoint_start_tracking(data):
    """Démarrer le tracking oculaire"""
    logger.info("Démarrage du tracking oculaire")
    websocket_manager.emit_to_module('gazepoint', 'tracking_started', {
        'status': 'tracking',
        'timestamp': datetime.now().isoformat()
    })


def handle_gazepoint_stop_tracking(data):
    """Arrêter le tracking oculaire"""
    logger.info("Arrêt du tracking oculaire")
    websocket_manager.emit_to_module('gazepoint', 'tracking_stopped', {
        'status': 'idle',
        'timestamp': datetime.now().isoformat()
    })


def handle_gazepoint_data_request(data):
    """Gérer une demande de données de regard"""
    # Simuler des données de regard
    fake_gaze_data = {
        'gaze_x': 1024,
        'gaze_y': 768,
        'pupil_diameter': 4.2,
        'fixation_duration': 250,
        'timestamp': datetime.now().isoformat()
    }
    websocket_manager.emit_to_current_client('gazepoint_gaze_data', fake_gaze_data)


def handle_thought_start_capture(data):
    """Démarrer la capture de pensée"""
    logger.info("Démarrage de la capture de pensée")
    websocket_manager.emit_to_module('thought_capture', 'capture_started', {
        'status': 'capturing',
        'timestamp': datetime.now().isoformat()
    })


def handle_thought_stop_capture(data):
    """Arrêter la capture de pensée"""
    logger.info("Arrêt de la capture de pensée")
    websocket_manager.emit_to_module('thought_capture', 'capture_stopped', {
        'status': 'idle',
        'timestamp': datetime.now().isoformat()
    })


def handle_thought_decode_intention(data):
    """Décoder une intention mentale"""
    # Simuler le décodage d'intention
    fake_intention_data = {
        'intention': 'move_cursor_right',
        'confidence': 0.87,
        'brain_signal_strength': 0.92,
        'timestamp': datetime.now().isoformat()
    }
    websocket_manager.emit_to_current_client('thought_intention_decoded', fake_intention_data)


# ========================
# GESTION D'ERREURS
# ========================

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Page not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Erreur interne du serveur: {error}")
    return jsonify({'error': 'Internal server error'}), 500


# ========================
# INITIALISATION
# ========================

# Enregistrer les événements WebSocket des modules
register_module_websocket_events()

# ========================
# POINT D'ENTRÉE
# ========================

if __name__ == '__main__':
    # Configuration du serveur - FORCER LOCALHOST
    host = 'localhost'  # Forcé à localhost au lieu de 0.0.0.0
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # Désactiver les logs Werkzeug en production
    if not debug:
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
    
    logger.info("=" * 60)
    logger.info("DÉMARRAGE DU BIOMEDICAL HUB DASHBOARD")
    logger.info("=" * 60)
    logger.info(f"Serveur: http://localhost:{port}")
    logger.info(f"Mode debug: {debug}")
    logger.info(f"Modules disponibles: {module_registry.get_modules_count()}")
    logger.info(f"🔌 WebSocket: Activé")
    logger.info("=" * 60)
    
    # Ouvrir automatiquement le navigateur
    if not os.environ.get('NO_BROWSER', False):
        # Vérifier si on est dans le processus principal (pas le reloader)
        if not debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            open_browser(port)
    
    # Démarrage du serveur
    websocket_manager.socketio.run(
        app,
        host=host,
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True,
        use_reloader=debug  # Reloader seulement en mode debug
    )