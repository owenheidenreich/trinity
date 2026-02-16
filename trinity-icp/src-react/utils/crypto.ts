/**
 * Client-side cryptography for Trinity auth overhaul.
 *
 * Key derivation uses Argon2id (via hash-wasm WebAssembly) instead of
 * browser-fingerprint PBKDF2. This makes identity derivation deterministic
 * across devices: same username + password = same Ed25519 keypair.
 *
 * Two derivation paths with different salts:
 *   1. Identity seed:  Argon2id(password, "trinity:" + username)  → Ed25519 keypair
 *   2. Storage key:    Argon2id(password, "trinity:storage:" + username) → AES-256-GCM key for localStorage
 */
import { argon2id } from 'hash-wasm';

// Argon2id parameters — must match across all clients
const ARGON2_MEMORY_KB = 65536; // 64 MB
const ARGON2_ITERATIONS = 3;
const ARGON2_PARALLELISM = 1; // WASM is single-threaded
const ARGON2_HASH_LENGTH = 32; // 32 bytes = 256 bits

/**
 * Derive a 32-byte Ed25519 seed from username + password.
 * Same inputs always produce the same seed (deterministic identity).
 */
export async function deriveIdentitySeed(
  password: string,
  username: string,
): Promise<Uint8Array> {
  const salt = `trinity:${username.toLowerCase()}`;
  const hash = await argon2id({
    password,
    salt,
    parallelism: ARGON2_PARALLELISM,
    iterations: ARGON2_ITERATIONS,
    memorySize: ARGON2_MEMORY_KB,
    hashLength: ARGON2_HASH_LENGTH,
    outputType: 'binary',
  });
  return new Uint8Array(hash);
}

/**
 * Derive a CryptoKey for encrypting the private key in localStorage.
 * Uses a different salt than identity derivation to produce a different key.
 */
async function deriveStorageKeyBytes(
  password: string,
  username: string,
): Promise<Uint8Array> {
  const salt = `trinity:storage:${username.toLowerCase()}`;
  const hash = await argon2id({
    password,
    salt,
    parallelism: ARGON2_PARALLELISM,
    iterations: ARGON2_ITERATIONS,
    memorySize: ARGON2_MEMORY_KB,
    hashLength: ARGON2_HASH_LENGTH,
    outputType: 'binary',
  });
  return new Uint8Array(hash);
}

/**
 * Import raw key bytes as an AES-256-GCM CryptoKey.
 */
async function importAesKey(rawBytes: Uint8Array): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    rawBytes.buffer as ArrayBuffer,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
}

/**
 * Encrypt plaintext for localStorage storage.
 * Requires username + password to derive the storage key.
 * Returns base64(IV + ciphertext).
 */
export async function encryptForStorage(
  plaintext: string,
  password: string,
  username: string,
): Promise<string> {
  const encoder = new TextEncoder();
  const keyBytes = await deriveStorageKeyBytes(password, username);
  const key = await importAesKey(keyBytes);
  const iv = crypto.getRandomValues(new Uint8Array(12));

  const encrypted = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    encoder.encode(plaintext),
  );

  // Prepend IV to ciphertext
  const combined = new Uint8Array(iv.length + encrypted.byteLength);
  combined.set(iv);
  combined.set(new Uint8Array(encrypted), iv.length);

  return btoa(String.fromCharCode(...combined));
}

/**
 * Decrypt base64-encoded ciphertext from localStorage.
 * Requires username + password to derive the storage key.
 */
export async function decryptFromStorage(
  encryptedBase64: string,
  password: string,
  username: string,
): Promise<string> {
  const decoder = new TextDecoder();
  const keyBytes = await deriveStorageKeyBytes(password, username);
  const key = await importAesKey(keyBytes);
  const combined = Uint8Array.from(atob(encryptedBase64), (c) => c.charCodeAt(0));
  const iv = combined.slice(0, 12);
  const ciphertext = combined.slice(12);

  const decrypted = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv },
    key,
    ciphertext,
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
