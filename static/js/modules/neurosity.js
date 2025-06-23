/**
 * MODULE NEUROSITY EEG CROWN - Version intégrée Dashboard BioMedical Hub
 * Interface utilisateur adaptée à la détection biologique réelle
 * Avec Sessions Manager optimisé pour milliers de fichiers
 * Architecture modulaire respectée
 */

// Namespace principal du module Neurosity
window.Neurosity = window.Neurosity || {};

// ===============================================
// CONFIGURATION ET ÉTAT DU MODULE
// ===============================================

// État global du module Neurosity
Neurosity.AppState = {
    isConnected: false,
    isRecording: false,
    isMonitoring: false,
    wsClient: null,
    chart: null,
    deviceStatus: {
        online: false,
        battery: 'unknown',
        signal: 'disconnected',
        validation: 'pending'
    },
    connectionHealth: true,
    lastDataTime: null,
    detectionInProgress: false,
    debugMode: false,
    currentSessionFile: null
};

// ===============================================
// SESSIONS MANAGER OPTIMISÉ POUR LE MODULE
// ===============================================

Neurosity.SessionsManager = {
    allSessions: [],
    visibleSessions: [],
    currentPage: 0,
    itemsPerPage: 50,
    isVirtualizationEnabled: false,
    scrollContainer: null,

    init() {
        this.scrollContainer = document.querySelector('.sessions-scroll-container');
        if (this.scrollContainer) {
            this.setupScrollHandlers();
        }
    },

    setupScrollHandlers() {
        if (!this.scrollContainer) return;

        this.scrollContainer.addEventListener('scroll', this.throttle(() => {
            this.handleScroll();
            this.updateScrollIndicators();
        }, 100));

        const observer = new MutationObserver(() => {
            this.updateScrollIndicators();
        });

        observer.observe(this.scrollContainer, {
            childList: true,
            subtree: true
        });
    },

    updateScrollIndicators() {
        if (!this.scrollContainer) return;

        const { scrollTop, scrollHeight, clientHeight } = this.scrollContainer;
        const hasScroll = scrollHeight > clientHeight;

        if (hasScroll) {
            this.scrollContainer.classList.add('has-scroll');
        } else {
            this.scrollContainer.classList.remove('has-scroll');
        }

        if (this.allSessions.length > 100) {
            this.scrollContainer.classList.add('many-sessions');
        } else {
            this.scrollContainer.classList.remove('many-sessions');
        }
    },

    handleScroll() {
        if (!this.isVirtualizationEnabled || !this.scrollContainer) return;

        const { scrollTop, scrollHeight, clientHeight } = this.scrollContainer;
        const scrollPercentage = scrollTop / (scrollHeight - clientHeight);

        if (scrollPercentage > 0.8 && this.hasMoreSessions()) {
            this.loadMoreSessions();
        }
    },

    hasMoreSessions() {
        return (this.currentPage + 1) * this.itemsPerPage < this.allSessions.length;
    },

    loadMoreSessions() {
        if (!this.hasMoreSessions()) return;

        this.currentPage++;
        const startIndex = this.currentPage * this.itemsPerPage;
        const endIndex = Math.min(startIndex + this.itemsPerPage, this.allSessions.length);

        const newSessions = this.allSessions.slice(startIndex, endIndex);
        this.visibleSessions.push(...newSessions);

        this.appendSessionsToDOM(newSessions);

        if (Neurosity.showToast) {
            Neurosity.showToast(
                `📄 ${newSessions.length} sessions supplémentaires chargées`,
                'info',
                2000
            );
        }
    },

    appendSessionsToDOM(sessions) {
        const sessionsList = document.getElementById('sessionsList');
        if (!sessionsList) return;

        const fragment = document.createDocumentFragment();

        sessions.forEach((session, index) => {
            const sessionElement = this.createSessionElement(session, this.visibleSessions.length - sessions.length + index);
            fragment.appendChild(sessionElement);
        });

        sessionsList.appendChild(fragment);
    },

    createSessionElement(session, index) {
        const sessionItem = document.createElement('div');
        sessionItem.className = 'session-item';
        sessionItem.style.animationDelay = `${(index % 10) * 0.05}s`;

        const dateMatch = session.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
        let displayDate = 'Session';
        let displayTime = '';

        if (dateMatch) {
            const [, year, month, day, hour, minute, second] = dateMatch;
            displayDate = `${day}/${month}/${year}`;
            displayTime = `${hour}:${minute}`;
        }

        sessionItem.innerHTML = `
            <div class="session-info">
                <div class="session-name">
                    ${session} 
                    <span style="color: #8b5cf6; font-size: 0.875rem;">✓</span>
                </div>
                <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 0.25rem; display: flex; gap: 1rem; flex-wrap: wrap;">
                    <span>📅 ${displayDate}</span>
                    <span>🕒 ${displayTime}</span>
                    <span style="color: #8b5cf6;">🔬 Données biologiques validées</span>
                </div>
            </div>
            <div class="session-actions">
                <button class="btn btn-outline btn-small" onclick="Neurosity.downloadSession('${session}')" title="Télécharger CSV validé">
                    <span>⬇️</span> CSV
                </button>
            </div>
        `;

        return sessionItem;
    },

    throttle(func, limit) {
        let lastFunc;
        let lastRan;
        return function() {
            const context = this;
            const args = arguments;
            if (!lastRan) {
                func.apply(context, args);
                lastRan = Date.now();
            } else {
                clearTimeout(lastFunc);
                lastFunc = setTimeout(function() {
                    if ((Date.now() - lastRan) >= limit) {
                        func.apply(context, args);
                        lastRan = Date.now();
                    }
                }, limit - (Date.now() - lastRan));
            }
        }
    }
};

