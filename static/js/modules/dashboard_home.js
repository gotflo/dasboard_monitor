/**
 * Dashboard Home Module - JavaScript Frontend
 * Gestion dynamique du dashboard principal avec WebSocket
 * Version avec mise à jour temps réel et animations fluides
 */

class DashboardHomeModule {
    constructor() {
        // État du module
        this.wsClient = null;
        this.isInitialized = false;
        this.updateInterval = null;
        this.toastTimeout = null;

        // État des modules
        this.modulesStatus = {
            polar: { connected: false, active: false, data: {} },
            neurosity: { connected: false, active: false, data: {} },
            thermal_camera: { connected: false, active: false, data: {} },
            gazepoint: { connected: false, active: false, data: {} },
            thought_capture: { connected: false, active: false, data: {} }
        };

        // Statistiques globales
        this.globalStats = {
            activeModules: 0,
            dataPoints: 0,
            sessionStart: null,
            storageUsed: 0
        };

        // Configuration
        this.config = {
            updateInterval: 1000, // Mise à jour toutes les secondes
            animationDuration: 300,
            toastDuration: 4000
        };

        // Animation des graphiques
        this.charts = {
            polar: null,
            neurosity: null,
            thermal: null
        };
    }

    /**
     * Initialisation du module
     */
    async init() {
        console.log('🏠 Initialisation Dashboard Home');

        try {
            // Récupérer le client WebSocket depuis le dashboard principal
            this.wsClient = window.dashboard?.wsClient;

            if (!this.wsClient) {
                console.error('WebSocket client non disponible');
                this.showToast('Erreur: WebSocket non disponible', 'error');
                return;
            }

            // S'abonner au module dashboard
            await this.subscribeToModule();

            // Initialiser les événements WebSocket
            this.initWebSocketEvents();

            // Initialiser les contrôles UI
            this.initUIControls();

            // Initialiser les mini-graphiques
            this.initMiniCharts();

            // Démarrer la mise à jour automatique
            this.startAutoUpdate();

            // Demander le résumé initial
            this.requestDashboardSummary();

            // Mettre à jour la date/heure
            this.updateDateTime();
            setInterval(() => this.updateDateTime(), 1000);

            this.isInitialized = true;
            console.log('✅ Dashboard Home prêt');

        } catch (error) {
            console.error('Erreur initialisation Dashboard Home:', error);
            this.showToast('Erreur d\'initialisation', 'error');
        }
    }

    /**
     * S'abonner au module dashboard via WebSocket
     */
    async subscribeToModule() {
        if (this.wsClient && this.wsClient.isConnected) {
            try {
                await this.wsClient.subscribeToModule('dashboard');
                console.log('✅ Abonné au module dashboard');
            } catch (error) {
                console.error('Erreur abonnement:', error);
            }
        }
    }

    /**
     * Initialiser les événements WebSocket
     */
    initWebSocketEvents() {
        if (!this.wsClient) return;

        // Résumé du dashboard
        this.wsClient.on('dashboard_summary', (data) => {
            this.updateDashboardSummary(data);
        });

        // Mise à jour du statut d'un module
        this.wsClient.on('module_status_update', (data) => {
            this.updateModuleStatus(data.module, data.status);
        });

        // Activité log
        this.wsClient.on('activity_log', (event) => {
            this.addActivityEvent(event);
        });

        // Événements de collecte globale
        this.wsClient.on('collection_started', (data) => {
            this.handleCollectionStarted(data);
        });

        this.wsClient.on('collection_stopped', (data) => {
            this.handleCollectionStopped(data);
        });

        // Écouter les événements de données des modules
        this.listenToModuleData();
    }

