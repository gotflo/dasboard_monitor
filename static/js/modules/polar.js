/**
 * Module Polar - Gestion des capteurs cardiaques Polar H10 et Verity Sense
 * Interface JavaScript pour la connexion, monitoring et enregistrement des données
 * Version avec support de persistance pour le dashboard
 */

class PolarModule {
    constructor() {
        // Configuration
        this.wsClient = null;
        this.isInitialized = false;

        // État des appareils
        this.devices = {
            h10: {
                connected: false,
                collecting: false,
                data: null,
                chart: null,
                chartData: []
            },
            verity: {
                connected: false,
                collecting: false,
                data: null,
                chart: null,
                chartData: []
            }
        };

        // État de l'enregistrement
        this.recording = {
            isRecording: false,
            startTime: null,
            duration: 0,
            interval: null
        };

        // Configuration des graphiques
        this.chartConfig = {
            maxDataPoints: 100,
            updateInterval: 1000
        };

        // Timer pour mise à jour
        this.updateTimer = null;
    }

    /**
     * Initialisation du module
     */
    init() {
        console.log('Initialisation du module Polar');

        // Vérifier si déjà initialisé
        if (this.isInitialized) {
            console.log('Module Polar déjà initialisé - réactivation');
            // Ne pas réinitialiser les graphiques, juste réactiver
            if (this.wsClient && this.wsClient.isConnected) {
                this.wsClient.emitToModule('polar', 'get_status', {});
            }
            return;
        }

        // Récupérer l'instance WebSocket du dashboard
        this.wsClient = window.dashboard?.wsClient;

        if (!this.wsClient) {
            console.error('WebSocket non disponible - connexion requise');
            this.showToast('Erreur: WebSocket non disponible', 'error');
            return;
        }

        // S'abonner au module
        if (this.wsClient.isConnected) {
            this.wsClient.subscribeToModule('polar').then(() => {
                console.log('Abonné au module Polar');
            }).catch(err => {
                console.error('Erreur abonnement module:', err);
            });
        }

        // Initialiser les événements WebSocket
        this.initWebSocketEvents();

        // Initialiser l'interface
        this.initUI();

        // Détruire les graphiques existants avant de les recréer
        this.destroyCharts();
        this.initCharts();

        // Demander le statut initial
        if (this.wsClient.isConnected) {
            this.wsClient.emitToModule('polar', 'get_status', {});
        }

        this.isInitialized = true;
        console.log('Module Polar initialisé');
    }

    /**
     * Initialisation de l'interface utilisateur
     */
    initUI() {
        // Boutons principaux
        this.setupMainControls();

        // Modal de connexion
        this.setupConnectionModal();

        // Contrôles CSV
        this.setupCSVControls();

        // Modal de téléchargement
        this.setupDownloadModal();

        // Mise à jour initiale de l'UI
        this.updateUI();
    }

    /**
     * Configuration des contrôles principaux
     */
    setupMainControls() {
        // Bouton de connexion
        const connectBtn = document.getElementById('polar_connectBtn');
        if (connectBtn) {
            connectBtn.addEventListener('click', () => this.scanForDevices());
        }

        // Bouton de déconnexion
        const disconnectBtn = document.getElementById('polar_disconnectBtn');
        if (disconnectBtn) {
            disconnectBtn.addEventListener('click', () => this.disconnectAllDevices());
        }
    }

