/**
 * Runtime configuration — ported from config.js with types.
 */

const PRODUCTION_API_URL = 'https://api.dubya.ai';
const LOCAL_API_URL = 'http://localhost:8000';

function isMockMode(): boolean {
  if (typeof window === 'undefined') return false;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  if ((window as any).TRINITY_MOCK_MODE) return true;
  const hostname = window.location.hostname;
  return hostname === 'localhost' || hostname === '127.0.0.1';
}

function getPreferredEnvironment(): string | null {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem('trinity_preferred_env');
}

function resolveApiUrl(): string {
  const preferred = getPreferredEnvironment();
  if (preferred === 'local') return LOCAL_API_URL;
  if (preferred === 'production') return PRODUCTION_API_URL;
  return isMockMode() ? LOCAL_API_URL : PRODUCTION_API_URL;
}

export const CONFIG = {
  APP_VERSION: '3.0.0',
  API_URL: resolveApiUrl(),
  PRODUCTION_API_URL,
  LOCAL_API_URL,

  // Timing
  TYPE_BASE_SPEED_MS: 15,
  HEALTH_CHECK_INTERVAL_MS: 30_000,
  AUTOSAVE_DEBOUNCE_MS: 2_000,

  // Limits
  CONTEXT_WINDOW_SIZE: 20,

  /** Switch between local and production */
  setAPIURL(url: string): void {
    this.API_URL = url;
  },

  switchEnvironment(env: 'local' | 'production'): void {
    const url = env === 'local' ? LOCAL_API_URL : PRODUCTION_API_URL;
    this.API_URL = url;
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('trinity_preferred_env', env);
    }
  },

  getApiHeaders(): Record<string, string> {
    return { 'Content-Type': 'application/json' };
  },
} as const satisfies Record<string, unknown>;

// Allow runtime mutation of API_URL
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export default CONFIG as any;
