import asyncio
import logging
import struct
from datetime import datetime
from typing import Dict, List, Optional, Any
import bleak
from bleak import BleakClient
import time
import threading
import numpy as np
from scipy import signal as scipy_signal

from .base_collector import BaseCollectorWithRSA, DeviceStatus, DataType, DeviceInfo

logger = logging.getLogger(__name__)


class VerityCollector(BaseCollectorWithRSA):
    """Collecteur de données pour Polar Verity Sense avec calcul RSA intégré et support PPG/PPI"""
    
    # UUIDs Standards Bluetooth
    HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
    HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
    BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
    BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
    DEVICE_INFORMATION_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
    
    # UUIDs Polar PMD (Polar Measurement Data)
    POLAR_PMD_SERVICE_UUID = "fb005c80-02e7-f387-1cad-8acd2d8df0c8"
    POLAR_PMD_CONTROL_UUID = "fb005c81-02e7-f387-1cad-8acd2d8df0c8"
    POLAR_PMD_DATA_UUID = "fb005c82-02e7-f387-1cad-8acd2d8df0c8"
    
    # Types de données PMD
    PMD_TYPE_ECG = 0x00
    PMD_TYPE_PPG = 0x01
    PMD_TYPE_ACC = 0x02
    PMD_TYPE_PPI = 0x03  # PPI (Peak-to-Peak Interval) = RR intervals
    
    def __init__(self, device_address: str):
        """Initialise le collecteur Verity Sense avec support complet PPG/PPI/RSA"""
        super().__init__(device_address, 'verity')
        
        self.client = None
        
        # Identification de l'appareil
        self.formatted_device_id = "Non connecté"
        self.device_name = "Polar Verity Sense"
        self.connection_timestamp = None
        
        # Buffers temporaires pour accumulation (1 seconde)
        self.temp_hr_buffer = []
        self.temp_rr_buffer = []
        self.last_data_processing = time.time()
        
        # Task de traitement périodique
        self.processing_task = None
        
        # Buffer PPG pour traitement du signal
        self.ppg_buffer = []
        self.max_ppg_buffer_size = 270  # ~2 secondes à 135Hz
        self.ppg_sample_rate = 135  # Hz typique pour Verity Sense
        self.ppg_processing_interval = 2.0  # Traiter toutes les 2 secondes
        self.last_ppg_processing = time.time()
        
        # Buffer accéléromètre
        self.acc_buffer = []
        self.max_acc_buffer_size = 50
        
        # État PMD
        self.pmd_available = False
        self.pmd_streaming = {
            'ppg': False,
            'ppi': False,
            'acc': False
        }
        
        # Thread-safe data handling
        self._data_lock = threading.Lock()
        self._running = False
        
        # Génération de RR synthétiques
        self.synthetic_rr_enabled = True
        self.last_synthetic_time = time.time()
        self.synthetic_rr_quality = 0.05  # Variabilité de 5%
        
        logger.info(f"Collecteur Polar Verity Sense initialisé: {device_address}")
    
    async def connect(self) -> bool:
        """Connecte au Polar Verity Sense avec configuration PMD"""
        try:
            logger.info(f"Connexion au Polar Verity Sense: {self.device_address}")
            self.set_status(DeviceStatus.CONNECTING)
            
            # Connexion BLE
            self.client = BleakClient(self.device_address)
            await self.client.connect()
            
            if not self.client.is_connected:
                raise Exception("Échec de la connexion BLE")
            
            self.is_connected = True
            self._running = True
            self.connection_timestamp = datetime.now()
            
            # Formatage de l'ID pour affichage
            self.formatted_device_id = self._format_device_id()
            
            # Vérifier les services disponibles
            await self._check_available_services()
            
            # Configurer PMD si disponible
            if self.pmd_available:
                await self._configure_pmd_streaming()
            
            # Récupérer les informations de l'appareil
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
        """Nettoie la connexion BLE"""
        self._running = False
        
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
            except Exception as e:
                logger.warning(f"Erreur lors de la déconnexion Verity: {e}")
        
        self.is_connected = False
        self.client = None
        self.pmd_available = False
        self.pmd_streaming = {'ppg': False, 'ppi': False, 'acc': False}
    
    async def _check_available_services(self):
        """Vérifie les services BLE disponibles"""
        try:
            services = await self.client.get_services()
            
            for service in services:
                if service.uuid.lower() == self.POLAR_PMD_SERVICE_UUID.lower():
                    self.pmd_available = True
                    logger.info("Service PMD Polar détecté sur Verity Sense")
                    break
            
            if not self.pmd_available:
                logger.info("Service PMD non disponible - utilisation des RR synthétiques")
        
        except Exception as e:
            logger.warning(f"Erreur vérification services Verity: {e}")
    
    async def _configure_pmd_streaming(self):
        """Configure le streaming PMD pour PPG et PPI"""
        try:
            logger.info("Configuration du streaming PMD pour Verity Sense")
            
            # Essayer d'activer le streaming PPI (RR intervals natifs)
            try:
                # Commande PMD pour PPI
                ppi_cmd = bytearray([0x01, 0x02, self.PMD_TYPE_PPI, 0x00, 0x01, 0x82, 0x00, 0x01, 0x01, 0x00, 0x00])
                await self.client.write_gatt_char(self.POLAR_PMD_CONTROL_UUID, ppi_cmd)
                self.pmd_streaming['ppi'] = True
                logger.info("✅ Streaming PPI (RR natifs) activé sur Verity Sense")
            except Exception as e:
                logger.warning(f"Impossible d'activer PPI: {e}")
            
            # Essayer d'activer le streaming PPG
            try:
                # Commande PMD pour PPG
                ppg_cmd = bytearray([0x01, 0x02, self.PMD_TYPE_PPG, 0x00, 0x01, 0x87, 0x00, 0x01, 0x01, 0x00, 0x00])
                await self.client.write_gatt_char(self.POLAR_PMD_CONTROL_UUID, ppg_cmd)
                self.pmd_streaming['ppg'] = True
                logger.info("✅ Streaming PPG activé sur Verity Sense")
            except Exception as e:
                logger.warning(f"Impossible d'activer PPG: {e}")
            
            # Activer l'accéléromètre
            try:
                acc_cmd = bytearray([0x01, 0x02, self.PMD_TYPE_ACC, 0x00, 0x01, 0x08, 0x00, 0x04, 0x01, 0x00, 0x00])
                await self.client.write_gatt_char(self.POLAR_PMD_CONTROL_UUID, acc_cmd)
                self.pmd_streaming['acc'] = True
                logger.info("✅ Streaming ACC activé sur Verity Sense")
            except Exception as e:
                logger.warning(f"Impossible d'activer ACC: {e}")
            
            # Si aucun streaming RR n'est disponible, garder la génération synthétique
            if not self.pmd_streaming['ppi'] and not self.pmd_streaming['ppg']:
                logger.info("⚠️ Aucun streaming RR natif - utilisation de RR synthétiques")
                self.synthetic_rr_enabled = True
        
        except Exception as e:
            logger.error(f"Erreur configuration PMD: {e}")
    
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
    
    async def start_data_collection(self):
        """Démarre la collecte de données avec traitement RSA et PPG"""
        if not self.is_connected:
            raise Exception("Appareil non connecté")
        
        try:
            logger.info("Démarrage collecte données Verity Sense avec traitement RSA et PPG")
            
            # Handler sécurisé pour HR
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
            
            # Démarrer le traitement périodique
            self.processing_task = asyncio.create_task(self._periodic_data_processor())
            
            logger.info("Collecte données Verity Sense démarrée avec processeur RSA et PPG")
        
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
        """Gestionnaire des notifications de fréquence cardiaque avec support RR amélioré"""
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
                
                # Génération de RR synthétiques si pas de RR natifs
                if self.synthetic_rr_enabled and not (flags & 0x10):
                    self._generate_synthetic_rr(heart_rate)
            
            # Extraire les intervalles RR natifs si présents
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
                        # Si on reçoit des RR natifs, désactiver la génération synthétique
                        self.synthetic_rr_enabled = False
                    logger.debug(f"RR natifs reçus via HR: {len(rr_intervals)} intervalles")
        
        except Exception as e:
            logger.error(f"Erreur traitement données Verity Sense: {e}")
    
    def _pmd_data_notification_handler(self, sender: int, data: bytearray):
        """Gestionnaire des notifications PMD avec support PPG et PPI"""
        try:
            if len(data) < 4:
                return
            
            data_type = data[0]
            timestamp = struct.unpack('<Q', data[1:9])[0] if len(data) >= 9 else time.time()
            
            if data_type == self.PMD_TYPE_PPI:  # RR intervals directs
                self._parse_ppi_data(data[9:], timestamp)
            elif data_type == self.PMD_TYPE_PPG:  # Signal PPG brut
                self._parse_ppg_data(data[9:], timestamp)
            elif data_type == self.PMD_TYPE_ACC:  # Accéléromètre
                self._parse_accelerometer_data(data[1:])
        
        except Exception as e:
            logger.error(f"Erreur traitement PMD Verity: {e}")
    
    def _generate_synthetic_rr(self, heart_rate: int):
        """Génère des intervalles RR synthétiques basés sur le BPM avec variabilité RSA"""
        try:
            current_time = time.time()
            
            # Calculer l'intervalle moyen en ms
            mean_rr = 60000.0 / heart_rate
            
            # Ajouter de la variabilité (HRV simulée)
            std_dev = mean_rr * self.synthetic_rr_quality
            
            # Générer plusieurs RR pour combler le temps écoulé
            time_elapsed = current_time - self.last_synthetic_time
            num_beats = max(1, int(time_elapsed * heart_rate / 60.0))
            
            synthetic_rr = []
            for i in range(num_beats):
                # Ajouter variabilité respiratoire (RSA simulée)
                # Oscillation sinusoïdale pour simuler l'effet de la respiration
                rsa_phase = ((
                                         current_time + i * mean_rr / 1000) % 4.0) / 4.0 * 2 * np.pi  # Cycle de 4 secondes (~15 rpm)
                rsa_amplitude = mean_rr * 0.03  # 3% d'amplitude RSA
                rsa_variation = rsa_amplitude * np.sin(rsa_phase)
                
                # RR avec variabilité normale + RSA
                rr = np.random.normal(mean_rr + rsa_variation, std_dev)
                rr = np.clip(rr, 300, 1500)  # Limiter aux valeurs physiologiques
                synthetic_rr.append(round(rr, 2))
            
            with self._data_lock:
                self.temp_rr_buffer.extend(synthetic_rr)
            
            self.last_synthetic_time = current_time
        
        except Exception as e:
            logger.error(f"Erreur génération RR synthétiques: {e}")
    
    def _parse_ppi_data(self, data: bytearray, timestamp: float):
        """Parse les données PPI (RR intervals) du PMD"""
        try:
            # Format PMD PPI: séquence d'intervalles en ms (uint16)
            i = 0
            rr_intervals = []
            
            while i < len(data) - 1:
                try:
                    rr_ms = struct.unpack('<H', data[i:i + 2])[0]
                    if 200 <= rr_ms <= 2000:
                        rr_intervals.append(float(rr_ms))
                    i += 2
                except:
                    break
            
            if rr_intervals:
                with self._data_lock:
                    self.temp_rr_buffer.extend(rr_intervals)
                    # Désactiver la génération synthétique
                    self.synthetic_rr_enabled = False
                
                logger.debug(f"PPI reçus: {len(rr_intervals)} intervalles")
        
        except Exception as e:
            logger.error(f"Erreur parsing PPI: {e}")
    
    def _parse_ppg_data(self, data: bytearray, timestamp: float):
        """Parse les données PPG brutes du PMD"""
        try:
            # Format PMD PPG: échantillons PPG (int16)
            i = 0
            ppg_samples = []
            
            while i < len(data) - 1:
                try:
                    ppg_value = struct.unpack('<h', data[i:i + 2])[0]
                    ppg_samples.append(ppg_value)
                    i += 2
                except:
                    break
            
            if ppg_samples:
                with self._data_lock:
                    self.ppg_buffer.extend(ppg_samples)
                    
                    # Limiter la taille du buffer
                    if len(self.ppg_buffer) > self.max_ppg_buffer_size:
                        self.ppg_buffer = self.ppg_buffer[-self.max_ppg_buffer_size:]
                
                # Traiter le signal PPG si on a assez d'échantillons
                current_time = time.time()
                if (len(self.ppg_buffer) >= self.ppg_sample_rate and
                        current_time - self.last_ppg_processing >= self.ppg_processing_interval):
                    self._process_ppg_signal()
                    self.last_ppg_processing = current_time
        
        except Exception as e:
            logger.error(f"Erreur parsing PPG: {e}")
    
    def _process_ppg_signal(self):
        """Traite le signal PPG pour extraire RR et respiration"""
        try:
            with self._data_lock:
                if len(self.ppg_buffer) < self.ppg_sample_rate:
                    return
                
                ppg_array = np.array(self.ppg_buffer)
            
            # 1. Filtrage passe-bande (0.7-4 Hz pour battements cardiaques)
            sos = scipy_signal.butter(3, [0.7, 4.0], btype='band',
                                      fs=self.ppg_sample_rate, output='sos')
            ppg_filtered = scipy_signal.sosfiltfilt(sos, ppg_array)
            
            # 2. Détection de pics (battements)
            min_distance = int(self.ppg_sample_rate * 0.3)  # Min 200 bpm
            peaks, properties = scipy_signal.find_peaks(ppg_filtered,
                                                        distance=min_distance,
                                                        prominence=np.std(ppg_filtered) * 0.3)
            
            if len(peaks) > 2:
                # 3. Calcul des intervalles RR
                peak_times = peaks / self.ppg_sample_rate
                rr_intervals = np.diff(peak_times) * 1000.0  # en ms
                
                # Filtrer les valeurs aberrantes
                valid_rr = rr_intervals[(rr_intervals >= 300) & (rr_intervals <= 1500)]
                
                if len(valid_rr) > 0:
                    with self._data_lock:
                        self.temp_rr_buffer.extend(valid_rr.tolist())
                    
                    # Désactiver la génération synthétique
                    self.synthetic_rr_enabled = False
                    
                    logger.debug(f"PPG: {len(valid_rr)} RR extraits du signal")
                
                # 4. Estimation de la respiration via variabilité des amplitudes
                if len(peaks) > 5:
                    peak_amplitudes = ppg_filtered[peaks]
                    
                    # Filtrage passe-bande pour respiration (0.1-0.5 Hz = 6-30 rpm)
                    try:
                        # Calcul de la fréquence d'échantillonnage des pics
                        peak_fs = len(peaks) / (len(ppg_array) / self.ppg_sample_rate)
                        
                        if peak_fs > 1.0:  # Assez de pics pour analyse
                            sos_resp = scipy_signal.butter(2, [0.1, 0.5], btype='band',
                                                           fs=peak_fs, output='sos')
                            resp_signal = scipy_signal.sosfiltfilt(sos_resp, peak_amplitudes)
                            
                            # Analyse spectrale pour trouver la fréquence respiratoire
                            f, pxx = scipy_signal.welch(resp_signal,
                                                        fs=peak_fs,
                                                        nperseg=min(len(resp_signal) // 2, 32))
                            
                            # Fréquence dominante dans la bande respiratoire
                            resp_band = (f >= 0.1) & (f <= 0.5)
                            if np.any(resp_band):
                                resp_freq_hz = f[resp_band][np.argmax(pxx[resp_band])]
                                resp_rpm = resp_freq_hz * 60
                                
                                # Mise à jour directe de la respiration
                                if 6 <= resp_rpm <= 30:
                                    self.update_breathing_metrics(
                                        breathing_rate=resp_rpm,
                                        amplitude=np.std(resp_signal),
                                        quality='ppg'
                                    )
                    except:
                        pass  # Ignorer les erreurs de traitement respiratoire
        
        except Exception as e:
            logger.error(f"Erreur traitement signal PPG: {e}")
    
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
                    
                    # Si aucun RR natif et génération synthétique active
                    if not rr_data and self.synthetic_rr_enabled:
                        # Forcer la génération pour maintenir le flux de données
                        self._generate_synthetic_rr(last_hr)
                        
                        # Récupérer les RR générés
                        with self._data_lock:
                            if self.temp_rr_buffer:
                                rr_data = self.temp_rr_buffer.copy()
                                self.temp_rr_buffer.clear()
                
                # Traiter RR (tous les intervalles de la seconde)
                if rr_data:
                    # Ajouter au calculateur RSA avec timestamp
                    self.rsa_calculator.add_rr_intervals(rr_data, current_time)
                    
                    # Ajouter le point de données RR
                    quality = 'synthetic' if self.synthetic_rr_enabled else 'good'
                    self.add_data_point(DataType.RR_INTERVALS, rr_data, quality=quality)
                    
                    # Le calcul RSA se fait automatiquement dans update_rr_metrics
                    # grâce à BaseCollectorWithRSA
                
                # Mettre à jour la batterie périodiquement (toutes les 30 secondes)
                if int(current_time) % 30 == 0:
                    asyncio.create_task(self._update_battery_level())
                
                # Log RSA si respiration détectée
                if self.breathing_metrics.frequency > 0:
                    source = "synthétique" if self.synthetic_rr_enabled else "natif"
                    logger.debug(f"Verity RSA ({source}): {self.breathing_metrics.frequency:.1f} rpm, "
                                 f"amplitude: {self.breathing_metrics.amplitude:.3f},")
                #     # Log RSA si respiration détectée
                # if self.breathing_metrics.frequency > 0:
                #     source = "synthétique" if self.synthetic_rr_enabled else "natif"
                #     logger.debug(f"Verity RSA ({source}): {self.breathing_metrics.frequency:.1f} rpm, "
                #                  f"amplitude: {self.breathing_metrics.amplitude:.3f}, "
                #                  f"qualité: {self.breathing_metrics.quality}")
            
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
    
    def get_simple_device_info(self) -> Dict[str, Any]:
        """Retourne les informations essentielles de l'appareil"""
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
            'pmd_available': self.pmd_available,
            'pmd_streaming': self.pmd_streaming.copy(),
            'synthetic_rr': self.synthetic_rr_enabled
        }
    
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
            'pmd_streaming': self.pmd_streaming.copy(),
            'synthetic_rr': self.synthetic_rr_enabled,
            'ppg_buffer_size': len(self.ppg_buffer),
            'rsa_breathing': {
                'rate_rpm': self.breathing_metrics.frequency,
                'amplitude': self.breathing_metrics.amplitude,
                'quality': self.breathing_metrics.quality,
                'buffer_size': len(self.rsa_calculator.rr_buffer),
                'window_seconds': self.rsa_calculator.breathing_window,
                'data_source': 'synthetic' if self.synthetic_rr_enabled else 'native'
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
            'ppg_data_rate': len(self.ppg_buffer),
            'pmd_available': self.pmd_available,
            'pmd_streaming': self.pmd_streaming.copy(),
            'rr_source': 'synthetic' if self.synthetic_rr_enabled else 'native',
            'rsa_status': {
                'breathing_detected': self.breathing_metrics.frequency > 0,
                'quality': self.breathing_metrics.quality,
                'buffer_fullness': f"{(len(self.rsa_calculator.rr_buffer) / self.rsa_calculator.rr_buffer.maxlen * 100):.0f}%"
            },
            'last_update': self.current_data.get('last_update'),
            'errors_count': self.connection_stats.get('errors_count', 0)
        }
    
    def get_accelerometer_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de l'accéléromètre"""
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
        """Nettoie toutes les ressources"""
        await super().cleanup()
        self._running = False
        
        # Nettoyer les données spécifiques au Verity
        self.temp_hr_buffer.clear()
        self.temp_rr_buffer.clear()
        self.ppg_buffer.clear()
        self.acc_buffer.clear()
        self.formatted_device_id = "Non connecté"
        self.connection_timestamp = None
        self.pmd_available = False
        self.pmd_streaming = {'ppg': False, 'ppi': False, 'acc': False}
        self.synthetic_rr_enabled = True