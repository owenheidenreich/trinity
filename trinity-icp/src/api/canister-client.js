// ============================================================================
// Trinity Frontend - ICP Canister Client
// ============================================================================
//
// ⚠️ STATUS: DISABLED (USE_CANISTER = false in config.js)
//
// REASON: ICP HTTPS outcalls have a hard 20-second timeout limit.
// Tier 3 models (Qwen 72B) require 60+ seconds for complex queries.
// The Cloudflare Worker path has no timeout limitation.
//
// RE-ENABLE WHEN:
// - ICP increases HTTPS outcall timeout (unlikely soon), OR
// - Using only fast models (Tier 1/2 with <20s response), OR
// - Implementing chunked/streaming responses via ICP
//
// ============================================================================
//
// PURPOSE:
// This module provides the frontend interface to the ICP backend canister,
// replacing the Cloudflare Worker for API communication.
//
// ARCHITECTURE:
// Frontend → This Client → ICP Actor → Backend Canister → HTTPS Outcall → Akash
//
// USAGE:
// import { generateViaCanister, healthCheckViaCanister } from './canister-client.js';
// const response = await generateViaCanister(prompt, contextMessages);
//
// ============================================================================

import { Actor, HttpAgent } from '@dfinity/agent';
import AuthManager from '../auth/authManager.js';

// ============================================================================
// CANISTER CONFIGURATION
// ============================================================================

// Backend canister ID - deployed via ./icp-deploy
// Fallback to production canister ID if env var not set
const BACKEND_CANISTER_ID = import.meta.env.VITE_BACKEND_CANISTER_ID || 'au5zq-2qaaa-aaaal-qtowa-cai';

// ICP host based on environment
const getICPHost = () => {
    const hostname = window.location.hostname;
    
    // Local development
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
        return 'http://localhost:4943';
    }
    
    // Production IC network
    return 'https://ic0.app';
};

// ============================================================================
// IDL FACTORY (Candid Interface)
// ============================================================================

// This defines the canister interface in JavaScript
// Matches trinity_backend.did
const idlFactory = ({ IDL }) => {
    const Message = IDL.Record({
        role: IDL.Text,
        content: IDL.Text,
    });
    
    const GenerateRequest = IDL.Record({
        prompt: IDL.Text,
        model: IDL.Opt(IDL.Text),
        context_messages: IDL.Opt(IDL.Vec(Message)),
    });
    
    const AuthHeaders = IDL.Record({
        principal_id: IDL.Text,
        timestamp: IDL.Text,
        signature: IDL.Text,
        public_key: IDL.Text,
    });
    
    const GenerateResponse = IDL.Record({
        response: IDL.Text,
        model: IDL.Text,
        provider_id: IDL.Text,
        done: IDL.Bool,
    });
    
    // Must match HealthResponse in lib.rs exactly
    // Fields from /health endpoint (deterministic for ICP consensus)
    // Some fields are optional for backwards compatibility with older backends
    const HealthResponse = IDL.Record({
        status: IDL.Text,
        provider_id: IDL.Text,
        model: IDL.Text,
        gpu_type: IDL.Text,
        ollama_connected: IDL.Bool,
        build_timestamp: IDL.Opt(IDL.Text),
        version: IDL.Opt(IDL.Text),
        icp_compatible: IDL.Opt(IDL.Bool),
    });
    
    const ErrorResponse = IDL.Record({
        error: IDL.Text,
        code: IDL.Nat16,
    });
    
    const Result_Generate = IDL.Variant({
        Ok: GenerateResponse,
        Err: ErrorResponse,
    });
    
    const Result_Health = IDL.Variant({
        Ok: HealthResponse,
        Err: ErrorResponse,
    });
    
    const Result_Unit = IDL.Variant({
        Ok: IDL.Null,
        Err: IDL.Text,
    });
    
    return IDL.Service({
        set_akash_url: IDL.Func([IDL.Text], [Result_Unit], []),
        get_akash_url: IDL.Func([], [IDL.Text], ['query']),
        get_canister_info: IDL.Func([], [IDL.Text], ['query']),
        get_cycle_balance: IDL.Func([], [IDL.Nat], ['query']),
        get_funding_info: IDL.Func([], [IDL.Text], ['query']),
        health: IDL.Func([], [Result_Health], []),
        generate: IDL.Func([GenerateRequest, AuthHeaders, IDL.Text], [Result_Generate], []),
    });
};

import Logger from '../core/logger.js';

// ============================================================================
// ACTOR MANAGEMENT
// ============================================================================

let agent = null;
let backendActor = null;

/**
 * Get or create the backend canister actor
 * @returns {Promise<Actor>} The backend canister actor
 */
async function getActor() {
    if (backendActor) return backendActor;
    
    if (!BACKEND_CANISTER_ID) {
        throw new Error('Backend canister ID not configured. Set VITE_BACKEND_CANISTER_ID in .env');
    }
    
    const host = getICPHost();
    
    Logger.debug('Connecting to ICP:', host, BACKEND_CANISTER_ID);
    
    agent = new HttpAgent({ host });
    
    // Fetch root key for local development (NEVER in production)
    if (host.includes('localhost')) {
        Logger.warn('Fetching root key for local development');
        await agent.fetchRootKey();
    }
    
    backendActor = Actor.createActor(idlFactory, {
        agent,
        canisterId: BACKEND_CANISTER_ID,
    });
    
    return backendActor;
}

