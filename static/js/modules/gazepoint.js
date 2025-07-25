/**
 * Module Gazepoint - Frontend
 * Gestion du tracking oculaire en temps réel
 */

(function() {
    'use strict';

    // Protection contre les redéclarations
    if (window.GazepointModuleClass) {
        console.log('Module Gazepoint déjà chargé, skip');
        return;
    }

    class GazepointModule {
        constructor() {
            // État du module
            this.isConnected = false;
            this.isTracking = false;
            this.isRecording = false;
            this.isCalibrating = false;

            // WebSocket client
            this.wsClient = null;

            // Canvas pour affichage du regard
            this.gazeCanvas = null;
            this.gazeCtx = null;

            // Données actuelles
            this.currentData = {
                gaze: { x: 0.5, y: 0.5 },
                eyes: {
                    left: { x: 0, y: 0, pupil: 0, valid: false, closed: false },
                    right: { x: 0, y: 0, pupil: 0, valid: false, closed: false }
                },
                fixation: { x: 0.5, y: 0.5, duration: 0, id: 0, valid: false },
                aoi: { current: null, zones: {} }
            };

            // Configuration
            this.config = {
                gazeTrailLength: 50,
                aoiHeatmapEnabled: true,
                eyeTrackingVisualization: true
            };

            // Zones d'intérêt prédéfinies
            this.aoiZones = {
                'top_left': { name: 'Haut Gauche', color: '#ff6b6b' },
                'top_center': { name: 'Haut Centre', color: '#4ecdc4' },
                'top_right': { name: 'Haut Droite', color: '#45b7d1' },
                'center_left': { name: 'Centre Gauche', color: '#96ceb4' },
                'center': { name: 'Centre', color: '#feca57' },
                'center_right': { name: 'Centre Droite', color: '#dfe6e9' },
                'bottom_left': { name: 'Bas Gauche', color: '#fab1a0' },
                'bottom_center': { name: 'Bas Centre', color: '#fd79a8' },
                'bottom_right': { name: 'Bas Droite', color: '#a29bfe' }
            };

            // Historique pour visualisation
            this.gazeTrail = [];
            this.fixationHistory = [];

            // Statistiques
            this.stats = {
                totalFixations: 0,
                averageFixationDuration: 0,
                heatmapData: []
            };

            // Sessions d'enregistrement
            this.recordings = [];

            this.init();
        }

        async init() {
            console.log('Initialisation du module Gazepoint');

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
            this.initCanvas();
            this.initVisualization();
            this.setupEventListeners();

            // Charger les sessions
            await this.loadRecordings();

            console.log('Module Gazepoint prêt');
        }

        async waitForDashboard() {
            let attempts = 0;
            while ((!window.dashboard || !window.dashboard.wsClient) && attempts < 50) {
                await new Promise(resolve => setTimeout(resolve, 100));
                attempts++;
            }
        }

        setupWebSocketHandlers() {
            if (!this.wsClient) return;

            console.log('Configuration des handlers WebSocket Gazepoint');

            // Connexion
            this.wsClient.on('gazepoint_connected', (data) => {
                console.log('Gazepoint connecté:', data);
                this.isConnected = true;
                this.updateUI();
                this.showToast('Gazepoint connecté !', 'success');
            });

            this.wsClient.on('gazepoint_disconnected', (data) => {
                console.log('Gazepoint déconnecté');
                this.isConnected = false;
                this.isTracking = false;
                this.updateUI();
                this.showToast('Gazepoint déconnecté', 'info');
            });

            // Données en temps réel
            this.wsClient.on('gazepoint_data', (data) => {
                this.handleGazeData(data);
            });

            // Tracking
            this.wsClient.on('gazepoint_tracking_started', (data) => {
                this.isTracking = true;
                this.updateUI();
                this.showToast('Tracking démarré', 'success');
            });

            this.wsClient.on('gazepoint_tracking_stopped', (data) => {
                this.isTracking = false;
                this.updateUI();
                this.showToast('Tracking arrêté', 'info');
            });

            // Enregistrement
            this.wsClient.on('gazepoint_recording_started', (data) => {
                this.isRecording = true;
                this.updateUI();
                this.showToast(`Enregistrement démarré: ${data.filename}`, 'success');
            });

            this.wsClient.on('gazepoint_recording_stopped', (data) => {
                this.isRecording = false;
                this.updateUI();
                this.showToast(`Enregistrement terminé: ${data.lines} lignes`, 'info');
                setTimeout(() => this.loadRecordings(), 1000);
            });

            // Calibration
            this.wsClient.on('gazepoint_calibration_point', (data) => {
                this.showCalibrationPoint(data);
            });

            this.wsClient.on('gazepoint_calibration_complete', (data) => {
                this.isCalibrating = false;
                this.showToast('Calibration terminée !', 'success');
            });

            // Liste des enregistrements
            this.wsClient.on('gazepoint_recordings_list', (data) => {
                this.displayRecordings(data.recordings || []);
            });

            // Erreurs
            this.wsClient.on('gazepoint_error', (data) => {
                console.error('Erreur Gazepoint:', data);
                this.showToast(`Erreur: ${data.error}`, 'error');
            });
        }

        setupEventListeners() {
            // Bouton connexion
            const connectBtn = document.getElementById('gaze_connectBtn');
            if (connectBtn) {
                connectBtn.addEventListener('click', () => this.toggleConnection());
            }

            // Bouton tracking
            const trackingBtn = document.getElementById('gaze_trackingBtn');
            if (trackingBtn) {
                trackingBtn.addEventListener('click', () => this.toggleTracking());
            }

            // Bouton enregistrement
            const recordBtn = document.getElementById('gaze_recordBtn');
            if (recordBtn) {
                recordBtn.addEventListener('click', () => this.toggleRecording());
            }

            // Bouton calibration
            const calibrateBtn = document.getElementById('gaze_calibrateBtn');
            if (calibrateBtn) {
                calibrateBtn.addEventListener('click', () => this.startCalibration());
            }

            // Bouton actualiser les enregistrements
            const refreshBtn = document.getElementById('gaze_refreshBtn');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', () => this.loadRecordings());
            }

            // Toggle heatmap
            const heatmapToggle = document.getElementById('gaze_heatmapToggle');
            if (heatmapToggle) {
                heatmapToggle.addEventListener('change', (e) => {
                    this.config.aoiHeatmapEnabled = e.target.checked;
                });
            }
        }

        initCanvas() {
            // Canvas pour la visualisation du regard
            this.gazeCanvas = document.getElementById('gaze_gazeCanvas');
            if (this.gazeCanvas) {
                this.gazeCtx = this.gazeCanvas.getContext('2d');
                this.gazeCanvas.width = 800;
                this.gazeCanvas.height = 600;

                // Démarrer l'animation
                this.startVisualizationLoop();
            }
        }

        initVisualization() {
            // Initialiser la grille AOI
            this.drawAOIGrid();
        }

        toggleConnection() {
            if (this.isConnected) {
                this.disconnect();
            } else {
                this.connect();
            }
        }

        connect() {
            if (this.wsClient) {
                this.wsClient.emitToModule('gazepoint', 'connect', {});
                this.showToast('Connexion à Gazepoint...', 'info');
            }
        }

        disconnect() {
            if (this.wsClient) {
                this.wsClient.emitToModule('gazepoint', 'disconnect', {});
            }
        }

        toggleTracking() {
            if (!this.isConnected) {
                this.showToast('Connectez-vous d\'abord à Gazepoint', 'warning');
                return;
            }

            if (this.isTracking) {
                this.stopTracking();
            } else {
                this.startTracking();
            }
        }

        startTracking() {
            if (this.wsClient) {
                this.wsClient.emitToModule('gazepoint', 'start_tracking', {});
            }
        }

        stopTracking() {
            if (this.wsClient) {
                this.wsClient.emitToModule('gazepoint', 'stop_tracking', {});
            }
        }

        toggleRecording() {
            if (!this.isTracking) {
                this.showToast('Démarrez d\'abord le tracking', 'warning');
                return;
            }

            if (this.isRecording) {
                this.stopRecording();
            } else {
                this.startRecording();
            }
        }

        startRecording() {
            if (this.wsClient) {
                this.wsClient.emitToModule('gazepoint', 'start_recording', {});
            }
        }

        stopRecording() {
            if (this.wsClient) {
                this.wsClient.emitToModule('gazepoint', 'stop_recording', {});
            }
        }

        startCalibration() {
            if (!this.isConnected) {
                this.showToast('Connectez-vous d\'abord à Gazepoint', 'warning');
                return;
            }

            if (this.wsClient) {
                this.wsClient.emitToModule('gazepoint', 'start_calibration', {});
                this.isCalibrating = true;
                this.showToast('Calibration démarrée, suivez les points', 'info');
            }
        }

        handleGazeData(data) {
            // Mettre à jour les données actuelles
            this.currentData = data;

            // Ajouter au trail du regard
            this.gazeTrail.push({
                x: data.gaze.x,
                y: data.gaze.y,
                timestamp: Date.now()
            });

            // Limiter la longueur du trail
            if (this.gazeTrail.length > this.config.gazeTrailLength) {
                this.gazeTrail.shift();
            }

            // Mettre à jour les fixations
            if (data.fixation.valid && data.fixation.duration > 0) {
                this.updateFixations(data.fixation);
            }

            // Mettre à jour les statistiques AOI
            this.updateAOIStats(data.aoi);

            // Mettre à jour l'affichage des yeux
            this.updateEyesDisplay(data.eyes);

            // Mettre à jour les métriques
            this.updateMetrics(data);
        }

        updateFixations(fixation) {
            // Ajouter à l'historique si c'est une nouvelle fixation
            const lastFixation = this.fixationHistory[this.fixationHistory.length - 1];
            if (!lastFixation || lastFixation.id !== fixation.id) {
                this.fixationHistory.push({
                    x: fixation.x,
                    y: fixation.y,
                    duration: fixation.duration,
                    id: fixation.id,
                    timestamp: Date.now()
                });

                this.stats.totalFixations++;

                // Limiter l'historique
                if (this.fixationHistory.length > 100) {
                    this.fixationHistory.shift();
                }
            }
        }

        updateAOIStats(aoiData) {
            if (aoiData.current) {
                const currentZone = document.getElementById('gaze_currentZone');
                if (currentZone) {
                    const zoneName = this.aoiZones[aoiData.current]?.name || aoiData.current;
                    currentZone.textContent = zoneName;
                }
            }

            // Mettre à jour le temps dans chaque zone
            if (aoiData.zones) {
                this.updateAOITimeDisplay(aoiData.zones);
            }
        }

        updateAOITimeDisplay(zones) {
            const container = document.getElementById('gaze_aoiStats');
            if (!container) return;

            let html = '';
            for (const [zoneId, zoneData] of Object.entries(zones)) {
                const zoneName = this.aoiZones[zoneId]?.name || zoneId;
                const timeInSeconds = (zoneData.time || 0).toFixed(1);
                const color = this.aoiZones[zoneId]?.color || '#666';

                html += `
                    <div class="gaze_aoi-stat">
                        <span class="gaze_aoi-indicator" style="background: ${color}"></span>
                        <span class="gaze_aoi-name">${zoneName}</span>
                        <span class="gaze_aoi-time">${timeInSeconds}s</span>
                    </div>
                `;
            }

            container.innerHTML = html;
        }

        updateEyesDisplay(eyes) {
            // Mettre à jour l'affichage de l'œil gauche
            const leftEyeCard = document.getElementById('gaze_leftEyeCard');
            if (leftEyeCard) {
                const eyeImg = leftEyeCard.querySelector('.gaze_eye-image');
                const statusText = leftEyeCard.querySelector('.gaze_eye-status');

                if (eyes.left.closed) {
                    eyeImg.classList.add('gaze_eye-closed');
                    statusText.textContent = 'Fermé';
                    statusText.style.color = '#e74c3c';
                } else {
                    eyeImg.classList.remove('gaze_eye-closed');
                    statusText.textContent = 'Ouvert';
                    statusText.style.color = '#27ae60';
                }

                // Afficher la taille de la pupille
                const pupilSize = leftEyeCard.querySelector('.gaze_pupil-size');
                if (pupilSize) {
                    pupilSize.textContent = `Pupille: ${eyes.left.pupil.toFixed(1)}px`;
                }
            }

            // Mettre à jour l'affichage de l'œil droit
            const rightEyeCard = document.getElementById('gaze_rightEyeCard');
            if (rightEyeCard) {
                const eyeImg = rightEyeCard.querySelector('.gaze_eye-image');
                const statusText = rightEyeCard.querySelector('.gaze_eye-status');

                if (eyes.right.closed) {
                    eyeImg.classList.add('gaze_eye-closed');
                    statusText.textContent = 'Fermé';
                    statusText.style.color = '#e74c3c';
                } else {
                    eyeImg.classList.remove('gaze_eye-closed');
                    statusText.textContent = 'Ouvert';
                    statusText.style.color = '#27ae60';
                }

                // Afficher la taille de la pupille
                const pupilSize = rightEyeCard.querySelector('.gaze_pupil-size');
                if (pupilSize) {
                    pupilSize.textContent = `Pupille: ${eyes.right.pupil.toFixed(1)}px`;
                }
            }
        }

        updateMetrics(data) {
            // Nombre de fixations
            const fixationCount = document.getElementById('gaze_fixationCount');
            if (fixationCount) {
                fixationCount.textContent = this.stats.totalFixations;
            }

            // Durée de fixation actuelle
            const fixationDuration = document.getElementById('gaze_fixationDuration');
            if (fixationDuration && data.fixation.valid) {
                fixationDuration.textContent = `${(data.fixation.duration * 1000).toFixed(0)}ms`;
            }

            // Lignes enregistrées
            const recordingLines = document.getElementById('gaze_recordingLines');
            if (recordingLines && data.recording) {
                recordingLines.textContent = data.recording.lines || 0;
            }
        }

        startVisualizationLoop() {
            const animate = () => {
                this.drawVisualization();
                requestAnimationFrame(animate);
            };
            animate();
        }

        drawVisualization() {
            if (!this.gazeCtx) return;

            const ctx = this.gazeCtx;
            const width = this.gazeCanvas.width;
            const height = this.gazeCanvas.height;

            // Effacer le canvas
            ctx.fillStyle = '#f8f9fa';
            ctx.fillRect(0, 0, width, height);

            // Dessiner la grille AOI
            this.drawAOIGrid();

            // Dessiner le heatmap si activé
            if (this.config.aoiHeatmapEnabled) {
                this.drawHeatmap();
            }

            // Dessiner le trail du regard
            this.drawGazeTrail();

            // Dessiner les fixations
            this.drawFixations();

            // Dessiner le curseur de regard actuel
            this.drawGazeCursor();
        }

        drawAOIGrid() {
            const ctx = this.gazeCtx;
            const width = this.gazeCanvas.width;
            const height = this.gazeCanvas.height;

            ctx.strokeStyle = '#ddd';
            ctx.lineWidth = 1;

            // Lignes verticales
            for (let i = 1; i < 3; i++) {
                const x = (width / 3) * i;
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, height);
                ctx.stroke();
            }

            // Lignes horizontales
            for (let i = 1; i < 3; i++) {
                const y = (height / 3) * i;
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(width, y);
                ctx.stroke();
            }

            // Labels des zones
            ctx.font = '12px Arial';
            ctx.fillStyle = '#666';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';

            const zones = [
                ['top_left', 'top_center', 'top_right'],
                ['center_left', 'center', 'center_right'],
                ['bottom_left', 'bottom_center', 'bottom_right']
            ];

            for (let row = 0; row < 3; row++) {
                for (let col = 0; col < 3; col++) {
                    const x = (width / 3) * col + width / 6;
                    const y = (height / 3) * row + height / 6;
                    const zoneId = zones[row][col];
                    const zoneName = this.aoiZones[zoneId]?.name || zoneId;
                    ctx.fillText(zoneName, x, y);
                }
            }
        }

        drawHeatmap() {
            // Dessiner un heatmap simple basé sur les fixations
            const ctx = this.gazeCtx;

            for (const fixation of this.fixationHistory) {
                const x = fixation.x * this.gazeCanvas.width;
                const y = fixation.y * this.gazeCanvas.height;
                const radius = Math.min(fixation.duration * 100, 50);

                const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
                gradient.addColorStop(0, 'rgba(255, 0, 0, 0.3)');
                gradient.addColorStop(1, 'rgba(255, 0, 0, 0)');

                ctx.fillStyle = gradient;
                ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
            }
        }

        drawGazeTrail() {
            const ctx = this.gazeCtx;

            if (this.gazeTrail.length < 2) return;

            ctx.strokeStyle = '#3498db';
            ctx.lineWidth = 2;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';

            ctx.beginPath();
            for (let i = 0; i < this.gazeTrail.length; i++) {
                const point = this.gazeTrail[i];
                const x = point.x * this.gazeCanvas.width;
                const y = point.y * this.gazeCanvas.height;

                // Opacité basée sur l'âge du point
                const age = Date.now() - point.timestamp;
                const opacity = Math.max(0, 1 - age / 5000);
                ctx.globalAlpha = opacity * (i / this.gazeTrail.length);

                if (i === 0) {
                    ctx.moveTo(x, y);
                } else {
                    ctx.lineTo(x, y);
                }
            }
            ctx.stroke();
            ctx.globalAlpha = 1;
        }

        drawFixations() {
            const ctx = this.gazeCtx;

            for (const fixation of this.fixationHistory.slice(-20)) {
                const x = fixation.x * this.gazeCanvas.width;
                const y = fixation.y * this.gazeCanvas.height;
                const radius = Math.min(fixation.duration * 20, 30);

                ctx.fillStyle = 'rgba(231, 76, 60, 0.5)';
                ctx.beginPath();
                ctx.arc(x, y, radius, 0, Math.PI * 2);
                ctx.fill();

                // Bordure
                ctx.strokeStyle = '#e74c3c';
                ctx.lineWidth = 2;
                ctx.stroke();
            }
        }

        drawGazeCursor() {
            const ctx = this.gazeCtx;
            const x = this.currentData.gaze.x * this.gazeCanvas.width;
            const y = this.currentData.gaze.y * this.gazeCanvas.height;

            // Cercle extérieur
            ctx.strokeStyle = '#2ecc71';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(x, y, 15, 0, Math.PI * 2);
            ctx.stroke();

            // Point central
            ctx.fillStyle = '#27ae60';
            ctx.beginPath();
            ctx.arc(x, y, 5, 0, Math.PI * 2);
            ctx.fill();

            // Croix
            ctx.strokeStyle = '#27ae60';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(x - 20, y);
            ctx.lineTo(x + 20, y);
            ctx.moveTo(x, y - 20);
            ctx.lineTo(x, y + 20);
            ctx.stroke();
        }

        showCalibrationPoint(data) {
            // Afficher le point de calibration sur le canvas
            if (!this.gazeCtx) return;

            const x = parseFloat(data.x) * this.gazeCanvas.width;
            const y = parseFloat(data.y) * this.gazeCanvas.height;

            // Effacer et dessiner le point de calibration
            this.gazeCtx.fillStyle = '#e74c3c';
            this.gazeCtx.beginPath();
            this.gazeCtx.arc(x, y, 10, 0, Math.PI * 2);
            this.gazeCtx.fill();
        }

        async loadRecordings() {
            if (this.wsClient && this.wsClient.isConnected) {
                this.wsClient.emitToModule('gazepoint', 'get_recordings', {});
            }
        }

        displayRecordings(recordings) {
            const container = document.getElementById('gaze_recordingsList');
            if (!container) return;

            if (recordings.length === 0) {
                container.innerHTML = `
                    <div class="gaze_no-recordings">
                        <p>Aucun enregistrement disponible</p>
                    </div>
                `;
                return;
            }

            const html = recordings.map(recording => `
                <div class="gaze_recording-item">
                    <div class="gaze_recording-info">
                        <div class="gaze_recording-name">${recording.filename}</div>
                        <div class="gaze_recording-meta">
                            ${recording.size} • ${recording.date}
                        </div>
                    </div>
                    <div class="gaze_recording-actions">
                        <button class="gaze_btn gaze_btn-small" onclick="window.gazepointModuleInstance.downloadRecording('${recording.filename}')">
                            <i class="fas fa-download"></i> Télécharger
                        </button>
                        <button class="gaze_btn gaze_btn-small gaze_btn-danger" onclick="window.gazepointModuleInstance.deleteRecording('${recording.filename}')">
                            <i class="fas fa-trash"></i> Supprimer
                        </button>
                    </div>
                </div>
            `).join('');

            container.innerHTML = html;
        }

        downloadRecording(filename) {
            const link = document.createElement('a');
            link.href = `/api/gazepoint/download/${filename}`;
            link.download = filename;
            link.click();
            this.showToast(`Téléchargement de ${filename}`, 'info');
        }

        deleteRecording(filename) {
            if (confirm(`Êtes-vous sûr de vouloir supprimer ${filename} ?`)) {
                if (this.wsClient) {
                    this.wsClient.emitToModule('gazepoint', 'delete_recording', { filename });
                    this.showToast(`${filename} supprimé`, 'info');
                }
            }
        }

        updateUI() {
            // Bouton connexion
            const connectBtn = document.getElementById('gaze_connectBtn');
            if (connectBtn) {
                connectBtn.innerHTML = this.isConnected ?
                    '<i class="fas fa-unlink"></i> Déconnecter' :
                    '<i class="fas fa-link"></i> Connecter';
                connectBtn.className = this.isConnected ?
                    'gaze_btn gaze_btn-danger' :
                    'gaze_btn gaze_btn-primary';
            }

            // Statut de connexion
            const statusDot = document.getElementById('gaze_statusDot');
            const statusText = document.getElementById('gaze_statusText');
            if (statusDot && statusText) {
                statusDot.className = this.isConnected ?
                    'gaze_status-dot gaze_status-connected' :
                    'gaze_status-dot gaze_status-disconnected';
                statusText.textContent = this.isConnected ? 'Connecté' : 'Déconnecté';
            }

            // Bouton tracking
            const trackingBtn = document.getElementById('gaze_trackingBtn');
            if (trackingBtn) {
                trackingBtn.disabled = !this.isConnected;
                trackingBtn.innerHTML = this.isTracking ?
                    '<i class="fas fa-stop"></i> Arrêter' :
                    '<i class="fas fa-play"></i> Démarrer';
                trackingBtn.className = this.isTracking ?
                    'gaze_btn gaze_btn-danger' :
                    'gaze_btn gaze_btn-success';
            }

            // Bouton enregistrement
            const recordBtn = document.getElementById('gaze_recordBtn');
            if (recordBtn) {
                recordBtn.disabled = !this.isTracking;
                recordBtn.innerHTML = this.isRecording ?
                    '<i class="fas fa-stop-circle"></i> Arrêter' :
                    '<i class="fas fa-circle"></i> Enregistrer';
                recordBtn.className = this.isRecording ?
                    'gaze_btn gaze_btn-danger' :
                    'gaze_btn gaze_btn-primary';
            }

            // Bouton calibration
            const calibrateBtn = document.getElementById('gaze_calibrateBtn');
            if (calibrateBtn) {
                calibrateBtn.disabled = !this.isConnected || this.isCalibrating;
            }

            // Indicateur d'enregistrement
            const recordingIndicator = document.getElementById('gaze_recordingIndicator');
            if (recordingIndicator) {
                recordingIndicator.style.display = this.isRecording ? 'flex' : 'none';
            }
        }

        showToast(message, type = 'info') {
            // Utiliser le système de toast du module Neurosity s'il existe
            if (window.neurosityModuleInstance && typeof window.neurosityModuleInstance.showToast === 'function') {
                window.neurosityModuleInstance.showToast(message, type);
                return;
            }

            // Sinon, créer notre propre toast
            const container = document.getElementById('gazeToastContainer') || this.createToastContainer();

            const toast = document.createElement('div');
            toast.className = `gaze_toast gaze_toast-${type}`;
            toast.textContent = message;

            container.appendChild(toast);

            setTimeout(() => {
                toast.style.opacity = '0';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }

        createToastContainer() {
            const container = document.createElement('div');
            container.id = 'gazeToastContainer';
            container.className = 'gaze_toast-container';
            document.body.appendChild(container);
            return container;
        }

        cleanup() {
            console.log('Nettoyage du module Gazepoint...');

            // Arrêter l'enregistrement si actif
            if (this.isRecording) {
                this.stopRecording();
            }

            // Arrêter le tracking
            if (this.isTracking) {
                this.stopTracking();
            }

            // Se déconnecter
            if (this.isConnected) {
                this.disconnect();
            }

            console.log('Module Gazepoint nettoyé');
        }
    }

    // Exposer la classe
    window.GazepointModuleClass = GazepointModule;

    // Créer l'instance
    window.initGazepointModule = function() {
        console.log('initGazepointModule appelée');
        if (!window.gazepointModuleInstance) {
            window.gazepointModuleInstance = new GazepointModule();
        }
        return window.gazepointModuleInstance;
    };

})();