import asyncio
import logging
import struct
from datetime import datetime
from typing import Dict, List, Optional, Any
import bleak
from bleak import BleakClient

from .base_collector import BaseCollector, DeviceStatus, DataType, DeviceInfo

logger = logging.getLogger(__name__)


class VerityCollector(BaseCollector):
    """Collecteur de données pour Polar Verity Sense"""
    
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
        super().__init__(device_address, 'verity')
        self.client = None
        
        # Buffer pour les intervalles RR
        self.rr_buffer = []
        self.max_rr_buffer_size = 100
        
        # Buffer pour l'accéléromètre
        self.acc_buffer = []
        self.max_acc_buffer_size = 50
        
        # Gestion du BPM
        self.last_bpm = 0
        self.bpm_history = []
        self.max_bpm_history = 10
        
        # État PMD
        self.pmd_available = False
        
        logger.info(f"Collecteur Polar Verity Sense initialisé: {device_address}")
    
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
            self.set_status(DeviceStatus.CONNECTED, "Connexion réussie")
            
            # Vérifier les services
            await self._check_available_services()
            
            # Récupérer les informations
            await self._get_device_information()
            await self._get_battery_level()
            
            logger.info("Connexion Polar Verity Sense réussie")
            return True
        
        except Exception as e:
            logger.error(f"Erreur connexion Polar Verity Sense: {e}")
            self.set_status(DeviceStatus.ERROR, f"Erreur connexion: {str(e)}")
            await self._cleanup_connection()
            return False
    
    async def disconnect(self):
        """Déconnecte du Polar Verity Sense"""
        try:
            if self.is_collecting:
                await self.stop_data_collection()
            
            await self._cleanup_connection()
            
            self.set_status(DeviceStatus.DISCONNECTED, "Déconnexion réussie")
            logger.info("Déconnexion Polar Verity Sense réussie")
        
        except Exception as e:
            logger.error(f"Erreur déconnexion Polar Verity Sense: {e}")
            self.set_status(DeviceStatus.ERROR, f"Erreur déconnexion: {str(e)}")
    
    async def _cleanup_connection(self):
        """Nettoie la connexion"""
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
            device_info = {}
            
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
                    device_info[info_name] = value.decode('utf-8').strip()
                except:
                    device_info[info_name] = "N/A"
            
            self.device_info = DeviceInfo(
                device_id=self.device_address,
                device_type='verity',
                name='Polar Verity Sense',
                manufacturer=device_info.get('manufacturer', 'Polar'),
                model=device_info.get('model_number', 'Verity Sense'),
                firmware_version=device_info.get('firmware_revision', 'Unknown'),
                hardware_version=device_info.get('hardware_revision', 'Unknown'),
                serial_number=device_info.get('serial_number', 'Unknown'),
                last_seen=datetime.now()
            )
            
            self.add_data_point(DataType.DEVICE_INFO, device_info)
            
            logger.info(
                f"Infos Verity: {device_info.get('manufacturer', 'Polar')} {device_info.get('model_number', 'Verity Sense')}")
        
        except Exception as e:
            logger.error(f"Erreur lecture infos Verity Sense: {e}")
    
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
    
    async def start_data_collection(self):
        """Démarre la collecte de données"""
        if not self.is_connected:
            raise Exception("Appareil non connecté")
        
        try:
            logger.info("Démarrage collecte données Verity Sense")
            
            # S'abonner aux notifications HR
            await self.client.start_notify(
                self.HEART_RATE_MEASUREMENT_UUID,
                self._heart_rate_notification_handler
            )
            logger.info("Notifications HR activées pour Verity Sense")
            
            # PMD si disponible
            if self.pmd_available:
                try:
                    await self.client.start_notify(
                        self.POLAR_PMD_DATA_UUID,
                        self._pmd_data_notification_handler
                    )
                    logger.info("Notifications PMD activées pour Verity Sense")
                except Exception as e:
                    logger.warning(f"PMD non activable sur Verity Sense: {e}")
                    self.pmd_available = False
            
            self.is_collecting = True
            logger.info("Collecte données Verity Sense démarrée")
        
        except Exception as e:
            logger.error(f"Erreur démarrage collecte Verity Sense: {e}")
            raise
    
    async def stop_data_collection(self):
        """Arrête la collecte de données"""
        try:
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
            
            # Validation
            if heart_rate < 30 or heart_rate > 250:
                return
            
            # Mise à jour
            self.last_bpm = heart_rate
            self.bpm_history.append(heart_rate)
            if len(self.bpm_history) > self.max_bpm_history:
                self.bpm_history.pop(0)
            
            self.add_data_point(DataType.HEART_RATE, heart_rate, quality='good')
            
            # Extraire les intervalles RR
            rr_intervals = []
            if flags & 0x10 and offset < len(data):
                i = offset
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
                    self.rr_buffer.extend(rr_intervals)
                    
                    if len(self.rr_buffer) > self.max_rr_buffer_size:
                        self.rr_buffer = self.rr_buffer[-self.max_rr_buffer_size:]
                    
                    self.add_data_point(DataType.RR_INTERVALS, self.rr_buffer.copy(), quality='good')
        
        except Exception as e:
            logger.error(f"Erreur traitement données Verity Sense: {e}")
            # Essayer de récupérer au moins le BPM
            try:
                if len(data) >= 2:
                    basic_hr = data[1] if not (data[0] & 0x01) else struct.unpack('<H', data[1:3])[0]
                    if 30 <= basic_hr <= 250:
                        self.add_data_point(DataType.HEART_RATE, basic_hr, quality='limited')
            except:
                pass
    
    def _pmd_data_notification_handler(self, sender: int, data: bytearray):
        """Gestionnaire des notifications PMD"""
        try:
            if len(data) < 4:
                return
            
            data_type = data[0]
            
            if data_type == 0x02:
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
                
                self.acc_buffer.append(acc_data)
                
                if len(self.acc_buffer) > self.max_acc_buffer_size:
                    self.acc_buffer = self.acc_buffer[-self.max_acc_buffer_size:]
        
        except Exception as e:
            logger.error(f"Erreur parsing accéléromètre: {e}")
    
    async def get_latest_data(self) -> Dict:
        """Récupère les dernières données"""
        if not self.is_connected:
            return {}
        
        # Mise à jour batterie périodiquement
        try:
            await self._get_battery_level()
        except:
            pass
        
        data = self.current_data.copy()
        data.update({
            'device_info': await self.get_device_info(),
            'rr_buffer_size': len(self.rr_buffer),
            'accelerometer_data': self.acc_buffer.copy(),
            'pmd_available': self.pmd_available,
            'last_bpm': self.last_bpm,
            'bpm_history': self.bpm_history.copy(),
            'avg_bpm': sum(self.bpm_history) / len(self.bpm_history) if self.bpm_history else 0,
            'data_rate': len(self.bpm_history),
            'connection_strength': 100 if self.is_connected else 0
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
        if not self.bpm_history:
            return 0.0
        return sum(self.bpm_history) / len(self.bpm_history)
    
    def get_connection_quality(self) -> Dict[str, Any]:
        """Retourne la qualité de connexion"""
        return {
            'is_connected': self.is_connected,
            'is_collecting': self.is_collecting,
            'bpm_data_rate': len(self.bpm_history),
            'rr_data_rate': len(self.rr_buffer),
            'acc_data_rate': len(self.acc_buffer),
            'pmd_available': self.pmd_available,
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