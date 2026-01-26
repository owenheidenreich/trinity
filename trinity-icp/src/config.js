// ============================================================================
// TRINITY CONFIGURATION
// ============================================================================
// Centralized configuration for API endpoints, feature flags, and environment
// detection. This module manages switching between different backends/models.
//
// ARCHITECTURE:
//   - All API requests route through ICP Backend Canister → Vercel Proxy → Akash
//   - Model switching will be implemented via this config (future: multiple Akash URLs)
//   - Local development bypasses ICP canister for faster iteration
// ============================================================================

// Current app version - increment to force cache clear on updates
const APP_VERSION = '2.6.1';

// Default production API URL (Vercel Proxy → Akash)
// Note: Akash URLs change on each deployment, Vercel proxy abstracts this
const DEFAULT_API_URL = 'https://vercel-proxy-swart-nine.vercel.app';

// ICP Backend Canister ID
const BACKEND_CANISTER_ID = 'au5zq-2qaaa-aaaal-qtowa-cai';

const CONFIG = {
    // =========================================================================
    // CORE SETTINGS
    // =========================================================================
    
    // Current API endpoint (can be changed at runtime)
    API_URL: DEFAULT_API_URL,
    
    // ICP Canister settings
    USE_CANISTER: true,  // Route through ICP backend canister for decentralization
    BACKEND_CANISTER_ID: BACKEND_CANISTER_ID,
    
    // Test mode - when true, uses mock responses instead of real API
    TEST_MODE: false,
    
    // Mock responses for TEST_MODE
    TEST_RESPONSES: [
        "I'm Trinity AI running in test mode. This is a mock response to verify the UI is working correctly.",
        "Test mode active! The frontend is functioning properly. Connect to a real backend for AI responses.",
        "Mock response #3: All systems nominal. Ready for production deployment."
    ],
    
    // =========================================================================
    // TIMING CONSTANTS
    // =========================================================================
    
    // Typing animation settings
    TYPE_ANIMATION_MAX_MS: 3000,    // Max time for typing animation
    TYPE_BASE_SPEED_MS: 15,         // Base speed per character
    
    // Mobile keyboard detection
    KEYBOARD_THRESHOLD: 0.75,       // Viewport ratio to detect keyboard
    
    // Health check interval
    HEALTH_CHECK_INTERVAL_MS: 30000, // 30 seconds
    
    // =========================================================================
    // ENVIRONMENT MANAGEMENT
    // =========================================================================
    
    // Available environments (populated at runtime)
    _availableEnvironments: {
        local: null,      // Set to 'http://localhost:8000' if local backend detected
        production: null  // Set to Vercel proxy URL
    },
    
    // Current active environment
    _currentEnvironment: 'production',
    
    // User's preferred environment (persisted to localStorage)
    getPreferredEnvironment() {
        return localStorage.getItem('trinity_preferred_env') || 'production';
    },
    
    setPreferredEnvironment(env) {
        localStorage.setItem('trinity_preferred_env', env);
    },
    
    // =========================================================================
    // ENVIRONMENT SWITCHING
    // =========================================================================
    
    /**
     * Set the API URL and optionally enable test mode
     * @param {string} url - The API URL to use
     * @param {boolean} testMode - Whether to enable test mode (mock responses)
     */
    setAPIURL(url, testMode = false) {
        this.API_URL = url;
        this.TEST_MODE = testMode;
        
        // Determine which environment this is
        if (url.includes('localhost') || url.includes('127.0.0.1')) {
            this._currentEnvironment = 'local';
        } else {
            this._currentEnvironment = 'production';
        }
        
        // Save preference
        this.setPreferredEnvironment(this._currentEnvironment);
        
        console.log(`⚙️ CONFIG: API_URL=${url}, TEST_MODE=${testMode}, env=${this._currentEnvironment}`);
    },
    
    /**
     * Switch to a different environment
     * @param {string} env - 'local' or 'production'
     * @returns {boolean} - Whether the switch was successful
     */
    switchEnvironment(env) {
        const url = this._availableEnvironments[env];
        if (!url) {
            console.warn(`⚠️ Environment '${env}' not available`);
            return false;
        }
        
        this.setAPIURL(url, false);
        return true;
    },
    
    // =========================================================================
    // VERSION MANAGEMENT (Cache Busting)
    // =========================================================================
    
    /**
     * Check if the app version has changed and clear cache if needed
     * @returns {boolean} - Whether the version is OK (no reload needed)
     */
    checkVersion() {
        const storedVersion = localStorage.getItem('trinity_app_version');
        
        if (storedVersion && storedVersion !== APP_VERSION) {
            console.log(`🔄 Version changed: ${storedVersion} → ${APP_VERSION}`);
            
            // Clear relevant caches
            localStorage.removeItem('trinity_app_version');
            
            // Clear any cached state that might be stale
            localStorage.removeItem('trinity_chat_cache');
            
            // Store new version
            localStorage.setItem('trinity_app_version', APP_VERSION);
            
            // Force reload to get fresh assets
            window.location.reload(true);
            return false;
        }
        
        // Store version if not set
        if (!storedVersion) {
            localStorage.setItem('trinity_app_version', APP_VERSION);
        }
        
        return true;
    },
    
    // =========================================================================
    // FUTURE: MODEL SWITCHING (Placeholder for Phase 2)
    // =========================================================================
    // This will be expanded to support multiple Akash deployments with different
    // models (e.g., TinyLlama for fast/cheap, Llama 70B for quality)
    //
    // _availableModels: {
    //     'tinyllama': 'https://akash-url-1.ingress.akash.pub',
    //     'llama70b': 'https://akash-url-2.ingress.akash.pub',
    // },
    //
    // switchModel(modelName) { ... }
    // =========================================================================
};

export default CONFIG;
