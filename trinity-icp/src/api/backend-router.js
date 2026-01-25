// ============================================================================
// Trinity Frontend - Backend Router
// ============================================================================
//
// PURPOSE:
// This module provides a unified API for backend communication, supporting
// gradual migration from Cloudflare Workers to ICP canister.
//
// ARCHITECTURE:
// ┌─────────────────────────────────────────────────────────────────┐
// │                      Backend Router                              │
// │                                                                  │
// │  ┌─────────────────┐              ┌─────────────────────────┐   │
// │  │  Canister Path  │◄── % ───────►│   Cloudflare Path       │   │
// │  │  (ICP Outcalls) │              │   (Current production)   │   │
// │  └────────┬────────┘              └───────────┬─────────────┘   │
// │           │                                   │                  │
// │           ▼                                   ▼                  │
// │     ICP Backend                         Cloudflare Worker        │
// │      Canister                           → Akash Backend          │
// │           │                                   │                  │
// │           └───────────► Akash Backend ◄───────┘                  │
// └─────────────────────────────────────────────────────────────────┘
//
// ROLLOUT STRATEGY (Phase 3):
// Week 1: 10% canister, 90% Cloudflare
// Week 2: 50% canister, 50% Cloudflare
// Week 3: 90% canister, 10% Cloudflare
// Week 4: 100% canister, delete Cloudflare
//
// USAGE:
// import { generate, health, setCanisterPercentage } from './backend-router.js';
// setCanisterPercentage(50); // 50% of requests go to canister
// const response = await generate(prompt, contextMessages);
// ============================================================================

import { 
    generateViaCanister, 
    healthCheckViaCanister, 
    isCanisterConfigured 
} from './canister-client.js';
import { CONFIG } from '../config.js';
import { AuthManager } from '../auth/authManager.js';

// ============================================================================
// ROUTING CONFIGURATION
// ============================================================================

// Storage key for routing percentage
const ROUTING_KEY = 'trinity_canister_percentage';
const METRICS_KEY = 'trinity_routing_metrics';

// Get current canister routing percentage (0-100)
function getCanisterPercentage() {
    const stored = localStorage.getItem(ROUTING_KEY);
    if (stored !== null) {
        return parseInt(stored, 10);
    }
    // Default: 0% canister (all traffic goes to Cloudflare)
    // Change this as we progress through Phase 3
    return 0;
}

/**
 * Set the percentage of requests to route through ICP canister
 * @param {number} percent - 0 to 100
 */
export function setCanisterPercentage(percent) {
    const value = Math.max(0, Math.min(100, parseInt(percent, 10)));
    localStorage.setItem(ROUTING_KEY, value.toString());
    console.log(`🎚️ Canister routing set to ${value}%`);
    return value;
}

/**
 * Decide whether to use canister for this request
 * @returns {boolean}
 */
function shouldUseCanister() {
    // If canister not configured, always use Cloudflare
    if (!isCanisterConfigured()) {
        return false;
    }
    
    const percentage = getCanisterPercentage();
    
    if (percentage === 100) return true;
    if (percentage === 0) return false;
    
    return Math.random() * 100 < percentage;
}

// ============================================================================
// METRICS COLLECTION
// ============================================================================

/**
 * Record metrics for a request
 * @param {Object} metrics - { path, latency, success, error? }
 */
function recordMetrics(metrics) {
    const stored = JSON.parse(localStorage.getItem(METRICS_KEY) || '[]');
    stored.push({
        ...metrics,
        timestamp: Date.now(),
    });
    
    // Keep only last 200 entries
    while (stored.length > 200) {
        stored.shift();
    }
    
    localStorage.setItem(METRICS_KEY, JSON.stringify(stored));
}

/**
 * Get metrics summary for debugging
 * @returns {Object} Summary of canister vs cloudflare metrics
 */
export function getMetricsSummary() {
    const metrics = JSON.parse(localStorage.getItem(METRICS_KEY) || '[]');
    
    const canisterMetrics = metrics.filter(m => m.path === 'canister');
    const cloudflareMetrics = metrics.filter(m => m.path === 'cloudflare');
    
    const avg = arr => arr.length > 0 
        ? arr.reduce((sum, m) => sum + m.latency, 0) / arr.length 
        : 0;
    
    const successRate = arr => arr.length > 0
        ? (arr.filter(m => m.success).length / arr.length * 100).toFixed(1)
        : 0;
    
    return {
        canister: {
            count: canisterMetrics.length,
            avgLatency: avg(canisterMetrics).toFixed(0) + 'ms',
            successRate: successRate(canisterMetrics) + '%',
        },
        cloudflare: {
            count: cloudflareMetrics.length,
            avgLatency: avg(cloudflareMetrics).toFixed(0) + 'ms',
            successRate: successRate(cloudflareMetrics) + '%',
        },
        routingPercentage: getCanisterPercentage() + '%',
        canisterConfigured: isCanisterConfigured(),
    };
}

