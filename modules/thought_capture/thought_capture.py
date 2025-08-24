#!/usr/bin/env python3
"""
Module Thought Capture - Routes et logique backend avec transcription Whisper optimisée
"""

from flask import Blueprint, request, jsonify, current_app
import os
from datetime import datetime
import logging
import json
import whisper
import torch
import threading
from queue import Queue
import re

# Créer le blueprint pour ce module
thought_capture_bp = Blueprint(
    'thought_capture',
    __name__,
    url_prefix='/api/thought-capture'
)

# Configuration du logging
logger = logging.getLogger(__name__)

# Configuration du module
AUDIO_FOLDER = 'static/audio_recordings'
TRANSCRIPTION_FOLDER = 'static/transcriptions'

# Modèle Whisper global (chargé une seule fois)
whisper_model = None
def load_whisper_model():
    """Charger Whisper uniquement si nécessaire"""
    global whisper_model
    if whisper_model is None:
        try:
            logger.info("Chargement à la demande du modèle Whisper Large...")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            whisper_model = whisper.load_model("large", device=device)
            logger.info(f"Modèle Whisper Large chargé sur {device}")
        except Exception as e:
            logger.error(f"Erreur chargement Whisper Large: {e}")
            logger.info("Tentative de fallback sur modèle Base...")
            try:
                whisper_model = whisper.load_model("base", device=device)
                logger.info(f"Modèle Whisper Base chargé sur {device}")
            except Exception as e2:
                logger.error(f"Erreur chargement Whisper Base: {e2}")
                whisper_model = None

transcription_queue = Queue()
transcription_thread = None

def perform_transcription(filepath, metadata_file, retranscribe=False):
    """Effectuer la transcription avec Whisper optimisé"""
    load_whisper_model()
    if whisper_model is None:
        return None, "Modèle Whisper non disponible"

    transcribe_params = {
        'language': 'fr',
        'temperature': 0,
        'without_timestamps': True,
        'condition_on_previous_text': True
    }
    if torch.cuda.is_available():
        transcribe_params['fp16'] = True

    logger.info(f"{'Re-' if retranscribe else ''}Transcription en cours: {os.path.basename(filepath)}")
    result = whisper_model.transcribe(filepath, **transcribe_params)

    cleaned_text = clean_transcription_text(result['text'])
    transcription_data = {
        'text': cleaned_text,
        'raw_text': result['text'],
        'segments': result.get('segments', []),
        'language': result.get('language', 'fr'),
        'timestamp': datetime.now().isoformat(),
        'model_used': 'large' if 'large' in str(whisper_model) else 'base',
        'device': 'cuda' if torch.cuda.is_available() else 'cpu'
    }
    if retranscribe:
        transcription_data['retranscribed'] = True

    # Mettre à jour les métadonnées
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        if retranscribe and metadata.get('transcription'):
            metadata['previous_transcription'] = metadata['transcription']
        metadata['transcription'] = transcription_data
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    return transcription_data, None


def clean_transcription_text(text):
    """Nettoyer le texte transcrit"""
    # Supprimer les espaces multiples et trimmer
    text_clean = re.sub(r"\s+", " ", text).strip()
    return text_clean


def init_module(app):
    """Initialiser le module avec l'application Flask"""
    global whisper_model, transcription_thread
    
    # Créer les dossiers nécessaires
    audio_path = os.path.join(app.root_path, AUDIO_FOLDER)
    transcription_path = os.path.join(app.root_path, TRANSCRIPTION_FOLDER)
    os.makedirs(audio_path, exist_ok=True)
    os.makedirs(transcription_path, exist_ok=True)
    
    logger.info(f"Module Thought Capture initialisé - Dossier audio: {audio_path}")
    logger.info(f"Dossier transcriptions: {transcription_path}")
    
    # Charger le modèle Whisper optimisé
    # try:
    #     logger.info("Chargement du modèle Whisper Large...")
    #     device = "cuda" if torch.cuda.is_available() else "cpu"
    #     logger.info(f"Utilisation de : {device}")
    #
    #     # Utiliser le modèle large pour une meilleure précision
    #     whisper_model = whisper.load_model("large", device=device)
    #     logger.info(f"Modèle Whisper Large chargé sur {device}")
    # except Exception as e:
    #     logger.error(f"Erreur chargement Whisper: {e}")
    #     # Fallback sur un modèle plus petit si le large échoue
    #     try:
    #         logger.info("Tentative de chargement du modèle base...")
    #         whisper_model = whisper.load_model("base", device=device)
    #         logger.info(f"Modèle Whisper Base chargé sur {device} (fallback)")
    #     except Exception as e2:
    #         logger.error(f"Erreur chargement Whisper Base: {e2}")
    #         whisper_model = None
    
    # Démarrer le thread de transcription
    transcription_thread = threading.Thread(target=process_transcription_queue, daemon=True)
    transcription_thread.start()
    
    # Enregistrer le blueprint
    app.register_blueprint(thought_capture_bp)
    
    # Ajouter la configuration au registre des modules si disponible
    if hasattr(app, 'module_registry'):
        app.module_registry.update_module_config('thought_capture', {
            'audio_folder': AUDIO_FOLDER,
            'transcription_folder': TRANSCRIPTION_FOLDER,
            'max_file_size': 50 * 1024 * 1024,  # 50 MB
            'allowed_formats': ['webm', 'mp3', 'wav', 'ogg'],
            'whisper_model': 'large',
            'whisper_device': device,
            'whisper_optimizations': {
                'fp16': torch.cuda.is_available(),  # Utiliser FP16 si GPU disponible
                'temperature': 0,
                'without_timestamps': True,
                'condition_on_previous_text': True
            }
        })


