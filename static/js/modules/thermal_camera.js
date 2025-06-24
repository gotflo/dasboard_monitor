/**
 * Module Caméra Thermique - BioMedical Hub
 */

class ThermalCameraModule {
    constructor() {
        this.isActive = false;
        this.isRecording = false;
        this.canvas = null;
        this.ctx = null;
        this.chart = null;
        this.wsClient = null;
        this.thermal_recordingTimer = null;
        this.thermal_recordingStartTime = null;
        this.thermal_recordingLineCount = 0;

        // Configuration du graphique
        this.chartConfig = {
            updateInterval: 1000,
            animationDuration: 300
        };

        // Points de mesure du visage
        this.facePoints = [
            'Nez', 'Bouche', 'Œil_Gauche', 'Œil_Droit',
            'Joue_Gauche', 'Joue_Droite', 'Front', 'Menton'
        ];

        // Données du graphique
        this.chartData = {
            labels: this.facePoints,
            datasets: []
        };

        this.init();
    }

    init() {
        console.log('Initialisation du module Caméra Thermique');

        // Récupération des éléments DOM
        this.canvas = document.getElementById('thermal-canvas');
        this.ctx = this.canvas ? this.canvas.getContext('2d') : null;

        // Configuration du canvas
        if (this.canvas) {
            this.canvas.width = 640;
            this.canvas.height = 480;
        }

        // Initialisation du graphique
        this.initChart();

        // Configuration des événements
        this.setupEventListeners();

        // Connexion WebSocket
        this.connectWebSocket();

        // Chargement initial des enregistrements
        this.loadRecordings();

        // S'assurer que l'UI est dans le bon état initial après un court délai
        setTimeout(() => {
            this.updateUI();
            console.log('UI mise à jour - État initial: isActive =', this.isActive);
        }, 100);
    }

