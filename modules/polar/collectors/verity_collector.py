import asyncio
import logging
import struct
from datetime import datetime
from typing import Dict, List, Optional, Any
import bleak
from bleak import BleakClient
import time
import threading

from .base_collector import BaseCollectorWithRSA, DeviceStatus, DataType, DeviceInfo

logger = logging.getLogger(__name__)


class VerityCollector(BaseCollectorWithRSA):
    """Collecteur de données pour Polar Verity Sense avec calcul RSA intégré"""
    
    # UUIDs spécifiques au Polar Verity Sense
    HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
    HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
    BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
    BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
    DEVICE_INFORMATION_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
    
    # UUIDs Polar propriétaires
    POLAR_PMD_SERVICE_UUID = "fb005c80-02e7-f387-1cad-8acd2d8df0c8"
    POLAR_PMD_CONTROL_UUID = "fb005c81-02e7-f387-1cad-8acd2d8df0c8"
    POLAR_PMD_DATA_UUID = "fb005c82-02e7-f387-1cad-8acd2d8df0c8"
    
    def __init__(self, device_address: str):
        # Utiliser BaseCollectorWithRSA pour avoir le calcul RSA
        super().__init__(device_address, 'verity')
        
        self.client = None
        
        # Stockage de l'ID formaté
        self.formatted_device_id = "Non connecté"
        self.device_name = "Polar Verity Sense"
        self.connection_timestamp = None
        
        # Buffer temporaire pour accumulation sur 1 seconde
        self.temp_hr_buffer = []
        self.temp_rr_buffer = []
        self.last_data_processing = time.time()
        
        # Task de traitement périodique
        self.processing_task = None
        
        # Buffer pour l'accéléromètre
        self.acc_buffer = []
        self.max_acc_buffer_size = 50
        
        # État PMD
        self.pmd_available = False
        
        # Thread-safe data handling
        self._data_lock = threading.Lock()
        self._running = False
        
        logger.info(f"Collecteur Polar Verity Sense avec RSA initialisé: {device_address}")
    
    async def connect(self) -> bool:
        """Connecte au Polar Verity Sense"""
        try:
            logger.info(f"Connexion au Polar Verity Sense: {self.device_address}")
            self.set_status(DeviceStatus.CONNECTING)
            
            self.client = BleakClient(self.device_address)
            await self.client.connect()
            
            if not self.client.is_connected:
                raise Exception("Échec de la connexion BLE")
            
            self.is_connected = True
            self._running = True
            self.connection_timestamp = datetime.now()
            
            # Formatage de l'ID
            self.formatted_device_id = self._format_device_id()
            
            # Vérifier les services
            await self._check_available_services()
            
            # Récupérer les informations
            asyncio.create_task(self._get_device_information())
            asyncio.create_task(self._get_battery_level())
            
            self.set_status(DeviceStatus.CONNECTED, f"Connecté: {self.formatted_device_id}")
            
            logger.info(f"Connexion Polar Verity Sense réussie: {self.formatted_device_id}")
            return True
        
        except Exception as e:
            logger.error(f"Erreur connexion Polar Verity Sense: {e}")
            self.formatted_device_id = "Non connecté"
            self.set_status(DeviceStatus.ERROR, f"Erreur connexion: {str(e)}")
            await self._cleanup_connection()
            return False
    
    def _format_device_id(self) -> str:
        """Formate l'ID pour l'affichage"""
        if not self.device_address:
            return "Non connecté"
        
        try:
            if ':' in self.device_address and len(self.device_address.split(':')) >= 6:
                parts = self.device_address.split(':')
                return f"{parts[-2]}:{parts[-1]}".upper()
            elif len(self.device_address) > 8:
                return f"...{self.device_address[-6:]}".upper()
            else:
                return self.device_address.upper()
        except:
            return "Connecté"
    
    async def disconnect(self):
        """Déconnecte du Polar Verity Sense"""
        try:
            self._running = False
            
            if self.is_collecting:
                await self.stop_data_collection()
            
            await self._cleanup_connection()
            
            self.formatted_device_id = "Non connecté"
            self.connection_timestamp = None
            self.device_info = None
            
            self.set_status(DeviceStatus.DISCONNECTED, "Déconnexion réussie")
            logger.info("Déconnexion Polar Verity Sense réussie")
        
        except Exception as e:
            logger.error(f"Erreur déconnexion Polar Verity Sense: {e}")
            self.set_status(DeviceStatus.ERROR, f"Erreur déconnexion: {str(e)}")
    
    async def _cleanup_connection(self):
        """Nettoie la connexion"""
        self._running = False
        
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
            except Exception as e:
                logger.warning(f"Erreur lors de la déconnexion Verity: {e}")
        
        self.is_connected = False
        self.client = None
        self.pmd_available = False
    
    async def _check_available_services(self):
        """Vérifie les services disponibles"""
        try:
            services = await self.client.get_services()
            
            for service in services:
                if service.uuid.lower() == self.POLAR_PMD_SERVICE_UUID.lower():
                    self.pmd_available = True
                    logger.info("Service PMD Polar détecté sur Verity Sense")
                    break
            
            if not self.pmd_available:
                logger.info("Service PMD non disponible")
        
        except Exception as e:
            logger.warning(f"Erreur vérification services Verity: {e}")
    
    async def _get_device_information(self):
        """Récupère les informations de l'appareil"""
        try:
            device_info_raw = {}
            
            info_characteristics = {
                "00002a29-0000-1000-8000-00805f9b34fb": "manufacturer",
                "00002a24-0000-1000-8000-00805f9b34fb": "model_number",
                "00002a25-0000-1000-8000-00805f9b34fb": "serial_number",
                "00002a27-0000-1000-8000-00805f9b34fb": "hardware_revision",
                "00002a26-0000-1000-8000-00805f9b34fb": "firmware_revision"
            }
            
            for char_uuid, info_name in info_characteristics.items():
                try:
                    value = await self.client.read_gatt_char(char_uuid)
                    device_info_raw[info_name] = value.decode('utf-8').strip()
                except:
                    device_info_raw[info_name] = "N/A"
            
            # Mettre à jour le nom de l'appareil
            if device_info_raw.get('model_number'):
                self.device_name = f"{device_info_raw.get('manufacturer', 'Polar')} {device_info_raw['model_number']}"
            
            self.device_info = DeviceInfo(
                device_id=self.device_address,
                device_type='verity',
                name=self.device_name,
                manufacturer=device_info_raw.get('manufacturer', 'Polar'),
                model=device_info_raw.get('model_number', 'Verity Sense'),
                firmware_version=device_info_raw.get('firmware_revision', 'Unknown'),
                hardware_version=device_info_raw.get('hardware_revision', 'Unknown'),
                serial_number=device_info_raw.get('serial_number', 'Unknown'),
                last_seen=datetime.now()
            )
            
            self.add_data_point(DataType.DEVICE_INFO, device_info_raw)
            
            logger.info(f"Infos Verity: {self.device_name}")
        
        except Exception as e:
            logger.error(f"Erreur lecture infos Verity Sense: {e}")
            self.device_info = DeviceInfo(
                device_id=self.device_address,
                device_type='verity',
                name=self.device_name,
                manufacturer='Polar',
                model='Verity Sense',
                firmware_version="Unknown",
                hardware_version="Unknown",
                serial_number="Unknown",
                last_seen=datetime.now()
            )
    
    async def _get_battery_level(self):
        """Récupère le niveau de batterie"""
        try:
            battery_data = await self.client.read_gatt_char(self.BATTERY_LEVEL_UUID)
            battery_level = int(battery_data[0])
            
            self.add_data_point(DataType.BATTERY_LEVEL, battery_level)
            
            logger.info(f"Niveau batterie Verity Sense: {battery_level}%")
        
        except Exception as e:
            logger.warning(f"Erreur lecture batterie Verity Sense: {e}")
            self.add_data_point(DataType.BATTERY_LEVEL, 0)
    
    def get_simple_device_info(self) -> Dict[str, Any]:
        """Retourne les informations essentielles"""
        return {
            'device_type': 'verity',
            'device_id': self.device_address,
            'formatted_id': self.formatted_device_id,
            'device_name': self.device_name,
            'status': self.status.value,
            'is_connected': self.is_connected,
            'connection_time': self.connection_timestamp.isoformat() if self.connection_timestamp else None,
            'manufacturer': getattr(self.device_info, 'manufacturer', 'Polar') if self.device_info else 'Polar',
            'model': getattr(self.device_info, 'model', 'Verity Sense') if self.device_info else 'Verity Sense',
            'pmd_available': self.pmd_available
        }
    
    async def start_data_collection(self):
        """Démarre la collecte de données avec traitement RSA"""
        if not self.is_connected:
            raise Exception("Appareil non connecté")
        
        try:
            logger.info("Démarrage collecte données Verity Sense avec traitement RSA")
            
            # Wrapper sécurisé pour les notifications
            def safe_hr_handler(sender: int, data: bytearray):
                if self._running:
                    try:
                        self._heart_rate_notification_handler(sender, data)
                    except Exception as e:
                        logger.error(f"Erreur dans le handler HR: {e}")
            
            # S'abonner aux notifications HR
            await self.client.start_notify(
                self.HEART_RATE_MEASUREMENT_UUID,
                safe_hr_handler
            )
            logger.info("Notifications HR activées pour Verity Sense")
            
            # PMD si disponible
            if self.pmd_available:
                try:
                    def safe_pmd_handler(sender: int, data: bytearray):
                        if self._running:
                            try:
                                self._pmd_data_notification_handler(sender, data)
                            except Exception as e:
                                logger.error(f"Erreur dans le handler PMD: {e}")
                    
                    await self.client.start_notify(
                        self.POLAR_PMD_DATA_UUID,
                        safe_pmd_handler
                    )
                    logger.info("Notifications PMD activées pour Verity Sense")
                except Exception as e:
                    logger.warning(f"PMD non activable sur Verity Sense: {e}")
                    self.pmd_available = False
            
            self.is_collecting = True
            
            # Démarrer le traitement périodique (toutes les secondes)
            self.processing_task = asyncio.create_task(self._periodic_data_processor())
            
            logger.info("Collecte données Verity Sense démarrée avec processeur RSA")
        
        except Exception as e:
            logger.error(f"Erreur démarrage collecte Verity Sense: {e}")
            raise
    
    async def stop_data_collection(self):
        """Arrête la collecte de données"""
        try:
            # Arrêter le traitement périodique
            if self.processing_task:
                self.processing_task.cancel()
                try:
                    await self.processing_task
                except asyncio.CancelledError:
                    pass
                self.processing_task = None
            
            # Arrêter les notifications
            if self.client and self.client.is_connected:
                await self.client.stop_notify(self.HEART_RATE_MEASUREMENT_UUID)
                
                if self.pmd_available:
                    try:
                        await self.client.stop_notify(self.POLAR_PMD_DATA_UUID)
                    except:
                        pass
            
            self.is_collecting = False
            logger.info("Collecte données Verity Sense arrêtée")
        
        except Exception as e:
            logger.error(f"Erreur arrêt collecte Verity Sense: {e}")
    
    def _heart_rate_notification_handler(self, sender: int, data: bytearray):
        """Gestionnaire des notifications de fréquence cardiaque"""
        try:
            if len(data) < 2:
                return
            
            # Parse selon le format Bluetooth Heart Rate
            flags = data[0]
            
            # Extraction du BPM
            if flags & 0x01:  # Format 16 bits
                if len(data) < 3:
                    return
                heart_rate = struct.unpack('<H', data[1:3])[0]
                offset = 3
            else:  # Format 8 bits
                heart_rate = data[1]
                offset = 2
            
            # Validation et accumulation thread-safe
            if 30 <= heart_rate <= 250:
                with self._data_lock:
                    self.temp_hr_buffer.append(heart_rate)
            
            # Extraire les intervalles RR
            if flags & 0x10 and offset < len(data):
                i = offset
                rr_intervals = []
                while i < len(data) - 1:
                    try:
                        rr_interval = struct.unpack('<H', data[i:i + 2])[0]
                        rr_ms = (rr_interval / 1024.0) * 1000.0
                        
                        if 200 <= rr_ms <= 2000:
                            rr_intervals.append(round(rr_ms, 2))
                        
                        i += 2
                    except:
                        break
                
                if rr_intervals:
                    with self._data_lock:
                        self.temp_rr_buffer.extend(rr_intervals)
        
        except Exception as e:
            logger.error(f"Erreur traitement données Verity Sense: {e}")
    
    def _pmd_data_notification_handler(self, sender: int, data: bytearray):
        """Gestionnaire des notifications PMD"""
        try:
            if len(data) < 4:
                return
            
            data_type = data[0]
            
            if data_type == 0x02:  # Accéléromètre
                self._parse_accelerometer_data(data[1:])
        
        except Exception as e:
            logger.error(f"Erreur traitement PMD Verity: {e}")
    
    def _parse_accelerometer_data(self, data: bytearray):
        """Parse les données d'accéléromètre"""
        try:
            if len(data) >= 6:
                x = struct.unpack('<h', data[0:2])[0]
                y = struct.unpack('<h', data[2:4])[0]
                z = struct.unpack('<h', data[4:6])[0]
                
                acc_data = {
                    'x': x,
                    'y': y,
                    'z': z,
                    'timestamp': datetime.now().isoformat(),
                    'magnitude': (x * x + y * y + z * z) ** 0.5
                }
                
                with self._data_lock:
                    self.acc_buffer.append(acc_data)
                    
                    if len(self.acc_buffer) > self.max_acc_buffer_size:
                        self.acc_buffer = self.acc_buffer[-self.max_acc_buffer_size:]
        
        except Exception as e:
            logger.error(f"Erreur parsing accéléromètre: {e}")
    
    async def _periodic_data_processor(self):
        """Processeur qui traite les données accumulées toutes les secondes avec RSA"""
        while self.is_collecting and self._running:
            try:
                await asyncio.sleep(1.0)  # Attendre 1 seconde
                
                current_time = time.time()
                
                # Copier et vider les buffers thread-safe
                with self._data_lock:
                    hr_data = self.temp_hr_buffer.copy()
                    rr_data = self.temp_rr_buffer.copy()
                    self.temp_hr_buffer.clear()
                    self.temp_rr_buffer.clear()
                
                # Traiter HR (dernière valeur de la seconde)
                if hr_data:
                    last_hr = hr_data[-1]
                    self.add_data_point(DataType.HEART_RATE, last_hr, quality='good')
                
                # Traiter RR (tous les intervalles de la seconde)
                if rr_data:
                    # Ajouter au calculateur RSA avec timestamp
                    self.rsa_calculator.add_rr_intervals(rr_data, current_time)
                    
                    # Ajouter le point de données RR
                    self.add_data_point(DataType.RR_INTERVALS, rr_data, quality='good')
                    
                    # Le calcul RSA se fait automatiquement dans update_rr_metrics
                    # grâce à BaseCollectorWithRSA
                
                # Mettre à jour la batterie périodiquement (toutes les 30 secondes)
                if int(current_time) % 30 == 0:
                    asyncio.create_task(self._update_battery_level())
                
                # Log RSA si respiration détectée
                if self.breathing_metrics.frequency > 0:
                    logger.debug(f"Verity RSA: {self.breathing_metrics.frequency:.1f} rpm, "
                                 f"amplitude: {self.breathing_metrics.amplitude:.3f}, "
                                 f"qualité: {self.breathing_metrics.quality}")
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur dans le processeur périodique Verity: {e}")
    
    async def _update_battery_level(self):
        """Met à jour le niveau de batterie"""
        try:
            if self.client and self.client.is_connected:
                battery_data = await self.client.read_gatt_char(self.BATTERY_LEVEL_UUID)
                battery_level = int(battery_data[0])
                self.add_data_point(DataType.BATTERY_LEVEL, battery_level)
        except Exception as e:
            logger.debug(f"Impossible de lire la batterie: {e}")
    
    async def get_latest_data(self) -> Dict:
        """Récupère les dernières données avec métriques RSA"""
        if not self.is_connected:
            return {}
        
        # Obtenir les données de base
        data = await super().get_latest_data()
        
        # Ajouter des informations spécifiques au Verity
        data.update({
            'device_info': self.get_simple_device_info(),
            'formatted_device_id': self.formatted_device_id,
            'device_name': self.device_name,
            'accelerometer_data': self.acc_buffer.copy() if self.acc_buffer else [],
            'pmd_available': self.pmd_available,
            'rsa_breathing': {
                'rate_rpm': self.breathing_metrics.frequency,
                'amplitude': self.breathing_metrics.amplitude,
                'quality': self.breathing_metrics.quality,
                'buffer_size': len(self.rsa_calculator.rr_buffer),
                'window_seconds': self.rsa_calculator.breathing_window
            }
        })
        
        return data
    
    async def test_connection(self) -> bool:
        """Test la connexion"""
        if not self.client or not self.client.is_connected:
            return False
        
        try:
            await self.client.read_gatt_char(self.BATTERY_LEVEL_UUID)
            return True
        except:
            return False
    
    def get_average_bpm(self) -> float:
        """Retourne le BPM moyen"""
        if not self.bpm_buffer:
            return 0.0
        return sum(self.bpm_buffer) / len(self.bpm_buffer)
    
    def get_connection_quality(self) -> Dict[str, Any]:
        """Retourne la qualité de connexion"""
        return {
            'is_connected': self.is_connected,
            'is_collecting': self.is_collecting,
            'bpm_data_rate': len(self.bpm_buffer),
            'rr_data_rate': len(self.rr_buffer),
            'acc_data_rate': len(self.acc_buffer),
            'pmd_available': self.pmd_available,
            'rsa_status': {
                'breathing_detected': self.breathing_metrics.frequency > 0,
                'quality': self.breathing_metrics.quality,
                'buffer_fullness': f"{(len(self.rsa_calculator.rr_buffer) / self.rsa_calculator.rr_buffer.maxlen * 100):.0f}%"
            },
            'last_update': self.current_data.get('last_update'),
            'errors_count': self.connection_stats.get('errors_count', 0)
        }
    
    def get_accelerometer_stats(self) -> Dict[str, Any]:
        """Retourne les stats accéléromètre"""
        if not self.acc_buffer:
            return {}
        
        recent_data = self.acc_buffer[-10:] if len(self.acc_buffer) >= 10 else self.acc_buffer
        
        if not recent_data:
            return {}
        
        avg_x = sum(d['x'] for d in recent_data) / len(recent_data)
        avg_y = sum(d['y'] for d in recent_data) / len(recent_data)
        avg_z = sum(d['z'] for d in recent_data) / len(recent_data)
        avg_mag = sum(d['magnitude'] for d in recent_data) / len(recent_data)
        
        return {
            'sample_count': len(self.acc_buffer),
            'recent_samples': len(recent_data),
            'average': {
                'x': round(avg_x, 2),
                'y': round(avg_y, 2),
                'z': round(avg_z, 2),
                'magnitude': round(avg_mag, 2)
            },
            'last_sample': recent_data[-1] if recent_data else None
        }
    
    async def cleanup(self):
        """Nettoie les ressources"""
        await super().cleanup()
        self._running = False
        
        # Nettoyer les données spécifiques au Verity
        self.temp_hr_buffer.clear()
        self.temp_rr_buffer.clear()
        self.acc_buffer.clear()
        self.formatted_device_id = "Non connecté"
        self.connection_timestamp = None
        self.pmd_available = False