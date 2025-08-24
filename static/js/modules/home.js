/**
 * Module Home - Frontend pour la vue d'ensemble en temps réel
 * Version complète avec intégration Gazepoint et Thought Capture
 */

class HomeModule {
    constructor() {
        this.container = document.querySelector('.home-container');
        this.wsClient = null;
        this.isInitialized = false;

        // État local des appareils
        this.devicesState = {
            polar: { connected: false, devices: [] },
            neurosity: { connected: false },
            thermal: { connected: false },
            gazepoint: { connected: false },
            thoughtCapture: { ready: true, recording: false, paused: false }
        };

        // État de la collecte
        this.collectionState = {
            isCollecting: false,
            startTime: null,
            timerInterval: null
        };

        // Configuration du monitoring automatique
        this.autoStartMonitoring = true;

        // Graphiques Chart.js
        this.charts = {
            bpm: null,
            rr: null,
            brainwaves: null,
            thermal: null
        };

        // État des métriques
        this.neurosityState = {
            calm: 0,
            focus: 0,
            brainwaves: {
                delta: 0,
                theta: 0,
                alpha: 0,
                beta: 0,
                gamma: 0
            },
            battery: null,
            lastUpdate: null
        };

        // État des métriques Thermal
        this.thermalState = {
            temperatures: {},
            avg: 0,
            min: 0,
            max: 0,
            lastUpdate: null
        };

        // État des métriques Gazepoint
        this.gazepointState = {
            leftEye: {
                isOpen: true,
                pupilSize: 0,
                position: { x: 50, y: 50 }
            },
            rightEye: {
                isOpen: true,
                pupilSize: 0,
                position: { x: 50, y: 50 }
            },
            gazePosition: { x: 0.5, y: 0.5 },
            fixationDuration: 0,
            blinkRate: 0,
            pupilVariation: 0,
            lastUpdate: null
        };

        // État des métriques Thought Capture
        this.thoughtCaptureState = {
            recording: false,
            paused: false,
            recordingStartTime: null,
            recordingDuration: 0,
            audioLevel: 0,
            totalRecordings: 0,
            totalDuration: 0,
            totalSize: 0,
            waveformData: new Uint8Array(256),
            lastUpdate: null
        };

        // Points thermiques du visage
        this.thermalPoints = [
            'Nez', 'Bouche', 'Œil_Gauche', 'Œil_Droit',
            'Joue_Gauche', 'Joue_Droite', 'Front', 'Menton'
        ];

        // Configuration des graphiques
        this.maxDataPoints = 30;
        this.thermalDataBuffers = {};

        // Initialiser les buffers pour chaque point
        this.thermalPoints.forEach(point => {
            this.thermalDataBuffers[point] = [];
        });

        // Animation du coeur
        this.heartbeatAnimation = null;

        // Animation Gazepoint
        this.gazeTrail = [];
        this.gazeCanvas = null;
        this.gazeCtx = null;
        this.gazeAnimationFrame = null;

        // Animation Thought Capture
        this.audioCanvas = null;
        this.audioCtx = null;
        this.audioAnimationFrame = null;
        this.audioAnalyser = null;
        this.thoughtTimerInterval = null;

        // Timeout pour les indicateurs
        this.neurosityIndicatorTimeout = null;
        this.thermalIndicatorTimeout = null;
        this.gazepointIndicatorTimeout = null;
        this.thoughtCaptureIndicatorTimeout = null;

        logger.info('Module Home créé avec support Gazepoint et Thought Capture');
    }

    init() {
        if (this.isInitialized) {
            logger.warn('Module Home déjà initialisé');
            return;
        }

        logger.info('Initialisation du module Home...');

        try {
            // Initialiser l'interface
            this.setupUI();

            // Initialiser les graphiques
            this.initCharts();

            // Initialiser les visualisations Gazepoint
            this.initGazepointVisualization();

            // Initialiser les visualisations Thought Capture
            this.initThoughtCaptureVisualization();

            // Connecter au WebSocket
            this.connectWebSocket();

            // Configurer les listeners d'événements
            this.setupEventListeners();

            // Demander l'état initial des appareils
            setTimeout(() => {
                this.requestDevicesStatus();

                // S'abonner aux broadcasts si possible
                if (this.wsClient && this.wsClient.socket) {
                    this.wsClient.socket.emit('subscribe_to_broadcast', {
                        modules: ['polar', 'neurosity', 'thermal', 'gazepoint', 'thought_capture']
                    });
                    logger.info('Abonnement aux broadcasts demandé (incluant Gazepoint et Thought Capture)');
                }
            }, 500);

            // Marquer comme initialisé
            this.isInitialized = true;

            logger.info('Module Home initialisé avec succès');
        } catch (error) {
            logger.error('Erreur initialisation module Home:', error);
            this.showNotification('Erreur d\'initialisation', 'error');
        }
    }

    setupUI() {
        // Charger la préférence de monitoring automatique
        const savedPref = localStorage.getItem('home_auto_start_monitoring');
        if (savedPref !== null) {
            this.autoStartMonitoring = savedPref === 'true';
        }

        // Vérifier la présence du menu de configuration
        const configCheckbox = document.getElementById('dh-auto-start-checkbox');
        if (configCheckbox) {
            configCheckbox.checked = this.autoStartMonitoring;
        }

        // Mettre à jour l'interface initiale
        this.updateDeviceStatus('polar', false);
        this.updateDeviceStatus('neurosity', false);
        this.updateDeviceStatus('thermal', false);
        this.updateDeviceStatus('gazepoint', false);
        this.updateThoughtCaptureStatus('ready');

        // Masquer la bannière de connexion par défaut
        const banner = document.getElementById('dh-connection-banner');
        if (banner) {
            banner.style.display = 'none';
        }
    }

    connectWebSocket() {
        // Si WebSocketClient n'est pas disponible, on est en mode local
        if (typeof WebSocketClient === 'undefined') {
            logger.warn('Mode local: WebSocket non disponible');
            this.showNotification('Mode local - Données simulées', 'info');
            return;
        }

        try {
            // Utiliser l'instance globale du dashboard
            this.wsClient = window.dashboard?.wsClient;

            if (!this.wsClient) {
                logger.warn('WebSocket client non disponible via dashboard');
                return;
            }

            // Listeners WebSocket pour le module Home
            this.setupWebSocketListeners();

            logger.info('WebSocket configuré pour le module Home');
        } catch (error) {
            logger.error('Erreur connexion WebSocket:', error);
        }
    }

    setupWebSocketListeners() {
        if (!this.wsClient) return;

        // === Événements du module Home ===
        this.wsClient.on('dashboard_state', (data) => {
            this.handleDashboardState(data);
        });

        // Mises à jour des modules
        this.wsClient.on('polar_data_update', (data) => {
            this.handlePolarDataUpdate(data);
        });

        this.wsClient.on('neurosity_data_update', (data) => {
            this.handleNeurosityDataUpdate(data);
        });

        this.wsClient.on('thermal_data_update', (data) => {
            this.handleThermalDataUpdate(data);
        });

        this.wsClient.on('gazepoint_data_update', (data) => {
            this.handleGazepointDataUpdate(data);
        });

        this.wsClient.on('thought_capture_data_update', (data) => {
            this.handleThoughtCaptureDataUpdate(data);
        });

        // Connexion/Déconnexion d'appareils
        this.wsClient.on('device_connected', (data) => {
            this.handleDeviceConnected(data);
        });

        this.wsClient.on('device_disconnected', (data) => {
            this.handleDeviceDisconnected(data);
        });

        // Collecte
        this.wsClient.on('collection_started', (data) => {
            this.handleCollectionStarted(data);
        });

        this.wsClient.on('collection_stopped', (data) => {
            this.handleCollectionStopped(data);
        });

        // === Écouter directement les événements broadcast via socket ===
        if (this.wsClient.socket) {
            // Polar broadcasts
            this.wsClient.socket.on('polar_h10_data', (data) => {
                this.handlePolarBroadcast('h10', data);
            });

            this.wsClient.socket.on('polar_verity_data', (data) => {
                this.handlePolarBroadcast('verity', data);
            });

            this.wsClient.socket.on('polar_h10_connected', (data) => {
                this.handlePolarConnected('h10', data);
            });

            this.wsClient.socket.on('polar_verity_connected', (data) => {
                this.handlePolarConnected('verity', data);
            });

            this.wsClient.socket.on('polar_h10_disconnected', () => {
                this.handlePolarDisconnected('h10');
            });

            this.wsClient.socket.on('polar_verity_disconnected', () => {
                this.handlePolarDisconnected('verity');
            });

            // Neurosity broadcasts
            this.wsClient.socket.on('neurosity_calm_data', (data) => {
                this.handleNeurosityBroadcast('calm', data);
            });

            this.wsClient.socket.on('neurosity_focus_data', (data) => {
                this.handleNeurosityBroadcast('focus', data);
            });

            this.wsClient.socket.on('neurosity_brainwaves_data', (data) => {
                this.handleNeurosityBroadcast('brainwaves', data);
            });

            this.wsClient.socket.on('neurosity_battery_data', (data) => {
                this.handleNeurosityBroadcast('battery', data);
            });

            this.wsClient.socket.on('neurosity_connected', (data) => {
                this.updateDeviceStatus('neurosity', true);
                this.checkAutoStartMonitoring();
            });

            this.wsClient.socket.on('neurosity_disconnected', () => {
                this.updateDeviceStatus('neurosity', false);
                // Réinitialiser l'affichage
                this.updateCalmCircle(0);
                this.updateFocusCircle(0);
                this.updateBrainwavesChart({
                    delta: 0, theta: 0, alpha: 0, beta: 0, gamma: 0
                });
            });

            // Thermal broadcasts
            this.wsClient.socket.on('thermal_temperature_data', (data) => {
                this.handleThermalBroadcast(data);
            });

            this.wsClient.socket.on('capture_started', (data) => {
                this.updateDeviceStatus('thermal', true);
                this.checkAutoStartMonitoring();
            });

            this.wsClient.socket.on('capture_stopped', (data) => {
                this.updateDeviceStatus('thermal', false);
                this.resetThermalDisplay();
            });

            // GAZEPOINT broadcasts
            this.wsClient.socket.on('gazepoint_gaze_data', (data) => {
                this.handleGazepointBroadcast('gaze', data);
            });

            this.wsClient.socket.on('gazepoint_eye_data', (data) => {
                this.handleGazepointBroadcast('eye', data);
            });

            this.wsClient.socket.on('gazepoint_fixation_data', (data) => {
                this.handleGazepointBroadcast('fixation', data);
            });

            this.wsClient.socket.on('gazepoint_connected', (data) => {
                this.updateDeviceStatus('gazepoint', true);
                this.checkAutoStartMonitoring();
            });

            this.wsClient.socket.on('gazepoint_disconnected', () => {
                this.updateDeviceStatus('gazepoint', false);
                this.resetGazepointDisplay();
            });

            // THOUGHT CAPTURE broadcasts
            this.wsClient.socket.on('thought_capture_recording_started', (data) => {
                this.handleThoughtCaptureBroadcast('recording_started', data);
            });

            this.wsClient.socket.on('thought_capture_recording_stopped', (data) => {
                this.handleThoughtCaptureBroadcast('recording_stopped', data);
            });

            this.wsClient.socket.on('thought_capture_recording_paused', (data) => {
                this.handleThoughtCaptureBroadcast('recording_paused', data);
            });

            this.wsClient.socket.on('thought_capture_recording_resumed', (data) => {
                this.handleThoughtCaptureBroadcast('recording_resumed', data);
            });

            this.wsClient.socket.on('thought_capture_audio_level', (data) => {
                this.handleThoughtCaptureBroadcast('audio_level', data);
            });

            this.wsClient.socket.on('thought_capture_stats_update', (data) => {
                this.handleThoughtCaptureBroadcast('stats_update', data);
            });

            logger.info('Listeners broadcast configurés (incluant Gazepoint et Thought Capture)');
        }

        // Réponse au statut des appareils
        this.wsClient.on('devices_status', (data) => {
            this.handleDevicesStatus(data);
        });

        // Listener direct sur le socket pour devices_status aussi
        if (this.wsClient.socket) {
            this.wsClient.socket.on('devices_status', (data) => {
                this.handleDevicesStatus(data);
            });
        }
    }

