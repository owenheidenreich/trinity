// ============================================================================
// ENVIRONMENT DETECTION
// ============================================================================
// Detects development vs production and configures API URL accordingly.
// Checks for local Ollama backend in dev mode, falls back to production.
// ============================================================================

import CONFIG from '../config.js';

/**
 * Detect runtime environment and configure API URL.
 * - Development: file://, localhost, 127.0.0.1
 * - Production: dubya.ai, icp0.io, ic0.app
 */
export async function detectEnvironment() {
    console.log('🔍 Detecting environment...');

    const hostname = window.location.hostname;
    const protocol = window.location.protocol;

    const isDevelopment = protocol === 'file:' ||
                         hostname === 'localhost' ||
                         hostname === '127.0.0.1' ||
                         hostname === '';

    const isProductionDomain = hostname === 'dubya.ai' ||
                               hostname === 'www.dubya.ai' ||
                               hostname.includes('icp0.io') ||
                               hostname.includes('ic0.app');

    console.log('📍 Location:', { hostname, protocol, isDevelopment, isProductionDomain });

    const preferredEnv = CONFIG.getPreferredEnvironment();
    let localAvailable = false;

    // Only check for localhost backend in development mode
    if (isDevelopment) {
        console.log('🔧 Development mode - checking for local backend');
        try {
            const testResponse = await fetch('http://localhost:8000/health', {
                method: 'GET',
                mode: 'cors',
                cache: 'no-cache',
                signal: AbortSignal.timeout(2000)
            });

            if (testResponse.ok) {
                const health = await testResponse.json();
                localAvailable = true;
                CONFIG._availableEnvironments.local = 'http://localhost:8000';
                console.log('✅ Local backend available:', health.model);
            }
        } catch (err) {
            console.log('ℹ️ Local backend not available:', err.message);
        }
    } else {
        console.log('🌐 Production domain - local backend disabled');
    }

    // Set production URL (always available as fallback)
    const prodURL = CONFIG.API_URL;
    CONFIG._availableEnvironments.production = prodURL;
    console.log('✅ Production backend:', prodURL);

    // Determine which environment to use
    if (isProductionDomain) {
        console.log('🔒 Production domain - using Akash backend');
        CONFIG.setAPIURL(prodURL);
    } else if (preferredEnv === 'local' && localAvailable) {
        console.log('🔧 Using preferred LOCAL environment');
        CONFIG.setAPIURL('http://localhost:8000');
    } else if (preferredEnv === 'production') {
        console.log('🔧 Using preferred PRODUCTION environment');
        CONFIG.setAPIURL(prodURL);
    } else if (localAvailable) {
        console.log('🔧 Defaulting to LOCAL environment');
        CONFIG.setAPIURL('http://localhost:8000');
    } else {
        console.log('🔧 Using PRODUCTION environment');
        CONFIG.setAPIURL(prodURL);
    }

    console.log('🎯 Final API URL:', CONFIG.API_URL);

    return isDevelopment;
}