// ===============================================
// SYSTÈME DE NOTIFICATIONS TOAST DU MODULE
// ===============================================

Neurosity.showToast = function(message, type = 'info', duration = 4000) {
    let toastContainer = document.getElementById('neurosityToastContainer');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'neurosityToastContainer';
        toastContainer.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 10px;
            max-width: 450px;
        `;
        document.body.appendChild(toastContainer);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.style.cssText = `
        padding: 16px 22px;
        border-radius: 12px;
        color: white;
        font-weight: 500;
        font-size: 14px;
        line-height: 1.4;
        min-width: 350px;
        box-shadow: 0 6px 25px rgba(0,0,0,0.15);
        transform: translateX(100%);
        transition: transform 0.3s ease;
        cursor: pointer;
        position: relative;
        overflow: hidden;
        backdrop-filter: blur(10px);
    `;

    const colors = {
        success: 'linear-gradient(135deg, #10b981 0%, #34d399 100%)',
        error: 'linear-gradient(135deg, #ef4444 0%, #f87171 100%)',
        warning: 'linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)',
        info: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
        detection: 'linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%)'
    };

    toast.style.background = colors[type] || colors.info;

    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: '💡',
        detection: '🔬'
    };

    const icon = icons[type] || icons.info;

    toast.innerHTML = `
        <div style="display: flex; align-items: flex-start; gap: 12px;">
            <div style="font-size: 18px; margin-top: 2px;">${icon}</div>
            <div style="flex: 1; line-height: 1.4;">${message}</div>
            <div style="cursor: pointer; opacity: 0.8; font-size: 18px; margin-left: 8px;">×</div>
        </div>
    `;

    toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.style.transform = 'translateX(0)';
    }, 10);

    const closeBtn = toast.querySelector('div:last-child');
    closeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        Neurosity.removeToast(toast);
    });

    toast.addEventListener('click', () => {
        Neurosity.removeToast(toast);
    });

    if (duration > 0) {
        setTimeout(() => {
            Neurosity.removeToast(toast);
        }, duration);
    }
};

Neurosity.removeToast = function(toast) {
    if (toast && toast.parentNode) {
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }
};

// ===============================================
// INITIALISATION DU MODULE
// ===============================================

Neurosity.init = function() {
    console.log('🚀 Démarrage Module Neurosity EEG Crown...');

    this.initializeUI();
    this.initializeCharts();
    this.initializeWebSocket();
    this.loadSessions();

    // Initialiser le gestionnaire de sessions optimisé
    this.SessionsManager.init();

    // Initialiser l'horloge du module
    this.initializeClock();

    this.showToast('🧠 Module Neurosity prêt ! Détection activée - Allumez votre casque Neurosity Crown puis cliquez "Connecter"', 'info', 8000);
    console.log('✅ Module Neurosity prêt avec détection et Sessions Manager optimisé');
};

Neurosity.initializeClock = function() {
    const timeElement = document.getElementById('neurosityCurrentTime');
    if (!timeElement) return;

    function updateClock() {
        try {
            const now = new Date();
            timeElement.textContent = now.toLocaleTimeString('fr-FR');
        } catch (e) {
            console.warn('Erreur mise à jour horloge Neurosity:', e);
        }
    }

    updateClock();
    setInterval(updateClock, 1000);
};

// ===============================================
// INITIALISATION INTERFACE UTILISATEUR
// ===============================================

Neurosity.initializeUI = function() {
    console.log('🎨 Initialisation UI Neurosity avec détection...');
    this.updateConnectionStatus(false, false, false);
    this.addStrictDetectionIndicator();
};

Neurosity.addStrictDetectionIndicator = function() {
    const navbar = document.querySelector('.neurosity-navbar');
    if (navbar && !document.getElementById('neurosityStrictModeIndicator')) {
        const indicator = document.createElement('div');
        indicator.id = 'neurosityStrictModeIndicator';
        indicator.style.cssText = `
            position: absolute;
            top: -8px;
            right: 20px;
            background: linear-gradient(135deg, #8b5cf6, #a855f7);
            color: white;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.7rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 8px rgba(139, 92, 246, 0.3);
        `;
        indicator.textContent = '🔬 Détection';
        navbar.appendChild(indicator);
    }
};

// ===============================================
// INITIALISATION WEBSOCKET AVEC ARCHITECTURE MODULAIRE
// ===============================================

Neurosity.initializeWebSocket = function() {
    console.log('🔌 Initialisation WebSocket Neurosity avec architecture modulaire...');

    // Utiliser le WebSocketClient existant du dashboard
    if (typeof WebSocketClient !== 'undefined' && window.dashboard && window.dashboard.wsClient) {
        this.AppState.wsClient = window.dashboard.wsClient;
        this.setupWebSocketEvents();
    } else {
        console.warn('⚠️ WebSocketClient non disponible, mode local pour Neurosity');
    }
};

Neurosity.setupWebSocketEvents = function() {
    if (!this.AppState.wsClient) return;

    // S'abonner au module neurosity
    this.AppState.wsClient.subscribeToModule('neurosity').then(() => {
        console.log('✅ Abonné au module neurosity');
    }).catch(err => {
        console.warn('⚠️ Erreur abonnement module neurosity:', err);
    });

    // Événements spécifiques au module Neurosity
    this.AppState.wsClient.onModuleEvent('neurosity', 'calm_data', (data) => {
        this.handleCalmData(data);
    });

    this.AppState.wsClient.onModuleEvent('neurosity', 'focus_data', (data) => {
        this.handleFocusData(data);
    });

    this.AppState.wsClient.onModuleEvent('neurosity', 'brainwaves_data', (data) => {
        this.handleBrainwavesData(data);
    });

    this.AppState.wsClient.onModuleEvent('neurosity', 'status_update', (data) => {
        this.updateConnectionStatus(data.connected, data.recording, data.monitoring);
        if (data.device_status) {
            this.updateDeviceStatus(data.device_status);
        }
    });

    this.AppState.wsClient.onModuleEvent('neurosity', 'monitoring_started', () => {
        this.showToast('🎯 Monitoring démarré ! Données biologiques validées en temps réel', 'success');
        this.AppState.isMonitoring = true;
        this.updateMonitoringStatus(true);
        this.updateConnectionStatus(this.AppState.isConnected, this.AppState.isRecording, true);
    });

    this.AppState.wsClient.onModuleEvent('neurosity', 'monitoring_stopped', () => {
        this.showToast('⏹️ Monitoring arrêté', 'info');
        this.AppState.isMonitoring = false;
        this.updateMonitoringStatus(false);
        this.updateConnectionStatus(this.AppState.isConnected, this.AppState.isRecording, false);
    });

    this.AppState.wsClient.onModuleEvent('neurosity', 'connection_warning', (data) => {
        this.showToast(`⚠️ ${data.message}`, 'warning', 8000);
        this.AppState.connectionHealth = false;
        this.updateConnectionHealth(false);
    });

    this.AppState.wsClient.onModuleEvent('neurosity', 'connection_restored', (data) => {
        this.showToast(`✅ ${data.message}`, 'success', 3000);
        this.AppState.connectionHealth = true;
        this.updateConnectionHealth(true);
    });
};

// ===============================================
// GRAPHIQUES NEUROSITY (CHART.JS)
// ===============================================

Neurosity.initializeCharts = function() {
    console.log('📊 Initialisation des graphiques PSD en barres Neurosity...');

    const canvas = document.getElementById('brainwavesChart');
    if (!canvas) {
        console.error('❌ Canvas brainwavesChart non trouvé');
        return;
    }

    if (this.AppState.chart) {
        this.AppState.chart.destroy();
    }

    const ctx = canvas.getContext('2d');

    this.AppState.chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [
                'Delta\n0.5-4 Hz',
                'Theta\n4-8 Hz',
                'Alpha\n8-12 Hz',
                'Beta\n12-30 Hz',
                'Gamma\n30+ Hz'
            ],
            datasets: [{
                label: 'Densité Spectrale de Puissance (μV²/Hz)',
                data: [0, 0, 0, 0, 0],
                backgroundColor: [
                    'rgba(99, 102, 241, 0.8)',
                    'rgba(139, 92, 246, 0.8)',
                    'rgba(16, 185, 129, 0.8)',
                    'rgba(245, 158, 11, 0.8)',
                    'rgba(239, 68, 68, 0.8)'
                ],
                borderColor: [
                    '#6366f1',
                    '#8b5cf6',
                    '#10b981',
                    '#f59e0b',
                    '#ef4444'
                ],
                borderWidth: 2,
                borderRadius: 8,
                borderSkipped: false,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 150,
                easing: 'easeOutQuint'
            },
            plugins: {
                legend: {
                    display: false
                },
                title: {
                    display: true,
                    text: 'Ondes Cérébrales Validées - Temps Réel',
                    font: {
                        family: 'Inter',
                        size: 16,
                        weight: '600'
                    },
                    color: '#334155',
                    padding: 20
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#ffffff',
                    bodyColor: '#ffffff',
                    borderColor: '#6366f1',
                    borderWidth: 1,
                    cornerRadius: 8,
                    displayColors: true,
                    callbacks: {
                        title: function(context) {
                            return context[0].label.split('\n')[0];
                        },
                        label: function(context) {
                            return `${context.parsed.y.toFixed(4)} μV²/Hz`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Types d\'ondes cérébrales',
                        font: {
                            family: 'Inter',
                            size: 14,
                            weight: '500'
                        },
                        color: '#64748b',
                        padding: 10
                    },
                    grid: {
                        display: false
                    },
                    ticks: {
                        font: {
                            family: 'Inter',
                            size: 11,
                            weight: '500'
                        },
                        color: '#64748b',
                        maxRotation: 0,
                        padding: 10
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Densité Spectrale de Puissance (μV²/Hz)',
                        font: {
                            family: 'Inter',
                            size: 14,
                            weight: '500'
                        },
                        color: '#64748b',
                        padding: 10
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.08)',
                        drawBorder: false,
                        lineWidth: 1
                    },
                    ticks: {
                        font: {
                            family: 'Inter',
                            size: 11
                        },
                        color: '#94a3b8',
                        padding: 8,
                        callback: function(value) {
                            return value.toFixed(3) + ' μV²/Hz';
                        }
                    },
                    beginAtZero: true,
                    max: 0.5
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            },
            elements: {
                bar: {
                    borderRadius: 8,
                    borderWidth: 2
                }
            }
        }
    });

    console.log('✅ Graphique en barres Neurosity créé avec PSD');
};

// ===============================================
// FONCTIONS DE CONNEXION/CONTRÔLE
// ===============================================

Neurosity.connectDevice = function() {
    const connectBtn = document.getElementById('connectBtn');
    if (connectBtn) {
        connectBtn.disabled = true;
        connectBtn.innerHTML = '<span>⏳</span><span class="btn-text">Connexion...</span>';
    }

    this.showToast('🔄 Connexion en cours...', 'info', 3000);

    // Émettre via WebSocket modulaire
    if (this.AppState.wsClient) {
        this.AppState.wsClient.emitToModule('neurosity', 'connect_device', {});
    } else {
        // Fallback API REST
        fetch('/api/neurosity/connect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.showToast('✅ ' + (data.message || 'Casque connecté avec succès !'), 'success');
                this.updateConnectionButton(true);
                this.AppState.isConnected = true;
                this.AppState.deviceStatus = data.device_status || {};
                this.updateConnectionStatus(true, false, false);
                this.updateDeviceStatus(data.device_status || {});

                setTimeout(() => {
                    console.log('🎯 Démarrage automatique du monitoring...');
                    this.startMonitoring();
                }, 1000);
            } else {
                this.showToast('❌ ' + (data.error || 'Erreur de connexion'), 'error', 8000);
                this.updateConnectionButton(false);
                this.AppState.isConnected = false;
                this.updateConnectionStatus(false, false, false);
            }
        })
        .catch(error => {
            console.error('Erreur connexion:', error);
            this.showToast('❌ Erreur de connexion réseau', 'error');
            this.updateConnectionButton(false);
            this.AppState.isConnected = false;
            this.updateConnectionStatus(false, false, false);
        })
        .finally(() => {
            if (connectBtn) {
                connectBtn.disabled = false;
            }
        });
    }
};

Neurosity.disconnectDevice = function() {
    if (!confirm('Êtes-vous sûr de vouloir déconnecter le casque ?')) {
        return;
    }

    const connectBtn = document.getElementById('connectBtn');
    if (connectBtn) {
        connectBtn.disabled = true;
        connectBtn.innerHTML = '<span>⏳</span><span class="btn-text">Déconnexion...</span>';
    }

    if (this.AppState.wsClient) {
        this.AppState.wsClient.emitToModule('neurosity', 'disconnect_device', {});
    } else {
        // Fallback API REST
        fetch('/api/neurosity/disconnect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.showToast('🔌 Casque déconnecté', 'success');
                this.updateConnectionButton(false);

                if (this.AppState.isMonitoring) {
                    this.stopMonitoring();
                }

                this.AppState.isConnected = false;
                this.AppState.isMonitoring = false;
                this.updateConnectionStatus(false, false, false);
            } else {
                this.showToast('❌ Erreur déconnexion: ' + (data.error || 'Erreur inconnue'), 'error');
            }
        })
        .catch(error => {
            console.error('Erreur déconnexion:', error);
            this.showToast('❌ Erreur de déconnexion', 'error');
        })
        .finally(() => {
            if (connectBtn) {
                connectBtn.disabled = false;
            }
        });
    }
};

Neurosity.updateConnectionButton = function(connected) {
    const connectBtn = document.getElementById('connectBtn');
    if (!connectBtn) return;

    if (connected) {
        connectBtn.innerHTML = '<span>🔌</span><span class="btn-text">Déconnecter</span>';
        connectBtn.className = 'btn btn-danger';
        connectBtn.onclick = () => this.disconnectDevice();
        connectBtn.title = 'Déconnecter le casque Neurosity';
    } else {
        connectBtn.innerHTML = '<span>🔗</span><span class="btn-text">Connecter</span>';
        connectBtn.className = 'btn btn-primary';
        connectBtn.onclick = () => this.connectDevice();
        connectBtn.title = 'Connecter le casque Neurosity (Ctrl+K)';
    }
};

Neurosity.startMonitoring = function() {
    if (!this.AppState.wsClient) {
        console.error('❌ WebSocket non disponible pour le monitoring');
        this.showToast('❌ Erreur WebSocket - impossible de démarrer le monitoring', 'error');
        return;
    }

    if (!this.AppState.isConnected) {
        console.warn('⚠️ Tentative de démarrage monitoring sans connexion');
        this.showToast('⚠️ Connectez d\'abord votre casque Neurosity Crown', 'warning');
        return;
    }

    if (this.AppState.isMonitoring) {
        console.log('🎯 Monitoring déjà actif');
        return;
    }

    console.log('🎯 Envoi commande start_monitoring...');
    this.showToast('🎯 Démarrage du monitoring...', 'info', 2000);

    try {
        this.AppState.wsClient.emitToModule('neurosity', 'start_monitoring', {});
    } catch (error) {
        console.error('❌ Erreur émission start_monitoring:', error);
        this.showToast('❌ Erreur de démarrage du monitoring', 'error');
    }
};

Neurosity.stopMonitoring = function() {
    if (!this.AppState.wsClient) {
        console.error('❌ WebSocket non disponible pour arrêter le monitoring');
        return;
    }

    if (!this.AppState.isMonitoring) {
        console.log('⏹️ Monitoring déjà arrêté');
        return;
    }

    console.log('⏹️ Envoi commande stop_monitoring...');
    this.showToast('⏹️ Arrêt du monitoring...', 'info', 2000);

    try {
        this.AppState.wsClient.emitToModule('neurosity', 'stop_monitoring', {});
    } catch (error) {
        console.error('❌ Erreur émission stop_monitoring:', error);
        this.showToast('❌ Erreur d\'arrêt du monitoring', 'error');
    }
};

Neurosity.toggleRecording = function() {
    if (!this.AppState.isConnected) {
        this.showToast('⚠️ Connectez d\'abord votre casque Neurosity Crown avec la détection', 'warning');
        return;
    }

    const endpoint = this.AppState.isRecording ? '/api/neurosity/stop_recording' : '/api/neurosity/start_recording';
    const actionText = this.AppState.isRecording ? 'Arrêt' : 'Démarrage';

    this.showToast(`🎬 ${actionText} de l'enregistrement...`, 'info');

    if (this.AppState.wsClient) {
        const action = this.AppState.isRecording ? 'stop_recording' : 'start_recording';
        this.AppState.wsClient.emitToModule('neurosity', action, {});
    } else {
        // Fallback API REST
        fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                this.AppState.isRecording = result.recording;

                if (this.AppState.isRecording) {
                    this.showToast('🔴 Enregistrement démarré ! Données biologiques validées sauvegardées en temps réel', 'success');
                    this.AppState.currentSessionFile = result.session_file;
                } else {
                    this.showToast('⏹️ Enregistrement arrêté. Fichier CSV avec données validées disponible', 'success');
                    setTimeout(() => this.loadSessions(), 1000);
                }
            } else {
                this.showToast('❌ Erreur enregistrement: ' + (result.error || 'Erreur inconnue'), 'error');
            }

            this.updateConnectionStatus(this.AppState.isConnected, this.AppState.isRecording, this.AppState.isMonitoring);
        })
        .catch(error => {
            console.error('❌ Erreur enregistrement:', error);
            this.showToast('❌ Erreur d\'enregistrement: ' + error.message, 'error');
        });
    }
};