def process_transcription_queue():
    """Thread pour traiter la queue de transcription avec paramètres optimisés"""
    while True:
        try:
            task = transcription_queue.get()
            if task is None:
                break
            
            filepath = task['filepath']
            metadata_file = task['metadata_file']
            
            # Effectuer la transcription avec paramètres optimisés
            if whisper_model:
                logger.info(f"Début transcription optimisée: {filepath}")
                
                # Paramètres optimisés pour la transcription
                transcribe_params = {
                    'language': 'fr',
                    'temperature': 0,  # Déterministe
                    'without_timestamps': True,  # Plus rapide sans timestamps
                    'condition_on_previous_text': True,  # Meilleur contexte
                }
                
                # Ajouter FP16 si GPU disponible
                if torch.cuda.is_available():
                    transcribe_params['fp16'] = True
                
                result = whisper_model.transcribe(filepath, **transcribe_params)
                
                # Nettoyer le texte transcrit
                cleaned_text = clean_transcription_text(result['text'])
                
                # Charger les métadonnées existantes
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Ajouter la transcription nettoyée
                metadata['transcription'] = {
                    'text': cleaned_text,
                    'raw_text': result['text'],  # Conserver l'original aussi
                    'segments': result.get('segments', []),
                    'language': result.get('language', 'fr'),
                    'timestamp': datetime.now().isoformat(),
                    'model_used': 'large' if 'large' in str(whisper_model) else 'base',
                    'device': 'cuda' if torch.cuda.is_available() else 'cpu'
                }
                
                # Sauvegarder les métadonnées mises à jour
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                
                logger.info(f"Transcription terminée: {os.path.basename(filepath)} - {len(cleaned_text)} caractères")
        
        except Exception as e:
            logger.error(f"Erreur transcription: {e}")
        finally:
            transcription_queue.task_done()


# ========================
# ROUTES DU MODULE
# ========================

@thought_capture_bp.route('/save-audio', methods=['POST'])
def save_audio():
    """Sauvegarder un fichier audio et lancer la transcription"""
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'Pas de fichier audio'}), 400
        
        audio_file = request.files['audio']
        
        # Créer un nom de fichier unique
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"recording_{timestamp}.webm"
        
        # Chemin complet du fichier
        audio_folder_path = os.path.join(current_app.root_path, AUDIO_FOLDER)
        filepath = os.path.join(audio_folder_path, filename)
        
        # Sauvegarder le fichier
        audio_file.save(filepath)
        
        # Récupérer la durée si fournie
        duration = request.form.get('duration', '0')
        
        # Sauvegarder les métadonnées
        metadata_file = filepath.replace('.webm', '.json')
        metadata = {
            'filename': filename,
            'timestamp': timestamp,
            'date': datetime.now().isoformat(),
            'duration': int(duration),
            'size': os.path.getsize(filepath),
            'transcription': None  # Sera rempli par le thread
        }
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        # Ajouter à la queue de transcription
        if whisper_model:
            transcription_queue.put({
                'filepath': filepath,
                'metadata_file': metadata_file
            })
        
        # Retourner l'URL pour accéder au fichier
        file_url = f"/{AUDIO_FOLDER}/{filename}"
        
        logger.info(f"Audio sauvegardé: {filename}")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'url': file_url,
            'timestamp': timestamp,
            'duration': duration,
            'transcription_pending': whisper_model is not None
        })
    
    except Exception as e:
        logger.error(f"Erreur sauvegarde audio: {e}")
        return jsonify({'error': str(e)}), 500


