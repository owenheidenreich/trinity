/**
 * useConnection hook tests.
 * Uses real timers (AbortSignal.timeout is incompatible with fake timers in jsdom).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// Mock config
vi.mock('../config', () => ({
  default: {
    API_URL: 'http://localhost:5000',
    HEALTH_CHECK_INTERVAL_MS: 600_000, // Very long to prevent interference
  },
}));

// Mock logger
vi.mock('../utils/logger', () => ({
  default: {
    debug: vi.fn(),
    info: vi.fn(),
    log: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

import { useConnection } from '../hooks/useConnection';

describe('useConnection', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('initializes as disconnected', () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok', model: 'llama' }),
    });

    const { result } = renderHook(() => useConnection());
    expect(result.current.status.connected).toBe(false);
    expect(result.current.status.model).toBeNull();
    expect(result.current.status.error).toBeNull();
  });

  it('connects after manual checkHealth call', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok', model: 'llama-3.1' }),
    });

    const { result } = renderHook(() => useConnection());

    await act(async () => {
      await result.current.checkHealth();
    });

    expect(result.current.status.connected).toBe(true);
    expect(result.current.status.model).toBe('llama-3.1');
    expect(result.current.status.error).toBeNull();
    expect(result.current.status.lastChecked).toBeTruthy();
  });

  it('sets error on health check failure', async () => {
    fetchSpy.mockRejectedValue(new Error('Connection refused'));

    const { result } = renderHook(() => useConnection());

    await act(async () => {
      await result.current.checkHealth();
    });

    expect(result.current.status.connected).toBe(false);
    expect(result.current.status.error).toContain('Connection refused');
  });

  it('sets error on non-ok response', async () => {
    fetchSpy.mockResolvedValue({ ok: false, status: 503 });

    const { result } = renderHook(() => useConnection());

    await act(async () => {
      await result.current.checkHealth();
    });

    expect(result.current.status.connected).toBe(false);
    expect(result.current.status.error).toContain('503');
  });

  it('calls /health endpoint with GET', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok' }),
    });

    const { result } = renderHook(() => useConnection());

    await act(async () => {
      await result.current.checkHealth();
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      'http://localhost:5000/health',
      expect.objectContaining({ method: 'GET' })
    );
  });

  it('handles null model in response', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok' }),
    });

    const { result } = renderHook(() => useConnection());

    await act(async () => {
      await result.current.checkHealth();
    });

    expect(result.current.status.connected).toBe(true);
    expect(result.current.status.model).toBeNull();
  });
});
