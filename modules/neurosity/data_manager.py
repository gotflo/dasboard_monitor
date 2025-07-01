#!/usr/bin/env python3
"""
DataManager optimisé pour le module Neurosity du Dashboard
Gestion des données CSV avec EEG brut et système de buffer
"""

import csv
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import statistics
import logging

logger = logging.getLogger(__name__)


class DataManager:
    """Gestionnaire de données pour les sessions Neurosity"""
    
    CSV_HEADERS = [
        'timestamp', 'session_duration',
        'calm_probability', 'focus_probability',
        'delta', 'theta', 'alpha', 'beta', 'gamma',
        'eeg_CP3', 'eeg_C3', 'eeg_F5', 'eeg_PO3',
        'eeg_PO4', 'eeg_F6', 'eeg_C4', 'eeg_CP4'
    ]
    
    def __init__(self, data_directory: str = "recordings/neurosity"):
        self.data_directory = Path(data_directory)
        self.current_session = None
        self.csv_file = None
        self.csv_writer = None
        self.session_start_time = None
        
        # Buffer pour stocker temporairement les dernières valeurs
        self.data_buffer = {
            'calm_probability': None,
            'focus_probability': None,
            'brainwaves': {},
            'eeg_raw': {}
        }
        
        # Créer le dossier de données
        self.data_directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"DataManager initialisé - Dossier: {self.data_directory}")
        
        # Statistiques
        self.write_interval = 0  # Compteur pour écrire périodiquement
    
    def start_session(self, session_name: Optional[str] = None) -> str:
        """Démarre une nouvelle session d'enregistrement"""
        # Fermer la session précédente si elle existe
        if self.csv_file and not self.csv_file.closed:
            self.stop_session()
        
        # Générer le nom de session
        if not session_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_name = f"neurosity_session_{timestamp}"
        
        self.current_session = session_name
        csv_filename = self.data_directory / f"{session_name}.csv"
        
        try:
            # Ouvrir le fichier CSV
            self.csv_file = open(csv_filename, 'w', newline='', encoding='utf-8')
            self.csv_writer = csv.DictWriter(
                self.csv_file,
                fieldnames=self.CSV_HEADERS,
                delimiter=';'
            )
            self.csv_writer.writeheader()
            
            self.session_start_time = datetime.now()
            
            # Réinitialiser le buffer
            self.data_buffer = {
                'calm_probability': None,
                'focus_probability': None,
                'brainwaves': {},
                'eeg_raw': {}
            }
            
            logger.info(f"Session démarrée: {csv_filename}")
            return str(csv_filename)
        
        except Exception as e:
            logger.error(f"Erreur démarrage session: {e}")
            self._cleanup()
            raise
    
    def add_data_point(self, data_type: str, data: Dict, metadata: Optional[Dict] = None):
        """Ajoute un point de données au buffer ou écrit une ligne complète"""
        if not self.current_session or not self.csv_writer:
            return
        
        try:
            # Mettre à jour le buffer selon le type de données
            if data_type == 'calm':
                self.data_buffer['calm_probability'] = data.get('probability', 0)
            elif data_type == 'focus':
                self.data_buffer['focus_probability'] = data.get('probability', 0)
            elif data_type == 'brainwaves':
                for wave in ['delta', 'theta', 'alpha', 'beta', 'gamma']:
                    if wave in data:
                        self.data_buffer['brainwaves'][wave] = data[wave]
            elif data_type == 'brainwaves_raw':
                # Traiter les données EEG brutes
                if 'data' in data and isinstance(data['data'], list) and len(data['data']) == 8:
                    channels = ['CP3', 'C3', 'F5', 'PO3', 'PO4', 'F6', 'C4', 'CP4']
                    raw_data = data['data']
                    
                    # Calculer la moyenne pour chaque canal (pour réduire la quantité de données)
                    for i, channel in enumerate(channels):
                        if i < len(raw_data) and isinstance(raw_data[i], list) and raw_data[i]:
                            # Prendre la moyenne des échantillons pour ce canal
                            avg_value = sum(raw_data[i]) / len(raw_data[i])
                            self.data_buffer['eeg_raw'][f'eeg_{channel}'] = round(avg_value, 3)
            
            # Écrire une ligne si nous avons suffisamment de données
            self._write_row_if_ready()
        
        except Exception as e:
            logger.error(f"Erreur ajout données: {e}")
    
    def _write_row_if_ready(self):
        """Écrit une ligne dans le CSV si nous avons des données suffisantes"""
        # Vérifier si nous avons au moins quelques données de base
        if (self.data_buffer['calm_probability'] is not None or
                self.data_buffer['focus_probability'] is not None or
                self.data_buffer['brainwaves'] or
                self.data_buffer['eeg_raw']):
            
            timestamp = datetime.now()
            session_duration = (timestamp - self.session_start_time).total_seconds() if self.session_start_time else 0
            
            # Construire la ligne de données
            row_data = {
                'timestamp': timestamp.isoformat(),
                'session_duration': round(session_duration, 2),
                'calm_probability': self.data_buffer['calm_probability'] or '',
                'focus_probability': self.data_buffer['focus_probability'] or ''
            }
            
            # Ajouter les ondes cérébrales
            for wave in ['delta', 'theta', 'alpha', 'beta', 'gamma']:
                row_data[wave] = round(self.data_buffer['brainwaves'].get(wave, 0), 3) if wave in self.data_buffer[
                    'brainwaves'] else ''
            
            # Ajouter les données EEG brutes
            for channel in ['CP3', 'C3', 'F5', 'PO3', 'PO4', 'F6', 'C4', 'CP4']:
                key = f'eeg_{channel}'
                row_data[key] = self.data_buffer['eeg_raw'].get(key, '')
            
            # Écrire la ligne
            self.csv_writer.writerow(row_data)
            self.csv_file.flush()
            
            # Optionnel : réinitialiser certaines parties du buffer après écriture
            # self.data_buffer['eeg_raw'] = {}  # Décommenter si vous voulez réinitialiser après chaque écriture
    
    def stop_session(self) -> Optional[str]:
        """Arrête la session d'enregistrement en cours"""
        if not self.csv_file:
            return None
        
        csv_path = self.csv_file.name
        
        try:
            self.csv_file.close()
            logger.info(f"Session terminée: {csv_path}")
        except Exception as e:
            logger.error(f"Erreur arrêt session: {e}")
        finally:
            self._cleanup()
        
        return csv_path
    
    def get_session_list(self) -> List[str]:
        """Retourne la liste des sessions disponibles"""
        try:
            csv_files = [
                f.name for f in self.data_directory.glob("*.csv")
                if f.is_file()
            ]
            return sorted(csv_files, reverse=True)
        except Exception as e:
            logger.error(f"Erreur liste sessions: {e}")
            return []
    
    def analyze_session(self, csv_filename: str) -> Dict[str, Any]:
        """Analyse basique d'une session"""
        csv_path = self.data_directory / csv_filename
        
        if not csv_path.exists():
            return {'error': 'Fichier non trouvé'}
        
        try:
            analysis = {
                'filename': csv_filename,
                'total_points': 0,
                'duration': 0,
                'metrics': {},
                'brainwaves': {},
                'eeg_channels': {}
            }
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                rows = list(reader)
                
                if rows:
                    analysis['total_points'] = len(rows)
                    
                    # Durée de la session
                    if rows[-1].get('session_duration'):
                        analysis['duration'] = float(rows[-1]['session_duration'])
                    
                    # Statistiques des métriques
                    for metric in ['calm_probability', 'focus_probability']:
                        values = [
                            float(row[metric])
                            for row in rows
                            if row.get(metric) and row[metric].strip()
                        ]
                        if values:
                            analysis['metrics'][metric] = {
                                'mean': round(statistics.mean(values), 1),
                                'min': round(min(values), 1),
                                'max': round(max(values), 1),
                                'stdev': round(statistics.stdev(values), 1) if len(values) > 1 else 0
                            }
                    
                    # Statistiques des ondes cérébrales
                    for wave in ['delta', 'theta', 'alpha', 'beta', 'gamma']:
                        values = [
                            float(row[wave])
                            for row in rows
                            if row.get(wave) and row[wave].strip()
                        ]
                        if values:
                            analysis['brainwaves'][wave] = {
                                'mean': round(statistics.mean(values), 3),
                                'min': round(min(values), 3),
                                'max': round(max(values), 3)
                            }
                    
                    # Statistiques EEG par canal
                    for channel in ['CP3', 'C3', 'F5', 'PO3', 'PO4', 'F6', 'C4', 'CP4']:
                        key = f'eeg_{channel}'
                        values = [
                            float(row[key])
                            for row in rows
                            if row.get(key) and row[key].strip()
                        ]
                        if values:
                            analysis['eeg_channels'][channel] = {
                                'mean': round(statistics.mean(values), 3),
                                'std': round(statistics.stdev(values), 3) if len(values) > 1 else 0,
                                'min': round(min(values), 3),
                                'max': round(max(values), 3)
                            }
            
            return analysis
        
        except Exception as e:
            logger.error(f"Erreur analyse session: {e}")
            return {'error': str(e)}
    
    def cleanup_old_sessions(self, days_to_keep: int = 30):
        """Supprime les sessions anciennes"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            deleted_count = 0
            
            for csv_file in self.data_directory.glob("*.csv"):
                try:
                    file_time = datetime.fromtimestamp(csv_file.stat().st_mtime)
                    if file_time < cutoff_date:
                        csv_file.unlink()
                        deleted_count += 1
                        logger.info(f"Session supprimée: {csv_file.name}")
                except Exception as e:
                    logger.error(f"Erreur suppression {csv_file.name}: {e}")
            
            if deleted_count > 0:
                logger.info(f"{deleted_count} session(s) supprimée(s)")
        
        except Exception as e:
            logger.error(f"Erreur nettoyage: {e}")
    
    def export_session_to_json(self, csv_filename: str) -> Optional[Dict]:
        """Exporte une session en format JSON"""
        csv_path = self.data_directory / csv_filename
        
        if not csv_path.exists():
            return None
        
        try:
            data = {
                'filename': csv_filename,
                'exported_at': datetime.now().isoformat(),
                'data_points': []
            }
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    # Convertir les valeurs numériques
                    point = {}
                    for key, value in row.items():
                        if value:
                            if key in ['session_duration', 'calm_probability', 'focus_probability',
                                       'delta', 'theta', 'alpha', 'beta', 'gamma'] or key.startswith('eeg_'):
                                try:
                                    point[key] = float(value)
                                except:
                                    point[key] = value
                            else:
                                point[key] = value
                    
                    data['data_points'].append(point)
            
            return data
        
        except Exception as e:
            logger.error(f"Erreur export JSON: {e}")
            return None
    
    def _cleanup(self):
        """Nettoie les ressources"""
        if self.csv_file and not self.csv_file.closed:
            try:
                self.csv_file.close()
            except:
                pass
        
        self.csv_file = None
        self.csv_writer = None
        self.current_session = None
        self.session_start_time = None
        self.data_buffer = {
            'calm_probability': None,
            'focus_probability': None,
            'brainwaves': {},
            'eeg_raw': {}
        }
    
    def get_storage_info(self) -> Dict[str, Any]:
        """Retourne des informations sur l'espace de stockage"""
        try:
            total_size = 0
            file_count = 0
            
            for csv_file in self.data_directory.glob("*.csv"):
                if csv_file.is_file():
                    total_size += csv_file.stat().st_size
                    file_count += 1
            
            return {
                'total_files': file_count,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'directory': str(self.data_directory)
            }
        
        except Exception as e:
            logger.error(f"Erreur info stockage: {e}")
            return {'error': str(e)}