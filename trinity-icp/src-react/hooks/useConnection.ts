/**
 * useConnection — health check polling for backend status.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import CONFIG from '../config';
import Logger from '../utils/logger';
import type { HealthCheckResponse } from '../types';

export interface ConnectionStatus {
  connected: boolean;
  model: string | null;
  lastChecked: number | null;
  error: string | null;
}

export function useConnection() {
  const [status, setStatus] = useState<ConnectionStatus>({
    connected: false,
    model: null,
    lastChecked: null,
    error: null,
  });
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const checkHealth = useCallback(async () => {
    try {
      const response = await fetch(`${CONFIG.API_URL}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(10_000),
      });

      if (!response.ok) throw new Error(`Health check failed: ${response.status}`);

      const data: HealthCheckResponse = await response.json();
      setStatus({
        connected: true,
        model: data.model ?? null,
        lastChecked: Date.now(),
        error: null,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      Logger.warn('Health check failed:', message);
      setStatus((prev) => ({
        ...prev,
        connected: false,
        lastChecked: Date.now(),
        error: message,
      }));
    }
  }, []);

  // Start/stop polling
  useEffect(() => {
    // Initial check after short delay (allow cold start)
    const initialTimer = setTimeout(() => void checkHealth(), 100);

    // Periodic polling
    intervalRef.current = setInterval(
      () => void checkHealth(),
      CONFIG.HEALTH_CHECK_INTERVAL_MS
    );

    return () => {
      clearTimeout(initialTimer);
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [checkHealth]);

  return { status, checkHealth };
}

export default useConnection;