/**
 * Reset the actor (useful for testing or after errors)
 */
export function resetActor() {
    agent = null;
    backendActor = null;
}

// ============================================================================
// API METHODS
// ============================================================================

/**
 * Generate LLM response via ICP canister
 * 
 * This is the main inference endpoint. It:
 * 1. Signs the request with Ed25519 (same as current auth)
 * 2. Calls the ICP canister
 * 3. Canister makes HTTPS outcall to Akash
 * 4. Returns the LLM response
 * 
 * @param {string} prompt - The user's message
 * @param {Array} contextMessages - Previous messages for context
 * @param {string} documentContext - Attached document content (optional)
 * @returns {Promise<Object>} The LLM response
 */
export async function generateViaCanister(prompt, contextMessages = [], documentContext = null) {
    const actor = await getActor();
    
    // Get auth credentials
    const publicKeyHex = AuthManager.getPublicKeyHex();
    const principal = AuthManager.getPrincipal();
    
    if (!publicKeyHex || !principal) {
        throw new Error('Not authenticated. Please generate or import a keypair.');
    }
    
    // Create timestamp and sign
    const timestamp = Date.now().toString();
    const message = `${principal}:${timestamp}`;
    const signature = await AuthManager.signMessage(message);
    
    // Generate unique request ID for idempotency
    const requestId = `${principal}-${timestamp}-${Math.random().toString(36).slice(2, 10)}`;
    
    // Build enhanced prompt with document context
    let enhancedPrompt = prompt;
    
    // Add document context if provided
    if (documentContext) {
        enhancedPrompt = `[DOCUMENT CONTEXT]\n${documentContext}\n[END DOCUMENT]\n\n${enhancedPrompt}`;
    }
    
    // Build request
    const request = {
        prompt: enhancedPrompt,
        model: [], // Empty array = use default model
        context_messages: contextMessages.length > 0 
            ? [contextMessages.map(m => ({ role: m.role, content: m.content }))]
            : [],
    };
    
    const auth = {
        principal_id: principal,
        timestamp,
        signature,
        public_key: publicKeyHex,
    };
    
    Logger.debug('Calling ICP canister generate...', {
        promptLength: enhancedPrompt.length,
        contextLength: contextMessages.length,
        hasDocument: !!documentContext,
        requestId: requestId.slice(0, 20) + '...',
    });
    
    const startTime = performance.now();
    
    try {
        const result = await actor.generate(request, auth, requestId);
        
        const latency = performance.now() - startTime;
        Logger.debug(`Canister response in ${latency.toFixed(0)}ms`);
        
        if ('Ok' in result) {
            return result.Ok;
        } else {
            const error = result.Err;
            throw new Error(`Canister error (${error.code}): ${error.error}`);
        }
    } catch (error) {
        Logger.error('Canister generate failed:', error);
        throw error;
    }
}

/**
 * Health check via ICP canister
 * 
 * Checks if both the canister and Akash backend are healthy.
 * 
 * @returns {Promise<Object>} Health status
 */
export async function healthCheckViaCanister() {
    const actor = await getActor();
    
    Logger.debug('Checking health via canister...');
    
    try {
        const result = await actor.health();
        
        if ('Ok' in result) {
            Logger.debug('Health check passed:', result.Ok);
            return result.Ok;
        } else {
            const error = result.Err;
            throw new Error(`Health check failed (${error.code}): ${error.error}`);
        }
    } catch (error) {
        Logger.error('Canister health check failed:', error);
        throw error;
    }
}

/**
 * Get current Akash URL from canister
 * 
 * @returns {Promise<string>} The Akash backend URL
 */
export async function getAkashUrl() {
    const actor = await getActor();
    return await actor.get_akash_url();
}

/**
 * Get canister info for debugging
 * 
 * @returns {Promise<string>} Canister debug info
 */
export async function getCanisterInfo() {
    const actor = await getActor();
    return await actor.get_canister_info();
}

/**
 * Get ICP cycle balance and funding info
 * 
 * @returns {Promise<Object>} Funding info with cycles, USD estimate, etc.
 */
export async function getFundingInfo() {
    try {
        const actor = await getActor();
        const infoStr = await actor.get_funding_info();
        return JSON.parse(infoStr);
    } catch (error) {
        Logger.warn('Failed to get funding info:', error);
        return null;
    }
}

/**
 * Check if canister client is configured
 * 
 * @returns {boolean} True if canister ID is set
 */
export function isCanisterConfigured() {
    return !!BACKEND_CANISTER_ID;
}

/**
 * Get the backend canister ID
 * 
 * @returns {string} The canister ID or empty string
 */
export function getCanisterId() {
    return BACKEND_CANISTER_ID;
}
