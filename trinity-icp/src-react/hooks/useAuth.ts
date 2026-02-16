/**
 * useAuth — Ed25519 key management as a React hook.
 * Ported from auth/authManager.js.
 *
 * Handles: key generation, import/export, signing, principal derivation.
 * Auth headers built per-request for ICP backend authentication.
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { useStore } from '../store';
import { encryptForStorage, decryptFromStorage, isEncrypted } from '../utils/crypto';
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
  const identityRef = useRef<Ed25519Identity | null>(null);
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

  /** Try restoring identity from localStorage */
  const restoreIdentity = useCallback(async (): Promise<boolean> => {
    const ICPAuth = getICPAuth();
    if (!ICPAuth) return false;

    const savedKey = localStorage.getItem('trinity_identity_key');
    const savedPrincipal = localStorage.getItem('trinity_principal');
    if (!savedKey || !savedPrincipal) return false;

    try {
      let keyHex = savedKey;

      // Decrypt if needed
      if (isEncrypted(savedKey)) {
        keyHex = await decryptFromStorage(savedKey);
      } else {
        // Migrate unencrypted key
        const encrypted = await encryptForStorage(savedKey);
        localStorage.setItem('trinity_identity_key', encrypted);
      }

      const keyBytes = Uint8Array.from(
        keyHex.match(/.{2}/g)!.map((byte) => parseInt(byte, 16))
      );
      const identity = ICPAuth.Ed25519KeyIdentity.fromSecretKey(keyBytes);
      const principal = identity.getPrincipal().toText();

      if (principal !== savedPrincipal) {
        Logger.warn('Principal mismatch during restore');
        return false;
      }

      identityRef.current = identity;
      const now = Date.now();
      const state: AuthState = {
        isAuthenticated: true,
        principal,
        authenticatedSince: now,
      };
      setAuthState(state);
      storeSetAuth(principal, now);
      return true;
    } catch (err) {
      Logger.error('Failed to restore identity:', err);
      return false;
    }
  }, [storeSetAuth]);

  /** Initialize auth — try restoring existing identity */
  const initialize = useCallback(async (): Promise<AuthState> => {
    try {
      const restored = await restoreIdentity();
      if (restored) {
        return {
          isAuthenticated: true,
          principal: identityRef.current?.getPrincipal().toText() ?? null,
          authenticatedSince: Date.now(),
        };
      }
      return { isAuthenticated: false, principal: null, authenticatedSince: null };
    } finally {
      setIsInitializing(false);
    }
  }, [restoreIdentity]);

  /** Generate new identity and login */
  const login = useCallback(async (): Promise<{
    success: boolean;
    principal?: string;
    privateKeyHex?: string;
  }> => {
    const ICPAuth = getICPAuth();
    if (!ICPAuth) return { success: false };

    try {
      const identity = ICPAuth.Ed25519KeyIdentity.generate();
      const principal = identity.getPrincipal().toText();
      const keyPair = identity.getKeyPair();
      const privateKeyHex = Array.from(new Uint8Array(keyPair.secretKey))
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');

      // Encrypt and store
      const encrypted = await encryptForStorage(privateKeyHex);
      localStorage.setItem('trinity_identity_key', encrypted);
      localStorage.setItem('trinity_principal', principal);

      identityRef.current = identity;
      const now = Date.now();
      setAuthState({ isAuthenticated: true, principal, authenticatedSince: now });
      storeSetAuth(principal, now);

      return { success: true, principal, privateKeyHex };
    } catch (err) {
      Logger.error('Login failed:', err);
      return { success: false };
    }
  }, [storeSetAuth]);

  /** Logout — clear identity and storage */
  const logout = useCallback(async () => {
    identityRef.current = null;
    localStorage.removeItem('trinity_identity_key');
    localStorage.removeItem('trinity_principal');
    setAuthState({ isAuthenticated: false, principal: null, authenticatedSince: null });
    storeClearAuth();
  }, [storeClearAuth]);

  /** Import private key from hex */
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

        const encrypted = await encryptForStorage(privateKeyHex);
        localStorage.setItem('trinity_identity_key', encrypted);
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

  // Auto-initialize on mount
  useEffect(() => {
    void initialize();
  }, [initialize]);

  return {
    ...authState,
    isInitializing,
    initialize,
    login,
    logout,
    importKey,
    exportKey,
    signMessage,
    buildAuthHeaders,
    getPublicKeyHex,
  };
}

export default useAuth;