@thought_capture_bp.route('/transcribe/<filename>', methods=['POST'])
def transcribe_audio(filename):
    """Transcrire un fichier audio avec Whisper optimisé"""
    try:
        # Sécurité
        if '..' in filename or '/' in filename:
            return jsonify({'error': 'Nom de fichier invalide'}), 400

        audio_folder_path = os.path.join(current_app.root_path, AUDIO_FOLDER)
        filepath = os.path.join(audio_folder_path, filename)
        if not os.path.exists(filepath):
            return jsonify({'error': 'Fichier non trouvé'}), 404

        # Vérifier si transcription déjà présente
        metadata_file = filepath.replace('.webm', '.json')
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                if metadata.get('transcription'):
                    return jsonify({
                        'success': True,
                        'transcription': metadata['transcription'],
                        'cached': True
                    })

        # Effectuer la transcription
        transcription_data, error = perform_transcription(filepath, metadata_file, retranscribe=False)
        if error:
            return jsonify({'error': error}), 503

        return jsonify({
            'success': True,
            'transcription': transcription_data,
            'cached': False
        })

    except Exception as e:
        logger.error(f"Erreur transcription: {e}")
        return jsonify({'error': str(e)}), 500


@thought_capture_bp.route('/get-transcription/<filename>', methods=['GET'])
def get_transcription(filename):
    """Obtenir la transcription d'un fichier"""
    try:
        # Sécuriser le nom de fichier
        if '..' in filename or '/' in filename:
            return jsonify({'error': 'Nom de fichier invalide'}), 400
        
        audio_folder_path = os.path.join(current_app.root_path, AUDIO_FOLDER)
        metadata_file = os.path.join(audio_folder_path, filename.replace('.webm', '.json'))
        
        if not os.path.exists(metadata_file):
            return jsonify({'error': 'Métadonnées non trouvées'}), 404
        
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        if metadata.get('transcription'):
            return jsonify({
                'success': True,
                'transcription': metadata['transcription'],
                'metadata': {
                    'date': metadata.get('date'),
                    'duration': metadata.get('duration'),
                    'size': metadata.get('size')
                }
            })
        else:
            return jsonify({
                'success': False,
                'pending': True,
                'message': 'Transcription en cours'
            })
    
    except Exception as e:
        logger.error(f"Erreur récupération transcription: {e}")
        return jsonify({'error': str(e)}), 500


@thought_capture_bp.route('/list-audios', methods=['GET'])
def list_audios():
    """Lister tous les fichiers audio avec leurs transcriptions"""
    try:
        files = []
        audio_folder_path = os.path.join(current_app.root_path, AUDIO_FOLDER)
        
        # Parcourir le dossier des enregistrements
        if os.path.exists(audio_folder_path):
            for filename in os.listdir(audio_folder_path):
                if filename.endswith('.webm'):
                    filepath = os.path.join(audio_folder_path, filename)
                    
                    # Extraire la date du nom de fichier
                    timestamp = filename.replace('recording_', '').replace('.webm', '')
                    
                    # Lire les métadonnées si disponibles
                    metadata_file = filepath.replace('.webm', '.json')
                    has_transcription = False
                    duration = 0
                    transcription_text = None
                    
                    if os.path.exists(metadata_file):
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            duration = metadata.get('duration', 0)
                            has_transcription = metadata.get('transcription') is not None
                            if has_transcription:
                                transcription_text = metadata['transcription'].get('text', '')
                    
                    files.append({
                        'filename': filename,
                        'url': f"/{AUDIO_FOLDER}/{filename}",
                        'size': os.path.getsize(filepath),
                        'timestamp': timestamp,
                        'duration': duration,
                        'has_transcription': has_transcription,
                        'transcription_preview': transcription_text[:100] + '...' if transcription_text and len(
                            transcription_text) > 100 else transcription_text
                    })
        
        # Trier par date (plus récent en premier)
        files.sort(key=lambda x: x['timestamp'], reverse=True)
        
        logger.info(f"{len(files)} fichiers audio trouvés")
        
        return jsonify({
            'files': files,
            'total': len(files),
            'whisper_available': whisper_model is not None,
            'model_info': {
                'model': 'large' if whisper_model and 'large' in str(whisper_model) else 'base',
                'device': 'cuda' if torch.cuda.is_available() else 'cpu',
                'fp16_enabled': torch.cuda.is_available()
            }
        })
    
    except Exception as e:
        logger.error(f"Erreur listing audio: {e}")
        return jsonify({'error': str(e)}), 500