Neurosity.downloadData = function() {
    this.showToast('📥 Recherche de la dernière session validée...', 'info');

    fetch('/api/neurosity/sessions')
    .then(response => response.json())
    .then(data => {
        if (data.sessions && data.sessions.length > 0) {
            const latestSession = data.sessions[0];
            const link = document.createElement('a');
            link.href = `/api/neurosity/download/${latestSession}`;
            link.download = latestSession;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            this.showToast(`📊 Téléchargement de ${latestSession} (données biologiques validées)`, 'success');
        } else {
            this.showToast('📝 Aucune session disponible. Démarrez un enregistrement d\'abord.', 'warning');
        }
    })
    .catch(error => {
        console.error('❌ Erreur téléchargement:', error);
        this.showToast('❌ Erreur de téléchargement: ' + error.message, 'error');
    });
};

Neurosity.downloadSession = function(filename) {
    const link = document.createElement('a');
    link.href = `/api/neurosity/download/${filename}`;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    this.showToast(`📊 Téléchargement de ${filename} (données validées)`, 'success');
};

// ===============================================
// GESTION DES DONNÉES EN TEMPS RÉEL
// ===============================================

Neurosity.handleCalmData = function(data) {
    if (!this.AppState.isConnected) return;

    this.AppState.lastDataTime = new Date();
    this.updateCircularProgress('calm', data.calm, data.timestamp);
    this.flashDataIndicator('calm');
};

