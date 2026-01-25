// ============================================================================
// Trinity Frontend - CONFIG Module
// ============================================================================
// Environment detection, API URLs, and application constants
// ============================================================================

export const CONFIG = {
    // Application version (MUST match meta tag in index.html)
    APP_VERSION: '2.0.1',
    
    // Test mode detection (set by environment check at startup)
    TEST_MODE: false,
    _detectedURL: null,
    _availableEnvironments: {
        local: null,  // Will be set if localhost:8000 is available
        production: null  // Will be set to Akash URL
    },
    _currentEnvironment: null,  // 'local' or 'production'
    
    // Check if user has an outdated cached version
    checkVersion() {
        const metaVersion = document.querySelector('meta[name="app-version"]')?.getAttribute('content');
        const cachedVersion = localStorage.getItem('trinity_app_version');
        
        console.log('📦 Version Check:', { 
            current: this.APP_VERSION, 
            meta: metaVersion,
            cached: cachedVersion 
        });
        
        // If versions don't match, clear cache and reload
        if (cachedVersion && cachedVersion !== this.APP_VERSION) {
            console.warn('⚠️ Version mismatch detected! Clearing cache...');
            console.log(`  Old version: ${cachedVersion}`);
            console.log(`  New version: ${this.APP_VERSION}`);
            
            // Clear all caches except auth credentials
            const authKey = localStorage.getItem('trinity_identity_key');
            const authPrincipal = localStorage.getItem('trinity_principal');
            
            // Clear localStorage except auth
            localStorage.clear();
            
            // Restore auth if it existed
            if (authKey) localStorage.setItem('trinity_identity_key', authKey);
            if (authPrincipal) localStorage.setItem('trinity_principal', authPrincipal);
            
            // Update version
            localStorage.setItem('trinity_app_version', this.APP_VERSION);
            
            // Force hard reload to bypass all caches
            console.log('🔄 Forcing reload to clear caches...');
            window.location.reload(true);
            return false; // Signal that reload is happening
        }
        
        // Store current version
        localStorage.setItem('trinity_app_version', this.APP_VERSION);
        return true; // Version OK, continue normal startup
    },
    
    // API URL with automatic test/production detection
    get API_URL() {
        // If already detected, return cached value
        if (this._detectedURL) {
            return this._detectedURL;
        }
        
        // Production URLs
        const hostname = window.location.hostname;
        if (hostname === 'trinityai.cc' ||
            hostname === 'www.trinityai.cc' ||
            hostname.includes('icp0.io')) {
            this._detectedURL = 'https://api.trinityai.cc';
            return this._detectedURL;
        }
        
        // Default to production Akash for other domains
        this._detectedURL = 'http://u2k74jdr358rt168vo6bmi8mas.ingress.akashprovid.com';
        return this._detectedURL;
    },
    
    // Set URL after environment detection
    setAPIURL(url, isTestMode = false) {
        this._detectedURL = url;
        this.TEST_MODE = isTestMode;
        this._currentEnvironment = isTestMode ? 'local' : 'production';
        console.log(`🔧 setAPIURL called: url="${url}", isTestMode=${isTestMode}`);
        console.log(`🔧 Environment: ${isTestMode ? 'TEST (local)' : 'PRODUCTION'}`);
        console.log(`🌐 API URL: ${url}`);
        console.log(`🔍 TEST_MODE is now: ${this.TEST_MODE}`);
    },
    
    // Switch between environments
    switchEnvironment(env) {
        const url = this._availableEnvironments[env];
        if (!url) {
            console.error(`Environment ${env} not available`);
            return false;
        }
        this.setAPIURL(url, false);  // Never use test mode - always make real API calls
        localStorage.setItem('trinity_preferred_env', env);
        return true;
    },
    
    // Get preferred environment from localStorage
    getPreferredEnvironment() {
        return localStorage.getItem('trinity_preferred_env') || null;
    },

    // Timing constants
    HEALTH_CHECK_INTERVAL_MS: 30000,
    KEYBOARD_THRESHOLD: 0.75,
    TYPE_ANIMATION_MAX_MS: 1500,
    TYPE_BASE_SPEED_MS: 20,

    // Test responses (for TEST_MODE)
    TEST_RESPONSES: [
        "Hello! I'm Trinity, your decentralized AI assistant. I'm running in test mode - all responses are simulated.",
        "This is a test response. In production, I'd be calling the Llama 70B model on Akash Network.",
        "Test mode is active. Your chats are saved to localStorage instead of Akash disk.",
        "I'm simulating an AI response. Switch to production mode to use the real LLM!",
        "This is response #5 in test mode. Pretty cool, right?",
        "Test response #6. Your chats are being autosaved to localStorage.",
        "Hello from test mode! I'm just a friendly placeholder.",
        "Test mode response #8. Try asking me anything!",
        "I'm response #9 in the test sequence.",
        "Final test response (#10). Cycling back to start..."
    ]
};

export default CONFIG;