@thought_capture_bp.route('/delete-audio/<filename>', methods=['DELETE'])
def delete_audio(filename):
    """Supprimer un fichier audio et sa transcription"""
    try:
        # Sécuriser le nom de fichier
        if '..' in filename or '/' in filename:
            return jsonify({'error': 'Nom de fichier invalide'}), 400
        
        audio_folder_path = os.path.join(current_app.root_path, AUDIO_FOLDER)
        filepath = os.path.join(audio_folder_path, filename)
        
        # Supprimer le fichier audio
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Fichier audio supprimé: {filename}")
            
            # Supprimer les métadonnées si elles existent
            metadata_file = filepath.replace('.webm', '.json')
            if os.path.exists(metadata_file):
                os.remove(metadata_file)
            
            return jsonify({'success': True, 'message': 'Fichier supprimé'})
        else:
            return jsonify({'error': 'Fichier non trouvé'}), 404
    
    except Exception as e:
        logger.error(f"Erreur suppression audio: {e}")
        return jsonify({'error': str(e)}), 500


@thought_capture_bp.route('/stats', methods=['GET'])
def get_stats():
    """Obtenir des statistiques sur les enregistrements"""
    try:
        audio_folder_path = os.path.join(current_app.root_path, AUDIO_FOLDER)
        
        total_files = 0
        total_size = 0
        total_duration = 0
        total_transcribed = 0
        total_words = 0
        
        if os.path.exists(audio_folder_path):
            for filename in os.listdir(audio_folder_path):
                if filename.endswith('.webm'):
                    filepath = os.path.join(audio_folder_path, filename)
                    total_files += 1
                    total_size += os.path.getsize(filepath)
                    
                    # Lire la durée et statut de transcription depuis les métadonnées
                    metadata_file = filepath.replace('.webm', '.json')
                    if os.path.exists(metadata_file):
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            total_duration += metadata.get('duration', 0)
                            if metadata.get('transcription'):
                                total_transcribed += 1
                                # Compter les mots dans la transcription
                                text = metadata['transcription'].get('text', '')
                                total_words += len(text.split())
        
        return jsonify({
            'total_recordings': total_files,
            'total_size': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'total_duration': total_duration,
            'average_duration': round(total_duration / total_files, 2) if total_files > 0 else 0,
            'total_transcribed': total_transcribed,
            'total_words': total_words,
            'average_words': round(total_words / total_transcribed, 2) if total_transcribed > 0 else 0,
            'whisper_available': whisper_model is not None,
            'model_info': {
                'model': 'large' if whisper_model and 'large' in str(whisper_model) else 'base',
                'device': 'cuda' if torch.cuda.is_available() else 'cpu',
                'fp16_enabled': torch.cuda.is_available()
            }
        })
    
    except Exception as e:
        logger.error(f"Erreur stats: {e}")
        return jsonify({'error': str(e)}), 500


@thought_capture_bp.route('/retranscribe/<filename>', methods=['POST'])
def retranscribe_audio(filename):
    """Forcer la re-transcription d'un fichier audio"""
    try:
        # Sécurité
        if '..' in filename or '/' in filename:
            return jsonify({'error': 'Nom de fichier invalide'}), 400

        audio_folder_path = os.path.join(current_app.root_path, AUDIO_FOLDER)
        filepath = os.path.join(audio_folder_path, filename)
        if not os.path.exists(filepath):
            return jsonify({'error': 'Fichier non trouvé'}), 404

        metadata_file = filepath.replace('.webm', '.json')
        transcription_data, error = perform_transcription(filepath, metadata_file, retranscribe=True)
        if error:
            return jsonify({'error': error}), 503

        return jsonify({
            'success': True,
            'transcription': transcription_data,
            'message': 'Re-transcription réussie'
        })

    except Exception as e:
        logger.error(f"Erreur re-transcription: {e}")
        return jsonify({'error': str(e)}), 500


# ========================
# ÉVÉNEMENTS WEBSOCKET (si utilisé)
# ========================

