/**
 * Module Neurosity - Frontend intégré au dashboard
 * Version corrigée avec protection contre les redéclarations
 */

// Protection IIFE pour éviter les conflits globaux
(function() {
    'use strict';

    // Si le module existe déjà, ne pas le redéclarer
    if (window.NeurosityModuleClass) {
        console.log('Module Neurosity déjà chargé, skip');
        return;
    }

    class NeurosityModule {
        constructor() {
            // État du module
            this.isConnected = false;
            this.isRecording = false;
            this.isMonitoring = false;
            this.deviceStatus = {
                online: false,
                battery: 0,
                charging: false,
                signal: 'disconnected'
            };

            // WebSocket client
            this.wsClient = null;

            // Graphiques
            this.charts = {
                brainwaves: null,
                eegRaw: null
            };

            // Sessions
            this.sessions = [];

            // Configuration
            this.config = {
                chartUpdateAnimation: 100,
                toastDuration: 4000
            };

            // Flags
            this.handlersSetup = false;
            this.initialized = false;

            // Initialisation automatique
            this.init();
        }

        async init() {
            if (this.initialized) {
                console.log('Module Neurosity déjà initialisé');
                return;
            }

            console.log('Initialisation du module Neurosity');

            // Attendre que le dashboard soit prêt
            await this.waitForDashboard();

            // Récupérer le client WebSocket
            if (window.dashboard && window.dashboard.wsClient) {
                this.wsClient = window.dashboard.wsClient;
                this.setupWebSocketHandlers();
            } else {
                console.warn('WebSocket client non disponible');
            }

            // Initialiser les composants
            this.initCharts();
            this.initClock();
            await this.loadSessions();
            this.setupEventListeners();

            // Demander le statut initial
            if (this.wsClient && this.wsClient.isConnected) {
                this.wsClient.emitToModule('neurosity', 'get_status', {});
            }

            this.initialized = true;
            console.log('Module Neurosity prêt');
        }

        async reinit() {
            console.log('Réinitialisation du module Neurosity');

            // Demander le statut actuel
            if (this.wsClient && this.wsClient.isConnected) {
                this.wsClient.emitToModule('neurosity', 'get_status', {});
            }

            // Recharger les sessions
            await this.loadSessions();
        }

        async waitForDashboard() {
            let attempts = 0;
            while ((!window.dashboard || !window.dashboard.wsClient) && attempts < 50) {
                await new Promise(resolve => setTimeout(resolve, 100));
                attempts++;
            }
        }

        setupWebSocketHandlers() {
            if (!this.wsClient || this.handlersSetup) return;

            console.log('Configuration des handlers WebSocket Neurosity');

            // Nettoyer les anciens handlers
            this.cleanupHandlers();

            // Données temps réel
            this.wsClient.on('neurosity_calm_data', (data) => this.handleMetricData('calm', data));
            this.wsClient.on('neurosity_focus_data', (data) => this.handleMetricData('focus', data));
            this.wsClient.on('neurosity_brainwaves_data', (data) => this.handleBrainwavesData(data));
            this.wsClient.on('neurosity_signal_quality_data', (data) => this.handleSignalQualityData(data));
            this.wsClient.on('neurosity_brainwaves_raw_data', (data) => this.handleBrainwavesRawData(data));
            this.wsClient.on('neurosity_battery_data', (data) => this.updateBatteryStatus(data));

            // Événements de connexion
            this.wsClient.on('neurosity_connected', (data) => {
                console.log('Casque connecté:', data);
                this.showToast('Casque Neurosity connecté !', 'success');
                this.isConnected = true;
                if (data.device_status) {
                    this.updateDeviceStatus(data.device_status);
                }
                this.updateUI();

                // Démarrer le monitoring automatiquement
                setTimeout(() => {
                    if (this.isConnected && !this.isMonitoring) {
                        this.startMonitoring();
                    }
                }, 1000);
            });

            this.wsClient.on('neurosity_disconnected', () => {
                console.log('Casque déconnecté');
                this.showToast('Casque déconnecté', 'info');
                this.isConnected = false;
                this.isMonitoring = false;
                this.updateUI();
                this.resetElectrodes();
            });

            this.wsClient.on('neurosity_error', (data) => {
                console.error('Erreur Neurosity:', data);
                this.showToast(`Erreur: ${data.error}`, 'error');
                const connectBtn = document.getElementById('connectBtn');
                if (connectBtn) {
                    connectBtn.disabled = false;
                    this.updateUI();
                }
            });

            // Statut
            this.wsClient.on('neurosity_status', (data) => {
                console.log('Statut reçu:', data);
                this.updateConnectionStatus(data.connected, data.recording, data.monitoring);
                if (data.device_status) {
                    this.updateDeviceStatus(data.device_status);
                }
            });

            // Monitoring
            this.wsClient.onModuleEvent('neurosity', 'monitoring_started', () => {
                this.showToast('Monitoring démarré !', 'success');
                this.isMonitoring = true;
                this.updateMonitoringUI(true);
            });

            this.wsClient.onModuleEvent('neurosity', 'monitoring_stopped', () => {
                this.showToast('Monitoring arrêté', 'info');
                this.isMonitoring = false;
                this.updateMonitoringUI(false);
            });

            // Enregistrement
            this.wsClient.on('neurosity_recording_status', (data) => {
                if (data.success) {
                    this.isRecording = data.recording;
                    this.updateUI();
                    this.showToast(
                        this.isRecording ? 'Enregistrement démarré !' : 'Enregistrement arrêté',
                        'success'
                    );
                    if (!this.isRecording) {
                        setTimeout(() => this.loadSessions(), 1000);
                    }
                } else {
                    this.showToast(`Erreur: ${data.error}`, 'error');
                }
            });

            // Sessions
            this.wsClient.on('neurosity_sessions_list', (data) => {
                this.displaySessions(data.sessions || []);
            });

            this.wsClient.onModuleEvent('neurosity', 'sessions_updated', (data) => {
                this.displaySessions(data.sessions || []);
            });

            this.handlersSetup = true;
        }

        cleanupHandlers() {
            if (!this.wsClient) return;

            const events = [
                'neurosity_calm_data', 'neurosity_focus_data', 'neurosity_brainwaves_data',
                'neurosity_signal_quality_data', 'neurosity_brainwaves_raw_data',
                'neurosity_battery_data', 'neurosity_connected', 'neurosity_disconnected',
                'neurosity_error', 'neurosity_status', 'neurosity_recording_status',
                'neurosity_sessions_list'
            ];

            events.forEach(event => this.wsClient.off(event));
        }

        setupEventListeners() {
            // Éviter les doublons
            const connectBtn = document.getElementById('connectBtn');
            if (connectBtn && !connectBtn.hasAttribute('data-listener')) {
                connectBtn.addEventListener('click', () => this.toggleConnection());
                connectBtn.setAttribute('data-listener', 'true');
            }

            const recordBtn = document.getElementById('recordBtn');
            if (recordBtn && !recordBtn.hasAttribute('data-listener')) {
                recordBtn.addEventListener('click', () => this.toggleRecording());
                recordBtn.setAttribute('data-listener', 'true');
            }

            const downloadBtn = document.getElementById('downloadBtn');
            if (downloadBtn && !downloadBtn.hasAttribute('data-listener')) {
                downloadBtn.addEventListener('click', () => this.downloadLatestSession());
                downloadBtn.setAttribute('data-listener', 'true');
            }

            const refreshBtn = document.querySelector('.neuro_sessions-refresh-btn');
            if (refreshBtn && !refreshBtn.hasAttribute('data-listener')) {
                refreshBtn.addEventListener('click', () => this.refreshSessions());
                refreshBtn.setAttribute('data-listener', 'true');
            }
        }

        initCharts() {
            // Graphique des ondes cérébrales
            const brainwavesCanvas = document.getElementById('brainwavesChart');
            if (brainwavesCanvas && !this.charts.brainwaves) {
                const ctx = brainwavesCanvas.getContext('2d');
                this.charts.brainwaves = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: ['Delta\n0.1-4 Hz', 'Theta\n4-7.5 Hz', 'Alpha\n7.5-12.5 Hz',
                                'Beta\n12.5-30 Hz', 'Gamma\n30-100 Hz'],
                        datasets: [{
                            label: 'Power (μV²/Hz)',
                            data: [0, 0, 0, 0, 0],
                            backgroundColor: [
                                'rgba(99, 102, 241, 0.8)', 'rgba(245, 158, 11, 0.8)',
                                'rgba(59, 130, 246, 0.8)', 'rgba(34, 197, 94, 0.8)',
                                'rgba(236, 72, 153, 0.8)'
                            ],
                            borderColor: [
                                'rgb(99, 102, 241)', 'rgb(245, 158, 11)',
                                'rgb(59, 130, 246)', 'rgb(34, 197, 94)',
                                'rgb(236, 72, 153)'
                            ],
                            borderWidth: 1,
                            barThickness: 'flex',
                            maxBarThickness: 100
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: { duration: this.config.chartUpdateAnimation },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                                callbacks: {
                                    title: (context) => context[0].label.split('\n')[0],
                                    label: (context) => context.parsed.y.toFixed(1) + ' μV²/Hz'
                                }
                            }
                        },
                        scales: {
                            x: {
                                grid: { display: false },
                                ticks: {
                                    font: { family: 'Inter, sans-serif', size: 11 },
                                    color: '#64748b'
                                }
                            },
                            y: {
                                min: 0,
                                max: 20,
                                grid: { color: 'rgba(0, 0, 0, 0.05)' },
                                ticks: {
                                    stepSize: 2,
                                    font: { family: 'Inter, sans-serif', size: 11 },
                                    color: '#94a3b8',
                                    callback: (value) => value % 2 === 0 ? value + ' μV²/Hz' : ''
                                }
                            }
                        }
                    }
                });
            }

            // Graphique EEG brut
            const eegRawCanvas = document.getElementById('eegRawChart');
            if (eegRawCanvas && !this.charts.eegRaw) {
                this.charts.eegRaw = new EEGRawChart(eegRawCanvas);
            }
        }

        async toggleConnection() {
            if (this.isConnected) {
                this.disconnect();
            } else {
                this.connect();
            }
        }

        async connect() {
            const connectBtn = document.getElementById('connectBtn');
            if (connectBtn) {
                connectBtn.disabled = true;
                connectBtn.innerHTML = '<span class="neuro_btn-text">Connexion...</span>';
            }

            this.showToast('Connexion au casque Neurosity...', 'info', 5000);

            if (this.wsClient && this.wsClient.isConnected) {
                console.log('Émission de la demande de connexion Neurosity');
                this.wsClient.emitToModule('neurosity', 'connect', {});
            } else {
                this.showToast('WebSocket non disponible', 'error');
                if (connectBtn) {
                    connectBtn.disabled = false;
                    this.updateUI();
                }
            }

            // Timeout de connexion
            setTimeout(() => {
                if (connectBtn && !this.isConnected) {
                    connectBtn.disabled = false;
                    this.updateUI();
                }
            }, 60000);
        }

        disconnect() {
            if (!confirm('Êtes-vous sûr de vouloir déconnecter le casque ?')) return;

            if (this.wsClient) {
                this.wsClient.emitToModule('neurosity', 'disconnect', {});
            }
        }

        startMonitoring() {
            if (this.wsClient && this.isConnected && !this.isMonitoring) {
                console.log('Démarrage du monitoring Neurosity');
                this.wsClient.emitToModule('neurosity', 'start_monitoring', {});
            }
        }

        toggleRecording() {
            if (!this.isConnected) {
                this.showToast('Connectez d\'abord votre casque', 'warning');
                return;
            }

            const action = this.isRecording ? 'stop_recording' : 'start_recording';
            if (this.wsClient) {
                this.wsClient.emitToModule('neurosity', action, {});
            }
        }

        async downloadLatestSession() {
            try {
                const response = await fetch('/api/neurosity/sessions');
                const data = await response.json();

                if (data.sessions && data.sessions.length > 0) {
                    const latestSession = data.sessions[0];
                    this.downloadSession(latestSession);
                } else {
                    this.showToast('Aucune session disponible', 'warning');
                }
            } catch (error) {
                console.error('Erreur téléchargement:', error);
                this.showToast('Erreur de téléchargement', 'error');
            }
        }

        downloadSession(filename) {
            const link = document.createElement('a');
            link.href = `/api/neurosity/download/${filename}`;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            this.showToast(`Téléchargement: ${filename}`, 'success');
        }

        handleMetricData(type, data) {
            if (!this.isConnected) return;

            const value = data[type] || 0;
            this.updateCircularProgress(type, value, data.timestamp);
            this.flashIndicator(type);
        }

        handleBrainwavesData(data) {
            if (!this.isConnected || !this.charts.brainwaves) return;

            const powerData = ['delta', 'theta', 'alpha', 'beta', 'gamma'].map(
                wave => Math.min(data[wave] || 0, 20)
            );

            this.charts.brainwaves.data.datasets[0].data = powerData;
            this.charts.brainwaves.update('none');

            const timestampEl = document.getElementById('brainwavesTimestamp');
            if (timestampEl) {
                timestampEl.textContent = 'Dernière mise à jour: ' + this.formatTimestamp(data.timestamp);
            }

            this.flashIndicator('brainwaves');
        }

        handleSignalQualityData(data) {
            if (!this.isConnected) return;

            ['F5', 'F6', 'C3', 'C4', 'CP3', 'CP4', 'PO3', 'PO4'].forEach(electrode => {
                if (data[electrode] !== undefined) {
                    this.updateElectrodeQuality(electrode, data[electrode]);
                }
            });

            this.flashIndicator('signal_quality');
        }

        handleBrainwavesRawData(data) {
            if (!this.isConnected || !this.charts.eegRaw) return;

            this.charts.eegRaw.updateData(data.raw_data, data.info);

            const timestampEl = document.getElementById('eegRawTimestamp');
            if (timestampEl) {
                timestampEl.textContent = 'Dernière mise à jour: ' + this.formatTimestamp(data.timestamp);
            }

            this.flashIndicator('eeg_raw');
        }

        updateConnectionStatus(connected, recording, monitoring) {
            this.isConnected = connected;
            this.isRecording = recording;
            this.isMonitoring = monitoring;

            this.updateUI();
            this.updateSystemStatus(connected, monitoring);
        }

        updateUI() {
            const connectBtn = document.getElementById('connectBtn');
            if (connectBtn) {
                connectBtn.innerHTML = this.isConnected ?
                    '<i class="fas fa-unlink"></i><span class="neuro_btn-text">Déconnecter</span>' :
                    '<i class="fas fa-link"></i><span class="neuro_btn-text">Connecter</span>';
                connectBtn.className = this.isConnected ?
                    'neuro_btn neuro_btn-danger' : 'neuro_btn neuro_btn-primary';
                connectBtn.disabled = false;
            }

            const connectionStatus = document.getElementById('connectionStatus');
            const connectionText = document.getElementById('connectionText');
            if (connectionStatus && connectionText) {
                connectionStatus.className = this.isConnected ?
                    'neuro_status-dot neuro_status-connected' :
                    'neuro_status-dot neuro_status-disconnected';
                connectionText.textContent = this.isConnected ? 'Connecté' : 'Déconnecté';
            }

            const recordBtn = document.getElementById('recordBtn');
            if (recordBtn) {
                recordBtn.disabled = !this.isConnected;
                recordBtn.innerHTML = this.isRecording ?
                    '<i class="fas fa-stop"></i><span class="neuro_btn-text">Arrêter</span>' :
                    '<i class="fas fa-circle"></i><span class="neuro_btn-text">Enregistrer</span>';
                recordBtn.className = this.isRecording ?
                    'neuro_btn neuro_btn-danger' : 'neuro_btn neuro_btn-success';
            }

            const recordingStatus = document.getElementById('recordingStatus');
            if (recordingStatus) {
                recordingStatus.style.display = this.isRecording ? 'flex' : 'none';
            }

            const downloadBtn = document.getElementById('downloadBtn');
            if (downloadBtn) {
                downloadBtn.disabled = !this.isConnected;
            }
        }

        updateDeviceStatus(deviceStatus) {
            this.deviceStatus = deviceStatus;

            const deviceIndicator = document.getElementById('deviceStatusIndicator');
            const deviceDot = document.getElementById('deviceStatusDot');
            const deviceText = document.getElementById('deviceStatusText');

            if (deviceIndicator && deviceDot && deviceText) {
                if (deviceStatus.online) {
                    deviceIndicator.style.display = 'flex';
                    deviceDot.className = 'neuro_status-dot neuro_status-connected';

                    let statusText = 'Crown';
                    if (deviceStatus.battery !== undefined && deviceStatus.battery !== 'unknown') {
                        const batteryIcon = deviceStatus.charging ? '⚡' : '🔋';
                        statusText += ` ${batteryIcon} ${deviceStatus.battery}%`;
                    }

                    deviceText.textContent = statusText;
                } else {
                    deviceIndicator.style.display = 'none';
                }
            }
        }

        updateBatteryStatus(data) {
            if (!data || data.level === undefined) return;

            const level = data.level;
            const charging = data.charging;

            this.deviceStatus.battery = level;
            this.deviceStatus.charging = charging;

            let batteryIcon = charging ? '⚡' : (level <= 20 ? '🪫' : '🔋');
            let colorClass = level <= 20 ? 'battery-low' :
                            (level <= 50 ? 'battery-medium' : 'battery-good');

            const batteryEl = document.getElementById('systemBattery');
            if (batteryEl) {
                batteryEl.innerHTML = `<span class="${colorClass}">${batteryIcon} ${level}%</span>`;
                batteryEl.classList.toggle('battery-charging', charging);
            }

            this.updateDeviceStatus(this.deviceStatus);
        }

        updateMonitoringUI(monitoring) {
            const charts = document.querySelectorAll('.neuro_chart-card');
            charts.forEach(chart => {
                chart.style.borderLeft = monitoring ? '4px solid #10b981' : '';
                chart.style.boxShadow = monitoring ? '0 0 20px rgba(16, 185, 129, 0.1)' : '';
            });

            const monitoringStatus = document.getElementById('systemMonitoringStatus');
            if (monitoringStatus) {
                monitoringStatus.textContent = monitoring ? 'Actif' : 'Arrêté';
            }
        }

        updateCircularProgress(type, value, timestamp) {
            const circumference = 2 * Math.PI * 65;
            const progress = Math.min(Math.max(value, 0), 100);
            const offset = circumference - (progress / 100) * circumference;

            const progressEl = document.getElementById(`${type}Progress`);
            const valueEl = document.getElementById(`${type}Value`);
            const timestampEl = document.getElementById(`${type}Timestamp`);

            if (progressEl) {
                progressEl.style.strokeDasharray = circumference;
                progressEl.style.strokeDashoffset = offset;
            }

            if (valueEl) {
                valueEl.textContent = Math.round(progress) + '%';
            }

            if (timestampEl) {
                timestampEl.textContent = this.formatTimestamp(timestamp) + ' ✓';
            }
        }

        updateSystemStatus(connected, monitoring) {
            const connectionEl = document.getElementById('systemConnectionStatus');
            if (connectionEl) {
                connectionEl.textContent = connected ? 'Connecté' : 'Déconnecté';
            }

            const monitoringEl = document.getElementById('systemMonitoringStatus');
            if (monitoringEl) {
                monitoringEl.textContent = monitoring ? 'Actif' : 'Arrêté';
            }
        }

        updateElectrodeQuality(electrode, qualityData) {
            const electrodeEl = document.querySelector(`[data-electrode="${electrode}"]`);
            if (!electrodeEl) return;

            const status = qualityData.status || 'noContact';
            const valueEl = electrodeEl.querySelector('.neuro_electrode-svg-value');

            if (valueEl) {
                const displayText = {
                    'great': '100%',
                    'good': '75%',
                    'bad': '25%',
                    'noContact': '0%'
                };
                valueEl.textContent = displayText[status] || '0%';
            }

            electrodeEl.classList.remove('neuro_quality-good', 'neuro_quality-medium', 'neuro_quality-poor');

            const qualityClass = {
                'great': 'neuro_quality-good',
                'good': 'neuro_quality-medium',
                'bad': 'neuro_quality-poor',
                'noContact': 'neuro_quality-poor'
            };

            electrodeEl.classList.add(qualityClass[status] || 'neuro_quality-poor');
        }

        resetElectrodes() {
            document.querySelectorAll('.neuro_electrode-svg').forEach(el => {
                el.classList.remove('neuro_quality-good', 'neuro_quality-medium');
                el.classList.add('neuro_quality-poor');
                const valueEl = el.querySelector('.neuro_electrode-svg-value');
                if (valueEl) valueEl.textContent = '--%';
            });
        }

        flashIndicator(type) {
            const elements = {
                'calm': '.neuro_metric-card:nth-child(1)',
                'focus': '.neuro_metric-card:nth-child(2)',
                'brainwaves': '.neuro_chart-card',
                'signal_quality': '.neuro_signal-quality-section',
                'eeg_raw': '.neuro_eeg-raw-card'
            };

            const element = document.querySelector(elements[type]);
            if (element) {
                element.style.boxShadow = '0 0 20px rgba(139, 92, 246, 0.4)';
                setTimeout(() => element.style.boxShadow = '', 300);
            }
        }

        async loadSessions() {
            if (this.wsClient && this.wsClient.isConnected) {
                this.wsClient.emitToModule('neurosity', 'get_sessions', {});
            } else {
                try {
                    const response = await fetch('/api/neurosity/sessions');
                    const data = await response.json();
                    this.displaySessions(data.sessions || []);
                } catch (error) {
                    console.error('Erreur chargement sessions:', error);
                }
            }
        }

        displaySessions(sessions) {
            const sessionsList = document.getElementById('sessionsList');
            if (!sessionsList) return;

            this.sessions = sessions;

            const counter = document.getElementById('sessionsCounter');
            if (counter) {
                counter.textContent = sessions.length === 0 ?
                    'Aucune session' : `${sessions.length} session${sessions.length > 1 ? 's' : ''}`;
            }

            const totalSessionsEl = document.getElementById('totalSessions');
            if (totalSessionsEl) totalSessionsEl.textContent = sessions.length;

            const totalSizeEl = document.getElementById('totalSize');
            if (totalSizeEl) {
                totalSizeEl.textContent = sessions.length < 1 ? '0 KB' :
                    `${(sessions.length * 0.4).toFixed(1)} MB`;
            }

            if (sessions.length === 0) {
                sessionsList.innerHTML = `
                    <div class="neuro_sessions-empty">
                        Aucune session enregistrée
                        <div style="font-size: 0.75rem; margin-top: 0.5rem; opacity: 0.7;">
                            Connectez votre casque pour créer une session
                        </div>
                    </div>
                `;
                return;
            }

            sessionsList.innerHTML = sessions.map((session, index) => {
                const dateMatch = session.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
                let displayDate = 'Session';
                let displayTime = '';

                if (dateMatch) {
                    const [, year, month, day, hour, minute] = dateMatch;
                    displayDate = `${day}/${month}/${year}`;
                    displayTime = `${hour}:${minute}`;
                }

                return `
                    <div class="neuro_session-item" style="animation-delay: ${(index % 10) * 0.05}s">
                        <div class="neuro_session-info">
                            <div class="neuro_session-name">${session}</div>
                            <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 0.25rem;">
                                <span>📅 ${displayDate}</span>
                                <span style="margin-left: 1rem;">🕒 ${displayTime}</span>
                            </div>
                        </div>
                        <div class="neuro_session-actions">
                            <button class="neuro_btn neuro_btn-outline neuro_btn-small" 
                                    onclick="window.neurosityModuleInstance.downloadSession('${session}')"
                                    title="Télécharger CSV">
                                <i class="fas fa-download"></i> CSV
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
        }

        refreshSessions() {
            const btn = document.querySelector('.neuro_sessions-refresh-btn');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="neuro_btn-text">Actualisation...</span>';
            }

            this.showToast('Actualisation des sessions...', 'info', 2000);

            this.loadSessions().finally(() => {
                if (btn) {
                    setTimeout(() => {
                        btn.disabled = false;
                        btn.innerHTML = '<i class="fas fa-sync-alt"></i><span class="neuro_btn-text">Actualiser</span>';
                    }, 1000);
                }
            });
        }

        formatTimestamp(timestamp) {
            if (!timestamp) return '--';
            try {
                return new Date(timestamp).toLocaleTimeString('fr-FR');
            } catch {
                return '--';
            }
        }

        initClock() {
            const timeEl = document.getElementById('currentTime');
            if (!timeEl) return;

            const updateClock = () => {
                timeEl.textContent = new Date().toLocaleTimeString('fr-FR');
            };

            updateClock();
            setInterval(updateClock, 1000);
        }

        showToast(message, type = 'info', duration = null) {
            let container = document.getElementById('neurosityToastContainer');
            if (!container) {
                container = document.createElement('div');
                container.id = 'neurosityToastContainer';
                container.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    z-index: 9999;
                    display: flex;
                    flex-direction: column;
                    gap: 10px;
                    max-width: 450px;
                `;
                document.body.appendChild(container);
            }

            const colors = {
                success: 'linear-gradient(135deg, #10b981 0%, #34d399 100%)',
                error: 'linear-gradient(135deg, #ef4444 0%, #f87171 100%)',
                warning: 'linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)',
                info: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)'
            };

            const icons = {
                success: '✅',
                error: '❌',
                warning: '⚠️',
                info: '💡'
            };

            const toast = document.createElement('div');
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
                backdrop-filter: blur(10px);
                background: ${colors[type] || colors.info};
            `;

            toast.innerHTML = `
                <div style="display: flex; align-items: flex-start; gap: 12px;">
                    <div style="font-size: 18px;">${icons[type] || icons.info}</div>
                    <div style="flex: 1;">${message}</div>
                    <div style="cursor: pointer; opacity: 0.8;" onclick="this.parentElement.parentElement.remove()">×</div>
                </div>
            `;

            container.appendChild(toast);
            setTimeout(() => toast.style.transform = 'translateX(0)', 10);

            const finalDuration = duration || this.config.toastDuration;
            if (finalDuration > 0) {
                setTimeout(() => {
                    toast.style.transform = 'translateX(100%)';
                    setTimeout(() => toast.remove(), 300);
                }, finalDuration);
            }
        }

        cleanup() {
            console.log('Nettoyage du module Neurosity...');

            this.cleanupHandlers();

            if (this.isMonitoring && this.wsClient) {
                this.wsClient.emitToModule('neurosity', 'stop_monitoring', {});
            }

            if (this.charts.brainwaves) {
                this.charts.brainwaves.destroy();
                this.charts.brainwaves = null;
            }

            if (this.charts.eegRaw) {
                this.charts.eegRaw = null;
            }

            console.log('Module Neurosity nettoyé');
        }
    }

    // Classe EEGRawChart
    class EEGRawChart {
        constructor(canvas) {
            this.canvas = canvas;
            this.ctx = canvas.getContext('2d');
            this.channelNames = ['CP3', 'C3', 'F5', 'PO3', 'PO4', 'F6', 'C4', 'CP4'];
            this.colors = [
                '#6366f1', '#0ea5e9', '#8b5cf6', '#a855f7',
                '#f59e0b', '#06b6d4', '#3b82f6', '#1e293b'
            ];

            this.dataBuffer = [];
            this.timeBuffer = [];
            this.maxBufferSize = 256 * 4;

            this.amplitudeScale = 2;
            this.margins = { left: 60, right: 50, top: 30, bottom: 40 };

            this.gridColor = 'rgba(226, 232, 240, 0.5)';
            this.gridTextColor = '#94a3b8';

            this.resize();
            window.addEventListener('resize', () => this.resize());
        }

        resize() {
            const rect = this.canvas.getBoundingClientRect();
            this.canvas.width = rect.width * window.devicePixelRatio;
            this.canvas.height = rect.height * window.devicePixelRatio;
            this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

            this.width = rect.width;
            this.height = rect.height;
            this.plotWidth = this.width - this.margins.left - this.margins.right;
            this.plotHeight = this.height - this.margins.top - this.margins.bottom;

            this.draw();
        }

        updateData(rawData, info) {
            if (rawData && rawData.length === 8) {
                const timestamp = Date.now();
                const numSamples = rawData[0].length;

                for (let i = 0; i < numSamples; i++) {
                    const sample = rawData.map(ch => ch[i]);
                    this.dataBuffer.push(sample);
                    this.timeBuffer.push(timestamp + (i * 1000 / 256));
                }

                if (this.dataBuffer.length > this.maxBufferSize) {
                    const excess = this.dataBuffer.length - this.maxBufferSize;
                    this.dataBuffer = this.dataBuffer.slice(excess);
                    this.timeBuffer = this.timeBuffer.slice(excess);
                }

                this.draw();
            }
        }

        draw() {
            this.ctx.clearRect(0, 0, this.width, this.height);
            this.drawGrid();
            this.drawChannelLabels();
            this.drawTimeScale();

            if (this.dataBuffer.length > 1) {
                this.drawSignals();
            }
        }

        drawGrid() {
            this.ctx.strokeStyle = this.gridColor;
            this.ctx.lineWidth = 1;

            for (let ch = 0; ch < 8; ch++) {
                const yBase = this.margins.top + (ch + 0.5) * (this.plotHeight / 8);
                this.ctx.beginPath();
                this.ctx.moveTo(this.margins.left, yBase);
                this.ctx.lineTo(this.width - this.margins.right, yBase);
                this.ctx.stroke();
            }

            const gridSpacing = this.plotWidth / 4;
            for (let i = 0; i <= 4; i++) {
                const x = this.margins.left + i * gridSpacing;
                this.ctx.beginPath();
                this.ctx.moveTo(x, this.margins.top);
                this.ctx.lineTo(x, this.height - this.margins.bottom);
                this.ctx.stroke();
            }

            this.ctx.strokeRect(this.margins.left, this.margins.top, this.plotWidth, this.plotHeight);
        }

        drawChannelLabels() {
            this.ctx.font = '12px Inter';
            this.ctx.textAlign = 'right';
            this.ctx.textBaseline = 'middle';

            for (let ch = 0; ch < 8; ch++) {
                const yBase = this.margins.top + (ch + 0.5) * (this.plotHeight / 8);
                this.ctx.fillStyle = this.colors[ch];
                this.ctx.fillText(this.channelNames[ch], this.margins.left - 10, yBase);
            }
        }

        drawTimeScale() {
            this.ctx.font = '11px Inter';
            this.ctx.fillStyle = this.gridTextColor;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'top';

            for (let i = 0; i <= 4; i++) {
                const x = this.margins.left + i * (this.plotWidth / 4);
                this.ctx.fillText(`-${4 - i}s`, x, this.height - this.margins.bottom + 10);
            }
        }

        drawSignals() {
            const pixelsPerSample = this.plotWidth / this.dataBuffer.length;

            for (let ch = 0; ch < 8; ch++) {
                const yBase = this.margins.top + (ch + 0.5) * (this.plotHeight / 8);

                this.ctx.save();
                this.ctx.beginPath();
                this.ctx.rect(
                    this.margins.left,
                    this.margins.top + ch * (this.plotHeight / 8),
                    this.plotWidth,
                    this.plotHeight / 8
                );
                this.ctx.clip();

                this.ctx.strokeStyle = this.colors[ch];
                this.ctx.lineWidth = 1.5;
                this.ctx.beginPath();

                for (let i = 0; i < this.dataBuffer.length; i++) {
                    const x = this.margins.left + i * pixelsPerSample;
                    const y = yBase - (this.dataBuffer[i][ch] * this.amplitudeScale);

                    if (i === 0) {
                        this.ctx.moveTo(x, y);
                    } else {
                        this.ctx.lineTo(x, y);
                    }
                }

                this.ctx.stroke();
                this.ctx.restore();
            }
        }
    }

    // Exposer les classes
    window.NeurosityModuleClass = NeurosityModule;
    window.EEGRawChart = EEGRawChart;

    // Créer une instance unique
    window.initNeurosityModule = function() {
        console.log('initNeurosityModule appelée');
        if (!window.neurosityModuleInstance) {
            window.neurosityModuleInstance = new NeurosityModule();
        } else {
            console.log('Instance Neurosity existante réutilisée');
            if (typeof window.neurosityModuleInstance.reinit === 'function') {
                window.neurosityModuleInstance.reinit();
            }
        }
        return window.neurosityModuleInstance;
    };

    // Fonctions globales
    window.connectDevice = function() {
        if (window.neurosityModuleInstance) {
            window.neurosityModuleInstance.connect();
        }
    };

    window.disconnectDevice = function() {
        if (window.neurosityModuleInstance) {
            window.neurosityModuleInstance.disconnect();
        }
    };

    window.toggleRecording = function() {
        if (window.neurosityModuleInstance) {
            window.neurosityModuleInstance.toggleRecording();
        }
    };

    window.downloadData = function() {
        if (window.neurosityModuleInstance) {
            window.neurosityModuleInstance.downloadLatestSession();
        }
    };

    window.refreshSessions = function() {
        if (window.neurosityModuleInstance) {
            window.neurosityModuleInstance.refreshSessions();
        }
    };

})();