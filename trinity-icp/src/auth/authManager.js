// auth/authManager.js - Ed25519 Authentication Manager
// Handles ICP identity management, Ed25519 keypair generation, and signature creation
//
// SECURITY:
// - All API requests signed with Ed25519 signature
// - Backend verifies signature + timestamp (prevents replay attacks)
// - No passwords - just cryptographic keypairs
// - Private keys encrypted in localStorage with browser-derived key

import { encryptForStorage, decryptFromStorage, isEncrypted } from '../utils/crypto.js';

const AuthManager = {
    isInitialized: false,
    identity: null,
    authClient: null,

    async initialize() {
        if (!window.ICPAuth) {
            console.error('❌ ICP Auth bundle not loaded');
            return false;
        }

        try {
            console.log('🔧 ICP Authentication initializing...');
            console.log('✅ ICPAuth available:', Object.keys(window.ICPAuth));
            
            // Verify we have the required classes
            if (!window.ICPAuth.HttpAgent || !window.ICPAuth.Ed25519KeyIdentity || !window.ICPAuth.Principal) {
                console.error('❌ Missing required ICP Auth classes');
                return false;
            }

            this.isInitialized = true;
            
            // Try to restore saved identity from localStorage
            const savedKey = localStorage.getItem('trinity_identity_key');
            const savedPrincipal = localStorage.getItem('trinity_principal');
            
            if (savedKey && savedPrincipal) {
                try {
                    console.log('🔄 Restoring saved identity...');
                    const restoredIdentity = await this.restoreIdentity(savedKey, savedPrincipal);
                    
                    if (restoredIdentity) {
                        console.log('✅ Identity restored:', savedPrincipal);
                        return restoredIdentity;
                    }
                } catch (error) {
                    console.error('❌ Failed to restore identity:', error);
                    localStorage.removeItem('trinity_identity_key');
                    localStorage.removeItem('trinity_principal');
                }
            }
            
            console.log('✅ ICP Authentication initialized');
            return { isAuthenticated: false };
        } catch (error) {
            console.error('❌ ICP Authentication initialization failed:', error);
            return false;
        }
    },

    async restoreIdentity(savedKey, savedPrincipal) {
        const { Ed25519KeyIdentity } = window.ICPAuth;
        
        // Decrypt if encrypted, otherwise use as-is (for migration)
        let privateKeyHex;
        if (isEncrypted(savedKey)) {
            console.log('🔓 Decrypting stored key...');
            privateKeyHex = await decryptFromStorage(savedKey);
        } else {
            // Migrate unencrypted key to encrypted storage
            console.log('🔐 Migrating unencrypted key to encrypted storage...');
            privateKeyHex = savedKey;
            const encryptedKey = await encryptForStorage(privateKeyHex);
            localStorage.setItem('trinity_identity_key', encryptedKey);
        }
        
        // Convert hex string back to Uint8Array
        const keyBytes = new Uint8Array(
            privateKeyHex.match(/.{1,2}/g).map(byte => parseInt(byte, 16))
        );
        
        // Restore identity from private key
        this.identity = Ed25519KeyIdentity.fromSecretKey(keyBytes);
        const restoredPrincipal = this.identity.getPrincipal().toText();
        
        // Verify it matches
        if (restoredPrincipal === savedPrincipal) {
            return {
                isAuthenticated: true,
                principal: savedPrincipal,
                authenticatedSince: Date.now()
            };
        } else {
            console.warn('⚠️ Principal mismatch, clearing saved data');
            localStorage.removeItem('trinity_identity_key');
            localStorage.removeItem('trinity_principal');
            return null;
        }
    },

    async initializeIdentity() {
        if (!this.authClient || !this.isInitialized) {
            return { isAuthenticated: false };
        }

        if (await this.authClient.isAuthenticated()) {
            this.identity = this.authClient.getIdentity();
            const principal = this.identity.getPrincipal().toText();
            console.log('✅ User already authenticated:', principal);
            return {
                isAuthenticated: true,
                principal: principal,
                authenticatedSince: Date.now()
            };
        }

        return { isAuthenticated: false };
    },

    async login() {
        console.log('🔐 Auth.login() called');
        
        if (!this.isInitialized) {
            console.error('❌ Auth not initialized');
            alert('Authentication not initialized. Please refresh the page.');
            return { success: false };
        }

        try {
            const { Ed25519KeyIdentity } = window.ICPAuth;
            
            // Generate new identity
            this.identity = Ed25519KeyIdentity.generate();
            const principal = this.identity.getPrincipal().toText();
            
            // Export private key for user to save
            const privateKeyArray = this.identity.getKeyPair().secretKey;
            const privateKeyHex = Array.from(privateKeyArray)
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            
            // Encrypt and store in localStorage
            console.log('🔐 Encrypting private key for storage...');
            const encryptedKey = await encryptForStorage(privateKeyHex);
            localStorage.setItem('trinity_identity_key', encryptedKey);
            localStorage.setItem('trinity_principal', principal);
            
            console.log('✅ New identity created:', principal);
            
            return { 
                success: true, 
                principal: principal,
                privateKeyHex: privateKeyHex, // Return unencrypted for user export
                authenticatedSince: Date.now()
            };
        } catch (error) {
            console.error('❌ Login exception:', error);
            alert('Login error: ' + error.message);
            return { success: false, error: error.message };
        }
    },

    async logout() {
        // Clear localStorage
        localStorage.removeItem('trinity_identity_key');
        localStorage.removeItem('trinity_principal');
        
        this.identity = null;
        this.authClient = null;
        console.log('✅ Logged out and cleared saved identity');
        
        return { success: true };
    },

    async importKey(privateKeyHex) {
        if (!privateKeyHex || typeof privateKeyHex !== 'string') {
            return { success: false, error: 'Invalid private key format' };
        }

        try {
            const { Ed25519KeyIdentity } = window.ICPAuth;
            
            // Convert hex to Uint8Array
            const keyBytes = new Uint8Array(
                privateKeyHex.match(/.{1,2}/g).map(byte => parseInt(byte, 16))
            );
            
            // Restore identity
            this.identity = Ed25519KeyIdentity.fromSecretKey(keyBytes);
            const principal = this.identity.getPrincipal().toText();
            
            // Encrypt and save to localStorage
            console.log('🔐 Encrypting imported key for storage...');
            const encryptedKey = await encryptForStorage(privateKeyHex);
            localStorage.setItem('trinity_identity_key', encryptedKey);
            localStorage.setItem('trinity_principal', principal);
            
            console.log('✅ Identity imported:', principal);
            
            return {
                success: true,
                principal: principal,
                authenticatedSince: Date.now()
            };
        } catch (error) {
            console.error('❌ Import key failed:', error);
            return { success: false, error: error.message };
        }
    },

    exportKey() {
        if (!this.identity) {
            return { success: false, error: 'Not authenticated' };
        }

        try {
            const privateKeyArray = this.identity.getKeyPair().secretKey;
            const privateKeyHex = Array.from(privateKeyArray)
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            
            return {
                success: true,
                privateKeyHex: privateKeyHex,
                principal: this.identity.getPrincipal().toText()
            };
        } catch (error) {
            console.error('❌ Export key failed:', error);
            return { success: false, error: error.message };
        }
    },

    async signMessage(message) {
        if (!this.identity) {
            throw new Error('Not authenticated - cannot sign message');
        }
        
        try {
            // Convert message string to Uint8Array
            const encoder = new TextEncoder();
            const messageBytes = encoder.encode(message);
            
            // Sign with Ed25519 private key
            const signature = await this.identity.sign(messageBytes);
            
            // Convert signature to hex string for transmission
            const signatureHex = Array.from(signature)
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            
            return signatureHex;
        } catch (error) {
            console.error('❌ Failed to sign message:', error);
            throw error;
        }
    },

    getPublicKeyHex() {
        if (!this.identity) {
            throw new Error('Not authenticated - no public key available');
        }
        
        try {
            // Get DER-encoded public key
            const publicKeyDer = this.identity.getPublicKey().toDer();
            
            // DER format includes algorithm identifier prefix (12 bytes for Ed25519)
            // We need just the raw 32-byte public key
            // Ed25519 DER: 30 2a 30 05 06 03 2b 65 70 03 21 00 [32 bytes]
            // Skip first 12 bytes to get raw key
            const rawPublicKey = publicKeyDer.slice(-32);
            
            // Convert to hex
            const publicKeyHex = Array.from(rawPublicKey)
                .map(b => b.toString(16).padStart(2, '0'))
                .join('');
            
            return publicKeyHex;
        } catch (error) {
            console.error('❌ Failed to get public key:', error);
            throw error;
        }
    },

    getPrincipal() {
        if (!this.identity) {
            return null;
        }
        return this.identity.getPrincipal().toText();
    },

    isAuthenticated() {
        return this.identity !== null;
    },

    isGuest() {
        return !this.isAuthenticated();
    }
};

export default AuthManager;