def register_websocket_events(websocket_manager):
    """Enregistrer les événements WebSocket pour ce module"""
    
    thought_events = {
        'get_recordings_list': handle_get_recordings_list,
        'delete_recording': handle_delete_recording,
        'get_recording_stats': handle_get_stats,
        'get_transcription': handle_get_transcription_ws,
        'transcribe_audio': handle_transcribe_audio_ws,
        'retranscribe_audio': handle_retranscribe_audio_ws
    }
    
    websocket_manager.register_module_events('thought_capture', thought_events)
    logger.info("Événements WebSocket du module Thought Capture enregistrés")


def handle_get_recordings_list(data):
    """Handler WebSocket pour obtenir la liste des enregistrements"""
    from flask_socketio import emit
    
    response = list_audios()
    emit('thought_recordings_list', response.get_json())


def handle_delete_recording(data):
    """Handler WebSocket pour supprimer un enregistrement"""
    from flask_socketio import emit
    
    filename = data.get('filename')
    if filename:
        response = delete_audio(filename)
        emit('thought_recording_deleted', response.get_json())


def handle_get_stats(data):
    """Handler WebSocket pour obtenir les statistiques"""
    from flask_socketio import emit
    
    response = get_stats()
    emit('thought_stats', response.get_json())


def handle_get_transcription_ws(data):
    """Handler WebSocket pour obtenir une transcription"""
    from flask_socketio import emit
    
    filename = data.get('filename')
    if filename:
        response = get_transcription(filename)
        emit('thought_transcription', response.get_json())


def handle_transcribe_audio_ws(data):
    """Handler WebSocket pour transcrire un audio"""
    from flask_socketio import emit
    
    filename = data.get('filename')
    if filename:
        response = transcribe_audio(filename)
        emit('thought_transcription_result', response.get_json())


def handle_retranscribe_audio_ws(data):
    """Handler WebSocket pour re-transcrire un audio"""
    from flask_socketio import emit
    
    filename = data.get('filename')
    if filename:
        response = retranscribe_audio(filename)
        emit('thought_retranscription_result', response.get_json())


# ========================
# FONCTIONS UTILITAIRES
# ========================

def cleanup_old_recordings(days=30):
    """Nettoyer les enregistrements de plus de X jours"""
    import time
    
    try:
        audio_folder_path = os.path.join(current_app.root_path, AUDIO_FOLDER)
        now = time.time()
        deleted_count = 0
        
        for filename in os.listdir(audio_folder_path):
            if filename.endswith('.webm'):
                filepath = os.path.join(audio_folder_path, filename)
                
                # Vérifier l'âge du fichier
                if os.stat(filepath).st_mtime < now - days * 86400:
                    os.remove(filepath)
                    
                    # Supprimer les métadonnées aussi
                    metadata_file = filepath.replace('.webm', '.json')
                    if os.path.exists(metadata_file):
                        os.remove(metadata_file)
                    
                    deleted_count += 1
                    logger.info(f"Ancien enregistrement supprimé: {filename}")
        
        return deleted_count
    
    except Exception as e:
        logger.error(f"Erreur nettoyage: {e}")
        return 0


def get_module_info():
    """Retourner les informations du module"""
    return {
        'id': 'thought_capture',
        'name': 'Capture de Pensée avec Transcription',
        'version': '3.0.0',
        'description': 'Module d\'enregistrement audio avec transcription automatique Whisper Large optimisée',
        'author': 'BioMedical Hub',
        'features': [
            'Enregistrement audio',
            'Transcription automatique avec Whisper Large',
            'Optimisations GPU avec FP16',
            'Nettoyage automatique du texte',
            'Gestion des métadonnées avancées',
            'Re-transcription forcée',
            'Interface moderne deux colonnes'
        ],
        'routes': [
            {'path': '/api/thought-capture/save-audio', 'method': 'POST'},
            {'path': '/api/thought-capture/list-audios', 'method': 'GET'},
            {'path': '/api/thought-capture/delete-audio/<filename>', 'method': 'DELETE'},
            {'path': '/api/thought-capture/stats', 'method': 'GET'},
            {'path': '/api/thought-capture/transcribe/<filename>', 'method': 'POST'},
            {'path': '/api/thought-capture/retranscribe/<filename>', 'method': 'POST'},
            {'path': '/api/thought-capture/get-transcription/<filename>', 'method': 'GET'}
        ],
        'optimization': {
            'model': 'Whisper Large',
            'gpu_acceleration': torch.cuda.is_available(),
            'fp16': torch.cuda.is_available(),
            'temperature': 0,
            'without_timestamps': True,
            'text_cleaning': True
        }
    }