    /**
     * Écouter les données en temps réel des modules
     */
    listenToModuleData() {
        // Polar
        this.wsClient.on('polar_realtime_data', (data) => {
            this.updatePolarData(data);
        });

        // Neurosity
        this.wsClient.on('neurosity_calm_data', (data) => {
            this.updateNeurosityData('calm', data);
        });

        this.wsClient.on('neurosity_focus_data', (data) => {
            this.updateNeurosityData('focus', data);
        });

        this.wsClient.on('neurosity_brainwaves_data', (data) => {
            this.updateNeurosityBrainwaves(data);
        });

        // Thermal Camera
        this.wsClient.on('thermal_temperature_data', (data) => {
            this.updateThermalData(data);
        });

        // Gazepoint
        this.wsClient.on('gazepoint_gaze_data', (data) => {
            this.updateGazepointData(data);
        });

        // Thought Capture
        this.wsClient.on('audio_level_update', (data) => {
            this.updateAudioLevel(data.level);
        });

        this.wsClient.on('recording_status_update', (data) => {
            this.updateThoughtCaptureStatus(data);
        });
    }

    /**
     * Initialiser les contrôles UI
     */
    initUIControls() {
        // Bouton démarrer collecte
        const startBtn = document.getElementById('homeStartCollection');
        if (startBtn) {
            startBtn.addEventListener('click', () => this.startGlobalCollection());
        }

        // Bouton arrêter collecte
        const stopBtn = document.getElementById('homeStopCollection');
        if (stopBtn) {
            stopBtn.addEventListener('click', () => this.stopGlobalCollection());
        }

        // Bouton télécharger
        const downloadBtn = document.getElementById('homeDownloadData');
        if (downloadBtn) {
            downloadBtn.addEventListener('click', () => this.downloadAllData());
        }
    }

    /**
     * Demander le résumé du dashboard
     */
    requestDashboardSummary() {
        if (this.wsClient && this.wsClient.isConnected) {
            this.wsClient.emitToModule('dashboard', 'request_summary', {});
        }
    }

    /**
     * Mettre à jour le résumé complet du dashboard
     */
    updateDashboardSummary(summary) {
        // Mettre à jour les statuts des modules
        if (summary.modules_status) {
            Object.entries(summary.modules_status).forEach(([module, status]) => {
                this.updateModuleStatus(module, status);
            });
        }

        // Mettre à jour les statistiques globales
        if (summary.global_stats) {
            this.updateGlobalStats(summary.global_stats);
        }

        // Mettre à jour l'activité récente
        if (summary.recent_activity) {
            this.updateActivityTimeline(summary.recent_activity);
        }
    }

    /**
     * Mettre à jour le statut d'un module
     */
    updateModuleStatus(moduleName, status) {
        this.modulesStatus[moduleName] = status;

        // Mettre à jour le badge de statut
        const statusBadge = document.querySelector(`[data-module="${moduleName}"] .home_status-badge`);
        if (statusBadge) {
            if (status.connected && status.active) {
                statusBadge.textContent = 'Actif';
                statusBadge.className = 'home_status-badge connected recording';
            } else if (status.connected) {
                statusBadge.textContent = 'Connecté';
                statusBadge.className = 'home_status-badge connected';
            } else {
                statusBadge.textContent = 'Déconnecté';
                statusBadge.className = 'home_status-badge';
            }
        }

        // Compter les modules actifs
        this.updateActiveModulesCount();
    }

    /**
     * Mettre à jour les données Polar
     */
    updatePolarData(data) {
        // BPM
        const bpmElement = document.getElementById('homePolarBPM');
        if (bpmElement && data.heart_rate) {
            this.animateValue(bpmElement, data.heart_rate, 'BPM');
        }

        // RR Interval
        const rrElement = document.getElementById('homePolarRR');
        if (rrElement && data.rr_interval) {
            this.animateValue(rrElement, Math.round(data.rr_interval), 'ms');
        }

        // HRV
        const hrvElement = document.getElementById('homePolarHRV');
        if (hrvElement && data.hrv) {
            this.animateValue(hrvElement, data.hrv.toFixed(1));
        }

        // Mettre à jour le mini graphique
        this.updatePolarChart(data.heart_rate);

        // Incrémenter les points de données
        this.incrementDataPoints();
    }

