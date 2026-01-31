/**
 * Trinity Funding Transparency Module
 * 
 * Displays real-time funding status for the community LLM:
 * - Akash deployment escrow balance and time remaining
 * - ICP canister cycles balance
 * - Donation QR codes for AKT and ICP
 * 
 * @module modules/funding
 */

import CONFIG from '../config.js';
import { getFundingInfo } from '../api/canister-client.js';

// Funding state
let fundingData = null;
let icpFundingData = null;
let updateInterval = null;

/**
 * Initialize funding module
 */
export function initFunding() {
    console.log('💰 Initializing funding module...');
    
    // Wire up donate button
    const donateLink = document.getElementById('donateLink');
    if (donateLink) {
        donateLink.addEventListener('click', (e) => {
            e.preventDefault();
            showDonateModal();
        });
    }
    
    // Initial fetch
    updateFundingStatus();
    
    // Update every 5 minutes
    updateInterval = setInterval(updateFundingStatus, 5 * 60 * 1000);
}

/**
 * Fetch and display funding status from both Akash backend and ICP canister
 */
export async function updateFundingStatus() {
    // Fetch Akash funding status
    try {
        const response = await fetch(`${CONFIG.API_URL}/funding/status`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
            fundingData = await response.json();
        }
    } catch (error) {
        console.warn('Failed to fetch Akash funding status:', error);
    }
    
    // Fetch ICP cycles info
    try {
        icpFundingData = await getFundingInfo();
    } catch (error) {
        console.warn('Failed to fetch ICP funding info:', error);
    }
    
    // Render with whatever data we have
    if (fundingData || icpFundingData) {
        renderFundingPanel(fundingData, icpFundingData);
    } else {
        renderFundingError();
    }
}

/**
 * Render funding panel with current data
 */
function renderFundingPanel(akashData, icpData) {
    const timeEl = document.getElementById('fundingTime');
    const costEl = document.getElementById('fundingCost');
    const fillEl = document.getElementById('fundingFill');
    
    // Handle missing Akash data
    if (!akashData?.akash) {
        if (timeEl) timeEl.textContent = 'Status unavailable';
        if (fillEl) fillEl.style.width = '0%';
        return;
    }
    
    const akash = akashData.akash;
    const hoursRemaining = akash.hours_remaining;
    const escrowAkt = akash.escrow_balance_akt;
    
    // Show tier name and time remaining
    if (timeEl) {
        const tierName = akash.tier_name || 'Community';
        if (hoursRemaining !== null && hoursRemaining !== undefined && hoursRemaining > 0) {
            if (hoursRemaining > 48) {
                const days = Math.round(hoursRemaining / 24);
                timeEl.textContent = `${tierName} • ~${days} days left`;
            } else {
                timeEl.textContent = `${tierName} • ~${Math.round(hoursRemaining)}h left`;
            }
        } else {
            timeEl.textContent = `${tierName} LLM Online`;
        }
    }
    
    // Show Akash cost/balance on one line, ICP on hover/modal
    if (costEl) {
        const hourlyUsd = (akash.hourly_cost_usd || 0).toFixed(2);
        if (escrowAkt && escrowAkt > 0) {
            // Show: "$0.54/hr • 12.5 AKT escrow"
            costEl.textContent = `$${hourlyUsd}/hr • ${escrowAkt.toFixed(1)} AKT`;
        } else {
            costEl.textContent = `$${hourlyUsd}/hr`;
        }
    }
    
    // Progress bar based on hours remaining (assume 30 days = 100%)
    if (fillEl) {
        if (hoursRemaining !== null && hoursRemaining !== undefined && hoursRemaining > 0) {
            const maxHours = 720; // 30 days
            const percentage = Math.min(100, (hoursRemaining / maxHours) * 100);
            fillEl.style.width = `${percentage}%`;
            
            // Color coding
            fillEl.classList.remove('healthy', 'warning', 'critical');
            if (hoursRemaining > 72) {
                fillEl.classList.add('healthy');
            } else if (hoursRemaining > 24) {
                fillEl.classList.add('warning');
            } else {
                fillEl.classList.add('critical');
            }
        } else {
            fillEl.style.width = '100%';
            fillEl.classList.remove('warning', 'critical');
            fillEl.classList.add('healthy');
        }
    }
}