/**
 * Clear metrics history
 */
export function clearMetrics() {
    localStorage.removeItem(METRICS_KEY);
    console.log('📊 Metrics cleared');
}

// ============================================================================
// CLOUDFLARE PATH (Current Production)
// ============================================================================

/**
 * Generate via Cloudflare Worker (current production path)
 */
async function generateViaCloudflare(prompt, contextMessages = []) {
    const url = `${CONFIG.API_URL}/generate`;
    
    // Build request body
    const body = {
        prompt,
        model: 'llama3.1:70b',
        context: contextMessages,
        stream: false,
    };
    
    // Get auth headers
    const headers = {
        'Content-Type': 'application/json',
    };
    
    // Add auth if authenticated
    if (AuthManager.isAuthenticated()) {
        const timestamp = Date.now().toString();
        const principal = AuthManager.getPrincipal();
        const message = `${principal}:${timestamp}`;
        const signature = await AuthManager.signMessage(message);
        
        headers['X-ICP-Principal'] = principal;
        headers['X-ICP-Timestamp'] = timestamp;
        headers['X-ICP-Signature'] = signature;
        headers['X-ICP-PublicKey'] = AuthManager.getPublicKeyHex();
    }
    
    const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
    });
    
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`Cloudflare request failed (${response.status}): ${text}`);
    }
    
    return response.json();
}

/**
 * Health check via Cloudflare Worker
 */
async function healthViaCloudflare() {
    const url = `${CONFIG.API_URL}/health`;
    
    const response = await fetch(url);
    
    if (!response.ok) {
        throw new Error(`Health check failed (${response.status})`);
    }
    
    return response.json();
}

// ============================================================================
// UNIFIED API
// ============================================================================

/**
 * Generate LLM response via the routed backend
 * 
 * Automatically routes to either canister or Cloudflare based on
 * the configured percentage.
 * 
 * @param {string} prompt - The user's message
 * @param {Array} contextMessages - Previous messages for context
 * @returns {Promise<Object>} The LLM response
 */
export async function generate(prompt, contextMessages = []) {
    const useCanister = shouldUseCanister();
    const path = useCanister ? 'canister' : 'cloudflare';
    const startTime = performance.now();
    
    console.log(`🔀 Routing to ${path} (${getCanisterPercentage()}% canister)`);
    
    try {
        let result;
        
        if (useCanister) {
            result = await generateViaCanister(prompt, contextMessages);
        } else {
            result = await generateViaCloudflare(prompt, contextMessages);
        }
        
        const latency = performance.now() - startTime;
        console.log(`✅ ${path} response in ${latency.toFixed(0)}ms`);
        
        recordMetrics({ path, latency, success: true });
        
        return result;
    } catch (error) {
        const latency = performance.now() - startTime;
        console.error(`❌ ${path} failed:`, error);
        
        recordMetrics({ 
            path, 
            latency, 
            success: false, 
            error: error.message 
        });
        
        // If canister failed, try fallback to Cloudflare
        if (useCanister && getCanisterPercentage() < 100) {
            console.log('🔄 Falling back to Cloudflare...');
            try {
                const fallbackResult = await generateViaCloudflare(prompt, contextMessages);
                recordMetrics({ 
                    path: 'cloudflare-fallback', 
                    latency: performance.now() - startTime, 
                    success: true 
                });
                return fallbackResult;
            } catch (fallbackError) {
                console.error('❌ Fallback also failed:', fallbackError);
                throw fallbackError;
            }
        }
        
        throw error;
    }
}

/**
 * Health check via the routed backend
 * 
 * @returns {Promise<Object>} Health status
 */
export async function health() {
    const useCanister = shouldUseCanister();
    const path = useCanister ? 'canister' : 'cloudflare';
    
    try {
        if (useCanister) {
            return await healthCheckViaCanister();
        } else {
            return await healthViaCloudflare();
        }
    } catch (error) {
        console.error(`❌ Health check via ${path} failed:`, error);
        throw error;
    }
}

/**
 * Get current routing configuration
 * 
 * @returns {Object} Routing config
 */
export function getRoutingConfig() {
    return {
        canisterPercentage: getCanisterPercentage(),
        canisterConfigured: isCanisterConfigured(),
        currentPath: shouldUseCanister() ? 'canister' : 'cloudflare',
    };
}

// ============================================================================
// DEVELOPER TOOLS (accessible via console)
// ============================================================================

// Expose to window for debugging
if (typeof window !== 'undefined') {
    window.TrinityRouter = {
        setCanisterPercentage,
        getMetricsSummary,
        clearMetrics,
        getRoutingConfig,
        // Force specific path for next request
        forceCanister: () => setCanisterPercentage(100),
        forceCloudflare: () => setCanisterPercentage(0),
    };
    
    console.log('💡 Debug: window.TrinityRouter available for routing control');
}
