// ============================================================================
// ENVIRONMENT DETECTION
// ============================================================================
// Detects development vs production and configures API URL accordingly.
// Checks for local Ollama backend in dev mode, falls back to production.
// ============================================================================

import CONFIG from '../config.js';
import Logger from './logger.js';

/**
 * Detect runtime environment and configure API URL.
 * - Development: file://, localhost, 127.0.0.1
 * - Production: dubya.ai, icp0.io, ic0.app
 */
export async function detectEnvironment() {
    Logger.debug('Detecting environment...');

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

    Logger.debug('Location:', { hostname, protocol, isDevelopment, isProductionDomain });

    const preferredEnv = CONFIG.getPreferredEnvironment();
    let localAvailable = false;

    // Only check for localhost backend in development mode
    if (isDevelopment) {
        Logger.debug('Development mode - checking for local backend');
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
                Logger.debug('Local backend available:', health.model);
            }
        } catch (err) {
            Logger.debug('Local backend not available:', err.message);
        }
    } else {
        Logger.debug('Production domain - local backend disabled');
    }

    // Set production URL (always available as fallback)
    const prodURL = CONFIG.API_URL;
    CONFIG._availableEnvironments.production = prodURL;
    Logger.debug('Production backend:', prodURL);

    // Determine which environment to use
    if (isProductionDomain) {
        Logger.debug('Production domain - using Akash backend');
        CONFIG.setAPIURL(prodURL);
    } else if (preferredEnv === 'local' && localAvailable) {
        Logger.debug('Using preferred LOCAL environment');
        CONFIG.setAPIURL('http://localhost:8000');
    } else if (preferredEnv === 'production') {
        Logger.debug('Using preferred PRODUCTION environment');
        CONFIG.setAPIURL(prodURL);
    } else if (localAvailable) {
        Logger.debug('Defaulting to LOCAL environment');
        CONFIG.setAPIURL('http://localhost:8000');
    } else {
        Logger.debug('Using PRODUCTION environment');
        CONFIG.setAPIURL(prodURL);
    }

    Logger.debug('Final API URL:', CONFIG.API_URL);

    return isDevelopment;
}
