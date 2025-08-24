#!/usr/bin/env python3
"""
BioMedical Hub - Application Flask Refactorisée
Application Flask simplifiée utilisant le gestionnaire WebSocket modulaire
Version corrigée pour multiprocessing sur Windows
"""
import asyncio
import multiprocessing as mp
from flask import Flask, render_template, jsonify, request
from datetime import datetime
import logging
import os
import webbrowser
import threading
import time
import platform
import subprocess
import signal

# Configuration multiprocessing pour Windows - DOIT être au tout début
if __name__ == '__main__':
    mp.set_start_method('spawn', force=True)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import du gestionnaire WebSocket et du registre des modules
from websocket_manager import websocket_manager
from module_registry import ModuleRegistry

# Initialisation de l'application Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'biomedical-hub-secret-key-2025')
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'

# Variables globales pour les modules
thought_capture_module = None
thermal_module = None
polar_module = None
neurosity_module = None
gazepoint_module = None
dashboard_home_module = None  # AJOUT: Variable pour dashboard
module_registry = None


def init_modules():
    """Initialise tous les modules - appelé seulement dans le main"""
    global thought_capture_module, thermal_module, polar_module, neurosity_module, gazepoint_module, dashboard_home_module, module_registry
    
    # Initialisation du gestionnaire WebSocket
    websocket_manager.init_app(app)
    
    # Initialisation du registre des modules
    module_registry = ModuleRegistry()
    
    # Import et initialisation des modules

    from modules.thought_capture.thought_capture import (
        init_module as init_thought_capture,
        register_websocket_events as register_thought_capture_events
    )
    from modules.thermal_camera.thermal_camera import (
        init_thermal_module,
        register_thermal_websocket_events
    )
    from modules.neurosity.neurosity import (
        init_neurosity_module,
        register_neurosity_websocket_events
    )
    from modules.polar.polar import (
        init_polar_module,
        register_polar_websocket_events
    )
    from modules.gazepoint.gazepoint import (
        init_gazepoint_module,
        register_gazepoint_websocket_events,
        register_gazepoint_routes
    )
    # AJOUT: Import du module dashboard
    from modules.dashboard.dashboard_home import (
        init_dashboard_home_module,
        register_dashboard_home_websocket_events
    )
    
    # Initialisation du module Thought Capture
    thought_capture_module = init_thought_capture(app)
    logger.info("Module Thought Capture initialisé")
    
    # Initialisation du module Caméra Thermique
    thermal_module = init_thermal_module(app, websocket_manager)
    logger.info("Module Caméra Thermique initialisé")
    
    # Initialisation du module Polar
    polar_module = init_polar_module(app, websocket_manager)
    logger.info("Module Polar initialisé")
    
    # Initialisation du module Neurosity
    neurosity_module = init_neurosity_module(app, websocket_manager)
    if neurosity_module:
        logger.info("Module Neurosity initialisé")
    else:
        logger.warning("Module Neurosity non initialisé - vérifiez la configuration .env")
    
    # Initialisation du module Gazepoint
    try:
        gazepoint_module = init_gazepoint_module(app, websocket_manager)
        if gazepoint_module:
            logger.info("Module Gazepoint initialisé")
            # Enregistrer les routes Flask pour Gazepoint
            register_gazepoint_routes(app)
        else:
            logger.warning("Module Gazepoint non initialisé")
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation du module Gazepoint: {e}")
        gazepoint_module = None
    
    # AJOUT: Initialisation du module Dashboard Home
    dashboard_home_module = init_dashboard_home_module(app, websocket_manager)
    
    # MODIFICATION: Passer les références de TOUS les modules au dashboard, incluant thought_capture
    dashboard_home_module.set_module_references(
        polar_module=polar_module,
        neurosity_module=neurosity_module,
        thermal_module=thermal_module,
        gazepoint_module=gazepoint_module,
        thought_capture_module=thought_capture_module  # AJOUT: Référence au module thought_capture
    )
    
    logger.info("Module Dashboard Home initialisé avec références")
    
    # Enregistrer les événements WebSocket des modules
    register_module_websocket_events()


# ========================
# FONCTION POUR TUER LE PORT
# ========================

