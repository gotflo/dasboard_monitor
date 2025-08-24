#!/usr/bin/env python3
"""
Module Neurosity - Backend intégré au dashboard
Gestion du casque Neurosity Crown
Version finale corrigée et optimisée
"""

import os
import time
import threading
import multiprocessing as mp
from pathlib import Path
from datetime import datetime
from queue import Empty
import logging
from dotenv import load_dotenv

# Import du data manager local
from .data_manager import DataManager

# Configuration du logger
logger = logging.getLogger(__name__)

# Charger le .env depuis la racine du projet (une seule fois)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # Remonter à la racine
ENV_PATH = PROJECT_ROOT / '.env'

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
    logger.info(f"Fichier .env chargé depuis: {ENV_PATH}")
else:
    logger.warning(f"Fichier .env non trouvé à: {ENV_PATH}")
    # Essayer la méthode par défaut
    load_dotenv()

# Configuration du multiprocessing pour Windows (une seule fois au niveau module)
if os.name == 'nt' and mp.get_start_method(allow_none=True) != 'spawn':
    try:
        mp.set_start_method('spawn', force=True)
        logger.info("Multiprocessing configuré en mode 'spawn' pour Windows")
    except RuntimeError:
        # Déjà configuré
        pass


class NeurosityModule:
    """Module de gestion du casque Neurosity Crown"""
    
    def __init__(self, app, websocket_manager):
        self.app = app
        self.websocket_manager = websocket_manager
        
        # État du module
        self.is_connected = False
        self.is_monitoring = False
        self.is_recording = False
        self.device_status = {
            'online': False,
            'battery': 0,
            'charging': False,
            'signal': 'disconnected'
        }
        
        # Gestionnaire de données
        self.data_manager = DataManager(data_directory='recordings/neurosity')
        
        # Processus et queues
        self.command_queue = None
        self.data_queue = None
        self.response_queue = None
        self.neurosity_process = None
        self.data_thread = None
        self.running = False
        
        # Vérifier les variables d'environnement
        self._check_env_variables()
        
        # Démarrer le module
        self._start_module()
        
        # Enregistrer les routes API
        self._register_routes()
        
        logger.info("Module Neurosity initialisé")
    
    def _check_env_variables(self):
        """Vérifie que les variables d'environnement nécessaires sont présentes"""
        required_vars = ['NEUROSITY_EMAIL', 'NEUROSITY_PASSWORD', 'NEUROSITY_DEVICE_ID']
        missing_vars = []
        
        for var in required_vars:
            value = os.getenv(var)
            if not value:
                missing_vars.append(var)
            else:
                # Log avec masquage des valeurs sensibles
                if var == 'NEUROSITY_EMAIL':
                    masked = value.split('@')[0][:3] + '***@' + value.split('@')[1] if '@' in value else '***'
                elif var == 'NEUROSITY_PASSWORD':
                    masked = '***'
                else:
                    masked = value[:8] + '...' if len(value) > 8 else value
                logger.debug(f"{var}: {masked}")
        
        if missing_vars:
            raise ValueError(f"Variables d'environnement manquantes: {', '.join(missing_vars)}")
    
    def _start_module(self):
        """Démarre le module et ses composants"""
        try:
            # Créer les queues avec un contexte spawn pour Windows
            ctx = mp.get_context('spawn')
            self.command_queue = ctx.Queue()
            self.data_queue = ctx.Queue()
            self.response_queue = ctx.Queue()
            
            # Démarrer le processus Neurosity avec le bon contexte
            self.neurosity_process = ctx.Process(
                target=neurosity_process_wrapper,
                args=(self.command_queue, self.data_queue, self.response_queue, str(ENV_PATH))
            )
            self.neurosity_process.daemon = True
            self.neurosity_process.start()
            
            # Attendre que le processus soit prêt
            time.sleep(1)
            
            # Démarrer le thread de traitement des données
            self.running = True
            self.data_thread = threading.Thread(target=self._data_processor, daemon=True)
            self.data_thread.start()
            
            logger.info("Processus et threads démarrés")
            return True
        
        except Exception as e:
            logger.error(f"Erreur démarrage module: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _stop_module(self):
        """Arrête le module et ses composants"""
        self.running = False
        
        # Arrêter le processus
        if self.command_queue:
            try:
                self.command_queue.put({'action': 'quit'})
            except:
                pass
        
        if self.neurosity_process and self.neurosity_process.is_alive():
            self.neurosity_process.join(timeout=5)
            if self.neurosity_process.is_alive():
                self.neurosity_process.terminate()
                self.neurosity_process.join(timeout=2)
        
        # Arrêter le thread
        if self.data_thread and self.data_thread.is_alive():
            self.data_thread.join(timeout=2)
        
        logger.info("Module arrêté")
    
    def _data_processor(self):
        """Thread qui traite les données reçues du processus"""
        logger.info("Processeur de données démarré")
        
        while self.running:
            try:
                # Traiter jusqu'à 10 messages par cycle
                for _ in range(10):
                    try:
                        message = self.data_queue.get_nowait()
                        self._handle_data_message(message)
                    except Empty:
                        break
                
                time.sleep(0.05)  # 50ms entre les cycles
            
            except Exception as e:
                logger.error(f"Erreur processeur de données: {e}")
                time.sleep(1)
    
    def _handle_data_message(self, message):
        """Traite un message de données"""
        try:
            data_type = message['type']
            data = message['data']
            timestamp = message['timestamp']
            device_status = message.get('device_status', {})
            
            # Mettre à jour le statut du dispositif
            self.device_status.update(device_status)
            
            # Préparer les données pour l'émission WebSocket
            emit_data = {
                'timestamp': timestamp,
                'device_status': self.device_status
            }
            
            # Formater selon le type de données
            if data_type == 'calm':
                emit_data['calm'] = data.get('percentage', 0)
                self.websocket_manager.broadcast(f'neurosity_calm_data', emit_data)
                if self.is_recording:
                    self.data_manager.add_data_point('calm', data)
            
            elif data_type == 'focus':
                emit_data['focus'] = data.get('percentage', 0)
                self.websocket_manager.broadcast(f'neurosity_focus_data', emit_data)
                if self.is_recording:
                    self.data_manager.add_data_point('focus', data)
            
            elif data_type == 'brainwaves':
                emit_data.update(data)
                self.websocket_manager.broadcast(f'neurosity_brainwaves_data', emit_data)
                if self.is_recording:
                    self.data_manager.add_data_point('brainwaves', data)
            
            elif data_type == 'signal_quality':
                emit_data.update(data)
                self.websocket_manager.broadcast(f'neurosity_signal_quality_data', emit_data)
            
            elif data_type == 'battery':
                emit_data.update(data)
                self.websocket_manager.broadcast(f'neurosity_battery_data', emit_data)
            
            elif data_type == 'brainwaves_raw':
                emit_data['raw_data'] = data.get('data', [])
                emit_data['info'] = data.get('info', {})
                self.websocket_manager.broadcast(f'neurosity_brainwaves_raw_data', emit_data)
                if self.is_recording:
                    self.data_manager.add_data_point('brainwaves_raw', data)
            
        except Exception as e:
            logger.error(f"Erreur traitement message: {e}")
            import traceback
            traceback.print_exc()
    
    def send_command(self, action, timeout=30):
        """Envoie une commande au processus Neurosity"""
        try:
            if not self.command_queue:
                return {'success': False, 'error': 'Module non initialisé'}
            
            # Vider la queue de réponse avant d'envoyer une nouvelle commande
            while True:
                try:
                    self.response_queue.get_nowait()
                except Empty:
                    break
            
            self.command_queue.put({'action': action})
            return self.response_queue.get(timeout=timeout)
        except Exception as e:
            logger.error(f"Erreur envoi commande: {e}")
            return {'success': False, 'error': str(e)}
    
    def connect_device(self):
        """Connecte le casque Neurosity"""
        logger.info("Tentative de connexion au casque...")
        response = self.send_command('connect', timeout=60)
        
        if response.get('success'):
            self.is_connected = True
            self.device_status = response.get('device_status', {})
            logger.info("Casque connecté avec succès")
        else:
            logger.error(f"Échec connexion: {response.get('error')}")
        
        return response
    
    def disconnect_device(self):
        """Déconnecte le casque Neurosity"""
        response = self.send_command('disconnect')
        
        if response.get('success'):
            self.is_connected = False
            self.is_monitoring = False
            self.device_status = {
                'online': False,
                'battery': 0,
                'charging': False,
                'signal': 'disconnected'
            }
            logger.info("Casque déconnecté")
        
        return response
    
    def start_monitoring(self):
        """Démarre le monitoring des données"""
        if not self.is_connected:
            return {'success': False, 'error': 'Casque non connecté'}
        
        response = self.send_command('start_monitoring')
        
        if response.get('success'):
            self.is_monitoring = True
            logger.info("Monitoring démarré")
        
        return response
    
    def stop_monitoring(self):
        """Arrête le monitoring des données"""
        response = self.send_command('stop_monitoring')
        
        if response.get('success'):
            self.is_monitoring = False
            logger.info("Monitoring arrêté")
        
        return response
    
    def start_recording(self, filename=None):
        """Démarre l'enregistrement des données"""
        if not self.is_connected:
            return {'success': False, 'error': 'Casque non connecté'}
        
        try:
            session_file = self.data_manager.start_session(filename)
            self.is_recording = True
            logger.info(f"Enregistrement démarré: {session_file}")
            
            return {
                'success': True,
                'recording': True,
                'session_file': session_file
            }
        
        except Exception as e:
            logger.error(f"Erreur démarrage enregistrement: {e}")
            return {'success': False, 'error': str(e)}
    
    def stop_recording(self):
        """Arrête l'enregistrement des données"""
        try:
            session_file = None
            if self.is_recording:
                session_file = self.data_manager.stop_session()
                self.is_recording = False
                logger.info(f"Enregistrement arrêté: {session_file}")
            
            return {
                'success': True,
                'recording': False,
                'session_file': session_file
            }
        
        except Exception as e:
            logger.error(f"Erreur arrêt enregistrement: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_sessions_list(self):
        """Récupère la liste des sessions enregistrées"""
        try:
            sessions = self.data_manager.get_session_list()
            return sessions
        except Exception as e:
            logger.error(f"Erreur récupération sessions: {e}")
            return []
    
    def get_status(self):
        """Récupère le statut complet du module"""
        return {
            'connected': self.is_connected,
            'monitoring': self.is_monitoring,
            'recording': self.is_recording,
            'device_status': self.device_status,
            'sessions_count': len(self.get_sessions_list())
        }
    
    def _register_routes(self):
        """Enregistre les routes API du module"""
        
        @self.app.route('/api/neurosity/connect', methods=['POST'])
        def api_connect():
            from flask import jsonify
            result = self.connect_device()
            return jsonify(result)
        
        @self.app.route('/api/neurosity/disconnect', methods=['POST'])
        def api_disconnect():
            from flask import jsonify
            result = self.disconnect_device()
            return jsonify(result)
        
        @self.app.route('/api/neurosity/start_recording', methods=['POST'])
        def api_start_recording():
            from flask import jsonify, request
            filename = request.json.get('filename') if request.is_json else None
            result = self.start_recording(filename)
            return jsonify(result)
        
        @self.app.route('/api/neurosity/stop_recording', methods=['POST'])
        def api_stop_recording():
            from flask import jsonify
            result = self.stop_recording()
            return jsonify(result)
        
        @self.app.route('/api/neurosity/sessions')
        def api_get_sessions():
            from flask import jsonify
            sessions = self.get_sessions_list()
            return jsonify({'sessions': sessions})
        
        @self.app.route('/api/neurosity/download/<filename>')
        def api_download_session(filename):
            from flask import send_file, abort
            file_path = self.data_manager.data_directory / filename
            if file_path.exists():
                return send_file(file_path, as_attachment=True)
            abort(404)
        
        @self.app.route('/api/neurosity/status')
        def api_get_status():
            from flask import jsonify
            return jsonify(self.get_status())
        
        @self.app.route('/api/neurosity/analyze/<filename>')
        def api_analyze_session(filename):
            from flask import jsonify
            analysis = self.data_manager.analyze_session(filename)
            return jsonify(analysis)
    
    def cleanup(self):
        """Nettoie les ressources du module"""
        logger.info("Nettoyage du module Neurosity...")
        
        # Arrêter l'enregistrement si actif
        if self.is_recording:
            self.stop_recording()
        
        # Déconnecter si connecté
        if self.is_connected:
            self.disconnect_device()
        
        # Arrêter le module
        self._stop_module()


def neurosity_process_wrapper(command_queue, data_queue, response_queue, env_path):
    """Wrapper pour le processus Neurosity - compatible Windows

    Args:
        command_queue: Queue pour recevoir les commandes
        data_queue: Queue pour envoyer les données
        response_queue: Queue pour envoyer les réponses
        env_path: Chemin vers le fichier .env
    """
    # Important: imports locaux pour éviter les problèmes de multiprocessing sur Windows
    import logging
    import time
    from datetime import datetime
    from dotenv import load_dotenv
    import os
    from pathlib import Path
    
    # Configuration du logging pour le processus
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger('neurosity_process')
    
    logger.info("[PROCESS] Démarrage du processus Neurosity...")
    
    # Charger les variables d'environnement
    if env_path and Path(env_path).exists():
        load_dotenv(dotenv_path=env_path)
        logger.info(f"[PROCESS] .env chargé depuis: {env_path}")
    else:
        load_dotenv()
        logger.info("[PROCESS] .env chargé avec méthode par défaut")
    
    try:
        from neurosity import NeurositySDK
    except ImportError:
        logger.error("[PROCESS] SDK Neurosity non installé")
        response_queue.put({
            'success': False,
            'error': 'SDK Neurosity non installé. Installez-le avec: pip install neurosity'
        })
        return
    
    neurosity = None
    is_connected = False
    is_monitoring = False
    subscriptions = []
    battery_subscription = None
    device_status = {
        'online': False,
        'battery': 0,
        'charging': False,
        'signal': 'disconnected'
    }
    
    def cleanup():
        """Nettoie les ressources"""
        nonlocal neurosity, is_monitoring, subscriptions, is_connected, battery_subscription
        
        # Nettoyer les souscriptions
        for unsub in subscriptions + ([battery_subscription] if battery_subscription else []):
            if callable(unsub):
                try:
                    unsub()
                except:
                    pass
        
        subscriptions = []
        battery_subscription = None
        is_monitoring = False
        
        if neurosity and is_connected:
            try:
                neurosity.logout()
            except:
                pass
        
        neurosity = None
        is_connected = False
    
    def send_data(data_type, data):
        """Envoie des données via la queue"""
        try:
            message = {
                'type': data_type,
                'data': data,
                'timestamp': datetime.now().isoformat(),
                'device_status': device_status.copy()
            }
            data_queue.put(message)
        except:
            pass
    
    def detect_device():
        """Détecte si le casque est connecté"""
        logger.info("[PROCESS] Détection du casque...")
        
        data_received = {'calm': False, 'focus': False}
        test_subs = []
        
        def test_callback(metric):
            def callback(data):
                if data and 'probability' in data:
                    data_received[metric] = True
            
            return callback
        
        try:
            test_subs = [
                neurosity.calm(test_callback('calm')),
                neurosity.focus(test_callback('focus'))
            ]
            
            # Attendre les données (10 secondes max)
            for i in range(100):
                if all(data_received.values()):
                    logger.info("[PROCESS] Casque détecté et opérationnel")
                    return True
                time.sleep(0.1)
            
            logger.warning("[PROCESS] Pas de données reçues du casque")
            return False
        
        finally:
            for sub in test_subs:
                if callable(sub):
                    try:
                        sub()
                    except:
                        pass
    
    # Callbacks pour les données
    def create_metric_callback(data_type):
        def callback(data):
            if data and 'probability' in data:
                send_data(data_type, {
                    'probability': data['probability'],
                    'percentage': data['probability'] * 100,
                    'timestamp': time.time() * 1000
                })
        
        return callback
    
    def brainwaves_callback(data):
        """Traite les données d'ondes cérébrales - VERSION MODIFIÉE"""
        try:
            if not data or 'data' not in data:
                return
            
            bands_data = data['data']
            result = {}
            
            # Pour chaque bande d'ondes, conserver toutes les 8 valeurs
            for wave in ['delta', 'theta', 'alpha', 'beta', 'gamma']:
                if wave in bands_data:
                    values = bands_data[wave]
                    if isinstance(values, list) and len(values) == 8:
                        # Conserver toutes les 8 valeurs (une par électrode)
                        result[wave] = [round(v, 3) if isinstance(v, (int, float)) and v >= 0 else 0 for v in values]
                    else:
                        # Si format incorrect, mettre 8 zéros
                        result[wave] = [0] * 8
                else:
                    # Si pas de données pour cette bande, mettre 8 zéros
                    result[wave] = [0] * 8
            
            result['timestamp'] = time.time() * 1000
            send_data('brainwaves', result)
        
        except Exception as e:
            logger.error(f"[PROCESS] Erreur brainwaves: {e}")
    
    def signal_quality_callback(data):
        """Traite la qualité du signal des électrodes"""
        try:
            if isinstance(data, list) and len(data) == 8:
                electrodes = ['CP3', 'C3', 'F5', 'PO3', 'PO4', 'F6', 'C4', 'CP4']
                
                signal_dict = {}
                for i in range(min(len(data), len(electrodes))):
                    electrode_data = data[i]
                    if isinstance(electrode_data, dict):
                        signal_dict[electrodes[i]] = {
                            'status': electrode_data.get('status', 'noContact'),
                            'standardDeviation': electrode_data.get('standardDeviation', 0)
                        }
                    else:
                        signal_dict[electrodes[i]] = {
                            'status': 'noContact',
                            'standardDeviation': 0
                        }
                
                send_data('signal_quality', signal_dict)
        
        except Exception as e:
            logger.error(f"[PROCESS] Erreur signal quality: {e}")
    
    def battery_callback(status):
        """Traite le statut de la batterie"""
        try:
            if isinstance(status, dict) and 'battery' in status:
                level = int(round(status.get('battery', 0)))
                charging = status.get('charging', False)
                
                device_status['battery'] = max(0, min(100, level))
                device_status['charging'] = charging
                
                send_data('battery', {
                    'level': device_status['battery'],
                    'charging': charging
                })
        
        except Exception as e:
            logger.error(f"[PROCESS] Erreur battery: {e}")
    
    def brainwaves_raw_callback(data):
        """Traite les données EEG brutes"""
        if data:
            send_data('brainwaves_raw', data)
    
    # Boucle principale du processus
    while True:
        try:
            command = command_queue.get(timeout=1)
            action = command.get('action')
            
            if action == 'connect':
                logger.info("[PROCESS] Connexion au casque...")
                try:
                    device_id = os.getenv("NEUROSITY_DEVICE_ID")
                    email = os.getenv("NEUROSITY_EMAIL")
                    password = os.getenv("NEUROSITY_PASSWORD")
                    
                    if not all([device_id, email, password]):
                        response_queue.put({
                            'success': False,
                            'error': 'Configuration manquante. Vérifiez votre fichier .env'
                        })
                        continue
                    
                    neurosity = NeurositySDK({
                        "device_id": device_id
                    })
                    
                    neurosity.login({
                        "email": email,
                        "password": password
                    })
                    
                    if detect_device():
                        is_connected = True
                        device_status['online'] = True
                        device_status['signal'] = 'excellent'
                        
                        # Récupérer le statut initial
                        try:
                            initial_status = neurosity.status()
                            if isinstance(initial_status, dict):
                                device_status['battery'] = int(round(initial_status.get('battery', 0)))
                                device_status['charging'] = initial_status.get('charging', False)
                        except:
                            pass
                        
                        # S'abonner au statut batterie
                        battery_subscription = neurosity.status(battery_callback)
                        
                        response_queue.put({
                            'success': True,
                            'connected': True,
                            'device_status': device_status,
                            'message': 'Casque Neurosity connecté !'
                        })
                    else:
                        cleanup()
                        response_queue.put({
                            'success': False,
                            'error': 'Casque non détecté. Vérifiez qu\'il est allumé et porté.'
                        })
                
                except Exception as e:
                    cleanup()
                    error_msg = str(e)
                    logger.error(f"[PROCESS] Erreur connexion: {error_msg}")
                    response_queue.put({'success': False, 'error': error_msg})
            
            elif action == 'start_monitoring':
                if not is_connected:
                    response_queue.put({'success': False, 'error': 'Non connecté'})
                    continue
                
                if not is_monitoring:
                    logger.info("[PROCESS] Démarrage du monitoring...")
                    
                    subscriptions = [
                        neurosity.calm(create_metric_callback('calm')),
                        neurosity.focus(create_metric_callback('focus')),
                        neurosity.brainwaves_power_by_band(brainwaves_callback),
                        neurosity.signal_quality(signal_quality_callback),
                        neurosity.brainwaves_raw(brainwaves_raw_callback)
                    ]
                    
                    is_monitoring = True
                    logger.info("[PROCESS] Monitoring actif")
                
                response_queue.put({'success': True, 'monitoring': True})
            
            elif action == 'stop_monitoring':
                if subscriptions:
                    for sub in subscriptions:
                        if callable(sub):
                            try:
                                sub()
                            except:
                                pass
                    subscriptions = []
                is_monitoring = False
                response_queue.put({'success': True, 'monitoring': False})
            
            elif action == 'disconnect':
                cleanup()
                device_status = {
                    'online': False,
                    'battery': 0,
                    'charging': False,
                    'signal': 'disconnected'
                }
                response_queue.put({'success': True, 'connected': False})
            
            elif action == 'quit':
                break
        
        except Empty:
            continue
        except Exception as e:
            logger.error(f"[PROCESS] Erreur: {e}")
            import traceback
            traceback.print_exc()
    
    cleanup()
    logger.info("[PROCESS] Processus terminé")


def register_neurosity_websocket_events(websocket_manager, neurosity_module):
    """Enregistre les événements WebSocket pour le module Neurosity"""
    
    def handle_connect(data):
        """Gère la connexion au casque"""
        logger.info("=== CONNEXION NEUROSITY DEMANDÉE ===")
        
        result = neurosity_module.connect_device()
        logger.info(f"Résultat connexion: {result}")
        
        if result.get('success'):
            # Émettre directement au client qui a fait la demande
            websocket_manager.emit_to_current_client('neurosity_connected', {
                'device_status': result.get('device_status', {}),
                'message': result.get('message', 'Connecté')
            })
            logger.info("Événement neurosity_connected émis")
            
            # Émettre le statut global au module
            websocket_manager.emit_to_module('neurosity', 'status', neurosity_module.get_status())
        else:
            # Émettre l'erreur directement au client
            error_message = result.get('error', 'Erreur de connexion')
            websocket_manager.emit_to_current_client('neurosity_error', {
                'error': error_message,
                'type': 'connection_failed'
            })
            logger.error(f"Erreur de connexion Neurosity: {error_message}")
    
    def handle_disconnect(data):
        """Gère la déconnexion du casque"""
        result = neurosity_module.disconnect_device()
        
        if result.get('success'):
            websocket_manager.emit_to_current_client('neurosity_disconnected', {})
            websocket_manager.emit_to_module('neurosity', 'status', neurosity_module.get_status())
    
    def handle_start_monitoring(data):
        """Démarre le monitoring"""
        result = neurosity_module.start_monitoring()
        
        if result.get('success'):
            websocket_manager.emit_to_module('neurosity', 'monitoring_started', {})
        else:
            websocket_manager.emit_to_current_client('neurosity_error', {
                'error': result.get('error', 'Erreur monitoring')
            })
    
    def handle_stop_monitoring(data):
        """Arrête le monitoring"""
        result = neurosity_module.stop_monitoring()
        
        if result.get('success'):
            websocket_manager.emit_to_module('neurosity', 'monitoring_stopped', {})
    
    def handle_start_recording(data):
        """Démarre l'enregistrement"""
        filename = data.get('filename') if data else None
        result = neurosity_module.start_recording(filename)
        
        websocket_manager.emit_to_current_client('neurosity_recording_status', result)
        websocket_manager.emit_to_module('neurosity', 'status', neurosity_module.get_status())
    
    def handle_stop_recording(data):
        """Arrête l'enregistrement"""
        result = neurosity_module.stop_recording()
        
        websocket_manager.emit_to_current_client('neurosity_recording_status', result)
        websocket_manager.emit_to_module('neurosity', 'status', neurosity_module.get_status())
        
        # Actualiser la liste des sessions
        sessions = neurosity_module.get_sessions_list()
        websocket_manager.emit_to_module('neurosity', 'sessions_updated', {
            'sessions': sessions
        })
    
    def handle_get_sessions(data):
        """Récupère la liste des sessions"""
        sessions = neurosity_module.get_sessions_list()
        websocket_manager.emit_to_current_client('neurosity_sessions_list', {
            'sessions': sessions
        })
    
    def handle_get_status(data):
        """Récupère le statut du module"""
        status = neurosity_module.get_status()
        websocket_manager.emit_to_current_client('neurosity_status', status)
    
    # Enregistrer les événements
    neurosity_events = {
        'connect': handle_connect,
        'disconnect': handle_disconnect,
        'start_monitoring': handle_start_monitoring,
        'stop_monitoring': handle_stop_monitoring,
        'start_recording': handle_start_recording,
        'stop_recording': handle_stop_recording,
        'get_sessions': handle_get_sessions,
        'get_status': handle_get_status
    }
    
    websocket_manager.register_module_events('neurosity', neurosity_events)
    logger.info("Événements WebSocket du module Neurosity enregistrés")


def init_neurosity_module(app, websocket_manager):
    """Initialise le module Neurosity"""
    
    try:
        # Créer le module
        neurosity_module = NeurosityModule(app, websocket_manager)
        
        # Enregistrer les événements WebSocket
        register_neurosity_websocket_events(websocket_manager, neurosity_module)
        
        return neurosity_module
    
    except ValueError as e:
        # Erreur de configuration (variables manquantes)
        logger.error(str(e))
        logger.error("Créez un fichier .env À LA RACINE DU PROJET avec:")
        logger.error("NEUROSITY_EMAIL=votre-email@exemple.com")
        logger.error("NEUROSITY_PASSWORD=votre-mot-de-passe")
        logger.error("NEUROSITY_DEVICE_ID=votre-device-id")
        return None
    
    except Exception as e:
        logger.error(f"Erreur initialisation module Neurosity: {e}")
        import traceback
        traceback.print_exc()
        return None