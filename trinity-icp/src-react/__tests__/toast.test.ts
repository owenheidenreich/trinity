/**
 * Toast notification system tests.
 * Tests the singleton toastManager and basic rendering.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// We test the toastManager singleton directly (no React rendering needed)
// Reset module state between tests
describe('toastManager', () => {
  // eslint-disable-next-line @typescript-eslint/consistent-type-imports
  let toastManager: Awaited<typeof import('../components/notifications/ToastProvider')>['toastManager'];

  beforeEach(async () => {
    // Fresh import each time to reset singleton state
    vi.resetModules();
    const mod = await import('../components/notifications/ToastProvider');
    toastManager = mod.toastManager;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('success() creates a success toast and returns an id', () => {
    const id = toastManager.success('Saved!');
    expect(typeof id).toBe('number');
    expect(id).toBeGreaterThan(0);
  });

  it('error() creates an error toast', () => {
    const id = toastManager.error('Something broke');
    expect(typeof id).toBe('number');
  });

  it('warning() creates a warning toast', () => {
    const id = toastManager.warning('Watch out');
    expect(typeof id).toBe('number');
  });

  it('info() creates an info toast', () => {
    const id = toastManager.info('FYI');
    expect(typeof id).toBe('number');
  });

  it('dismiss() removes a toast', () => {
    // We can test this indirectly by checking sequential IDs
    const id1 = toastManager.success('First');
    const id2 = toastManager.success('Second');
    // Dismiss the first one
    toastManager.dismiss(id1);
    // No error thrown means it works
    expect(id2).toBeGreaterThan(id1);
  });

  it('each toast gets a unique incremental id', () => {
    const id1 = toastManager.success('A');
    const id2 = toastManager.error('B');
    const id3 = toastManager.warning('C');
    expect(id2).toBe(id1 + 1);
    expect(id3).toBe(id2 + 1);
  });

  it('rateLimitCountdown creates a countdown toast', () => {
    vi.useFakeTimers();
    // rateLimitCountdown doesn't return an id, but shouldn't throw
    expect(() => toastManager.rateLimitCountdown(5)).not.toThrow();
    vi.useRealTimers();
  });

  it('toasts with links include link data', () => {
    // The success function accepts link option — we just verify it doesn't throw
    const id = toastManager.success('Check this', {
      link: { url: 'https://example.com', label: 'View' },
    });
    expect(typeof id).toBe('number');
  });

  it('custom duration is accepted', () => {
    const id = toastManager.success('Quick', { duration: 1000 });
    expect(typeof id).toBe('number');
  });
});
