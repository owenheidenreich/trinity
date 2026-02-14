/**
 * Client-side AES-256-GCM encryption for localStorage key protection.
 * Ported from utils/crypto.js with types.
 * Browser-bound: different browser/machine = different derived key.
 */

const SALT_STRING = 'TRINITY_KEY_SALT';
const ITERATIONS = 50_000;
const KEY_LENGTH = 256; // bits

/** Derive a browser-fingerprint-based encryption key */
async function deriveKey(): Promise<CryptoKey> {
  const encoder = new TextEncoder();

  // Browser fingerprint components
  const origin = 'https://dubya.ai';
  const ua = typeof navigator !== 'undefined' ? navigator.userAgent : '';
  const platform = typeof navigator !== 'undefined' ? navigator.platform : '';
  const screen =
    typeof window !== 'undefined'
      ? `${window.screen.width}x${window.screen.height}`
      : '0x0';
  const passphrase = `${origin}:${ua}:${platform}:${screen}`;

  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    encoder.encode(passphrase),
    'PBKDF2',
    false,
    ['deriveKey']
  );

  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: encoder.encode(SALT_STRING),
      iterations: ITERATIONS,
      hash: 'SHA-256',
    },
    keyMaterial,
    { name: 'AES-GCM', length: KEY_LENGTH },
    false,
    ['encrypt', 'decrypt']
  );
}

/** Encrypt plaintext for localStorage storage. Returns base64. */
export async function encryptForStorage(plaintext: string): Promise<string> {
  const encoder = new TextEncoder();
  const key = await deriveKey();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    encoder.encode(plaintext)
  );

  // Prepend IV to ciphertext
  const combined = new Uint8Array(iv.length + encrypted.byteLength);
  combined.set(iv);
  combined.set(new Uint8Array(encrypted), iv.length);

  return btoa(String.fromCharCode(...combined));
}

/** Decrypt base64-encoded ciphertext from localStorage. */
export async function decryptFromStorage(encryptedBase64: string): Promise<string> {
  const decoder = new TextDecoder();
  const key = await deriveKey();
  const combined = Uint8Array.from(atob(encryptedBase64), (c) => c.charCodeAt(0));
  const iv = combined.slice(0, 12);
  const ciphertext = combined.slice(12);

  const decrypted = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv },
    key,
    ciphertext
  );

  return decoder.decode(decrypted);
}

/** Heuristic check if a string looks encrypted (base64, min length) */
export function isEncrypted(data: string): boolean {
  if (!data || data.length < 24) return false;
  if (/^[0-9a-f]+$/i.test(data)) return false; // raw hex, not encrypted
  try {
    atob(data);
    return true;
  } catch {
    return false;
  }
}
