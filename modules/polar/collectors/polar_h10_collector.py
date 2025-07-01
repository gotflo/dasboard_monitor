import asyncio
import logging
import struct
from datetime import datetime
from typing import Dict, List, Optional, Any
import bleak
from bleak import BleakClient
import threading

from .base_collector import BaseCollector, DeviceStatus, DataType, DeviceInfo

logger = logging.getLogger(__name__)


class PolarH10Collector(BaseCollector):
    """Collecteur Polar H10 - Communication Bluetooth BLE"""
    
    # UUIDs spécifiques au Polar H10
    HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
    HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
    BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
    BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
    DEVICE_INFORMATION_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
    
    def __init__(self, device_address: str):
        super().__init__(device_address, 'h10')
        self.client = None
        
        # Stockage de l'ID formaté
        self.formatted_device_id = "Non connecté"
        self.device_name = "Polar H10"
        self.connection_timestamp = None
        
        # Buffer pour les intervalles RR
        self.rr_buffer = []
        self.max_rr_buffer_size = 100
        
        # Gestion du BPM
        self.last_bpm = 0
        self.bpm_history = []
        self.max_bpm_history = 10
        
        # Thread-safe data handling
        self._data_lock = threading.Lock()
        self._running = False
        
        logger.info(f"Collecteur Polar H10 initialisé: {device_address}")
    
    async def connect(self) -> bool:
        """Connecte au Polar H10"""
        try:
            logger.info(f"Connexion au Polar H10: {self.device_address}")
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
            
            # Récupération des informations en arrière-plan
            asyncio.create_task(self._get_device_information())
            asyncio.create_task(self._get_battery_level())
            
            self.set_status(DeviceStatus.CONNECTED, f"Connecté: {self.formatted_device_id}")
            
            logger.info(f"Connexion Polar H10 réussie: {self.formatted_device_id}")
            return True
        
        except Exception as e:
            logger.error(f"Erreur connexion Polar H10: {e}")
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
    
    async def _get_device_information(self):
        """Récupère les informations de l'appareil"""
        try:
            device_info_raw = {}
            
            # Manufacturer
            try:
                manufacturer_data = await self.client.read_gatt_char("00002a29-0000-1000-8000-00805f9b34fb")
                manufacturer = manufacturer_data.decode('utf-8').strip()
                if manufacturer:
                    device_info_raw['manufacturer'] = manufacturer
            except:
                device_info_raw['manufacturer'] = "Polar"
            
            # Model
            try:
                model_data = await self.client.read_gatt_char("00002a24-0000-1000-8000-00805f9b34fb")
                model = model_data.decode('utf-8').strip()
                if model:
                    device_info_raw['model'] = model
                    self.device_name = f"{device_info_raw['manufacturer']} {model}"
            except:
                device_info_raw['model'] = "H10"
            
            # Créer l'objet DeviceInfo
            self.device_info = DeviceInfo(
                device_id=self.device_address,
                device_type='h10',
                name=self.device_name,
                manufacturer=device_info_raw.get('manufacturer', 'Polar'),
                model=device_info_raw.get('model', 'H10'),
                firmware_version="Unknown",
                hardware_version="Unknown",
                serial_number="Unknown",
                last_seen=datetime.now()
            )
            
            logger.info(f"H10 Infos récupérées: {self.device_name}")
        
        except Exception as e:
            logger.error(f"Erreur récupération infos H10: {e}")
            self.device_info = DeviceInfo(
                device_id=self.device_address,
                device_type='h10',
                name=self.device_name,
                manufacturer='Polar',
                model='H10',
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
            logger.info(f"Niveau batterie H10: {battery_level}%")
        except Exception as e:
            logger.error(f"Erreur lecture batterie H10: {e}")
            self.add_data_point(DataType.BATTERY_LEVEL, 0)
    
    def get_simple_device_info(self) -> Dict[str, Any]:
        """Retourne les informations essentielles"""
        return {
            'device_type': 'h10',
            'device_id': self.device_address,
            'formatted_id': self.formatted_device_id,
            'device_name': self.device_name,
            'status': self.status.value,
            'is_connected': self.is_connected,
            'connection_time': self.connection_timestamp.isoformat() if self.connection_timestamp else None,
            'manufacturer': getattr(self.device_info, 'manufacturer', 'Polar') if self.device_info else 'Polar',
            'model': getattr(self.device_info, 'model', 'H10') if self.device_info else 'H10'
        }
    
    async def disconnect(self):
        """Déconnecte du Polar H10"""
        try:
            self._running = False
            
            if self.is_collecting:
                await self.stop_data_collection()
            
            await self._cleanup_connection()
            
            self.formatted_device_id = "Non connecté"
            self.connection_timestamp = None
            self.device_info = None
            
            self.set_status(DeviceStatus.DISCONNECTED, "Déconnexion réussie")
            logger.info("Déconnexion Polar H10 réussie")
        
        except Exception as e:
            logger.error(f"Erreur déconnexion Polar H10: {e}")
            self.set_status(DeviceStatus.ERROR, f"Erreur déconnexion: {str(e)}")
    
    async def _cleanup_connection(self):
        """Nettoie la connexion"""
        self._running = False
        
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
            except Exception as e:
                logger.warning(f"Erreur lors de la déconnexion: {e}")
        
        self.is_connected = False
        self.client = None
    
    async def start_data_collection(self):
        """Démarre la collecte de données"""
        if not self.is_connected:
            raise Exception("Appareil non connecté")
        
        try:
            logger.info("Démarrage collecte données H10")
            
            # Créer un wrapper pour le callback qui vérifie si on est toujours actif
            def safe_notification_handler(sender: int, data: bytearray):
                if self._running:
                    try:
                        self._heart_rate_notification_handler(sender, data)
                    except Exception as e:
                        logger.error(f"Erreur dans le handler de notification: {e}")
            
            await self.client.start_notify(
                self.HEART_RATE_MEASUREMENT_UUID,
                safe_notification_handler
            )
            
            self.is_collecting = True
            logger.info("Collecte données H10 démarrée")
        
        except Exception as e:
            logger.error(f"Erreur démarrage collecte H10: {e}")
            raise
    
    async def stop_data_collection(self):
        """Arrête la collecte de données"""
        try:
            if self.client and self.client.is_connected:
                await self.client.stop_notify(self.HEART_RATE_MEASUREMENT_UUID)
            
            self.is_collecting = False
            logger.info("Collecte données H10 arrêtée")
        
        except Exception as e:
            logger.error(f"Erreur arrêt collecte H10: {e}")
    
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
            
            # Mise à jour avec thread safety
            with self._data_lock:
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
                    with self._data_lock:
                        self.rr_buffer.extend(rr_intervals)
                        if len(self.rr_buffer) > self.max_rr_buffer_size:
                            self.rr_buffer = self.rr_buffer[-self.max_rr_buffer_size:]
                    
                    self.add_data_point(DataType.RR_INTERVALS, self.rr_buffer.copy(), quality='good')
        
        except Exception as e:
            logger.error(f"Erreur traitement données H10: {e}")
    
    async def get_latest_data(self) -> Dict:
        """Récupère les dernières données"""
        if not self.is_connected:
            return {}
        
        data = self.current_data.copy()
        data.update({
            'device_info': self.get_simple_device_info(),
            'formatted_device_id': self.formatted_device_id,
            'device_name': self.device_name,
            'rr_buffer_size': len(self.rr_buffer),
            'last_bpm': self.last_bpm,
            'bpm_history': self.bpm_history.copy(),
            'avg_bpm': sum(self.bpm_history) / len(self.bpm_history) if self.bpm_history else 0,
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
    
    async def cleanup(self):
        """Nettoie les ressources"""
        await super().cleanup()
        self._running = False