/**
 * Render error state
 */
function renderFundingError() {
    const timeEl = document.getElementById('fundingTime');
    const fillEl = document.getElementById('fundingFill');
    
    if (timeEl) timeEl.textContent = 'Offline';
    if (fillEl) {
        fillEl.style.width = '0%';
        fillEl.classList.remove('healthy', 'warning', 'critical');
    }
}

/**
 * Show donation modal with QR codes
 */
export async function showDonateModal() {
    if (!fundingData) {
        await updateFundingStatus();
    }
    
    let modal = document.getElementById('donateModal');
    if (modal) {
        modal.remove();
    }
    modal = createDonateModal();
    document.body.appendChild(modal);
    
    setTimeout(() => {
        generateQRCodes();
    }, 100);
    
    modal.style.display = 'flex';
}

/**
 * Create the donation modal element
 */
function createDonateModal() {
    const modal = document.createElement('div');
    modal.id = 'donateModal';
    modal.className = 'modal-overlay';
    
    // Calculate display values
    const akash = fundingData?.akash || {};
    const hoursRemaining = akash.hours_remaining;
    const escrowAkt = akash.escrow_balance_akt || 0;
    const escrowUsd = akash.escrow_balance_usd || 0;
    const hourlyAkt = akash.hourly_cost_akt || 0;
    const hourlyUsd = akash.hourly_cost_usd || 0;
    const aktPrice = fundingData?.akt_price_usd || 0;
    
    // ICP cycles info
    const cyclesT = icpFundingData?.cycles_trillion || 0;
    const cyclesUsd = (cyclesT * 1.37).toFixed(2); // 1T cycles ≈ $1.37
    const requestsRemaining = icpFundingData?.estimated_requests_remaining || 0;
    
    // Format time remaining
    let timeRemainingText = 'Unknown';
    if (hoursRemaining !== null && hoursRemaining !== undefined && hoursRemaining > 0) {
        if (hoursRemaining > 48) {
            timeRemainingText = `~${Math.round(hoursRemaining / 24)} days`;
        } else {
            timeRemainingText = `~${Math.round(hoursRemaining)} hours`;
        }
    }
    
    modal.innerHTML = `
        <div class="modal donate-modal-content" style="max-width: 520px;">
            <button class="modal-close" onclick="document.getElementById('donateModal').style.display='none'">×</button>
            <h3 style="margin-bottom: 8px;">Fund the Community LLM</h3>
            <p style="font-size: 12px; color: #888; margin-bottom: 16px;">
                Your donations keep Trinity free and decentralized for everyone.
            </p>
            
            <!-- Funding Status -->
            <div style="background: #2d2d2d; border-radius: 8px; padding: 12px; margin-bottom: 16px;">
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; text-align: center;">
                    <div>
                        <div style="font-size: 10px; color: #888; margin-bottom: 4px;">AKASH (GPU)</div>
                        <div style="font-size: 16px; font-weight: 600; color: #10b981;">${escrowAkt.toFixed(2)} AKT</div>
                        <div style="font-size: 10px; color: #666;">~$${escrowUsd.toFixed(2)} • ${timeRemainingText}</div>
                    </div>
                    <div>
                        <div style="font-size: 10px; color: #888; margin-bottom: 4px;">ICP (Frontend)</div>
                        <div style="font-size: 16px; font-weight: 600; color: #60a5fa;">${cyclesT.toFixed(2)}T cycles</div>
                        <div style="font-size: 10px; color: #666;">~$${cyclesUsd} • ${requestsRemaining.toLocaleString()} requests</div>
                    </div>
                    <div>
                        <div style="font-size: 10px; color: #888; margin-bottom: 4px;">IPFS</div>
                        <div style="font-size: 16px; font-weight: 600; color: #fbbf24;">Free</div>
                        <div style="font-size: 10px; color: #666;">1GB via <a href="https://docs.ipfs.tech/concepts/what-is-ipfs/" target="_blank" style="color: #60a5fa;">Lighthouse</a></div>
                    </div>
                </div>
                <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #3d3d3d; text-align: center;">
                    <span style="font-size: 11px; color: #888;">
                        Running cost: <strong>$${hourlyUsd.toFixed(2)}/hr</strong> (${hourlyAkt.toFixed(3)} AKT @ $${aktPrice.toFixed(2)})
                    </span>
                </div>
            </div>
            
            <div class="donate-grid">
                <div class="donate-option">
                    <h4>Akash (AKT)</h4>
                    <p style="font-size: 10px; color: #666; margin-bottom: 8px;">Powers the AI compute</p>
                    <div class="donate-qr" id="aktQR"></div>
                    <div class="donate-address" id="aktAddress" onclick="copyAddress('akt')">
                        ${fundingData?.donations?.akt_address || 'Loading...'}
                    </div>
                </div>
                
                <div class="donate-option">
                    <h4>Internet Computer (ICP)</h4>
                    <p style="font-size: 10px; color: #666; margin-bottom: 8px;">Powers the frontend</p>
                    <div class="donate-qr" id="icpQR"></div>
                    <div class="donate-address" id="icpAddress" onclick="copyAddress('icp')">
                        ${fundingData?.icp?.backend_canister || 'Loading...'}
                    </div>
                </div>
            </div>
            
            <p class="donate-note">
                Click address to copy • Scan QR to send directly
            </p>
        </div>
    `;
    
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    return modal;
}

