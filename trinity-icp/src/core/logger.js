// ============================================================================
// TRINITY LOGGER — Conditional console logging
// ============================================================================
// Replaces raw console.log calls with environment-aware logging.
// In production, debug logs are suppressed. Warnings/errors always show.
//
// Usage:
//   import Logger from './core/logger.js';
//   Logger.debug('Only in dev mode');
//   Logger.info('Always shown');
//   Logger.warn('Always shown');
//   Logger.error('Always shown');
// ============================================================================

const IS_DEV = typeof window !== 'undefined' && (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.protocol === 'file:' ||
    window.TRINITY_DEBUG === true
);

const Logger = {
    /** Debug-level — suppressed in production */
    debug: (...args) => { if (IS_DEV) console.debug('[Trinity]', ...args); },

    /** Info-level — always shown (operational messages) */
    info: (...args) => { if (IS_DEV) console.info('[Trinity]', ...args); },

    /** Log-level — same as info, suppressed in prod */
    log: (...args) => { if (IS_DEV) console.log('[Trinity]', ...args); },

    /** Warning-level — always shown */
    warn: (...args) => console.warn('[Trinity]', ...args),

    /** Error-level — always shown */
    error: (...args) => console.error('[Trinity]', ...args),

    /** Whether debug mode is active */
    isDebug: IS_DEV,
};

export default Logger;