    /**
     * Mettre à jour les données Neurosity
     */
    updateNeurosityData(type, data) {
        if (type === 'calm') {
            const calmPercent = document.getElementById('homeNeurosityCalm');
            const calmBar = document.querySelector('.home_calm-fill');
            if (calmPercent && calmBar) {
                const value = Math.round(data.calm * 100);
                calmPercent.textContent = value + '%';
                calmBar.style.width = value + '%';
            }
        } else if (type === 'focus') {
            const focusPercent = document.getElementById('homeNeurosityFocus');
            const focusBar = document.querySelector('.home_focus-fill');
            if (focusPercent && focusBar) {
                const value = Math.round(data.focus * 100);
                focusPercent.textContent = value + '%';
                focusBar.style.width = value + '%';
            }
        }

        this.incrementDataPoints();
    }

    /**
     * Mettre à jour les ondes cérébrales
     */
    updateNeurosityBrainwaves(data) {
        // Ici on pourrait ajouter un mini graphique des ondes
        // Pour l'instant on se contente d'incrémenter les points
        this.incrementDataPoints();
    }

    /**
     * Mettre à jour les données thermiques
     */
    updateThermalData(data) {
        // Température moyenne
        const avgTempElement = document.getElementById('homeThermalAvgTemp');
        if (avgTempElement && data.average_temp) {
            this.animateValue(avgTempElement, data.average_temp.toFixed(1), '°C');
        }

        // Température max
        const maxTempElement = document.getElementById('homeThermalMaxTemp');
        if (maxTempElement && data.max_temp) {
            this.animateValue(maxTempElement, data.max_temp.toFixed(1), '°C');
        }

        // Mettre à jour la visualisation SVG
        this.updateThermalVisualization(data);

        this.incrementDataPoints();
    }

    /**
     * Mettre à jour la visualisation thermique SVG
     */
    updateThermalVisualization(data) {
        // Simuler des points de température sur le visage
        const tempPoints = [
            { id: 'forehead', selector: '.home_temp-forehead', temp: data.max_temp },
            { id: 'nose', selector: '.home_temp-nose', temp: data.average_temp },
            { id: 'cheek-left', selector: '.home_temp-cheek-left', temp: data.average_temp - 0.2 },
            { id: 'cheek-right', selector: '.home_temp-cheek-right', temp: data.average_temp - 0.2 }
        ];

        tempPoints.forEach(point => {
            const element = document.querySelector(point.selector);
            if (element) {
                // Couleur basée sur la température
                const color = this.getTemperatureColor(point.temp);
                element.setAttribute('fill', color);

                // Mettre à jour le label
                const label = element.nextElementSibling;
                if (label) {
                    label.textContent = point.temp.toFixed(1) + '°';
                }
            }
        });
    }

    /**
     * Obtenir la couleur selon la température
     */
    getTemperatureColor(temp) {
        if (temp >= 37.5) return '#ef4444'; // Rouge (fièvre)
        if (temp >= 37.0) return '#f59e0b'; // Orange
        if (temp >= 36.5) return '#10b981'; // Vert
        return '#3b82f6'; // Bleu
    }

    /**
     * Mettre à jour les données Gazepoint
     */
    updateGazepointData(data) {
        // Position du regard
        const gazeXElement = document.getElementById('homeGazeX');
        const gazeYElement = document.getElementById('homeGazeY');

        if (gazeXElement && data.gaze_x !== undefined) {
            this.animateValue(gazeXElement, Math.round(data.gaze_x));
        }

        if (gazeYElement && data.gaze_y !== undefined) {
            this.animateValue(gazeYElement, Math.round(data.gaze_y));
        }

        // Diamètre pupillaire
        const pupilElement = document.getElementById('homeGazePupil');
        if (pupilElement && data.pupil_diameter) {
            this.animateValue(pupilElement, data.pupil_diameter.toFixed(1), 'mm');
        }

        // Animer les yeux
        this.animateEyes(data.gaze_x, data.gaze_y);

        this.incrementDataPoints();
    }

