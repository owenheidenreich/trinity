/**
 * Trinity Funding Transparency Module
 * 
 * Displays real-time funding status for the community LLM:
 * - Akash deployment escrow balance and time remaining
 * - AKT price in USD
 * - Donation QR codes for AKT and ICP
 * 
 * @module modules/funding
 */

import CONFIG from '../config.js';

// Funding state
let fundingData = null;
let updateInterval = null;

/**
 * Initialize funding module
 * Sets up periodic updates and click handlers
 */
export function initFunding() {
    // Wire up donate button
    const donateLink = document.getElementById('donateLink');
    if (donateLink) {
        donateLink.addEventListener('click', (e) => {
            e.preventDefault();
            showDonateModal();
        });
    }
    
    // Wire up private session button (Phase 2 - currently hidden)
    const privateBtn = document.getElementById('privateSessionBtn');
    if (privateBtn) {
        privateBtn.addEventListener('click', (e) => {
            e.preventDefault();
            showPrivateSessionModal();
        });
    }
    
    // Initial fetch
    updateFundingStatus();
    
    // Update every 5 minutes
    updateInterval = setInterval(updateFundingStatus, 5 * 60 * 1000);
}

/**
 * Fetch and display funding status
 */
export async function updateFundingStatus() {
    try {
        const response = await fetch(`${CONFIG.API_URL}/funding/status`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        fundingData = await response.json();
        renderFundingPanel(fundingData);
        
    } catch (error) {
        console.warn('Failed to fetch funding status:', error);
        renderFundingError();
    }
}

/**
 * Render funding panel with current data
 */
function renderFundingPanel(data) {
    const timeEl = document.getElementById('fundingTime');
    const costEl = document.getElementById('fundingCost');
    const fillEl = document.getElementById('fundingFill');
    
    if (!data.akash) {
        if (timeEl) timeEl.textContent = 'Status unavailable';
        if (fillEl) fillEl.style.width = '0%';
        return;
    }
    
    const akash = data.akash;
    const sessionType = akash.session_type || 'community';
    
    // For community deployments, show "LLM Online" with tier info
    if (sessionType === 'community') {
        if (timeEl) {
            timeEl.textContent = `${akash.tier_name || 'Community'} LLM Online`;
        }
        if (costEl && data.akt_price_usd) {
            const dailyCost = akash.daily_cost_usd || 0;
            costEl.textContent = `$${dailyCost.toFixed(2)}/day`;
        }
        // Show green "healthy" bar for online community LLM
        if (fillEl) {
            fillEl.style.width = '100%';
            fillEl.classList.remove('warning', 'critical');
            fillEl.classList.add('healthy');
        }
        return;
    }
    
    // For private sessions, show time remaining
    const hoursRemaining = akash.hours_remaining || 0;
    const minutesRemaining = akash.minutes_remaining || 0;
    
    // Calculate percentage (based on initial funded amount)
    const fundedAkt = akash.funded_akt || 1;
    const hourlyRate = akash.hourly_cost_akt || 0.15;
    const maxHours = fundedAkt / hourlyRate;
    const percentage = Math.min(100, Math.max(0, (hoursRemaining / maxHours) * 100));
    
    // Update progress bar
    if (fillEl) {
        fillEl.style.width = `${percentage}%`;
        
        // Color coding
        fillEl.classList.remove('healthy', 'warning', 'critical');
        if (hoursRemaining > 1) {
            fillEl.classList.add('healthy');
        } else if (minutesRemaining > 15) {
            fillEl.classList.add('warning');
        } else {
            fillEl.classList.add('critical');
        }
    }
    
    // Update time remaining
    if (timeEl) {
        if (hoursRemaining >= 1) {
            timeEl.textContent = `~${Math.round(hoursRemaining)} hours remaining`;
        } else if (minutesRemaining > 0) {
            timeEl.textContent = `~${Math.round(minutesRemaining)} min remaining`;
        } else {
            timeEl.textContent = 'Session expired';
        }
    }
    
    // Update cost info
    if (costEl && data.akt_price_usd) {
        const hourlyUsd = akash.hourly_cost_usd || 0;
        costEl.textContent = `$${hourlyUsd.toFixed(2)}/hr`;
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
export function showDonateModal() {
    // Create modal if it doesn't exist
    let modal = document.getElementById('donateModal');
    if (!modal) {
        modal = createDonateModal();
        document.body.appendChild(modal);
    }
    
    // Generate QR codes
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
    modal.innerHTML = `
        <div class="modal donate-modal-content">
            <button class="modal-close" onclick="document.getElementById('donateModal').style.display='none'">×</button>
            <h3 style="margin-bottom: 8px;">Fund the Community LLM</h3>
            <p style="font-size: 12px; color: #888; margin-bottom: 16px;">
                Your donations keep Trinity free and decentralized for everyone.
            </p>
            
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
            
            ${fundingData?.akash ? `
            <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid #3d3d3d;">
                <p style="font-size: 11px; color: #666;">
                    Current status: ${fundingData.akash.days_remaining?.toFixed(1) || '?'} days remaining
                    (${fundingData.akash.escrow_akt?.toFixed(2) || '?'} AKT in escrow)
                </p>
            </div>
            ` : ''}
        </div>
    `;
    
    // Close on backdrop click
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
    
    // Clear existing
    if (aktContainer) aktContainer.innerHTML = '';
    if (icpContainer) icpContainer.innerHTML = '';
    
    // Generate AKT QR
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
    
    // Generate ICP QR
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
            // Show brief feedback
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
 * Show private session modal (Phase 2)
 * This will contain tier selection and payment flow
 */
function showPrivateSessionModal() {
    // Create modal if it doesn't exist
    let modal = document.getElementById('privateSessionModal');
    if (!modal) {
        modal = createPrivateSessionModal();
        document.body.appendChild(modal);
    }
    
    // Update prices with current AKT rate
    updateTierPrices();
    
    modal.style.display = 'flex';
}

/**
 * Create the private session modal
 */
function createPrivateSessionModal() {
    const modal = document.createElement('div');
    modal.id = 'privateSessionModal';
    modal.className = 'modal-overlay';
    
    const tiers = fundingData?.private_session?.tiers || [
        { name: 'Starter', model: 'tinyllama', hourly_akt: 0.15, ram_gb: 4 },
        { name: 'Standard', model: 'llama3.1:8b', hourly_akt: 0.4, ram_gb: 16 },
        { name: 'Professional', model: 'qwen2.5:72b', hourly_akt: 1.75, ram_gb: 64 }
    ];
    
    modal.innerHTML = `
        <div class="modal private-session-modal">
            <button class="modal-close" onclick="document.getElementById('privateSessionModal').style.display='none'">×</button>
            
            <h3 style="margin-bottom: 4px;">🔒 Launch Your Private LLM</h3>
            <p style="font-size: 11px; color: #888; margin-bottom: 20px;">
                Dedicated resources, no sharing, full privacy
            </p>
            
            <div class="tier-selector" id="tierSelector">
                ${tiers.map((tier, i) => `
                    <div class="tier-option ${i === 1 ? 'selected' : ''}" data-tier="${i}">
                        <div class="tier-radio">${i === 1 ? '●' : '○'}</div>
                        <div class="tier-info">
                            <div class="tier-name">${tier.name}</div>
                            <div class="tier-model">${tier.model}</div>
                        </div>
                        <div class="tier-price">
                            <span class="tier-akt">${tier.hourly_akt} AKT/hr</span>
                            <span class="tier-usd" id="tierUsd${i}">≈ $?.??/hr</span>
                        </div>
                        <div class="tier-specs">${tier.ram_gb}GB RAM</div>
                    </div>
                `).join('')}
            </div>
            
            <div class="duration-selector">
                <label>Session Duration:</label>
                <select id="sessionDuration">
                    <option value="1">1 hour</option>
                    <option value="2" selected>2 hours</option>
                    <option value="4">4 hours</option>
                    <option value="8">8 hours</option>
                    <option value="24">24 hours</option>
                </select>
            </div>
            
            <div class="cost-breakdown" id="costBreakdown">
                <div class="cost-header">Cost Breakdown</div>
                <div class="cost-row">
                    <span>Hardware (95%)</span>
                    <span id="costHardware">0.76 AKT</span>
                </div>
                <div class="cost-row">
                    <span>Community Fund (4%)</span>
                    <span id="costCommunity">0.032 AKT</span>
                </div>
                <div class="cost-row">
                    <span>Platform Fee (1%)</span>
                    <span id="costPlatform">0.008 AKT</span>
                </div>
                <div class="cost-row cost-total">
                    <span>Total</span>
                    <span id="costTotal">0.8 AKT (~$?.??)</span>
                </div>
            </div>
            
            <div class="payment-section" id="paymentSection" style="display: none;">
                <p style="font-size: 11px; color: #888; margin-bottom: 8px;">
                    Send AKT to start your session:
                </p>
                <div class="payment-address" id="paymentAddress">
                    ${fundingData?.donations?.akt_address || 'Loading...'}
                </div>
                <div class="payment-qr" id="paymentQR"></div>
                <div class="payment-status" id="paymentStatus">
                    Waiting for payment...
                </div>
            </div>
            
            <button class="launch-btn" id="launchBtn" onclick="window.requestPrivateSession()">
                Continue to Payment
            </button>
            
            <p style="font-size: 10px; color: #666; margin-top: 12px; text-align: center;">
                95% pays for your hardware • 4% funds the free community LLM • 1% platform
            </p>
        </div>
    `;
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // Wire up tier selection
    setTimeout(() => {
        const tierOptions = modal.querySelectorAll('.tier-option');
        tierOptions.forEach(option => {
            option.addEventListener('click', () => {
                tierOptions.forEach(o => {
                    o.classList.remove('selected');
                    o.querySelector('.tier-radio').textContent = '○';
                });
                option.classList.add('selected');
                option.querySelector('.tier-radio').textContent = '●';
                updateCostBreakdown();
            });
        });
        
        // Wire up duration change
        const durationSelect = modal.querySelector('#sessionDuration');
        if (durationSelect) {
            durationSelect.addEventListener('change', updateCostBreakdown);
        }
    }, 0);
    
    return modal;
}

/**
 * Update tier prices with current AKT/USD rate
 */
function updateTierPrices() {
    const aktPrice = fundingData?.akt_price_usd || 0;
    const tiers = fundingData?.private_session?.tiers || [];
    
    tiers.forEach((tier, i) => {
        const usdEl = document.getElementById(`tierUsd${i}`);
        if (usdEl && aktPrice > 0) {
            const usdPrice = (tier.hourly_akt * aktPrice).toFixed(2);
            usdEl.textContent = `≈ $${usdPrice}/hr`;
        }
    });
    
    updateCostBreakdown();
}

/**
 * Update cost breakdown based on selected tier and duration
 */
function updateCostBreakdown() {
    const selectedTier = document.querySelector('.tier-option.selected');
    const durationSelect = document.getElementById('sessionDuration');
    
    if (!selectedTier || !durationSelect) return;
    
    const tierIndex = parseInt(selectedTier.dataset.tier);
    const tiers = fundingData?.private_session?.tiers || [];
    const tier = tiers[tierIndex];
    const duration = parseInt(durationSelect.value);
    const aktPrice = fundingData?.akt_price_usd || 0;
    
    if (!tier) return;
    
    // Calculate costs
    const baseCost = tier.hourly_akt * duration;
    const totalCost = baseCost / 0.95; // Add 5% markup
    const hardwareCost = baseCost;
    const communityCost = totalCost * 0.04;
    const platformCost = totalCost * 0.01;
    
    // Update display
    document.getElementById('costHardware').textContent = `${hardwareCost.toFixed(3)} AKT`;
    document.getElementById('costCommunity').textContent = `${communityCost.toFixed(3)} AKT`;
    document.getElementById('costPlatform').textContent = `${platformCost.toFixed(3)} AKT`;
    
    let totalText = `${totalCost.toFixed(3)} AKT`;
    if (aktPrice > 0) {
        totalText += ` (~$${(totalCost * aktPrice).toFixed(2)})`;
    }
    document.getElementById('costTotal').textContent = totalText;
}

/**
 * Handle private session payment request
 */
window.requestPrivateSession = function() {
    const paymentSection = document.getElementById('paymentSection');
    const launchBtn = document.getElementById('launchBtn');
    
    if (paymentSection && launchBtn) {
        paymentSection.style.display = 'block';
        launchBtn.textContent = 'Waiting for Payment...';
        launchBtn.disabled = true;
        
        // Generate payment QR
        const qrContainer = document.getElementById('paymentQR');
        if (qrContainer && fundingData?.donations?.akt_address && typeof QRCode !== 'undefined') {
            qrContainer.innerHTML = '';
            new QRCode(qrContainer, {
                text: fundingData.donations.akt_address,
                width: 120,
                height: 120,
                colorDark: '#000000',
                colorLight: '#ffffff',
                correctLevel: QRCode.CorrectLevel.M
            });
        }
        
        // TODO: Implement payment detection
        // This would poll a backend endpoint or use websockets to detect incoming payment
        // Once payment is detected, trigger deployment
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
