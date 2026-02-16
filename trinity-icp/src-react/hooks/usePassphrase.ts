/**
 * usePassphrase — simplified passphrase management.
 *
 * Auth overhaul: the login password IS the passphrase. This hook is now
 * an internal implementation detail, not a user-facing flow. After
 * register() or signIn(), the auth layer calls setupOrUnlock() automatically.
 *
 * The backend passphrase endpoints (/api/passphrase/setup, /unlock) remain
 * unchanged — this hook just auto-calls them with the user's password.
 */
import { useState, useCallback } from 'react';
import CONFIG from '../config';
import Logger from '../utils/logger';

/** Fetch with an AbortController timeout (default 15s). */
function fetchWithTimeout(
  url: string,
  opts: RequestInit,
  timeoutMs = 15_000,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...opts, signal: controller.signal }).finally(() =>
    clearTimeout(timer),
  );
}

export type PassphraseStatus = 'unknown' | 'locked' | 'unlocked';

interface UsePassphraseReturn {
  status: PassphraseStatus;
  loading: boolean;
  error: string | null;
  /** Auto-setup or unlock the passphrase after authentication. */
  setupOrUnlock: (
    password: string,
    buildAuthHeaders: (endpoint: string) => Promise<Record<string, string> | null>,
  ) => Promise<boolean>;
  /** Lock the session (logout). */
  lock: (
    buildAuthHeaders: (endpoint: string) => Promise<Record<string, string> | null>,
  ) => Promise<void>;
}

export function usePassphrase(): UsePassphraseReturn {
  const [status, setStatus] = useState<PassphraseStatus>('unknown');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Auto-setup or unlock: check status, then call setup or unlock as needed.
   * Called automatically after register() or signIn() — not user-facing.
   */
  const setupOrUnlock = useCallback(
    async (
      password: string,
      buildAuthHeaders: (endpoint: string) => Promise<Record<string, string> | null>,
    ): Promise<boolean> => {
      setLoading(true);
      setError(null);

      try {
        // 1. Check current status
        const statusHeaders = await buildAuthHeaders('/api/passphrase/status');
        if (!statusHeaders) {
          setError('Not authenticated');
          setLoading(false);
          return false;
        }

        let hasPassphrase = false;
        let sessionUnlocked = false;

        try {
          const statusRes = await fetchWithTimeout(
            `${CONFIG.API_URL}/api/passphrase/status`,
            { method: 'GET', headers: statusHeaders },
          );
          const statusData = await statusRes.json();
          hasPassphrase = statusData.has_passphrase ?? false;
          sessionUnlocked = statusData.session_unlocked ?? false;
        } catch {
          // Network error — assume locked (returning user)
          hasPassphrase = true;
          sessionUnlocked = false;
        }

        // Already unlocked — nothing to do
        if (sessionUnlocked) {
          setStatus('unlocked');
          setLoading(false);
          return true;
        }

        // 2. Setup or unlock
        const endpoint = hasPassphrase ? '/api/passphrase/unlock' : '/api/passphrase/setup';
        const headers = await buildAuthHeaders(endpoint);
        if (!headers) {
          setError('Not authenticated');
          setLoading(false);
          return false;
        }

        const res = await fetchWithTimeout(
          `${CONFIG.API_URL}${endpoint}`,
          {
            method: 'POST',
            headers,
            body: JSON.stringify({ passphrase: password }),
          },
        );
        const data = await res.json();

        if (data.success) {
          setStatus('unlocked');
          setLoading(false);
          return true;
        }

        // If setup returned 409 (canary already exists), try unlock instead
        if (res.status === 409) {
          const unlockHeaders = await buildAuthHeaders('/api/passphrase/unlock');
          if (!unlockHeaders) {
            setError('Not authenticated');
            setLoading(false);
            return false;
          }

          const unlockRes = await fetchWithTimeout(
            `${CONFIG.API_URL}/api/passphrase/unlock`,
            {
              method: 'POST',
              headers: unlockHeaders,
              body: JSON.stringify({ passphrase: password }),
            },
          );
          const unlockData = await unlockRes.json();

          if (unlockData.success) {
            setStatus('unlocked');
            setLoading(false);
            return true;
          }

          setError(unlockData.error || 'Failed to unlock');
          setLoading(false);
          return false;
        }

        setError(data.error || 'Passphrase setup failed');
        setLoading(false);
        return false;
      } catch (err) {
        Logger.error('Passphrase setup/unlock failed:', err);
        setError('Network error');
        setLoading(false);
        return false;
      }
    },
    [],
  );

  const lock = useCallback(
    async (
      buildAuthHeaders: (endpoint: string) => Promise<Record<string, string> | null>,
    ) => {
      try {
        const headers = await buildAuthHeaders('/api/passphrase/lock');
        if (!headers) return;

        await fetchWithTimeout(`${CONFIG.API_URL}/api/passphrase/lock`, {
          method: 'POST',
          headers,
        });
        setStatus('locked');
      } catch (err) {
        Logger.error('Passphrase lock failed:', err);
      }
    },
    [],
  );

  return { status, loading, error, setupOrUnlock, lock };
}

export default usePassphrase;