Neurosity.handleFocusData = function(data) {
    if (!this.AppState.isConnected) return;

    this.AppState.lastDataTime = new Date();
    this.updateCircularProgress('focus', data.focus, data.timestamp);
    this.flashDataIndicator('focus');
};

Neurosity.handleBrainwavesData = function(data) {
    if (!this.AppState.isConnected || !this.AppState.chart) return;

    this.AppState.lastDataTime = new Date();

    const chart = this.AppState.chart;

    const avgData = {
        delta: this.calculateAverage(data.delta),
        theta: this.calculateAverage(data.theta),
        alpha: this.calculateAverage(data.alpha),
        beta: this.calculateAverage(data.beta),
        gamma: this.calculateAverage(data.gamma)
    };

    chart.data.datasets[0].data = [
        avgData.delta,
        avgData.theta,
        avgData.alpha,
        avgData.beta,
        avgData.gamma
    ];

    chart.update('none');

    const timestampElement = document.getElementById('brainwavesTimestamp');
    if (timestampElement) {
        timestampElement.textContent = 'Dernière validation: ' + this.formatTimestamp(data.timestamp);
    }

    this.flashDataIndicator('brainwaves');

    if (this.AppState.debugMode) {
        console.log('📊 Ondes cérébrales (μV²/Hz):', {
            delta: avgData.delta.toFixed(4),
            theta: avgData.theta.toFixed(4),
            alpha: avgData.alpha.toFixed(4),
            beta: avgData.beta.toFixed(4),
            gamma: avgData.gamma.toFixed(4)
        });
    }
};