def kill_port(port):
    """Tuer le processus qui utilise le port spécifié"""
    system = platform.system()
    logger.info(f"Tentative de libération du port {port} sur {system}...")
    
    try:
        if system == "Windows":
            # Pour Windows
            cmd = f"netstat -ano | findstr :{port}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.stdout:
                lines = result.stdout.strip().split('\n')
                pids = set()
                
                for line in lines:
                    parts = line.split()
                    if len(parts) > 4:
                        pid = parts[-1]
                        if pid.isdigit():
                            pids.add(pid)
                
                for pid in pids:
                    try:
                        kill_cmd = f"taskkill /F /PID {pid}"
                        subprocess.run(kill_cmd, shell=True, capture_output=True)
                        logger.info(f"Processus PID {pid} tué sur le port {port}")
                    except Exception as e:
                        logger.warning(f"Impossible de tuer le processus PID {pid}: {e}")
                
                if pids:
                    time.sleep(1)
                    logger.info(f"Port {port} libéré avec succès")
                else:
                    logger.info(f"Aucun processus trouvé sur le port {port}")
            else:
                logger.info(f"Le port {port} est déjà libre")
        
        else:  # Linux ou macOS
            try:
                cmd = f"lsof -ti:{port}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                if result.stdout:
                    pids = result.stdout.strip().split('\n')
                    
                    for pid in pids:
                        if pid and pid.isdigit():
                            try:
                                os.kill(int(pid), signal.SIGKILL)
                                logger.info(f"Processus PID {pid} tué sur le port {port}")
                            except ProcessLookupError:
                                logger.warning(f"Le processus PID {pid} n'existe plus")
                            except PermissionError:
                                logger.warning(f"Permission refusée pour tuer le processus PID {pid}")
                                try:
                                    subprocess.run(f"sudo kill -9 {pid}", shell=True)
                                    logger.info(f"Processus PID {pid} tué avec sudo")
                                except:
                                    pass
                    
                    time.sleep(1)
                    logger.info(f"Port {port} libéré avec succès")
                else:
                    logger.info(f"Le port {port} est déjà libre")
            
            except FileNotFoundError:
                logger.warning("lsof non trouvé. Essai avec netstat...")
                try:
                    cmd = f"netstat -tlnp 2>/dev/null | grep :{port}"
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    
                    if result.stdout:
                        logger.warning(
                            f"Un processus utilise le port {port} mais impossible de le tuer automatiquement")
                        logger.warning("Essayez de tuer le processus manuellement ou utilisez sudo")
                except:
                    pass
    
    except Exception as e:
        logger.error(f"Erreur lors de la tentative de libération du port {port}: {e}")
        logger.info("Tentative de démarrage du serveur malgré l'erreur...")


# ========================
# FONCTION POUR OUVRIR LE NAVIGATEUR
# ========================

def open_browser(port):
    """Ouvrir le navigateur après un court délai"""
    
    def _open():
        time.sleep(1.5)
        url = f'http://localhost:{port}/#home'
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
    if module_registry:
        return render_template('base.html', modules=module_registry.get_all_modules())
    else:
        return render_template('base.html', modules={})


@app.route('/health')
def health_check():
    """Endpoint de vérification de santé"""
    modules_count = module_registry.get_modules_count() if module_registry else 0
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '1.0.0',
        'modules_available': modules_count,
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
    if not module_registry:
        return jsonify({'error': 'Module registry not initialized'}), 503
    
    return jsonify({
        'modules': module_registry.get_all_modules(),
        'total': module_registry.get_modules_count(),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/modules/<module_name>')
def get_module_info(module_name):
    """Récupérer les informations d'un module spécifique"""
    if not module_registry:
        return jsonify({'error': 'Module registry not initialized'}), 503
    
    module_data = module_registry.get_module(module_name)
    
    if not module_data:
        return jsonify({'error': f'Module "{module_name}" not found'}), 404
    
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
    if not module_registry:
        return jsonify({'error': 'Module registry not initialized'}), 503
    
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
    if not module_registry:
        return jsonify({'error': 'Module registry not initialized'}), 503
    
    if not module_registry.module_exists(module_name):
        return jsonify({'error': f'Module "{module_name}" not found'}), 404
    
    success = module_registry.activate_module(module_name)
    
    if success:
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
    if not module_registry:
        return jsonify({'error': 'Module registry not initialized'}), 503
    
    if not module_registry.module_exists(module_name):
        return jsonify({'error': f'Module "{module_name}" not found'}), 404
    
    success = module_registry.deactivate_module(module_name)
    
    if success:
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
            'client_id': client_id[:8] + '...',
            'connected_at': info.get('connected_at'),
            'subscriptions': info.get('subscriptions', []),
            'ip': info.get('ip', 'Unknown')[:10] + '...'
        })
    
    return jsonify({
        'clients': clients_info,
        'total': len(clients_info),
        'timestamp': datetime.now().isoformat()
    })


# ========================
# HANDLERS D'ÉVÉNEMENTS WEBSOCKET HOME & DEVICES
# ========================

