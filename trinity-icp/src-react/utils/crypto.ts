/**
 * Client-side AES-256-GCM encryption for localStorage key protection.
 * Ported from utils/crypto.js with types.
 * Browser-bound: different browser/machine = different derived key.
 */

const SALT_STRING = 'TRINITY_KEY_SALT';
const ITERATIONS = 50_000;
const KEY_LENGTH = 256; // bits

/**
 * Derive a browser-fingerprint-based encryption key.
 *
 * IMPORTANT: The fingerprint must remain **stable** across browser updates,
 * OS patches, and window resizes. We intentionally exclude volatile values
 * like navigator.userAgent / navigator.platform / screen dimensions.
 *
 * Components used (all stable for a given browser profile):
 *   - origin:        always https://dubya.ai
 *   - hardwareConcurrency: CPU core count (rarely changes)
 *   - language:      user locale (stable per profile)
 *   - colorDepth:    display colour depth (stable per monitor)
 */
async function deriveKey(): Promise<CryptoKey> {
  const encoder = new TextEncoder();

  // Stable fingerprint components — intentionally excludes userAgent/platform/screen size
  const origin = 'https://dubya.ai';
  const cores =
    typeof navigator !== 'undefined' ? String(navigator.hardwareConcurrency ?? 0) : '0';
  const lang =
    typeof navigator !== 'undefined' ? (navigator.language ?? 'en') : 'en';
  const depth =
    typeof screen !== 'undefined' ? String(screen.colorDepth ?? 24) : '24';
  const passphrase = `${origin}:${cores}:${lang}:${depth}`;

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