    /**
     * Configuration de la modal de connexion
     */
    setupConnectionModal() {
        // Bouton fermer
        const closeBtn = document.getElementById('polar_modalCloseBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                // Utiliser la version forcée
                this.forceShowMonitoring();
            });
        }

        // Clic en dehors de la modal
        const modal = document.getElementById('polar_connectionModal');
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    // Utiliser la version forcée
                    this.forceShowMonitoring();
                }
            });
        }
    }

    /**
     * Configuration des contrôles CSV
     */
    setupCSVControls() {
        // Bouton enregistrement
        const recordBtn = document.getElementById('polar_recordToggleBtn');
        if (recordBtn) {
            recordBtn.addEventListener('click', () => this.toggleRecording());
        }

        // Bouton téléchargement
        const downloadBtn = document.getElementById('polar_downloadBtn');
        if (downloadBtn) {
            downloadBtn.addEventListener('click', () => this.showDownloadModal());
        }
    }

    /**
     * Configuration de la modal de téléchargement
     */
    setupDownloadModal() {
        // Bouton fermer
        const closeBtn = document.getElementById('polar_closeDownloadModalBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.closeDownloadModal());
        }

        // Bouton télécharger tout
        const downloadAllBtn = document.getElementById('polar_downloadAllBtn');
        if (downloadAllBtn) {
            downloadAllBtn.addEventListener('click', () => this.downloadAllFiles());
        }
    }

    /**
     * Détruit les graphiques existants
     */
    destroyCharts() {
        // Détruire le graphique H10
        if (this.devices.h10.chart) {
            try {
                this.devices.h10.chart.destroy();
                this.devices.h10.chart = null;
            } catch (e) {
                console.warn('Erreur destruction chart H10:', e);
            }
        }

        // Détruire le graphique Verity
        if (this.devices.verity.chart) {
            try {
                this.devices.verity.chart.destroy();
                this.devices.verity.chart = null;
            } catch (e) {
                console.warn('Erreur destruction chart Verity:', e);
            }
        }
    }

    /**
     * Initialisation des graphiques
     */
    initCharts() {
        // Vérifier si les graphiques existent déjà
        if (this.devices.h10.chart || this.devices.verity.chart) {
            console.log('Graphiques déjà initialisés');
            return;
        }

        // Configuration commune
        const commonOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 0
            },
            scales: {
                x: {
                    display: false
                },
                y: {
                    beginAtZero: false,
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    },
                    ticks: {
                        font: {
                            size: 10
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: false
                }
            }
        };

        // Chart H10
        const h10Canvas = document.getElementById('polar_h10Chart');
        if (h10Canvas && window.Chart) {
            // Vérifier que le canvas n'est pas déjà utilisé
            const existingChart = Chart.getChart(h10Canvas);
            if (existingChart) {
                existingChart.destroy();
            }

            this.devices.h10.chart = new Chart(h10Canvas, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        data: [],
                        borderColor: '#f87171',
                        borderWidth: 2,
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0
                    }]
                },
                options: {
                    ...commonOptions,
                    scales: {
                        ...commonOptions.scales,
                        y: {
                            ...commonOptions.scales.y,
                            title: {
                                display: true,
                                text: 'RR (ms)',
                                font: {
                                    size: 11
                                }
                            }
                        }
                    }
                }
            });
        }

        // Chart Verity
        const verityCanvas = document.getElementById('polar_verityChart');
        if (verityCanvas && window.Chart) {
            // Vérifier que le canvas n'est pas déjà utilisé
            const existingChart = Chart.getChart(verityCanvas);
            if (existingChart) {
                existingChart.destroy();
            }

            this.devices.verity.chart = new Chart(verityCanvas, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        data: [],
                        borderColor: '#667eea',
                        borderWidth: 2,
                        fill: false,
                        tension: 0.1,
                        pointRadius: 0
                    }]
                },
                options: {
                    ...commonOptions,
                    scales: {
                        ...commonOptions.scales,
                        y: {
                            ...commonOptions.scales.y,
                            title: {
                                display: true,
                                text: 'RR (ms)',
                                font: {
                                    size: 11
                                }
                            }
                        }
                    }
                }
            });
        }
    }

    /**
     * Événements WebSocket
     */
    initWebSocketEvents() {
        if (!this.wsClient) return;

        // Nettoyage des anciens écouteurs
        this.cleanupWebSocketEvents();

        // Scan devices
        this.wsClient.on('polar_scan_started', (data) => console.log('Scan démarré:', data));
        this.wsClient.on('devices_found', (data) => this.handleDevicesFound(data));
        this.wsClient.on('scan_retry', (data) => this.handleScanRetry(data));

        // Connexion/Déconnexion
        this.wsClient.on('h10_connected', (data) => this.handleDeviceConnected('h10', data));
        this.wsClient.on('verity_connected', (data) => this.handleDeviceConnected('verity', data));
        this.wsClient.on('h10_disconnected', () => this.handleDeviceDisconnected('h10'));
        this.wsClient.on('verity_disconnected', () => this.handleDeviceDisconnected('verity'));

        // Données temps réel
        this.wsClient.on('h10_data', (data) => this.handleDeviceData('h10', data));
        this.wsClient.on('verity_data', (data) => this.handleDeviceData('verity', data));

        // Statut
        this.wsClient.on('h10_status', (data) => this.handleDeviceStatus('h10', data));
        this.wsClient.on('verity_status', (data) => this.handleDeviceStatus('verity', data));
        this.wsClient.on('polar_status', (data) => this.handleGlobalStatus(data));

        // CSV
        this.wsClient.on('csv_recording_started', (data) => this.handleRecordingStarted(data));
        this.wsClient.on('csv_recording_stopped', (data) => this.handleRecordingStopped(data));
        this.wsClient.on('polar_csv_files', (data) => this.handleCSVFilesList(data));

        // Erreurs
        this.wsClient.on('error', (data) => this.handleError(data));
        this.wsClient.on('polar_error', (data) => this.handleError(data));
        this.wsClient.on('polar_connect_result', (data) => this.handleConnectResult(data));
    }

    /**
     * Nettoyage des événements WebSocket
     */
    cleanupWebSocketEvents() {
        if (!this.wsClient) return;

        const events = [
            'polar_scan_started', 'devices_found', 'scan_retry',
            'h10_connected', 'verity_connected', 'h10_disconnected', 'verity_disconnected',
            'h10_data', 'verity_data', 'h10_status', 'verity_status', 'polar_status',
            'csv_recording_started', 'csv_recording_stopped', 'polar_csv_files',
            'error', 'polar_error', 'polar_connect_result'
        ];

        events.forEach(event => this.wsClient.off(event));
    }

    /**
     * Lance le scan Bluetooth pour trouver les appareils
     */
    async scanForDevices() {
        if (!this.wsClient || !this.wsClient.isConnected) {
            this.showToast('Erreur: Connexion WebSocket requise', 'error');
            return;
        }

        const modal = document.getElementById('polar_connectionModal');
        const devicesList = document.getElementById('polar_devicesList');
        const noDevices = document.getElementById('polar_noDevices');

        if (!modal || !devicesList) return;

        // Réinitialiser
        devicesList.innerHTML = '';
        noDevices.style.display = 'none';

        // Afficher le chargement
        this.showLoading('Recherche des appareils...', 'Scan Bluetooth en cours');
        modal.classList.add('polar_active');

        // Demander le scan au backend avec retry automatique
        this.wsClient.emitToModule('polar', 'scan_devices', {
            timeout: 10000, // 10 secondes de scan
            max_retries: 3  // 3 tentatives maximum
        });
    }

    /**
     * Gère la liste des appareils trouvés
     */
    handleDevicesFound(data) {
        console.log('Appareils trouvés:', data);

        this.hideLoading();

        const devicesList = document.getElementById('polar_devicesList');
        const noDevices = document.getElementById('polar_noDevices');

        if (!data.devices || data.devices.length === 0) {
            noDevices.style.display = 'block';
            devicesList.innerHTML = '';

            // Afficher le message si présent
            if (data.message) {
                const messageEl = noDevices.querySelector('p');
                if (messageEl) {
                    messageEl.textContent = data.message;
                }
            }
        } else {
            noDevices.style.display = 'none';
            devicesList.innerHTML = '';

            data.devices.forEach(device => {
                this.addDeviceToModal(device);
            });
        }
    }

    /**
     * Gère les tentatives de retry du scan
     */
    handleScanRetry(data) {
        console.log('Retry scan:', data);

        // Mettre à jour le texte de chargement
        const loadingText = document.getElementById('polar_loadingText');
        if (loadingText) {
            loadingText.textContent = data.message || `Tentative ${data.attempt}/${data.max_retries}...`;
        }

        // Afficher un toast informatif
        this.showToast(data.message, 'info');
    }

    /**
     * Ajoute un appareil à la modal
     */
    addDeviceToModal(device) {
        const devicesList = document.getElementById('polar_devicesList');
        if (!devicesList) return;

        const template = document.getElementById('polar_deviceCardTemplate');
        if (!template) return;

        const deviceCard = template.content.cloneNode(true);
        const option = deviceCard.querySelector('.polar_device-option');

        // Configurer les données
        option.setAttribute('data-device-id', device.device_address);
        option.setAttribute('data-device-type', device.device_type);

        // Nom et ID
        option.querySelector('.polar_device-name').textContent = device.name;
        option.querySelector('.polar_device-id').textContent = this.formatDeviceId(device.device_address);

        // Signal
        const signal = device.rssi || -50;
        const signalStrength = this.calculateSignalStrength(signal);
        option.querySelector('.polar_device-signal').textContent = `Signal: ${signalStrength}%`;

        // Icône appropriée
        const icon = option.querySelector('.polar_device-option-icon i');
        if (device.device_type === 'h10') {
            icon.className = 'fas fa-heartbeat';
        } else {
            icon.className = 'fas fa-user-clock';
        }

        // Bouton de connexion
        const connectBtn = option.querySelector('.polar_connect-btn');
        connectBtn.addEventListener('click', () => this.connectDevice(device.device_type, device.device_address));

        // Vérifier si déjà connecté
        if (this.devices[device.device_type]?.connected) {
            option.classList.add('polar_connected');
            connectBtn.innerHTML = '<i class="fas fa-check"></i> Connecté';
            connectBtn.disabled = true;
        }

        devicesList.appendChild(deviceCard);
    }

    /**
     * Connecte à un appareil
     */
    async connectDevice(deviceType, deviceAddress) {
        console.log(`Connexion à ${deviceType}: ${deviceAddress}`);

        if (!this.wsClient || !this.wsClient.isConnected) {
            this.showToast('Erreur: Connexion WebSocket requise', 'error');
            return;
        }

        const deviceOption = document.querySelector(`[data-device-id="${deviceAddress}"]`);
        if (deviceOption) {
            deviceOption.classList.add('polar_connecting');
            const btn = deviceOption.querySelector('.polar_connect-btn');
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            btn.disabled = true;
        }

        // Envoyer la demande de connexion
        this.wsClient.emitToModule('polar', 'connect_device', {
            device_type: deviceType,
            device_address: deviceAddress
        });

        // Timeout de sécurité : si après 10 secondes on n'a pas de réponse, forcer la vérification
        setTimeout(() => {
            // Si on reçoit des données mais que la modal est toujours ouverte
            if (this.devices[deviceType].data && this.devices[deviceType].data.heart_rate > 0) {
                const modal = document.getElementById('polar_connectionModal');
                if (modal && modal.classList.contains('polar_active')) {
                    console.log('Timeout de sécurité - fermeture forcée de la modal');
                    this.forceShowMonitoring();
                }
            }
        }, 10000);
    }

    /**
     * Déconnecte tous les appareils
     */
    async disconnectAllDevices() {
        console.log('Déconnexion de tous les appareils');

        if (!this.wsClient || !this.wsClient.isConnected) {
            this.showToast('Erreur: Connexion WebSocket requise', 'error');
            return;
        }

        // Arrêter l'enregistrement si actif
        if (this.recording.isRecording) {
            await this.stopRecording();
        }

        // Déconnecter chaque appareil
        for (const [deviceType, device] of Object.entries(this.devices)) {
            if (device.connected) {
                this.wsClient.emitToModule('polar', 'disconnect_device', {
                    device_type: deviceType
                });
            }
        }

        // Réinitialiser complètement l'interface après un court délai
        setTimeout(() => {
            this.resetInterface();
        }, 500);
    }

    /**
     * Réinitialise complètement l'interface
     */
    resetInterface() {
        console.log('Réinitialisation complète de l\'interface');

        // Animation de fermeture
        const grid = document.getElementById('polar_monitoringGrid');
        if (grid) {
            grid.style.opacity = '0.3';
            grid.style.transform = 'scale(0.98)';
        }

        setTimeout(() => {
            // Réinitialiser l'état de tous les appareils
            for (const [deviceType, device] of Object.entries(this.devices)) {
                // État
                device.connected = false;
                device.collecting = false;
                device.data = null;

                // Graphique
                if (device.chart) {
                    device.chartData = [];
                    device.chart.data.labels = [];
                    device.chart.data.datasets[0].data = [];
                    device.chart.update();
                }

                // UI de la carte
                const card = document.getElementById(`polar_${deviceType}Card`);
                if (card) {
                    card.classList.remove('polar_active');
                    card.classList.add('polar_inactive');
                    card.style.display = ''; // S'assurer que la carte est visible
                }

                // Overlay du graphique
                const overlay = document.getElementById(`polar_${deviceType}ChartOverlay`);
                if (overlay) {
                    overlay.classList.add('polar_active');
                }

                // Réinitialiser toutes les valeurs
                this.resetDeviceValues(deviceType);
            }

            // Réinitialiser la grille en mode dual
            if (grid) {
                grid.classList.remove('polar_single-device');
                // Animation d'ouverture
                setTimeout(() => {
                    grid.style.opacity = '1';
                    grid.style.transform = 'scale(1)';
                }, 50);
            }

            const comparison = document.getElementById('polar_comparisonPanel');
            if (comparison) {
                comparison.classList.remove('polar_single-mode');
            }

            // Réinitialiser les métriques de comparaison
            const comparisonElements = ['polar_hrDifference', 'polar_rrDifference', 'polar_breathingSync'];
            comparisonElements.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = '--';
            });

            // Mettre à jour l'UI globale
            this.updateUI();

            console.log('Interface réinitialisée');
        }, 200);
    }

    /**
     * Réinitialise toutes les valeurs d'un appareil
     */
    resetDeviceValues(deviceType) {
        const prefix = `polar_${deviceType}`;

        // Réinitialiser toutes les métriques
        const elements = {
            // Valeurs principales
            [`${prefix}HeartRate`]: '--',
            [`${prefix}DeviceId`]: 'Non connecté',

            // RR Intervals
            [`${prefix}LastRR`]: '--',
            [`${prefix}MeanRR`]: '--',
            [`${prefix}RMSSD`]: '--',

            // BPM Stats
            [`${prefix}MeanBPM`]: '--',
            [`${prefix}MinBPM`]: '--',
            [`${prefix}MaxBPM`]: '--',

            // Respiration
            [`${prefix}BreathingFreq`]: '--',
            [`${prefix}BreathingAmp`]: '--',
            [`${prefix}BreathingQuality`]: '--',

            // Zone
            [`${prefix}ZoneLabel`]: 'En attente'
        };

        // Appliquer les réinitialisations
        Object.entries(elements).forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = value;
                // Retirer les classes de qualité pour breathing quality
                if (id.includes('BreathingQuality')) {
                    el.className = 'polar_metric-value';
                }
            }
        });

        // Réinitialiser le statut
        const statusEl = document.getElementById(`${prefix}Status`);
        if (statusEl) {
            const statusDot = statusEl.querySelector('.polar_status-dot');
            const statusText = statusEl.querySelector('span:last-child');
            if (statusDot) {
                statusDot.classList.remove('polar_connected');
            }
            if (statusText) {
                statusText.textContent = 'Déconnecté';
            }
        }

        // Réinitialiser la zone cardiaque
        const zoneIndicator = document.getElementById(`${prefix}ZoneIndicator`);
        if (zoneIndicator) {
            zoneIndicator.style.background = '#e0f2fe';
            zoneIndicator.style.color = '#0369a1';
        }
    }

    /**
     * Force l'affichage de l'interface de monitoring
     */
    forceShowMonitoring() {
        console.log('Force affichage du monitoring');

        // Fermer toutes les modals
        const connectionModal = document.getElementById('polar_connectionModal');
        if (connectionModal) {
            connectionModal.classList.remove('polar_active');
            // Forcer le style pour être sûr
            connectionModal.style.display = 'none';
            connectionModal.style.opacity = '0';
            connectionModal.style.visibility = 'hidden';
        }

        const downloadModal = document.getElementById('polar_downloadModal');
        if (downloadModal) {
            downloadModal.classList.remove('polar_active');
            downloadModal.style.display = 'none';
        }

        // Cacher l'overlay de chargement
        this.hideLoading();

        // S'assurer que l'interface principale est visible
        const monitoringGrid = document.getElementById('polar_monitoringGrid');
        if (monitoringGrid) {
            monitoringGrid.style.display = 'grid';
            monitoringGrid.style.opacity = '1';
            monitoringGrid.style.visibility = 'visible';
        }

        // S'assurer que le conteneur principal est visible
        const moduleContainer = document.querySelector('.polar_module-container');
        if (moduleContainer) {
            moduleContainer.style.display = 'block';
            moduleContainer.style.opacity = '1';
            moduleContainer.style.visibility = 'visible';
        }

        // Mettre à jour l'UI
        this.updateUI();

        console.log('Interface de monitoring forcée à l\'affichage');
    }

    /**
     * Gère la connexion d'un appareil
     */
    handleDeviceConnected(deviceType, data) {
        console.log(`${deviceType} connecté (événement direct):`, data);

        // Si déjà marqué comme connecté, ne pas refaire
        if (this.devices[deviceType].connected) {
            console.log(`${deviceType} déjà marqué comme connecté`);
            return;
        }

        this.devices[deviceType].connected = true;
        this.devices[deviceType].collecting = true;

        // Mettre à jour l'UI
        this.updateDeviceUI(deviceType, true);

        // Fermer la modal immédiatement
        this.forceShowMonitoring();
    }

    /**
     * Gère la déconnexion d'un appareil
     */
    handleDeviceDisconnected(deviceType) {
        console.log(`${deviceType} déconnecté`);

        this.devices[deviceType].connected = false;
        this.devices[deviceType].collecting = false;
        this.devices[deviceType].data = null;

        // Réinitialiser le graphique
        if (this.devices[deviceType].chart) {
            this.devices[deviceType].chartData = [];
            this.devices[deviceType].chart.data.labels = [];
            this.devices[deviceType].chart.data.datasets[0].data = [];
            this.devices[deviceType].chart.update();
        }

        this.updateDeviceUI(deviceType, false);
        this.showToast(`${deviceType.toUpperCase()} déconnecté`, 'info');
    }

    /**
     * Gère les données reçues d'un appareil
     */
    handleDeviceData(deviceType, data) {
        // Si on reçoit des données mais que l'appareil n'est pas marqué comme connecté
        if (!this.devices[deviceType].connected && data.data && data.data.heart_rate !== undefined) {
            console.log(`Données reçues pour ${deviceType} non connecté - connexion implicite`);
            this.devices[deviceType].connected = true;
            this.devices[deviceType].collecting = true;
            this.updateDeviceUI(deviceType, true);

            // Forcer l'affichage si la modal est encore ouverte
            const modal = document.getElementById('polar_connectionModal');
            if (modal && modal.classList.contains('polar_active')) {
                setTimeout(() => this.forceShowMonitoring(), 500);
            }
        }

        // Stocker les données
        this.devices[deviceType].data = data.data;

        // Mettre à jour l'UI
        this.updateDeviceData(deviceType, data.data);

        // Mettre à jour le graphique
        this.updateChart(deviceType, data.data);

        // Mettre à jour la comparaison si les deux sont connectés
        if (this.devices.h10.connected && this.devices.verity.connected) {
            this.updateComparison();
        }
    }

    /**
     * Met à jour les données d'un appareil dans l'UI
     */
    updateDeviceData(deviceType, data) {
        const prefix = `polar_${deviceType}`;

        // BPM
        const heartRateEl = document.getElementById(`${prefix}HeartRate`);
        if (heartRateEl && data.heart_rate) {
            heartRateEl.textContent = data.heart_rate;

            // Animation du cœur
            const heartIcon = document.getElementById(`${prefix}HeartIcon`);
            if (heartIcon) {
                heartIcon.classList.add('polar_beating');
                setTimeout(() => heartIcon.classList.remove('polar_beating'), 600);
            }
        }

        // Zone cardiaque
        const zoneLabel = document.getElementById(`${prefix}ZoneLabel`);
        if (zoneLabel && data.heart_rate) {
            const zone = this.calculateHeartRateZone(data.heart_rate);
            zoneLabel.textContent = zone.label;

            const zoneIndicator = document.getElementById(`${prefix}ZoneIndicator`);
            if (zoneIndicator) {
                zoneIndicator.style.background = zone.color;
                zoneIndicator.style.color = zone.textColor;
            }
        }

        // Métriques temps réel
        if (data.real_time_metrics) {
            const metrics = data.real_time_metrics;

            // RR Intervals
            this.updateMetric(`${prefix}LastRR`, metrics.rr_metrics?.last_rr);
            this.updateMetric(`${prefix}MeanRR`, metrics.rr_metrics?.mean_rr);
            this.updateMetric(`${prefix}RMSSD`, metrics.rr_metrics?.rmssd);

            // BPM Stats
            this.updateMetric(`${prefix}MeanBPM`, metrics.bpm_metrics?.mean_bpm);
            this.updateMetric(`${prefix}MinBPM`, metrics.bpm_metrics?.min_bpm);
            this.updateMetric(`${prefix}MaxBPM`, metrics.bpm_metrics?.max_bpm);

            // Respiration
            this.updateMetric(`${prefix}BreathingFreq`, metrics.breathing_metrics?.frequency);
            this.updateMetric(`${prefix}BreathingAmp`, metrics.breathing_metrics?.amplitude);

            const qualityEl = document.getElementById(`${prefix}BreathingQuality`);
            if (qualityEl && metrics.breathing_metrics?.quality) {
                qualityEl.textContent = this.translateQuality(metrics.breathing_metrics.quality);
                qualityEl.className = `polar_metric-value quality-${metrics.breathing_metrics.quality}`;
            }
        }
    }

    /**
     * Met à jour une métrique
     */
    updateMetric(elementId, value) {
        const el = document.getElementById(elementId);
        if (el && value !== undefined && value !== null) {
            el.textContent = value === 0 ? '--' : value;
            el.classList.add('polar_updating');
            setTimeout(() => el.classList.remove('polar_updating'), 300);
        }
    }

    /**
     * Met à jour le graphique
     */
    updateChart(deviceType, data) {
        const device = this.devices[deviceType];
        if (!device.chart || !data.real_time_metrics?.rr_metrics) return;

        const rrValue = data.real_time_metrics.rr_metrics.last_rr;
        if (rrValue && rrValue > 0) {
            // Ajouter la nouvelle valeur
            device.chartData.push(rrValue);

            // Limiter le nombre de points
            if (device.chartData.length > this.chartConfig.maxDataPoints) {
                device.chartData.shift();
            }

            // Mettre à jour le graphique
            const labels = device.chartData.map((_, i) => i);
            device.chart.data.labels = labels;
            device.chart.data.datasets[0].data = device.chartData;
            device.chart.update('none');

            // Masquer l'overlay si c'est la première donnée
            const overlay = document.getElementById(`${deviceType === 'h10' ? 'polar_h10' : 'polar_verity'}ChartOverlay`);
            if (overlay && overlay.classList.contains('polar_active')) {
                overlay.classList.remove('polar_active');
            }
        }
    }

    /**
     * Met à jour la comparaison
     */
    updateComparison() {
        const h10Data = this.devices.h10.data;
        const verityData = this.devices.verity.data;

        if (!h10Data || !verityData) return;

        // Différence BPM
        const hrDiffEl = document.getElementById('polar_hrDifference');
        if (hrDiffEl && h10Data.heart_rate && verityData.heart_rate) {
            const diff = Math.abs(h10Data.heart_rate - verityData.heart_rate);
            hrDiffEl.textContent = diff;
            hrDiffEl.style.color = diff > 5 ? '#ef4444' : '#10b981';
        }

        // Sync RR
        const rrDiffEl = document.getElementById('polar_rrDifference');
        if (rrDiffEl && h10Data.real_time_metrics?.rr_metrics && verityData.real_time_metrics?.rr_metrics) {
            const diff = Math.abs(
                h10Data.real_time_metrics.rr_metrics.mean_rr -
                verityData.real_time_metrics.rr_metrics.mean_rr
            );
            rrDiffEl.textContent = Math.round(diff);
        }

        // Cohérence respiration
        const breathingSyncEl = document.getElementById('polar_breathingSync');
        if (breathingSyncEl && h10Data.real_time_metrics?.breathing_metrics && verityData.real_time_metrics?.breathing_metrics) {
            const h10Freq = h10Data.real_time_metrics.breathing_metrics.frequency;
            const verityFreq = verityData.real_time_metrics.breathing_metrics.frequency;

            if (h10Freq > 0 && verityFreq > 0) {
                const diff = Math.abs(h10Freq - verityFreq);
                const coherence = Math.max(0, 100 - (diff * 10));
                breathingSyncEl.textContent = Math.round(coherence);
                breathingSyncEl.style.color = coherence > 80 ? '#10b981' : '#f59e0b';
            }
        }
    }

    /**
     * Démarre/arrête l'enregistrement CSV
     */
    async toggleRecording() {
        if (this.recording.isRecording) {
            await this.stopRecording();
        } else {
            await this.startRecording();
        }
    }

    /**
     * Démarre l'enregistrement
     */
    async startRecording() {
        console.log('Démarrage de l\'enregistrement CSV');

        if (!this.wsClient || !this.wsClient.isConnected) {
            this.showToast('Erreur: Connexion WebSocket requise', 'error');
            return;
        }

        this.wsClient.emitToModule('polar', 'start_csv_recording', {});
    }

    /**
     * Arrête l'enregistrement
     */
    async stopRecording() {
        console.log('Arrêt de l\'enregistrement CSV');

        if (!this.wsClient || !this.wsClient.isConnected) {
            this.showToast('Erreur: Connexion WebSocket requise', 'error');
            return;
        }

        this.wsClient.emitToModule('polar', 'stop_csv_recording', {});
    }

    /**
     * Gère le démarrage de l'enregistrement
     */
    handleRecordingStarted(data) {
        console.log('Enregistrement démarré:', data);

        this.recording.isRecording = true;
        this.recording.startTime = new Date(data.timestamp);
        this.recording.duration = 0;

        // Mettre à jour l'UI
        const recordBtn = document.getElementById('polar_recordToggleBtn');
        if (recordBtn) {
            recordBtn.innerHTML = '<i class="fas fa-stop"></i> <span>Arrêter</span>';
            recordBtn.classList.add('polar_recording');
        }

        const statusDot = document.getElementById('polar_csvStatusDot');
        const statusText = document.getElementById('polar_csvStatusText');
        if (statusDot) {
            statusDot.classList.remove('polar_idle');
            statusDot.classList.add('polar_recording');
        }
        if (statusText) {
            statusText.textContent = 'Enregistrement...';
        }

        // Afficher le timer
        const sessionInfo = document.getElementById('polar_csvSessionInfo');
        if (sessionInfo) {
            sessionInfo.classList.remove('polar_hidden');
        }

        // Démarrer le timer
        this.recording.interval = setInterval(() => {
            this.recording.duration++;
            this.updateRecordingTimer();
        }, 1000);

        this.showToast('Enregistrement CSV démarré', 'success');
    }

    /**
     * Gère l'arrêt de l'enregistrement
     */
    handleRecordingStopped(data) {
        console.log('Enregistrement arrêté:', data);

        this.recording.isRecording = false;

        // Arrêter le timer
        if (this.recording.interval) {
            clearInterval(this.recording.interval);
            this.recording.interval = null;
        }

        // Mettre à jour l'UI
        const recordBtn = document.getElementById('polar_recordToggleBtn');
        if (recordBtn) {
            recordBtn.innerHTML = '<i class="fas fa-record-vinyl"></i> <span>Enregistrer</span>';
            recordBtn.classList.remove('polar_recording');
        }

        const statusDot = document.getElementById('polar_csvStatusDot');
        const statusText = document.getElementById('polar_csvStatusText');
        if (statusDot) {
            statusDot.classList.remove('polar_recording');
            statusDot.classList.add('polar_idle');
        }
        if (statusText) {
            statusText.textContent = 'CSV Prêt';
        }

        // Cacher le timer
        const sessionInfo = document.getElementById('polar_csvSessionInfo');
        if (sessionInfo) {
            sessionInfo.classList.add('polar_hidden');
        }

        // Afficher les stats
        if (data.lines_written) {
            this.showToast(
                `Enregistrement terminé: ${data.lines_written} lignes écrites (${this.formatDuration(data.duration || this.recording.duration)})`,
                'success'
            );
        }

        // Réinitialiser
        this.recording.duration = 0;
        this.recording.startTime = null;
    }

    /**
     * Met à jour le timer d'enregistrement
     */
    updateRecordingTimer() {
        const durationEl = document.getElementById('polar_sessionDuration');
        if (durationEl) {
            durationEl.textContent = this.formatDuration(this.recording.duration);
        }
    }

    /**
     * Affiche la modal de téléchargement
     */
    async showDownloadModal() {
        console.log('Affichage modal téléchargement');

        if (!this.wsClient || !this.wsClient.isConnected) {
            this.showToast('Erreur: Connexion WebSocket requise', 'error');
            return;
        }

        const modal = document.getElementById('polar_downloadModal');
        if (!modal) return;

        // Afficher la modal
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.add('polar_active'), 10);

        // Afficher le chargement
        document.getElementById('polar_downloadLoadingState').style.display = 'block';
        document.getElementById('polar_downloadFilesState').style.display = 'none';
        document.getElementById('polar_downloadEmptyState').style.display = 'none';

        // Récupérer la liste des fichiers
        this.wsClient.emitToModule('polar', 'get_csv_files', {});
    }

    /**
     * Ferme la modal de téléchargement
     */
    closeDownloadModal() {
        const modal = document.getElementById('polar_downloadModal');
        if (modal) {
            modal.classList.remove('polar_active');
            setTimeout(() => {
                modal.style.display = 'none';
            }, 300);
        }
    }

    /**
     * Gère la liste des fichiers CSV
     */
    handleCSVFilesList(data) {
        console.log('Fichiers CSV reçus:', data);

        const filesList = document.getElementById('polar_filesList');
        if (!filesList) return;

        // Cacher le chargement
        document.getElementById('polar_downloadLoadingState').style.display = 'none';

        if (!data.files || data.files.length === 0) {
            // Aucun fichier
            document.getElementById('polar_downloadEmptyState').style.display = 'block';
            document.getElementById('polar_downloadFilesState').style.display = 'none';
        } else {
            // Afficher les fichiers
            document.getElementById('polar_downloadFilesState').style.display = 'block';
            document.getElementById('polar_downloadEmptyState').style.display = 'none';

            // Vider la liste
            filesList.innerHTML = '';

            // Ajouter chaque fichier
            data.files.forEach(file => {
                const fileItem = this.createFileItem(file);
                filesList.appendChild(fileItem);
            });
        }
    }

    /**
     * Crée un élément de fichier
     */
    createFileItem(file) {
        const div = document.createElement('div');
        div.className = 'polar_file-item';

        const date = new Date(file.modified);
        const dateStr = date.toLocaleDateString('fr-FR') + ' ' + date.toLocaleTimeString('fr-FR', {
            hour: '2-digit',
            minute: '2-digit'
        });

        div.innerHTML = `
            <div class="polar_file-info">
                <div class="polar_file-icon">
                    <i class="fas fa-file-csv"></i>
                </div>
                <div class="polar_file-details">
                    <div class="polar_file-name">${file.filename}</div>
                    <div class="polar_file-meta">
                        <span>${file.size_str}</span>
                        <span>•</span>
                        <span>${dateStr}</span>
                    </div>
                </div>
            </div>
            <button class="polar_file-download-btn" onclick="window.polarModuleInstance.downloadFile('${file.filename}')">
                <i class="fas fa-download"></i>
            </button>
        `;

        return div;
    }

    /**
     * Télécharge un fichier
     */
    downloadFile(filename) {
        console.log('Téléchargement:', filename);

        // Créer un lien de téléchargement
        const link = document.createElement('a');
        link.href = `/api/polar/csv/${filename}`;
        link.download = filename;
        link.click();

        this.showToast('Téléchargement démarré', 'success');
    }

    /**
     * Télécharge tous les fichiers en ZIP
     */
    downloadAllFiles() {
        console.log('Téléchargement de tous les fichiers');

        // Créer un lien pour le téléchargement ZIP
        const link = document.createElement('a');
        link.href = '/api/polar/csv/download-all';
        link.download = `polar_sessions_${new Date().toISOString().slice(0,10)}.zip`;
        link.click();

        this.showToast('Préparation du fichier ZIP...', 'info');
    }

    /**
     * Met à jour l'UI d'un appareil
     */
    updateDeviceUI(deviceType, connected) {
        const card = document.getElementById(`polar_${deviceType}Card`);
        const statusEl = document.getElementById(`polar_${deviceType}Status`);
        const deviceIdEl = document.getElementById(`polar_${deviceType}DeviceId`);

        if (card) {
            if (connected) {
                card.classList.remove('polar_inactive');
                card.classList.add('polar_active');
            } else {
                card.classList.remove('polar_active');
                card.classList.add('polar_inactive');
            }
        }

        if (statusEl) {
            const statusDot = statusEl.querySelector('.polar_status-dot');
            const statusText = statusEl.querySelector('span:last-child');

            if (connected) {
                statusDot.classList.add('polar_connected');
                statusText.textContent = 'Connecté';
            } else {
                statusDot.classList.remove('polar_connected');
                statusText.textContent = 'Déconnecté';
            }
        }

        if (deviceIdEl) {
            if (connected && this.devices[deviceType].data?.device_info) {
                deviceIdEl.textContent = this.devices[deviceType].data.device_info.formatted_id || 'Connecté';
            } else {
                deviceIdEl.textContent = 'Non connecté';
            }
        }

        // Réinitialiser les valeurs si déconnecté
        if (!connected) {
            const prefix = `polar_${deviceType}`;
            const elements = [
                'HeartRate', 'LastRR', 'MeanRR', 'RMSSD',
                'MeanBPM', 'MinBPM', 'MaxBPM',
                'BreathingFreq', 'BreathingAmp'
            ];

            elements.forEach(suffix => {
                const el = document.getElementById(`${prefix}${suffix}`);
                if (el) el.textContent = '--';
            });

            const zoneLabel = document.getElementById(`${prefix}ZoneLabel`);
            if (zoneLabel) zoneLabel.textContent = 'En attente';

            const qualityEl = document.getElementById(`${prefix}BreathingQuality`);
            if (qualityEl) qualityEl.textContent = '--';
        }

        // Mettre à jour l'UI globale immédiatement
        this.updateUI();

        // Si on passe en mode single device, forcer l'animation
        const connectedCount = Object.values(this.devices).filter(d => d.connected).length;
        if (connectedCount === 1 && connected) {
            // Petit délai pour que la transition CSS s'applique
            setTimeout(() => {
                const activeCard = document.querySelector('.polar_device-card.polar_active');
                if (activeCard) {
                    activeCard.style.opacity = '1';
                    activeCard.style.transform = 'scale(1)';
                }
            }, 50);
        }
    }

    /**
     * Met à jour l'UI globale
     */
    updateUI() {
        const connectedCount = Object.values(this.devices).filter(d => d.connected).length;

        // Compteur d'appareils
        const deviceCount = document.getElementById('polar_deviceCount');
        if (deviceCount) {
            deviceCount.textContent = connectedCount;
        }

        // Boutons principaux
        const connectBtn = document.getElementById('polar_connectBtn');
        const disconnectBtn = document.getElementById('polar_disconnectBtn');

        if (connectBtn && disconnectBtn) {
            if (connectedCount > 0) {
                connectBtn.classList.add('polar_hidden');
                disconnectBtn.classList.remove('polar_hidden');
            } else {
                connectBtn.classList.remove('polar_hidden');
                disconnectBtn.classList.add('polar_hidden');
            }
        }

        // Bouton enregistrement
        const recordBtn = document.getElementById('polar_recordToggleBtn');
        if (recordBtn) {
            recordBtn.disabled = connectedCount === 0;
        }

        // Mode d'affichage (single ou dual)
        const grid = document.getElementById('polar_monitoringGrid');
        const comparison = document.getElementById('polar_comparisonPanel');

        if (grid) {
            if (connectedCount === 1) {
                grid.classList.add('polar_single-device');
                if (comparison) comparison.classList.add('polar_single-mode');
            } else {
                grid.classList.remove('polar_single-device');
                if (comparison) comparison.classList.remove('polar_single-mode');

                // S'assurer que les deux cartes sont visibles quand aucun appareil n'est connecté
                if (connectedCount === 0) {
                    const h10Card = document.getElementById('polar_h10Card');
                    const verityCard = document.getElementById('polar_verityCard');

                    if (h10Card) {
                        h10Card.style.display = '';
                        h10Card.classList.add('polar_inactive');
                    }

                    if (verityCard) {
                        verityCard.style.display = '';
                        verityCard.classList.add('polar_inactive');
                    }
                }
            }
        }
    }

    /**
     * Vérifie si tous les appareils détectés sont connectés
     */
    checkAllDevicesConnected() {
        const modal = document.getElementById('polar_connectionModal');
        console.log('Modal trouvée:', !!modal, 'Modal active:', modal?.classList.contains('polar_active'));

        if (!modal || !modal.classList.contains('polar_active')) return;

        const devices = modal.querySelectorAll('.polar_device-option');
        console.log('Devices trouvés:', devices.length);

        const connectedDevices = Array.from(devices).filter(device =>
            device.classList.contains('polar_connected')
        );
        console.log('Devices connectés:', connectedDevices.length);

        const allConnected = devices.length > 0 && devices.length === connectedDevices.length;
        console.log('Tous connectés:', allConnected);

        if (allConnected) {
            console.log('Fermeture automatique de la modal dans 1.5s');
            setTimeout(() => this.forceShowMonitoring(), 1500);
        }
    }

    /**
     * Ferme la modal de connexion (version forcée)
     */
    closeConnectionModal() {
        console.log('Fermeture de la modal de connexion');

        const modal = document.getElementById('polar_connectionModal');
        if (modal) {
            // Retirer toutes les classes et styles
            modal.classList.remove('polar_active');
            modal.style.display = 'none';
            modal.style.opacity = '0';
            modal.style.visibility = 'hidden';

            // Nettoyer aussi l'overlay de chargement
            this.hideLoading();
        }
    }

    /**
     * Réessaye la connexion
     */
    retryConnection() {
        this.scanForDevices();
    }

    /**
     * Réinitialise un graphique
     */
    resetChart(deviceType) {
        const device = this.devices[deviceType];
        if (device.chart) {
            device.chartData = [];
            device.chart.data.labels = [];
            device.chart.data.datasets[0].data = [];
            device.chart.update();

            this.showToast(`Graphique ${deviceType.toUpperCase()} réinitialisé`, 'info');
        }
    }

    /**
     * Calcule la zone cardiaque
     */
    calculateHeartRateZone(hr) {
        // Estimation basique (normalement basée sur l'âge et FCmax)
        if (hr < 60) {
            return { label: 'Repos', color: '#e0f2fe', textColor: '#0369a1' };
        } else if (hr < 100) {
            return { label: 'Légère', color: '#d1fae5', textColor: '#059669' };
        } else if (hr < 140) {
            return { label: 'Modérée', color: '#fed7aa', textColor: '#c2410c' };
        } else if (hr < 170) {
            return { label: 'Intense', color: '#fecaca', textColor: '#dc2626' };
        } else {
            return { label: 'Maximale', color: '#e0e7ff', textColor: '#4338ca' };
        }
    }

    /**
     * Formate l'ID d'un appareil
     */
    formatDeviceId(address) {
        if (!address) return 'Unknown';

        if (address.includes(':')) {
            const parts = address.split(':');
            return `${parts[parts.length-2]}:${parts[parts.length-1]}`;
        }

        return address.substring(address.length - 6);
    }

    /**
     * Calcule la force du signal
     */
    calculateSignalStrength(rssi) {
        // RSSI typique: -40 (excellent) à -90 (faible)
        const strength = Math.max(0, Math.min(100, (rssi + 90) * 2));
        return Math.round(strength);
    }

    /**
     * Traduit la qualité
     */
    translateQuality(quality) {
        const translations = {
            'excellent': 'Excellent',
            'good': 'Bon',
            'fair': 'Moyen',
            'poor': 'Faible',
            'unknown': '--'
        };
        return translations[quality] || quality;
    }

    /**
     * Formate une durée
     */
    formatDuration(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }

    /**
     * Affiche un toast
     */
    showToast(message, type = 'info') {
        const container = document.getElementById('polar_toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `polar_toast polar_${type}`;

        const icon = type === 'success' ? 'fa-check-circle' :
                     type === 'error' ? 'fa-exclamation-circle' :
                     'fa-info-circle';

        toast.innerHTML = `
            <div class="polar_toast-icon">
                <i class="fas ${icon}"></i>
            </div>
            <div class="polar_toast-content">
                <div class="polar_toast-message">${message}</div>
            </div>
        `;

        container.appendChild(toast);

        // Animation d'entrée
        setTimeout(() => toast.classList.add('polar_show'), 10);

        // Suppression automatique
        setTimeout(() => {
            toast.classList.add('polar_removing');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    /**
     * Affiche le chargement
     */
    showLoading(title = 'Chargement...', text = '') {
        const overlay = document.getElementById('polar_loadingOverlay');
        if (!overlay) return;

        const titleEl = document.getElementById('polar_loadingTitle');
        const textEl = document.getElementById('polar_loadingText');

        if (titleEl) titleEl.textContent = title;
        if (textEl) textEl.textContent = text;

        overlay.classList.add('polar_active');
    }

    /**
     * Cache le chargement
     */
    hideLoading() {
        const overlay = document.getElementById('polar_loadingOverlay');
        if (overlay) {
            overlay.classList.remove('polar_active');
        }
    }

    /**
     * Gère les erreurs
     */
    handleError(data) {
        console.error('Erreur Polar:', data);
        this.showToast(data.error || 'Une erreur est survenue', 'error');
    }

    /**
     * Gère le résultat de connexion
     */
    handleConnectResult(data) {
        console.log('Résultat de connexion:', data);

        if (data.success && data.device_type) {
            // Marquer l'appareil comme connecté immédiatement
            this.devices[data.device_type].connected = true;
            this.devices[data.device_type].collecting = true;

            // Mettre à jour l'UI de l'appareil
            this.updateDeviceUI(data.device_type, true);

            // Mettre à jour la modal si elle est ouverte
            const modal = document.getElementById('polar_connectionModal');
            if (modal && modal.classList.contains('polar_active')) {
                const deviceOption = document.querySelector(`[data-device-type="${data.device_type}"]`);
                if (deviceOption) {
                    deviceOption.classList.remove('polar_connecting');
                    deviceOption.classList.add('polar_connected');
                    const btn = deviceOption.querySelector('.polar_connect-btn');
                    if (btn) {
                        btn.innerHTML = '<i class="fas fa-check"></i> Connecté';
                        btn.disabled = true;
                    }
                }
            }

            this.showToast(`${data.device_type.toUpperCase()} connecté avec succès`, 'success');

            // Fermer la modal et afficher le monitoring après un court délai
            setTimeout(() => {
                this.forceShowMonitoring();
            }, 1000);

        } else {
            this.showToast(
                `Échec de connexion ${data.device_type?.toUpperCase() || ''}`,
                'error'
            );

            // Réinitialiser l'UI de la modal
            const deviceOption = document.querySelector(`[data-device-type="${data.device_type}"]`);
            if (deviceOption) {
                deviceOption.classList.remove('polar_connecting');
                const btn = deviceOption.querySelector('.polar_connect-btn');
                if (btn) {
                    btn.innerHTML = '<i class="fas fa-link"></i> <span>Connecter</span>';
                    btn.disabled = false;
                }
            }
        }
    }

    /**
     * Gère le statut d'un appareil
     */
    handleDeviceStatus(deviceType, data) {
        console.log(`Statut ${deviceType}:`, data);

        // Mettre à jour selon le statut
        if (data.status === 'disconnected') {
            this.handleDeviceDisconnected(deviceType);
        } else if (data.status === 'error') {
            this.showToast(
                `Erreur ${deviceType.toUpperCase()}: ${data.message}`,
                'error'
            );
        }
    }

    /**
     * Gère le statut global
     */
    handleGlobalStatus(data) {
        console.log('Statut global:', data);

        // Mettre à jour l'état des appareils
        if (data.h10) {
            this.devices.h10.connected = data.h10.connected || false;
            this.devices.h10.collecting = data.h10.collecting || false;
            if (data.h10.latest_data) {
                this.devices.h10.data = data.h10.latest_data;
            }
        }

        if (data.verity) {
            this.devices.verity.connected = data.verity.connected || false;
            this.devices.verity.collecting = data.verity.collecting || false;
            if (data.verity.latest_data) {
                this.devices.verity.data = data.verity.latest_data;
            }
        }

        // Mettre à jour l'état d'enregistrement
        if (data.csv_recording !== undefined) {
            this.recording.isRecording = data.csv_recording;
            if (this.recording.isRecording && data.session_stats?.start_time) {
                this.recording.startTime = new Date(data.session_stats.start_time);

                // Redémarrer le timer si nécessaire
                if (!this.recording.interval) {
                    const elapsed = Math.floor((Date.now() - this.recording.startTime.getTime()) / 1000);
                    this.recording.duration = elapsed;
                    this.recording.interval = setInterval(() => {
                        this.recording.duration++;
                        this.updateRecordingTimer();
                    }, 1000);
                }
            }
        }

        // Mettre à jour toute l'UI
        this.updateUI();

        // Mettre à jour les appareils connectés
        for (const [deviceType, device] of Object.entries(this.devices)) {
            if (device.connected) {
                this.updateDeviceUI(deviceType, true);
                if (device.data) {
                    this.updateDeviceData(deviceType, device.data);
                }
            }
        }
    }

    /**
     * Nettoyage du module
     */
    cleanup() {
        console.log('Nettoyage du module Polar');

        // Ne pas réinitialiser si c'est un module persistant
        const isPersistent = window.dashboard?.persistentModules?.has('polar');

        if (isPersistent) {
            console.log('Module Polar persistant - nettoyage minimal');
            // Juste nettoyer les timers
            if (this.updateTimer) {
                clearInterval(this.updateTimer);
                this.updateTimer = null;
            }

            if (this.recording.interval) {
                clearInterval(this.recording.interval);
                this.recording.interval = null;
            }
            return;
        }

        // Nettoyage complet seulement si non persistant
        // Arrêter les timers
        if (this.updateTimer) {
            clearInterval(this.updateTimer);
            this.updateTimer = null;
        }

        if (this.recording.interval) {
            clearInterval(this.recording.interval);
            this.recording.interval = null;
        }

        // Réinitialiser l'interface si des appareils sont connectés
        if (Object.values(this.devices).some(d => d.connected)) {
            this.resetInterface();
        }

        // Détruire les graphiques
        this.destroyCharts();

        // Nettoyer les événements WebSocket
        this.cleanupWebSocketEvents();

        // Se désabonner du module
        if (this.wsClient && this.wsClient.isConnected) {
            this.wsClient.unsubscribeFromModule('polar');
        }

        // Marquer comme non initialisé
        this.isInitialized = false;
    }
}

// Fonction d'initialisation globale
function initPolarModule() {
    console.log('Initialisation du module Polar...');

    // Créer l'instance
    const polarModule = new PolarModule();

    // Stocker globalement pour accès depuis HTML
    window.polarModuleInstance = polarModule;

    // Initialiser
    polarModule.init();

    return polarModule;
}

// Export pour le dashboard
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { PolarModule, initPolarModule };
} else if (typeof window !== 'undefined') {
    window.PolarModule = PolarModule;
    window.initPolarModule = initPolarModule;
}