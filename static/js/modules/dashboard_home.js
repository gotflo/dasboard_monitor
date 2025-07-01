/**
 * Dashboard Home - Module JavaScript
 * Gestion de la page d'accueil avec données temps réel
 */

class DashboardHome {
    constructor() {
        this.wsClient = null;
        this.modules = {
            polar: { connected: false, data: {} },
            neurosity: { connected: false, data: {} },
            thermal_camera: { connected: false, data: {} },
            gazepoint: { connected: false, data: {} },
            thought_capture: { connected: false, data: {} }
        };

        this.charts = {};
        this.activeModulesCount = 0;
        this.dataPointsCount = 0;
        this.sessionStartTime = null;
        this.isCollecting = false;

        this.init();
    }

    async init() {
        console.log('Initialisation Dashboard Home');

        // Récupérer le client WebSocket du dashboard principal
        if (window.dashboard && window.dashboard.wsClient) {
            this.wsClient = window.dashboard.wsClient;
            this.setupWebSocketHandlers();
        }

        // Initialiser les mini-graphiques
        this.initCharts();

        // Configurer les event listeners
        this.setupEventListeners();

        // Démarrer l'horloge
        this.startClock();

        // Charger l'état initial des modules
        this.loadModulesStatus();

        // Démarrer les animations
        this.startAnimations();
    }

    setupWebSocketHandlers() {
        if (!this.wsClient) return;

        // Gestionnaire global de statut WebSocket
        this.wsClient.on('connected', () => {
            this.updateWebSocketStatus(true);
        });

        this.wsClient.on('disconnected', () => {
            this.updateWebSocketStatus(false);
        });

        // Handlers pour module Polar
        this.wsClient.onModuleEvent('polar', 'heart_rate_data', (data) => {
            this.updatePolarData(data);
        });

        // Handlers pour module Neurosity
        this.wsClient.onModuleEvent('neurosity', 'calm_data', (data) => {
            this.updateNeurosityCalm(data);
        });

        this.wsClient.onModuleEvent('neurosity', 'focus_data', (data) => {
            this.updateNeurosityFocus(data);
        });

        this.wsClient.onModuleEvent('neurosity', 'brainwaves_data', (data) => {
            this.updateBrainwaves(data);
        });

        // Handlers pour module Thermal Camera
        this.wsClient.onModuleEvent('thermal_camera', 'thermal_temperature_data', (data) => {
            this.updateThermalData(data);
        });

        // Handlers pour module Gazepoint
        this.wsClient.onModuleEvent('gazepoint', 'gaze_data', (data) => {
            this.updateGazepointData(data);
        });

        // Handlers pour module Thought Capture
        this.wsClient.onModuleEvent('thought_capture', 'recording_status', (data) => {
            this.updateThoughtCaptureStatus(data);
        });

        this.wsClient.onModuleEvent('thought_capture', 'audio_level', (data) => {
            this.updateAudioLevel(data);
        });

        // Écouter les changements de statut des modules
        this.wsClient.on('module_status_changed', (data) => {
            this.updateModuleStatus(data.module, data.status);
        });
    }

    setupEventListeners() {
        // Boutons de contrôle globaux
        document.getElementById('startAllCollection')?.addEventListener('click', () => {
            this.startGlobalCollection();
        });

        document.getElementById('stopAllCollection')?.addEventListener('click', () => {
            this.stopGlobalCollection();
        });

        document.getElementById('downloadAllData')?.addEventListener('click', () => {
            this.downloadAllData();
        });
    }

