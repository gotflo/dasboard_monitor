/**
 * Base Manager - BioMedical Hub (Version corrigée avec navigation SPA robuste)
 */

class Base {
    constructor() {
        this.currentModule = null;
        this.isLoading = false;
        this.wsClient = null;
        this.modules = this.getAvailableModules();
        this.templateCache = new Map();
        this.loadedScripts = new Set();
        this.moduleInstances = new Map();
        this.devMode = this.isDevMode();
        this.persistentModules = new Set(['thermal_camera', 'thought_capture', 'neurosity', 'polar', 'gazepoint', 'home']);
        this.hiddenContainer = null;
        this.persistentScriptsLoaded = new Set();
        this.navigationHistory = [];
        this.homeModuleAlwaysActive = true; // Garder Home toujours actif

        this.init();
    }

    isDevMode() {
        return window.location.hostname === 'localhost' ||
               window.location.hostname === '127.0.0.1' ||
               window.location.search.includes('dev=true') ||
               window.DEV_MODE === true;
    }

    async init() {
        try {
            console.log('Initialisation Base SPA...');

            if (this.devMode) {
                console.log('MODE DÉVELOPPEMENT: Cache désactivé');
            }

            // Créer le container caché pour les modules persistants
            this.createHiddenContainer();

            this.setupNavigation();
            this.setupHistory();
            this.setupMobileMenu();
            this.initWebSocketClient();

            // Charger le module initial
            await this.loadInitialModule();

            console.log('Base SPA initialisé');
        } catch (error) {
            console.error('Erreur initialisation:', error);
            this.loadFallbackModule();
        }
    }

    createHiddenContainer() {
        if (!this.hiddenContainer) {
            this.hiddenContainer = document.createElement('div');
            this.hiddenContainer.id = 'hidden-modules';
            this.hiddenContainer.style.cssText = 'display: none; position: absolute; left: -9999px;';
            document.body.appendChild(this.hiddenContainer);
        }
    }

    getAvailableModules() {
        return {
            'home': {
                name: "Vue d'ensemble",
                subtitle: 'Monitoring unifié & Collecte de données',
                template: '/static/templates/modules/home.html',
                script: '/static/js/modules/home.js',
                style: '/static/css/modules/home.css',
            },
            'polar': {
                name: 'Polar Monitor',
                subtitle: 'H10 / Verity Sense',
                template: '/static/templates/modules/polar.html',
                script: '/static/js/modules/polar.js',
                style: '/static/css/modules/polar.css'
            },
            'neurosity': {
                name: 'EEG Crown',
                subtitle: 'Neurosity',
                template: '/static/templates/modules/neurosity.html',
                script: '/static/js/modules/neurosity.js',
                style: '/static/css/modules/neurosity.css'
            },
            'thermal_camera': {
                name: 'Caméra Thermique',
                subtitle: 'Détection IR',
                template: '/static/templates/modules/thermal_camera.html',
                script: '/static/js/modules/thermal_camera.js',
                style: '/static/css/modules/thermal_camera.css'
            },
            'gazepoint': {
                name: 'Gazepoint',
                subtitle: 'Suivi oculaire',
                template: '/static/templates/modules/gazepoint.html',
                script: '/static/js/modules/gazepoint.js',
                style: '/static/css/modules/gazepoint.css'
            },
            'thought_capture': {
                name: 'Capture de la Pensée',
                subtitle: 'Micro',
                template: '/static/templates/modules/thought_capture.html',
                script: '/static/js/modules/thought_capture.js',
                style: '/static/css/modules/thought_capture.css'
            }
        };
    }

    setupNavigation() {
        // Gestionnaire de clics sur les liens de navigation
        document.addEventListener('click', (e) => {
            const navLink = e.target.closest('[data-module]');
            if (navLink && !navLink.classList.contains('disabled')) {
                e.preventDefault();
                e.stopPropagation();

                const moduleName = navLink.getAttribute('data-module');

                console.log(`Navigation click: ${moduleName}`);
                this.navigateToModule(moduleName);
            }
        });

        // Raccourcis clavier
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeMobileMenu();
            }

