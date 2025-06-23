/**
 * WebSocket Client - BioMedical Hub
 * Client WebSocket réutilisable pour tous les modules
 */

class WebSocketClient {
    constructor(options = {}) {
        this.socket = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 5;
        this.reconnectDelay = options.reconnectDelay || 1000;
        this.eventListeners = new Map();
        this.moduleSubscriptions = new Set();
        this.clientId = null;

        // Options de configuration
        this.options = {
            autoConnect: options.autoConnect !== false,
            reconnection: options.reconnection !== false,
            timeout: options.timeout || 20000,
            ...options
        };

        if (this.options.autoConnect) {
            this.connect();
        }
    }

    /**
     * Établir la connexion WebSocket
     */
    connect() {
        try {
            this.socket = io({
                autoConnect: false,
                reconnection: false, // Gérer la reconnexion manuellement
                timeout: this.options.timeout
            });

            this._setupDefaultEvents();
            this.socket.connect();

            console.log('Tentative de connexion WebSocket...');
        } catch (error) {
            console.error('Erreur lors de la connexion WebSocket:', error);
            this._handleConnectionError(error);
        }
    }

    /**
     * Déconnexion propre
     */
    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.isConnected = false;
            console.log('Déconnexion WebSocket');
        }
    }

    /**
     * Configurer les événements par défaut
     */
    _setupDefaultEvents() {
        this.socket.on('connect', () => {
            this.isConnected = true;
            this.reconnectAttempts = 0;
            console.log('WebSocket connecté');
            this._emit('connected');
        });

        this.socket.on('disconnect', (reason) => {
            this.isConnected = false;
            console.log('WebSocket déconnecté:', reason);
            this._emit('disconnected', { reason });

            if (this.options.reconnection && reason !== 'io client disconnect') {
                this._attemptReconnection();
            }
        });

        this.socket.on('connect_error', (error) => {
            console.error('Erreur de connexion WebSocket:', error);
            this._handleConnectionError(error);
        });

        this.socket.on('connection_established', (data) => {
            this.clientId = data.client_id;
            console.log('Client ID reçu:', this.clientId);
            this._emit('connection_established', data);
        });

        this.socket.on('pong', (data) => {
            this._emit('pong', data);
        });

        this.socket.on('subscription_confirmed', (data) => {
            this.moduleSubscriptions.add(data.module);
            console.log(`Abonné au module: ${data.module}`);
            this._emit('subscription_confirmed', data);
        });

        this.socket.on('subscription_failed', (data) => {
            console.error(`Échec d'abonnement au module: ${data.module}`, data.error);
            this._emit('subscription_failed', data);
        });

        this.socket.on('unsubscription_confirmed', (data) => {
            this.moduleSubscriptions.delete(data.module);
            console.log(`Désabonné du module: ${data.module}`);
            this._emit('unsubscription_confirmed', data);
        });
    }

    /**
     * Gestion des erreurs de connexion
     */
    _handleConnectionError(error) {
        this._emit('connection_error', error);

        if (this.options.reconnection) {
            this._attemptReconnection();
        }
    }

    /**
     * Tentative de reconnexion automatique
     */
    _attemptReconnection() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Nombre maximum de tentatives de reconnexion atteint');
            this._emit('reconnection_failed');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Backoff exponentiel

        console.log(`Tentative de reconnexion ${this.reconnectAttempts}/${this.maxReconnectAttempts} dans ${delay}ms`);

        setTimeout(() => {
            if (!this.isConnected) {
                this.connect();
            }
        }, delay);
    }

    /**
     * Émettre un événement vers le serveur
     */
    emit(event, data = {}) {
        if (!this.isConnected) {
            console.warn('Tentative d\'émission sur une connexion fermée:', event);
            return false;
        }

        this.socket.emit(event, {
            ...data,
            timestamp: new Date().toISOString(),
            client_id: this.clientId
        });

        return true;
    }

    /**
     * Écouter un événement du serveur
     */
    on(event, callback) {
        if (!this.eventListeners.has(event)) {
            this.eventListeners.set(event, []);

            // Enregistrer l'événement avec Socket.IO
            this.socket?.on(event, (data) => {
                this._emit(event, data);
            });
        }

        this.eventListeners.get(event).push(callback);
    }

    /**
     * Arrêter d'écouter un événement
     */
    off(event, callback = null) {
        if (!this.eventListeners.has(event)) return;

        if (callback) {
            const listeners = this.eventListeners.get(event);
            const index = listeners.indexOf(callback);
            if (index !== -1) {
                listeners.splice(index, 1);
            }

            if (listeners.length === 0) {
                this.eventListeners.delete(event);
                this.socket?.off(event);
            }
        } else {
            this.eventListeners.delete(event);
            this.socket?.off(event);
        }
    }

    /**
     * S'abonner à un module
     */
    subscribeToModule(moduleName) {
        if (!this.isConnected) {
            console.warn(`Impossible de s'abonner au module ${moduleName}: pas de connexion`);
            return Promise.reject(new Error('No connection'));
        }

        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                reject(new Error('Subscription timeout'));
            }, 5000);

            const handleConfirmation = (data) => {
                if (data.module === moduleName) {
                    clearTimeout(timeout);
                    this.off('subscription_confirmed', handleConfirmation);
                    this.off('subscription_failed', handleFailure);
                    resolve(data);
                }
            };

            const handleFailure = (data) => {
                if (data.module === moduleName) {
                    clearTimeout(timeout);
                    this.off('subscription_confirmed', handleConfirmation);
                    this.off('subscription_failed', handleFailure);
                    reject(new Error(data.error || 'Subscription failed'));
                }
            };

            this.on('subscription_confirmed', handleConfirmation);
            this.on('subscription_failed', handleFailure);

            this.emit('subscribe_to_module', { module: moduleName });
        });
    }

    /**
     * Se désabonner d'un module
     */
    unsubscribeFromModule(moduleName) {
        if (!this.isConnected) {
            console.warn(`Impossible de se désabonner du module ${moduleName}: pas de connexion`);
            return Promise.reject(new Error('No connection'));
        }

        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                reject(new Error('Unsubscription timeout'));
            }, 5000);

            const handleConfirmation = (data) => {
                if (data.module === moduleName) {
                    clearTimeout(timeout);
                    this.off('unsubscription_confirmed', handleConfirmation);
                    resolve(data);
                }
            };

            this.on('unsubscription_confirmed', handleConfirmation);
            this.emit('unsubscribe_from_module', { module: moduleName });
        });
    }

    /**
     * Envoyer un ping au serveur
     */
    ping(data = {}) {
        return this.emit('ping', data);
    }

    /**
     * Émettre un événement spécifique à un module
     */
    emitToModule(moduleName, event, data = {}) {
        const fullEventName = `${moduleName}_${event}`;
        return this.emit(fullEventName, data);
    }

    /**
     * Écouter un événement spécifique à un module
     */
    onModuleEvent(moduleName, event, callback) {
        const fullEventName = `${moduleName}_${event}`;
        this.on(fullEventName, callback);
    }

    /**
     * Arrêter d'écouter un événement spécifique à un module
     */
    offModuleEvent(moduleName, event, callback = null) {
        const fullEventName = `${moduleName}_${event}`;
        this.off(fullEventName, callback);
    }

    /**
     * Récupérer le statut de connexion
     */
    getConnectionStatus() {
        return {
            connected: this.isConnected,
            clientId: this.clientId,
            reconnectAttempts: this.reconnectAttempts,
            subscriptions: Array.from(this.moduleSubscriptions)
        };
    }

    /**
     * Émettre un événement local
     */
    _emit(event, data) {
        if (this.eventListeners.has(event)) {
            this.eventListeners.get(event).forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`Erreur dans le callback de l'événement ${event}:`, error);
                }
            });
        }
    }

    /**
     * Nettoyer les ressources
     */
    destroy() {
        this.disconnect();
        this.eventListeners.clear();
        this.moduleSubscriptions.clear();
        this.socket = null;
    }
}

// Fonction utilitaire pour créer une instance globale
function createWebSocketClient(options = {}) {
    return new WebSocketClient(options);
}

// Export pour utilisation dans d'autres modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { WebSocketClient, createWebSocketClient };
} else if (typeof window !== 'undefined') {
    window.WebSocketClient = WebSocketClient;
    window.createWebSocketClient = createWebSocketClient;
}