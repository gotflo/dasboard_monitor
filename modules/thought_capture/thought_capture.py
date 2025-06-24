#!/usr/bin/env python3
"""
Module Thought Capture - Routes et logique backend
"""

from flask import Blueprint, request, jsonify, current_app
import os
from datetime import datetime
import logging

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


def init_module(app):
    """Initialiser le module avec l'application Flask"""
    # Créer le dossier pour stocker les audios
    audio_path = os.path.join(app.root_path, AUDIO_FOLDER)
    os.makedirs(audio_path, exist_ok=True)
    
    logger.info(f"Module Thought Capture initialisé - Dossier audio: {audio_path}")
    
    # Enregistrer le blueprint
    app.register_blueprint(thought_capture_bp)
    
    # Ajouter la configuration au registre des modules si disponible
    if hasattr(app, 'module_registry'):
        app.module_registry.update_module_config('thought_capture', {
            'audio_folder': AUDIO_FOLDER,
            'max_file_size': 50 * 1024 * 1024,  # 50 MB
            'allowed_formats': ['webm', 'mp3', 'wav', 'ogg']
        })


# ========================
# ROUTES DU MODULE
# ========================

@thought_capture_bp.route('/save-audio', methods=['POST'])
def save_audio():
    """Sauvegarder un fichier audio"""
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
        
        # Optionnel : sauvegarder les métadonnées
        metadata_file = filepath.replace('.webm', '.json')
        metadata = {
            'filename': filename,
            'timestamp': timestamp,
            'date': datetime.now().isoformat(),
            'duration': int(duration),
            'size': os.path.getsize(filepath)
        }
        
        import json
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        
        # Retourner l'URL pour accéder au fichier
        file_url = f"/{AUDIO_FOLDER}/{filename}"
        
        logger.info(f"Audio sauvegardé: {filename}")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'url': file_url,
            'timestamp': timestamp,
            'duration': duration
        })
    
    except Exception as e:
        logger.error(f"Erreur sauvegarde audio: {e}")
        return jsonify({'error': str(e)}), 500


@thought_capture_bp.route('/list-audios', methods=['GET'])
def list_audios():
    """Lister tous les fichiers audio"""
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
                    if os.path.exists(metadata_file):
                        import json
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            duration = metadata.get('duration', 0)
                    else:
                        duration = 0
                    
                    files.append({
                        'filename': filename,
                        'url': f"/{AUDIO_FOLDER}/{filename}",
                        'size': os.path.getsize(filepath),
                        'timestamp': timestamp,
                        'duration': duration
                    })
        
        # Trier par date (plus récent en premier)
        files.sort(key=lambda x: x['timestamp'], reverse=True)
        
        logger.info(f"{len(files)} fichiers audio trouvés")
        
        return jsonify({
            'files': files,
            'total': len(files)
        })
    
    except Exception as e:
        logger.error(f"Erreur listing audio: {e}")
        return jsonify({'error': str(e)}), 500


@thought_capture_bp.route('/delete-audio/<filename>', methods=['DELETE'])
def delete_audio(filename):
    """Supprimer un fichier audio"""
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
        
        if os.path.exists(audio_folder_path):
            for filename in os.listdir(audio_folder_path):
                if filename.endswith('.webm'):
                    filepath = os.path.join(audio_folder_path, filename)
                    total_files += 1
                    total_size += os.path.getsize(filepath)
                    
                    # Lire la durée depuis les métadonnées
                    metadata_file = filepath.replace('.webm', '.json')
                    if os.path.exists(metadata_file):
                        import json
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            total_duration += metadata.get('duration', 0)
        
        return jsonify({
            'total_recordings': total_files,
            'total_size': total_size,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'total_duration': total_duration,
            'average_duration': round(total_duration / total_files, 2) if total_files > 0 else 0
        })
    
    except Exception as e:
        logger.error(f"Erreur stats: {e}")
        return jsonify({'error': str(e)}), 500


# ========================
# ÉVÉNEMENTS WEBSOCKET (si utilisé)
# ========================

def register_websocket_events(websocket_manager):
    """Enregistrer les événements WebSocket pour ce module"""
    
    thought_events = {
        'get_recordings_list': handle_get_recordings_list,
        'delete_recording': handle_delete_recording,
        'get_recording_stats': handle_get_stats
    }
    
    websocket_manager.register_module_events('thought_capture', thought_events)
    logger.info("Événements WebSocket du module Thought Capture enregistrés")


def handle_get_recordings_list(data):
    """Handler WebSocket pour obtenir la liste des enregistrements"""
    from flask_socketio import emit
    
    # Utiliser la même logique que la route REST
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
        'name': 'Capture de Pensée',
        'version': '1.0.0',
        'description': 'Module d\'enregistrement audio pour capture de pensées',
        'author': 'BioMedical Hub',
        'routes': [
            {'path': '/api/thought_capture-capture/save-audio', 'method': 'POST'},
            {'path': '/api/thought_capture-capture/list-audios', 'method': 'GET'},
            {'path': '/api/thought_capture-capture/delete-audio/<filename>', 'method': 'DELETE'},
            {'path': '/api/thought_capture-capture/stats', 'method': 'GET'}
        ]
    }