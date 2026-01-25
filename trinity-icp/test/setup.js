// Test setup file
import { vi } from 'vitest';

// Mock localStorage
global.localStorage = {
  store: {},
  getItem(key) {
    return this.store[key] || null;
  },
  setItem(key, value) {
    this.store[key] = String(value);
  },
  removeItem(key) {
    delete this.store[key];
  },
  clear() {
    this.store = {};
  }
};

// Mock window.ICPAuth
global.window = global.window || {};
global.window.ICPAuth = {
  Ed25519KeyIdentity: {
    generate: vi.fn(),
    fromSecretKey: vi.fn()
  },
  Principal: {
    fromText: vi.fn()
  },
  HttpAgent: vi.fn()
};

// Reset localStorage before each test
beforeEach(() => {
  global.localStorage.clear();
});
