/**
 * Module Capture de Pensée - Version simple avec stockage fichiers
 */

class ThoughtCaptureModule {
    constructor() {
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.isPaused = false;
        this.recordingStartTime = null;
        this.timerInterval = null;
        this.audioContext = null;
        this.analyser = null;
        this.recordings = [];

        this.init();
    }

    async init() {
        console.log('Initialisation du module Capture de Pensée (Simple)');

        try {
            // Charger la liste des enregistrements
            await this.loadRecordings();

            // Configuration des boutons
            this.setupEventListeners();

            // Vérifier les permissions audio
            await this.checkAudioPermissions();

            // Initialiser le visualiseur
            this.initAudioVisualizer();

            console.log('Module initialisé');
        } catch (error) {
            console.error('Erreur:', error);
        }
    }

    async loadRecordings() {
        try {
            const response = await fetch('/api/thought-capture/list-audios');
            const data = await response.json();

            this.recordings = data.files || [];
            console.log(`${this.recordings.length} fichiers trouvés`);

            this.renderRecordings();
        } catch (error) {
            console.error('Erreur chargement:', error);
            this.recordings = [];
            this.renderRecordings();
        }
    }

    setupEventListeners() {
        document.getElementById('btnRecord')?.addEventListener('click', () => this.toggleRecording());
        document.getElementById('btnStop')?.addEventListener('click', () => this.stopRecording());
        document.getElementById('btnPause')?.addEventListener('click', () => this.togglePause());
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
        const canvas = document.getElementById('audioCanvas');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        ctx.strokeStyle = '#feca57';
        ctx.lineWidth = 2;
    }