            // Raccourci pour recharger le module actuel en dev
            if (this.devMode && e.ctrlKey && e.key === 'r') {
                e.preventDefault();
                this.reloadCurrentModule();
            }
        });
    }

    setupHistory() {
        // Gestion du bouton retour du navigateur
        window.addEventListener('popstate', (e) => {
            console.log('Popstate event:', e.state);

            if (e.state && e.state.module) {
                this.loadModule(e.state.module, false);
            } else {
                // Si pas d'état, charger le module par défaut
                this.loadModule('home', false);
            }
        });
    }

    setupMobileMenu() {
        if (!document.querySelector('.menu-toggle')) {
            const menuButton = document.createElement('button');
            menuButton.className = 'menu-toggle';
            menuButton.innerHTML = '<i class="fas fa-bars"></i>';
            menuButton.setAttribute('aria-label', 'Ouvrir le menu');
            document.body.appendChild(menuButton);

            menuButton.addEventListener('click', () => {
                this.toggleMobileMenu();
            });
        }

        document.querySelector('.main-content')?.addEventListener('click', () => {
            this.closeMobileMenu();
        });
    }

    async loadInitialModule() {
        // Déterminer le module initial basé sur l'URL
        const hash = window.location.hash.slice(1);
        let initialModule = 'home';

        if (hash && this.modules[hash]) {
            initialModule = hash;
        }

        console.log(`Module initial: ${initialModule}`);

        //  S'assurer que le module Home est toujours chargé en premier
        if (this.homeModuleAlwaysActive && initialModule !== 'home') {
            console.log('Chargement du module Home en arrière-plan');
            await this.loadModuleInBackground('home');
        }

        // Charger le module sans mettre à jour l'historique
        await this.loadModule(initialModule, false);

        // Mettre à jour l'URL si nécessaire
        this.updateURL(initialModule);
    }

    async loadModuleInBackground(moduleName) {
        if (!this.modules[moduleName]) {
            console.error(`Module "${moduleName}" introuvable`);
            return;
        }

        if (this.moduleInstances.has(moduleName)) {
            console.log(`Module ${moduleName} déjà chargé`);
            return;
        }

        try {
            console.log(`Chargement en arrière-plan du module: ${moduleName}`);

            // Créer un container caché
            const container = document.createElement('div');
            container.setAttribute('data-module', moduleName);
            container.style.display = 'none';
            this.hiddenContainer.appendChild(container);

            // Charger le template
            const templateHTML = await this.loadModuleTemplate(moduleName);
            container.innerHTML = templateHTML;

            // Charger les ressources
            await this.loadModuleResources(moduleName, container);

            console.log(`Module ${moduleName} chargé en arrière-plan`);
        } catch (error) {
            console.error(`Erreur chargement arrière-plan ${moduleName}:`, error);
        }
    }

    async navigateToModule(moduleName) {
        console.log(`Navigation vers: ${moduleName} (actuel: ${this.currentModule})`);

        // Éviter la navigation vers le même module
        if (moduleName === this.currentModule) {
            console.log('Déjà sur ce module');
            return;
        }

        // Éviter la navigation pendant le chargement
        if (this.isLoading) {
            console.log('Chargement en cours, navigation annulée');
            return;
        }

        // Sauvegarder dans l'historique de navigation
        this.navigationHistory.push({
            from: this.currentModule,
            to: moduleName,
            timestamp: Date.now()
        });

        // Nettoyer le module actuel
        await this.cleanupCurrentModule();

        // S'abonner au nouveau module via WebSocket
        if (this.wsClient && this.wsClient.isConnected) {
            try {
                await this.wsClient.subscribeToModule(moduleName);
            } catch (error) {
                console.warn(`Erreur abonnement module ${moduleName}:`, error);
            }
        }

        // Charger le nouveau module
        await this.loadModule(moduleName, true);

        // Fermer le menu mobile si ouvert
        this.closeMobileMenu();
    }

    async loadModule(moduleName, updateHistory = false) {
        console.log(`Chargement module: ${moduleName} (updateHistory: ${updateHistory})`);

        if (!this.modules[moduleName]) {
            console.error(`Module "${moduleName}" introuvable`);
            this.loadFallbackModule();
            return;
        }

        if (this.isLoading) {
            console.log('Chargement déjà en cours');
            return;
        }

        this.isLoading = true;

        const content = document.getElementById('main-content');
        if (!content) {
            console.error('Élément main-content introuvable');
            this.isLoading = false;
            return;
        }

        try {
            // Pour les modules persistants, vérifier le cache
            if (this.persistentModules.has(moduleName) && this.hiddenContainer) {
                const cachedModule = this.hiddenContainer.querySelector(`[data-module="${moduleName}"]`);

                if (cachedModule) {
                    console.log(`Restauration du module persistant: ${moduleName}`);

                    // Transition de sortie
                    content.style.opacity = '0';

                    await new Promise(resolve => setTimeout(resolve, 150));

                    // Déplacer le module caché vers le contenu principal
                    content.innerHTML = '';
                    content.appendChild(cachedModule);

                    // Transition d'entrée
                    requestAnimationFrame(() => {
                        content.style.opacity = '1';
                        content.style.transform = 'translateY(0)';
                    });

                    // Mettre à jour l'état
                    this.currentModule = moduleName;
                    this.updateActiveNavigation(moduleName);

                    if (updateHistory) {
                        this.updateURL(moduleName);
                    }

                    // Réinitialiser le module si nécessaire
                    const instance = this.moduleInstances.get(moduleName);
                    if (instance && typeof instance.onRestore === 'function') {
                        instance.onRestore();
                    } else if (instance && typeof instance.init === 'function') {
                        instance.init();
                    }

                    // Demander les données du module
                    this.requestModuleData(moduleName);

                    this.isLoading = false;
                    return;
                }
            }

            // Charger le module depuis zéro
            await this.loadModuleFromScratch(moduleName, content, updateHistory);

        } catch (error) {
            console.error('Erreur chargement module:', error);
            this.loadFallbackModule();
        } finally {
            this.isLoading = false;
            content.classList.remove('loading');
        }
    }

    async loadModuleFromScratch(moduleName, content, updateHistory) {
        console.log(`Chargement complet du module: ${moduleName}`);

        // Transition de sortie
        content.style.opacity = '0';
        content.style.transform = 'translateY(20px)';
        content.classList.add('loading');

        // Charger le template
        const templateHTML = await this.loadModuleTemplate(moduleName);

        // Attendre la transition
        await new Promise(resolve => setTimeout(resolve, 150));

        // Injecter le nouveau contenu
        content.innerHTML = templateHTML;

        // Marquer le contenu pour les modules persistants
        if (this.persistentModules.has(moduleName)) {
            const moduleContainer = content.firstElementChild;
            if (moduleContainer) {
                moduleContainer.setAttribute('data-module', moduleName);
            }
        }

        // Mettre à jour la navigation
        this.updateActiveNavigation(moduleName);

        // Charger les ressources du module
        await this.loadModuleResources(moduleName, content);

        // Transition d'entrée
        requestAnimationFrame(() => {
            content.style.opacity = '1';
            content.style.transform = 'translateY(0)';
        });

        // Mettre à jour l'état
        this.currentModule = moduleName;

        if (updateHistory) {
            this.updateURL(moduleName);
        }

        // Demander les données du module
        this.requestModuleData(moduleName);

        console.log(`Module "${moduleName}" chargé avec succès`);
    }

    updateURL(moduleName) {
        // Construire l'URL appropriée
        const url = moduleName === 'dashboard' ? '/' : `/#${moduleName}`;

        // Mettre à jour l'historique du navigateur
        const state = { module: moduleName, timestamp: Date.now() };

        if (window.location.href.endsWith(url) ||
            (moduleName === 'dashboard' && window.location.pathname === '/' && !window.location.hash)) {
            // L'URL est déjà correcte, juste mettre à jour l'état
            history.replaceState(state, '', url);
        } else {
            // Nouvelle entrée dans l'historique
            history.pushState(state, '', url);
        }

        console.log(`URL mise à jour: ${url}`);
    }

    async loadModuleResources(moduleName, container) {
        const module = this.modules[moduleName];

        // Charger le style
        if (module.style) {
            await this.loadModuleStyle(module.style);
        }

        // Charger le script
        if (module.script) {
            // Pour les modules persistants, ne charger qu'une seule fois
            if (this.persistentModules.has(moduleName) && this.persistentScriptsLoaded.has(moduleName)) {
                console.log(`Script déjà chargé pour le module persistant: ${moduleName}`);
                this.initializeModule(moduleName);
            } else {
                await this.loadModuleScript(module.script, moduleName);
                if (this.persistentModules.has(moduleName)) {
                    this.persistentScriptsLoaded.add(moduleName);
                }
            }
        }

        // Charger les scripts inline
        this.loadInlineScripts(container);
    }

    async loadModuleStyle(styleUrl) {
        const existingStyle = document.querySelector(`link[href="${styleUrl}"]`);
        if (existingStyle) {
            console.log(`Style déjà chargé: ${styleUrl}`);
            return;
        }

        return new Promise((resolve, reject) => {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = styleUrl;

            link.onload = () => {
                console.log(`Style chargé: ${styleUrl}`);
                resolve();
            };

            link.onerror = () => {
                console.error(`Erreur chargement style: ${styleUrl}`);
                reject(new Error(`Failed to load style: ${styleUrl}`));
            };

            document.head.appendChild(link);
        });
    }

    async loadModuleScript(scriptUrl, moduleName) {
        // Éviter le double chargement
        if (this.loadedScripts.has(scriptUrl)) {
            console.log(`Script déjà chargé: ${scriptUrl}`);
            this.initializeModule(moduleName);
            return;
        }

        // Vérifier les instances globales existantes
        if (this.checkExistingInstance(moduleName)) {
            this.loadedScripts.add(scriptUrl);
            return;
        }

        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = scriptUrl;
            script.async = false;

            script.onload = () => {
                console.log(`Script chargé: ${scriptUrl}`);
                this.loadedScripts.add(scriptUrl);
                this.initializeModule(moduleName);
                resolve();
            };

            script.onerror = () => {
                console.error(`Erreur chargement script: ${scriptUrl}`);
                reject(new Error(`Failed to load script: ${scriptUrl}`));
            };

            document.body.appendChild(script);
        });
    }

    checkExistingInstance(moduleName) {
        const globalInstances = {
            'polar': 'polarModuleInstance',
            'thermal_camera': 'thermalModuleInstance',
            'neurosity': 'neurosityModuleInstance',
            'gazepoint': 'gazepointModuleInstance',
            'thought_capture': 'thoughtCaptureModuleInstance'
        };

        const globalVar = globalInstances[moduleName];
        if (globalVar && window[globalVar]) {
            console.log(`Instance globale existante pour ${moduleName}`);
            this.moduleInstances.set(moduleName, window[globalVar]);
            window[globalVar].init();
            return true;
        }

        return false;
    }

    loadInlineScripts(container) {
        const scripts = container.querySelectorAll('script:not([src])');
        scripts.forEach(script => {
            const newScript = document.createElement('script');
            newScript.textContent = script.textContent;
            script.parentNode.replaceChild(newScript, script);
        });
    }

    initializeModule(moduleName) {
        const initFunctions = {
            'thought_capture': 'initThoughtCaptureModule',
            'polar': 'initPolarModule',
            'neurosity': 'initNeurosityModule',
            'thermal_camera': 'initThermalModule',
            'gazepoint': 'initGazepointModule',
            'home': () => {
                // Pour le module Home, on crée directement l'instance
                const container = document.querySelector(`[data-module="home"]`);
                if (container && window.HomeModule) {
                    const instance = new window.HomeModule(container);
                    instance.init();
                    return instance;
                }
                return null;
            }
        };

        const initFn = initFunctions[moduleName];

        if (initFn) {
            try {
                console.log(`Initialisation du module ${moduleName}`);

                let instance;
                if (typeof initFn === 'function') {
                    instance = initFn();
                } else if (window[initFn]) {
                    instance = window[initFn]();
                }

                if (instance) {
                    this.moduleInstances.set(moduleName, instance);

                    // Ajouter une méthode onRestore si elle n'existe pas
                    if (!instance.onRestore && instance.init) {
                        instance.onRestore = instance.init;
                    }
                }
            } catch (error) {
                console.error(`Erreur initialisation module ${moduleName}:`, error);
            }
        } else {
            console.warn(`Fonction d'initialisation non trouvée pour ${moduleName}`);
        }
    }

    async cleanupCurrentModule() {
        console.log(`Nettoyage du module: ${this.currentModule}`);

        if (this.persistentModules.has(this.currentModule)) {
            const content = document.getElementById('main-content');
            const moduleContent = content?.firstElementChild;

            if (moduleContent && this.hiddenContainer) {
                // Gérer les cas spéciaux avant de cacher
                this.handleModuleBeforeHiding(this.currentModule);

                // Déplacer vers le container caché
                moduleContent.setAttribute('data-module', this.currentModule);
                this.hiddenContainer.appendChild(moduleContent);
                console.log(`Module ${this.currentModule} déplacé vers le cache`);
            }
            return;
        }

        // Pour les modules non persistants, nettoyer complètement
        const instance = this.moduleInstances.get(this.currentModule);
        if (instance && typeof instance.cleanup === 'function') {
            await instance.cleanup();
            console.log(`Module ${this.currentModule} nettoyé`);
        }

        // Supprimer l'instance si non persistante
        if (!this.persistentModules.has(this.currentModule)) {
            this.moduleInstances.delete(this.currentModule);
        }
    }

    handleModuleBeforeHiding(moduleName) {
        const instance = this.moduleInstances.get(moduleName);

        if (!instance) return;

        // Gérer les cas spéciaux par module
        switch (moduleName) {
            case 'thought_capture':
                if (!instance.thought_isRecording && instance.thought_timerInterval) {
                    console.log('Arrêt du timer du module thought_capture');
                    instance.stopTimer();
                }
                break;

            case 'home':
                if (typeof instance.onHide === 'function') {
                    instance.onHide();
                }
                break;
        }
    }

    async loadModuleTemplate(moduleName) {
        // Utiliser le cache en production
        if (!this.devMode && this.templateCache.has(moduleName)) {
            return this.templateCache.get(moduleName);
        }

        const module = this.modules[moduleName];
        if (!module.template) {
            throw new Error(`Template non défini pour le module ${moduleName}`);
        }

        try {
            let templateURL = module.template;

            // Ajouter un timestamp en mode dev pour éviter le cache
            if (this.devMode) {
                templateURL += `?t=${Date.now()}`;
            }

            const response = await fetch(templateURL, {
                cache: this.devMode ? 'no-cache' : 'default'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const templateHTML = await response.text();

            // Mettre en cache en production
            if (!this.devMode) {
                this.templateCache.set(moduleName, templateHTML);
            }

            return templateHTML;

        } catch (error) {
            console.error(`Erreur chargement template ${moduleName}:`, error);
            return this.getFallbackContent(moduleName);
        }
    }

    reloadCurrentModule() {
        console.log(`Rechargement du module actuel: ${this.currentModule}`);

        // Vider le cache pour ce module
        this.templateCache.delete(this.currentModule);

        // Si c'est un module persistant, le retirer du cache
        if (this.persistentModules.has(this.currentModule) && this.hiddenContainer) {
            const cached = this.hiddenContainer.querySelector(`[data-module="${this.currentModule}"]`);
            if (cached) {
                cached.remove();
            }
        }

        // Recharger le module
        this.loadModule(this.currentModule, false);
    }

    clearTemplateCache() {
        this.templateCache.clear();
        console.log('Cache des templates vidé');
    }

    getFallbackContent(moduleName) {
        const module = this.modules[moduleName] || { name: 'Module inconnu', subtitle: '' };
        return `
            <div class="module-container">
                <div class="module-content">
                    <h1 class="module-title">${module.name}</h1>
                    ${module.subtitle ? `<p class="module-subtitle">${module.subtitle}</p>` : ''}
                    <div style="margin-top: 2rem; padding: 1rem; background: #fef3c7; border-radius: 8px; border: 1px solid #f59e0b;">
                        <p style="margin: 0; font-size: 0.875rem; color: #92400e;">
                            Impossible de charger le module. Veuillez rafraîchir la page.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    loadFallbackModule() {
        const content = document.getElementById('main-content');
        if (content) {
            content.innerHTML = this.getFallbackContent('home');
            this.currentModule = 'home';
            this.updateActiveNavigation('home');
        }
    }

    updateActiveNavigation(moduleName) {
        // Retirer la classe active de tous les liens
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });

        // Ajouter la classe active au lien actuel
        const activeLink = document.querySelector(`[data-module="${moduleName}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
        }
    }

    toggleMobileMenu() {
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) {
            sidebar.classList.toggle('open');
        }
    }

    closeMobileMenu() {
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) {
            sidebar.classList.remove('open');
        }
    }

    initWebSocketClient() {
        if (typeof WebSocketClient === 'undefined') {
            console.log('📱 Mode local: WebSocket non disponible');
            return;
        }

        try {
            this.wsClient = new WebSocketClient({
                autoConnect: true,
                reconnection: true,
                maxReconnectAttempts: 5,
                reconnectDelay: 1000
            });

            this.wsClient.on('connected', () => {
                console.log('WebSocket connecté');
                this.updateConnectionStatus(true);

                // Demander les données du module actuel
                this.requestModuleData(this.currentModule);
            });

            this.wsClient.on('disconnected', (data) => {
                console.log('WebSocket déconnecté:', data.reason);
                this.updateConnectionStatus(false);
            });

            this.wsClient.on('connection_error', (error) => {
                console.warn('Erreur WebSocket:', error);
                this.updateConnectionStatus(false);
            });

        } catch (error) {
            console.log('Mode local: WebSocket désactivé');
            this.wsClient = null;
        }
    }

    requestModuleData(moduleName) {
        if (!this.wsClient || !this.wsClient.isConnected) {
            console.log(`Mode local: pas de données pour ${moduleName}`);
            return;
        }

        const moduleEvents = {
            'polar': ['polar', 'get_hrv_data', {}],
            'neurosity': ['neurosity', 'get_neurosity_status', {}],
            'thermal_camera': ['thermal_camera', 'get_temperature_map', {}],
            'gazepoint': ['gazepoint', 'get_gaze_data', {}],
            'thought_capture': ['thought_capture', 'decode_intention', {}],
            'home': ['dashboard', 'get_devices_status', {}]
        };

        const eventData = moduleEvents[moduleName];
        if (eventData) {
            this.wsClient.emitToModule(...eventData);
        }
    }

    updateConnectionStatus(connected) {
        let statusIndicator = document.querySelector('.connection-status');
        if (!statusIndicator) {
            statusIndicator = document.createElement('div');
            statusIndicator.className = 'connection-status';
            statusIndicator.style.cssText = `
                position: fixed;
                top: 1rem;
                right: 1rem;
                z-index: 1001;
                padding: 0.5rem 1rem;
                border-radius: 20px;
                font-size: 0.875rem;
                font-weight: 500;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                pointer-events: none;
            `;
            document.body.appendChild(statusIndicator);
        }

        if (connected) {
            statusIndicator.innerHTML = `<i class="fas fa-circle" style="color: #10b981;"></i> WebSocket Connecté`;
            statusIndicator.style.background = '#dcfce7';
            statusIndicator.style.color = '#166534';

            // Masquer automatiquement après 3 secondes
            setTimeout(() => {
                if (statusIndicator) {
                    statusIndicator.style.opacity = '0';
                    setTimeout(() => {
                        if (statusIndicator && statusIndicator.parentNode) {
                            statusIndicator.parentNode.removeChild(statusIndicator);
                        }
                    }, 300);
                }
            }, 3000);
        } else {
            statusIndicator.innerHTML = `<i class="fas fa-circle" style="color: #ef4444;"></i> WebSocket Déconnecté`;
            statusIndicator.style.background = '#fef2f2';
            statusIndicator.style.color = '#991b1b';
        }
    }

    // Méthode pour obtenir des informations de debug
    getDebugInfo() {
        return {
            currentModule: this.currentModule,
            isLoading: this.isLoading,
            loadedScripts: Array.from(this.loadedScripts),
            persistentScriptsLoaded: Array.from(this.persistentScriptsLoaded),
            moduleInstances: Array.from(this.moduleInstances.keys()),
            navigationHistory: this.navigationHistory.slice(-10), // Dernières 10 navigations
            wsConnected: this.wsClient?.isConnected || false
        };
    }

    destroy() {
        console.log('Destruction du Base');

        // Nettoyer tous les modules
        this.moduleInstances.forEach((instance, moduleName) => {
            if (instance && typeof instance.cleanup === 'function') {
                instance.cleanup();
            }
        });

        this.moduleInstances.clear();

        // Déconnecter WebSocket
        if (this.wsClient) {
            this.wsClient.destroy();
        }

        // Vider les caches
        this.templateCache.clear();
        this.loadedScripts.clear();
        this.persistentScriptsLoaded.clear();

        // Retirer le container caché
        if (this.hiddenContainer && this.hiddenContainer.parentNode) {
            this.hiddenContainer.parentNode.removeChild(this.hiddenContainer);
        }
    }
}

// Initialisation au chargement du DOM
document.addEventListener('DOMContentLoaded', () => {
    try {
        window.dashboard = new Base();
        console.log('✅ Base BioMedical Hub SPA initialisé !');

        // Ajouter des commandes de debug en mode dev
        if (window.dashboard.devMode) {
            window.debugDashboard = () => console.table(window.dashboard.getDebugInfo());
            console.log('🛠️ Mode Dev: tapez debugDashboard() pour voir l\'état');
        }
    } catch (error) {
        console.error('❌ Erreur initialisation Base:', error);
    }
});

// Gestion globale des erreurs
window.addEventListener('error', (e) => {
    console.error('Erreur JavaScript:', e.error);
});

// Export pour les tests ou l'utilisation externe
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Base;
}