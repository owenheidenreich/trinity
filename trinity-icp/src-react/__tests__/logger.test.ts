/**
 * Logger utility tests.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// We need to test both dev and prod modes, so we import dynamically
describe('logger', () => {
  let consoleSpy: {
    log: ReturnType<typeof vi.spyOn>;
    debug: ReturnType<typeof vi.spyOn>;
    info: ReturnType<typeof vi.spyOn>;
    warn: ReturnType<typeof vi.spyOn>;
    error: ReturnType<typeof vi.spyOn>;
  };

  beforeEach(() => {
    consoleSpy = {
      log: vi.spyOn(console, 'log').mockImplementation(() => {}),
      debug: vi.spyOn(console, 'debug').mockImplementation(() => {}),
      info: vi.spyOn(console, 'info').mockImplementation(() => {}),
      warn: vi.spyOn(console, 'warn').mockImplementation(() => {}),
      error: vi.spyOn(console, 'error').mockImplementation(() => {}),
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('warn always logs regardless of environment', async () => {
    const { default: Logger } = await import('../utils/logger');
    Logger.warn('test warning', 'detail');
    expect(consoleSpy.warn).toHaveBeenCalledWith('[Trinity]', 'test warning', 'detail');
  });

  it('error always logs regardless of environment', async () => {
    const { default: Logger } = await import('../utils/logger');
    Logger.error('test error');
    expect(consoleSpy.error).toHaveBeenCalledWith('[Trinity]', 'test error');
  });

  it('exports debug, info, log, warn, error methods', async () => {
    const { default: Logger } = await import('../utils/logger');
    expect(Logger).toHaveProperty('debug');
    expect(Logger).toHaveProperty('info');
    expect(Logger).toHaveProperty('log');
    expect(Logger).toHaveProperty('warn');
    expect(Logger).toHaveProperty('error');
  });
});