    /**
     * Animer les yeux selon la position du regard
     */
    animateEyes(x, y) {
        const pupils = document.querySelectorAll('.home_pupil');
        pupils.forEach(pupil => {
            if (pupil) {
                // Normaliser les coordonnées (0-1920, 0-1080) vers (-10, 10)
                const offsetX = ((x / 1920) - 0.5) * 20;
                const offsetY = ((y / 1080) - 0.5) * 20;

                pupil.style.transform = `translate(calc(-50% + ${offsetX}px), calc(-50% + ${offsetY}px))`;
            }
        });
    }

    /**
     * Mettre à jour le niveau audio
     */
    updateAudioLevel(level) {
        const levelFill = document.getElementById('homeAudioLevel');
        if (levelFill) {
            levelFill.style.width = (level * 100) + '%';
        }
    }

    /**
     * Mettre à jour le statut de Thought Capture
     */
    updateThoughtCaptureStatus(data) {
        const statusBadge = document.querySelector('[data-module="thought_capture"] .home_status-badge');
        const recordingTime = document.getElementById('homeRecordingTime');

        if (data.isRecording) {
            if (statusBadge) {
                statusBadge.textContent = 'Enregistrement';
                statusBadge.className = 'home_status-badge recording';
            }

            // Mettre à jour le timer
            if (recordingTime && data.duration) {
                const minutes = Math.floor(data.duration / 60);
                const seconds = data.duration % 60;
                recordingTime.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            }
        } else {
            if (statusBadge) {
                statusBadge.textContent = 'Prêt';
                statusBadge.className = 'home_status-badge';
            }

            if (recordingTime) {
                recordingTime.textContent = '00:00';
            }
        }

        // Dernier enregistrement
        if (data.lastRecording) {
            const lastRecording = document.getElementById('homeLastRecording');
            if (lastRecording) {
                lastRecording.textContent = data.lastRecording;
            }
        }
    }

    /**
     * Mettre à jour les statistiques globales
     */
    updateGlobalStats(stats) {
        this.globalStats = { ...this.globalStats, ...stats };

        // Modules actifs
        const activeModulesElement = document.getElementById('homeActiveModules');
        if (activeModulesElement) {
            this.animateValue(activeModulesElement, this.globalStats.activeModules);
        }

        // Points de données
        const dataPointsElement = document.getElementById('homeDataPoints');
        if (dataPointsElement) {
            this.animateValue(dataPointsElement, this.globalStats.dataPoints);
        }

        // Durée de session
        if (stats.session_duration) {
            const sessionTimeElement = document.getElementById('homeSessionTime');
            if (sessionTimeElement) {
                sessionTimeElement.textContent = this.formatDuration(stats.session_duration);
            }
        }

        // Stockage utilisé
        const storageElement = document.getElementById('homeStorageUsed');
        if (storageElement && stats.storage_used !== undefined) {
            storageElement.textContent = `${stats.storage_used} MB`;
        }
    }

    /**
     * Compter et mettre à jour le nombre de modules actifs
     */
    updateActiveModulesCount() {
        const count = Object.values(this.modulesStatus).filter(m => m.active).length;
        this.globalStats.activeModules = count;

        const element = document.getElementById('homeActiveModules');
        if (element) {
            this.animateValue(element, count);
        }
    }

    /**
     * Incrémenter le compteur de points de données
     */
    incrementDataPoints() {
        this.globalStats.dataPoints++;
        const element = document.getElementById('homeDataPoints');
        if (element) {
            element.textContent = this.formatNumber(this.globalStats.dataPoints);
        }
    }

