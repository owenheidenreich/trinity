// Entry point for bundling ICP authentication libraries
import { HttpAgent } from '@dfinity/agent';
import { Ed25519KeyIdentity } from '@dfinity/identity';
import { Principal } from '@dfinity/principal';

// Export individual items directly (esbuild IIFE will wrap these)
export {
  HttpAgent,
  Ed25519KeyIdentity,
  Principal
};

// Also export helpers
export function createAnonymousAgent(host) {
  return new HttpAgent({ host });
}

export function createAuthenticatedAgent(host, identity) {
  return new HttpAgent({ host, identity });
}
