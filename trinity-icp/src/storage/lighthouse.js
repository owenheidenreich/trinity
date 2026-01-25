// ============================================================================
// Trinity Frontend - Lighthouse Storage Module
// ============================================================================
// 
// PURPOSE:
// Provides frontend utilities for Lighthouse/Filecoin storage integration.
// Primary archive operations are handled by the backend (inference_server.py),
// but this module provides client-side helpers for:
//   - Checking Filecoin deal status
//   - Retrieving content from IPFS gateways
//   - Storage quota information
//
// ARCHITECTURE NOTE:
// The actual upload to Lighthouse happens on the backend to:
//   1. Keep the API key secure (not exposed to browser)
//   2. Maintain encryption/decryption in one place
//   3. Allow backend-side metadata management
//
// This module complements the backend by providing client-side utilities.
//
// DEPENDENCIES:
//   - @lighthouse-web3/sdk (installed via npm)
//   - Backend endpoints at /chat/archive/status/<cid>
//
// ============================================================================

import lighthouse from '@lighthouse-web3/sdk';

// ============================================================================
// CONFIGURATION
// ============================================================================

// IPFS Gateways for content retrieval (ordered by preference)
const IPFS_GATEWAYS = [
    'https://gateway.lighthouse.storage/ipfs',  // Lighthouse (primary)
    'https://ipfs.io/ipfs',                      // Protocol Labs
    'https://dweb.link/ipfs',                    // dweb.link
    'https://cloudflare-ipfs.com/ipfs'           // Cloudflare
];

// Timeout for gateway requests (ms)
const GATEWAY_TIMEOUT_MS = 30000;

// ============================================================================
// FILECOIN DEAL STATUS
// ============================================================================

/**
 * Check Filecoin deal status for an archived chat
 * 
 * Filecoin deals typically take 1-24 hours to be created after upload.
 * This function checks the current status via the backend endpoint.
 * 
 * @param {string} cid - IPFS Content Identifier
 * @param {string} apiBaseUrl - Base URL for backend API
 * @returns {Promise<{status: string, message: string, deals: Array, gateways: Array}>}
 */
export async function checkFilecoinDealStatus(cid, apiBaseUrl) {
    if (!cid) {
        return {
            status: 'error',
            message: 'No CID provided',
            deals: [],
            gateways: []
        };
    }

    try {
        const response = await fetch(`${apiBaseUrl}/chat/archive/status/${cid}`, {
            method: 'GET',
            headers: { 'Accept': 'application/json' }
        });

        if (!response.ok) {
            throw new Error(`Status check failed: ${response.status}`);
        }

        const data = await response.json();
        
        console.log(`📊 Filecoin deal status for ${cid.substring(0, 12)}...:`, data.filecoin?.status);
        
        return {
            cid: data.cid,
            status: data.filecoin?.status || 'unknown',
            message: data.filecoin?.message || 'Status unknown',
            deals: data.filecoin?.deals || [],
            gateways: data.gateways || [],
            checkedAt: data.checkedAt
        };
    } catch (error) {
        console.error('Failed to check Filecoin deal status:', error);
        return {
            status: 'error',
            message: error.message,
            deals: [],
            gateways: getGatewayUrls(cid)
        };
    }
}

// ============================================================================
// IPFS GATEWAY UTILITIES
// ============================================================================

/**
 * Get gateway URLs for a CID
 * 
 * Returns multiple gateway URLs for redundancy.
 * If one gateway is slow or unavailable, clients can try others.
 * 
 * @param {string} cid - IPFS Content Identifier
 * @returns {string[]} Array of gateway URLs
 */
export function getGatewayUrls(cid) {
    if (!cid) return [];
    return IPFS_GATEWAYS.map(gateway => `${gateway}/${cid}`);
}

/**
 * Retrieve content from IPFS via multiple gateways
 * 
 * Tries gateways in order until one succeeds.
 * Useful for downloading archived chat content directly from IPFS.
 * 
 * @param {string} cid - IPFS Content Identifier
 * @returns {Promise<string>} Content as text
 * @throws {Error} If all gateways fail
 */