    /**
     * Mettre à jour la timeline d'activité
     */
    updateActivityTimeline(events) {
        const timeline = document.getElementById('homeActivityTimeline');
        if (!timeline) return;

        timeline.innerHTML = '';

        if (events.length === 0) {
            timeline.innerHTML = `
                <div class="home_timeline-item">
                    <span class="home_timeline-dot"></span>
                    <span class="home_timeline-text">En attente de données...</span>
                </div>
            `;
            return;
        }

        events.forEach(event => {
            const item = document.createElement('div');
            item.className = 'home_timeline-item';

            const time = new Date(event.timestamp).toLocaleTimeString('fr-FR', {
                hour: '2-digit',
                minute: '2-digit'
            });

            item.innerHTML = `
                <span class="home_timeline-dot" style="background: ${this.getEventColor(event.level)}"></span>
                <span class="home_timeline-text">
                    <strong>${time}</strong> - ${event.module}: ${event.message}
                </span>
            `;

            timeline.appendChild(item);
        });
    }

    /**
     * Ajouter un événement à la timeline
     */
    addActivityEvent(event) {
        const timeline = document.getElementById('homeActivityTimeline');
        if (!timeline) return;

        // Créer le nouvel élément
        const item = document.createElement('div');
        item.className = 'home_timeline-item';
        item.style.opacity = '0';

        const time = new Date(event.timestamp).toLocaleTimeString('fr-FR', {
            hour: '2-digit',
            minute: '2-digit'
        });

        item.innerHTML = `
            <span class="home_timeline-dot" style="background: ${this.getEventColor(event.level)}"></span>
            <span class="home_timeline-text">
                <strong>${time}</strong> - ${event.module}: ${event.message}
            </span>
        `;

        // Ajouter en haut de la liste
        timeline.insertBefore(item, timeline.firstChild);

        // Animer l'apparition
        setTimeout(() => {
            item.style.opacity = '1';
            item.style.transition = 'opacity 0.3s ease';
        }, 10);

        // Limiter le nombre d'éléments affichés
        while (timeline.children.length > 10) {
            timeline.removeChild(timeline.lastChild);
        }
    }

    /**
     * Obtenir la couleur selon le niveau d'événement
     */
    getEventColor(level) {
        const colors = {
            'success': '#10b981',
            'info': '#3b82f6',
            'warning': '#f59e0b',
            'error': '#ef4444'
        };
        return colors[level] || colors.info;
    }

