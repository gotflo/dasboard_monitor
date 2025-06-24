/**
 * Module Capture de Pensée - Version corrigée avec gestion robuste du template
 * Tous les éléments DOM utilisent le préfixe thought_ pour éviter les conflits
 */

class ThoughtCaptureModule {
    constructor() {
        this.thought_mediaRecorder = null;
        this.thought_audioChunks = [];
        this.thought_isRecording = false;
        this.thought_isPaused = false;
        this.thought_recordingStartTime = null;
        this.thought_timerInterval = null;
        this.thought_audioContext = null;
        this.thought_analyser = null;
        this.thought_recordings = [];
        this.audioPermissionsChecked = false;
        this.isInitialized = false;

        // Stocker le template HTML comme string pour éviter les problèmes de DOM
        this.recordingItemTemplateHTML = `
            <div class="thought_recording-item" data-id="">
                <div class="thought_recording-info">
                    <div class="thought_recording-icon">
                        <i class="fas fa-file-audio"></i>
                    </div>
                    <div class="thought_recording-details">
                        <h4 class="thought_recording-name"></h4>
                        <div class="thought_recording-meta">
                            <span class="thought_recording-date"></span>
                            <span class="thought_recording-duration"></span>
                            <span class="thought_recording-size"></span>
                        </div>
                    </div>
                </div>
                
                <div class="thought_recording-actions">
                    <button class="thought_btn-action thought_btn-play" title="Écouter">
                        <i class="fas fa-play"></i>
                    </button>
                    <button class="thought_btn-action thought_btn-download" title="Télécharger">
                        <i class="fas fa-download"></i>
                    </button>
                    <button class="thought_btn-action thought_btn-delete" title="Supprimer">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
                
                <!-- Player audio caché -->
                <div class="thought_audio-player-container" style="display: none;">
                    <audio class="thought_audio-player" controls></audio>
                </div>
            </div>
        `;

        this.init();
    }

    async init() {
        console.log('Initialisation du module Capture de Pensée (Simple)');

        try {
            // Ne pas réinitialiser le timer si un enregistrement est en cours
            if (!this.thought_isRecording) {
                // Nettoyer tout timer existant
                if (this.thought_timerInterval) {
                    clearInterval(this.thought_timerInterval);
                    this.thought_timerInterval = null;
                }

                // Réinitialiser l'affichage du timer seulement si pas d'enregistrement
                const timerElement = document.getElementById('thought_recordingTimer');
                if (timerElement) {
                    timerElement.textContent = '00:00';
                }
            } else {
                console.log('Enregistrement en cours, conservation du timer');
                // Redémarrer le timer avec le temps sauvegardé
                this.startTimer();

                // Restaurer la visualisation si nécessaire
                if (this.thought_mediaRecorder && this.thought_mediaRecorder.stream) {
                    this.startAudioVisualization(this.thought_mediaRecorder.stream);
                }
            }

            // Charger la liste des enregistrements
            await this.loadRecordings();

            // Configuration des boutons
            this.setupEventListeners();

            // Vérifier les permissions audio seulement si pas déjà fait
            if (!this.audioPermissionsChecked) {
                await this.checkAudioPermissions();
                this.audioPermissionsChecked = true;
            }

            // Initialiser le visualiseur
            this.initAudioVisualizer();

            // Restaurer l'état de l'UI si enregistrement en cours
            if (this.thought_isRecording) {
                this.updateRecordingUI(true);
            }

            console.log('Module initialisé');
        } catch (error) {
            console.error('Erreur:', error);
        }
    }

    async loadRecordings() {
        try {
            const response = await fetch('/api/thought-capture/list-audios');
            const data = await response.json();

            this.thought_recordings = data.files || [];
            console.log(`${this.thought_recordings.length} fichiers trouvés`);

            this.renderRecordings();
        } catch (error) {
            console.error('Erreur chargement:', error);
            this.thought_recordings = [];
            this.renderRecordings();
        }
    }