    async toggleRecording() {
        if (!this.isRecording) {
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

            this.mediaRecorder = new MediaRecorder(stream);
            this.audioChunks = [];

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };

            this.mediaRecorder.onstop = () => {
                this.saveRecording();
            };

            this.mediaRecorder.start();
            this.isRecording = true;
            this.recordingStartTime = Date.now();

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
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;
            this.isPaused = false;

            if (this.mediaRecorder.stream) {
                this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
            }

            this.updateRecordingUI(false);
            this.stopTimer();
            this.stopAudioVisualization();

            console.log('Enregistrement arrêté');
        }
    }

    togglePause() {
        if (!this.isRecording) return;

        const btnPause = document.getElementById('btnPause');
        const status = document.getElementById('recordingStatus');

        if (!this.isPaused) {
            this.mediaRecorder.pause();
            this.isPaused = true;
            btnPause.classList.add('paused');
            status.textContent = 'En pause';
            status.classList.add('paused');
        } else {
            this.mediaRecorder.resume();
            this.isPaused = false;
            btnPause.classList.remove('paused');
            status.textContent = 'Enregistrement...';
            status.classList.remove('paused');
        }
    }

    updateRecordingUI(isRecording) {
        const btnRecord = document.getElementById('btnRecord');
        const btnStop = document.getElementById('btnStop');
        const btnPause = document.getElementById('btnPause');
        const status = document.getElementById('recordingStatus');
        const visualizerOverlay = document.querySelector('.visualizer-overlay');

        if (isRecording) {
            btnRecord.classList.add('recording');
            btnRecord.querySelector('span').textContent = 'Enregistrement...';
            btnStop.disabled = false;
            btnPause.disabled = false;
            status.textContent = 'Enregistrement...';
            status.classList.add('recording');
            visualizerOverlay?.classList.add('recording');
        } else {
            btnRecord.classList.remove('recording');
            btnRecord.querySelector('span').textContent = 'Enregistrer';
            btnStop.disabled = true;
            btnPause.disabled = true;
            status.textContent = 'Prêt';
            status.classList.remove('recording', 'paused');
            visualizerOverlay?.classList.remove('recording');
        }
    }

    startTimer() {
        const timerElement = document.getElementById('recordingTimer');
        if (!timerElement) return;

        let seconds = 0;

        this.timerInterval = setInterval(() => {
            seconds++;
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            timerElement.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }, 1000);
    }

    stopTimer() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
            document.getElementById('recordingTimer').textContent = '00:00';
        }
    }

    startAudioVisualization(stream) {
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = this.audioContext.createMediaStreamSource(stream);
            this.analyser = this.audioContext.createAnalyser();
            this.analyser.fftSize = 256;

            source.connect(this.analyser);

            const canvas = document.getElementById('audioCanvas');
            if (!canvas) return;

            const ctx = canvas.getContext('2d');
            const bufferLength = this.analyser.frequencyBinCount;
            const dataArray = new Uint8Array(bufferLength);

            const draw = () => {
                if (!this.isRecording) return;

                requestAnimationFrame(draw);

                this.analyser.getByteFrequencyData(dataArray);

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
                const audioLevel = document.getElementById('audioLevel');
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
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        const canvas = document.getElementById('audioCanvas');
        if (canvas) {
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#f8fafc';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        }

        const audioLevel = document.getElementById('audioLevel');
        if (audioLevel) {
            audioLevel.style.width = '0%';
        }
    }

    async saveRecording() {
        const blob = new Blob(this.audioChunks, { type: 'audio/webm' });
        const duration = Math.floor((Date.now() - this.recordingStartTime) / 1000);

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

    renderRecordings() {
        const listContainer = document.getElementById('recordingsList');
        const countElement = document.querySelector('.recordings-count');

        if (!listContainer || !countElement) return;

        countElement.textContent = `${this.recordings.length} fichiers`;

        if (this.recordings.length === 0) {
            listContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-microphone-slash"></i>
                    <p>Aucun enregistrement</p>
                    <span>Commencez par enregistrer votre première pensée</span>
                </div>
            `;
            return;
        }

        listContainer.innerHTML = '';
        const template = document.getElementById('recordingItemTemplate');
        if (!template) {
            console.error('Template non trouvé');
            return;
        }

        this.recordings.forEach(recording => {
            const item = template.content.cloneNode(true);
            const element = item.querySelector('.recording-item');

            // Formater la date depuis le timestamp
            const year = recording.timestamp.substring(0, 4);
            const month = recording.timestamp.substring(4, 6);
            const day = recording.timestamp.substring(6, 8);
            const hour = recording.timestamp.substring(9, 11);
            const min = recording.timestamp.substring(11, 13);
            const sec = recording.timestamp.substring(13, 15);
            const dateStr = `${day}/${month}/${year} ${hour}:${min}:${sec}`;

            element.dataset.filename = recording.filename;
            item.querySelector('.recording-name').textContent = `Pensée ${dateStr}`;
            item.querySelector('.recording-date').textContent = dateStr;
            item.querySelector('.recording-duration').textContent = '-';
            item.querySelector('.recording-size').textContent = this.formatSize(recording.size);

            const playBtn = item.querySelector('.btn-play');
            const downloadBtn = item.querySelector('.btn-download');
            const deleteBtn = item.querySelector('.btn-delete');
            const audioPlayer = item.querySelector('.audio-player');
            const playerContainer = item.querySelector('.audio-player-container');

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

            listContainer.appendChild(item);
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
        notification.className = 'thought-notification';
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
            animation: slideIn 0.3s ease;
            max-width: 350px;
        `;
        notification.textContent = message;

        document.body.appendChild(notification);

        setTimeout(() => {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 300);
        }, 3000);
    }

    cleanup() {
        console.log('🧹 Nettoyage du module...');

        if (this.isRecording) {
            this.stopRecording();
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }

        document.querySelectorAll('.thought-notification').forEach(notif => {
            notif.remove();
        });

        console.log('Module nettoyé');
    }
}

// Point d'entrée pour le dashboard
window.initThoughtCaptureModule = function() {
    return new ThoughtCaptureModule();
};