Neurosity.flashDataIndicator = function(type) {
    const elements = {
        'calm': document.querySelector('.metric-card:nth-child(1)'),
        'focus': document.querySelector('.metric-card:nth-child(2)'),
        'brainwaves': document.querySelector('.chart-card')
    };

    const element = elements[type];
    if (element) {
        element.style.boxShadow = '0 0 20px rgba(139, 92, 246, 0.4)';
        setTimeout(() => {
            element.style.boxShadow = '';
        }, 300);
    }
};

Neurosity.updateCircularProgress = function(type, value, timestamp) {
    const circumference = 2 * Math.PI * 65;
    const progress = Math.min(Math.max(value, 0), 100);
    const offset = circumference - (progress / 100) * circumference;

    const progressElement = document.getElementById(`${type}Progress`);
    const valueElement = document.getElementById(`${type}Value`);
    const timestampElement = document.getElementById(`${type}Timestamp`);

    if (progressElement) {
        progressElement.style.strokeDasharray = circumference;
        progressElement.style.strokeDashoffset = offset;
    }

    if (valueElement) {
        valueElement.textContent = Math.round(progress) + '%';
    }

    if (timestampElement) {
        timestampElement.textContent = this.formatTimestamp(timestamp) + ' ✓';
    }
};

// ===============================================
// GESTION DES SESSIONS OPTIMISÉE
// ===============================================

Neurosity.loadSessions = function() {
    return fetch('/api/neurosity/sessions')
    .then(response => response.json())
    .then(data => {
        this.displaySessionsOptimized(data.sessions || []);
        return Promise.resolve();
    })
    .catch(error => {
        console.error('❌ Erreur chargement sessions:', error);
        const sessionsList = document.getElementById('sessionsList');
        if (sessionsList) {
            sessionsList.innerHTML = '<p style="color: #ef4444;">Erreur de chargement des sessions</p>';
        }
        return Promise.reject(error);
    });
};