    setupEventListeners() {
        // Éviter de dupliquer les event listeners
        if (this.isInitialized) {
            console.log('Event listeners déjà configurés');
            return;
        }

        const btnRecord = document.getElementById('thought_btnRecord');
        const btnStop = document.getElementById('thought_btnStop');
        const btnPause = document.getElementById('thought_btnPause');

        if (btnRecord) {
            btnRecord.removeEventListener('click', this.toggleRecordingHandler);
            this.toggleRecordingHandler = () => this.toggleRecording();
            btnRecord.addEventListener('click', this.toggleRecordingHandler);
        }

        if (btnStop) {
            btnStop.removeEventListener('click', this.stopRecordingHandler);
            this.stopRecordingHandler = () => this.stopRecording();
            btnStop.addEventListener('click', this.stopRecordingHandler);
        }

        if (btnPause) {
            btnPause.removeEventListener('click', this.togglePauseHandler);
            this.togglePauseHandler = () => this.togglePause();
            btnPause.addEventListener('click', this.togglePauseHandler);
        }

        this.isInitialized = true;
    }

    async checkAudioPermissions() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            stream.getTracks().forEach(track => track.stop());
            return true;
        } catch (error) {
            console.error('Erreur permissions audio:', error);
            this.showNotification('Veuillez autoriser l\'accès au microphone', 'error');
            return false;
        }
    }

    initAudioVisualizer() {
        const canvas = document.getElementById('thought_audioCanvas');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        ctx.strokeStyle = '#feca57';
        ctx.lineWidth = 2;
    }

    async toggleRecording() {
        if (!this.thought_isRecording) {
            await this.startRecording();
        } else {
            this.stopRecording();
        }
    }

    async startRecording() {
        try {
            const hasPermission = await this.checkAudioPermissions();
            if (!hasPermission) return;

            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

            this.thought_mediaRecorder = new MediaRecorder(stream);
            this.thought_audioChunks = [];

            this.thought_mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.thought_audioChunks.push(event.data);
                }
            };

            this.thought_mediaRecorder.onstop = async () => {
                // S'assurer que le timer est arrêté avant la sauvegarde
                this.stopTimer();
                await this.saveRecording();
            };

            this.thought_mediaRecorder.start();
            this.thought_isRecording = true;
            this.thought_recordingStartTime = Date.now();

            this.updateRecordingUI(true);
            this.startTimer();
            this.startAudioVisualization(stream);

            console.log('Enregistrement démarré');
        } catch (error) {
            console.error('Erreur:', error);
            this.showNotification('Impossible de démarrer l\'enregistrement', 'error');
        }
    }

    stopRecording() {
        if (this.thought_mediaRecorder && this.thought_isRecording) {
            this.thought_mediaRecorder.stop();
            this.thought_isRecording = false;
            this.thought_isPaused = false;
            this.thought_recordingStartTime = null; // Réinitialiser le temps de départ

            if (this.thought_mediaRecorder.stream) {
                this.thought_mediaRecorder.stream.getTracks().forEach(track => track.stop());
            }

            // Arrêter le timer immédiatement
            this.stopTimer();

            // Mettre à jour l'UI
            this.updateRecordingUI(false);

            // Arrêter la visualisation
            this.stopAudioVisualization();

            console.log('Enregistrement arrêté');
        }
    }

    togglePause() {
        if (!this.thought_isRecording) return;

        const btnPause = document.getElementById('thought_btnPause');
        const status = document.getElementById('thought_recordingStatus');

        if (!this.thought_isPaused) {
            this.thought_mediaRecorder.pause();
            this.thought_isPaused = true;
            btnPause.classList.add('thought_paused');
            status.textContent = 'En pause';
            status.classList.add('thought_paused');
        } else {
            this.thought_mediaRecorder.resume();
            this.thought_isPaused = false;
            btnPause.classList.remove('thought_paused');
            status.textContent = 'Enregistrement...';
            status.classList.remove('thought_paused');
        }
    }

    updateRecordingUI(isRecording) {
        const btnRecord = document.getElementById('thought_btnRecord');
        const btnStop = document.getElementById('thought_btnStop');
        const btnPause = document.getElementById('thought_btnPause');
        const status = document.getElementById('thought_recordingStatus');
        const visualizerOverlay = document.querySelector('.thought_visualizer-overlay');
        const timerElement = document.getElementById('thought_recordingTimer');

        if (isRecording) {
            btnRecord?.classList.add('thought_recording');
            if (btnRecord?.querySelector('span')) {
                btnRecord.querySelector('span').textContent = 'Enregistrement...';
            }
            if (btnStop) btnStop.disabled = false;
            if (btnPause) btnPause.disabled = false;
            if (status) {
                status.textContent = 'Enregistrement...';
                status.classList.add('thought_recording');
            }
            visualizerOverlay?.classList.add('thought_recording');
        } else {
            btnRecord?.classList.remove('thought_recording');
            if (btnRecord?.querySelector('span')) {
                btnRecord.querySelector('span').textContent = 'Enregistrer';
            }
            if (btnStop) btnStop.disabled = true;
            if (btnPause) btnPause.disabled = true;
            if (status) {
                status.textContent = 'Prêt';
                status.classList.remove('thought_recording', 'thought_paused');
            }
            visualizerOverlay?.classList.remove('thought_recording');

            // S'assurer que le timer est réinitialisé
            if (timerElement) {
                timerElement.textContent = '00:00';
            }
        }
    }

    startTimer() {
        // S'assurer qu'aucun timer n'est déjà en cours
        if (this.thought_timerInterval) {
            clearInterval(this.thought_timerInterval);
            this.thought_timerInterval = null;
        }

        const timerElement = document.getElementById('thought_recordingTimer');
        if (!timerElement) return;

        // Utiliser le temps de départ sauvegardé
        const startTime = this.thought_recordingStartTime || Date.now();

        this.thought_timerInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            const mins = Math.floor(elapsed / 60);
            const secs = elapsed % 60;

            const currentTimerElement = document.getElementById('thought_recordingTimer');
            if (currentTimerElement) {
                currentTimerElement.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
            } else {
                // Si l'élément n'existe plus, arrêter le timer
                clearInterval(this.thought_timerInterval);
                this.thought_timerInterval = null;
            }
        }, 1000);

        // Afficher immédiatement le temps écoulé si on restaure
        if (this.thought_recordingStartTime) {
            const elapsed = Math.floor((Date.now() - this.thought_recordingStartTime) / 1000);
            const mins = Math.floor(elapsed / 60);
            const secs = elapsed % 60;
            timerElement.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }
    }

    stopTimer() {
        if (this.thought_timerInterval) {
            clearInterval(this.thought_timerInterval);
            this.thought_timerInterval = null;
        }

        // S'assurer que le timer est bien réinitialisé même si l'élément n'est pas trouvé immédiatement
        const timerElement = document.getElementById('thought_recordingTimer');
        if (timerElement) {
            timerElement.textContent = '00:00';
        }
    }

    startAudioVisualization(stream) {
        try {
            this.thought_audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = this.thought_audioContext.createMediaStreamSource(stream);
            this.thought_analyser = this.thought_audioContext.createAnalyser();
            this.thought_analyser.fftSize = 256;

            source.connect(this.thought_analyser);

            const canvas = document.getElementById('thought_audioCanvas');
            if (!canvas) return;

            const ctx = canvas.getContext('2d');
            const bufferLength = this.thought_analyser.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);

            const draw = () => {
                if (!this.thought_isRecording) return;

                requestAnimationFrame(draw);

                this.thought_analyser.getByteFrequencyData(dataArray);

                ctx.fillStyle = '#f8fafc';
                ctx.fillRect(0, 0, canvas.width, canvas.height);

                const barWidth = (canvas.width / bufferLength) * 2.5;
                let barHeight;
                let x = 0;

                for (let i = 0; i < bufferLength; i++) {
                    barHeight = (dataArray[i] / 255) * canvas.height * 0.8;

                    const gradient = ctx.createLinearGradient(0, canvas.height, 0, canvas.height - barHeight);
                    gradient.addColorStop(0, '#feca57');
                    gradient.addColorStop(1, '#f59e0b');

                    ctx.fillStyle = gradient;
                    ctx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);

                    x += barWidth + 1;
                }

                // Mettre à jour le niveau audio
                const average = dataArray.reduce((a, b) => a + b) / bufferLength;
                const level = (average / 255) * 100;
                const audioLevel = document.getElementById('thought_audioLevel');
                if (audioLevel) {
                    audioLevel.style.width = `${level}%`;
                }
            };

            draw();
        } catch (error) {
            console.error('Erreur visualisation:', error);
        }
    }

    stopAudioVisualization() {
        if (this.thought_audioContext) {
            this.thought_audioContext.close();
            this.thought_audioContext = null;
        }

        const canvas = document.getElementById('thought_audioCanvas');
        if (canvas) {
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#f8fafc';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }

        const audioLevel = document.getElementById('thought_audioLevel');
        if (audioLevel) {
            audioLevel.style.width = '0%';
        }
    }

    async saveRecording() {
        const blob = new Blob(this.thought_audioChunks, { type: 'audio/webm' });
        const duration = Math.floor((Date.now() - this.thought_recordingStartTime) / 1000);

        // Créer un FormData pour envoyer le fichier
        const formData = new FormData();
        formData.append('audio', blob, 'recording.webm');
        formData.append('duration', duration);

        try {
            this.showNotification('Sauvegarde en cours...', 'info');

            const response = await fetch('/api/thought-capture/save-audio', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('Erreur serveur');
            }

            const result = await response.json();
            console.log('Fichier sauvegardé:', result.filename);

            // Recharger la liste
            await this.loadRecordings();

            this.showNotification('Enregistrement sauvegardé !', 'success');
        } catch (error) {
            console.error('Erreur:', error);
            this.showNotification('Erreur lors de la sauvegarde', 'error');
        }
    }

    createRecordingElement(recording) {
        // Créer un élément DOM à partir du template HTML
        const wrapper = document.createElement('div');
        wrapper.innerHTML = this.recordingItemTemplateHTML;
        const element = wrapper.firstElementChild;

        // Formater la date depuis le timestamp
        const year = recording.timestamp.substring(0, 4);
        const month = recording.timestamp.substring(4, 6);
        const day = recording.timestamp.substring(6, 8);
        const hour = recording.timestamp.substring(9, 11);
        const min = recording.timestamp.substring(11, 13);
        const sec = recording.timestamp.substring(13, 15);
        const dateStr = `${day}/${month}/${year} ${hour}:${min}:${sec}`;

        element.dataset.filename = recording.filename;
        element.querySelector('.thought_recording-name').textContent = `Pensée ${dateStr}`;
        element.querySelector('.thought_recording-date').textContent = dateStr;
        element.querySelector('.thought_recording-duration').textContent = '-';
        element.querySelector('.thought_recording-size').textContent = this.formatSize(recording.size);

        const playBtn = element.querySelector('.thought_btn-play');
        const downloadBtn = element.querySelector('.thought_btn-download');
        const deleteBtn = element.querySelector('.thought_btn-delete');
        const audioPlayer = element.querySelector('.thought_audio-player');
        const playerContainer = element.querySelector('.thought_audio-player-container');

        // Utiliser directement l'URL du fichier
        const audioUrl = recording.url;

        playBtn.addEventListener('click', () => {
            if (playerContainer.style.display === 'none') {
                playerContainer.style.display = 'block';
                audioPlayer.src = audioUrl;
                audioPlayer.play();
                playBtn.innerHTML = '<i class="fas fa-pause"></i>';
            } else {
                if (audioPlayer.paused) {
                    audioPlayer.play();
                    playBtn.innerHTML = '<i class="fas fa-pause"></i>';
                } else {
                    audioPlayer.pause();
                    playBtn.innerHTML = '<i class="fas fa-play"></i>';
                }
            }
        });

        audioPlayer.addEventListener('ended', () => {
            playBtn.innerHTML = '<i class="fas fa-play"></i>';
        });

        downloadBtn.addEventListener('click', () => {
            const a = document.createElement('a');
            a.href = audioUrl;
            a.download = recording.filename;
            a.click();
            this.showNotification('Téléchargement démarré', 'success');
        });

        deleteBtn.addEventListener('click', () => {
            this.deleteRecording(recording.filename);
        });

        return element;
    }

    renderRecordings() {
        const listContainer = document.getElementById('thought_recordingsList');
        const countElement = document.querySelector('.thought_recordings-count');

        if (!listContainer || !countElement) return;

        countElement.textContent = `${this.thought_recordings.length} fichiers`;

        if (this.thought_recordings.length === 0) {
            listContainer.innerHTML = `
                <div class="thought_empty-state">
                    <i class="fas fa-microphone-slash"></i>
                    <p>Aucun enregistrement</p>
                    <span>Commencez par enregistrer votre première pensée</span>
                </div>
            `;
            return;
        }

        listContainer.innerHTML = '';

        this.thought_recordings.forEach(recording => {
            const element = this.createRecordingElement(recording);
            listContainer.appendChild(element);
        });
    }

    formatSize(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }

    async deleteRecording(filename) {
        if (confirm('Êtes-vous sûr de vouloir supprimer cet enregistrement ?')) {
            try {
                const response = await fetch(`/api/thought-capture/delete-audio/${filename}`, {
                    method: 'DELETE'
                });

                if (!response.ok) {
                    throw new Error('Erreur serveur');
                }

                // Recharger la liste
                await this.loadRecordings();

                this.showNotification('Enregistrement supprimé', 'info');
            } catch (error) {
                console.error('Erreur:', error);
                this.showNotification('Erreur lors de la suppression', 'error');
            }
        }
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = 'thought_capture-notification';
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 1rem 1.5rem;
            background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
            color: white;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 10000;
            animation: thought_slideIn 0.3s ease;
            max-width: 350px;
        `;
        notification.textContent = message;

        document.body.appendChild(notification);

        setTimeout(() => {
            notification.style.animation = 'thought_slideOut 0.3s ease';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 300);
        }, 3000);
    }

    cleanup() {
        console.log('Nettoyage du module...');

        // Arrêter l'enregistrement si en cours
        if (this.thought_isRecording) {
            this.stopRecording();
        }

        // S'assurer que le timer est bien arrêté
        if (this.thought_timerInterval) {
            clearInterval(this.thought_timerInterval);
            this.thought_timerInterval = null;
        }

        // Fermer le contexte audio
        if (this.thought_audioContext) {
            this.thought_audioContext.close();
            this.thought_audioContext = null;
        }

        // Supprimer les notifications
        document.querySelectorAll('.thought_capture-notification').forEach(notif => {
            notif.remove();
        });

        console.log('Module nettoyé');
    }
}

// Protection contre les redéclarations
if (!window.thoughtCaptureModuleInstance) {
    window.thoughtCaptureModuleInstance = null;
}

// Point d'entrée pour le dashboard
window.initThoughtCaptureModule = function() {
    if (!window.thoughtCaptureModuleInstance) {
        window.thoughtCaptureModuleInstance = new ThoughtCaptureModule();
    }
    return window.thoughtCaptureModuleInstance;
};