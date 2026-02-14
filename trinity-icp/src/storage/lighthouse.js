// ============================================================================
// Trinity Frontend - IPFS Storage Module (Lighthouse)
// ============================================================================
// 
// PURPOSE:
// Provides frontend utilities for IPFS storage via Lighthouse.
// Primary storage operations are handled by the backend (inference_server.py),
// but this module provides client-side helpers for:
//   - Retrieving content from IPFS gateways
//   - Storage quota information
//
// ARCHITECTURE NOTE:
// The actual upload to IPFS/Lighthouse happens on the backend to:
//   1. Keep the API key secure (not exposed to browser)
//   2. Maintain encryption/decryption in one place
//   3. Allow backend-side metadata management
//
// This module complements the backend by providing client-side utilities.
//
// DEPENDENCIES:
//   - @lighthouse-web3/sdk (installed via npm)
//
// Learn more about IPFS: https://docs.ipfs.tech/concepts/what-is-ipfs/
//
// ============================================================================

import lighthouse from '@lighthouse-web3/sdk';
import Logger from '../core/logger.js';

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
// IPFS STATUS CHECK
// ============================================================================

/**
 * Check IPFS availability status for an archived chat
 * 
 * @param {string} cid - IPFS Content Identifier
 * @param {string} apiBaseUrl - Base URL for backend API
 * @returns {Promise<{status: string, message: string, gateways: Array}>}
 */
export async function checkIPFSStatus(cid, apiBaseUrl) {
    if (!cid) {
        return {
            status: 'error',
            message: 'No CID provided',
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
        
        Logger.debug(`IPFS status for ${cid.substring(0, 12)}...:`, data.status);
        
        return {
            cid: data.cid,
            status: data.status || 'available',
            message: data.message || 'Available on IPFS',
            gateways: data.gateways || getGatewayUrls(cid),
            checkedAt: data.checkedAt
        };
    } catch (error) {
        Logger.error('Failed to check IPFS status:', error);
        return {
            status: 'error',
            message: error.message,
            gateways: getGatewayUrls(cid)
        };
    }
}

// Keep old function name for backwards compatibility
export const checkFilecoinDealStatus = checkIPFSStatus;

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
            Logger.debug(`Trying gateway: ${gatewayUrl}`);
            
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), GATEWAY_TIMEOUT_MS);
            
            const response = await fetch(gatewayUrl, {
                signal: controller.signal,
                headers: { 'Accept': 'application/json, text/plain, */*' }
            });
            
            clearTimeout(timeoutId);

            if (response.ok) {
                const content = await response.text();
                Logger.debug(`Successfully retrieved from: ${gatewayUrl}`);
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
            Logger.warn(`Gateway failed: ${gatewayUrl}`, error.message);
        }
    }

    throw new Error(`All IPFS gateways failed for CID ${cid}:\n${errors.join('\n')}`);
}

// ============================================================================
// LIGHTHOUSE SDK UTILITIES
// ============================================================================

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
        Logger.error('Failed to get file info:', error);
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
                text: 'Stored on IPFS',
                color: '#4ade80'  // Green
            };
        case 'pending':
            return {
                icon: '⏳',
                text: 'Uploading to IPFS...',
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
    checkIPFSStatus,
    checkFilecoinDealStatus,  // Legacy alias
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
