/**
 * Environment-gated structured logger.
 * Replaces 253 console.log statements with controlled output.
 * Only warn/error shown in production.
 */
/* eslint-disable no-console */

const IS_DEV =
  typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.protocol === 'file:');

const PREFIX = '[Trinity]';

export const Logger = {
  /** Debug-only output (suppressed in production) */
  debug(...args: unknown[]): void {
    if (IS_DEV) console.debug(PREFIX, ...args);
  },

  /** Info-level output (suppressed in production) */
  info(...args: unknown[]): void {
    if (IS_DEV) console.info(PREFIX, ...args);
  },

  /** General log (suppressed in production) */
  log(...args: unknown[]): void {
    if (IS_DEV) console.log(PREFIX, ...args);
  },

  /** Warnings — always shown */
  warn(...args: unknown[]): void {
    console.warn(PREFIX, ...args);
  },

  /** Errors — always shown */
  error(...args: unknown[]): void {
    console.error(PREFIX, ...args);
  },

  /** Whether debug mode is active */
  get isDebug(): boolean {
    return IS_DEV;
  },
} as const;

export default Logger;
