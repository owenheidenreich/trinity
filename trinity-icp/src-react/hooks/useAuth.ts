/**
 * useAuth — deterministic Ed25519 identity from username + password.
 *
 * Auth overhaul: replaces random keypair generation with Argon2id-based
 * deterministic derivation. Same username + password = same identity
 * on any device.
 *
 * Flow:
 *   register(username, password) → derive keypair → register on-chain → store locally
 *   signIn(username, password)   → derive keypair → verify on-chain → store locally
 *   autoRestore()                → decrypt key from localStorage → resume session
 *
 * The Ed25519 signing and auth header logic is unchanged from the original.
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { useStore } from '../store';
import { deriveIdentitySeed, encryptForStorage } from '../utils/crypto';
import { registerUsername, lookupUsername } from '../services/canister';
import Logger from '../utils/logger';
import type { AuthState, Ed25519Identity, ICPAuthBundle, AuthHeaders } from '../types';

/** Get the ICP auth bundle from window */
function getICPAuth(): ICPAuthBundle | null {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (window as any).ICPAuth ?? null;
}

export function useAuth() {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    principal: null,
    authenticatedSince: null,
  });
  const [isInitializing, setIsInitializing] = useState(true);
  const [username, setUsername] = useState<string | null>(null);
  const identityRef = useRef<Ed25519Identity | null>(null);
  // Store the password in a ref for passphrase operations (never persisted)
  const passwordRef = useRef<string | null>(null);
  const storeSetAuth = useStore((s) => s.setAuthenticated);
  const storeClearAuth = useStore((s) => s.clearAuthentication);

  /** Get raw 32-byte public key hex (skip 12-byte DER prefix) */
  const getPublicKeyHex = useCallback((): string | null => {
    const identity = identityRef.current;
    if (!identity) return null;
    const derBytes = new Uint8Array(identity.getKeyPair().publicKey.toDer());
    const rawKey = derBytes.slice(12); // Skip DER prefix
    return Array.from(rawKey)
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  }, []);

  /** Sign a message with Ed25519, return hex signature */
  const signMessage = useCallback(async (message: string): Promise<string> => {
    const identity = identityRef.current;
    if (!identity) throw new Error('Not authenticated');
    const encoder = new TextEncoder();
    const signature = await identity.sign(encoder.encode(message));
    return Array.from(new Uint8Array(signature))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  }, []);

  /** Build authentication headers for a request */
  const buildAuthHeaders = useCallback(
    async (endpoint: string): Promise<AuthHeaders | null> => {
      if (!authState.isAuthenticated || !authState.principal) return null;

      const timestamp = Date.now().toString();
      const nonce = Array.from(crypto.getRandomValues(new Uint8Array(16)))
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');
      const message = `${authState.principal}:${timestamp}:${endpoint}:${nonce}`;
      const signature = await signMessage(message);
      const publicKeyHex = getPublicKeyHex();

      if (!publicKeyHex) return null;

      return {
        'Content-Type': 'application/json',
        'ICP-Principal': authState.principal,
        'ICP-Signature': signature,
        'ICP-Timestamp': timestamp,
        'ICP-PublicKey': publicKeyHex,
        'ICP-Nonce': nonce,
      };
    },
    [authState.isAuthenticated, authState.principal, signMessage, getPublicKeyHex]
  );

  /** Set authenticated state from an identity */
  const setAuthenticated = useCallback(
    (identity: Ed25519Identity, user: string) => {
      identityRef.current = identity;
      const principal = identity.getPrincipal().toText();
      const now = Date.now();
      setAuthState({ isAuthenticated: true, principal, authenticatedSince: now });
      setUsername(user);
      storeSetAuth(principal, now);
    },
    [storeSetAuth]
  );

  /**
   * Register a new account: derive identity, register username on-chain, store locally.
   */
  const register = useCallback(
    async (
      user: string,
      password: string,
    ): Promise<{ success: boolean; error?: string }> => {
      const ICPAuth = getICPAuth();
      if (!ICPAuth) return { success: false, error: 'Auth library not loaded' };

      try {
        // 1. Derive Ed25519 keypair from username + password
        const seed = await deriveIdentitySeed(password, user);
        const identity = ICPAuth.Ed25519KeyIdentity.fromSecretKey(seed);
        const principal = identity.getPrincipal().toText();

        // 2. Get public key hex for registration
        const derBytes = new Uint8Array(identity.getKeyPair().publicKey.toDer());
        const rawKey = derBytes.slice(12);
        const publicKeyHex = Array.from(rawKey)
          .map((b) => b.toString(16).padStart(2, '0'))
          .join('');

        // 3. Sign registration message
        const timestamp = Date.now().toString();
        const regMessage = `register:${user.toLowerCase()}:${principal}:${timestamp}`;
        const encoder = new TextEncoder();
        const sigBytes = await identity.sign(encoder.encode(regMessage));
        const signatureHex = Array.from(new Uint8Array(sigBytes))
          .map((b) => b.toString(16).padStart(2, '0'))
          .join('');

        // 4. Register on-chain
        await registerUsername(user, principal, publicKeyHex, signatureHex, timestamp);

        // 5. Encrypt and store private key locally
        const keyPair = identity.getKeyPair();
        const privateKeyHex = Array.from(new Uint8Array(keyPair.secretKey))
          .map((b) => b.toString(16).padStart(2, '0'))
          .join('');
        const encrypted = await encryptForStorage(privateKeyHex, password, user);
        localStorage.setItem('trinity_identity_key', encrypted);
        localStorage.setItem('trinity_principal', principal);
        localStorage.setItem('trinity_username', user.toLowerCase());

        // 6. Set authenticated state
        passwordRef.current = password;
        setAuthenticated(identity, user.toLowerCase());

        return { success: true };
      } catch (err) {
        Logger.error('Registration failed:', err);
        const message = err instanceof Error ? err.message : 'Registration failed';
        return { success: false, error: message };
      }
    },
    [setAuthenticated]
  );

  /**
   * Sign in: derive identity, verify principal matches on-chain registry.
   */
  const signIn = useCallback(
    async (
      user: string,
      password: string,
    ): Promise<{ success: boolean; error?: string }> => {
      const ICPAuth = getICPAuth();
      if (!ICPAuth) return { success: false, error: 'Auth library not loaded' };

      try {
        // 1. Derive Ed25519 keypair from username + password
        const seed = await deriveIdentitySeed(password, user);
        const identity = ICPAuth.Ed25519KeyIdentity.fromSecretKey(seed);
        const derivedPrincipal = identity.getPrincipal().toText();

        // 2. Look up registered principal on-chain
        const registeredPrincipal = await lookupUsername(user.toLowerCase());
        if (!registeredPrincipal) {
          return { success: false, error: 'Username not found' };
        }

        // 3. Compare — wrong password = wrong keypair = wrong principal
        if (derivedPrincipal !== registeredPrincipal) {
          return { success: false, error: 'Incorrect password' };
        }

        // 4. Store encrypted key locally
        const keyPair = identity.getKeyPair();
        const privateKeyHex = Array.from(new Uint8Array(keyPair.secretKey))
          .map((b) => b.toString(16).padStart(2, '0'))
          .join('');
        const encrypted = await encryptForStorage(privateKeyHex, password, user);
        localStorage.setItem('trinity_identity_key', encrypted);
        localStorage.setItem('trinity_principal', derivedPrincipal);
        localStorage.setItem('trinity_username', user.toLowerCase());

        // 5. Set authenticated state
        passwordRef.current = password;
        setAuthenticated(identity, user.toLowerCase());

        return { success: true };
      } catch (err) {
        Logger.error('Sign-in failed:', err);
        const message = err instanceof Error ? err.message : 'Sign-in failed';
        return { success: false, error: message };
      }
    },
    [setAuthenticated]
  );

  /** Get the current password (for passphrase setup/unlock) */
  const getPassword = useCallback((): string | null => {
    return passwordRef.current;
  }, []);

  /** Logout — clear identity and storage */
  const logout = useCallback(async () => {
    identityRef.current = null;
    passwordRef.current = null;
    localStorage.removeItem('trinity_identity_key');
    localStorage.removeItem('trinity_principal');
    localStorage.removeItem('trinity_username');
    setAuthState({ isAuthenticated: false, principal: null, authenticatedSince: null });
    setUsername(null);
    storeClearAuth();
  }, [storeClearAuth]);

  /** Import private key from hex (migration path for existing users) */
  const importKey = useCallback(
    async (privateKeyHex: string): Promise<{ success: boolean; principal?: string }> => {
      const ICPAuth = getICPAuth();
      if (!ICPAuth) return { success: false };

      try {
        const keyBytes = Uint8Array.from(
          privateKeyHex.match(/.{2}/g)!.map((byte) => parseInt(byte, 16))
        );
        const identity = ICPAuth.Ed25519KeyIdentity.fromSecretKey(keyBytes);
        const principal = identity.getPrincipal().toText();

        // Store unencrypted for now — user should claim a username to encrypt
        localStorage.setItem('trinity_identity_key', privateKeyHex);
        localStorage.setItem('trinity_principal', principal);

        identityRef.current = identity;
        const now = Date.now();
        setAuthState({ isAuthenticated: true, principal, authenticatedSince: now });
        storeSetAuth(principal, now);

        return { success: true, principal };
      } catch (err) {
        Logger.error('Key import failed:', err);
        return { success: false };
      }
    },
    [storeSetAuth]
  );

  /** Export private key as hex */
  const exportKey = useCallback((): {
    success: boolean;
    privateKeyHex?: string;
    principal?: string;
  } => {
    const identity = identityRef.current;
    if (!identity) return { success: false };

    const keyPair = identity.getKeyPair();
    const privateKeyHex = Array.from(new Uint8Array(keyPair.secretKey))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');

    return {
      success: true,
      privateKeyHex,
      principal: identity.getPrincipal().toText(),
    };
  }, []);

  /** Try restoring identity from localStorage (auto-login on return visit) */
  const initialize = useCallback(async (): Promise<AuthState> => {
    try {
      const ICPAuth = getICPAuth();
      if (!ICPAuth) {
        return { isAuthenticated: false, principal: null, authenticatedSince: null };
      }

      const savedKey = localStorage.getItem('trinity_identity_key');
      const savedPrincipal = localStorage.getItem('trinity_principal');
      const savedUsername = localStorage.getItem('trinity_username');

      if (!savedKey || !savedPrincipal) {
        return { isAuthenticated: false, principal: null, authenticatedSince: null };
      }

      // If key is encrypted (base64), we need the password to decrypt.
      // For auto-restore, we can only restore unencrypted (legacy) keys.
      // Encrypted keys require re-entering the password via sign-in.
      const isBase64 = /^[A-Za-z0-9+/]+=*$/.test(savedKey) && savedKey.length > 64;

      if (isBase64) {
        // Encrypted key — user must sign in again to decrypt.
        // But we know who they are, so pre-fill the username.
        if (savedUsername) {
          setUsername(savedUsername);
        }
        return { isAuthenticated: false, principal: null, authenticatedSince: null };
      }

      // Unencrypted hex key (legacy migration path)
      try {
        const keyBytes = Uint8Array.from(
          savedKey.match(/.{2}/g)!.map((byte) => parseInt(byte, 16))
        );
        const identity = ICPAuth.Ed25519KeyIdentity.fromSecretKey(keyBytes);
        const principal = identity.getPrincipal().toText();

        if (principal !== savedPrincipal) {
          Logger.warn('Principal mismatch during restore');
          return { isAuthenticated: false, principal: null, authenticatedSince: null };
        }

        identityRef.current = identity;
        const now = Date.now();
        const state: AuthState = { isAuthenticated: true, principal, authenticatedSince: now };
        setAuthState(state);
        if (savedUsername) setUsername(savedUsername);
        storeSetAuth(principal, now);
        return state;
      } catch {
        return { isAuthenticated: false, principal: null, authenticatedSince: null };
      }
    } finally {
      setIsInitializing(false);
    }
  }, [storeSetAuth]);

  // Auto-initialize on mount
  useEffect(() => {
    void initialize();
  }, [initialize]);

  return {
    ...authState,
    isInitializing,
    username,
    savedUsername: localStorage.getItem('trinity_username'),
    initialize,
    register,
    signIn,
    getPassword,
    logout,
    importKey,
    exportKey,
    signMessage,
    buildAuthHeaders,
    getPublicKeyHex,
  };
}

export default useAuth;
