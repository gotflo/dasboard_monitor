import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from collections import deque
import statistics

logger = logging.getLogger(__name__)


class DeviceStatus(Enum):
    """États possibles d'un appareil"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class DataType(Enum):
    """Types de données collectées"""
    HEART_RATE = "heart_rate"
    RR_INTERVALS = "rr_intervals"
    BATTERY_LEVEL = "battery_level"
    DEVICE_INFO = "device_info"
    BREATHING_RATE = "breathing_rate"


@dataclass
class DeviceInfo:
    """Informations sur un appareil"""
    device_id: str
    device_type: str
    name: str
    manufacturer: str = "Polar"
    model: str = "Unknown"
    firmware_version: str = "Unknown"
    hardware_version: str = "Unknown"
    serial_number: str = "Unknown"
    last_seen: Optional[datetime] = None


@dataclass
class RRMetrics:
    """Métriques RR en temps réel"""
    last_rr: float = 0.0
    mean_rr: float = 0.0
    rmssd: float = 0.0
    count: int = 0


@dataclass
class BPMMetrics:
    """Métriques BPM en temps réel"""
    current_bpm: int = 0
    mean_bpm: float = 0.0
    min_bpm: int = 0
    max_bpm: int = 0
    session_min: int = 999
    session_max: int = 0


@dataclass
class BreathingMetrics:
    """Métriques de respiration en temps réel"""
    frequency: float = 0.0
    amplitude: float = 0.0
    variability_percent: float = 0.0
    quality: str = "unknown"


class BaseCollector(ABC):
    """Classe de base pour tous les collecteurs Polar"""
    
    def __init__(self, device_address: str, device_type: str):
        self.device_address = device_address
        self.device_type = device_type
        self.device_info = None
        self.status = DeviceStatus.DISCONNECTED
        
        # État de la connexion
        self.is_connected = False
        self.is_collecting = False
        
        # Données actuelles
        self.current_data = {
            'heart_rate': 0,
            'rr_intervals': [],
            'breathing_rate': 0,
            'battery_level': 0,
            'last_update': None,
            'data_quality': 'unknown',
            'connection_strength': 0,
        }
        
        # Buffers pour les calculs temps réel
        self.rr_buffer = deque(maxlen=100)
        self.bpm_buffer = deque(maxlen=50)
        self.breathing_buffer = deque(maxlen=20)
        
        # Métriques temps réel
        self.rr_metrics = RRMetrics()
        self.bpm_metrics = BPMMetrics()
        self.breathing_metrics = BreathingMetrics()
        
        # Historique pour calculs
        self.breathing_frequency_history = deque(maxlen=15)
        self.amplitude_history = deque(maxlen=30)
        
        # Callbacks
        self.data_callbacks: List[Callable] = []
        self.status_callbacks: List[Callable] = []
        
        # Statistiques de connexion
        self.connection_stats = {
            'connection_time': None,
            'last_data_received': None,
            'data_points_received': 0,
            'errors_count': 0,
            'reconnection_attempts': 0
        }
        
        logger.info(f"BaseCollector initialisé pour {device_type}: {device_address}")
    
    # ===== MÉTHODES ABSTRAITES =====
    
    @abstractmethod
    async def connect(self) -> bool:
        """Connecte à l'appareil"""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Déconnecte de l'appareil"""
        pass
    
    @abstractmethod
    async def start_data_collection(self):
        """Démarre la collecte de données"""
        pass
    
    @abstractmethod
    async def stop_data_collection(self):
        """Arrête la collecte de données"""
        pass
    
    @abstractmethod
    async def get_latest_data(self) -> Dict[str, Any]:
        """Récupère les dernières données"""
        pass
    
    # ===== GESTION DES MÉTRIQUES =====
    
    def update_rr_metrics(self, rr_intervals: List[float]):
        """Met à jour les métriques RR"""
        if not rr_intervals:
            return
        
        try:
            # Ajouter au buffer
            for rr in rr_intervals:
                if self._is_valid_rr(rr):
                    self.rr_buffer.append(rr)
            
            if len(self.rr_buffer) == 0:
                return
            
            # Calculer les métriques
            self.rr_metrics.last_rr = self.rr_buffer[-1]
            self.rr_metrics.mean_rr = statistics.mean(self.rr_buffer)
            
            # RMSSD
            if len(self.rr_buffer) >= 2:
                successive_diffs = []
                rr_list = list(self.rr_buffer)
                for i in range(1, len(rr_list)):
                    diff = rr_list[i] - rr_list[i - 1]
                    successive_diffs.append(diff * diff)
                
                if successive_diffs:
                    self.rr_metrics.rmssd = (sum(successive_diffs) / len(successive_diffs)) ** 0.5
            
            self.rr_metrics.count = len(self.rr_buffer)
        
        except Exception as e:
            logger.error(f"Erreur mise à jour métriques RR: {e}")
    
    def update_bpm_metrics(self, bpm: int):
        """Met à jour les métriques BPM"""
        if not self._is_valid_bpm(bpm):
            return
        
        try:
            self.bpm_buffer.append(bpm)
            self.bpm_metrics.current_bpm = bpm
            self.bpm_metrics.mean_bpm = statistics.mean(self.bpm_buffer)
            
            # Min/Max session
            if self.bpm_metrics.session_min == 999:
                self.bpm_metrics.session_min = bpm
                self.bpm_metrics.session_max = bpm
            else:
                self.bpm_metrics.session_min = min(self.bpm_metrics.session_min, bpm)
                self.bpm_metrics.session_max = max(self.bpm_metrics.session_max, bpm)
            
            # Min/Max buffer
            self.bpm_metrics.min_bpm = min(self.bpm_buffer)
            self.bpm_metrics.max_bpm = max(self.bpm_buffer)
        
        except Exception as e:
            logger.error(f"Erreur mise à jour métriques BPM: {e}")
    
    def update_breathing_metrics(self, breathing_rate: float):
        """Met à jour les métriques de respiration"""
        if not self._is_valid_breathing_rate(breathing_rate):
            return
        
        try:
            self.breathing_buffer.append(breathing_rate)
            self.breathing_frequency_history.append(breathing_rate)
            
            self.breathing_metrics.frequency = breathing_rate
            
            # Amplitude basée sur la variabilité RR
            if len(self.rr_buffer) >= 10:
                self.breathing_metrics.amplitude = self._calculate_breathing_amplitude()
            
            # Variabilité
            if len(self.breathing_frequency_history) >= 5:
                self.breathing_metrics.variability_percent = self._calculate_breathing_variability()
            
            # Qualité
            self.breathing_metrics.quality = self._assess_breathing_quality()
        
        except Exception as e:
            logger.error(f"Erreur mise à jour métriques respiration: {e}")
    
    def _calculate_breathing_amplitude(self) -> float:
        """Calcule l'amplitude respiratoire"""
        try:
            if len(self.rr_buffer) < 10:
                return 0.0
            
            recent_rr = list(self.rr_buffer)[-30:]
            
            if len(recent_rr) >= 3:
                variance = statistics.variance(recent_rr)
                amplitude = min(100.0, variance / 10.0)
                return round(amplitude, 1)
            
            return 0.0
        except:
            return 0.0
    
    def _calculate_breathing_variability(self) -> float:
        """Calcule la variabilité respiratoire"""
        try:
            if len(self.breathing_frequency_history) < 3:
                return 0.0
            
            freq_list = list(self.breathing_frequency_history)
            mean_freq = statistics.mean(freq_list)
            
            if mean_freq == 0:
                return 0.0
            
            std_dev = statistics.stdev(freq_list) if len(freq_list) > 1 else 0.0
            cv_percent = (std_dev / mean_freq) * 100.0
            
            return round(min(100.0, cv_percent), 1)
        except:
            return 0.0
    
    def _assess_breathing_quality(self) -> str:
        """Évalue la qualité de la respiration"""
        try:
            freq = self.breathing_metrics.frequency
            variability = self.breathing_metrics.variability_percent
            
            if freq == 0:
                return "unknown"
            
            if 12 <= freq <= 18 and variability <= 15:
                return "excellent"
            elif 10 <= freq <= 20 and variability <= 25:
                return "good"
            elif 8 <= freq <= 25 and variability <= 35:
                return "fair"
            else:
                return "poor"
        except:
            return "unknown"
    
    # ===== VALIDATION =====
    
    def _is_valid_rr(self, rr: float) -> bool:
        """Valide un intervalle RR"""
        return isinstance(rr, (int, float)) and 200 <= rr <= 2000
    
    def _is_valid_bpm(self, bpm: int) -> bool:
        """Valide un BPM"""
        return isinstance(bpm, int) and 30 <= bpm <= 250
    
    def _is_valid_breathing_rate(self, rate: float) -> bool:
        """Valide une fréquence respiratoire"""
        return isinstance(rate, (int, float)) and 5 <= rate <= 40
    
    # ===== GESTION DU STATUT =====
    
    def set_status(self, status: DeviceStatus, message: str = ""):
        """Met à jour le statut de l'appareil"""
        old_status = self.status
        self.status = status
        
        if status == DeviceStatus.CONNECTED:
            self.connection_stats['connection_time'] = datetime.now()
            self.connection_stats['reconnection_attempts'] = 0
        elif status == DeviceStatus.ERROR:
            self.connection_stats['errors_count'] += 1
        
        logger.info(f"Statut {self.device_type}: {old_status.value} -> {status.value}")
        
        # Notifier les callbacks
        for callback in self.status_callbacks:
            try:
                callback(self.device_type, status, message)
            except Exception as e:
                logger.error(f"Erreur callback statut: {e}")
    
    # ===== GESTION DES DONNÉES =====
    
    def add_data_point(self, data_type: DataType, value: Any, quality: str = 'good'):
        """Ajoute un point de données"""
        try:
            # Validation
            validated_value = self._validate_data(data_type, value)
            if validated_value is None:
                return
            
            # Mise à jour selon le type
            if data_type == DataType.HEART_RATE:
                self.current_data['heart_rate'] = validated_value
                self.update_bpm_metrics(validated_value)
            
            elif data_type == DataType.RR_INTERVALS:
                if isinstance(validated_value, list):
                    self.current_data['rr_intervals'] = validated_value
                    self.update_rr_metrics(validated_value)
                    
                    # Calculer la respiration
                    breathing_rate = self._calculate_breathing_rate_from_rr(validated_value)
                    if breathing_rate > 0:
                        self.current_data['breathing_rate'] = breathing_rate
                        self.update_breathing_metrics(breathing_rate)
            
            elif data_type == DataType.BATTERY_LEVEL:
                self.current_data['battery_level'] = validated_value
            
            elif data_type == DataType.BREATHING_RATE:
                self.current_data['breathing_rate'] = validated_value
                self.update_breathing_metrics(validated_value)
            
            # Métadonnées
            self.current_data['last_update'] = datetime.now().isoformat()
            self.current_data['data_quality'] = quality
            self.connection_stats['last_data_received'] = datetime.now()
            self.connection_stats['data_points_received'] += 1
            
            # Notifier
            for callback in self.data_callbacks:
                try:
                    callback(self.current_data.copy())
                except Exception as e:
                    logger.error(f"Erreur callback données: {e}")
        
        except Exception as e:
            logger.error(f"Erreur ajout données: {e}")
    
    def _validate_data(self, data_type: DataType, value: Any) -> Any:
        """Valide les données selon leur type"""
        try:
            if data_type == DataType.HEART_RATE:
                hr = int(value)
                return hr if 30 <= hr <= 250 else None
            elif data_type == DataType.BATTERY_LEVEL:
                battery = int(value)
                return battery if 0 <= battery <= 100 else None
            elif data_type == DataType.BREATHING_RATE:
                br = float(value)
                return br if 5 <= br <= 40 else None
            elif data_type == DataType.RR_INTERVALS:
                if isinstance(value, list):
                    valid_intervals = []
                    for interval in value:
                        if isinstance(interval, (int, float)) and 200 <= interval <= 2000:
                            valid_intervals.append(float(interval))
                    return valid_intervals if valid_intervals else None
                return None
            else:
                return value
        except:
            return None
    
    def _calculate_breathing_rate_from_rr(self, rr_intervals: List[float]) -> float:
        """Calcule la fréquence respiratoire à partir des RR"""
        if len(rr_intervals) < 10:
            return 0.0
        
        try:
            recent_intervals = rr_intervals[-30:] if len(rr_intervals) >= 30 else rr_intervals
            
            mean_rr = sum(recent_intervals) / len(recent_intervals)
            variance = sum((x - mean_rr) ** 2 for x in recent_intervals) / len(recent_intervals)
            std_dev = variance ** 0.5
            
            if std_dev > 0 and mean_rr > 0:
                bpm = 60000 / mean_rr
                base_breathing_rate = 15.0
                variability_factor = min(std_dev / mean_rr, 0.1)
                
                if bpm < 60:
                    hr_factor = 0.9
                elif bpm > 100:
                    hr_factor = 1.2
                else:
                    hr_factor = 1.0
                
                breathing_rate = base_breathing_rate * hr_factor * (1 + variability_factor * 5)
                
                return max(8.0, min(25.0, breathing_rate))
            
            return 15.0
        except:
            return 0.0
    
    # ===== MÉTRIQUES =====
    
    def get_real_time_metrics(self) -> Dict[str, Any]:
        """Retourne les métriques temps réel"""
        return {
            'rr_metrics': {
                'last_rr': round(self.rr_metrics.last_rr, 1),
                'mean_rr': round(self.rr_metrics.mean_rr, 1),
                'rmssd': round(self.rr_metrics.rmssd, 1),
                'count': self.rr_metrics.count
            },
            'bpm_metrics': {
                'current_bpm': self.bpm_metrics.current_bpm,
                'mean_bpm': round(self.bpm_metrics.mean_bpm, 1),
                'min_bpm': self.bpm_metrics.min_bpm,
                'max_bpm': self.bpm_metrics.max_bpm,
                'session_min': self.bpm_metrics.session_min if self.bpm_metrics.session_min != 999 else 0,
                'session_max': self.bpm_metrics.session_max
            },
            'breathing_metrics': {
                'frequency': round(self.breathing_metrics.frequency, 1),
                'amplitude': round(self.breathing_metrics.amplitude, 1),
                'variability_percent': round(self.breathing_metrics.variability_percent, 1),
                'quality': self.breathing_metrics.quality
            }
        }
    
    # ===== CALLBACKS =====
    
    def add_data_callback(self, callback: Callable):
        """Ajoute un callback données"""
        if callback not in self.data_callbacks:
            self.data_callbacks.append(callback)
    
    def remove_data_callback(self, callback: Callable):
        """Supprime un callback données"""
        if callback in self.data_callbacks:
            self.data_callbacks.remove(callback)
    
    def add_status_callback(self, callback: Callable):
        """Ajoute un callback statut"""
        if callback not in self.status_callbacks:
            self.status_callbacks.append(callback)
    
    def remove_status_callback(self, callback: Callable):
        """Supprime un callback statut"""
        if callback in self.status_callbacks:
            self.status_callbacks.remove(callback)
    
    # ===== INFORMATIONS =====
    
    async def get_device_info(self) -> Dict[str, Any]:
        """Retourne les informations de l'appareil"""
        base_info = {
            'device_id': self.device_address,
            'device_type': self.device_type,
            'status': self.status.value,
            'is_connected': self.is_connected,
            'is_collecting': self.is_collecting,
            'connection_stats': self.connection_stats.copy(),
            'data_quality': self.current_data.get('data_quality', 'unknown'),
            'real_time_metrics': self.get_real_time_metrics()
        }
        
        if self.device_info:
            base_info.update({
                'name': self.device_info.name,
                'manufacturer': self.device_info.manufacturer,
                'model': self.device_info.model,
                'firmware_version': self.device_info.firmware_version,
                'hardware_version': self.device_info.hardware_version,
                'serial_number': self.device_info.serial_number,
                'last_seen': self.device_info.last_seen.isoformat() if self.device_info.last_seen else None
            })
        
        return base_info
    
    async def get_latest_data(self) -> Dict[str, Any]:
        """Récupère les dernières données"""
        data = self.current_data.copy()
        data['real_time_metrics'] = self.get_real_time_metrics()
        return data
    
    # ===== NETTOYAGE =====
    
    async def cleanup(self):
        """Nettoie les ressources"""
        logger.info(f"Nettoyage du collecteur {self.device_type}")
        
        try:
            if self.is_collecting:
                await self.stop_data_collection()
            
            if self.is_connected:
                await self.disconnect()
            
            self.data_callbacks.clear()
            self.status_callbacks.clear()
            
            # Réinitialiser
            self.current_data = {
                'heart_rate': 0,
                'rr_intervals': [],
                'breathing_rate': 0,
                'battery_level': 0,
                'last_update': None,
                'data_quality': 'unknown',
                'connection_strength': 0,
            }
            
            self.rr_buffer.clear()
            self.bpm_buffer.clear()
            self.breathing_buffer.clear()
            self.breathing_frequency_history.clear()
            self.amplitude_history.clear()
            
            self.rr_metrics = RRMetrics()
            self.bpm_metrics = BPMMetrics()
            self.breathing_metrics = BreathingMetrics()
            
            self.connection_stats = {
                'connection_time': None,
                'last_data_received': None,
                'data_points_received': 0,
                'errors_count': 0,
                'reconnection_attempts': 0
            }
            
            logger.info(f"Nettoyage terminé pour {self.device_type}")
        
        except Exception as e:
            logger.error(f"Erreur nettoyage: {e}")
    
    # ===== UTILITAIRES =====
    
    def is_data_fresh(self, max_age_seconds: int = 5) -> bool:
        """Vérifie si les données sont récentes"""
        if not self.current_data.get('last_update'):
            return False
        
        try:
            last_update = datetime.fromisoformat(self.current_data['last_update'])
            age = (datetime.now() - last_update).total_seconds()
            return age <= max_age_seconds
        except:
            return False