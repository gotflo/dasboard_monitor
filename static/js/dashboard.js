/**
 * Dashboard Manager - BioMedical Hub
 */

class Dashboard {
    constructor() {
        this.currentModule = 'dashboard';
        this.isLoading = false;
        this.wsClient = null;
        this.modules = this.getAvailableModules();
        this.templateCache = new Map();
        this.loadedScripts = new Set();
        this.moduleInstances = new Map();
        this.devMode = this.isDevMode();

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
            console.log('Initialisation Dashboard BioMedical Hub...');

            if (this.devMode) {
                console.log('🔧 MODE DÉVELOPPEMENT: Cache désactivé');
            }

            this.setupNavigation();
            this.setupHistory();
            this.setupMobileMenu();
            this.loadInitialModule();
            this.initWebSocketClient();

            console.log('Dashboard initialisé');
        } catch (error) {
            console.error('Erreur initialisation:', error);
            this.loadFallbackModule();
        }
    }

    getAvailableModules() {
        return {
            'dashboard': {
                name: 'BioMedical Hub',
                subtitle: 'Monitoring unifié & Collecte de données',
                template: '/static/templates/modules/dashboard.html'
            },
            'polar': {
                name: 'Polar Monitor',
                subtitle: 'H10 / Verity Sense',
                template: '/static/templates/modules/polar.html',
                script: '/static/js/modules/polar.js',
                style: '/static/css/modules/polar.css'
            },
            'eeg_crown': {
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
        document.addEventListener('click', (e) => {
            const navLink = e.target.closest('[data-module]');
            if (navLink) {
                e.preventDefault();
                const module = navLink.getAttribute('data-module');
                this.navigateToModule(module);
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeMobileMenu();
            }

            if (this.devMode && e.ctrlKey && e.key === 'r') {
                e.preventDefault();
                this.clearTemplateCache();
                this.loadModule(this.currentModule, false);
                console.log('Cache vidé et module rechargé');
            }
        });
    }

    setupHistory() {
        window.addEventListener('popstate', (e) => {
            if (e.state && e.state.module) {
                this.loadModule(e.state.module, false);
            } else {
                this.loadModule('dashboard', false);
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

    loadInitialModule() {
        const hash = window.location.hash.slice(1);
        if (hash && this.modules[hash]) {
            this.navigateToModule(hash);
        } else {
            this.loadModule('dashboard', false);
        }
    }

    async navigateToModule(moduleName) {
        if (moduleName === this.currentModule || this.isLoading) return;

        this.cleanupCurrentModule();

        console.log(`Navigation vers: ${moduleName}`);

        if (this.wsClient && this.wsClient.isConnected) {
            try {
                await this.wsClient.subscribeToModule(moduleName);
            } catch (error) {
                console.warn(`Erreur abonnement module ${moduleName}:`, error);
            }
        }

        this.loadModule(moduleName, true);
        this.closeMobileMenu();

        const url = moduleName === 'dashboard' ? '/' : `/#${moduleName}`;
        history.pushState({ module: moduleName }, '', url);
    }

    async loadModule(moduleName, updateHistory = false) {
        if (!this.modules[moduleName]) {
            console.error(`Module "${moduleName}" introuvable`);
            return;
        }

        if (this.isLoading) return;
        this.isLoading = true;

        const content = document.getElementById('main-content');
        if (!content) {
            console.error('Élément main-content introuvable');
            this.isLoading = false;
            return;
        }

        try {
            content.style.opacity = '0';
            content.style.transform = 'translateY(20px)';
            content.classList.add('loading');

            const templateHTML = await this.loadModuleTemplate(moduleName);

            setTimeout(() => {
                content.innerHTML = templateHTML;
                this.updateActiveNavigation(moduleName);
                this.loadModuleResources(moduleName, content);

                setTimeout(() => {
                    content.style.opacity = '1';
                    content.style.transform = 'translateY(0)';
                    content.classList.remove('loading');

                    this.currentModule = moduleName;
                    this.isLoading = false;

                    this.requestModuleData(moduleName);

                    console.log(`Module "${moduleName}" chargé`);
                }, 50);
            }, 150);

        } catch (error) {
            console.error('Erreur chargement module:', error);
            this.loadFallbackModule();
            this.isLoading = false;
            content.classList.remove('loading');
        }
    }

    async loadModuleResources(moduleName, container) {
        const module = this.modules[moduleName];

        if (module.style) {
            await this.loadModuleStyle(module.style);
        }

        if (module.script) {
            await this.loadModuleScript(module.script, moduleName);
        }

        this.loadInlineScripts(container);
    }

    async loadModuleStyle(styleUrl) {
        const existingStyle = document.querySelector(`link[href="${styleUrl}"]`);
        if (existingStyle) return;

        return new Promise((resolve, reject) => {
            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = styleUrl;

            link.onload = () => {
                console.log(`Style chargé: ${styleUrl}`);
                resolve();
            };

            link.onerror = () => {
                console.error(`Erreur style: ${styleUrl}`);
                reject(new Error(`Failed to load style: ${styleUrl}`));
            };

            document.head.appendChild(link);
        });
    }

    async loadModuleScript(scriptUrl, moduleName) {
        if (this.loadedScripts.has(scriptUrl)) {
            this.initializeModule(moduleName);
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
                console.error(`Erreur script: ${scriptUrl}`);
                reject(new Error(`Failed to load script: ${scriptUrl}`));
            };

            document.body.appendChild(script);
        });
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
            'eeg_crown': 'initEEGModule',
            'thermal_camera': 'initThermalModule',
            'gazepoint': 'initGazepointModule'
        };

        const initFn = initFunctions[moduleName];
        if (initFn && window[initFn]) {
            const instance = window[initFn]();
            if (instance) {
                this.moduleInstances.set(moduleName, instance);
            }
        }
    }

    cleanupCurrentModule() {
        const instance = this.moduleInstances.get(this.currentModule);

        if (instance && typeof instance.cleanup === 'function') {
            instance.cleanup();
            console.log(`Module ${this.currentModule} nettoyé`);
        }

        this.moduleInstances.delete(this.currentModule);
    }

    async loadModuleTemplate(moduleName) {
        if (!this.devMode && this.templateCache.has(moduleName)) {
            return this.templateCache.get(moduleName);
        }

        const module = this.modules[moduleName];
        if (!module.template) {
            throw new Error(`Template non défini pour le module ${moduleName}`);
        }

        try {
            let templateURL = module.template;
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

            if (!this.devMode) {
                this.templateCache.set(moduleName, templateHTML);
            }

            return templateHTML;
        } catch (error) {
            console.warn(`Template fallback pour ${moduleName}`);
            return this.getFallbackContent(moduleName);
        }
    }

    clearTemplateCache() {
        this.templateCache.clear();
    }

    getFallbackContent(moduleName) {
        const module = this.modules[moduleName];
        return `
            <div class="module-container">
                <div class="module-content">
                    <h1 class="module-title">${module.name}</h1>
                    ${module.subtitle ? `<p class="module-subtitle">${module.subtitle}</p>` : ''}
                    <div style="margin-top: 2rem; padding: 1rem; background: #fef3c7; border-radius: 8px; border: 1px solid #f59e0b;">
                        <p style="margin: 0; font-size: 0.875rem; color: #92400e;">
                            Template non chargé
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    loadFallbackModule() {
        const content = document.getElementById('main-content');
        if (content) {
            content.innerHTML = this.getFallbackContent('dashboard');
            this.currentModule = 'dashboard';
            this.updateActiveNavigation('dashboard');
        }
    }

    updateActiveNavigation(moduleName) {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });

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
            'dashboard': ['dashboard', 'request_dashboard_data', {}],
            'polar': ['polar', 'get_hrv_data', {}],
            'eeg_crown': ['eeg_crown', 'get_brain_waves', {}],
            'thermal_camera': ['thermal_camera', 'get_temperature_map', {}],
            'gazepoint': ['gazepoint', 'get_gaze_data', {}],
            'thought_capture': ['thought_capture', 'decode_intention', {}]
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

        const devModeText = this.devMode ? ' (Dev)' : '';

        if (connected) {
            statusIndicator.innerHTML = `<i class="fas fa-circle" style="color: #10b981;"></i> WebSocket Connecté`;
            statusIndicator.style.background = '#dcfce7';
            statusIndicator.style.color = '#166534';
        } else {
            statusIndicator.innerHTML = `<i class="fas fa-circle" style="color: #ef4444;"></i> WebSocket Déconnecté`;
            statusIndicator.style.background = '#fef2f2';
            statusIndicator.style.color = '#991b1b';
        }

        if (connected) {
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
        }
    }

    destroy() {
        this.moduleInstances.forEach((instance, moduleName) => {
            if (instance && typeof instance.cleanup === 'function') {
                instance.cleanup();
            }
        });

        this.moduleInstances.clear();

        if (this.wsClient) {
            this.wsClient.destroy();
        }

        this.templateCache.clear();
        this.loadedScripts.clear();
    }
}

// Initialisation
document.addEventListener('DOMContentLoaded', () => {
    try {
        window.dashboard = new Dashboard();
        console.log('Dashboard BioMedical Hub prêt !');
    } catch (error) {
        console.error('Erreur initialisation:', error);
    }
});

window.addEventListener('error', (e) => {
    console.error('Erreur JavaScript:', e.error);
});

if (typeof module !== 'undefined' && module.exports) {
    module.exports = Dashboard;
}