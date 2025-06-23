#!/usr/bin/env python3
"""
WebSocket Manager - BioMedical Hub
Gestionnaire centralisé pour toutes les communications WebSocket
"""

from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Gestionnaire centralisé des WebSockets pour tous les modules"""
    
    def __init__(self, app=None):
        self.app = app
        self.socketio = None
        self.connected_clients = {}
        self.active_modules = {}
        self.event_handlers = {}
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialiser le gestionnaire avec l'application Flask"""
        self.app = app
        self.socketio = SocketIO(
            app,
            cors_allowed_origins="*",
            async_mode='threading',
            logger=True,
            engineio_logger=True
        )
        
        # Enregistrer les événements par défaut
        self._register_default_events()
        logger.info("WebSocket Manager initialisé")
    
    def _register_default_events(self):
        """Enregistrer les événements WebSocket de base"""
        
        @self.socketio.on('connect')
        def handle_connect(auth):
            client_id = self._get_client_id()
            client_info = {
                'connected_at': datetime.now().isoformat(),
                'current_module': None,
                'subscriptions': [],
                'ip': self._get_client_ip(),
                'user_agent': self._get_user_agent()
            }
            
            self.connected_clients[client_id] = client_info
            logger.info(f"Client connecté: {client_id}")
            
            # Émettre le statut de connexion
            self.emit_to_client(client_id, 'connection_established', {
                'client_id': client_id,
                'timestamp': datetime.now().isoformat(),
                'server_info': self._get_server_info()
            })
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            client_id = self._get_client_id()
            self._cleanup_client(client_id)
            logger.info(f"Client déconnecté: {client_id}")
        
        @self.socketio.on('ping')
        def handle_ping(data):
            self.emit_to_current_client('pong', {
                'timestamp': datetime.now().isoformat(),
                'received_data': data
            })
        
        @self.socketio.on('subscribe_to_module')
        def handle_module_subscription(data):
            client_id = self._get_client_id()
            module_name = data.get('module')
            
            if self._subscribe_client_to_module(client_id, module_name):
                self.emit_to_current_client('subscription_confirmed', {
                    'module': module_name,
                    'timestamp': datetime.now().isoformat()
                })
            else:
                self.emit_to_current_client('subscription_failed', {
                    'module': module_name,
                    'error': 'Module not found or subscription failed'
                })
        
        @self.socketio.on('unsubscribe_from_module')
        def handle_module_unsubscription(data):
            client_id = self._get_client_id()
            module_name = data.get('module')
            
            if self._unsubscribe_client_from_module(client_id, module_name):
                self.emit_to_current_client('unsubscription_confirmed', {
                    'module': module_name,
                    'timestamp': datetime.now().isoformat()
                })
    
    def register_module_events(self, module_name, event_handlers):
        """Enregistrer les événements spécifiques à un module

        Args:
            module_name (str): Nom du module
            event_handlers (dict): Dictionnaire {event_name: handler_function}
        """
        if module_name not in self.event_handlers:
            self.event_handlers[module_name] = {}
        
        for event_name, handler in event_handlers.items():
            full_event_name = f"{module_name}_{event_name}"
            self.event_handlers[module_name][event_name] = handler
            
            # Enregistrer l'événement avec SocketIO
            self.socketio.on(full_event_name)(handler)
            logger.info(f"Événement enregistré: {full_event_name}")
    
    def emit_to_client(self, client_id, event, data):
        """Émettre un événement à un client spécifique"""
        self.socketio.emit(event, data, room=client_id)
    
    def emit_to_current_client(self, event, data):
        """Émettre un événement au client actuel"""
        emit(event, data)
    
    def emit_to_module(self, module_name, event, data):
        """Émettre un événement à tous les clients d'un module"""
        room_name = f"module_{module_name}"
        self.socketio.emit(event, data, room=room_name)
        logger.info(f"Événement {event} émis au module {module_name}")
    
    def broadcast(self, event, data):
        """Diffuser un événement à tous les clients connectés"""
        self.socketio.emit(event, data, broadcast=True)
        logger.info(f"Événement {event} diffusé à tous les clients")
    
    def get_module_clients(self, module_name):
        """Récupérer la liste des clients connectés à un module"""
        return self.active_modules.get(module_name, {}).get('clients', [])
    
    def get_client_info(self, client_id):
        """Récupérer les informations d'un client"""
        return self.connected_clients.get(client_id)
    
    def get_connected_clients_count(self):
        """Récupérer le nombre de clients connectés"""
        return len(self.connected_clients)
    
    def get_active_modules_count(self):
        """Récupérer le nombre de modules actifs"""
        return len(self.active_modules)
    
    def _subscribe_client_to_module(self, client_id, module_name):
        """Abonner un client à un module"""
        if client_id not in self.connected_clients:
            return False
        
        # Rejoindre la room du module
        join_room(f"module_{module_name}")
        
        # Ajouter à la liste des abonnements du client
        client_subscriptions = self.connected_clients[client_id].get('subscriptions', [])
        if module_name not in client_subscriptions:
            client_subscriptions.append(module_name)
            self.connected_clients[client_id]['subscriptions'] = client_subscriptions
        
        # Ajouter le client au module actif
        if module_name not in self.active_modules:
            self.active_modules[module_name] = {
                'activated_at': datetime.now().isoformat(),
                'clients': []
            }
        
        if client_id not in self.active_modules[module_name]['clients']:
            self.active_modules[module_name]['clients'].append(client_id)
        
        logger.info(f"Client {client_id} abonné au module {module_name}")
        return True
    
    def _unsubscribe_client_from_module(self, client_id, module_name):
        """Désabonner un client d'un module"""
        if client_id not in self.connected_clients:
            return False
        
        # Quitter la room du module
        leave_room(f"module_{module_name}")
        
        # Retirer de la liste des abonnements du client
        client_subscriptions = self.connected_clients[client_id].get('subscriptions', [])
        if module_name in client_subscriptions:
            client_subscriptions.remove(module_name)
            self.connected_clients[client_id]['subscriptions'] = client_subscriptions
        
        # Retirer le client du module actif
        if module_name in self.active_modules:
            if client_id in self.active_modules[module_name]['clients']:
                self.active_modules[module_name]['clients'].remove(client_id)
            
            # Supprimer le module s'il n'y a plus de clients
            if not self.active_modules[module_name]['clients']:
                del self.active_modules[module_name]
        
        logger.info(f"Client {client_id} désabonné du module {module_name}")
        return True
    
    def _cleanup_client(self, client_id):
        """Nettoyer les données d'un client déconnecté"""
        if client_id not in self.connected_clients:
            return
        
        # Désabonner de tous les modules
        subscriptions = self.connected_clients[client_id].get('subscriptions', [])
        for module_name in subscriptions:
            self._unsubscribe_client_from_module(client_id, module_name)
        
        # Supprimer le client
        del self.connected_clients[client_id]
    
    def _get_client_id(self):
        """Récupérer l'ID du client actuel"""
        from flask import request
        return request.sid
    
    def _get_client_ip(self):
        """Récupérer l'IP du client actuel"""
        from flask import request
        return request.remote_addr
    
    def _get_user_agent(self):
        """Récupérer le User-Agent du client actuel"""
        from flask import request
        return request.headers.get('User-Agent', 'Unknown')
    
    def _get_server_info(self):
        """Récupérer les informations du serveur"""
        return {
            'timestamp': datetime.now().isoformat(),
            'connected_clients': len(self.connected_clients),
            'active_modules': len(self.active_modules),
            'version': '1.0.0'
        }


# Instance globale du gestionnaire WebSocket
websocket_manager = WebSocketManager()