def handle_get_devices_status(data):
    """Gère la demande de statut des appareils"""
    status = {
        'polar': {
            'connected': False,
            'devices': []
        },
        'neurosity': {
            'connected': False
        },
        'thermal': {
            'connected': False
        },
        'gazepoint': {
            'connected': False
        },
        'thought_capture': {  # AJOUT: Statut du module thought_capture
            'ready': True,
            'recording': False
        },
        'timestamp': datetime.now().isoformat()
    }
    
    # Vérifier le statut Polar
    if polar_module:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            polar_status = loop.run_until_complete(polar_module.get_devices_status())
            
            # Vérifier que polar_status n'est pas None
            if polar_status:
                if polar_status.get('h10', {}).get('connected'):
                    status['polar']['connected'] = True
                    status['polar']['devices'].append('h10')
                
                if polar_status.get('verity', {}).get('connected'):
                    status['polar']['connected'] = True
                    status['polar']['devices'].append('verity')
        except Exception as e:
            logger.error(f"Erreur récupération statut Polar: {e}")
    
    # Vérifier le statut Neurosity
    if neurosity_module and hasattr(neurosity_module, 'crown') and neurosity_module.crown:
        status['neurosity']['connected'] = True
    
    # Vérifier le statut Gazepoint
    if gazepoint_module and hasattr(gazepoint_module, 'is_connected') and gazepoint_module.is_connected:
        status['gazepoint']['connected'] = True
    
    # Vérifier le statut Thought Capture
    if thought_capture_module:
        status['thought_capture']['ready'] = True
        # Si on avait accès à l'état d'enregistrement, on le mettrait ici
    
    websocket_manager.emit_to_current_client('devices_status', status)


def handle_dashboard_home_request(data):
    """Gère les requêtes du dashboard home"""
    if dashboard_home_module:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        status = loop.run_until_complete(dashboard_home_module.get_aggregated_data())
        websocket_manager.emit_to_current_client('dashboard_data', status)


def handle_dashboard_home_status(data):
    """Envoie le statut du dashboard home"""
    if dashboard_home_module:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        status = loop.run_until_complete(dashboard_home_module.get_aggregated_data())
        websocket_manager.emit_to_current_client('dashboard_status', status)


def handle_start_collection(data):
    """Démarre la collecte globale via dashboard"""
    if dashboard_home_module:
        result = dashboard_home_module.start_collection()
        websocket_manager.emit_to_current_client('collection_started', result)


def handle_stop_collection(data):
    """Arrête la collecte globale via dashboard"""
    if dashboard_home_module:
        result = dashboard_home_module.stop_collection()
        websocket_manager.emit_to_current_client('collection_stopped', result)


def handle_dashboard_data_request(data):
    """Gérer une demande de données du dashboard (fallback)"""
    if dashboard_home_module:
        handle_dashboard_home_request(data)
    else:
        # Fallback vers l'ancien système
        modules = module_registry.get_all_modules() if module_registry else {}
        websocket_manager.emit_to_current_client('dashboard_data', {
            'modules': modules,
            'websocket_status': {
                'connected_clients': websocket_manager.get_connected_clients_count(),
                'active_modules': websocket_manager.get_active_modules_count()
            },
            'timestamp': datetime.now().isoformat()
        })


def handle_dashboard_config_update(data):
    """Gérer une mise à jour de configuration du dashboard"""
    logger.info(f"Configuration dashboard mise à jour: {data}")
    websocket_manager.emit_to_current_client('config_updated', {
        'success': True,
        'timestamp': datetime.now().isoformat()
    })


# ========================
# ENREGISTREMENT DES ÉVÉNEMENTS WEBSOCKET DES MODULES
# ========================