Neurosity.displaySessionsOptimized = function(sessions) {
    const sessionsList = document.getElementById('sessionsList');
    if (!sessionsList) return;

    this.SessionsManager.allSessions = [...sessions];
    this.SessionsManager.currentPage = 0;
    this.SessionsManager.visibleSessions = [];

    const useVirtualization = sessions.length > 100;
    this.SessionsManager.isVirtualizationEnabled = useVirtualization;

    if (sessions.length === 0) {
        sessionsList.innerHTML = `
            <div class="sessions-empty">
                Aucune session validée enregistrée
                <div style="font-size: 0.75rem; margin-top: 0.5rem; opacity: 0.7;">
                    Connectez votre casque avec détection pour créer une session
                </div>
            </div>
        `;
        sessionsList.className = 'sessions-empty';
        this.updateSessionsStats([]);
        return;
    }

    sessionsList.className = '';
    sessionsList.innerHTML = '';

    if (useVirtualization) {
        console.log(`📊 Virtualisation activée pour ${sessions.length} sessions`);

        const initialSessions = sessions.slice(0, this.SessionsManager.itemsPerPage);
        this.SessionsManager.visibleSessions = [...initialSessions];

        const fragment = document.createDocumentFragment();
        initialSessions.forEach((session, index) => {
            const sessionElement = this.SessionsManager.createSessionElement(session, index);
            fragment.appendChild(sessionElement);
        });
        sessionsList.appendChild(fragment);

        if (this.SessionsManager.hasMoreSessions()) {
            const loadMoreIndicator = document.createElement('div');
            loadMoreIndicator.className = 'load-more-indicator';
            loadMoreIndicator.innerHTML = `
                <div style="text-align: center; padding: 1rem; color: #8b5cf6; font-size: 0.875rem;">
                    📄 ${sessions.length - this.SessionsManager.itemsPerPage} sessions supplémentaires disponibles
                    <br>
                    <small style="opacity: 0.7;">Faites défiler pour charger automatiquement</small>
                </div>
            `;
            sessionsList.appendChild(loadMoreIndicator);
        }

        this.showToast(
            `📊 ${initialSessions.length}/${sessions.length} sessions affichées (chargement progressif activé)`,
            'info',
            4000
        );
    } else {
        console.log(`📊 Affichage normal pour ${sessions.length} sessions`);

        const fragment = document.createDocumentFragment();
        sessions.forEach((session, index) => {
            const sessionElement = this.SessionsManager.createSessionElement(session, index);
            fragment.appendChild(sessionElement);
        });
        sessionsList.appendChild(fragment);

        if (sessions.length > 0) {
            this.showToast(
                `📁 ${sessions.length} session(s) validée(s) trouvée(s)`,
                'info',
                2000
            );
        }
    }

    this.updateSessionsStats(sessions);

    setTimeout(() => {
        this.SessionsManager.updateScrollIndicators();
    }, 100);
};

Neurosity.updateSessionsStats = function(sessions) {
    const totalSessionsEl = document.getElementById('totalSessions');
    const totalSizeEl = document.getElementById('totalSize');
    const sessionsCounterEl = document.getElementById('sessionsCounter');

    if (totalSessionsEl) {
        totalSessionsEl.textContent = sessions.length;
    }

    if (sessionsCounterEl) {
        const displayText = sessions.length === 0
            ? 'Aucune session'
            : `${sessions.length} session${sessions.length > 1 ? 's' : ''}`;
        sessionsCounterEl.textContent = displayText;
    }

    if (totalSizeEl) {
        let estimatedSize;
        if (sessions.length === 0) {
            estimatedSize = 0;
        } else if (sessions.length < 10) {
            estimatedSize = sessions.length * 0.3;
        } else if (sessions.length < 100) {
            estimatedSize = sessions.length * 0.5;
        } else {
            estimatedSize = sessions.length * 0.4;
        }

        if (estimatedSize < 1) {
            totalSizeEl.textContent = (estimatedSize * 1000).toFixed(0) + ' KB';
        } else {
            totalSizeEl.textContent = estimatedSize.toFixed(1) + ' MB';
        }
    }

    [totalSessionsEl, totalSizeEl].forEach(el => {
        if (el) {
            el.style.transform = 'scale(1.1)';
            el.style.transition = 'transform 0.2s ease';
            setTimeout(() => {
                el.style.transform = 'scale(1)';
            }, 200);
        }
    });
};

Neurosity.refreshSessions = function() {
    const refreshBtn = document.querySelector('.sessions-refresh-btn');
    if (!refreshBtn) return;

    const originalText = refreshBtn.innerHTML;
    refreshBtn.innerHTML = '<span style="animation: spin 1s linear infinite;">🔄</span> <span class="btn-text">Actualisation...</span>';
    refreshBtn.disabled = true;

    this.showToast('🔄 Actualisation des sessions...', 'info', 2000);

    this.loadSessions().finally(() => {
        setTimeout(() => {
            refreshBtn.innerHTML = originalText;
            refreshBtn.disabled = false;
        }, 1000);
    });
};

// ===============================================
// FONCTIONS UTILITAIRES DU MODULE
// ===============================================

