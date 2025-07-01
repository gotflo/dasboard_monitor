#!/usr/bin/env python3
"""
Module Registry - BioMedical Hub
Registre centralisé pour la gestion des modules
"""

from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ModuleRegistry:
    """Registre centralisé pour tous les modules du système"""
    
    def __init__(self):
        self.modules = {}
        self._initialize_default_modules()
    
    def _initialize_default_modules(self):
        """Initialiser les modules par défaut"""
        self.modules = {
            'dashboard': {
                'name': 'Dashboard Principal',
                'description': 'Centre de contrôle principal',
                'icon': 'fas fa-dashboard_home',
                'enabled': True,
                'status': 'active',
                'version': '1.0.0',
                'category': 'core',
                'dependencies': [],
                'config': {},
                'created_at': datetime.now().isoformat()
            },
            'polar': {
                'name': 'Polar Monitor',
                'subtitle': 'H10 / Verity Sense',
                'description': 'Moniteur cardiaque et analyse ECG en temps réel',
                'icon': 'fas fa-heartbeat',
                'color': '#ff6b6b',
                'badge': 'ECG',
                'enabled': True,
                'status': 'ready',
                'version': '1.0.0',
                'category': 'sensor',
                'dependencies': ['bluetooth'],
                'features': [
                    'Fréquence cardiaque temps réel',
                    'Analyse de variabilité HRV',
                    'Détection d\'arythmies',
                    'Export des données ECG'
                ],
                'websocket_events': [
                    'start_monitoring',
                    'stop_monitoring',
                    'get_hrv_data'
                ],
                'config': {
                    'sample_rate': 130,
                    'device_type': 'H10',
                    'auto_connect': True
                },
                'created_at': datetime.now().isoformat()
            },
            'neurosity': {
                'name': 'Neurosity Crown',
                'subtitle': 'EEG Monitor',
                'description': 'Interface cerveau-ordinateur avec monitoring EEG en temps réel',
                'icon': 'fas fa-brain',
                'color': '#4ecdc4',
                'badge': 'EEG',
                'enabled': True,
                'status': 'ready',
                'version': '1.0.0',
                'category': 'sensor',
                'dependencies': ['neurosity_sdk', 'multiprocessing'],
                'features': [
                    'Monitoring calme et concentration',
                    'Ondes cérébrales (Delta, Theta, Alpha, Beta, Gamma)',
                    'Signal EEG brut 8 canaux',
                    'Qualité du signal par électrode',
                    'Enregistrement CSV des sessions',
                    'Export et analyse des données'
                ],
                'websocket_events': [
                    'connect',
                    'disconnect',
                    'start_monitoring',
                    'stop_monitoring',
                    'start_recording',
                    'stop_recording',
                    'get_sessions'
                ],
                'config': {
                    'channels': 8,
                    'sample_rate': 256,
                    'electrodes': ['CP3', 'C3', 'F5', 'PO3', 'PO4', 'F6', 'C4', 'CP4'],
                    'device_name': 'Crown',
                    'data_types': ['calm', 'focus', 'brainwaves', 'raw_eeg'],
                    'recording_format': 'csv',
                    'auto_connect': False,
                    'auto_start_monitoring': True
                },
                'api_routes': [
                    {'path': '/api/neurosity/status', 'method': 'GET'},
                    {'path': '/api/neurosity/sessions', 'method': 'GET'},
                    {'path': '/api/neurosity/download/<filename>', 'method': 'GET'},
                    {'path': '/api/neurosity/analyze/<filename>', 'method': 'GET'}
                ],
                'created_at': datetime.now().isoformat()
            },
            'thermal_camera': {
                'name': 'Caméra Thermique',
                'subtitle': 'Détection IR',
                'description': 'Imagerie thermique et analyse de température corporelle',
                'icon': 'fas fa-thermometer-half',
                'color': '#45b7d1',
                'badge': 'IR',
                'enabled': True,
                'status': 'ready',
                'version': '1.0.0',
                'category': 'sensor',
                'dependencies': ['opencv', 'thermal_sdk'],
                'features': [
                    'Imagerie infrarouge temps réel',
                    'Détection automatique de fièvre',
                    'Cartes de chaleur corporelle',
                    'Alertes de température'
                ],
                'websocket_events': [
                    'start_capture',
                    'stop_capture',
                    'get_temperature_map'
                ],
                'config': {
                    'resolution': '640x480',
                    'fps': 30,
                    'temperature_unit': 'celsius'
                },
                'created_at': datetime.now().isoformat()
            },
            'gazepoint': {
                'name': 'Gazepoint',
                'subtitle': 'Suivi oculaire',
                'description': 'Eye tracking et analyse d\'attention haute précision',
                'icon': 'fas fa-eye',
                'color': '#96ceb4',
                'badge': 'Eye',
                'enabled': True,
                'status': 'ready',
                'version': '1.0.0',
                'category': 'sensor',
                'dependencies': ['gazepoint_api'],
                'features': [
                    'Tracking oculaire haute précision',
                    'Heatmaps de fixation du regard',
                    'Analyse des patterns d\'attention',
                    'Évaluation cognitive'
                ],
                'websocket_events': [
                    'start_tracking',
                    'stop_tracking',
                    'get_gaze_data'
                ],
                'config': {
                    'sampling_rate': 60,
                    'calibration_points': 9,
                    'accuracy_threshold': 0.5
                },
                'created_at': datetime.now().isoformat()
            },
            'thought_capture': {
                'name': 'Capture de la Pensée',
                'subtitle': 'BCI Interface',
                'description': 'Interface cerveau-ordinateur pour décodage d\'intentions',
                'icon': 'fas fa-lightbulb',
                'color': '#feca57',
                'badge': 'BCI',
                'enabled': True,
                'status': 'ready',
                'version': '1.0.0',
                'category': 'experimental',
                'dependencies': ['bci_sdk', 'ml_models'],
                'features': [
                    'Décodage d\'intentions mentales',
                    'Contrôle par la pensée',
                    'Apprentissage neuronal adaptatif',
                    'Interface neuronale directe'
                ],
                'websocket_events': [
                    'start_thought_capture',
                    'stop_thought_capture',
                    'decode_intention'
                ],
                'config': {
                    'model_type': 'neural_network',
                    'training_sessions': 10,
                    'confidence_threshold': 0.8
                },
                'created_at': datetime.now().isoformat()
            }
        }
        
        logger.info(f"Registre des modules initialisé avec {len(self.modules)} modules")
    
    def register_module(self, module_id, module_config):
        """Enregistrer un nouveau module

        Args:
            module_id (str): Identifiant unique du module
            module_config (dict): Configuration du module

        Returns:
            bool: True si l'enregistrement a réussi
        """
        if module_id in self.modules:
            logger.warning(f"Module {module_id} déjà enregistré, mise à jour...")
        
        # Valider la configuration du module
        if not self._validate_module_config(module_config):
            logger.error(f"Configuration invalide pour le module {module_id}")
            return False
        
        # Ajouter les métadonnées
        module_config['created_at'] = datetime.now().isoformat()
        module_config['updated_at'] = datetime.now().isoformat()
        
        self.modules[module_id] = module_config
        logger.info(f"Module {module_id} enregistré avec succès")
        return True
    
    def unregister_module(self, module_id):
        """Désinscrire un module

        Args:
            module_id (str): Identifiant du module

        Returns:
            bool: True si la désinscription a réussi
        """
        if module_id not in self.modules:
            logger.warning(f"Module {module_id} non trouvé pour désinscription")
            return False
        
        del self.modules[module_id]
        logger.info(f"Module {module_id} désinscrit avec succès")
        return True
    
    def get_module(self, module_id):
        """Récupérer la configuration d'un module

        Args:
            module_id (str): Identifiant du module

        Returns:
            dict: Configuration du module ou None si non trouvé
        """
        return self.modules.get(module_id)
    
    def get_all_modules(self):
        """Récupérer tous les modules

        Returns:
            dict: Dictionnaire de tous les modules
        """
        return self.modules.copy()
    
    def get_modules_by_category(self, category):
        """Récupérer les modules par catégorie

        Args:
            category (str): Catégorie des modules

        Returns:
            dict: Modules de la catégorie spécifiée
        """
        return {
            module_id: module_config
            for module_id, module_config in self.modules.items()
            if module_config.get('category') == category
        }
    
    def get_enabled_modules(self):
        """Récupérer uniquement les modules activés

        Returns:
            dict: Modules activés
        """
        return {
            module_id: module_config
            for module_id, module_config in self.modules.items()
            if module_config.get('enabled', False)
        }
    
    def module_exists(self, module_id):
        """Vérifier si un module existe

        Args:
            module_id (str): Identifiant du module

        Returns:
            bool: True si le module existe
        """
        return module_id in self.modules
    
    def enable_module(self, module_id):
        """Activer un module

        Args:
            module_id (str): Identifiant du module

        Returns:
            bool: True si l'activation a réussi
        """
        if module_id not in self.modules:
            return False
        
        self.modules[module_id]['enabled'] = True
        self.modules[module_id]['updated_at'] = datetime.now().isoformat()
        logger.info(f"Module {module_id} activé")
        return True
    
    def disable_module(self, module_id):
        """Désactiver un module

        Args:
            module_id (str): Identifiant du module

        Returns:
            bool: True si la désactivation a réussi
        """
        if module_id not in self.modules:
            return False
        
        self.modules[module_id]['enabled'] = False
        self.modules[module_id]['updated_at'] = datetime.now().isoformat()
        logger.info(f"Module {module_id} désactivé")
        return True
    
    def activate_module(self, module_id):
        """Activer un module (changer le statut à 'active')

        Args:
            module_id (str): Identifiant du module

        Returns:
            bool: True si l'activation a réussi
        """
        if module_id not in self.modules:
            return False
        
        self.modules[module_id]['status'] = 'active'
        self.modules[module_id]['activated_at'] = datetime.now().isoformat()
        self.modules[module_id]['updated_at'] = datetime.now().isoformat()
        logger.info(f"Module {module_id} activé (statut: active)")
        return True
    
    def deactivate_module(self, module_id):
        """Désactiver un module (changer le statut à 'inactive')

        Args:
            module_id (str): Identifiant du module

        Returns:
            bool: True si la désactivation a réussi
        """
        if module_id not in self.modules:
            return False
        
        self.modules[module_id]['status'] = 'inactive'
        self.modules[module_id]['deactivated_at'] = datetime.now().isoformat()
        self.modules[module_id]['updated_at'] = datetime.now().isoformat()
        logger.info(f"Module {module_id} désactivé (statut: inactive)")
        return True
    
    def update_module_config(self, module_id, config_updates):
        """Mettre à jour la configuration d'un module

        Args:
            module_id (str): Identifiant du module
            config_updates (dict): Mises à jour de configuration

        Returns:
            bool: True si la mise à jour a réussi
        """
        if module_id not in self.modules:
            return False
        
        # Mettre à jour la configuration
        if 'config' not in self.modules[module_id]:
            self.modules[module_id]['config'] = {}
        
        self.modules[module_id]['config'].update(config_updates)
        self.modules[module_id]['updated_at'] = datetime.now().isoformat()
        
        logger.info(f"Configuration du module {module_id} mise à jour")
        return True
    
    def get_modules_count(self):
        """Récupérer le nombre total de modules

        Returns:
            int: Nombre de modules
        """
        return len(self.modules)
    
    def get_modules_summary(self):
        """Récupérer un résumé des modules

        Returns:
            dict: Résumé avec statistiques
        """
        enabled_count = len(self.get_enabled_modules())
        categories = {}
        statuses = {}
        
        for module_config in self.modules.values():
            category = module_config.get('category', 'unknown')
            status = module_config.get('status', 'unknown')
            
            categories[category] = categories.get(category, 0) + 1
            statuses[status] = statuses.get(status, 0) + 1
        
        return {
            'total_modules': len(self.modules),
            'enabled_modules': enabled_count,
            'disabled_modules': len(self.modules) - enabled_count,
            'categories': categories,
            'statuses': statuses,
            'timestamp': datetime.now().isoformat()
        }
    
    def _validate_module_config(self, config):
        """Valider la configuration d'un module

        Args:
            config (dict): Configuration à valider

        Returns:
            bool: True si la configuration est valide
        """
        required_fields = ['name', 'description', 'icon']
        
        for field in required_fields:
            if field not in config:
                logger.error(f"Champ requis manquant: {field}")
                return False
        
        # Valider les types
        if not isinstance(config.get('enabled', True), bool):
            logger.error("Le champ 'enabled' doit être un booléen")
            return False
        
        if config.get('features') and not isinstance(config['features'], list):
            logger.error("Le champ 'features' doit être une liste")
            return False
        
        if config.get('dependencies') and not isinstance(config['dependencies'], list):
            logger.error("Le champ 'dependencies' doit être une liste")
            return False
        
        return True
    
    def export_modules_config(self):
        """Exporter la configuration de tous les modules

        Returns:
            dict: Configuration complète
        """
        return {
            'modules': self.modules,
            'exported_at': datetime.now().isoformat(),
            'version': '1.0.0'
        }
    
    def import_modules_config(self, config_data):
        """Importer une configuration de modules

        Args:
            config_data (dict): Données de configuration

        Returns:
            bool: True si l'import a réussi
        """
        if 'modules' not in config_data:
            logger.error("Données d'import invalides: 'modules' manquant")
            return False
        
        imported_count = 0
        for module_id, module_config in config_data['modules'].items():
            if self._validate_module_config(module_config):
                self.modules[module_id] = module_config
                imported_count += 1
            else:
                logger.warning(f"Configuration invalide pour le module {module_id}, ignoré")
        
        logger.info(f"{imported_count} modules importés avec succès")
        return imported_count > 0