export async function retrieveFromIPFS(cid) {
    if (!cid) {
        throw new Error('No CID provided');
    }

    const gateways = getGatewayUrls(cid);
    const errors = [];

    for (const gatewayUrl of gateways) {
        try {
            console.log(`🌐 Trying gateway: ${gatewayUrl}`);
            
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), GATEWAY_TIMEOUT_MS);
            
            const response = await fetch(gatewayUrl, {
                signal: controller.signal,
                headers: { 'Accept': 'application/json, text/plain, */*' }
            });
            
            clearTimeout(timeoutId);

            if (response.ok) {
                const content = await response.text();
                console.log(`✅ Successfully retrieved from: ${gatewayUrl}`);
                return content;
            } else {
                errors.push(`${gatewayUrl}: HTTP ${response.status}`);
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                errors.push(`${gatewayUrl}: Timeout`);
            } else {
                errors.push(`${gatewayUrl}: ${error.message}`);
            }
            console.warn(`Gateway failed: ${gatewayUrl}`, error.message);
        }
    }

    throw new Error(`All IPFS gateways failed for CID ${cid}:\n${errors.join('\n')}`);
}

// ============================================================================
// LIGHTHOUSE SDK UTILITIES
// ============================================================================

/**
 * Get Filecoin deal status directly via Lighthouse SDK
 * 
 * Alternative to backend endpoint - can be used for direct status checks.
 * Note: This is informational only; the backend handles primary operations.
 * 
 * @param {string} cid - IPFS Content Identifier
 * @returns {Promise<{dealStatus: string, deals: Array}>}
 */
export async function getFilecoinDealStatusDirect(cid) {
    try {
        const response = await lighthouse.dealStatus(cid);
        
        if (!response.data || response.data.length === 0) {
            return {
                dealStatus: 'pending',
                message: 'Filecoin deal not yet created (typically takes 1-24 hours)',
                deals: []
            };
        }

        return {
            dealStatus: 'active',
            message: 'Content is stored on Filecoin',
            deals: response.data.map(deal => ({
                dealId: deal.dealId,
                storageProvider: deal.storageProvider,
                status: deal.dealStatus,
                startEpoch: deal.startEpoch,
                endEpoch: deal.endEpoch
            }))
        };
    } catch (error) {
        console.error('Failed to check deal status via Lighthouse SDK:', error);
        return {
            dealStatus: 'unknown',
            message: error.message,
            deals: []
        };
    }
}

/**
 * Get file information from Lighthouse
 * 
 * Returns metadata about an uploaded file.
 * 
 * @param {string} cid - IPFS Content Identifier
 * @returns {Promise<{cid: string, size: string, encryption: boolean, fileName: string}>}
 */
export async function getFileInfo(cid) {
    try {
        const response = await lighthouse.getFileInfo(cid);
        return response.data;
    } catch (error) {
        console.error('Failed to get file info:', error);
        return null;
    }
}

// ============================================================================
// ARCHIVE DISPLAY HELPERS
// ============================================================================

/**
 * Format deal status for display in UI
 * 
 * @param {string} status - Deal status ('pending', 'active', 'error', 'unknown')
 * @returns {{icon: string, text: string, color: string}}
 */
export function formatDealStatus(status) {
    switch (status) {
        case 'active':
            return {
                icon: '✅',
                text: 'Stored on Filecoin',
                color: '#4ade80'  // Green
            };
        case 'pending':
            return {
                icon: '⏳',
                text: 'Awaiting Filecoin deal (1-24 hours)',
                color: '#fbbf24'  // Yellow
            };
        case 'error':
            return {
                icon: '❌',
                text: 'Status check failed',
                color: '#f87171'  // Red
            };
        default:
            return {
                icon: '❓',
                text: 'Status unknown',
                color: '#9ca3af'  // Gray
            };
    }
}

/**
 * Format CID for display (truncated with ellipsis)
 * 
 * @param {string} cid - Full CID string
 * @param {number} prefixLen - Characters to show at start (default: 8)
 * @param {number} suffixLen - Characters to show at end (default: 6)
 * @returns {string} Truncated CID like "QmXy...abc123"
 */
export function formatCID(cid, prefixLen = 8, suffixLen = 6) {
    if (!cid || cid.length <= prefixLen + suffixLen + 3) {
        return cid || '';
    }
    return `${cid.substring(0, prefixLen)}...${cid.substring(cid.length - suffixLen)}`;
}

// ============================================================================
// MODULE EXPORTS
// ============================================================================

export default {
    // Status checking
    checkFilecoinDealStatus,
    getFilecoinDealStatusDirect,
    getFileInfo,
    
    // IPFS retrieval
    getGatewayUrls,
    retrieveFromIPFS,
    
    // Display helpers
    formatDealStatus,
    formatCID,
    
    // Constants
    IPFS_GATEWAYS
};
