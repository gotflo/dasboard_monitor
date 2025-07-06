#!/usr/bin/env python3
"""
Module Polar - Backend pour capteurs cardiaques Polar H10 et Verity Sense
Gestion des connexions Bluetooth et collecte de données en temps réel
Version optimisée avec CSV une ligne par intervalle RR
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import csv
import zipfile
import io
import threading
from functools import partial
from flask import send_file, jsonify, abort, request, copy_current_request_context
from bleak import BleakScanner

from .collectors.polar_h10_collector import PolarH10Collector
from .collectors.verity_collector import VerityCollector
from .collectors.base_collector import DeviceStatus

logger = logging.getLogger(__name__)


class PolarModule:
    """Module principal pour la gestion des appareils Polar avec CSV optimisé"""
    
    def __init__(self, app, websocket_manager):
        self.app = app
        self.websocket_manager = websocket_manager
        self.is_initialized = False
        
        # Collecteurs pour chaque appareil
        self.collectors = {
            'h10': None,
            'verity': None
        }
        
        # Configuration CSV - Un writer par appareil
        self.csv_writers = {
            'h10': None,
            'verity': None
        }
        self.csv_files = {
            'h10': None,
            'verity': None
        }
        self.csv_recording = False
        self.csv_session_start = None
        self.csv_lines_written = {
            'h10': 0,
            'verity': 0
        }
        
        # Configuration du module
        self.config = {
            'csv_directory': Path('recordings/polar'),
            'csv_delimiter': ';',  # Point-virgule comme délimiteur
            'csv_decimal': '.',  # Point comme séparateur décimal
            'buffer_size': 100,
            'reconnect_attempts': 3,
            'connection_timeout': 30,
            'write_empty_intervals': True  # Écrire les lignes même sans RR
        }
        
        # Créer le dossier pour les enregistrements
        self.config['csv_directory'].mkdir(parents=True, exist_ok=True)
        
        # Statistiques de session
        self.session_stats = {
            'start_time': None,
            'devices_connected': 0,
            'data_points_collected': 0,
            'total_rr_intervals': 0,
            'total_hr_samples': 0
        }
        
        # Buffers pour optimisation écriture
        self.write_buffers = {
            'h10': [],
            'verity': []
        }
        self.max_buffer_size = 50  # Flush tous les 50 enregistrements
        
        logger.info("Module Polar initialisé avec CSV optimisé (une ligne par RR)")
    
    async def scan_for_devices(self, timeout: int = 10) -> List[Dict[str, Any]]:
        """Scan pour trouver les appareils Polar disponibles"""
        try:
            logger.info(f"Démarrage du scan Bluetooth (timeout: {timeout}s)")
            
            # Vérifier si le Bluetooth est disponible
            try:
                test_scanner = BleakScanner()
                await asyncio.wait_for(test_scanner.start(), timeout=1.0)
                await test_scanner.stop()
            except Exception as e:
                logger.warning(f"Bluetooth peut ne pas être disponible: {e}")
            
            # Scanner les appareils BLE avec détection de métadonnées
            discovered_devices = {}
            
            def detection_callback(device, advertisement_data):
                discovered_devices[device.address] = (device, advertisement_data)
            
            scanner = BleakScanner(detection_callback=detection_callback)
            await scanner.start()
            await asyncio.sleep(timeout)
            await scanner.stop()
            
            polar_devices = []
            for address, (device, adv_data) in discovered_devices.items():
                # Filtrer pour ne garder que les appareils Polar
                if device.name and 'Polar' in device.name:
                    device_type = None
                    
                    if 'H10' in device.name:
                        device_type = 'h10'
                    elif 'Verity' in device.name or 'Sense' in device.name:
                        device_type = 'verity'
                    
                    if device_type:
                        rssi = adv_data.rssi if adv_data else -50
                        
                        polar_devices.append({
                            'device_type': device_type,
                            'device_address': device.address,
                            'name': device.name,
                            'rssi': rssi,
                            'signal_quality': self._calculate_signal_quality(rssi)
                        })
                        logger.info(f"Appareil Polar trouvé: {device.name} ({device.address}) RSSI: {rssi}")
            
            # Trier par force du signal
            polar_devices.sort(key=lambda x: x['rssi'], reverse=True)
            
            logger.info(f"Scan terminé: {len(polar_devices)} appareils Polar trouvés")
            return polar_devices
        
        except Exception as e:
            logger.error(f"Erreur scan Bluetooth: {e}")
            return []
    
    def _calculate_signal_quality(self, rssi: int) -> str:
        """Calcule la qualité du signal basée sur le RSSI"""
        if rssi > -50:
            return "excellent"
        elif rssi > -60:
            return "très bon"
        elif rssi > -70:
            return "bon"
        elif rssi > -80:
            return "moyen"
        else:
            return "faible"
    
    async def connect_device(self, device_type: str, device_address: str) -> bool:
        """Connecte à un appareil Polar"""
        try:
            logger.info(f"Tentative de connexion {device_type}: {device_address}")
            
            # Vérifier si déjà connecté
            if self.collectors.get(device_type) and self.collectors[device_type].is_connected:
                logger.warning(f"{device_type} déjà connecté")
                return True
            
            # Créer le collecteur approprié
            if device_type == 'h10':
                collector = PolarH10Collector(device_address)
            elif device_type == 'verity':
                collector = VerityCollector(device_address)
            else:
                raise ValueError(f"Type d'appareil non supporté: {device_type}")
            
            # Ajouter les callbacks
            collector.add_data_callback(lambda data: self._handle_device_data(device_type, data))
            collector.add_status_callback(
                lambda dev_type, status, msg: self._handle_device_status(device_type, status, msg))
            
            # Connecter
            success = await collector.connect()
            
            if success:
                self.collectors[device_type] = collector
                self.session_stats['devices_connected'] += 1
                
                # Démarrer la collecte automatiquement
                await collector.start_data_collection()
                
                # Notifier via WebSocket
                await self._emit_device_connected(device_type, collector)
                
                logger.info(f"✅ {device_type} connecté avec succès")
                return True
            else:
                logger.error(f"❌ Échec connexion {device_type}")
                return False
        
        except Exception as e:
            logger.error(f"Erreur connexion {device_type}: {e}")
            self._emit_error(device_type, str(e))
            return False
    
    async def disconnect_device(self, device_type: str) -> bool:
        """Déconnecte un appareil Polar"""
        try:
            collector = self.collectors.get(device_type)
            if not collector:
                logger.warning(f"Aucun collecteur actif pour {device_type}")
                return False
            
            # Flush les buffers CSV avant déconnexion
            if self.csv_recording:
                self._flush_csv_buffer(device_type)
            
            # Arrêter la collecte et déconnecter
            await collector.disconnect()
            
            # Retirer le collecteur
            self.collectors[device_type] = None
            self.session_stats['devices_connected'] = max(0, self.session_stats['devices_connected'] - 1)
            
            # Notifier via WebSocket
            self._emit_device_disconnected(device_type)
            
            logger.info(f"✅ {device_type} déconnecté")
            return True
        
        except Exception as e:
            logger.error(f"Erreur déconnexion {device_type}: {e}")
            return False
    
    def _handle_device_data(self, device_type: str, data: Dict[str, Any]):
        """Gère les nouvelles données d'un appareil"""
        try:
            # Incrémenter les compteurs
            self.session_stats['data_points_collected'] += 1
            if data.get('heart_rate'):
                self.session_stats['total_hr_samples'] += 1
            if data.get('rr_intervals'):
                self.session_stats['total_rr_intervals'] += len(data['rr_intervals'])
            
            # Récupérer les métriques temps réel si disponibles
            collector = self.collectors.get(device_type)
            if collector:
                metrics = collector.get_real_time_metrics()
                data['real_time_metrics'] = metrics
            
            # Émettre via WebSocket
            self.websocket_manager.emit_to_module('polar', f'{device_type}_data', {
                'device_type': device_type,
                'data': data,
                'timestamp': datetime.now().isoformat()
            })
            
            # Enregistrer en CSV si actif
            if self.csv_recording:
                self._buffer_csv_data(device_type, data)
        
        except Exception as e:
            logger.error(f"Erreur traitement données {device_type}: {e}")
    
    def _handle_device_status(self, device_type: str, status: DeviceStatus, message: str):
        """Gère les changements de statut d'un appareil"""
        try:
            # Émettre via WebSocket
            self.websocket_manager.emit_to_module('polar', f'{device_type}_status', {
                'device_type': device_type,
                'status': status.value,
                'message': message,
                'timestamp': datetime.now().isoformat()
            })
            
            # Actions selon le statut
            if status == DeviceStatus.DISCONNECTED:
                # Flush CSV si enregistrement actif
                if self.csv_recording:
                    self._flush_csv_buffer(device_type)
                
                self.collectors[device_type] = None
                self.session_stats['devices_connected'] = max(0, self.session_stats['devices_connected'] - 1)
            elif status == DeviceStatus.ERROR:
                logger.error(f"Erreur appareil {device_type}: {message}")
        
        except Exception as e:
            logger.error(f"Erreur gestion statut {device_type}: {e}")
    
    async def _emit_device_connected(self, device_type: str, collector):
        """Émet l'événement de connexion avec les infos de l'appareil"""
        try:
            device_info = await collector.get_device_info()
            
            # Convertir toutes les dates en chaînes pour la sérialisation JSON
            if isinstance(device_info, dict):
                serializable_info = {}
                for key, value in device_info.items():
                    if hasattr(value, 'isoformat'):  # datetime object
                        serializable_info[key] = value.isoformat()
                    else:
                        serializable_info[key] = value
            else:
                serializable_info = device_info
            
            self.websocket_manager.emit_to_module('polar', f'{device_type}_connected', {
                'device_type': device_type,
                'device_info': serializable_info,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Erreur émission connexion {device_type}: {e}")
    
    def _emit_device_disconnected(self, device_type: str):
        """Émet l'événement de déconnexion"""
        try:
            self.websocket_manager.emit_to_module('polar', f'{device_type}_disconnected', {
                'device_type': device_type,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Erreur émission déconnexion {device_type}: {e}")
    
    def _emit_error(self, device_type: str, error_message: str):
        """Émet une erreur via WebSocket"""
        try:
            self.websocket_manager.emit_to_module('polar', 'error', {
                'device_type': device_type,
                'error': error_message,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Erreur émission erreur: {e}")
    
    # ===== GESTION CSV OPTIMISÉE =====
    
    def start_csv_recording(self, filename_prefix: Optional[str] = None) -> Dict[str, str]:
        """Démarre l'enregistrement CSV avec format optimisé"""
        if self.csv_recording:
            logger.warning("Enregistrement CSV déjà en cours")
            return {}
        
        try:
            # Générer le préfixe de nom de fichier
            if not filename_prefix:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename_prefix = f"polar_session_{timestamp}"
            
            filenames_created = {}
            
            # Créer un fichier CSV pour chaque capteur connecté
            for device_type, collector in self.collectors.items():
                if collector and collector.is_connected:
                    filename = f"{filename_prefix}_{device_type}.csv"
                    filepath = self.config['csv_directory'] / filename
                    
                    # Ouvrir le fichier
                    self.csv_files[device_type] = open(filepath, 'w', newline='', encoding='utf-8')
                    
                    # Créer le writer avec les en-têtes optimisés
                    fieldnames = [
                        'timestamp',  # Unix timestamp avec millisecondes
                        'heart_rate_bpm',  # Fréquence cardiaque
                        'rr_interval_ms',  # Un seul intervalle RR par ligne
                        'breathing_rate_rpm',  # Fréquence respiratoire RSA
                        'breathing_amplitude',  # Amplitude RSA
                        'breathing_quality',  # Qualité du signal RSA
                        'battery_level'  # Niveau batterie
                    ]
                    
                    self.csv_writers[device_type] = csv.DictWriter(
                        self.csv_files[device_type],
                        fieldnames=fieldnames,
                        delimiter=self.config['csv_delimiter']
                    )
                    self.csv_writers[device_type].writeheader()
                    self.csv_lines_written[device_type] = 0
                    
                    # Initialiser le buffer
                    self.write_buffers[device_type] = []
                    
                    filenames_created[device_type] = filename
                    logger.info(f"📝 Fichier CSV créé pour {device_type}: {filename}")
            
            if not filenames_created:
                logger.warning("Aucun capteur connecté pour l'enregistrement")
                return {}
            
            self.csv_recording = True
            self.csv_session_start = datetime.now()
            self.session_stats['start_time'] = self.csv_session_start
            
            # Notifier via WebSocket
            self.websocket_manager.emit_to_module('polar', 'csv_recording_started', {
                'filenames': filenames_created,
                'timestamp': self.csv_session_start.isoformat()
            })
            
            return filenames_created
        
        except Exception as e:
            logger.error(f"Erreur démarrage CSV: {e}")
            self.csv_recording = False
            return {}
    
    def stop_csv_recording(self) -> Dict[str, Any]:
        """Arrête l'enregistrement CSV"""
        if not self.csv_recording:
            logger.warning("Aucun enregistrement CSV en cours")
            return {}
        
        try:
            # Calculer la durée
            duration = (datetime.now() - self.csv_session_start).total_seconds() if self.csv_session_start else 0
            
            files_info = {}
            total_lines = 0
            
            # Flush et fermer chaque fichier CSV
            for device_type in ['h10', 'verity']:
                if self.csv_files[device_type]:
                    # Flush le buffer restant
                    self._flush_csv_buffer(device_type)
                    
                    # Fermer le fichier
                    self.csv_files[device_type].close()
                    
                    filename = self.csv_files[device_type].name
                    lines = self.csv_lines_written[device_type]
                    
                    files_info[device_type] = {
                        'filename': Path(filename).name,
                        'lines_written': lines,
                        'file_size': Path(filename).stat().st_size if Path(filename).exists() else 0
                    }
                    total_lines += lines
                    
                    # Réinitialiser
                    self.csv_files[device_type] = None
                    self.csv_writers[device_type] = None
                    self.csv_lines_written[device_type] = 0
                    self.write_buffers[device_type] = []
            
            # Statistiques complètes
            stats = {
                'files': files_info,
                'duration': round(duration, 2),
                'total_lines_written': total_lines,
                'total_rr_intervals': self.session_stats['total_rr_intervals'],
                'total_hr_samples': self.session_stats['total_hr_samples'],
                'average_data_rate': round(total_lines / duration, 1) if duration > 0 else 0,
                'timestamp': datetime.now().isoformat()
            }
            
            # Réinitialiser
            self.csv_recording = False
            self.csv_session_start = None
            
            # Notifier via WebSocket
            self.websocket_manager.emit_to_module('polar', 'csv_recording_stopped', stats)
            
            logger.info(f"⏹️ Enregistrement CSV arrêté: {total_lines} lignes, {duration:.1f}s")
            return stats
        
        except Exception as e:
            logger.error(f"Erreur arrêt CSV: {e}")
            return {}
    
    def _buffer_csv_data(self, device_type: str, data: Dict[str, Any]):
        """Ajoute les données au buffer pour écriture optimisée"""
        if not self.csv_writers.get(device_type):
            return
        
        try:
            base_timestamp = datetime.now().timestamp()
            metrics = data.get('real_time_metrics', {})
            
            # Données communes
            breathing_metrics = metrics.get('breathing_metrics', {})
            breathing_rate = round(breathing_metrics['frequency'], 1) if breathing_metrics.get('frequency',
                                                                                               0) > 0 else ''
            breathing_amplitude = round(breathing_metrics['amplitude'], 3) if breathing_metrics.get('frequency',
                                                                                                    0) > 0 else ''
            breathing_quality = breathing_metrics.get('quality', '') if breathing_metrics.get('frequency',
                                                                                              0) > 0 else ''
            
            heart_rate = data.get('heart_rate', '')
            battery_level = data.get('battery_level', '')
            
            # Traiter les intervalles RR
            rr_intervals = data.get('rr_intervals', [])
            
            if rr_intervals:
                # Créer une ligne pour chaque intervalle RR
                for i, rr_interval in enumerate(rr_intervals):
                    # Calculer le timestamp précis de chaque RR
                    rr_timestamp = base_timestamp - (len(rr_intervals) - i - 1) * (rr_interval / 1000.0)
                    
                    row = {
                        'timestamp': round(rr_timestamp, 3),
                        'heart_rate_bpm': heart_rate,
                        'rr_interval_ms': round(rr_interval, 1),
                        'breathing_rate_rpm': breathing_rate,
                        'breathing_amplitude': breathing_amplitude,
                        'breathing_quality': breathing_quality,
                        'battery_level': battery_level
                    }
                    
                    self.write_buffers[device_type].append(row)
            
            elif self.config['write_empty_intervals'] and heart_rate:
                # Si pas d'intervalles RR mais on a un BPM, écrire une ligne
                row = {
                    'timestamp': round(base_timestamp, 3),
                    'heart_rate_bpm': heart_rate,
                    'rr_interval_ms': '',
                    'breathing_rate_rpm': breathing_rate,
                    'breathing_amplitude': breathing_amplitude,
                    'breathing_quality': breathing_quality,
                    'battery_level': battery_level
                }
                
                self.write_buffers[device_type].append(row)
            
            # Vérifier si on doit flush le buffer
            if len(self.write_buffers[device_type]) >= self.max_buffer_size:
                self._flush_csv_buffer(device_type)
        
        except Exception as e:
            logger.error(f"Erreur buffer CSV {device_type}: {e}")
    
    def _flush_csv_buffer(self, device_type: str):
        """Écrit le buffer dans le fichier CSV"""
        if not self.csv_writers.get(device_type) or not self.write_buffers[device_type]:
            return
        
        try:
            # Écrire toutes les lignes du buffer
            for row in self.write_buffers[device_type]:
                self.csv_writers[device_type].writerow(row)
                self.csv_lines_written[device_type] += 1
            
            # Flush le fichier
            self.csv_files[device_type].flush()
            
            # Vider le buffer
            self.write_buffers[device_type] = []
            
            logger.debug(f"Buffer CSV flush pour {device_type}: {self.csv_lines_written[device_type]} lignes totales")
        
        except Exception as e:
            logger.error(f"Erreur flush CSV {device_type}: {e}")
    
    def get_csv_files(self) -> List[Dict[str, Any]]:
        """Retourne la liste des fichiers CSV disponibles"""
        files = []
        
        try:
            for csv_file in self.config['csv_directory'].glob("*.csv"):
                file_stat = csv_file.stat()
                
                # Identifier le type de capteur depuis le nom du fichier
                device_type = 'unknown'
                if '_h10.csv' in csv_file.name:
                    device_type = 'h10'
                elif '_verity.csv' in csv_file.name:
                    device_type = 'verity'
                
                # Analyser rapidement le fichier pour compter les lignes
                line_count = 0
                try:
                    with open(csv_file, 'r', encoding='utf-8') as f:
                        line_count = sum(1 for line in f) - 1  # -1 pour l'en-tête
                except:
                    pass
                
                files.append({
                    'filename': csv_file.name,
                    'device_type': device_type,
                    'size': file_stat.st_size,
                    'size_str': self._format_file_size(file_stat.st_size),
                    'lines': line_count,
                    'created': datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                    'modified': datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                    'duration_estimate': self._estimate_duration(csv_file.name)
                })
            
            # Trier par date de modification (plus récent en premier)
            files.sort(key=lambda x: x['modified'], reverse=True)
        
        except Exception as e:
            logger.error(f"Erreur listing CSV: {e}")
        
        return files
    
    def create_csv_zip(self) -> io.BytesIO:
        """Crée un fichier ZIP contenant tous les CSV"""
        try:
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Parcourir tous les fichiers CSV
                csv_files = list(self.config['csv_directory'].glob("*.csv"))
                
                if not csv_files:
                    logger.warning("Aucun fichier CSV à zipper")
                    return None
                
                for csv_file in csv_files:
                    # Ajouter chaque fichier au ZIP
                    zip_file.write(csv_file, csv_file.name)
                    logger.info(f"Fichier ajouté au ZIP: {csv_file.name}")
                
                # Ajouter un fichier README
                readme_content = self._generate_readme_content()
                zip_file.writestr('README.txt', readme_content)
            
            zip_buffer.seek(0)
            return zip_buffer
        
        except Exception as e:
            logger.error(f"Erreur création ZIP: {e}")
            return None
    
    def _format_file_size(self, size: int) -> str:
        """Formate la taille d'un fichier"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def _estimate_duration(self, filename: str) -> str:
        """Estime la durée d'enregistrement basée sur le nom du fichier"""
        try:
            # Format attendu: polar_session_YYYYMMDD_HHMMSS_device.csv
            parts = filename.split('_')
            if len(parts) >= 4:
                date_str = parts[2]  # YYYYMMDD
                time_str = parts[3]  # HHMMSS
                
                # Extraire aussi de la date de modification du fichier
                filepath = self.config['csv_directory'] / filename
                if filepath.exists():
                    created = datetime.fromtimestamp(filepath.stat().st_ctime)
                    modified = datetime.fromtimestamp(filepath.stat().st_mtime)
                    duration = (modified - created).total_seconds()
                    
                    if duration > 0:
                        hours = int(duration // 3600)
                        minutes = int((duration % 3600) // 60)
                        seconds = int(duration % 60)
                        
                        if hours > 0:
                            return f"{hours}h {minutes}m {seconds}s"
                        elif minutes > 0:
                            return f"{minutes}m {seconds}s"
                        else:
                            return f"{seconds}s"
        except:
            pass
        
        return "N/A"
    
    def _generate_readme_content(self) -> str:
        """Génère le contenu du fichier README pour le ZIP"""
        return f"""Module Polar - BioMedical Hub
============================

Date d'export: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Format des fichiers CSV:
-----------------------
Délimiteur: {self.config['csv_delimiter']}
Encodage: UTF-8

Colonnes:
- timestamp: Timestamp Unix avec millisecondes
- heart_rate_bpm: Fréquence cardiaque en battements par minute
- rr_interval_ms: Intervalle RR en millisecondes (un par ligne)
- breathing_rate_rpm: Fréquence respiratoire RSA en respirations par minute
- breathing_amplitude: Amplitude de la respiration RSA
- breathing_quality: Qualité du signal RSA (excellent/good/fair/poor)
- battery_level: Niveau de batterie du capteur en %

Notes:
------
- Chaque ligne représente un intervalle RR unique
- Les timestamps sont calculés rétrospectivement pour chaque RR
- La respiration est calculée par analyse RSA (Respiratory Sinus Arrhythmia)
- Les fichiers _h10.csv proviennent du Polar H10
- Les fichiers _verity.csv proviennent du Polar Verity Sense

Pour plus d'informations: https://github.com/biomedical-hub
"""
    
    # ===== MÉTHODES D'INFORMATION =====
    
    async def get_devices_status(self) -> Dict[str, Any]:
        """Retourne le statut complet de tous les appareils"""
        status = {
            'h10': None,
            'verity': None,
            'session_stats': self.session_stats.copy(),
            'csv_recording': self.csv_recording,
            'csv_session_duration': None
        }
        
        # Calculer la durée de session CSV si active
        if self.csv_recording and self.csv_session_start:
            status['csv_session_duration'] = (datetime.now() - self.csv_session_start).total_seconds()
        
        for device_type, collector in self.collectors.items():
            if collector:
                try:
                    device_info = await collector.get_device_info()
                    latest_data = await collector.get_latest_data()
                    
                    # Ajouter des métriques de qualité
                    connection_quality = collector.get_connection_quality() if hasattr(collector,
                                                                                       'get_connection_quality') else {}
                    
                    status[device_type] = {
                        'connected': collector.is_connected,
                        'collecting': collector.is_collecting,
                        'device_info': device_info,
                        'latest_data': latest_data,
                        'connection_quality': connection_quality,
                        'data_freshness': collector.is_data_fresh(),
                        'last_update': latest_data.get('last_update') if latest_data else None
                    }
                except Exception as e:
                    logger.error(f"Erreur récupération statut {device_type}: {e}")
        
        return status
    
    async def check_bluetooth_status(self) -> Dict[str, Any]:
        """Vérifie le statut du Bluetooth sur le système"""
        status = {
            'available': False,
            'message': 'Unknown',
            'error': None,
            'platform': self._get_platform_info()
        }
        
        try:
            # Essayer un scan rapide
            scanner = BleakScanner()
            await asyncio.wait_for(scanner.start(), timeout=2.0)
            await scanner.stop()
            
            status['available'] = True
            status['message'] = 'Bluetooth disponible et fonctionnel'
        
        except asyncio.TimeoutError:
            status['available'] = False
            status['message'] = 'Timeout lors du test Bluetooth'
            status['error'] = 'Le Bluetooth met trop de temps à répondre'
        
        except OSError as e:
            error_str = str(e).lower()
            if "could not be started" in error_str:
                status['available'] = False
                status['message'] = 'Adaptateur Bluetooth non trouvé'
                status['error'] = 'Vérifiez que le Bluetooth est activé dans Windows'
            elif "permissions" in error_str:
                status['available'] = False
                status['message'] = 'Permissions insuffisantes'
                status['error'] = 'L\'application nécessite les permissions Bluetooth'
            else:
                status['available'] = False
                status['message'] = f'Erreur système: {str(e)}'
                status['error'] = str(e)
        
        except Exception as e:
            status['available'] = False
            status['message'] = f'Erreur inattendue: {type(e).__name__}'
            status['error'] = str(e)
        
        logger.info(f"Statut Bluetooth: {status}")
        return status
    
    def _get_platform_info(self) -> Dict[str, str]:
        """Récupère les informations de la plateforme"""
        import platform
        return {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine()
        }
    
    def get_csv_status(self) -> Dict[str, Any]:
        """Retourne le statut de l'enregistrement CSV"""
        status = {
            'recording': self.csv_recording,
            'session_start': self.csv_session_start.isoformat() if self.csv_session_start else None,
            'duration': None,
            'files_active': {},
            'lines_written': self.csv_lines_written.copy(),
            'buffer_sizes': {}
        }
        
        if self.csv_recording and self.csv_session_start:
            status['duration'] = (datetime.now() - self.csv_session_start).total_seconds()
        
        for device_type in ['h10', 'verity']:
            if self.csv_files.get(device_type):
                status['files_active'][device_type] = Path(self.csv_files[device_type].name).name
            status['buffer_sizes'][device_type] = len(self.write_buffers.get(device_type, []))
        
        return status
    
    async def cleanup(self):
        """Nettoie toutes les ressources"""
        logger.info("Nettoyage du module Polar...")
        
        # Arrêter l'enregistrement CSV si actif
        if self.csv_recording:
            self.stop_csv_recording()
        
        # Déconnecter tous les appareils
        for device_type, collector in list(self.collectors.items()):
            if collector:
                try:
                    await collector.cleanup()
                except Exception as e:
                    logger.error(f"Erreur nettoyage {device_type}: {e}")
                self.collectors[device_type] = None
        
        # Réinitialiser les statistiques
        self.session_stats = {
            'start_time': None,
            'devices_connected': 0,
            'data_points_collected': 0,
            'total_rr_intervals': 0,
            'total_hr_samples': 0
        }
        
        logger.info("Module Polar nettoyé")


# ===== FONCTIONS D'INITIALISATION =====

def register_polar_websocket_events(websocket_manager, polar_module):
    """Enregistre les événements WebSocket pour le module Polar"""
    
    # Dictionnaire pour stocker les boucles d'événements actives
    active_loops = {}
    
    def handle_scan_devices(data):
        """Lance un scan Bluetooth pour trouver les appareils"""
        
        @copy_current_request_context
        def run_async_scan():
            # Créer une nouvelle boucle d'événements pour ce thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def _scan():
                timeout = data.get('timeout', 10000) / 1000  # Convertir ms en secondes
                max_retries = data.get('max_retries', 3)
                retry_count = 0
                
                websocket_manager.emit_to_module('polar', 'polar_scan_started', {
                    'timestamp': datetime.now().isoformat()
                })
                
                while retry_count < max_retries:
                    # Scanner les appareils
                    devices = await polar_module.scan_for_devices(timeout)
                    
                    if devices:
                        # Appareils trouvés
                        websocket_manager.emit_to_module('polar', 'devices_found', {
                            'devices': devices,
                            'count': len(devices),
                            'timestamp': datetime.now().isoformat()
                        })
                        break
                    else:
                        # Aucun appareil trouvé
                        retry_count += 1
                        
                        if retry_count < max_retries:
                            # Notifier le retry
                            websocket_manager.emit_to_module('polar', 'scan_retry', {
                                'attempt': retry_count,
                                'max_retries': max_retries,
                                'message': f'Aucun appareil trouvé. Nouvelle tentative ({retry_count}/{max_retries})...',
                                'timestamp': datetime.now().isoformat()
                            })
                            
                            # Attendre un peu avant de réessayer
                            await asyncio.sleep(2)
                        else:
                            # Échec après tous les essais
                            websocket_manager.emit_to_module('polar', 'devices_found', {
                                'devices': [],
                                'count': 0,
                                'message': 'Aucun appareil Polar trouvé après plusieurs tentatives',
                                'timestamp': datetime.now().isoformat()
                            })
            
            # Exécuter la coroutine
            loop.run_until_complete(_scan())
            loop.close()
        
        # Lancer dans un thread séparé pour ne pas bloquer
        thread = threading.Thread(target=run_async_scan)
        thread.daemon = True
        thread.start()
    
    def handle_connect_device(data):
        """Connecte à un appareil"""
        
        @copy_current_request_context
        def run_async_connect():
            device_type = data.get('device_type')
            device_address = data.get('device_address')
            
            if not device_type or not device_address:
                websocket_manager.emit_to_module('polar', 'polar_error', {
                    'error': 'Type ou adresse manquant',
                    'timestamp': datetime.now().isoformat()
                })
                return
            
            # Créer une boucle d'événements dédiée pour cette connexion
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Stocker la boucle pour ce device
            device_key = f"{device_type}_{device_address}"
            active_loops[device_key] = loop
            
            async def _connect():
                try:
                    success = await polar_module.connect_device(device_type, device_address)
                    
                    websocket_manager.emit_to_module('polar', 'polar_connect_result', {
                        'device_type': device_type,
                        'success': success,
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    if success:
                        # Garder la boucle active tant que l'appareil est connecté
                        collector = polar_module.collectors.get(device_type)
                        while collector and collector.is_connected:
                            await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Erreur dans la boucle de connexion {device_type}: {e}")
                finally:
                    # Nettoyer la boucle quand terminé
                    if device_key in active_loops:
                        del active_loops[device_key]
            
            try:
                loop.run_until_complete(_connect())
            except Exception as e:
                logger.error(f"Erreur run_until_complete: {e}")
            finally:
                # S'assurer que la boucle est bien fermée
                try:
                    loop.close()
                except Exception as e:
                    logger.warning(f"Erreur fermeture boucle: {e}")
        
        thread = threading.Thread(target=run_async_connect)
        thread.daemon = True
        thread.start()
    
    def handle_disconnect_device(data):
        """Déconnecte un appareil"""
        
        @copy_current_request_context
        def run_async_disconnect():
            device_type = data.get('device_type')
            
            if not device_type:
                return
            
            # Créer une nouvelle boucle temporaire pour la déconnexion
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def _disconnect():
                success = await polar_module.disconnect_device(device_type)
                
                websocket_manager.emit_to_module('polar', 'polar_disconnect_result', {
                    'device_type': device_type,
                    'success': success,
                    'timestamp': datetime.now().isoformat()
                })
            
            loop.run_until_complete(_disconnect())
            loop.close()
        
        thread = threading.Thread(target=run_async_disconnect)
        thread.daemon = True
        thread.start()
    
    def handle_start_csv_recording(data):
        """Démarre l'enregistrement CSV"""
        filename_prefix = data.get('filename_prefix')
        filenames = polar_module.start_csv_recording(filename_prefix)
        
        # La notification est déjà gérée dans start_csv_recording
    
    def handle_stop_csv_recording(data):
        """Arrête l'enregistrement CSV"""
        stats = polar_module.stop_csv_recording()
        
        # La notification est déjà gérée dans stop_csv_recording
    
    def handle_get_csv_files(data):
        """Récupère la liste des fichiers CSV"""
        files = polar_module.get_csv_files()
        
        websocket_manager.emit_to_module('polar', 'polar_csv_files', {
            'files': files,
            'count': len(files),
            'timestamp': datetime.now().isoformat()
        })
    
    def handle_get_csv_status(data):
        """Récupère le statut de l'enregistrement CSV"""
        status = polar_module.get_csv_status()
        
        websocket_manager.emit_to_module('polar', 'polar_csv_status', status)
    
    def handle_get_status(data):
        """Récupère le statut des appareils"""
        
        @copy_current_request_context
        def run_async_status():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def _get_status():
                status = await polar_module.get_devices_status()
                websocket_manager.emit_to_module('polar', 'polar_status', status)
            
            loop.run_until_complete(_get_status())
            loop.close()
        
        thread = threading.Thread(target=run_async_status)
        thread.daemon = True
        thread.start()
    
    def handle_get_hrv_data(data):
        """Gère la demande de données HRV"""
        
        @copy_current_request_context
        def run_async_hrv():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def _get_hrv():
                status = await polar_module.get_devices_status()
                hrv_data = {
                    'h10': None,
                    'verity': None,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Extraire les données HRV de chaque appareil
                for device_type in ['h10', 'verity']:
                    if status.get(device_type) and status[device_type].get('latest_data'):
                        latest_data = status[device_type]['latest_data']
                        metrics = latest_data.get('real_time_metrics', {})
                        
                        hrv_data[device_type] = {
                            'connected': status[device_type].get('connected', False),
                            'heart_rate': latest_data.get('heart_rate', 0),
                            'rmssd': metrics.get('rr_metrics', {}).get('rmssd', 0),
                            'mean_rr': metrics.get('rr_metrics', {}).get('mean_rr', 0),
                            'hrv_score': metrics.get('rr_metrics', {}).get('rmssd', 0) * 0.8,  # Score simplifié
                            'breathing_rate': metrics.get('breathing_metrics', {}).get('frequency', 0)
                        }
                
                websocket_manager.emit_to_module('polar', 'polar_hrv_data', hrv_data)
            
            loop.run_until_complete(_get_hrv())
            loop.close()
        
        thread = threading.Thread(target=run_async_hrv)
        thread.daemon = True
        thread.start()
    
    def handle_check_bluetooth(data):
        """Vérifie le statut du Bluetooth"""
        
        @copy_current_request_context
        def run_async_check():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def _check():
                status = await polar_module.check_bluetooth_status()
                websocket_manager.emit_to_module('polar', 'bluetooth_status', status)
            
            loop.run_until_complete(_check())
            loop.close()
        
        thread = threading.Thread(target=run_async_check)
        thread.daemon = True
        thread.start()
    
    # Enregistrer les événements
    polar_events = {
        'scan_devices': handle_scan_devices,
        'connect_device': handle_connect_device,
        'disconnect_device': handle_disconnect_device,
        'start_csv_recording': handle_start_csv_recording,
        'stop_csv_recording': handle_stop_csv_recording,
        'get_csv_files': handle_get_csv_files,
        'get_csv_status': handle_get_csv_status,
        'get_status': handle_get_status,
        'get_hrv_data': handle_get_hrv_data,
        'check_bluetooth': handle_check_bluetooth
    }
    
    websocket_manager.register_module_events('polar', polar_events)
    logger.info("Événements WebSocket du module Polar enregistrés")


def init_polar_module(app, websocket_manager):
    """Initialise le module Polar"""
    polar_module = PolarModule(app, websocket_manager)
    
    # ===== ROUTES API =====
    
    @app.route('/api/polar/status')
    def get_polar_status():
        """Récupère le statut complet du module Polar"""
        try:
            # Créer une coroutine et l'exécuter
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            status = loop.run_until_complete(polar_module.get_devices_status())
            return jsonify(status)
        except Exception as e:
            logger.error(f"Erreur récupération statut: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/polar/scan', methods=['POST'])
    def scan_polar_devices():
        """Lance un scan Bluetooth pour trouver les appareils Polar"""
        try:
            timeout = request.json.get('timeout', 10) if request.json else 10
            
            # Exécuter la coroutine
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            devices = loop.run_until_complete(polar_module.scan_for_devices(timeout))
            
            return jsonify({
                'devices': devices,
                'count': len(devices),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Erreur scan: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/polar/connect', methods=['POST'])
    def connect_polar_device():
        """Connecte à un appareil Polar spécifique"""
        try:
            data = request.json
            device_type = data.get('device_type')
            device_address = data.get('device_address')
            
            if not device_type or not device_address:
                return jsonify({'error': 'Type ou adresse manquant'}), 400
            
            # Exécuter la coroutine
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(polar_module.connect_device(device_type, device_address))
            
            return jsonify({
                'success': success,
                'device_type': device_type,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Erreur connexion: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/polar/disconnect/<device_type>', methods=['POST'])
    def disconnect_polar_device(device_type):
        """Déconnecte un appareil Polar"""
        try:
            # Exécuter la coroutine
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(polar_module.disconnect_device(device_type))
            
            return jsonify({
                'success': success,
                'device_type': device_type,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Erreur déconnexion: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/polar/csv/start', methods=['POST'])
    def start_csv_recording():
        """Démarre l'enregistrement CSV"""
        try:
            filename_prefix = request.json.get('filename_prefix') if request.json else None
            filenames = polar_module.start_csv_recording(filename_prefix)
            return jsonify({
                'success': bool(filenames),
                'filenames': filenames,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Erreur démarrage CSV: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/polar/csv/stop', methods=['POST'])
    def stop_csv_recording():
        """Arrête l'enregistrement CSV"""
        try:
            stats = polar_module.stop_csv_recording()
            return jsonify(stats)
        except Exception as e:
            logger.error(f"Erreur arrêt CSV: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/polar/csv/status')
    def get_csv_status():
        """Récupère le statut de l'enregistrement CSV"""
        try:
            status = polar_module.get_csv_status()
            return jsonify(status)
        except Exception as e:
            logger.error(f"Erreur récupération statut CSV: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/polar/csv/list')
    def list_csv_files():
        """Liste tous les fichiers CSV disponibles"""
        try:
            files = polar_module.get_csv_files()
            return jsonify({
                'files': files,
                'count': len(files),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Erreur listing CSV: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/polar/csv/<filename>')
    def download_polar_csv(filename):
        """Télécharge un fichier CSV spécifique"""
        try:
            # Vérifier que le nom de fichier est sûr (éviter path traversal)
            if '..' in filename or '/' in filename or '\\' in filename:
                abort(400)
            
            filepath = polar_module.config['csv_directory'] / filename
            
            if not filepath.exists():
                abort(404)
            
            return send_file(
                filepath,
                as_attachment=True,
                download_name=filename,
                mimetype='text/csv'
            )
        except Exception as e:
            logger.error(f"Erreur téléchargement CSV: {e}")
            abort(500)
    
    @app.route('/api/polar/csv/download-all')
    def download_all_polar_csv():
        """Télécharge tous les fichiers CSV dans un ZIP"""
        try:
            # Créer le ZIP
            zip_buffer = polar_module.create_csv_zip()
            
            if not zip_buffer:
                return jsonify({'error': 'Aucun fichier CSV disponible'}), 404
            
            # Générer le nom du fichier
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"polar_sessions_{timestamp}.zip"
            
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=filename
            )
        except Exception as e:
            logger.error(f"Erreur téléchargement ZIP: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/polar/bluetooth/status')
    def check_bluetooth_status():
        """Vérifie le statut du Bluetooth"""
        try:
            # Exécuter la coroutine
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            status = loop.run_until_complete(polar_module.check_bluetooth_status())
            return jsonify(status)
        except Exception as e:
            logger.error(f"Erreur vérification Bluetooth: {e}")
            return jsonify({
                'available': False,
                'message': 'Erreur lors de la vérification',
                'error': str(e)
            }), 500
    
    logger.info("Routes API du module Polar enregistrées")
    
    return polar_module