Neurosity.updateConnectionStatus = function(connected, recording, monitoring) {
    this.AppState.isConnected = connected;
    this.AppState.isRecording = recording;
    this.AppState.isMonitoring = monitoring;

    const recordBtn = document.getElementById('recordBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const connectionStatus = document.getElementById('connectionStatus');
    const connectionText = document.getElementById('connectionText');
    const recordingStatus = document.getElementById('recordingStatus');

    this.updateConnectionButton(connected);

    if (connectionStatus && connectionText) {
        if (connected) {
            connectionStatus.className = 'status-dot status-connected';
            connectionText.textContent = 'Connecté (Validé)';
        } else {
            connectionStatus.className = 'status-dot status-disconnected';
            connectionText.textContent = 'Déconnecté';
        }
    }

    if (recordBtn) {
        recordBtn.disabled = !connected;

        if (recording) {
            recordBtn.innerHTML = '<span>⏹️</span><span class="btn-text"> Arrêter</span>';
            recordBtn.className = 'btn btn-danger';
        } else {
            recordBtn.innerHTML = '<span>⏺️</span><span class="btn-text"> Enregistrer</span>';
            recordBtn.className = 'btn btn-success';
        }
    }

    if (downloadBtn) {
        downloadBtn.disabled = !connected;
    }

    if (recordingStatus) {
        if (recording) {
            recordingStatus.style.display = 'flex';
        } else {
            recordingStatus.style.display = 'none';
        }
    }

    console.log(`🔄 Statut Neurosity mis à jour: Connected=${connected}, Recording=${recording}, Monitoring=${monitoring}`);
};

Neurosity.updateDeviceStatus = function(deviceStatus) {
    this.AppState.deviceStatus = deviceStatus;

    const deviceIndicator = document.getElementById('deviceStatusIndicator');
    const deviceDot = document.getElementById('deviceStatusDot');
    const deviceText = document.getElementById('deviceStatusText');

    if (deviceIndicator && deviceDot && deviceText) {
        if (deviceStatus.online) {
            deviceIndicator.style.display = 'flex';
            deviceDot.className = 'status-dot status-connected';

            let statusText = 'Crown';

            if (deviceStatus.validation === 'biological_data_confirmed_v2') {
                statusText += ' ✓';
            }

            if (deviceStatus.battery && deviceStatus.battery !== 'unknown') {
                statusText += ` ${deviceStatus.battery}%`;
            }

            if (deviceStatus.signal && deviceStatus.signal !== 'unknown') {
                const signalEmoji = {
                    'excellent': '🟢',
                    'good': '🟡',
                    'poor': '🟠',
                    'biological_data_confirmed': '🔬'
                }[deviceStatus.signal] || '🔴';
                statusText += ` ${signalEmoji}`;
            }

            deviceText.textContent = statusText;
        } else {
            deviceIndicator.style.display = 'none';
        }
    }

    this.updateSystemStatus(this.AppState.isConnected, this.AppState.isMonitoring, deviceStatus);
};

Neurosity.updateSystemStatus = function(connected, monitoring, deviceStatus) {
    const elements = {
        connection: document.getElementById('systemConnectionStatus'),
        monitoring: document.getElementById('systemMonitoringStatus'),
        signal: document.getElementById('systemSignalQuality'),
        battery: document.getElementById('systemBattery')
    };

    if (!elements.connection) return;

    Object.values(elements).forEach(el => {
        if (el) {
            el.style.transform = 'scale(0.95)';
            el.style.opacity = '0.7';
        }
    });

    setTimeout(() => {
        if (elements.connection) {
            elements.connection.textContent = connected ? '✅ Connecté (Validé)' : '❌ Déconnecté';
            elements.connection.style.background = connected ?
                'rgba(139, 92, 246, 0.1)' : 'rgba(239, 68, 68, 0.1)';
            elements.connection.style.color = connected ? '#8b5cf6' : '#dc2626';
            elements.connection.style.borderColor = connected ?
                'rgba(139, 92, 246, 0.3)' : 'rgba(239, 68, 68, 0.3)';
        }

        if (elements.monitoring) {
            elements.monitoring.textContent = monitoring ? '🎯 Actif (Validé)' : '⏹️ Arrêté';
            elements.monitoring.style.background = monitoring ?
                'rgba(139, 92, 246, 0.1)' : 'rgba(148, 163, 184, 0.1)';
            elements.monitoring.style.color = monitoring ? '#8b5cf6' : '#64748b';
            elements.monitoring.style.borderColor = monitoring ?
                'rgba(139, 92, 246, 0.3)' : 'rgba(148, 163, 184, 0.3)';
        }

        if (elements.signal && deviceStatus) {
            const signal = deviceStatus.signal || 'unknown';
            const validation = deviceStatus.validation || '';

            let signalText = 'Inconnu';
            let signalColor = '#dc2626';
            let signalBg = 'rgba(239, 68, 68, 0.1)';
            let signalEmoji = '🔴';

            if (validation === 'biological_data_confirmed_v2') {
                signalText = 'Données Biologiques ✓';
                signalColor = '#8b5cf6';
                signalBg = 'rgba(139, 92, 246, 0.1)';
                signalEmoji = '🔬';
            } else if (signal === 'excellent') {
                signalText = 'Excellent';
                signalColor = '#059669';
                signalBg = 'rgba(16, 185, 129, 0.1)';
                signalEmoji = '🟢';
            }

            elements.signal.textContent = `${signalEmoji} ${signalText}`;
            elements.signal.style.background = signalBg;
            elements.signal.style.color = signalColor;
            elements.signal.style.borderColor = signalColor + '40';
        }

        if (elements.battery && deviceStatus) {
            const battery = deviceStatus.battery || 0;
            let batteryConfig;

            if (battery > 60 || battery === 'unknown') {
                batteryConfig = { emoji: '🔋', color: '#059669', bg: 'rgba(16, 185, 129, 0.1)' };
            } else if (battery > 30) {
                batteryConfig = { emoji: '🪫', color: '#d97706', bg: 'rgba(245, 158, 11, 0.1)' };
            } else if (battery > 0) {
                batteryConfig = { emoji: '🔴', color: '#dc2626', bg: 'rgba(239, 68, 68, 0.1)' };
            } else {
                batteryConfig = { emoji: '❓', color: '#64748b', bg: 'rgba(148, 163, 184, 0.1)' };
            }

            const batteryText = battery === 'unknown' ? 'N/A' : `${battery}%`;
            elements.battery.textContent = `${batteryConfig.emoji} ${batteryText}`;
            elements.battery.style.background = batteryConfig.bg;
            elements.battery.style.color = batteryConfig.color;
            elements.battery.style.borderColor = batteryConfig.color + '40';
        }

        Object.values(elements).forEach(el => {
            if (el) {
                el.style.transform = 'scale(1)';
                el.style.opacity = '1';
                el.style.transition = 'all 0.3s ease';
            }
        });
    }, 150);
};

Neurosity.updateConnectionHealth = function(healthy) {
    const connectionStatus = document.getElementById('connectionStatus');
    if (connectionStatus && this.AppState.isConnected) {
        if (healthy) {
            connectionStatus.className = 'status-dot status-connected';
        } else {
            connectionStatus.className = 'status-dot status-recording';
        }
    }
};

Neurosity.updateMonitoringStatus = function(monitoring) {
    const charts = document.querySelectorAll('.chart-card');
    charts.forEach(chart => {
        if (monitoring) {
            chart.style.borderLeft = '4px solid #10b981';
            chart.style.boxShadow = '0 0 20px rgba(16, 185, 129, 0.1)';
        } else {
            chart.style.borderLeft = 'none';
            chart.style.boxShadow = '';
        }
    });
};

Neurosity.calculateAverage = function(array) {
    if (!array || array.length === 0) return 0;
    const validNumbers = array.filter(val => typeof val === 'number' && !isNaN(val));
    if (validNumbers.length === 0) return 0;
    return validNumbers.reduce((a, b) => a + b, 0) / validNumbers.length;
};

Neurosity.formatTimestamp = function(timestamp) {
    if (!timestamp) return '--';
    try {
        return new Date(timestamp).toLocaleString('fr-FR');
    } catch {
        return '--';
    }
};

// ===============================================
// GESTION DES ÉVÉNEMENTS ET RACCOURCIS
// ===============================================

// Gestionnaire de clavier pour le module
document.addEventListener('keydown', function(e) {
    // Vérifier si on est dans le module neurosity
    if (!document.querySelector('.neurosity-module')) return;

    if (e.ctrlKey || e.metaKey) {
        switch(e.key) {
            case 'k':
                e.preventDefault();
                if (Neurosity.AppState.isConnected) {
                    Neurosity.disconnectDevice();
                } else {
                    Neurosity.connectDevice();
                }
                break;
            case 'r':
                e.preventDefault();
                if (Neurosity.AppState.isConnected) {
                    Neurosity.toggleRecording();
                }
                break;
            case 'd':
                e.preventDefault();
                Neurosity.toggleDebugMode();
                break;
        }
    }

    // Recherche rapide dans les sessions
    if ((e.ctrlKey || e.metaKey) && e.key === 'f' && Neurosity.SessionsManager.allSessions.length > 0) {
        e.preventDefault();
        const searchTerm = prompt('🔍 Rechercher dans les sessions:', '');
        if (searchTerm !== null) {
            Neurosity.filterSessions(searchTerm);
        }
    }
});

Neurosity.toggleDebugMode = function() {
    this.AppState.debugMode = !this.AppState.debugMode;
    this.showToast(
        `🔧 Mode debug ${this.AppState.debugMode ? 'activé' : 'désactivé'}`,
        'info',
        2000
    );
    console.log(`Debug mode Neurosity: ${this.AppState.debugMode}`);
};

Neurosity.filterSessions = function(searchTerm) {
    if (!searchTerm || searchTerm.trim() === '') {
        this.displaySessionsOptimized(this.SessionsManager.allSessions);
        return;
    }

    const filtered = this.SessionsManager.allSessions.filter(session =>
        session.toLowerCase().includes(searchTerm.toLowerCase())
    );

    this.displaySessionsOptimized(filtered);

    this.showToast(
        `🔍 ${filtered.length} session(s) trouvée(s) pour "${searchTerm}"`,
        'info',
        3000
    );
};

// Gestion des erreurs globales du module
window.addEventListener('error', function(event) {
    if (document.querySelector('.neurosity-module')) {
        console.error('Erreur JavaScript Neurosity:', event.error);
        if (Neurosity.showToast) {
            Neurosity.showToast('❌ Erreur module Neurosity: ' + event.error.message, 'error');
        }
    }
});

// Confirmation avant fermeture si enregistrement en cours
window.addEventListener('beforeunload', function(event) {
    if (Neurosity.AppState.isRecording) {
        event.preventDefault();
        event.returnValue = 'Un enregistrement de données biologiques validées est en cours. Êtes-vous sûr de vouloir fermer ?';
        return event.returnValue;
    }
});

console.log('✅ Module JavaScript Neurosity EEG Crown chargé complètement avec Sessions Manager optimisé pour milliers de fichiers');

// Auto-initialisation si le module est déjà chargé
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (document.querySelector('.neurosity-module') && !Neurosity.isInitialized) {
            Neurosity.init();
            Neurosity.isInitialized = true;
        }
    });
} else {
    // DOM déjà chargé
    if (document.querySelector('.neurosity-module') && !Neurosity.isInitialized) {
        Neurosity.init();
        Neurosity.isInitialized = true;
    }
}