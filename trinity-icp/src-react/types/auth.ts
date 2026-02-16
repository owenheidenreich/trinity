/**
 * Authentication types for Ed25519-based ICP auth.
 */

/** Ed25519 key pair stored in localStorage (encrypted) */
export interface StoredKeyPair {
  privateKeyHex: string;
  principal: string;
  encrypted: boolean;
}

/** Authentication state */
export interface AuthState {
  isAuthenticated: boolean;
  principal: string | null;
  authenticatedSince: number | null;
}

/** Register/SignIn result */
export interface AuthResult {
  success: boolean;
  error?: string;
}

/** Login result (legacy, kept for compatibility) */
export interface LoginResult {
  success: boolean;
  principal?: string;
  privateKeyHex?: string;
  error?: string;
}

/** Key import result */
export interface ImportKeyResult {
  success: boolean;
  principal?: string;
  error?: string;
}

/** Key export result */
export interface ExportKeyResult {
  success: boolean;
  privateKeyHex?: string;
  principal?: string;
}

/**
 * Interface for the ICP Auth bundle (window.ICPAuth).
 * This is the pre-built auth bundle that provides Ed25519 identity management.
 */
export interface ICPAuthBundle {
  Ed25519KeyIdentity: {
    generate: () => Ed25519Identity;
    fromSecretKey: (key: Uint8Array | ArrayBuffer) => Ed25519Identity;
  };
  Principal: {
    selfAuthenticating: (publicKey: Uint8Array) => { toText: () => string };
  };
  HttpAgent: unknown;
}

/** Ed25519 identity instance */
export interface Ed25519Identity {
  getKeyPair: () => {
    secretKey: Uint8Array | ArrayBuffer;
    publicKey: {
      toDer: () => ArrayBuffer;
    };
  };
  getPrincipal: () => { toText: () => string };
  sign: (data: Uint8Array | ArrayBuffer) => Promise<Uint8Array | ArrayBuffer>;
}