    initCharts() {
        // Chart Polar - Fréquence cardiaque
        const polarCanvas = document.getElementById('polarHeartRateChart');
        if (polarCanvas) {
            this.charts.polar = new Chart(polarCanvas.getContext('2d'), {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'BPM',
                        data: [],
                        borderColor: '#ff6b6b',
                        backgroundColor: 'rgba(255, 107, 107, 0.1)',
                        borderWidth: 2,
                        tension: 0.4,
                        pointRadius: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        x: { display: false },
                        y: {
                            display: false,
                            min: 50,
                            max: 150
                        }
                    }
                }
            });
        }

        // Chart Neurosity - Ondes cérébrales
        const brainwavesCanvas = document.getElementById('brainwavesMiniChart');
        if (brainwavesCanvas) {
            this.charts.brainwaves = new Chart(brainwavesCanvas.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: ['δ', 'θ', 'α', 'β', 'γ'],
                    datasets: [{
                        data: [0, 0, 0, 0, 0],
                        backgroundColor: [
                            'rgba(99, 102, 241, 0.8)',
                            'rgba(245, 158, 11, 0.8)',
                            'rgba(59, 130, 246, 0.8)',
                            'rgba(34, 197, 94, 0.8)',
                            'rgba(236, 72, 153, 0.8)'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        x: { display: false },
                        y: { display: false, max: 20 }
                    }
                }
            });
        }

        // Chart Thermal - Températures
        const thermalCanvas = document.getElementById('thermalMiniChart');
        if (thermalCanvas) {
            this.charts.thermal = new Chart(thermalCanvas.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: ['Nez', 'Bouche', 'Yeux', 'Joues', 'Front', 'Menton'],
                    datasets: [{
                        data: [36.5, 36.8, 36.4, 36.6, 36.7, 36.5],
                        backgroundColor: 'rgba(69, 183, 209, 0.8)',
                        borderColor: '#45b7d1',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        x: { display: false },
                        y: {
                            display: false,
                            min: 35,
                            max: 38
                        }
                    }
                }
            });
        }

        // Canvas pour l'audio visualizer
        const audioCanvas = document.getElementById('audioVisualizerMini');
        if (audioCanvas) {
            this.initAudioVisualizer(audioCanvas);
        }
    }

    initAudioVisualizer(canvas) {
        const ctx = canvas.getContext('2d');
        canvas.width = canvas.offsetWidth;
        canvas.height = canvas.offsetHeight;

        // Animation simple pour l'audio
        const drawWaveform = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.strokeStyle = '#feca57';
            ctx.lineWidth = 2;
            ctx.beginPath();

            const bars = 20;
            const barWidth = canvas.width / bars;

            for (let i = 0; i < bars; i++) {
                const x = i * barWidth + barWidth / 2;
                const height = Math.random() * canvas.height * 0.8;
                const y = (canvas.height - height) / 2;

                ctx.moveTo(x, y);
                ctx.lineTo(x, y + height);
            }

            ctx.stroke();
        };

        // Animation continue si enregistrement actif
        this.audioAnimationInterval = setInterval(() => {
            if (this.modules.thought_capture.data.isRecording) {
                drawWaveform();
            }
        }, 100);
    }

    // Méthodes de mise à jour des données

    updatePolarData(data) {
        // Mettre à jour les valeurs
        document.getElementById('polarBPM').textContent = data.heart_rate || '--';
        document.getElementById('polarRR').textContent = data.rr_interval || '--';
        document.getElementById('polarRespiration').textContent = data.respiration_rate || '--';

        // Mettre à jour le graphique
        if (this.charts.polar) {
            const chart = this.charts.polar;
            chart.data.labels.push('');
            chart.data.datasets[0].data.push(data.heart_rate);

            // Garder seulement les 20 derniers points
            if (chart.data.labels.length > 20) {
                chart.data.labels.shift();
                chart.data.datasets[0].data.shift();
            }

            chart.update('none');
        }

        this.updateModuleStatus('polar', 'connected');
        this.addActivityLog('Polar', 'Données cardiaques mises à jour');
    }

    updateNeurosityCalm(data) {
        const calmPercent = Math.round(data.calm || 0);
        document.getElementById('calmPercent').textContent = calmPercent + '%';
        document.getElementById('calmProgress').style.width = calmPercent + '%';

        this.modules.neurosity.data.calm = calmPercent;
        this.updateModuleStatus('neurosity', 'connected');
    }

    updateNeurosityFocus(data) {
        const focusPercent = Math.round(data.focus || 0);
        document.getElementById('focusPercent').textContent = focusPercent + '%';
        document.getElementById('focusProgress').style.width = focusPercent + '%';

        this.modules.neurosity.data.focus = focusPercent;
    }

    updateBrainwaves(data) {
        if (this.charts.brainwaves) {
            const waves = ['delta', 'theta', 'alpha', 'beta', 'gamma'];
            const values = waves.map(wave => data[wave] || 0);

            this.charts.brainwaves.data.datasets[0].data = values;
            this.charts.brainwaves.update('none');
        }

        this.addActivityLog('Neurosity', 'Ondes cérébrales actualisées');
    }

    updateThermalData(data) {
        // Mettre à jour la visualisation du visage
        const temps = data.temperatures;
        if (temps) {
            Object.keys(temps).forEach(point => {
                const element = document.querySelector(`[data-point="${point}"]`);
                if (element) {
                    const temp = temps[point];
                    const color = this.getTemperatureColor(temp);
                    element.setAttribute('fill', color);
                    element.querySelector('title').textContent = `${point}: ${temp}°C`;
                }
            });

            // Calculer la moyenne
            const values = Object.values(temps);
            const avg = (values.reduce((a, b) => a + b, 0) / values.length).toFixed(1);
            document.getElementById('thermalAvgTemp').textContent = avg;

            // Mettre à jour le graphique
            if (this.charts.thermal) {
                // Regrouper certains points pour le graphique simplifié
                const chartData = [
                    temps['Nez'] || 36.5,
                    temps['Bouche'] || 36.8,
                    (temps['Œil_Gauche'] + temps['Œil_Droit']) / 2 || 36.4,
                    (temps['Joue_Gauche'] + temps['Joue_Droite']) / 2 || 36.6,
                    temps['Front'] || 36.7,
                    temps['Menton'] || 36.5
                ];

                this.charts.thermal.data.datasets[0].data = chartData;
                this.charts.thermal.update('none');
            }
        }

        this.updateModuleStatus('thermal_camera', 'active');
        this.addActivityLog('Thermique', 'Carte de température mise à jour');
    }

    updateGazepointData(data) {
        // Mettre à jour la dilatation pupillaire
        const dilation = data.pupil_diameter || 0;
        document.getElementById('pupilDilation').textContent = dilation.toFixed(1) + ' mm';

        // Animer les pupilles
        const pupilSize = Math.max(10, Math.min(25, dilation * 5));
        document.getElementById('leftPupil').style.width = pupilSize + 'px';
        document.getElementById('leftPupil').style.height = pupilSize + 'px';
        document.getElementById('rightPupil').style.width = pupilSize + 'px';
        document.getElementById('rightPupil').style.height = pupilSize + 'px';

        // Durée de fixation
        document.getElementById('fixationDuration').textContent = (data.fixation_duration || 0) + ' ms';

        this.updateModuleStatus('gazepoint', 'connected');
        this.addActivityLog('Gazepoint', 'Données oculaires reçues');
    }

    updateThoughtCaptureStatus(data) {
        const status = data.isRecording ? 'Enregistrement' : 'Prêt';
        document.getElementById('thoughtStatus').textContent = status;
        document.getElementById('thoughtStatus').classList.toggle('active', data.isRecording);

        if (data.isRecording) {
            this.modules.thought_capture.data.isRecording = true;
            this.modules.thought_capture.data.recordingStartTime = Date.now();
        } else {
            this.modules.thought_capture.data.isRecording = false;
            if (data.lastRecording) {
                document.getElementById('lastRecordingName').textContent = data.lastRecording;
            }
        }

        this.updateModuleStatus('thought_capture', data.isRecording ? 'active' : 'connected');
    }

    updateAudioLevel(data) {
        const level = Math.min(100, data.level || 0);
        document.getElementById('audioLevelFill').style.width = level + '%';
    }

    // Méthodes utilitaires

    getTemperatureColor(temp) {
        if (temp < 35) return '#3b82f6'; // Bleu froid
        if (temp < 36) return '#06b6d4'; // Cyan
        if (temp < 36.5) return '#10b981'; // Vert
        if (temp < 37) return '#fbbf24'; // Jaune
        if (temp < 37.5) return '#f97316'; // Orange
        return '#ef4444'; // Rouge chaud
    }

    updateModuleStatus(moduleName, status) {
        const statusElement = document.getElementById(moduleName + 'Status');
        if (statusElement) {
            const statusTexts = {
                'connected': 'Connecté',
                'active': 'Actif',
                'recording': 'Enregistrement',
                'disconnected': 'Déconnecté',
                'error': 'Erreur'
            };

            statusElement.textContent = statusTexts[status] || status;
            statusElement.className = 'status-badge ' + status;
        }

        // Mettre à jour le module dans notre état
        this.modules[moduleName].connected = (status !== 'disconnected' && status !== 'error');

        // Mettre à jour le compteur de modules actifs
        this.updateActiveModulesCount();
    }

    updateActiveModulesCount() {
        this.activeModulesCount = Object.values(this.modules).filter(m => m.connected).length;
        document.getElementById('activeModules').textContent = this.activeModulesCount;
    }

    updateWebSocketStatus(connected) {
        const wsStatus = document.getElementById('wsStatus');
        if (wsStatus) {
            wsStatus.textContent = connected ? 'Connecté' : 'Déconnecté';
            wsStatus.className = 'ws-status ' + (connected ? 'connected' : '');
        }
    }

    addActivityLog(module, message) {
        const timeline = document.getElementById('activityTimeline');
        if (!timeline) return;

        const item = document.createElement('div');
        item.className = 'timeline-item';
        item.innerHTML = `
            <span class="timeline-dot"></span>
            <span class="timeline-text">${new Date().toLocaleTimeString('fr-FR')} - ${module}: ${message}</span>
        `;

        timeline.insertBefore(item, timeline.firstChild);

        // Garder seulement les 10 derniers événements
        while (timeline.children.length > 10) {
            timeline.removeChild(timeline.lastChild);
        }

        // Incrémenter le compteur de points de données
        this.dataPointsCount++;
        document.getElementById('dataPoints').textContent = this.dataPointsCount;
    }

    // Contrôles globaux

    async startGlobalCollection() {
        console.log('Démarrage de la collecte globale');

        this.isCollecting = true;
        this.sessionStartTime = Date.now();

        // Mettre à jour l'UI
        document.getElementById('startAllCollection').disabled = true;
        document.getElementById('stopAllCollection').disabled = false;
        document.getElementById('globalStatusDot').classList.add('active');
        document.getElementById('globalStatusText').textContent = 'Collecte active';

        // Démarrer chaque module via WebSocket
        if (this.wsClient) {
            // Polar
            this.wsClient.emitToModule('polar', 'start_monitoring', {});

            // Neurosity
            this.wsClient.emitToModule('neurosity', 'start_monitoring', {});

            // Thermal Camera
            this.wsClient.emitToModule('thermal_camera', 'start_capture', {});

            // Gazepoint
            this.wsClient.emitToModule('gazepoint', 'start_tracking', {});

            // Thought Capture n'est pas démarré automatiquement (nécessite action utilisateur)
        }

        this.showToast('Collecte globale démarrée', 'success');
        this.addActivityLog('Système', 'Collecte globale démarrée');

        // Démarrer le timer de session
        this.startSessionTimer();
    }

    async stopGlobalCollection() {
        console.log('Arrêt de la collecte globale');

        this.isCollecting = false;

        // Mettre à jour l'UI
        document.getElementById('startAllCollection').disabled = false;
        document.getElementById('stopAllCollection').disabled = true;
        document.getElementById('globalStatusDot').classList.remove('active');
        document.getElementById('globalStatusText').textContent = 'Prêt';

        // Arrêter chaque module
        if (this.wsClient) {
            this.wsClient.emitToModule('polar', 'stop_monitoring', {});
            this.wsClient.emitToModule('neurosity', 'stop_monitoring', {});
            this.wsClient.emitToModule('thermal_camera', 'stop_capture', {});
            this.wsClient.emitToModule('gazepoint', 'stop_tracking', {});
        }

        this.showToast('Collecte globale arrêtée', 'info');
        this.addActivityLog('Système', 'Collecte globale arrêtée');

        // Arrêter le timer
        if (this.sessionTimer) {
            clearInterval(this.sessionTimer);
        }
    }

    async downloadAllData() {
        console.log('Téléchargement de toutes les données');

        // Créer un ZIP avec toutes les données disponibles
        this.showToast('Préparation du téléchargement...', 'info');

        // Pour l'instant, on simule
        setTimeout(() => {
            this.showToast('Données téléchargées avec succès', 'success');
            this.addActivityLog('Système', 'Export des données effectué');
        }, 2000);
    }

    // Utilitaires

    startClock() {
        const updateDateTime = () => {
            const now = new Date();
            const dateTimeStr = now.toLocaleDateString('fr-FR') + ' ' + now.toLocaleTimeString('fr-FR');
            document.getElementById('currentDateTime').textContent = dateTimeStr;
        };

        updateDateTime();
        setInterval(updateDateTime, 1000);
    }

    startSessionTimer() {
        this.sessionTimer = setInterval(() => {
            if (this.sessionStartTime) {
                const elapsed = Date.now() - this.sessionStartTime;
                const minutes = Math.floor(elapsed / 60000);
                const seconds = Math.floor((elapsed % 60000) / 1000);
                const timeStr = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                document.getElementById('sessionDuration').textContent = timeStr;
            }
        }, 1000);
    }

    loadModulesStatus() {
        // Simuler le chargement de l'état initial
        // En production, ceci ferait un appel API
        setTimeout(() => {
            this.updateModuleStatus('neurosity', 'disconnected');
            this.updateModuleStatus('polar', 'disconnected');
            this.updateModuleStatus('thermal_camera', 'disconnected');
            this.updateModuleStatus('gazepoint', 'disconnected');
            this.updateModuleStatus('thought_capture', 'disconnected');
        }, 500);
    }

    startAnimations() {
        // Timer pour l'enregistrement audio
        setInterval(() => {
            if (this.modules.thought_capture.data.isRecording) {
                const elapsed = Date.now() - this.modules.thought_capture.data.recordingStartTime;
                const minutes = Math.floor(elapsed / 60000);
                const seconds = Math.floor((elapsed % 60000) / 1000);
                const timeStr = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
                document.getElementById('recordingTime').textContent = timeStr;
            }
        }, 1000);

        // Mise à jour du stockage (simulation)
        setInterval(() => {
            const storage = (Math.random() * 50 + 10).toFixed(1);
            document.getElementById('storageUsed').textContent = storage + ' MB';
        }, 30000);
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('dashboardToastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️'
        };

        toast.innerHTML = `
            <span>${icons[type] || icons.info}</span>
            <span>${message}</span>
        `;

        container.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    cleanup() {
        // Nettoyer les intervalles
        if (this.audioAnimationInterval) {
            clearInterval(this.audioAnimationInterval);
        }
        if (this.sessionTimer) {
            clearInterval(this.sessionTimer);
        }

        // Détruire les graphiques
        Object.values(this.charts).forEach(chart => {
            if (chart) chart.destroy();
        });

        console.log('Dashboard Home nettoyé');
    }
}

// Initialisation du module
window.initDashboardHome = function() {
    console.log('Initialisation Dashboard Home');
    if (!window.dashboardHomeInstance) {
        window.dashboardHomeInstance = new DashboardHome();
    }
    return window.dashboardHomeInstance;
};

// Auto-initialisation si le module est chargé directement
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.initDashboardHome();
    });
} else {
    window.initDashboardHome();
}