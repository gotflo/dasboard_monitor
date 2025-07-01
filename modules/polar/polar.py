#!/usr/bin/env python3
"""
Module Polar - Backend pour capteurs cardiaques Polar H10 et Verity Sense
Gestion des connexions Bluetooth et collecte de données en temps réel
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
    """Module principal pour la gestion des appareils Polar"""
    
    def __init__(self, app, websocket_manager):
        self.app = app
        self.websocket_manager = websocket_manager
        self.is_initialized = False
        
        # Collecteurs pour chaque appareil
        self.collectors = {
            'h10': None,
            'verity': None
        }
        
        # Configuration CSV
        self.csv_writer = None
        self.csv_file = None
        self.csv_recording = False
        self.csv_session_start = None
        self.csv_data_buffer = {
            'h10': {},
            'verity': {}
        }
        
        # Configuration du module
        self.config = {
            'csv_directory': Path('recordings/polar'),
            'csv_delimiter': ';',
            'buffer_size': 100,
            'reconnect_attempts': 3,
            'connection_timeout': 30
        }
        
        # Créer le dossier pour les enregistrements
        self.config['csv_directory'].mkdir(parents=True, exist_ok=True)
        
        # Statistiques de session
        self.session_stats = {
            'start_time': None,
            'devices_connected': 0,
            'data_points_collected': 0,
            'csv_lines_written': 0
        }
        
        logger.info("Module Polar initialisé")
    
    async def scan_for_devices(self, timeout: int = 10) -> List[Dict[str, Any]]:
        """Scan pour trouver les appareils Polar disponibles"""
        try:
            logger.info(f"Démarrage du scan Bluetooth (timeout: {timeout}s)")
            
            # Vérifier si le Bluetooth est disponible
            try:
                # Test rapide pour voir si BleakScanner fonctionne
                test_scanner = BleakScanner()
                await asyncio.wait_for(test_scanner.start(), timeout=1.0)
                await test_scanner.stop()
            except Exception as e:
                logger.warning(f"Bluetooth peut ne pas être disponible: {e}")
                # Continuer quand même le scan
            
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
                        # Utiliser le RSSI de advertisement_data
                        rssi = adv_data.rssi if adv_data else -50
                        
                        polar_devices.append({
                            'device_type': device_type,
                            'device_address': device.address,
                            'name': device.name,
                            'rssi': rssi
                        })
                        logger.info(f"Appareil Polar trouvé: {device.name} ({device.address})")
            
            logger.info(
                f"Scan terminé: {len(polar_devices)} appareils Polar trouvés sur {len(discovered_devices)} appareils BLE détectés")
            return polar_devices
        
        except Exception as e:
            logger.error(f"Erreur scan Bluetooth: {e}")
            # Retourner une liste vide plutôt qu'une erreur
            return []
    
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
            # Incrémenter le compteur
            self.session_stats['data_points_collected'] += 1
            
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
    
    # ===== GESTION CSV =====
    
    def start_csv_recording(self, filename: Optional[str] = None) -> str:
        """Démarre l'enregistrement CSV"""
        if self.csv_recording:
            logger.warning("Enregistrement CSV déjà en cours")
            return self.csv_file.name if self.csv_file else ""
        
        try:
            # Générer le nom de fichier
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"polar_session_{timestamp}.csv"
            
            filepath = self.config['csv_directory'] / filename
            
            # Ouvrir le fichier
            self.csv_file = open(filepath, 'w', newline='', encoding='utf-8')
            
            # Créer les en-têtes
            fieldnames = self._generate_csv_headers()
            self.csv_writer = csv.DictWriter(
                self.csv_file,
                fieldnames=fieldnames,
                delimiter=self.config['csv_delimiter']
            )
            self.csv_writer.writeheader()
            
            self.csv_recording = True
            self.csv_session_start = datetime.now()
            self.session_stats['start_time'] = self.csv_session_start
            
            # Notifier via WebSocket
            self.websocket_manager.emit_to_module('polar', 'csv_recording_started', {
                'filename': filename,
                'timestamp': self.csv_session_start.isoformat()
            })
            
            logger.info(f"📝 Enregistrement CSV démarré: {filename}")
            return str(filepath)
        
        except Exception as e:
            logger.error(f"Erreur démarrage CSV: {e}")
            self.csv_recording = False
            return ""
    
    def stop_csv_recording(self) -> Dict[str, Any]:
        """Arrête l'enregistrement CSV"""
        if not self.csv_recording:
            logger.warning("Aucun enregistrement CSV en cours")
            return {}
        
        try:
            # Écrire les dernières données du buffer
            self._flush_csv_buffer()
            
            # Fermer le fichier
            if self.csv_file:
                self.csv_file.close()
            
            # Calculer les statistiques
            duration = (datetime.now() - self.csv_session_start).total_seconds() if self.csv_session_start else 0
            stats = {
                'filename': self.csv_file.name if self.csv_file else "",
                'duration': duration,
                'lines_written': self.session_stats['csv_lines_written'],
                'timestamp': datetime.now().isoformat()
            }
            
            # Réinitialiser
            self.csv_recording = False
            self.csv_file = None
            self.csv_writer = None
            self.csv_session_start = None
            self.session_stats['csv_lines_written'] = 0
            
            # Notifier via WebSocket
            self.websocket_manager.emit_to_module('polar', 'csv_recording_stopped', stats)
            
            logger.info(f"⏹️ Enregistrement CSV arrêté: {stats['lines_written']} lignes")
            return stats
        
        except Exception as e:
            logger.error(f"Erreur arrêt CSV: {e}")
            return {}
    
    def _generate_csv_headers(self) -> List[str]:
        """Génère les en-têtes CSV"""
        headers = ['timestamp', 'session_duration']
        
        # Headers pour H10
        headers.extend([
            'h10_connected', 'h10_heart_rate', 'h10_last_rr', 'h10_mean_rr',
            'h10_rmssd', 'h10_mean_bpm', 'h10_min_bpm', 'h10_max_bpm',
            'h10_breathing_freq', 'h10_breathing_amp', 'h10_breathing_quality',
            'h10_battery'
        ])
        
        # Headers pour Verity
        headers.extend([
            'verity_connected', 'verity_heart_rate', 'verity_last_rr', 'verity_mean_rr',
            'verity_rmssd', 'verity_mean_bpm', 'verity_min_bpm', 'verity_max_bpm',
            'verity_breathing_freq', 'verity_breathing_amp', 'verity_breathing_quality',
            'verity_battery'
        ])
        
        return headers
    
    def _buffer_csv_data(self, device_type: str, data: Dict[str, Any]):
        """Met en buffer les données pour l'écriture CSV"""
        try:
            # Extraire les métriques pertinentes
            metrics = data.get('real_time_metrics', {})
            
            self.csv_data_buffer[device_type] = {
                'connected': True,
                'heart_rate': data.get('heart_rate', 0),
                'battery': data.get('battery_level', 0),
                'last_rr': metrics.get('rr_metrics', {}).get('last_rr', 0),
                'mean_rr': metrics.get('rr_metrics', {}).get('mean_rr', 0),
                'rmssd': metrics.get('rr_metrics', {}).get('rmssd', 0),
                'mean_bpm': metrics.get('bpm_metrics', {}).get('mean_bpm', 0),
                'min_bpm': metrics.get('bpm_metrics', {}).get('min_bpm', 0),
                'max_bpm': metrics.get('bpm_metrics', {}).get('max_bpm', 0),
                'breathing_freq': metrics.get('breathing_metrics', {}).get('frequency', 0),
                'breathing_amp': metrics.get('breathing_metrics', {}).get('amplitude', 0),
                'breathing_quality': metrics.get('breathing_metrics', {}).get('quality', 'unknown')
            }
            
            # Écrire périodiquement
            if len(self.csv_data_buffer['h10']) > 0 or len(self.csv_data_buffer['verity']) > 0:
                self._write_csv_row()
        
        except Exception as e:
            logger.error(f"Erreur buffer CSV: {e}")
    
    def _write_csv_row(self):
        """Écrit une ligne dans le fichier CSV"""
        if not self.csv_writer:
            return
        
        try:
            timestamp = datetime.now()
            duration = (timestamp - self.csv_session_start).total_seconds() if self.csv_session_start else 0
            
            row = {
                'timestamp': timestamp.isoformat(),
                'session_duration': round(duration, 2)
            }
            
            # Données H10
            h10_data = self.csv_data_buffer.get('h10', {})
            if h10_data:
                row.update({
                    'h10_connected': h10_data.get('connected', False),
                    'h10_heart_rate': h10_data.get('heart_rate', 0),
                    'h10_last_rr': h10_data.get('last_rr', 0),
                    'h10_mean_rr': h10_data.get('mean_rr', 0),
                    'h10_rmssd': h10_data.get('rmssd', 0),
                    'h10_mean_bpm': h10_data.get('mean_bpm', 0),
                    'h10_min_bpm': h10_data.get('min_bpm', 0),
                    'h10_max_bpm': h10_data.get('max_bpm', 0),
                    'h10_breathing_freq': h10_data.get('breathing_freq', 0),
                    'h10_breathing_amp': h10_data.get('breathing_amp', 0),
                    'h10_breathing_quality': h10_data.get('breathing_quality', 'unknown'),
                    'h10_battery': h10_data.get('battery', 0)
                })
            else:
                row.update({f'h10_{key}': 0 for key in ['connected', 'heart_rate', 'last_rr', 'mean_rr',
                                                        'rmssd', 'mean_bpm', 'min_bpm', 'max_bpm', 'breathing_freq',
                                                        'breathing_amp', 'battery']})
                row['h10_breathing_quality'] = 'unknown'
            
            # Données Verity
            verity_data = self.csv_data_buffer.get('verity', {})
            if verity_data:
                row.update({
                    'verity_connected': verity_data.get('connected', False),
                    'verity_heart_rate': verity_data.get('heart_rate', 0),
                    'verity_last_rr': verity_data.get('last_rr', 0),
                    'verity_mean_rr': verity_data.get('mean_rr', 0),
                    'verity_rmssd': verity_data.get('rmssd', 0),
                    'verity_mean_bpm': verity_data.get('mean_bpm', 0),
                    'verity_min_bpm': verity_data.get('min_bpm', 0),
                    'verity_max_bpm': verity_data.get('max_bpm', 0),
                    'verity_breathing_freq': verity_data.get('breathing_freq', 0),
                    'verity_breathing_amp': verity_data.get('breathing_amp', 0),
                    'verity_breathing_quality': verity_data.get('breathing_quality', 'unknown'),
                    'verity_battery': verity_data.get('battery', 0)
                })
            else:
                row.update({f'verity_{key}': 0 for key in ['connected', 'heart_rate', 'last_rr', 'mean_rr',
                                                           'rmssd', 'mean_bpm', 'min_bpm', 'max_bpm', 'breathing_freq',
                                                           'breathing_amp', 'battery']})
                row['verity_breathing_quality'] = 'unknown'
            
            self.csv_writer.writerow(row)
            self.csv_file.flush()
            self.session_stats['csv_lines_written'] += 1
        
        except Exception as e:
            logger.error(f"Erreur écriture CSV: {e}")
    
    def _flush_csv_buffer(self):
        """Vide le buffer CSV"""
        if self.csv_writer and (self.csv_data_buffer['h10'] or self.csv_data_buffer['verity']):
            self._write_csv_row()
    
    def get_csv_files(self) -> List[Dict[str, Any]]:
        """Retourne la liste des fichiers CSV disponibles"""
        files = []
        
        try:
            for csv_file in self.config['csv_directory'].glob("*.csv"):
                file_stat = csv_file.stat()
                files.append({
                    'filename': csv_file.name,
                    'size': file_stat.st_size,
                    'size_str': self._format_file_size(file_stat.st_size),
                    'created': datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                    'modified': datetime.fromtimestamp(file_stat.st_mtime).isoformat()
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
                for csv_file in self.config['csv_directory'].glob("*.csv"):
                    # Ajouter chaque fichier au ZIP
                    zip_file.write(csv_file, csv_file.name)
                    logger.info(f"Fichier ajouté au ZIP: {csv_file.name}")
            
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
    
    # ===== MÉTHODES D'INFORMATION =====
    
    async def get_devices_status(self) -> Dict[str, Any]:
        """Retourne le statut de tous les appareils"""
        status = {
            'h10': None,
            'verity': None,
            'session_stats': self.session_stats.copy(),
            'csv_recording': self.csv_recording
        }
        
        for device_type, collector in self.collectors.items():
            if collector:
                try:
                    device_info = await collector.get_device_info()
                    latest_data = await collector.get_latest_data()
                    
                    status[device_type] = {
                        'connected': collector.is_connected,
                        'collecting': collector.is_collecting,
                        'device_info': device_info,
                        'latest_data': latest_data,
                        'connection_quality': collector.is_data_fresh()
                    }
                except Exception as e:
                    logger.error(f"Erreur récupération statut {device_type}: {e}")
        
        return status
    
    async def check_bluetooth_status(self) -> Dict[str, Any]:
        """Vérifie le statut du Bluetooth sur le système"""
        status = {
            'available': False,
            'message': 'Unknown',
            'error': None
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
            if "could not be started" in str(e).lower():
                status['available'] = False
                status['message'] = 'Adaptateur Bluetooth non trouvé'
                status['error'] = 'Vérifiez que le Bluetooth est activé dans Windows'
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
    
    async def cleanup(self):
        """Nettoie toutes les ressources"""
        logger.info("Nettoyage du module Polar...")
        
        # Arrêter l'enregistrement CSV
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
        filename = data.get('filename')
        filepath = polar_module.start_csv_recording(filename)
        
        websocket_manager.emit_to_module('polar', 'polar_csv_started', {
            'filepath': filepath,
            'timestamp': datetime.now().isoformat()
        })
    
    def handle_stop_csv_recording(data):
        """Arrête l'enregistrement CSV"""
        stats = polar_module.stop_csv_recording()
        
        websocket_manager.emit_to_module('polar', 'polar_csv_stopped', stats)
    
    def handle_get_csv_files(data):
        """Récupère la liste des fichiers CSV"""
        files = polar_module.get_csv_files()
        
        websocket_manager.emit_to_module('polar', 'polar_csv_files', {
            'files': files,
            'timestamp': datetime.now().isoformat()
        })
    
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
                            'hrv_score': metrics.get('rr_metrics', {}).get('rmssd', 0) * 0.8  # Score simplifié
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
        'get_status': handle_get_status,
        'get_hrv_data': handle_get_hrv_data,  # Ajout pour compatibilité
        'check_bluetooth': handle_check_bluetooth  # Nouveau handler
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
            filename = request.json.get('filename') if request.json else None
            filepath = polar_module.start_csv_recording(filename)
            return jsonify({
                'success': bool(filepath),
                'filepath': filepath,
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
                return jsonify({'error': 'Erreur création ZIP'}), 500
            
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
    
    @app.route('/api/polar/sessions')
    def get_polar_sessions():
        """Récupère la liste des sessions enregistrées avec statistiques"""
        try:
            files = polar_module.get_csv_files()
            
            # Analyser chaque fichier pour obtenir des stats
            sessions = []
            for file_info in files:
                try:
                    filepath = polar_module.config['csv_directory'] / file_info['filename']
                    
                    # Lire quelques lignes pour obtenir des stats basiques
                    with open(filepath, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f, delimiter=polar_module.config['csv_delimiter'])
                        rows = list(reader)
                        
                        if rows:
                            # Calculer la durée
                            first_row = rows[0]
                            last_row = rows[-1]
                            duration = float(last_row.get('session_duration', 0))
                            
                            # Déterminer les appareils utilisés
                            devices_used = []
                            if any(float(row.get('h10_heart_rate', 0)) > 0 for row in rows[:10]):
                                devices_used.append('h10')
                            if any(float(row.get('verity_heart_rate', 0)) > 0 for row in rows[:10]):
                                devices_used.append('verity')
                            
                            session_info = {
                                **file_info,
                                'duration': duration,
                                'duration_str': f"{int(duration // 60)}m {int(duration % 60)}s",
                                'data_points': len(rows),
                                'devices_used': devices_used,
                                'start_time': first_row.get('timestamp', ''),
                                'end_time': last_row.get('timestamp', '')
                            }
                            
                            sessions.append(session_info)
                except Exception as e:
                    logger.warning(f"Impossible d'analyser {file_info['filename']}: {e}")
                    sessions.append(file_info)
            
            return jsonify({
                'sessions': sessions,
                'count': len(sessions),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Erreur récupération sessions: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/polar/sessions/<filename>/analyze')
    def analyze_polar_session(filename):
        """Analyse une session CSV et retourne des statistiques détaillées"""
        try:
            filepath = polar_module.config['csv_directory'] / filename
            
            if not filepath.exists():
                abort(404)
            
            # Lire et analyser le fichier CSV
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=polar_module.config['csv_delimiter'])
                rows = list(reader)
            
            if not rows:
                return jsonify({'error': 'Fichier CSV vide'}), 400
            
            # Analyser les données
            analysis = {
                'filename': filename,
                'total_data_points': len(rows),
                'h10': {
                    'connected': False,
                    'heart_rate': {'min': None, 'max': None, 'mean': None},
                    'rr_intervals': {'mean': None, 'rmssd': None},
                    'breathing': {'mean_freq': None}
                },
                'verity': {
                    'connected': False,
                    'heart_rate': {'min': None, 'max': None, 'mean': None},
                    'rr_intervals': {'mean': None, 'rmssd': None},
                    'breathing': {'mean_freq': None}
                }
            }
            
            # Analyser H10
            h10_hrs = [float(row['h10_heart_rate']) for row in rows if float(row.get('h10_heart_rate', 0)) > 0]
            if h10_hrs:
                analysis['h10']['connected'] = True
                analysis['h10']['heart_rate'] = {
                    'min': min(h10_hrs),
                    'max': max(h10_hrs),
                    'mean': sum(h10_hrs) / len(h10_hrs)
                }
                
                # RR et respiration
                h10_rmssd = [float(row['h10_rmssd']) for row in rows if float(row.get('h10_rmssd', 0)) > 0]
                if h10_rmssd:
                    analysis['h10']['rr_intervals']['rmssd'] = sum(h10_rmssd) / len(h10_rmssd)
                
                h10_breathing = [float(row['h10_breathing_freq']) for row in rows if
                                 float(row.get('h10_breathing_freq', 0)) > 0]
                if h10_breathing:
                    analysis['h10']['breathing']['mean_freq'] = sum(h10_breathing) / len(h10_breathing)
            
            # Analyser Verity (similaire)
            verity_hrs = [float(row['verity_heart_rate']) for row in rows if float(row.get('verity_heart_rate', 0)) > 0]
            if verity_hrs:
                analysis['verity']['connected'] = True
                analysis['verity']['heart_rate'] = {
                    'min': min(verity_hrs),
                    'max': max(verity_hrs),
                    'mean': sum(verity_hrs) / len(verity_hrs)
                }
                
                verity_rmssd = [float(row['verity_rmssd']) for row in rows if float(row.get('verity_rmssd', 0)) > 0]
                if verity_rmssd:
                    analysis['verity']['rr_intervals']['rmssd'] = sum(verity_rmssd) / len(verity_rmssd)
                
                verity_breathing = [float(row['verity_breathing_freq']) for row in rows if
                                    float(row.get('verity_breathing_freq', 0)) > 0]
                if verity_breathing:
                    analysis['verity']['breathing']['mean_freq'] = sum(verity_breathing) / len(verity_breathing)
            
            # Durée de session
            duration = float(rows[-1].get('session_duration', 0))
            analysis['session_duration'] = {
                'seconds': duration,
                'formatted': f"{int(duration // 60)}m {int(duration % 60)}s"
            }
            
            # Timestamps
            analysis['start_time'] = rows[0].get('timestamp')
            analysis['end_time'] = rows[-1].get('timestamp')
            
            return jsonify(analysis)
        
        except Exception as e:
            logger.error(f"Erreur analyse session: {e}")
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