/**
 * Generate QR codes for donation addresses
 */
function generateQRCodes() {
    const aktContainer = document.getElementById('aktQR');
    const icpContainer = document.getElementById('icpQR');
    
    if (aktContainer) aktContainer.innerHTML = '';
    if (icpContainer) icpContainer.innerHTML = '';
    
    if (aktContainer && fundingData?.donations?.akt_address && typeof QRCode !== 'undefined') {
        new QRCode(aktContainer, {
            text: fundingData.donations.akt_address,
            width: 104,
            height: 104,
            colorDark: '#000000',
            colorLight: '#ffffff',
            correctLevel: QRCode.CorrectLevel.M
        });
    }
    
    if (icpContainer && fundingData?.icp?.backend_canister && typeof QRCode !== 'undefined') {
        new QRCode(icpContainer, {
            text: fundingData.icp.backend_canister,
            width: 104,
            height: 104,
            colorDark: '#000000',
            colorLight: '#ffffff',
            correctLevel: QRCode.CorrectLevel.M
        });
    }
}

/**
 * Copy donation address to clipboard
 */
window.copyAddress = function(type) {
    let address = '';
    if (type === 'akt') {
        address = fundingData?.donations?.akt_address || '';
    } else if (type === 'icp') {
        address = fundingData?.icp?.backend_canister || '';
    }
    
    if (address) {
        navigator.clipboard.writeText(address).then(() => {
            const el = document.getElementById(`${type}Address`);
            if (el) {
                const original = el.textContent;
                el.textContent = 'Copied!';
                el.style.color = '#10b981';
                setTimeout(() => {
                    el.textContent = original;
                    el.style.color = '';
                }, 1500);
            }
        });
    }
};

/**
 * Get current funding data
 */
export function getFundingData() {
    return fundingData;
}

/**
 * Cleanup on module unload
 */
export function cleanup() {
    if (updateInterval) {
        clearInterval(updateInterval);
        updateInterval = null;
    }
}