    /**
     * Démarrer la collecte globale
     */
    async startGlobalCollection() {
        try {
            // Appel API pour démarrer la collecte
            const response = await fetch('/api/dashboard/start-collection', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            const result = await response.json();

            if (result.success) {
                this.showToast('Collecte globale démarrée', 'success');

                // Mettre à jour l'UI
                document.getElementById('homeStartCollection').disabled = true;
                document.getElementById('homeStopCollection').disabled = false;

                // Démarrer le timer de session
                this.globalStats.sessionStart = Date.now();
                this.updateSessionTimer();
            } else {
                this.showToast('Erreur lors du démarrage', 'error');
            }
        } catch (error) {
            console.error('Erreur démarrage collecte:', error);
            this.showToast('Erreur de connexion', 'error');
        }
    }

    /**
     * Arrêter la collecte globale
     */
    async stopGlobalCollection() {
        try {
            const response = await fetch('/api/dashboard/stop-collection', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            const result = await response.json();

            if (result.success) {
                this.showToast('Collecte globale arrêtée', 'info');

                // Mettre à jour l'UI
                document.getElementById('homeStartCollection').disabled = false;
                document.getElementById('homeStopCollection').disabled = true;

                // Arrêter le timer
                this.globalStats.sessionStart = null;
            } else {
                this.showToast('Erreur lors de l\'arrêt', 'error');
            }
        } catch (error) {
            console.error('Erreur arrêt collecte:', error);
            this.showToast('Erreur de connexion', 'error');
        }
    }

    /**
     * Gérer l'événement de démarrage de collecte
     */
    handleCollectionStarted(data) {
        document.getElementById('homeStartCollection').disabled = true;
        document.getElementById('homeStopCollection').disabled = false;

        this.globalStats.sessionStart = Date.now();
        this.updateSessionTimer();

        this.showToast('Collecte démarrée sur tous les modules', 'success');
    }

    /**
     * Gérer l'événement d'arrêt de collecte
     */
    handleCollectionStopped(data) {
        document.getElementById('homeStartCollection').disabled = false;
        document.getElementById('homeStopCollection').disabled = true;

        this.globalStats.sessionStart = null;

        this.showToast('Collecte arrêtée sur tous les modules', 'info');
    }

    /**
     * Mettre à jour le timer de session
     */
    updateSessionTimer() {
        if (!this.globalStats.sessionStart) return;

        const updateTimer = () => {
            if (!this.globalStats.sessionStart) return;

            const elapsed = Date.now() - this.globalStats.sessionStart;
            const seconds = Math.floor(elapsed / 1000);
            const minutes = Math.floor(seconds / 60);
            const hours = Math.floor(minutes / 60);

            let timeStr;
            if (hours > 0) {
                timeStr = `${hours}h ${minutes % 60}m`;
            } else {
                timeStr = `${minutes}:${(seconds % 60).toString().padStart(2, '0')}`;
            }

            const element = document.getElementById('homeSessionTime');
            if (element) {
                element.textContent = timeStr;
            }

            // Continuer la mise à jour
            if (this.globalStats.sessionStart) {
                requestAnimationFrame(updateTimer);
            }
        };

        updateTimer();
    }

    /**
     * Télécharger toutes les données
     */
    async downloadAllData() {
        this.showToast('Préparation du téléchargement...', 'info');

        // Ici on pourrait implémenter le téléchargement des données
        // Pour l'instant on affiche juste un message
        setTimeout(() => {
            this.showToast('Fonction de téléchargement en développement', 'warning');
        }, 1000);
    }

    /**
     * Initialiser les mini graphiques
     */
    initMiniCharts() {
        // Initialiser le graphique Polar
        const polarCanvas = document.querySelector('.home_mini-chart canvas');
        if (polarCanvas) {
            this.initPolarMiniChart(polarCanvas);
        }
    }

    /**
     * Initialiser le mini graphique Polar
     */
    initPolarMiniChart(canvas) {
        const ctx = canvas.getContext('2d');
        canvas.width = canvas.offsetWidth;
        canvas.height = canvas.offsetHeight;

        // Données du graphique
        this.charts.polar = {
            ctx: ctx,
            data: [],
            maxPoints: 50
        };
    }

    /**
     * Mettre à jour le graphique Polar
     */
    updatePolarChart(heartRate) {
        if (!this.charts.polar) return;

        const chart = this.charts.polar;
        chart.data.push(heartRate);

        // Limiter le nombre de points
        if (chart.data.length > chart.maxPoints) {
            chart.data.shift();
        }

        // Redessiner le graphique
        const ctx = chart.ctx;
        const width = ctx.canvas.width;
        const height = ctx.canvas.height;

        // Effacer
        ctx.clearRect(0, 0, width, height);

        // Dessiner la ligne
        ctx.beginPath();
        ctx.strokeStyle = '#ef4444';
        ctx.lineWidth = 2;

        chart.data.forEach((value, index) => {
            const x = (index / (chart.maxPoints - 1)) * width;
            const y = height - ((value - 40) / 80) * height; // Normaliser entre 40-120 BPM

            if (index === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        });

        ctx.stroke();
    }

    /**
     * Démarrer la mise à jour automatique
     */
    startAutoUpdate() {
        // Mettre à jour les données toutes les secondes
        this.updateInterval = setInterval(() => {
            // Demander les informations de stockage
            this.updateStorageInfo();

            // Mettre à jour le timer de session si actif
            if (this.globalStats.sessionStart) {
                this.updateSessionTimer();
            }
        }, this.config.updateInterval);
    }

    /**
     * Mettre à jour les informations de stockage
     */
    async updateStorageInfo() {
        try {
            const response = await fetch('/api/dashboard/storage');
            const data = await response.json();

            if (data.storage_used_formatted) {
                const element = document.getElementById('homeStorageUsed');
                if (element) {
                    element.textContent = data.storage_used_formatted;
                }
            }
        } catch (error) {
            console.error('Erreur récupération stockage:', error);
        }
    }

    /**
     * Animer la valeur d'un élément
     */
    animateValue(element, newValue, suffix = '') {
        const current = parseFloat(element.textContent) || 0;
        const diff = newValue - current;
        const duration = 300;
        const startTime = Date.now();

        const animate = () => {
            const elapsed = Date.now() - startTime;
            const progress = Math.min(elapsed / duration, 1);

            const value = current + (diff * this.easeOutQuart(progress));
            element.textContent = Math.round(value) + suffix;

            if (progress < 1) {
                requestAnimationFrame(animate);
            }
        };

        animate();
    }

    /**
     * Fonction d'easing
     */
    easeOutQuart(t) {
        return 1 - Math.pow(1 - t, 4);
    }

    /**
     * Formater un nombre
     */
    formatNumber(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toString();
    }

    /**
     * Formater une durée
     */
    formatDuration(duration) {
        // Parser la durée si c'est une chaîne
        if (typeof duration === 'string') {
            const parts = duration.match(/(\d+):(\d+):(\d+)/);
            if (parts) {
                const hours = parseInt(parts[1]);
                const minutes = parseInt(parts[2]);

                if (hours > 0) {
                    return `${hours}h ${minutes}m`;
                } else {
                    return `${minutes}m`;
                }
            }
        }
        return '0m';
    }

    /**
     * Mettre à jour la date et l'heure
     */
    updateDateTime() {
        const element = document.getElementById('homeDateTime');
        if (element) {
            const now = new Date();
            const date = now.toLocaleDateString('fr-FR', {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            });
            const time = now.toLocaleTimeString('fr-FR', {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });

            element.textContent = `${date} - ${time}`;
        }
    }

    /**
     * Afficher un toast de notification
     */
    showToast(message, type = 'info') {
        const container = document.getElementById('homeToastContainer');
        if (!container) return;

        // Créer le toast
        const toast = document.createElement('div');
        toast.className = `home_toast ${type}`;

        const icons = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };

        toast.innerHTML = `
            <i class="fas ${icons[type] || icons.info}"></i>
            <span>${message}</span>
        `;

        container.appendChild(toast);

        // Animation d'apparition
        setTimeout(() => {
            toast.style.opacity = '1';
        }, 10);

        // Supprimer après un délai
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => {
                container.removeChild(toast);
            }, 300);
        }, this.config.toastDuration);
    }

    /**
     * Nettoyer le module
     */
    cleanup() {
        console.log('🧹 Nettoyage Dashboard Home');

        // Arrêter les intervalles
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }

        // Retirer les écouteurs WebSocket
        if (this.wsClient) {
            this.wsClient.off('dashboard_summary');
            this.wsClient.off('module_status_update');
            this.wsClient.off('activity_log');
            this.wsClient.off('collection_started');
            this.wsClient.off('collection_stopped');

            // Retirer les écouteurs de données
            this.wsClient.off('polar_realtime_data');
            this.wsClient.off('neurosity_calm_data');
            this.wsClient.off('neurosity_focus_data');
            this.wsClient.off('neurosity_brainwaves_data');
            this.wsClient.off('thermal_temperature_data');
            this.wsClient.off('gazepoint_gaze_data');
            this.wsClient.off('audio_level_update');
            this.wsClient.off('recording_status_update');
        }

        this.isInitialized = false;
    }
}

// Fonction d'initialisation globale
function initDashboardHome() {
    console.log('🚀 Chargement module Dashboard Home');

    // Créer et retourner l'instance
    const dashboardHome = new DashboardHomeModule();
    dashboardHome.init();

    return dashboardHome;
}

// Export pour utilisation dans le dashboard principal
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { DashboardHomeModule, initDashboardHome };
} else if (typeof window !== 'undefined') {
    window.DashboardHomeModule = DashboardHomeModule;
    window.initDashboardHome = initDashboardHome;
}