    initChart() {
        const chartCanvas = document.getElementById('thermal-chart');
        if (!chartCanvas) return;

        // Détruire le graphique existant s'il existe
        if (this.chart) {
            this.chart.destroy();
        }

        // Couleurs pour chaque point de mesure
        const colors = [
            '#ef4444', '#f59e0b', '#10b981', '#3b82f6',
            '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'
        ];

        // Initialisation pour un seul dataset (dernières valeurs)
        this.chartData = {
            labels: this.facePoints,
            datasets: [{
                label: 'Température actuelle',
                data: new Array(this.facePoints.length).fill(0),
                backgroundColor: colors.map(color => color + 'CC'), // Couleurs avec transparence
                borderColor: colors,
                borderWidth: 2,
                borderRadius: 8, // Coins arrondis pour les barres
                barThickness: 'flex',
                hoverBackgroundColor: colors, // Couleur pleine au survol
                hoverBorderWidth: 3
            }]
        };

        // Configuration Chart.js pour Bar Chart
        this.chart = new Chart(chartCanvas, {
            type: 'bar',
            data: this.chartData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: {
                        display: false // Pas besoin de légende pour un seul dataset
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        cornerRadius: 8,
                        titleFont: {
                            size: 14,
                            family: 'Inter'
                        },
                        bodyFont: {
                            size: 13,
                            family: 'Inter'
                        },
                        callbacks: {
                            label: function(context) {
                                return 'Température: ' + context.parsed.y.toFixed(1) + '°C';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        display: true,
                        grid: {
                            display: false
                        },
                        ticks: {
                            font: {
                                size: 11,
                                family: 'Inter',
                                weight: 500
                            }
                        }
                    },
                    y: {
                        display: true,
                        beginAtZero: false,
                        title: {
                            display: true,
                            text: 'Température (°C)',
                            font: {
                                size: 12,
                                family: 'Inter'
                            }
                        },
                        min: 30,  // Valeur minimale fixe
                        max: 40,  // Valeur maximale fixe
                        ticks: {
                            stepSize: 1, // Intervalles de 1°C
                            callback: function(value) {
                                return value + '°C';
                            },
                            font: {
                                size: 11,
                                family: 'Inter'
                            }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    }
                },
                animation: {
                    duration: this.chartConfig.animationDuration || 300
                }
            }
        });
    }

    setupEventListeners() {
        // Bouton de contrôle caméra
        const toggleBtn = document.getElementById('thermal-toggle-btn');
        if (toggleBtn) {
            // Retirer tout listener existant pour éviter les doublons
            const newToggleBtn = toggleBtn.cloneNode(true);
            toggleBtn.parentNode.replaceChild(newToggleBtn, toggleBtn);

            newToggleBtn.addEventListener('click', () => {
                console.log('Bouton caméra cliqué');
                this.toggleCamera();
            });
        }

        // Bouton d'enregistrement
        const recordingBtn = document.getElementById('recording-toggle-btn');
        if (recordingBtn) {
            // Retirer tout listener existant pour éviter les doublons
            const newRecordingBtn = recordingBtn.cloneNode(true);
            recordingBtn.parentNode.replaceChild(newRecordingBtn, recordingBtn);

            newRecordingBtn.addEventListener('click', () => {
                console.log('Bouton enregistrement cliqué');
                this.toggleRecording();
            });
        }

        // Bouton actualiser les enregistrements
        const refreshBtn = document.getElementById('refresh-recordings-btn');
        if (refreshBtn) {
            // Retirer tout listener existant pour éviter les doublons
            const newRefreshBtn = refreshBtn.cloneNode(true);
            refreshBtn.parentNode.replaceChild(newRefreshBtn, refreshBtn);

            newRefreshBtn.addEventListener('click', () => {
                console.log('Bouton actualiser cliqué');
                this.loadRecordings();
            });
        }
    }

    connectWebSocket() {
        if (typeof window.dashboard !== 'undefined' && window.dashboard.wsClient) {
            this.wsClient = window.dashboard.wsClient;

            // Écoute des événements WebSocket
            this.wsClient.on('thermal_frame', (data) => this.handleThermalFrame(data));
            this.wsClient.on('thermal_temperature_data', (data) => this.updateTemperatureData(data));
            this.wsClient.on('thermal_recording_started', (data) => this.handleRecordingStarted(data));
            this.wsClient.on('thermal_recording_stopped', (data) => this.handleRecordingStopped(data));
            this.wsClient.on('thermal_recordings_list', (data) => this.displayRecordings(data));

            // Écouter les confirmations de changement d'état
            this.wsClient.on('capture_started', (data) => {
                console.log('Capture confirmée par le serveur');
                this.isActive = true;
                this.updateUI();
            });

            this.wsClient.on('capture_stopped', (data) => {
                console.log('Arrêt confirmé par le serveur');
                this.isActive = false;
                this.updateUI();
            });

            console.log('WebSocket connecté pour le module thermique');
        } else {
            console.log('Mode autonome - WebSocket non disponible');
        }
    }

    toggleCamera() {
        console.log('Toggle camera - État actuel:', this.isActive);
        if (this.isActive) {
            this.stopCamera();
        } else {
            this.startCamera();
        }
    }

    startCamera() {
        console.log('Démarrage de la caméra thermique...');

        if (this.wsClient) {
            this.wsClient.emit('thermal_camera_start_capture', {});
        }

        this.isActive = true;
        this.updateUI();
        this.showToast('Caméra thermique démarrée', 'success');
        console.log('État isActive:', this.isActive);
    }

    stopCamera() {
        console.log('Arrêt de la caméra thermique...');

        if (this.wsClient) {
            this.wsClient.emit('thermal_camera_stop_capture', {});
        }

        this.isActive = false;

        // Arrêter l'enregistrement si actif
        if (this.isRecording) {
            this.stopRecording();
        }

        // Clear canvas
        if (this.ctx) {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        }

        // Arrêter le chart s'il est en animation
        if (this.chart) {
            this.chart.stop();
            // Réinitialiser les données
            this.chartData.datasets[0].data = new Array(this.facePoints.length).fill(0);
            this.chart.update('none');
        }

        // Réinitialiser les statistiques
        const tempAvg = document.querySelector('.temp-avg');
        const tempMax = document.querySelector('.temp-max');
        const tempMin = document.querySelector('.temp-min');

        if (tempAvg) tempAvg.textContent = 'Moy: --°C';
        if (tempMax) tempMax.textContent = 'Max: --°C';
        if (tempMin) tempMin.textContent = 'Min: --°C';

        this.updateUI();
        this.showToast('Caméra thermique arrêtée', 'info');
        console.log('État isActive:', this.isActive);
    }

    toggleRecording() {
        if (this.isRecording) {
            this.stopRecording();
        } else {
            this.startRecording();
        }
    }

    startRecording() {
        if (!this.isActive) {
            this.showToast('Veuillez d\'abord démarrer la caméra', 'error');
            return;
        }

        if (this.wsClient) {
            this.wsClient.emit('thermal_camera_start_recording', {});
        }

        this.isRecording = true;
        this.thermal_recordingStartTime = Date.now();
        this.thermal_recordingLineCount = 0;

        // Démarrer le timer
        this.startRecordingTimer();

        this.updateUI();
    }

    stopRecording() {
        if (this.wsClient) {
            this.wsClient.emit('thermal_camera_stop_recording', {});
        }

        this.isRecording = false;

        // Arrêter le timer
        if (this.thermal_recordingTimer) {
            clearInterval(this.thermal_recordingTimer);
            this.thermal_recordingTimer = null;
        }

        // Mettre à jour l'interface immédiatement
        this.updateUI();

        // Forcer le rechargement de la liste après un délai
        setTimeout(() => {
            console.log('Actualisation de la liste après arrêt enregistrement');
            this.loadRecordings();
        }, 1500);
    }

    startRecordingTimer() {
        this.thermal_recordingTimer = setInterval(() => {
            const elapsed = Date.now() - this.thermal_recordingStartTime;
            const hours = Math.floor(elapsed / 3600000);
            const minutes = Math.floor((elapsed % 3600000) / 60000);
            const seconds = Math.floor((elapsed % 60000) / 1000);

            const timeStr = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;

            const timeElement = document.querySelector('.recording-time');
            if (timeElement) {
                timeElement.textContent = timeStr;
            }
        }, 1000);
    }

    handleThermalFrame(data) {
        if (!this.ctx || !data.image) return;

        // Afficher l'image sur le canvas
        const img = new Image();
        img.onload = () => {
            this.ctx.drawImage(img, 0, 0, this.canvas.width, this.canvas.height);
        };
        img.src = 'data:image/jpeg;base64,' + data.image;
    }

    updateTemperatureData(data) {
        if (!this.chart) return;

        // Mettre à jour les données des barres
        const temperatures = [];
        this.facePoints.forEach((point) => {
            const temp = data.temperatures?.[point] || 0;
            temperatures.push(temp);
        });

        // Mettre à jour le dataset
        this.chartData.datasets[0].data = temperatures;

        // Mettre à jour le graphique avec animation fluide
        this.chart.update('active');

        // Mettre à jour les statistiques
        this.updateTemperatureStats(data.temperatures);

        // Mettre à jour le compteur de lignes si enregistrement
        if (this.isRecording && data.recording_lines) {
            this.thermal_recordingLineCount = data.recording_lines;
            const sizeElement = document.querySelector('.thermal_recording-size');
            if (sizeElement) {
                sizeElement.textContent = `${this.thermal_recordingLineCount} lignes`;
            }
        }
    }

    updateTemperatureStats(temperatures) {
        if (!temperatures) return;

        const temps = Object.values(temperatures).filter(t => t != null);
        if (temps.length === 0) return;

        const avg = temps.reduce((a, b) => a + b, 0) / temps.length;
        const max = Math.max(...temps);
        const min = Math.min(...temps);

        const tempAvg = document.querySelector('.temp-avg');
        const tempMax = document.querySelector('.temp-max');
        const tempMin = document.querySelector('.temp-min');

        if (tempAvg) tempAvg.textContent = `Moy: ${avg.toFixed(1)}°C`;
        if (tempMax) tempMax.textContent = `Max: ${max.toFixed(1)}°C`;
        if (tempMin) tempMin.textContent = `Min: ${min.toFixed(1)}°C`;
    }

    handleRecordingStarted(data) {
        this.showToast(`Enregistrement démarré: ${data.filename}`, 'success');
    }

    handleRecordingStopped(data) {
        this.showToast(`Enregistrement terminé: ${data.lines} lignes sauvegardées`, 'info');

        // Forcer le rechargement de la liste après un court délai
        setTimeout(() => {
            console.log('Rechargement de la liste des enregistrements...');
            this.loadRecordings();
        }, 1000); // Délai d'1 seconde pour s'assurer que le fichier est bien écrit
    }

    loadRecordings() {
        console.log('Chargement de la liste des enregistrements...');

        if (this.wsClient && this.wsClient.isConnected) {
            this.wsClient.emit('thermal_camera_get_recordings', {
                timestamp: new Date().toISOString()
            });
        } else {
            console.warn('WebSocket non connecté, impossible de charger les enregistrements');
        }

        // Animation du bouton refresh
        const refreshBtn = document.getElementById('refresh-recordings-btn');
        if (refreshBtn) {
            const icon = refreshBtn.querySelector('.refresh-icon');
            if (icon) {
                icon.style.animation = 'rotate 1s linear';
                setTimeout(() => {
                    icon.style.animation = '';
                }, 1000);
            }
        }
    }

    displayRecordings(data) {
        console.log('Affichage des enregistrements:', data);

        const listContainer = document.getElementById('recordings-list');
        if (!listContainer) {
            console.error('Container recordings-list non trouvé');
            return;
        }

        if (!data.recordings || data.recordings.length === 0) {
            listContainer.innerHTML = `
                <div class="no-recordings">
                    <p>Aucun enregistrement disponible</p>
                    <p class="text-muted">Les fichiers CSV apparaîtront ici après enregistrement</p>
                </div>
            `;
            return;
        }

        console.log(`${data.recordings.length} enregistrements trouvés`);

        const recordingsHTML = data.recordings.map(recording => `
            <div class="recording-item">
                <div class="recording-info-item">
                    <div class="recording-name">${recording.filename}</div>
                    <div class="recording-meta">
                        ${recording.size} • ${recording.date}
                    </div>
                </div>
                <div class="recording-actions">
                    <button class="thermal-btn small" onclick="window.thermalModuleInstance.downloadRecording('${recording.filename}')">
                        Télécharger
                    </button>
                    <button class="thermal-btn small secondary" onclick="window.thermalModuleInstance.deleteRecording('${recording.filename}')">
                        Supprimer
                    </button>
                </div>
            </div>
        `).join('');

        listContainer.innerHTML = recordingsHTML;
        console.log('Liste des enregistrements mise à jour');
    }

    downloadRecording(filename) {
        if (this.wsClient) {
            this.wsClient.emit('thermal_camera_download_recording', { filename });
        }

        // Créer un lien de téléchargement
        const link = document.createElement('a');
        link.href = `/api/thermal/download/${filename}`;
        link.download = filename;
        link.click();

        this.showToast(`Téléchargement de ${filename}`, 'info');
    }

    deleteRecording(filename) {
        if (confirm(`Êtes-vous sûr de vouloir supprimer ${filename} ?`)) {
            if (this.wsClient) {
                this.wsClient.emit('thermal_camera_delete_recording', { filename });
            }

            this.showToast(`${filename} supprimé`, 'info');
            // Recharger la liste après un court délai
            setTimeout(() => {
                console.log('Rechargement après suppression');
                this.loadRecordings();
            }, 800);
        }
    }

    updateUI() {
        console.log('Mise à jour UI - isActive:', this.isActive, 'isRecording:', this.isRecording);

        // Bouton caméra
        const toggleBtn = document.getElementById('thermal-toggle-btn');
        if (toggleBtn) {
            toggleBtn.classList.toggle('active', this.isActive);
            const btnText = toggleBtn.querySelector('.btn-text');
            const startIcon = toggleBtn.querySelector('.start-icon');
            const stopIcon = toggleBtn.querySelector('.stop-icon');

            if (btnText) {
                btnText.textContent = this.isActive ? 'Arrêter la caméra' : 'Démarrer la caméra';
            }
            if (startIcon) {
                startIcon.style.display = this.isActive ? 'none' : 'inline';
            }
            if (stopIcon) {
                stopIcon.style.display = this.isActive ? 'inline' : 'none';
            }
        }

        // Statut
        const statusIndicator = document.getElementById('thermal-status');
        const statusText = document.querySelector('.status-text');
        if (statusIndicator) {
            if (this.isActive) {
                statusIndicator.classList.add('active');
            } else {
                statusIndicator.classList.remove('active');
            }
        }
        if (statusText) {
            statusText.textContent = this.isActive ? 'En ligne' : 'Hors ligne';
        }

        // Overlay - IMPORTANT : retirer 'hidden' quand actif, l'ajouter quand inactif
        const overlay = document.getElementById('thermal-overlay');
        if (overlay) {
            if (this.isActive) {
                overlay.classList.add('hidden');
                overlay.style.display = 'none'; // Force cache
            } else {
                overlay.classList.remove('hidden');
                overlay.style.display = ''; // Restaure l'affichage par défaut
            }
            console.log('Overlay hidden:', overlay.classList.contains('hidden'));
        }

        // Bouton enregistrement
        const recordingBtn = document.getElementById('recording-toggle-btn');
        if (recordingBtn) {
            recordingBtn.disabled = !this.isActive;
            const btnText = recordingBtn.querySelector('.btn-text');
            const recordingIndicator = recordingBtn.querySelector('.recording-indicator');

            if (btnText) {
                btnText.textContent = this.isRecording ? 'Arrêter l\'enregistrement' : 'Démarrer l\'enregistrement';
            }
            if (recordingIndicator) {
                if (this.isRecording) {
                    recordingIndicator.classList.add('active');
                } else {
                    recordingIndicator.classList.remove('active');
                }
            }
        }

        // Info enregistrement
        const recordingInfo = document.getElementById('recording-info');
        if (recordingInfo) {
            recordingInfo.style.display = this.isRecording ? 'flex' : 'none';
        }
    }

    showToast(message, type = 'info') {
        const container = document.getElementById('thermal-toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `thermal-toast ${type}`;
        toast.textContent = message;

        container.appendChild(toast);

        // Animation de sortie
        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => {
                container.removeChild(toast);
            }, 300);
        }, 3000);
    }

    cleanup() {
        // Arrêter la caméra si active
        if (this.isActive) {
            this.stopCamera();
        }

        // Arrêter le timer
        if (this.thermal_recordingTimer) {
            clearInterval(this.thermal_recordingTimer);
        }

        // Détruire le graphique
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }

        // Nettoyer les événements WebSocket
        if (this.wsClient) {
            this.wsClient.off('thermal_frame');
            this.wsClient.off('thermal_temperature_data');
            this.wsClient.off('thermal_recording_started');
            this.wsClient.off('thermal_recording_stopped');
            this.wsClient.off('thermal_recordings_list');
        }

        console.log('Module Caméra Thermique nettoyé');
    }
}

// Protection contre les redéclarations
if (!window.thermalModuleInstance) {
    window.thermalModuleInstance = null;
}

// Fonction d'initialisation globale
window.initThermalModule = function() {
    console.log('initThermalModule appelée');
    if (!window.thermalModuleInstance) {
        window.thermalModuleInstance = new ThermalCameraModule();

        // Forcer une mise à jour de l'UI après l'initialisation complète
        setTimeout(() => {
            if (window.thermalModuleInstance) {
                window.thermalModuleInstance.updateUI();
                console.log('UI forcée à jour après initialisation');
            }
        }, 200);
    }
    return window.thermalModuleInstance;
};

// Export pour utilisation dans d'autres modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ThermalCameraModule, initThermalModule };
}