def register_module_websocket_events():
    """Enregistrer les événements WebSocket spécifiques aux modules"""
    from modules.polar.polar import register_polar_websocket_events
    from modules.thermal_camera.thermal_camera import register_thermal_websocket_events
    from modules.neurosity.neurosity import register_neurosity_websocket_events
    from modules.thought_capture.thought_capture import register_websocket_events as register_thought_capture_events
    from modules.gazepoint.gazepoint import register_gazepoint_websocket_events
    
    # MODIFICATION: Événements pour le dashboard principal pointent vers dashboard
    dashboard_events = {
        'request_dashboard_data': handle_dashboard_home_request,
        'get_dashboard_status': handle_dashboard_home_status,
        'start_collection': handle_start_collection,
        'stop_collection': handle_stop_collection,
        'update_dashboard_config': handle_dashboard_config_update,
        'get_devices_status': handle_get_devices_status  # NOUVEAU
    }
    websocket_manager.register_module_events('dashboard', dashboard_events)
    
    # Événements pour le module Polar
    if polar_module:
        register_polar_websocket_events(websocket_manager, polar_module)
    
    # Enregistrer les événements du module thermique
    if thermal_module:
        register_thermal_websocket_events(websocket_manager, thermal_module)
    
    # Enregistrer les événements du module Neurosity
    if neurosity_module:
        register_neurosity_websocket_events(websocket_manager, neurosity_module)
    
    # Enregistrer les événements du module Gazepoint
    if gazepoint_module:
        register_gazepoint_websocket_events(websocket_manager, gazepoint_module)
        logger.info("Événements WebSocket Gazepoint enregistrés avec succès")
    else:
        logger.warning("Module Gazepoint non disponible pour l'enregistrement des événements")
    
    # Enregistrer les événements du module Capture de la Pensée
    register_thought_capture_events(websocket_manager)
    
    # AJOUT: Enregistrer les événements du module Dashboard Home
    if dashboard_home_module:
        from modules.dashboard.dashboard_home import register_dashboard_home_websocket_events
        register_dashboard_home_websocket_events(
            websocket_manager,
            dashboard_home_module,
            polar_module=polar_module,
            thought_capture_module=thought_capture_module  # AJOUT: Passer la référence thought_capture
        )
        logger.info("Événements WebSocket Dashboard Home enregistrés")


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
# CLEANUP DES MODULES
# ========================

def cleanup_modules():
    """Nettoyer tous les modules avant l'arrêt"""
    logger.info("Nettoyage des modules...")
    
    # AJOUT: Nettoyer le module Dashboard Home
    if dashboard_home_module:
        try:
            if dashboard_home_module.collection_state['is_collecting']:
                dashboard_home_module.stop_collection()
            logger.info("Module Dashboard Home nettoyé")
        except Exception as e:
            logger.error(f"Erreur nettoyage module Dashboard Home: {e}")
    
    # Nettoyer le module Neurosity
    if neurosity_module:
        try:
            neurosity_module.cleanup()
            logger.info("Module Neurosity nettoyé")
        except Exception as e:
            logger.error(f"Erreur nettoyage module Neurosity: {e}")
    
    # Nettoyer le module Polar
    if polar_module:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(polar_module.cleanup())
            logger.info("Module Polar nettoyé")
        except Exception as e:
            logger.error(f"Erreur nettoyage module Polar: {e}")
    
    # Nettoyer le module Gazepoint
    if gazepoint_module:
        try:
            gazepoint_module.cleanup()
            logger.info("Module Gazepoint nettoyé")
        except Exception as e:
            logger.error(f"Erreur nettoyage module Gazepoint: {e}")
    
    # Nettoyer le module Thermal
    if thermal_module:
        try:
            thermal_module.stop_capture()
            logger.info("Module Thermal nettoyé")
        except Exception as e:
            logger.error(f"Erreur nettoyage module Thermal: {e}")
    
    # Nettoyer le module Thought Capture
    if thought_capture_module:
        try:
            # Si le module a une méthode cleanup, l'appeler
            if hasattr(thought_capture_module, 'cleanup'):
                thought_capture_module.cleanup()
            logger.info("Module Thought Capture nettoyé")
        except Exception as e:
            logger.error(f"Erreur nettoyage module Thought Capture: {e}")
    
    logger.info("Nettoyage terminé")


# ========================
# POINT D'ENTRÉE PRINCIPAL
# ========================

if __name__ == '__main__':
    # Configuration du serveur
    host = 'localhost'
    port = int(os.environ.get('PORT', 3333))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # LIBÉRER LE PORT AVANT DE DÉMARRER
    kill_port(port)
    
    # Désactiver les logs Werkzeug en production
    if not debug:
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
    
    logger.info("=" * 60)
    logger.info("DÉMARRAGE DU BIOMEDICAL HUB")
    logger.info("=" * 60)
    logger.info(f"Serveur: http://localhost:{port}")
    logger.info(f"Mode debug: {debug}")
    logger.info("=" * 60)
    
    # Initialiser les modules SEULEMENT dans le processus principal
    init_modules()
    
    # Ouvrir automatiquement le navigateur
    if not os.environ.get('NO_BROWSER', False):
        if not debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            open_browser(port)
    
    try:
        # Démarrage du serveur
        websocket_manager.socketio.run(
            app,
            host=host,
            port=port,
            debug=debug,
            allow_unsafe_werkzeug=True,
            use_reloader=debug
        )
    except KeyboardInterrupt:
        logger.info("\nArrêt demandé par l'utilisateur...")
        cleanup_modules()
    except Exception as e:
        logger.error(f"Erreur lors du démarrage: {e}")
        cleanup_modules()
        raise
    finally:
        logger.info("Application fermée")