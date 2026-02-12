/**
 * Browser-side encryption utilities for localStorage key protection
 * Uses Web Crypto API for AES-GCM encryption
 */

// Salt for key derivation (static but provides some obfuscation)
const STORAGE_SALT = new Uint8Array([
    0x54, 0x52, 0x49, 0x4e, 0x49, 0x54, 0x59, 0x5f,
    0x4b, 0x45, 0x59, 0x5f, 0x53, 0x41, 0x4c, 0x54
]); // "TRINITY_KEY_SALT"

/**
 * Derive an encryption key from browser fingerprint + origin
 * This provides some protection against localStorage data being
 * extracted and used on a different machine/browser.
 */
async function deriveStorageKey() {
    // Combine multiple factors for key derivation
    const factors = [
        'https://dubya.ai',  // Fixed origin - never changes on redeployment
        navigator.userAgent,
        (await navigator.userAgentData?.getHighEntropyValues?.(['platform']))?.platform || '',
        screen.width.toString(),
        screen.height.toString()
    ].join('|');
    
    const encoder = new TextEncoder();
    const keyMaterial = await crypto.subtle.importKey(
        'raw',
        encoder.encode(factors),
        'PBKDF2',
        false,
        ['deriveKey']
    );
    
    return crypto.subtle.deriveKey(
        {
            name: 'PBKDF2',
            salt: STORAGE_SALT,
            iterations: 50000, // Lighter for client-side
            hash: 'SHA-256'
        },
        keyMaterial,
        { name: 'AES-GCM', length: 256 },
        false,
        ['encrypt', 'decrypt']
    );
}

/**
 * Encrypt sensitive data before storing in localStorage
 * @param {string} plaintext - The data to encrypt
 * @returns {Promise<string>} Base64-encoded encrypted data with IV prepended
 */
export async function encryptForStorage(plaintext) {
    try {
        const key = await deriveStorageKey();
        const iv = crypto.getRandomValues(new Uint8Array(12)); // 96-bit IV for GCM
        const encoder = new TextEncoder();
        
        const encrypted = await crypto.subtle.encrypt(
            { name: 'AES-GCM', iv },
            key,
            encoder.encode(plaintext)
        );
        
        // Prepend IV to ciphertext
        const combined = new Uint8Array(iv.length + encrypted.byteLength);
        combined.set(iv, 0);
        combined.set(new Uint8Array(encrypted), iv.length);
        
        // Return as base64
        return btoa(String.fromCharCode(...combined));
    } catch (error) {
        console.error('❌ Encryption failed:', error);
        throw error;
    }
}

/**
 * Decrypt data from localStorage
 * @param {string} encryptedBase64 - Base64-encoded encrypted data
 * @returns {Promise<string>} Decrypted plaintext
 */
export async function decryptFromStorage(encryptedBase64) {
    try {
        const key = await deriveStorageKey();
        
        // Decode base64
        const combined = new Uint8Array(
            atob(encryptedBase64).split('').map(c => c.charCodeAt(0))
        );
        
        // Extract IV (first 12 bytes) and ciphertext
        const iv = combined.slice(0, 12);
        const ciphertext = combined.slice(12);
        
        const decrypted = await crypto.subtle.decrypt(
            { name: 'AES-GCM', iv },
            key,
            ciphertext
        );
        
        const decoder = new TextDecoder();
        return decoder.decode(decrypted);
    } catch (error) {
        console.error('❌ Decryption failed:', error);
        throw error;
    }
}

/**
 * Check if a string looks like encrypted data (base64 with minimum length)
 * @param {string} data - Data to check
 * @returns {boolean}
 */
export function isEncrypted(data) {
    if (!data || typeof data !== 'string') return false;
    // Encrypted data has IV (12 bytes) + ciphertext, base64 encoded
    // Minimum length for smallest encrypted content
    if (data.length < 24) return false;
    // Raw hex private keys (64 or 128 hex chars) are NOT encrypted
    if (/^[0-9a-f]+$/i.test(data)) return false;
    // Check if valid base64
    try {
        atob(data);
        return true;
    } catch {
        return false;
    }
}
