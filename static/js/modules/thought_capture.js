/**
 * Module Capture de Pensée - Version avec transcription Whisper
 * Interface deux colonnes moderne avec gestion des transcriptions
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
        this.wsClient = null;
        this.selectedRecording = null;
        this.transcriptionPollingInterval = null;

        // Template HTML pour les items de la liste
        this.recordingItemTemplateHTML = `
            <div class="thought_recording-item" data-filename="">
                <div class="thought_recording-info">
                    <div class="thought_recording-icon">
                        <i class="fas fa-file-audio"></i>
                    </div>
                    <div class="thought_recording-details">
                        <h4 class="thought_recording-name"></h4>
                        <div class="thought_recording-meta">
                            <span class="thought_recording-date"></span>
                            <span class="thought_recording-duration"></span>
                            <span class="thought_recording-transcription-status"></span>
                        </div>
                    </div>
                </div>
                
                <div class="thought_recording-actions">
                    <button class="thought_btn-action thought_btn-play" title="Écouter">
                        <i class="fas fa-play"></i>
                    </button>
                    <button class="thought_btn-action thought_btn-transcribe" title="Voir transcription">
                        <i class="fas fa-file-text"></i>
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
        console.log('Initialisation du module Capture de Pensée avec Transcription');

        try {
            // Récupérer le client WebSocket
            this.wsClient = window.dashboard?.wsClient;

            // Ne pas réinitialiser le timer si un enregistrement est en cours
            if (!this.thought_isRecording) {
                if (this.thought_timerInterval) {
                    clearInterval(this.thought_timerInterval);
                    this.thought_timerInterval = null;
                }

                const timerElement = document.getElementById('thought_recordingTimer');
                if (timerElement) {
                    timerElement.textContent = '00:00';
                }
            } else {
                console.log('Enregistrement en cours, conservation du timer');
                this.startTimer();

                if (this.thought_mediaRecorder && this.thought_mediaRecorder.stream) {
                    this.startAudioVisualization(this.thought_mediaRecorder.stream);
                }
            }

            // Charger la liste des enregistrements
            await this.loadRecordings();

            // Configuration des boutons
            this.setupEventListeners();

            // Vérifier les permissions audio
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

            // Initialiser l'affichage de la transcription
            this.initTranscriptionDisplay();

            // Émettre les statistiques initiales
            this.emitStatsUpdate();

            console.log('Module initialisé avec transcription');
        } catch (error) {
            console.error('Erreur:', error);
        }
    }

    initTranscriptionDisplay() {
        // Afficher un message par défaut dans la zone de transcription
        const transcriptionContent = document.getElementById('thought_transcriptionContent');
        if (transcriptionContent && !this.selectedRecording) {
            transcriptionContent.innerHTML = `
                <div class="thought_empty-transcription">
                    <i class="fas fa-file-text"></i>
                    <p>Aucune transcription sélectionnée</p>
                    <span>Sélectionnez un enregistrement pour voir sa transcription</span>
                </div>
            `;
        }
    }

    async loadRecordings() {
        try {
            const response = await fetch('/api/thought-capture/list-audios');
            const data = await response.json();

            this.thought_recordings = data.files || [];
            console.log(`${this.thought_recordings.length} fichiers trouvés`);

            this.renderRecordings();
            this.calculateAndEmitStats();
        } catch (error) {
            console.error('Erreur chargement:', error);
            this.thought_recordings = [];
            this.renderRecordings();
        }
    }

    setupEventListeners() {
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

        // Bouton pour copier la transcription
        const btnCopy = document.getElementById('thought_btnCopyTranscription');
        if (btnCopy) {
            btnCopy.addEventListener('click', () => this.copyTranscriptionToClipboard());
        }

        // Écouter les événements WebSocket
        if (this.wsClient && this.wsClient.socket) {
            this.wsClient.socket.on('thought_capture_start_recording', () => {
                if (!this.thought_isRecording) {
                    this.startRecording();
                }
            });

            this.wsClient.socket.on('thought_capture_stop_recording', () => {
                if (this.thought_isRecording) {
                    this.stopRecording();
                }
            });

            this.wsClient.socket.on('thought_capture_transcription_ready', (data) => {
                this.onTranscriptionReady(data);
            });
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
        ctx.strokeStyle = '#3b82f6';
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
                this.stopTimer();
                await this.saveRecording();
            };

            this.thought_mediaRecorder.start();
            this.thought_isRecording = true;
            this.thought_recordingStartTime = Date.now();

            this.updateRecordingUI(true);
            this.startTimer();
            this.startAudioVisualization(stream);

            this.emitRecordingStarted();

            console.log('Enregistrement démarré');
        } catch (error) {
            console.error('Erreur:', error);
            this.showNotification('Impossible de démarrer l\'enregistrement', 'error');
        }
    }

    stopRecording() {
        if (this.thought_mediaRecorder && this.thought_isRecording) {
            const duration = Math.floor((Date.now() - this.thought_recordingStartTime) / 1000);

            this.thought_mediaRecorder.stop();
            this.thought_isRecording = false;
            this.thought_isPaused = false;
            this.thought_recordingStartTime = null;

            if (this.thought_mediaRecorder.stream) {
                this.thought_mediaRecorder.stream.getTracks().forEach(track => track.stop());
            }

            this.stopTimer();
            this.updateRecordingUI(false);
            this.stopAudioVisualization();

            this.emitRecordingStopped(duration);

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

            this.emitRecordingPaused();
        } else {
            this.thought_mediaRecorder.resume();
            this.thought_isPaused = false;
            btnPause.classList.remove('thought_paused');
            status.textContent = 'Enregistrement...';
            status.classList.remove('thought_paused');

            this.emitRecordingResumed();
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

            if (timerElement) {
                timerElement.textContent = '00:00';
            }
        }
    }

    startTimer() {
        if (this.thought_timerInterval) {
            clearInterval(this.thought_timerInterval);
            this.thought_timerInterval = null;
        }

        const timerElement = document.getElementById('thought_recordingTimer');
        if (!timerElement) return;

        const startTime = this.thought_recordingStartTime || Date.now();

        this.thought_timerInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            const mins = Math.floor(elapsed / 60);
            const secs = elapsed % 60;

            const currentTimerElement = document.getElementById('thought_recordingTimer');
            if (currentTimerElement) {
                currentTimerElement.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
            } else {
                clearInterval(this.thought_timerInterval);
                this.thought_timerInterval = null;
            }
        }, 1000);

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

                ctx.fillStyle = '#ffffff';
                ctx.fillRect(0, 0, canvas.width, canvas.height);

                const barWidth = (canvas.width / bufferLength) * 2.5;
                let barHeight;
                let x = 0;

                for (let i = 0; i < bufferLength; i++) {
                    barHeight = (dataArray[i] / 255) * canvas.height * 0.8;

                    const gradient = ctx.createLinearGradient(0, canvas.height, 0, canvas.height - barHeight);
                    gradient.addColorStop(0, '#3b82f6');
                    gradient.addColorStop(1, '#60a5fa');

                    ctx.fillStyle = gradient;
                    ctx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);

                    x += barWidth + 1;
                }

                const average = dataArray.reduce((a, b) => a + b) / bufferLength;
                const level = (average / 255) * 100;
                const audioLevel = document.getElementById('thought_audioLevel');
                if (audioLevel) {
                    audioLevel.style.width = `${level}%`;
                }

                this.emitAudioLevel(level, dataArray);
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
            ctx.fillStyle = '#ffffff';
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

        const formData = new FormData();
        formData.append('audio', blob, 'recording.webm');
        formData.append('duration', duration);

        try {
            this.showNotification('Sauvegarde et transcription en cours...', 'info');

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

            // Si transcription en attente, démarrer le polling
            if (result.transcription_pending) {
                this.startTranscriptionPolling(result.filename);
            }

            this.showNotification('Enregistrement sauvegardé ! Transcription en cours...', 'success');
        } catch (error) {
            console.error('Erreur:', error);
            this.showNotification('Erreur lors de la sauvegarde', 'error');
        }
    }

    startTranscriptionPolling(filename) {
        // Vérifier périodiquement si la transcription est prête
        let attempts = 0;
        const maxAttempts = 30; // Maximum 30 secondes

        const checkTranscription = async () => {
            attempts++;

            try {
                const response = await fetch(`/api/thought-capture/get-transcription/${filename}`);
                const data = await response.json();

                if (data.success && data.transcription) {
                    // Transcription prête
                    this.onTranscriptionReady({ filename, transcription: data.transcription });

                    // Recharger la liste pour mettre à jour le statut
                    await this.loadRecordings();

                    clearInterval(this.transcriptionPollingInterval);
                    this.transcriptionPollingInterval = null;
                } else if (attempts >= maxAttempts) {
                    clearInterval(this.transcriptionPollingInterval);
                    this.transcriptionPollingInterval = null;
                }
            } catch (error) {
                console.error('Erreur polling transcription:', error);
                clearInterval(this.transcriptionPollingInterval);
                this.transcriptionPollingInterval = null;
            }
        };

        // Vérifier toutes les secondes
        this.transcriptionPollingInterval = setInterval(checkTranscription, 1000);
    }

    onTranscriptionReady(data) {
        console.log('Transcription prête:', data.filename);

        // Mettre à jour l'élément dans la liste
        const item = document.querySelector(`[data-filename="${data.filename}"]`);
        if (item) {
            const statusElement = item.querySelector('.thought_recording-transcription-status');
            if (statusElement) {
                statusElement.innerHTML = '<i class="fas fa-check-circle"></i> Transcrit';
                statusElement.classList.add('thought_transcribed');
            }
        }

        // Si c'est l'enregistrement sélectionné, afficher la transcription
        if (this.selectedRecording === data.filename) {
            this.displayTranscription(data.transcription);
        }

        this.showNotification('Transcription terminée !', 'success');
    }

    async selectRecording(filename) {
        this.selectedRecording = filename;

        // Mettre à jour l'UI pour montrer la sélection
        document.querySelectorAll('.thought_recording-item').forEach(item => {
            item.classList.remove('thought_selected');
        });

        const selectedItem = document.querySelector(`[data-filename="${filename}"]`);
        if (selectedItem) {
            selectedItem.classList.add('thought_selected');
        }

        // Charger et afficher la transcription
        await this.loadTranscription(filename);
    }

    async loadTranscription(filename) {
        const transcriptionContent = document.getElementById('thought_transcriptionContent');
        const transcriptionHeader = document.getElementById('thought_selectedRecordingName');

        // Afficher un loader
        if (transcriptionContent) {
            transcriptionContent.innerHTML = `
                <div class="thought_loading-transcription">
                    <div class="thought_spinner"></div>
                    <p>Chargement de la transcription...</p>
                </div>
            `;
        }

        // Mettre à jour le header
        if (transcriptionHeader) {
            const recording = this.thought_recordings.find(r => r.filename === filename);
            if (recording) {
                const date = this.formatTimestamp(recording.timestamp);
                transcriptionHeader.textContent = `Pensée du ${date}`;
            }
        }

        try {
            // Essayer de récupérer la transcription existante
            let response = await fetch(`/api/thought-capture/get-transcription/${filename}`);
            let data = await response.json();

            if (!data.success || !data.transcription) {
                // Si pas de transcription, en demander une
                response = await fetch(`/api/thought-capture/transcribe/${filename}`, {
                    method: 'POST'
                });
                data = await response.json();
            }

            if (data.success && data.transcription) {
                this.displayTranscription(data.transcription);

                // Mettre à jour le statut dans la liste
                const item = document.querySelector(`[data-filename="${filename}"]`);
                if (item) {
                    const statusElement = item.querySelector('.thought_recording-transcription-status');
                    if (statusElement && !statusElement.classList.contains('thought_transcribed')) {
                        statusElement.innerHTML = '<i class="fas fa-check-circle"></i> Transcrit';
                        statusElement.classList.add('thought_transcribed');
                    }
                }
            } else {
                this.displayTranscriptionError('Transcription non disponible');
            }
        } catch (error) {
            console.error('Erreur chargement transcription:', error);
            this.displayTranscriptionError('Erreur lors du chargement de la transcription');
        }
    }

    displayTranscription(transcription) {
        const transcriptionContent = document.getElementById('thought_transcriptionContent');
        if (!transcriptionContent) return;

        // Afficher le texte principal
        let html = `
            <div class="thought_transcription-text">
                ${this.formatTranscriptionText(transcription.text)}
            </div>
        `;

        // Si on a des segments avec timestamps, les afficher
        if (transcription.segments && transcription.segments.length > 0) {
            html += `
                <div class="thought_transcription-segments">
                    <h4>Segments détaillés</h4>
                    <div class="thought_segments-list">
            `;

            transcription.segments.forEach(segment => {
                const startTime = this.formatTime(segment.start);
                const endTime = this.formatTime(segment.end);
                html += `
                    <div class="thought_segment">
                        <span class="thought_segment-time">[${startTime} - ${endTime}]</span>
                        <span class="thought_segment-text">${segment.text}</span>
                    </div>
                `;
            });

            html += `
                    </div>
                </div>
            `;
        }

        transcriptionContent.innerHTML = html;
    }

    displayTranscriptionError(message) {
        const transcriptionContent = document.getElementById('thought_transcriptionContent');
        if (transcriptionContent) {
            transcriptionContent.innerHTML = `
                <div class="thought_transcription-error">
                    <i class="fas fa-exclamation-triangle"></i>
                    <p>${message}</p>
                </div>
            `;
        }
    }

    formatTranscriptionText(text) {
        // Formater le texte pour une meilleure lisibilité
        return text
            .replace(/\n/g, '<br>')
            .replace(/([.!?])\s+/g, '$1<br><br>')
            .trim();
    }

    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    formatTimestamp(timestamp) {
        const year = timestamp.substring(0, 4);
        const month = timestamp.substring(4, 6);
        const day = timestamp.substring(6, 8);
        const hour = timestamp.substring(9, 11);
        const min = timestamp.substring(11, 13);
        return `${day}/${month}/${year} à ${hour}:${min}`;
    }

    async copyTranscriptionToClipboard() {
        const transcriptionText = document.querySelector('.thought_transcription-text');
        if (transcriptionText) {
            const text = transcriptionText.innerText;
            try {
                await navigator.clipboard.writeText(text);
                this.showNotification('Transcription copiée !', 'success');
            } catch (error) {
                console.error('Erreur copie:', error);
                this.showNotification('Erreur lors de la copie', 'error');
            }
        }
    }

    createRecordingElement(recording) {
        const wrapper = document.createElement('div');
        wrapper.innerHTML = this.recordingItemTemplateHTML;
        const element = wrapper.firstElementChild;

        const dateStr = this.formatTimestamp(recording.timestamp);

        element.dataset.filename = recording.filename;
        element.querySelector('.thought_recording-name').textContent = `Pensée ${dateStr}`;
        element.querySelector('.thought_recording-date').textContent = dateStr;
        element.querySelector('.thought_recording-duration').textContent = `${recording.duration || 0}s`;

        // Statut de transcription
        const transcriptionStatus = element.querySelector('.thought_recording-transcription-status');
        if (recording.has_transcription) {
            transcriptionStatus.innerHTML = '<i class="fas fa-check-circle"></i> Transcrit';
            transcriptionStatus.classList.add('thought_transcribed');
        } else {
            transcriptionStatus.innerHTML = '<i class="fas fa-clock"></i> En attente';
        }

        const playBtn = element.querySelector('.thought_btn-play');
        const transcribeBtn = element.querySelector('.thought_btn-transcribe');
        const downloadBtn = element.querySelector('.thought_btn-download');
        const deleteBtn = element.querySelector('.thought_btn-delete');
        const audioPlayer = element.querySelector('.thought_audio-player');
        const playerContainer = element.querySelector('.thought_audio-player-container');

        const audioUrl = recording.url;

        // Clic sur l'élément pour sélectionner
        element.addEventListener('click', (e) => {
            if (!e.target.closest('.thought_recording-actions') &&
                !e.target.closest('.thought_audio-player-container')) {
                this.selectRecording(recording.filename);
            }
        });

        playBtn.addEventListener('click', (e) => {
            e.stopPropagation();
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

        transcribeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.selectRecording(recording.filename);
        });

        downloadBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const a = document.createElement('a');
            a.href = audioUrl;
            a.download = recording.filename;
            a.click();
            this.showNotification('Téléchargement démarré', 'success');
        });

        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.deleteRecording(recording.filename);
        });

        return element;
    }

    renderRecordings() {
        const listContainer = document.getElementById('thought_recordingsList');
        const countElement = document.querySelector('.thought_recordings-count');

        if (!listContainer || !countElement) return;

        countElement.textContent = `${this.thought_recordings.length} enregistrements`;

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

        // Si un enregistrement était sélectionné, le resélectionner
        if (this.selectedRecording) {
            const selectedItem = document.querySelector(`[data-filename="${this.selectedRecording}"]`);
            if (selectedItem) {
                selectedItem.classList.add('thought_selected');
            }
        }
    }

    formatSize(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }

    async deleteRecording(filename) {
        if (confirm('Êtes-vous sûr de vouloir supprimer cet enregistrement et sa transcription ?')) {
            try {
                const response = await fetch(`/api/thought-capture/delete-audio/${filename}`, {
                    method: 'DELETE'
                });

                if (!response.ok) {
                    throw new Error('Erreur serveur');
                }

                // Si c'était l'enregistrement sélectionné, réinitialiser
                if (this.selectedRecording === filename) {
                    this.selectedRecording = null;
                    this.initTranscriptionDisplay();
                }

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
            border-radius: 12px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.2);
            z-index: 10000;
            animation: thought_slideIn 0.3s ease;
            max-width: 350px;
            font-weight: 500;
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

    // === MÉTHODES D'ÉMISSION WEBSOCKET ===

    emitRecordingStarted() {
        if (this.wsClient && this.wsClient.socket) {
            this.wsClient.socket.emit('thought_capture_recording_started', {
                timestamp: new Date().toISOString()
            });
        }
    }

    emitRecordingStopped(duration) {
        if (this.wsClient && this.wsClient.socket) {
            const estimatedSize = duration * 16000;

            this.wsClient.socket.emit('thought_capture_recording_stopped', {
                duration: duration,
                size: estimatedSize,
                timestamp: new Date().toISOString()
            });
        }
    }

    emitRecordingPaused() {
        if (this.wsClient && this.wsClient.socket) {
            this.wsClient.socket.emit('thought_capture_recording_paused', {
                timestamp: new Date().toISOString()
            });
        }
    }

    emitRecordingResumed() {
        if (this.wsClient && this.wsClient.socket) {
            this.wsClient.socket.emit('thought_capture_recording_resumed', {
                timestamp: new Date().toISOString()
            });
        }
    }

    emitAudioLevel(level, waveformData) {
        if (this.wsClient && this.wsClient.socket) {
            if (!this.lastAudioLevelEmit || Date.now() - this.lastAudioLevelEmit > 100) {
                this.lastAudioLevelEmit = Date.now();

                const waveform = [];
                const step = Math.floor(waveformData.length / 64);
                for (let i = 0; i < waveformData.length; i += step) {
                    waveform.push(waveformData[i]);
                }

                this.wsClient.socket.emit('thought_capture_audio_level', {
                    level: level,
                    frequency: this.calculateDominantFrequency(waveformData),
                    waveform: waveform,
                    timestamp: new Date().toISOString()
                });
            }
        }
    }

    emitStatsUpdate() {
        if (this.wsClient && this.wsClient.socket) {
            const stats = this.calculateStats();
            this.wsClient.socket.emit('thought_capture_stats_update', stats);
        }
    }

    calculateStats() {
        let totalDuration = 0;
        let totalSize = 0;
        let totalTranscribed = 0;

        this.thought_recordings.forEach(recording => {
            totalDuration += recording.duration || 0;
            totalSize += recording.size || 0;
            if (recording.has_transcription) {
                totalTranscribed++;
            }
        });

        return {
            total_recordings: this.thought_recordings.length,
            total_duration: totalDuration,
            total_size: totalSize,
            total_transcribed: totalTranscribed,
            timestamp: new Date().toISOString()
        };
    }

    calculateAndEmitStats() {
        const stats = this.calculateStats();
        this.emitStatsUpdate();

        const totalRecordingsEl = document.querySelector('.thought_stats-value[data-stat="total"]');
        const totalDurationEl = document.querySelector('.thought_stats-value[data-stat="duration"]');
        const totalSizeEl = document.querySelector('.thought_stats-value[data-stat="size"]');

        if (totalRecordingsEl) totalRecordingsEl.textContent = stats.total_recordings;
        if (totalDurationEl) totalDurationEl.textContent = this.formatDuration(stats.total_duration);
        if (totalSizeEl) totalSizeEl.textContent = this.formatSize(stats.total_size);
    }

    calculateDominantFrequency(dataArray) {
        let maxValue = 0;
        let maxIndex = 0;

        for (let i = 0; i < dataArray.length; i++) {
            if (dataArray[i] > maxValue) {
                maxValue = dataArray[i];
                maxIndex = i;
            }
        }

        const nyquist = this.thought_audioContext ? this.thought_audioContext.sampleRate / 2 : 22050;
        const frequency = (maxIndex / dataArray.length) * nyquist;

        return Math.round(frequency);
    }

    formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;

        if (hours > 0) {
            return `${hours}h ${minutes}m`;
        } else if (minutes > 0) {
            return `${minutes}m ${secs}s`;
        } else {
            return `${secs}s`;
        }
    }

    cleanup() {
        console.log('Nettoyage du module...');

        if (this.thought_isRecording) {
            this.stopRecording();
        }

        if (this.thought_timerInterval) {
            clearInterval(this.thought_timerInterval);
            this.thought_timerInterval = null;
        }

        if (this.transcriptionPollingInterval) {
            clearInterval(this.transcriptionPollingInterval);
            this.transcriptionPollingInterval = null;
        }

        if (this.thought_audioContext) {
            this.thought_audioContext.close();
            this.thought_audioContext = null;
        }

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