    setupEventListeners() {
        // Bouton de collecte
        const collectBtn = document.getElementById('dh-collect-btn');
        if (collectBtn) {
            collectBtn.addEventListener('click', () => this.toggleCollection());
        }

        // Menu de configuration
        const configBtn = document.getElementById('dh-config-btn');
        const configDropdown = document.getElementById('dh-config-dropdown');
        if (configBtn && configDropdown) {
            configBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                configDropdown.style.display = configDropdown.style.display === 'none' ? 'block' : 'none';
            });

            // Fermer le menu en cliquant ailleurs
            document.addEventListener('click', () => {
                configDropdown.style.display = 'none';
            });
        }

        // Checkbox auto-start
        const autoStartCheckbox = document.getElementById('dh-auto-start-checkbox');
        if (autoStartCheckbox) {
            autoStartCheckbox.addEventListener('change', (e) => {
                this.autoStartMonitoring = e.target.checked;
                localStorage.setItem('home_auto_start_monitoring', this.autoStartMonitoring);
                logger.info(`Monitoring visuel automatique: ${this.autoStartMonitoring ? 'activé' : 'désactivé'}`);
            });
        }

        // Contrôles Thought Capture
        const thoughtRecord = document.getElementById('dh-thought-record');
        const thoughtPause = document.getElementById('dh-thought-pause');
        const thoughtStop = document.getElementById('dh-thought-stop');

        if (thoughtRecord) {
            thoughtRecord.addEventListener('click', () => this.toggleThoughtRecording());
        }

        if (thoughtPause) {
            thoughtPause.addEventListener('click', () => this.pauseThoughtRecording());
        }

        if (thoughtStop) {
            thoughtStop.addEventListener('click', () => this.stopThoughtRecording());
        }
    }

    // === INITIALISATION DES GRAPHIQUES ===

    initCharts() {
        // Vérifier si Chart.js est disponible
        if (typeof Chart === 'undefined') {
            logger.warn('Chart.js non disponible, graphiques désactivés');
            return;
        }

        // Configuration commune
        const commonOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            },
            scales: {
                x: { display: false },
                y: { display: false }
            },
            elements: {
                line: {
                    borderWidth: 2,
                    tension: 0.4
                },
                point: {
                    radius: 0
                }
            }
        };

        // Graphique BPM
        const bpmCanvas = document.getElementById('dh-bpm-chart');
        if (bpmCanvas) {
            this.charts.bpm = new Chart(bpmCanvas.getContext('2d'), {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        data: [],
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.1)'
                    }]
                },
                options: commonOptions
            });
        }

        // Graphique RR
        const rrCanvas = document.getElementById('dh-rr-chart');
        if (rrCanvas) {
            this.charts.rr = new Chart(rrCanvas.getContext('2d'), {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        data: [],
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139, 92, 246, 0.1)'
                    }]
                },
                options: commonOptions
            });
        }

        // Graphique des ondes cérébrales
        const brainwavesCanvas = document.getElementById('dh-brainwaves-chart');
        if (brainwavesCanvas) {
            this.charts.brainwaves = new Chart(brainwavesCanvas.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: ['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma'],
                    datasets: [{
                        data: [0, 0, 0, 0, 0],
                        backgroundColor: [
                            '#6366f1',  // Delta - Indigo
                            '#f59e0b',  // Theta - Amber
                            '#3b82f6',  // Alpha - Blue
                            '#10b981',  // Beta - Emerald
                            '#ec4899'   // Gamma - Pink
                        ],
                        borderColor: [
                            '#4f46e5',
                            '#d97706',
                            '#2563eb',
                            '#059669',
                            '#db2777'
                        ],
                        borderWidth: 1,
                        barThickness: 30
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: 'rgba(0, 0, 0, 0.8)',
                            callbacks: {
                                label: (context) => {
                                    return context.parsed.y.toFixed(2) + ' μV²/Hz';
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: {
                                font: { size: 11 },
                                color: '#64748b'
                            }
                        },
                        y: {
                            min: 0,
                            max: 15,
                            grid: {
                                color: 'rgba(0, 0, 0, 0.05)',
                                drawBorder: false
                            },
                            ticks: {
                                stepSize: 3,
                                font: { size: 10 },
                                color: '#94a3b8',
                                callback: (value) => value + ' μV²'
                            }
                        }
                    }
                }
            });
        }

        // Graphique Thermal (zone avec vagues)
        const thermalCanvas = document.getElementById('dh-thermal-chart');
        if (thermalCanvas) {
            // Créer les datasets avec effet de vague
            const datasets = this.thermalPoints.map((point, index) => {
                const colors = {
                    'Nez': { main: '#ef4444', light: 'rgba(239, 68, 68, 0.15)' },
                    'Bouche': { main: '#f59e0b', light: 'rgba(245, 158, 11, 0.15)' },
                    'Œil_Gauche': { main: '#10b981', light: 'rgba(16, 185, 129, 0.15)' },
                    'Œil_Droit': { main: '#3b82f6', light: 'rgba(59, 130, 246, 0.15)' },
                    'Joue_Gauche': { main: '#8b5cf6', light: 'rgba(139, 92, 246, 0.15)' },
                    'Joue_Droite': { main: '#ec4899', light: 'rgba(236, 72, 153, 0.15)' },
                    'Front': { main: '#14b8a6', light: 'rgba(20, 184, 166, 0.15)' },
                    'Menton': { main: '#f97316', light: 'rgba(249, 115, 22, 0.15)' }
                };

                return {
                    label: point,
                    data: [],
                    borderColor: colors[point].main,
                    backgroundColor: colors[point].light,
                    borderWidth: 2,
                    tension: 0.4, // Courbes douces
                    pointRadius: 0,
                    fill: 'origin', // Remplir jusqu'à l'origine
                    order: index // Ordre d'affichage
                };
            });

            this.charts.thermal = new Chart(thermalCanvas.getContext('2d'), {
                type: 'line',
                data: {
                    labels: [],
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: 'index',
                        intersect: false
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: 'rgba(0, 0, 0, 0.9)',
                            titleFont: { size: 11 },
                            bodyFont: { size: 10 },
                            padding: 8,
                            callbacks: {
                                title: () => 'Températures',
                                label: (context) => {
                                    return `${context.dataset.label}: ${context.parsed.y?.toFixed(1)}°C`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            display: false
                        },
                        y: {
                            min: 16,  // Commence à 16°C
                            max: 40,  // Jusqu'à 40°C
                            grid: {
                                color: 'rgba(0, 0, 0, 0.03)',
                                drawBorder: false
                            },
                            ticks: {
                                stepSize: 2, // Intervalles de 2°C
                                font: { size: 10 },
                                color: '#94a3b8',
                                callback: (value) => value + '°C'
                            }
                        }
                    },
                    animation: {
                        duration: 750,
                        easing: 'easeInOutQuart'
                    }
                }
            });
        }
    }

    // === INITIALISATION GAZEPOINT ===

    initGazepointVisualization() {
        // Récupérer le canvas pour la visualisation du regard
        this.gazeCanvas = document.getElementById('dh-gaze-canvas');
        if (this.gazeCanvas) {
            this.gazeCtx = this.gazeCanvas.getContext('2d');
            this.resizeGazeCanvas();

            // Adapter le canvas au redimensionnement
            window.addEventListener('resize', () => this.resizeGazeCanvas());

            // Démarrer l'animation du regard
            this.startGazeAnimation();
        }

        // Animation de clignement des yeux
        this.startEyeBlinkAnimation();
    }

    resizeGazeCanvas() {
        if (!this.gazeCanvas) return;

        const container = this.gazeCanvas.parentElement;
        this.gazeCanvas.width = container.clientWidth;
        this.gazeCanvas.height = container.clientHeight;
    }

    startGazeAnimation() {
        const animate = () => {
            if (!this.gazeCtx || !this.gazeCanvas) return;

            // Effacer le canvas avec un effet de fondu
            this.gazeCtx.fillStyle = 'rgba(255, 255, 255, 0.1)';
            this.gazeCtx.fillRect(0, 0, this.gazeCanvas.width, this.gazeCanvas.height);

            // Dessiner la grille de référence
            this.drawGazeGrid();

            // Dessiner la traînée du regard
            this.drawGazeTrail();

            this.gazeAnimationFrame = requestAnimationFrame(animate);
        };

        animate();
    }

    drawGazeGrid() {
        const ctx = this.gazeCtx;
        const width = this.gazeCanvas.width;
        const height = this.gazeCanvas.height;

        ctx.strokeStyle = 'rgba(0, 0, 0, 0.05)';
        ctx.lineWidth = 1;

        // Lignes verticales
        for (let x = 0; x <= width; x += width / 4) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, height);
            ctx.stroke();
        }

        // Lignes horizontales
        for (let y = 0; y <= height; y += height / 4) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(width, y);
            ctx.stroke();
        }
    }

    drawGazeTrail() {
        if (this.gazeTrail.length < 2) return;

        const ctx = this.gazeCtx;

        // Dessiner la traînée
        ctx.strokeStyle = 'rgba(102, 126, 234, 0.6)';
        ctx.lineWidth = 3;
        ctx.beginPath();

        for (let i = 1; i < this.gazeTrail.length; i++) {
            const prev = this.gazeTrail[i - 1];
            const curr = this.gazeTrail[i];

            const alpha = i / this.gazeTrail.length;
            ctx.globalAlpha = alpha * 0.6;

            if (i === 1) {
                ctx.moveTo(prev.x * this.gazeCanvas.width, prev.y * this.gazeCanvas.height);
            }
            ctx.lineTo(curr.x * this.gazeCanvas.width, curr.y * this.gazeCanvas.height);
        }

        ctx.stroke();
        ctx.globalAlpha = 1;

        // Limiter la taille de la traînée
        if (this.gazeTrail.length > 30) {
            this.gazeTrail.shift();
        }
    }

    startEyeBlinkAnimation() {
        // Ajouter l'animation de clignement aléatoire
        setInterval(() => {
            if (Math.random() < 0.3 && this.devicesState.gazepoint.connected) {
                this.simulateBlink();
            }
        }, 3000);
    }

    simulateBlink() {
        const leftLid = document.getElementById('dh-left-lid');
        const rightLid = document.getElementById('dh-right-lid');

        if (leftLid && rightLid) {
            leftLid.style.opacity = '1';
            rightLid.style.opacity = '1';

            setTimeout(() => {
                leftLid.style.opacity = '0';
                rightLid.style.opacity = '0';
            }, 150);
        }
    }

    // === INITIALISATION THOUGHT CAPTURE ===

    initThoughtCaptureVisualization() {
        // Récupérer le canvas pour la visualisation audio
        this.audioCanvas = document.getElementById('dh-audio-waveform');
        if (this.audioCanvas) {
            this.audioCtx = this.audioCanvas.getContext('2d');
            this.resizeAudioCanvas();

            // Adapter le canvas au redimensionnement
            window.addEventListener('resize', () => this.resizeAudioCanvas());

            // Démarrer l'animation audio
            this.startAudioAnimation();
        }

        // Initialiser les statistiques
        this.updateThoughtCaptureStats();
    }

    resizeAudioCanvas() {
        if (!this.audioCanvas) return;

        const container = this.audioCanvas.parentElement;
        this.audioCanvas.width = container.clientWidth;
        this.audioCanvas.height = container.clientHeight;
    }

    startAudioAnimation() {
        const animate = () => {
            if (!this.audioCtx || !this.audioCanvas) return;

            // Effacer le canvas
            this.audioCtx.fillStyle = '#f8fafc';
            this.audioCtx.fillRect(0, 0, this.audioCanvas.width, this.audioCanvas.height);

            // Dessiner la forme d'onde
            this.drawAudioWaveform();

            this.audioAnimationFrame = requestAnimationFrame(animate);
        };

        animate();
    }

    drawAudioWaveform() {
        const ctx = this.audioCtx;
        const width = this.audioCanvas.width;
        const height = this.audioCanvas.height;
        const data = this.thoughtCaptureState.waveformData;

        if (!data || data.length === 0) {
            // Dessiner une ligne plate si pas de données
            ctx.strokeStyle = '#e5e7eb';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(0, height / 2);
            ctx.lineTo(width, height / 2);
            ctx.stroke();
            return;
        }

        // Dessiner la forme d'onde
        const sliceWidth = width / data.length;
        let x = 0;

        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth = 2;
        ctx.beginPath();

        for (let i = 0; i < data.length; i++) {
            const v = data[i] / 128.0; // Normaliser 0-255 à 0-2
            const y = v * height / 2;

            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }

            x += sliceWidth;
        }

        ctx.stroke();

        // Dessiner les barres de fréquence si enregistrement actif
        if (this.thoughtCaptureState.recording) {
            ctx.fillStyle = 'rgba(245, 158, 11, 0.3)';
            x = 0;

            for (let i = 0; i < data.length; i += 4) {
                const barHeight = (data[i] / 255) * height * 0.8;

                ctx.fillRect(x, height - barHeight, sliceWidth * 3, barHeight);
                x += sliceWidth * 4;
            }
        }
    }

    // === GESTION DES ÉVÉNEMENTS THOUGHT CAPTURE ===

    handleThoughtCaptureBroadcast(eventType, data) {
        logger.info(`Données Thought Capture ${eventType} reçues:`, data);

        switch (eventType) {
            case 'recording_started':
                this.handleThoughtCaptureRecordingStarted(data);
                break;
            case 'recording_stopped':
                this.handleThoughtCaptureRecordingStopped(data);
                break;
            case 'recording_paused':
                this.handleThoughtCaptureRecordingPaused(data);
                break;
            case 'recording_resumed':
                this.handleThoughtCaptureRecordingResumed(data);
                break;
            case 'audio_level':
                this.handleThoughtCaptureAudioLevel(data);
                break;
            case 'stats_update':
                this.handleThoughtCaptureStatsUpdate(data);
                break;
        }

        // Afficher l'indicateur live si audio actif
        if (eventType === 'audio_level' && this.thoughtCaptureState.recording) {
            const indicator = document.getElementById('dh-audio-indicator');
            if (indicator) {
                indicator.style.display = 'flex';
                clearTimeout(this.thoughtCaptureIndicatorTimeout);
                this.thoughtCaptureIndicatorTimeout = setTimeout(() => {
                    indicator.style.display = 'none';
                }, 2000);
            }
        }
    }

    handleThoughtCaptureRecordingStarted(data) {
        this.thoughtCaptureState.recording = true;
        this.thoughtCaptureState.paused = false;
        this.thoughtCaptureState.recordingStartTime = new Date();

        // Mettre à jour l'interface
        this.updateThoughtCaptureStatus('recording');
        this.startThoughtTimer();

        // Mettre à jour les boutons
        const recordBtn = document.getElementById('dh-thought-record');
        const pauseBtn = document.getElementById('dh-thought-pause');
        const stopBtn = document.getElementById('dh-thought-stop');

        if (recordBtn) {
            recordBtn.classList.add('recording');
            recordBtn.querySelector('i').className = 'fas fa-microphone';
        }

        if (pauseBtn) pauseBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = false;

        this.showNotification('Enregistrement audio démarré', 'info');
    }

    handleThoughtCaptureRecordingStopped(data) {
        this.thoughtCaptureState.recording = false;
        this.thoughtCaptureState.paused = false;
        this.thoughtCaptureState.recordingStartTime = null;

        // Mettre à jour l'interface
        this.updateThoughtCaptureStatus('ready');
        this.stopThoughtTimer();

        // Mettre à jour les statistiques
        if (data.duration) {
            this.thoughtCaptureState.totalDuration += data.duration;
        }
        if (data.size) {
            this.thoughtCaptureState.totalSize += data.size;
        }
        this.thoughtCaptureState.totalRecordings++;

        this.updateThoughtCaptureStats();

        // Réinitialiser les boutons
        const recordBtn = document.getElementById('dh-thought-record');
        const pauseBtn = document.getElementById('dh-thought-pause');
        const stopBtn = document.getElementById('dh-thought-stop');

        if (recordBtn) {
            recordBtn.classList.remove('recording');
            recordBtn.querySelector('i').className = 'fas fa-microphone';
        }

        if (pauseBtn) {
            pauseBtn.disabled = true;
            pauseBtn.classList.remove('paused');
        }
        if (stopBtn) stopBtn.disabled = true;

        // Réinitialiser la forme d'onde
        this.thoughtCaptureState.waveformData = new Uint8Array(256);

        this.showNotification('Enregistrement audio terminé', 'success');
    }

    handleThoughtCaptureRecordingPaused(data) {
        this.thoughtCaptureState.paused = true;
        this.updateThoughtCaptureStatus('paused');

        const pauseBtn = document.getElementById('dh-thought-pause');
        if (pauseBtn) {
            pauseBtn.classList.add('paused');
            pauseBtn.querySelector('i').className = 'fas fa-play';
        }
    }

    handleThoughtCaptureRecordingResumed(data) {
        this.thoughtCaptureState.paused = false;
        this.updateThoughtCaptureStatus('recording');

        const pauseBtn = document.getElementById('dh-thought-pause');
        if (pauseBtn) {
            pauseBtn.classList.remove('paused');
            pauseBtn.querySelector('i').className = 'fas fa-pause';
        }
    }

    handleThoughtCaptureAudioLevel(data) {
        // Mettre à jour le niveau audio
        if (data.level !== undefined) {
            this.thoughtCaptureState.audioLevel = data.level;
            this.updateAudioLevel(data.level);
        }

        // Mettre à jour la forme d'onde
        if (data.waveform && Array.isArray(data.waveform)) {
            this.thoughtCaptureState.waveformData = new Uint8Array(data.waveform);
        }

        // Mettre à jour l'affichage des dB
        if (data.level !== undefined) {
            const dbLevel = this.calculateDbLevel(data.level);
            this.updateElement('dh-audio-db', `${dbLevel} dB`);
        }
    }

    handleThoughtCaptureStatsUpdate(data) {
        if (data.total_recordings !== undefined) {
            this.thoughtCaptureState.totalRecordings = data.total_recordings;
        }
        if (data.total_duration !== undefined) {
            this.thoughtCaptureState.totalDuration = data.total_duration;
        }
        if (data.total_size !== undefined) {
            this.thoughtCaptureState.totalSize = data.total_size;
        }

        this.updateThoughtCaptureStats();
    }

    handleThoughtCaptureDataUpdate(data) {
        logger.info('Mise à jour Thought Capture reçue:', data);

        // Traiter selon le type de mise à jour
        if (data.update_type === 'audio_level') {
            this.handleThoughtCaptureAudioLevel(data.data);
        } else if (data.update_type === 'stats') {
            this.handleThoughtCaptureStatsUpdate(data.data);
        }

        // Mettre à jour l'état si fourni
        if (data.state) {
            this.thoughtCaptureState.recording = data.state.recording;
            this.thoughtCaptureState.paused = data.state.paused;

            if (data.state.recording) {
                this.updateThoughtCaptureStatus(data.state.paused ? 'paused' : 'recording');
            } else {
                this.updateThoughtCaptureStatus('ready');
            }
        }
    }

    updateThoughtCaptureStatus(status) {
        const statusElement = document.getElementById('dh-thought-capture-status');
        if (!statusElement) return;

        const indicator = statusElement.querySelector('.device-indicator');
        const text = statusElement.querySelector('.status-text');

        if (indicator) {
            indicator.className = 'device-indicator';
            switch (status) {
                case 'recording':
                    indicator.classList.add('online');
                    break;
                case 'paused':
                    indicator.classList.add('online');
                    break;
                case 'ready':
                default:
                    indicator.classList.add('offline');
                    break;
            }
        }

        if (text) {
            switch (status) {
                case 'recording':
                    text.textContent = 'Enregistrement...';
                    break;
                case 'paused':
                    text.textContent = 'En pause';
                    break;
                case 'ready':
                default:
                    text.textContent = 'Prêt';
                    break;
            }
        }

        // Gérer le timer d'enregistrement
        const timer = document.getElementById('dh-thought-timer');
        if (timer) {
            timer.style.display = (status === 'recording' || status === 'paused') ? 'flex' : 'none';
        }
    }

    updateAudioLevel(level) {
        const levelBar = document.getElementById('dh-audio-level');
        if (levelBar) {
            // Normaliser le niveau (0-100)
            const normalizedLevel = Math.min(100, Math.max(0, level));
            levelBar.style.width = `${normalizedLevel}%`;

            // Changer la couleur selon le niveau
            if (normalizedLevel < 30) {
                levelBar.style.background = 'linear-gradient(to right, #10b981, #10b981)';
            } else if (normalizedLevel < 70) {
                levelBar.style.background = 'linear-gradient(to right, #10b981, #f59e0b)';
            } else {
                levelBar.style.background = 'linear-gradient(to right, #10b981, #f59e0b, #ef4444)';
            }
        }
    }

    calculateDbLevel(level) {
        if (level <= 0) return '-∞';
        // Convertir le niveau linéaire en dB
        const db = 20 * Math.log10(level / 100);
        return db.toFixed(1);
    }

    updateThoughtCaptureStats() {
        // Total des enregistrements
        this.updateElement('dh-total-recordings', this.thoughtCaptureState.totalRecordings);

        // Durée totale formatée
        const totalDuration = this.formatDuration(this.thoughtCaptureState.totalDuration);
        this.updateElement('dh-total-duration', totalDuration);

        // Taille totale formatée
        const totalSize = this.formatFileSize(this.thoughtCaptureState.totalSize);
        this.updateElement('dh-total-size', totalSize);
    }

    startThoughtTimer() {
        if (this.thoughtTimerInterval) return;

        const updateTimer = () => {
            if (!this.thoughtCaptureState.recordingStartTime) return;

            const elapsed = Math.floor((new Date() - this.thoughtCaptureState.recordingStartTime) / 1000);
            const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
            const seconds = (elapsed % 60).toString().padStart(2, '0');

            const timerText = document.querySelector('#dh-thought-timer .timer-text');
            if (timerText) {
                timerText.textContent = `${minutes}:${seconds}`;
            }
        };

        updateTimer(); // Mise à jour immédiate
        this.thoughtTimerInterval = setInterval(updateTimer, 1000);
    }

    stopThoughtTimer() {
        if (this.thoughtTimerInterval) {
            clearInterval(this.thoughtTimerInterval);
            this.thoughtTimerInterval = null;
        }

        const timerText = document.querySelector('#dh-thought-timer .timer-text');
        if (timerText) {
            timerText.textContent = '00:00';
        }
    }

    toggleThoughtRecording() {
        if (!this.wsClient || !this.wsClient.socket) {
            this.showNotification('WebSocket non connecté', 'error');
            return;
        }

        if (this.thoughtCaptureState.recording) {
            // Si déjà en cours, ne rien faire (utiliser stop pour arrêter)
            return;
        }

        // Émettre l'événement de démarrage
        this.wsClient.socket.emit('thought_capture_start_recording', {});
    }

    pauseThoughtRecording() {
        if (!this.wsClient || !this.wsClient.socket) return;

        const event = this.thoughtCaptureState.paused ?
            'thought_capture_resume_recording' :
            'thought_capture_pause_recording';

        this.wsClient.socket.emit(event, {});
    }

    stopThoughtRecording() {
        if (!this.wsClient || !this.wsClient.socket) return;

        this.wsClient.socket.emit('thought_capture_stop_recording', {});
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 MB';
        const mb = bytes / (1024 * 1024);
        return mb.toFixed(1) + ' MB';
    }

    // === GESTION DES ÉVÉNEMENTS GAZEPOINT (existant) ===

    handleGazepointBroadcast(dataType, data) {
        logger.info(`Données Gazepoint ${dataType} reçues:`, data);

        switch (dataType) {
            case 'gaze':
                this.handleGazeData(data);
                break;
            case 'eye':
                this.handleEyeData(data);
                break;
            case 'fixation':
                this.handleFixationData(data);
                break;
        }

        // Afficher l'indicateur live
        const indicator = document.getElementById('dh-gaze-indicator');
        if (indicator) {
            indicator.style.display = 'flex';
            clearTimeout(this.gazepointIndicatorTimeout);
            this.gazepointIndicatorTimeout = setTimeout(() => {
                indicator.style.display = 'none';
            }, 2000);
        }
    }

    handleGazeData(data) {
        if (!data || !data.gaze_data) return;

        const gazeData = data.gaze_data;

        // Mettre à jour la position du regard
        if (gazeData.FPOGX !== undefined && gazeData.FPOGY !== undefined) {
            const x = parseFloat(gazeData.FPOGX);
            const y = parseFloat(gazeData.FPOGY);

            if (!isNaN(x) && !isNaN(y)) {
                this.gazepointState.gazePosition = { x, y };
                this.updateGazePosition(x, y);

                // Ajouter à la traînée
                this.gazeTrail.push({ x, y, timestamp: Date.now() });
            }
        }

        // Mettre à jour les coordonnées affichées
        this.updateElement('dh-gaze-x', (this.gazepointState.gazePosition.x * 100).toFixed(1) + '%');
        this.updateElement('dh-gaze-y', (this.gazepointState.gazePosition.y * 100).toFixed(1) + '%');
    }

    handleEyeData(data) {
        if (!data || !data.eye_data) return;

        const eyeData = data.eye_data;

        // État des yeux (ouvert/fermé)
        if (eyeData.LEYEOPENESS !== undefined) {
            this.gazepointState.leftEye.isOpen = eyeData.LEYEOPENESS > 0.5;
            this.updateEyeState('left', this.gazepointState.leftEye.isOpen);
        }

        if (eyeData.REYEOPENESS !== undefined) {
            this.gazepointState.rightEye.isOpen = eyeData.REYEOPENESS > 0.5;
            this.updateEyeState('right', this.gazepointState.rightEye.isOpen);
        }

        // Taille des pupilles
        if (eyeData.LPUPILD !== undefined && eyeData.RPUPILD !== undefined) {
            const leftPupil = parseFloat(eyeData.LPUPILD);
            const rightPupil = parseFloat(eyeData.RPUPILD);

            if (!isNaN(leftPupil) && !isNaN(rightPupil)) {
                this.gazepointState.leftEye.pupilSize = leftPupil;
                this.gazepointState.rightEye.pupilSize = rightPupil;

                const avgPupil = (leftPupil + rightPupil) / 2;
                this.updatePupilSize(avgPupil);

                // Calculer la variation
                const basePupilSize = 4.0; // Taille de base en mm
                const variation = ((avgPupil - basePupilSize) / basePupilSize) * 100;
                this.gazepointState.pupilVariation = variation;
                this.updateElement('dh-pupil-variation', variation.toFixed(1) + '%');
            }
        }

        // Position des yeux
        if (eyeData.LEYEGAZEX !== undefined && eyeData.LEYEGAZEY !== undefined) {
            const x = parseFloat(eyeData.LEYEGAZEX);
            const y = parseFloat(eyeData.LEYEGAZEY);
            if (!isNaN(x) && !isNaN(y)) {
                this.updateEyePosition('left', x, y);
            }
        }

        if (eyeData.REYEGAZEX !== undefined && eyeData.REYEGAZEY !== undefined) {
            const x = parseFloat(eyeData.REYEGAZEX);
            const y = parseFloat(eyeData.REYEGAZEY);
            if (!isNaN(x) && !isNaN(y)) {
                this.updateEyePosition('right', x, y);
            }
        }
    }

    handleFixationData(data) {
        if (!data || !data.fixation_data) return;

        const fixationData = data.fixation_data;

        // Durée de fixation
        if (fixationData.FPOGD !== undefined) {
            const duration = parseFloat(fixationData.FPOGD);
            if (!isNaN(duration)) {
                this.gazepointState.fixationDuration = duration;
                this.updateElement('dh-fixation-time', Math.round(duration) + ' ms');
            }
        }
    }

    updateGazePosition(x, y) {
        const gazePoint = document.getElementById('dh-gaze-point');
        if (gazePoint) {
            gazePoint.style.left = (x * 100) + '%';
            gazePoint.style.top = (y * 100) + '%';
            gazePoint.classList.add('active');
        }
    }

    updateEyeState(eye, isOpen) {
        const lidId = eye === 'left' ? 'dh-left-lid' : 'dh-right-lid';
        const lid = document.getElementById(lidId);

        if (lid) {
            lid.style.opacity = isOpen ? '0' : '1';
        }
    }

    updateEyePosition(eye, x, y) {
        const pupilId = eye === 'left' ? 'dh-left-pupil' : 'dh-right-pupil';
        const pupil = document.getElementById(pupilId);

        if (pupil) {
            // Convertir les coordonnées du regard en position de l'iris
            const centerX = 50;
            const centerY = 50;
            const maxOffset = 12; // Limite de mouvement de l'iris

            const offsetX = (x - 0.5) * maxOffset;
            const offsetY = (y - 0.5) * maxOffset;

            pupil.setAttribute('cx', centerX + offsetX);
            pupil.setAttribute('cy', centerY + offsetY);
        }
    }

    updatePupilSize(avgSize) {
        // Mettre à jour l'affichage de la taille moyenne
        this.updateElement('dh-pupil-size', avgSize.toFixed(1) + ' mm');

        // Ajuster visuellement la taille des pupilles
        const leftPupil = document.getElementById('dh-left-pupil');
        const rightPupil = document.getElementById('dh-right-pupil');

        if (leftPupil && rightPupil) {
            // Mapper la taille réelle (3-7mm) sur une échelle visuelle (6-12)
            const visualSize = 6 + ((avgSize - 3) / 4) * 6;

            leftPupil.setAttribute('r', visualSize);
            rightPupil.setAttribute('r', visualSize);
        }
    }

    resetGazepointDisplay() {
        // Réinitialiser l'état des yeux
        this.updateEyeState('left', true);
        this.updateEyeState('right', true);

        // Réinitialiser les positions
        this.updateEyePosition('left', 0.5, 0.5);
        this.updateEyePosition('right', 0.5, 0.5);

        // Réinitialiser les métriques
        this.updateElement('dh-pupil-size', '-- mm');
        this.updateElement('dh-pupil-variation', '-- %');
        this.updateElement('dh-gaze-x', '--');
        this.updateElement('dh-gaze-y', '--');
        this.updateElement('dh-fixation-time', '-- ms');

        // Masquer le point de regard
        const gazePoint = document.getElementById('dh-gaze-point');
        if (gazePoint) {
            gazePoint.classList.remove('active');
        }

        // Vider la traînée
        this.gazeTrail = [];

        // Effacer le canvas
        if (this.gazeCtx && this.gazeCanvas) {
            this.gazeCtx.clearRect(0, 0, this.gazeCanvas.width, this.gazeCanvas.height);
        }
    }

    handleGazepointDataUpdate(data) {
        logger.info('Mise à jour Gazepoint reçue:', data);

        // Traiter selon le type de données
        if (data.data_type === 'gaze') {
            this.handleGazeData(data);
        } else if (data.data_type === 'eye') {
            this.handleEyeData(data);
        } else if (data.data_type === 'fixation') {
            this.handleFixationData(data);
        }
    }

    // === GESTION DES ÉVÉNEMENTS THERMAL (existant) ===

    handleThermalBroadcast(data) {
        logger.info('Données thermiques reçues:', data);

        if (!data || !data.temperatures) return;

        // Mettre à jour l'état
        this.thermalState.temperatures = data.temperatures;
        this.thermalState.lastUpdate = new Date();

        // Mettre à jour l'affichage de la silhouette
        this.updateThermalFace(data.temperatures);

        // Ajouter les données aux buffers pour le graphique
        this.updateThermalChartData(data.temperatures);

        // Calculer et afficher les statistiques
        this.updateThermalStats(data.temperatures);

        // Afficher l'indicateur live
        const indicator = document.getElementById('dh-thermal-indicator');
        if (indicator) {
            indicator.style.display = 'flex';
            clearTimeout(this.thermalIndicatorTimeout);
            this.thermalIndicatorTimeout = setTimeout(() => {
                indicator.style.display = 'none';
            }, 2000);
        }
    }

    updateThermalFace(temperatures) {
        // Mapper les noms normalisés pour les IDs
        const idMapping = {
            'Nez': 'nez',
            'Bouche': 'bouche',
            'Œil_Gauche': 'oeil-gauche',
            'Œil_Droit': 'oeil-droit',
            'Joue_Gauche': 'joue-gauche',
            'Joue_Droite': 'joue-droite',
            'Front': 'front',
            'Menton': 'menton'
        };

        for (const [point, normalizedId] of Object.entries(idMapping)) {
            const temp = temperatures[point];
            if (temp === null || temp === undefined) continue;

            // Mettre à jour le point thermique
            const pointElement = document.getElementById(`dh-thermal-${normalizedId}`);
            if (pointElement) {
                // Déterminer la classe de couleur selon la température
                let colorClass = 'normal';
                if (temp < 25) {
                    colorClass = 'cool';
                } else if (temp < 32) {
                    colorClass = 'normal';
                } else if (temp < 36) {
                    colorClass = 'warm';
                } else {
                    colorClass = 'hot';
                }

                // Retirer les anciennes classes et ajouter la nouvelle
                pointElement.classList.remove('cool', 'normal', 'warm', 'hot');
                pointElement.classList.add(colorClass);
            }

            // Mettre à jour le label de température
            const wrapper = pointElement?.closest('.thermal-point-wrapper');
            const labelElement = wrapper?.querySelector('.thermal-label');
            if (labelElement) {
                labelElement.textContent = `${temp.toFixed(1)}°C`;
            }
        }
    }

    updateThermalChartData(temperatures) {
        if (!this.charts.thermal) return;

        // Ajouter un timestamp
        const timestamp = new Date().toLocaleTimeString('fr-FR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });

        // Limiter le nombre de labels
        if (this.charts.thermal.data.labels.length >= this.maxDataPoints) {
            this.charts.thermal.data.labels.shift();
        }
        this.charts.thermal.data.labels.push(timestamp);

        // Mettre à jour chaque dataset
        this.thermalPoints.forEach((point, index) => {
            const dataset = this.charts.thermal.data.datasets[index];
            const temp = temperatures[point];

            if (temp !== null && temp !== undefined) {
                // Ajouter au buffer
                if (!this.thermalDataBuffers[point]) {
                    this.thermalDataBuffers[point] = [];
                }

                this.thermalDataBuffers[point].push(temp);

                // Limiter la taille du buffer
                if (this.thermalDataBuffers[point].length > this.maxDataPoints) {
                    this.thermalDataBuffers[point].shift();
                }

                // Lisser les données pour créer un effet de vague
                const smoothedData = this.smoothData(this.thermalDataBuffers[point]);
                dataset.data = smoothedData;
            }
        });

        // Mettre à jour le graphique avec animation
        this.charts.thermal.update('active');
    }

    // Fonction pour lisser les données (créer l'effet vague)
    smoothData(data) {
        if (data.length < 3) return data;

        const smoothed = [];
        const windowSize = 3;

        for (let i = 0; i < data.length; i++) {
            let sum = 0;
            let count = 0;

            for (let j = Math.max(0, i - Math.floor(windowSize / 2));
                 j <= Math.min(data.length - 1, i + Math.floor(windowSize / 2));
                 j++) {
                sum += data[j];
                count++;
            }

            smoothed.push(sum / count);
        }

        return smoothed;
    }

    updateThermalStats(temperatures) {
        const temps = Object.values(temperatures).filter(t => t !== null && t !== undefined);

        if (temps.length === 0) {
            this.updateElement('dh-thermal-avg', '--°C');
            this.updateElement('dh-thermal-max', '--°C');
            this.updateElement('dh-thermal-min', '--°C');
            return;
        }

        const avg = temps.reduce((a, b) => a + b, 0) / temps.length;
        const max = Math.max(...temps);
        const min = Math.min(...temps);

        this.thermalState.avg = avg;
        this.thermalState.max = max;
        this.thermalState.min = min;

        this.updateElement('dh-thermal-avg', `${avg.toFixed(1)}°C`);
        this.updateElement('dh-thermal-max', `${max.toFixed(1)}°C`);
        this.updateElement('dh-thermal-min', `${min.toFixed(1)}°C`);
    }

    resetThermalDisplay() {
        // Réinitialiser tous les points thermiques
        const idMapping = ['nez', 'bouche', 'oeil-gauche', 'oeil-droit',
                          'joue-gauche', 'joue-droite', 'front', 'menton'];

        idMapping.forEach(id => {
            const pointElement = document.getElementById(`dh-thermal-${id}`);
            if (pointElement) {
                pointElement.classList.remove('cool', 'normal', 'warm', 'hot');
            }

            const wrapper = pointElement?.closest('.thermal-point-wrapper');
            const labelElement = wrapper?.querySelector('.thermal-label');
            if (labelElement) {
                labelElement.textContent = '--°C';
            }
        });

        // Réinitialiser les stats
        this.updateElement('dh-thermal-avg', '--°C');
        this.updateElement('dh-thermal-max', '--°C');
        this.updateElement('dh-thermal-min', '--°C');

        // Réinitialiser le graphique et les buffers
        if (this.charts.thermal) {
            this.charts.thermal.data.labels = [];
            this.charts.thermal.data.datasets.forEach(dataset => {
                dataset.data = [];
            });
            this.charts.thermal.update('none');
        }

        // Vider les buffers
        this.thermalPoints.forEach(point => {
            this.thermalDataBuffers[point] = [];
        });
    }

    // === GESTION DES ÉVÉNEMENTS BROADCAST POLAR (existant) ===

    handlePolarBroadcast(deviceType, data) {
        logger.info(`Données Polar ${deviceType} reçues:`, data);

        // Traiter les données broadcast du module Polar
        if (!data || !data.data) return;

        const polarData = data.data;

        // Mettre à jour les cartes métriques
        this.updateBPMCard(polarData);
        this.updateBreathingCard(polarData);
        this.updateRRCard(polarData);

        // Animer le coeur
        this.animateHeartbeat();
    }

    handlePolarConnected(deviceType, data) {
        logger.info(`Appareil Polar ${deviceType} connecté`);

        // Mettre à jour l'état
        if (!this.devicesState.polar.devices.includes(deviceType)) {
            this.devicesState.polar.devices.push(deviceType);
        }
        this.devicesState.polar.connected = true;

        // Mettre à jour l'interface
        this.updateDeviceStatus('polar', true);

        // Masquer la bannière
        const banner = document.getElementById('dh-connection-banner');
        if (banner) {
            banner.style.display = 'none';
        }

        // Vérifier le démarrage automatique
        this.checkAutoStartMonitoring();

        // Notification
        this.showNotification(`Polar ${deviceType.toUpperCase()} connecté`, 'success');
    }

    handlePolarDisconnected(deviceType) {
        logger.info(`Appareil Polar ${deviceType} déconnecté`);

        // Mettre à jour l'état
        this.devicesState.polar.devices = this.devicesState.polar.devices.filter(d => d !== deviceType);
        this.devicesState.polar.connected = this.devicesState.polar.devices.length > 0;

        // Mettre à jour l'interface
        this.updateDeviceStatus('polar', this.devicesState.polar.connected);

        // Afficher la bannière si aucun appareil connecté
        if (!this.hasConnectedDevice()) {
            const banner = document.getElementById('dh-connection-banner');
            if (banner) {
                banner.style.display = 'block';
            }
        }

        // Notification
        this.showNotification(`Polar ${deviceType.toUpperCase()} déconnecté`, 'info');
    }

    // === GESTION DES ÉVÉNEMENTS BROADCAST NEUROSITY (existant) ===

    handleNeurosityBroadcast(dataType, data) {
        if (!data) return;

        logger.info(`Données Neurosity ${dataType} reçues:`, data);

        switch (dataType) {
            case 'calm':
                if (data.calm !== undefined) {
                    this.updateCalmCircle(data.calm);
                }
                break;

            case 'focus':
                if (data.focus !== undefined) {
                    this.updateFocusCircle(data.focus);
                }
                break;

            case 'brainwaves':
                if (data.delta !== undefined && data.theta !== undefined) {
                    const brainwaves = {
                        delta: Array.isArray(data.delta) ?
                               data.delta.reduce((a, b) => a + b, 0) / data.delta.length :
                               data.delta,
                        theta: Array.isArray(data.theta) ?
                               data.theta.reduce((a, b) => a + b, 0) / data.theta.length :
                               data.theta,
                        alpha: Array.isArray(data.alpha) ?
                               data.alpha.reduce((a, b) => a + b, 0) / data.alpha.length :
                               data.alpha,
                        beta: Array.isArray(data.beta) ?
                              data.beta.reduce((a, b) => a + b, 0) / data.beta.length :
                              data.beta,
                        gamma: Array.isArray(data.gamma) ?
                               data.gamma.reduce((a, b) => a + b, 0) / data.gamma.length :
                               data.gamma
                    };

                    this.updateBrainwavesChart(brainwaves);
                }
                break;

            case 'battery':
                if (data.level !== undefined) {
                    this.updateNeurosityBattery(data.level, data.charging);
                }
                break;
        }

        // Afficher l'indicateur live
        const indicator = document.getElementById('dh-brainwaves-indicator');
        if (indicator) {
            indicator.style.display = 'flex';
            clearTimeout(this.neurosityIndicatorTimeout);
            this.neurosityIndicatorTimeout = setTimeout(() => {
                indicator.style.display = 'none';
            }, 2000);
        }
    }

    // === GESTION DES ÉVÉNEMENTS MODULE HOME (existant) ===

    handleDashboardState(data) {
        // Mettre à jour l'état global du dashboard
        if (data.devices) {
            // Mise à jour manuelle des statuts d'appareils
            for (const [module, deviceData] of Object.entries(data.devices)) {
                if (module === 'polar' && deviceData.connected !== undefined) {
                    this.devicesState.polar.connected = deviceData.connected;
                    this.devicesState.polar.devices = deviceData.devices || [];
                    this.updateDeviceStatus('polar', deviceData.connected);
                } else if (module === 'neurosity' && deviceData.connected !== undefined) {
                    this.devicesState.neurosity.connected = deviceData.connected;
                    this.updateDeviceStatus('neurosity', deviceData.connected);
                    // Batterie
                    if (deviceData.battery !== undefined) {
                        this.updateNeurosityBattery(deviceData.battery, deviceData.charging);
                    }
                } else if (module === 'thermal' && deviceData.connected !== undefined) {
                    this.devicesState.thermal.connected = deviceData.connected;
                    this.updateDeviceStatus('thermal', deviceData.connected);
                } else if (module === 'gazepoint' && deviceData.connected !== undefined) {
                    this.devicesState.gazepoint.connected = deviceData.connected;
                    this.updateDeviceStatus('gazepoint', deviceData.connected);
                } else if (module === 'thought_capture' && deviceData.ready !== undefined) {
                    this.devicesState.thoughtCapture.ready = deviceData.ready;
                    this.devicesState.thoughtCapture.recording = deviceData.recording;
                    this.devicesState.thoughtCapture.paused = deviceData.paused;
                    const status = deviceData.recording ? (deviceData.paused ? 'paused' : 'recording') : 'ready';
                    this.updateThoughtCaptureStatus(status);
                }
            }
        }

        if (data.session) {
            this.updateSessionInfo(data.session);
        }
    }

    updateSessionInfo(sessionData) {
        // Mettre à jour les informations de session si nécessaire
        if (sessionData.is_collecting !== undefined && sessionData.is_collecting !== this.collectionState.isCollecting) {
            if (sessionData.is_collecting) {
                // La collecte a été démarrée ailleurs
                this.collectionState.isCollecting = true;
                this.collectionState.startTime = new Date();
                this.startTimer();

                const btn = document.getElementById('dh-collect-btn');
                if (btn) {
                    btn.classList.add('collecting');
                    btn.innerHTML = '<i class="fas fa-stop"></i><span>Arrêter l\'enregistrement CSV</span>';
                }
            } else {
                // La collecte a été arrêtée
                this.collectionState.isCollecting = false;
                this.stopTimer();

                const btn = document.getElementById('dh-collect-btn');
                if (btn) {
                    btn.classList.remove('collecting');
                    btn.innerHTML = '<i class="fas fa-play"></i><span>Démarrer l\'enregistrement CSV</span>';
                }
            }
        }

        // Mettre à jour les stats Thought Capture si présentes
        if (sessionData.total_recordings !== undefined) {
            this.thoughtCaptureState.totalRecordings = sessionData.total_recordings;
        }
        if (sessionData.total_recording_duration !== undefined) {
            this.thoughtCaptureState.totalDuration = sessionData.total_recording_duration;
        }
        if (sessionData.total_recording_size !== undefined) {
            this.thoughtCaptureState.totalSize = sessionData.total_recording_size;
        }

        this.updateThoughtCaptureStats();
    }

    handlePolarDataUpdate(data) {
        // Mise à jour détaillée depuis le backend Home
        this.updateBPMMetrics(data.bpm);
        this.updateRRMetrics(data.rr);
        this.updateBreathingMetrics(data.breathing);

        // Mettre à jour les graphiques
        if (data.graphs) {
            this.updateCharts(data.graphs);
        }
    }

    handleNeurosityDataUpdate(data) {
        logger.info('Mise à jour Neurosity reçue:', data);

        // Mettre à jour selon le type de données
        if (data.data_type === 'calm' && data.calm !== undefined) {
            this.updateCalmCircle(data.calm);
        } else if (data.data_type === 'focus' && data.focus !== undefined) {
            this.updateFocusCircle(data.focus);
        } else if (data.data_type === 'brainwaves' && data.brainwaves) {
            this.updateBrainwavesChart(data.brainwaves);
        } else if (data.data_type === 'battery') {
            this.updateNeurosityBattery(data.battery, data.charging);
        }

        // Afficher l'indicateur live
        const indicator = document.getElementById('dh-brainwaves-indicator');
        if (indicator) {
            indicator.style.display = 'flex';
            // Le masquer après 2 secondes
            clearTimeout(this.neurosityIndicatorTimeout);
            this.neurosityIndicatorTimeout = setTimeout(() => {
                indicator.style.display = 'none';
            }, 2000);
        }
    }

    handleThermalDataUpdate(data) {
        logger.info('Mise à jour Thermal reçue:', data);

        if (data.temperatures) {
            this.handleThermalBroadcast(data);
        }
    }

    handleDevicesStatus(data) {
        logger.info('Statut des appareils reçu:', data);

        // Réponse à la demande de statut initial
        if (data.polar) {
            this.devicesState.polar.connected = data.polar.connected;
            this.devicesState.polar.devices = data.polar.devices || [];
            this.updateDeviceStatus('polar', data.polar.connected);
        }

        if (data.neurosity) {
            this.devicesState.neurosity.connected = data.neurosity.connected;
            this.updateDeviceStatus('neurosity', data.neurosity.connected);
        }

        if (data.thermal) {
            this.devicesState.thermal.connected = data.thermal.connected;
            this.updateDeviceStatus('thermal', data.thermal.connected);
        }

        if (data.gazepoint) {
            this.devicesState.gazepoint.connected = data.gazepoint.connected;
            this.updateDeviceStatus('gazepoint', data.gazepoint.connected);
        }

        if (data.thought_capture) {
            this.devicesState.thoughtCapture.ready = data.thought_capture.ready;
            this.devicesState.thoughtCapture.recording = data.thought_capture.recording;
            this.devicesState.thoughtCapture.paused = data.thought_capture.paused;
            const status = data.thought_capture.recording ?
                (data.thought_capture.paused ? 'paused' : 'recording') : 'ready';
            this.updateThoughtCaptureStatus(status);
        }

        // Afficher/masquer la bannière
        const banner = document.getElementById('dh-connection-banner');
        if (banner) {
            banner.style.display = this.hasConnectedDevice() ? 'none' : 'block';
        }

        // Vérifier le démarrage automatique
        if (this.hasConnectedDevice() && this.autoStartMonitoring) {
            this.checkAutoStartMonitoring();
        }
    }

    // === MISE À JOUR DE L'INTERFACE POLAR (existant) ===

    updateBPMCard(data) {
        const bpmValue = document.getElementById('dh-bpm-value');
        if (bpmValue && data.heart_rate) {
            bpmValue.textContent = data.heart_rate;

            // Ajouter une animation de pulsation à la carte
            const card = document.getElementById('dh-polar-card');
            if (card) {
                card.classList.add('pulse');
                setTimeout(() => card.classList.remove('pulse'), 600);
            }
        }

        // Mettre à jour les métriques si disponibles
        if (data.real_time_metrics?.bpm_metrics) {
            const metrics = data.real_time_metrics.bpm_metrics;
            this.updateElement('dh-bpm-min', metrics.session_min || '--');
            this.updateElement('dh-bpm-max', metrics.session_max || '--');
            this.updateElement('dh-bpm-avg', Math.round(metrics.mean_bpm) || '--');
        }
    }

    updateBreathingCard(data) {
        if (!data.real_time_metrics?.breathing_metrics) return;

        const breathing = data.real_time_metrics.breathing_metrics;

        if (breathing.frequency > 0) {
            this.updateElement('dh-breathing-value', Math.round(breathing.frequency));
            this.updateElement('dh-breathing-amp', breathing.amplitude.toFixed(3));

            // Mettre à jour la qualité
            const qualityBadge = document.getElementById('dh-breathing-quality');
            if (qualityBadge) {
                qualityBadge.textContent = breathing.quality || '--';
                qualityBadge.className = `quality-badge quality-${breathing.quality}`;
            }

            // Animer la vague de respiration
            const wave = document.getElementById('dh-breathing-wave');
            if (wave) {
                wave.classList.add('active');
            }
        }
    }

    updateRRCard(data) {
        if (!data.real_time_metrics?.rr_metrics) return;

        const rr = data.real_time_metrics.rr_metrics;

        if (rr.last_rr > 0) {
            this.updateElement('dh-rr-value', Math.round(rr.last_rr));
            this.updateElement('dh-rr-rmssd', Math.round(rr.rmssd));
            this.updateElement('dh-rr-mean', Math.round(rr.mean_rr));
        }
    }

    updateBPMMetrics(metrics) {
        if (!metrics) return;

        this.updateElement('dh-bpm-value', metrics.current || '--');
        this.updateElement('dh-bpm-min', metrics.min || '--');
        this.updateElement('dh-bpm-max', metrics.max || '--');
        this.updateElement('dh-bpm-avg', Math.round(metrics.avg) || '--');
    }

    updateRRMetrics(metrics) {
        if (!metrics) return;

        this.updateElement('dh-rr-value', Math.round(metrics.last) || '--');
        this.updateElement('dh-rr-rmssd', Math.round(metrics.rmssd) || '--');
        this.updateElement('dh-rr-mean', Math.round(metrics.mean) || '--');
    }

    updateBreathingMetrics(metrics) {
        if (!metrics) return;

        this.updateElement('dh-breathing-value', Math.round(metrics.rate) || '--');
        this.updateElement('dh-breathing-amp', metrics.amplitude?.toFixed(3) || '--');

        const qualityBadge = document.getElementById('dh-breathing-quality');
        if (qualityBadge && metrics.quality) {
            qualityBadge.textContent = metrics.quality;
            qualityBadge.className = `quality-badge quality-${metrics.quality}`;
        }
    }

    // === MISE À JOUR DE L'INTERFACE NEUROSITY (existant) ===

    updateCalmCircle(value) {
        // Mettre à jour la valeur
        const calmValueEl = document.getElementById('dh-calm-value');
        if (calmValueEl) {
            calmValueEl.textContent = Math.round(value);
        }

        // Mettre à jour le cercle de progression
        const calmProgress = document.querySelector('.calm-progress');
        if (calmProgress) {
            const circumference = 2 * Math.PI * 45; // rayon = 45
            const offset = circumference - (value / 100) * circumference;
            calmProgress.style.strokeDashoffset = offset;
        }

        // Animer le conteneur
        const container = document.querySelector('[data-metric="calm"]')?.parentElement;
        if (container) {
            container.classList.add('updating');
            setTimeout(() => container.classList.remove('updating'), 300);
        }

        this.neurosityState.calm = value;
    }

    updateFocusCircle(value) {
        // Mettre à jour la valeur
        const focusValueEl = document.getElementById('dh-focus-value');
        if (focusValueEl) {
            focusValueEl.textContent = Math.round(value);
        }

        // Mettre à jour le cercle de progression
        const focusProgress = document.querySelector('.focus-progress');
        if (focusProgress) {
            const circumference = 2 * Math.PI * 45; // rayon = 45
            const offset = circumference - (value / 100) * circumference;
            focusProgress.style.strokeDashoffset = offset;
        }

        // Animer le conteneur
        const container = document.querySelector('[data-metric="focus"]')?.parentElement;
        if (container) {
            container.classList.add('updating');
            setTimeout(() => container.classList.remove('updating'), 300);
        }

        this.neurosityState.focus = value;
    }

    updateBrainwavesChart(brainwaves) {
        if (!this.charts.brainwaves) return;

        // Préparer les données pour le graphique
        const waves = ['delta', 'theta', 'alpha', 'beta', 'gamma'];
        const data = waves.map(wave => {
            const value = brainwaves[wave] || 0;
            // Limiter à 15 pour une meilleure visualisation
            return Math.min(value, 15);
        });

        // Mettre à jour le graphique
        this.charts.brainwaves.data.datasets[0].data = data;
        this.charts.brainwaves.update('none');

        // Sauvegarder l'état
        this.neurosityState.brainwaves = { ...brainwaves };
    }

    updateNeurosityBattery(level, charging) {
        const batteryEl = document.getElementById('dh-neurosity-battery');
        const batteryLevelEl = batteryEl?.querySelector('.battery-level');
        const batteryIcon = batteryEl?.querySelector('i');

        if (batteryEl && level !== undefined && level !== null) {
            batteryEl.style.display = 'flex';

            if (batteryLevelEl) {
                batteryLevelEl.textContent = level;
            }

            if (batteryIcon) {
                // Changer l'icône selon le niveau
                let iconClass = 'fa-battery-full';
                if (level <= 20) {
                    iconClass = 'fa-battery-empty';
                    batteryEl.style.color = '#ef4444';
                } else if (level <= 50) {
                    iconClass = 'fa-battery-half';
                    batteryEl.style.color = '#f59e0b';
                } else if (level <= 75) {
                    iconClass = 'fa-battery-three-quarters';
                    batteryEl.style.color = '#10b981';
                } else {
                    batteryEl.style.color = '#10b981';
                }

                // Ajouter l'icône de charge si en charge
                if (charging) {
                    iconClass = 'fa-bolt';
                    batteryEl.style.color = '#3b82f6';
                }

                batteryIcon.className = `fas ${iconClass}`;
            }
        }
    }

    updateDeviceStatus(device, connected) {
        const statusElement = document.getElementById(`dh-${device}-status`);
        if (!statusElement) return;

        const indicator = statusElement.querySelector('.device-indicator');
        const text = statusElement.querySelector('.status-text') || statusElement.querySelector('span:last-child');

        if (indicator) {
            indicator.className = `device-indicator ${connected ? 'online' : 'offline'}`;
        }

        if (text) {
            if (device === 'polar' && connected) {
                const devices = this.devicesState.polar.devices.map(d => d.toUpperCase()).join(' + ');
                text.textContent = devices || 'Connecté';
            } else {
                text.textContent = connected ? 'Connecté' : 'Non connecté';
            }
        }

        // Mise à jour spécifique pour Neurosity
        if (device === 'neurosity') {
            const batteryEl = document.getElementById('dh-neurosity-battery');
            if (batteryEl && !connected) {
                batteryEl.style.display = 'none';
            }
        }
    }

    updateElement(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }

    // === GRAPHIQUES (existant) ===

    updateCharts(graphData) {
        // Mettre à jour le graphique BPM
        if (this.charts.bpm && graphData.bpm && graphData.bpm.length > 0) {
            const bpmData = graphData.bpm.map(d => d.value);
            const labels = graphData.bpm.map((_, i) => i);

            this.charts.bpm.data.labels = labels;
            this.charts.bpm.data.datasets[0].data = bpmData;
            this.charts.bpm.update('none');
        }

        // Mettre à jour le graphique RR
        if (this.charts.rr && graphData.rr && graphData.rr.length > 0) {
            const rrData = graphData.rr.map(d => d.value);
            const labels = graphData.rr.map((_, i) => i);

            this.charts.rr.data.labels = labels;
            this.charts.rr.data.datasets[0].data = rrData;
            this.charts.rr.update('none');
        }
    }

    // === COLLECTION (existant) ===

    toggleCollection() {
        if (this.collectionState.isCollecting) {
            this.stopCollection();
        } else {
            this.startCollection();
        }
    }

    startCollection() {
        if (!this.wsClient || !this.wsClient.isConnected) {
            logger.error('WebSocket non connecté');
            this.showNotification('Impossible de démarrer l\'enregistrement - WebSocket non connecté', 'error');
            return;
        }

        logger.info('Démarrage de l\'enregistrement CSV...');

        // Émettre la demande de démarrage
        this.wsClient.emit('home_start_collection', {});

        // Mettre à jour l'interface immédiatement
        this.collectionState.isCollecting = true;
        this.collectionState.startTime = new Date();

        // Mettre à jour le bouton
        const btn = document.getElementById('dh-collect-btn');
        if (btn) {
            btn.classList.add('collecting');
            btn.innerHTML = '<i class="fas fa-stop"></i><span>Arrêter l\'enregistrement CSV</span>';
        }

        // Démarrer le timer
        this.startTimer();

        // Afficher le badge de monitoring
        const badge = document.getElementById('dh-monitoring-badge');
        if (badge) {
            badge.style.display = 'flex';
            badge.classList.add('live');
        }

        // Mettre à jour le statut
        this.updateStatus('recording', 'Enregistrement CSV en cours');

        // Notification claire
        this.showNotification('Enregistrement CSV démarré - Les données sont maintenant sauvegardées', 'success');
    }

    stopCollection() {
        if (!this.wsClient || !this.wsClient.isConnected) return;

        logger.info('Arrêt de l\'enregistrement CSV...');

        // Émettre la demande d'arrêt
        this.wsClient.emit('home_stop_collection', {});

        // Mettre à jour l'interface
        this.collectionState.isCollecting = false;

        // Mettre à jour le bouton
        const btn = document.getElementById('dh-collect-btn');
        if (btn) {
            btn.classList.remove('collecting');
            btn.innerHTML = '<i class="fas fa-play"></i><span>Démarrer l\'enregistrement CSV</span>';
        }

        // Arrêter le timer
        this.stopTimer();

        // Masquer le badge
        const badge = document.getElementById('dh-monitoring-badge');
        if (badge) {
            badge.style.display = 'none';
            badge.classList.remove('live');
        }

        // Mettre à jour le statut
        this.updateStatus('ready', 'Prêt');

        // Notification
        this.showNotification('Arrêt de l\'enregistrement CSV en cours...', 'info');
    }

    handleCollectionStarted(data) {
        logger.info('Collecte CSV démarrée:', data);

        // Vérifier si c'est un succès
        if (data === true || data.success === true || data.session_id) {
            this.showNotification('Enregistrement CSV démarré avec succès', 'success');
        } else {
            this.showNotification('Erreur lors du démarrage de l\'enregistrement', 'error');
            // Remettre l'interface dans l'état non-collecte
            this.collectionState.isCollecting = false;
            this.stopTimer();

            const btn = document.getElementById('dh-collect-btn');
            if (btn) {
                btn.classList.remove('collecting');
                btn.innerHTML = '<i class="fas fa-play"></i><span>Démarrer l\'enregistrement CSV</span>';
            }
        }
    }

    handleCollectionStopped(data) {
        logger.info('Collecte CSV arrêtée:', data);

        // Afficher un résumé si disponible
        if (data === true || data.success === true) {
            let message = 'Enregistrement CSV arrêté';

            if (data.duration && data.total_samples) {
                const duration = this.formatDuration(data.duration);
                message = `Enregistrement terminé: ${duration}, ${data.total_samples} échantillons`;
            } else if (data.duration) {
                const duration = this.formatDuration(data.duration);
                message = `Enregistrement terminé: ${duration}`;
            }

            this.showNotification(message, 'success');
        }
    }

    handleDeviceConnected(data) {
        logger.info('Appareil connecté:', data);

        if (data.module === 'polar') {
            this.handlePolarConnected(data.device_type, data.device_info);
        } else if (data.module === 'neurosity') {
            this.handleNeurosityConnected({ device_status: data.device_info });
        } else if (data.module === 'thermal') {
            this.handleThermalConnected();
        } else if (data.module === 'gazepoint') {
            this.handleGazepointConnected();
        }
    }

    handleDeviceDisconnected(data) {
        logger.info('Appareil déconnecté:', data);

        if (data.module === 'polar') {
            this.handlePolarDisconnected(data.device_type);
        } else if (data.module === 'neurosity') {
            this.handleNeurosityDisconnected({});
        } else if (data.module === 'thermal') {
            this.handleThermalDisconnected();
        } else if (data.module === 'gazepoint') {
            this.handleGazepointDisconnected();
        }
    }

    handleNeurosityConnected(data) {
        try {
            this.devicesState.neurosity.connected = true;
            this.updateDeviceStatus('neurosity', true);

            // Masquer la bannière si nécessaire
            if (this.hasConnectedDevice()) {
                const banner = document.getElementById('dh-connection-banner');
                if (banner) banner.style.display = 'none';
            }

            this.checkAutoStartMonitoring();
            this.showNotification('Neurosity Crown connecté', 'success');
        } catch (error) {
            logger.error('Erreur gestion connexion Neurosity:', error);
        }
    }

    handleNeurosityDisconnected(data) {
        try {
            this.devicesState.neurosity.connected = false;
            this.updateDeviceStatus('neurosity', false);

            // Réinitialiser l'affichage
            this.updateCalmCircle(0);
            this.updateFocusCircle(0);
            this.updateBrainwavesChart({
                delta: 0, theta: 0, alpha: 0, beta: 0, gamma: 0
            });

            // Afficher la bannière si aucun appareil
            if (!this.hasConnectedDevice()) {
                const banner = document.getElementById('dh-connection-banner');
                if (banner) banner.style.display = 'block';
            }

            this.showNotification('Neurosity Crown déconnecté', 'info');
        } catch (error) {
            logger.error('Erreur gestion déconnexion Neurosity:', error);
        }
    }

    handleThermalConnected() {
        try {
            this.devicesState.thermal.connected = true;
            this.updateDeviceStatus('thermal', true);

            if (this.hasConnectedDevice()) {
                const banner = document.getElementById('dh-connection-banner');
                if (banner) banner.style.display = 'none';
            }

            this.checkAutoStartMonitoring();
            this.showNotification('Caméra thermique connectée', 'success');
        } catch (error) {
            logger.error('Erreur gestion connexion thermal:', error);
        }
    }

    handleThermalDisconnected() {
        try {
            this.devicesState.thermal.connected = false;
            this.updateDeviceStatus('thermal', false);
            this.resetThermalDisplay();

            if (!this.hasConnectedDevice()) {
                const banner = document.getElementById('dh-connection-banner');
                if (banner) banner.style.display = 'block';
            }

            this.showNotification('Caméra thermique déconnectée', 'info');
        } catch (error) {
            logger.error('Erreur gestion déconnexion thermal:', error);
        }
    }

    handleGazepointConnected() {
        try {
            this.devicesState.gazepoint.connected = true;
            this.updateDeviceStatus('gazepoint', true);

            if (this.hasConnectedDevice()) {
                const banner = document.getElementById('dh-connection-banner');
                if (banner) banner.style.display = 'none';
            }

            this.checkAutoStartMonitoring();
            this.showNotification('Gazepoint connecté', 'success');
        } catch (error) {
            logger.error('Erreur gestion connexion Gazepoint:', error);
        }
    }

    handleGazepointDisconnected() {
        try {
            this.devicesState.gazepoint.connected = false;
            this.updateDeviceStatus('gazepoint', false);
            this.resetGazepointDisplay();

            if (!this.hasConnectedDevice()) {
                const banner = document.getElementById('dh-connection-banner');
                if (banner) banner.style.display = 'block';
            }

            this.showNotification('Gazepoint déconnecté', 'info');
        } catch (error) {
            logger.error('Erreur gestion déconnexion Gazepoint:', error);
        }
    }

    // === TIMER (existant) ===

    startTimer() {
        if (this.collectionState.timerInterval) return;

        const timerDisplay = document.getElementById('dh-timer-display');
        const timerContainer = document.getElementById('dh-session-timer');

        if (timerContainer) {
            timerContainer.style.display = 'flex';
        }

        this.collectionState.timerInterval = setInterval(() => {
            if (!this.collectionState.startTime) return;

            const elapsed = Math.floor((new Date() - this.collectionState.startTime) / 1000);
            const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
            const seconds = (elapsed % 60).toString().padStart(2, '0');

            if (timerDisplay) {
                timerDisplay.textContent = `${minutes}:${seconds}`;
            }
        }, 1000);
    }

    stopTimer() {
        if (this.collectionState.timerInterval) {
            clearInterval(this.collectionState.timerInterval);
            this.collectionState.timerInterval = null;
        }

        const timerContainer = document.getElementById('dh-session-timer');
        if (timerContainer) {
            timerContainer.style.display = 'none';
        }

        this.collectionState.startTime = null;
    }

    // === UTILITAIRES ===

    requestDevicesStatus() {
        if (this.wsClient && this.wsClient.isConnected) {
            // Demander le statut via l'événement dashboard
            this.wsClient.socket.emit('dashboard_get_devices_status', {});
            logger.info('Demande du statut des appareils envoyée');
        }
    }

    hasConnectedDevice() {
        return this.devicesState.polar.connected ||
               this.devicesState.neurosity.connected ||
               this.devicesState.thermal.connected ||
               this.devicesState.gazepoint.connected;
    }

    checkAutoStartMonitoring() {
        // Le démarrage automatique ne doit PAS lancer la collecte CSV
        // Il doit seulement activer le monitoring visuel
        if (this.autoStartMonitoring && this.hasConnectedDevice()) {
            logger.info('Monitoring automatique activé (sans enregistrement CSV)');
            // Le monitoring visuel est déjà actif dès la connexion des appareils
        }
    }

    animateHeartbeat() {
        const heartIcon = document.getElementById('dh-heart-icon');
        if (!heartIcon) return;

        // Ajouter l'animation
        heartIcon.style.transform = 'scale(1.2)';
        heartIcon.style.color = '#dc2626';

        setTimeout(() => {
            heartIcon.style.transform = 'scale(1)';
            heartIcon.style.color = '';
        }, 200);
    }

    updateStatus(type, text) {
        const statusDot = document.querySelector('#dh-status .dh-status-dot');
        const statusText = document.querySelector('#dh-status .dh-status-text');

        if (statusDot) {
            statusDot.className = `dh-status-dot ${type === 'recording' ? 'recording' : ''}`;
        }

        if (statusText) {
            statusText.textContent = text;
        }
    }

    formatDuration(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        if (mins === 0) {
            return `${secs}s`;
        } else if (mins < 60) {
            return `${mins}m ${secs}s`;
        } else {
            const hours = Math.floor(mins / 60);
            const remainingMins = mins % 60;
            return `${hours}h ${remainingMins}m`;
        }
    }

    showNotification(message, type = 'info') {
        const container = document.getElementById('dh-notifications');
        if (!container) return;

        const notification = document.createElement('div');
        notification.className = `dh-notification ${type} show`;

        const icon = type === 'success' ? 'fa-check-circle' :
                    type === 'error' ? 'fa-exclamation-circle' :
                    'fa-info-circle';

        notification.innerHTML = `
            <i class="fas ${icon}"></i>
            <span>${message}</span>
        `;

        container.appendChild(notification);

        // Retirer après 3 secondes
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    // === MÉTHODES DE CYCLE DE VIE ===

    onRestore() {
        logger.info('Module Home restauré');

        // Réinitialiser les graphiques si nécessaire
        if (!this.charts.bpm || !this.charts.rr || !this.charts.brainwaves || !this.charts.thermal) {
            this.initCharts();
        }

        // Réinitialiser la visualisation Gazepoint
        if (!this.gazeCanvas) {
            this.initGazepointVisualization();
        }

        // Réinitialiser la visualisation Thought Capture
        if (!this.audioCanvas) {
            this.initThoughtCaptureVisualization();
        }

        // Redemander le statut des appareils
        this.requestDevicesStatus();
    }

    onHide() {
        // Appelé quand le module est caché (navigation vers un autre module)
        logger.info('Module Home caché');

        // Arrêter l'animation du regard
        if (this.gazeAnimationFrame) {
            cancelAnimationFrame(this.gazeAnimationFrame);
            this.gazeAnimationFrame = null;
        }

        // Arrêter l'animation audio
        if (this.audioAnimationFrame) {
            cancelAnimationFrame(this.audioAnimationFrame);
            this.audioAnimationFrame = null;
        }
    }

    cleanup() {
        logger.info('Nettoyage du module Home');

        // Arrêter la collecte si active
        if (this.collectionState.isCollecting) {
            this.stopCollection();
        }

        // Arrêter le timer
        this.stopTimer();

        // Arrêter le timer thought capture
        this.stopThoughtTimer();

        // Arrêter l'animation du regard
        if (this.gazeAnimationFrame) {
            cancelAnimationFrame(this.gazeAnimationFrame);
            this.gazeAnimationFrame = null;
        }

        // Arrêter l'animation audio
        if (this.audioAnimationFrame) {
            cancelAnimationFrame(this.audioAnimationFrame);
            this.audioAnimationFrame = null;
        }

        // Détruire les graphiques
        if (this.charts.bpm) {
            this.charts.bpm.destroy();
            this.charts.bpm = null;
        }
        if (this.charts.rr) {
            this.charts.rr.destroy();
            this.charts.rr = null;
        }
        if (this.charts.brainwaves) {
            this.charts.brainwaves.destroy();
            this.charts.brainwaves = null;
        }
        if (this.charts.thermal) {
            this.charts.thermal.destroy();
            this.charts.thermal = null;
        }

        // Réinitialiser l'état
        this.isInitialized = false;
    }
}

// Logger utilitaire
const logger = {
    info: (...args) => console.log('%c[Home]', 'color: #667eea', ...args),
    warn: (...args) => console.warn('%c[Home]', 'color: #f59e0b', ...args),
    error: (...args) => console.error('%c[Home]', 'color: #ef4444', ...args)
};

// Export global pour l'initialisation
window.HomeModule = HomeModule;