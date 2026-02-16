/**
 * usePassphrase — manages passphrase state for encrypted memory.
 *
 * Passphrase is held in React state only (never in localStorage).
 * Calls backend /api/passphrase/* endpoints for setup/unlock/lock.
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

export type PassphraseStatus = 'unknown' | 'no_passphrase' | 'locked' | 'unlocked';

interface UsePassphraseReturn {
  status: PassphraseStatus;
  loading: boolean;
  error: string | null;
  checkStatus: (buildAuthHeaders: (endpoint: string) => Promise<Record<string, string> | null>) => Promise<void>;
  setup: (passphrase: string, buildAuthHeaders: (endpoint: string) => Promise<Record<string, string> | null>) => Promise<boolean>;
  unlock: (passphrase: string, buildAuthHeaders: (endpoint: string) => Promise<Record<string, string> | null>) => Promise<boolean>;
  lock: (buildAuthHeaders: (endpoint: string) => Promise<Record<string, string> | null>) => Promise<void>;
  skipSetup: () => void;
}

export function usePassphrase(): UsePassphraseReturn {
  const [status, setStatus] = useState<PassphraseStatus>('unknown');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const checkStatus = useCallback(
    async (buildAuthHeaders: (endpoint: string) => Promise<Record<string, string> | null>) => {
      try {
        const headers = await buildAuthHeaders('/api/passphrase/status');
        if (!headers) return;

        const res = await fetchWithTimeout(`${CONFIG.API_URL}/api/passphrase/status`, {
          method: 'GET',
          headers,
        });
        const data = await res.json();

        if (data.session_unlocked) {
          setStatus('unlocked');
        } else if (data.has_passphrase) {
          setStatus('locked');
        } else {
          setStatus('no_passphrase');
        }
      } catch (err) {
        Logger.error('Passphrase status check failed:', err);
        // Network error: assume returning user whose passphrase is locked.
        // This avoids showing the "set new password" screen to existing users
        // when the backend is temporarily unreachable.
        setStatus('locked');
      }
    },
    []
  );

  const setup = useCallback(
    async (
      passphrase: string,
      buildAuthHeaders: (endpoint: string) => Promise<Record<string, string> | null>
    ): Promise<boolean> => {
      setLoading(true);
      setError(null);
      try {
        const headers = await buildAuthHeaders('/api/passphrase/setup');
        if (!headers) {
          setError('Not authenticated');
          setLoading(false);
          return false;
        }

        const res = await fetchWithTimeout(`${CONFIG.API_URL}/api/passphrase/setup`, {
          method: 'POST',
          headers,
          body: JSON.stringify({ passphrase }),
        });
        const data = await res.json();

        if (data.success) {
          setStatus('unlocked');
          setLoading(false);
          return true;
        } else if (res.status === 409) {
          // Canary already exists — this user already has a passphrase.
          // Transition to unlock flow instead of showing a confusing error.
          setStatus('locked');
          setError('Password already set. Please enter your existing password.');
          setLoading(false);
          return false;
        } else {
          setError(data.error || 'Setup failed');
          setLoading(false);
          return false;
        }
      } catch (err) {
        Logger.error('Passphrase setup failed:', err);
        setError('Network error');
        setLoading(false);
        return false;
      }
    },
    []
  );

  const unlock = useCallback(
    async (
      passphrase: string,
      buildAuthHeaders: (endpoint: string) => Promise<Record<string, string> | null>
    ): Promise<boolean> => {
      setLoading(true);
      setError(null);
      try {
        const headers = await buildAuthHeaders('/api/passphrase/unlock');
        if (!headers) {
          setError('Not authenticated');
          setLoading(false);
          return false;
        }

        const res = await fetchWithTimeout(`${CONFIG.API_URL}/api/passphrase/unlock`, {
          method: 'POST',
          headers,
          body: JSON.stringify({ passphrase }),
        });
        const data = await res.json();

        if (data.success) {
          setStatus('unlocked');
          setLoading(false);
          return true;
        } else {
          setError(data.error || 'Incorrect passphrase');
          setLoading(false);
          return false;
        }
      } catch (err) {
        Logger.error('Passphrase unlock failed:', err);
        setError('Network error');
        setLoading(false);
        return false;
      }
    },
    []
  );

  const lock = useCallback(
    async (buildAuthHeaders: (endpoint: string) => Promise<Record<string, string> | null>) => {
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
    []
  );

  const skipSetup = useCallback(() => {
    setStatus('unlocked');
  }, []);

  return { status, loading, error, checkStatus, setup, unlock, lock, skipSetup };
}

export default usePassphrase;
