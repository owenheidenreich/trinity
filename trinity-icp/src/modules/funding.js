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
    
    // Wire up private session button
    const privateBtn = document.getElementById('privateSessionBtn');
    if (privateBtn) {
        privateBtn.addEventListener('click', (e) => {
            e.preventDefault();
            showPrivateSessionModal();
        });
    }
    
    // Check for existing active session and resume timer if needed
    const activeSession = checkActiveSession();
    if (activeSession) {
        console.log('🔒 Resuming active private session:', activeSession.tier_name);
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
    const privateBtn = document.getElementById('privateSessionBtn');
    
    if (!data.akash) {
        if (timeEl) timeEl.textContent = 'Status unavailable';
        if (fillEl) fillEl.style.width = '0%';
        return;
    }
    
    // Show private session button if enabled
    if (privateBtn && data.private_session?.enabled) {
        privateBtn.style.display = 'flex';
    }
    
    const akash = data.akash;
    const sessionType = akash.session_type || 'community';
    
    // For community deployments, show "LLM Online" with tier info
    if (sessionType === 'community') {
        if (timeEl) {
            timeEl.textContent = `${akash.tier_name || 'Community'} LLM Online`;
        }
        if (costEl && data.akt_price_usd) {
            const hourlyCost = akash.hourly_cost_usd || 0;
            costEl.textContent = `$${hourlyCost.toFixed(2)}/hr`;
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
export async function showDonateModal() {
    // Fetch funding data if not available
    if (!fundingData) {
        await updateFundingStatus();
    }
    
    // Create modal if it doesn't exist, or recreate to update addresses
    let modal = document.getElementById('donateModal');
    if (modal) {
        modal.remove();
    }
    modal = createDonateModal();
    document.body.appendChild(modal);
    
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
                    Running cost: $${fundingData.akash.hourly_cost_usd?.toFixed(2) || '?'}/hr 
                    (${fundingData.akash.hourly_cost_akt?.toFixed(2) || '?'} AKT/hr at $${fundingData.akt_price_usd?.toFixed(2) || '?'}/AKT)
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
async function showPrivateSessionModal() {
    // Fetch funding data if not available
    if (!fundingData) {
        await updateFundingStatus();
    }
    
    // Create modal if it doesn't exist, or recreate to ensure fresh state
    let modal = document.getElementById('privateSessionModal');
    if (modal) {
        modal.remove();
    }
    modal = createPrivateSessionModal();
    document.body.appendChild(modal);
    
    // Update prices with current AKT rate
    updateTierPrices();
    
    modal.style.display = 'flex';
}

/**
 * Create the private session modal with two-step confirmation
 * Step 1: Tier and duration selection
 * Step 2: Itemized review with confirm/back
 */
function createPrivateSessionModal() {
    const modal = document.createElement('div');
    modal.id = 'privateSessionModal';
    modal.className = 'modal-overlay';
    
    const tiers = fundingData?.private_session?.tiers || [
        { name: 'Starter', model: 'tinyllama:1.1b', hourly_akt: 0.15, ram_gb: 4 },
        { name: 'Standard', model: 'llama3.1:8b', hourly_akt: 0.4, ram_gb: 16 },
        { name: 'Professional', model: 'qwen2.5:72b', hourly_akt: 1.75, ram_gb: 64 }
    ];
    
    modal.innerHTML = `
        <div class="modal private-session-modal">
            <button class="modal-close" onclick="document.getElementById('privateSessionModal').style.display='none'">×</button>
            
            <!-- Step 1: Selection -->
            <div id="sessionStep1" class="session-step">
                <h3 style="margin-bottom: 4px;">Launch Your Private LLM</h3>
                <p style="font-size: 11px; color: #888; margin-bottom: 20px;">
                    Dedicated resources, no sharing, full privacy
                </p>
                
                <div class="tier-selector" id="tierSelector">
                    ${tiers.map((tier, i) => `
                        <div class="tier-option ${i === 0 ? 'selected' : ''}" data-tier="${i}">
                            <div class="tier-radio">${i === 0 ? '●' : '○'}</div>
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
                        <option value="1" selected>1 hour</option>
                        <option value="2">2 hours</option>
                        <option value="4">4 hours</option>
                        <option value="8">8 hours</option>
                        <option value="24">24 hours</option>
                    </select>
                </div>
                
                <button class="launch-btn" id="reviewOrderBtn">
                    Review Order
                </button>
                
                <p style="font-size: 10px; color: #666; margin-top: 12px; text-align: center;">
                    95% pays for your hardware • 4% funds the free community LLM • 1% platform
                </p>
            </div>
            
            <!-- Step 2: Review and Confirm -->
            <div id="sessionStep2" class="session-step" style="display: none;">
                <h3 style="margin-bottom: 16px;">Confirm Your Order</h3>
                
                <div class="order-summary">
                    <div class="order-row">
                        <span class="order-label">Model</span>
                        <span class="order-value" id="orderModel">-</span>
                    </div>
                    <div class="order-row">
                        <span class="order-label">Duration</span>
                        <span class="order-value" id="orderDuration">-</span>
                    </div>
                    <div class="order-row">
                        <span class="order-label">Hardware (95%)</span>
                        <span class="order-value" id="orderHardware">-</span>
                    </div>
                    <div class="order-row">
                        <span class="order-label">Community Fund (4%)</span>
                        <span class="order-value" id="orderCommunity">-</span>
                    </div>
                    <div class="order-row">
                        <span class="order-label">Platform Fee (1%)</span>
                        <span class="order-value" id="orderPlatform">-</span>
                    </div>
                    <div class="order-row order-total">
                        <span class="order-label">Total</span>
                        <span class="order-value" id="orderTotal">-</span>
                    </div>
                </div>
                
                <div class="payment-instructions">
                    <p style="font-size: 11px; color: #888; margin-bottom: 8px;">
                        Send payment to:
                    </p>
                    <div class="payment-address" id="paymentAddress">
                        ${fundingData?.donations?.akt_address || 'Loading...'}
                    </div>
                    <p style="font-size: 10px; color: #666; margin-top: 8px;">
                        Include memo: <code id="paymentMemo">-</code>
                    </p>
                </div>
                
                <div class="confirm-buttons">
                    <button class="back-btn" id="backToStep1Btn">
                        Back
                    </button>
                    <button class="launch-btn" id="confirmPaymentBtn">
                        Yes, Send Payment
                    </button>
                </div>
                
                <p style="font-size: 10px; color: #ff6b6b; margin-top: 12px; text-align: center;">
                    ⚠️ No refunds • Session starts when payment is confirmed
                </p>
            </div>
            
            <!-- Step 3: Waiting for Payment -->
            <div id="sessionStep3" class="session-step" style="display: none;">
                <h3 style="margin-bottom: 16px;">Waiting for Payment</h3>
                
                <div class="payment-qr" id="paymentQR"></div>
                
                <div class="payment-address" id="paymentAddressQR">
                    ${fundingData?.donations?.akt_address || 'Loading...'}
                </div>
                
                <p style="font-size: 11px; color: #888; margin: 12px 0;">
                    Amount: <strong id="paymentAmount">-</strong><br>
                    Memo: <code id="paymentMemoQR">-</code>
                </p>
                
                <div class="payment-status" id="paymentStatus">
                    <div class="spinner"></div>
                    <span>Scanning blockchain for payment...</span>
                </div>
                
                <button class="back-btn" id="cancelPaymentBtn" style="margin-top: 16px;">
                    Cancel
                </button>
            </div>
            
            <!-- Step 4: Deploying -->
            <div id="sessionStep4" class="session-step" style="display: none;">
                <h3 style="margin-bottom: 16px;">Payment Confirmed!</h3>
                
                <div class="deploy-status">
                    <div class="spinner large"></div>
                    <p style="margin-top: 16px;">Deploying your private LLM...</p>
                    <p style="font-size: 11px; color: #888;">This may take 1-2 minutes</p>
                </div>
            </div>
            
            <!-- Step 5: Session Active -->
            <div id="sessionStep5" class="session-step" style="display: none;">
                <h3 style="margin-bottom: 16px; color: #10b981;">Session Active!</h3>
                
                <div class="session-info">
                    <p><strong id="activeModel">-</strong></p>
                    <p style="font-size: 11px; color: #888;" id="activeExpiry">-</p>
                </div>
                
                <div class="archive-reminder" style="margin: 16px 0; padding: 12px; background: #2d2d2d; border-radius: 6px;">
                    <p style="font-size: 11px; color: #fbbf24; margin-bottom: 8px;">
                        ⚠️ Archive your chats before the session expires
                    </p>
                    <p style="font-size: 10px; color: #888;">
                        Chats on private sessions are not automatically saved.
                    </p>
                </div>
                
                <button class="launch-btn" id="startChattingBtn">
                    Start Chatting
                </button>
            </div>
        </div>
    `;
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // Wire up event handlers after render
    setTimeout(() => {
        wirePrivateSessionHandlers(modal, tiers);
    }, 0);
    
    return modal;
}

/**
 * Wire up all event handlers for private session modal
 */
function wirePrivateSessionHandlers(modal, tiers) {
    // Tier selection
    const tierOptions = modal.querySelectorAll('.tier-option');
    tierOptions.forEach(option => {
        option.addEventListener('click', () => {
            tierOptions.forEach(o => {
                o.classList.remove('selected');
                o.querySelector('.tier-radio').textContent = '○';
            });
            option.classList.add('selected');
            option.querySelector('.tier-radio').textContent = '●';
        });
    });
    
    // Review Order button -> Step 2
    const reviewBtn = modal.querySelector('#reviewOrderBtn');
    if (reviewBtn) {
        reviewBtn.addEventListener('click', () => showStep2(modal, tiers));
    }
    
    // Back button -> Step 1
    const backBtn = modal.querySelector('#backToStep1Btn');
    if (backBtn) {
        backBtn.addEventListener('click', () => {
            modal.querySelector('#sessionStep1').style.display = 'block';
            modal.querySelector('#sessionStep2').style.display = 'none';
        });
    }
    
    // Confirm Payment button -> Step 3
    const confirmBtn = modal.querySelector('#confirmPaymentBtn');
    if (confirmBtn) {
        confirmBtn.addEventListener('click', () => startPaymentPolling(modal, tiers));
    }
    
    // Cancel button -> close modal
    const cancelBtn = modal.querySelector('#cancelPaymentBtn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            if (window.paymentPollingInterval) {
                clearInterval(window.paymentPollingInterval);
            }
            modal.style.display = 'none';
        });
    }
    
    // Start Chatting button -> close modal and start session
    const startBtn = modal.querySelector('#startChattingBtn');
    if (startBtn) {
        startBtn.addEventListener('click', () => {
            modal.style.display = 'none';
            // Focus the input
            const input = document.getElementById('userInput');
            if (input) input.focus();
        });
    }
}

/**
 * Show Step 2: Order review with itemized breakdown
 */
function showStep2(modal, tiers) {
    const selectedTier = modal.querySelector('.tier-option.selected');
    const durationSelect = modal.querySelector('#sessionDuration');
    
    if (!selectedTier || !durationSelect) return;
    
    const tierIndex = parseInt(selectedTier.dataset.tier);
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
    
    // Generate session ID
    const sessionId = `ps-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const memo = `trinity:tier:${tierIndex + 1}:${sessionId}`;
    
    // Store for later
    window.pendingSession = {
        tier: tierIndex + 1,
        tierName: tier.name,
        model: tier.model,
        hours: duration,
        totalAkt: totalCost,
        sessionId: sessionId,
        memo: memo
    };
    
    // Update order summary
    modal.querySelector('#orderModel').textContent = `${tier.name} (${tier.model})`;
    modal.querySelector('#orderDuration').textContent = `${duration} hour${duration > 1 ? 's' : ''}`;
    modal.querySelector('#orderHardware').textContent = `${hardwareCost.toFixed(4)} AKT`;
    modal.querySelector('#orderCommunity').textContent = `${communityCost.toFixed(4)} AKT`;
    modal.querySelector('#orderPlatform').textContent = `${platformCost.toFixed(4)} AKT`;
    
    let totalText = `${totalCost.toFixed(4)} AKT`;
    if (aktPrice > 0) {
        totalText += ` (~$${(totalCost * aktPrice).toFixed(2)})`;
    }
    modal.querySelector('#orderTotal').textContent = totalText;
    modal.querySelector('#paymentMemo').textContent = memo;
    
    // Switch steps
    modal.querySelector('#sessionStep1').style.display = 'none';
    modal.querySelector('#sessionStep2').style.display = 'block';
}

/**
 * Start polling for payment and show Step 3
 */
async function startPaymentPolling(modal, tiers) {
    const session = window.pendingSession;
    if (!session) return;
    
    // Update step 3 with payment details
    modal.querySelector('#paymentAmount').textContent = `${session.totalAkt.toFixed(4)} AKT`;
    modal.querySelector('#paymentMemoQR').textContent = session.memo;
    
    // Switch to step 3
    modal.querySelector('#sessionStep2').style.display = 'none';
    modal.querySelector('#sessionStep3').style.display = 'block';
    
    // Generate QR code
    const qrContainer = modal.querySelector('#paymentQR');
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
    
    // First, request a session from backend to register it
    try {
        const response = await fetch(`${CONFIG.API_URL}/session/request`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tier: session.tier,
                hours: session.hours
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            // Use backend-provided session_id and memo
            window.pendingSession.sessionId = data.session_id;
            window.pendingSession.memo = data.memo;
            modal.querySelector('#paymentMemoQR').textContent = data.memo;
        }
    } catch (error) {
        console.warn('Failed to register session:', error);
    }
    
    // Start polling for payment confirmation
    window.paymentPollingInterval = setInterval(async () => {
        try {
            const response = await fetch(`${CONFIG.API_URL}/session/check/${window.pendingSession.sessionId}`);
            const data = await response.json();
            
            if (data.status === 'deploying') {
                // Payment received, deploying
                clearInterval(window.paymentPollingInterval);
                modal.querySelector('#sessionStep3').style.display = 'none';
                modal.querySelector('#sessionStep4').style.display = 'block';
                
                // Continue polling for active status
                pollForActive(modal);
            } else if (data.status === 'active') {
                // Already active
                clearInterval(window.paymentPollingInterval);
                showSessionActive(modal, data);
            }
        } catch (error) {
            console.warn('Error checking session status:', error);
        }
    }, 5000); // Poll every 5 seconds
}

/**
 * Poll for session to become active
 */
function pollForActive(modal) {
    const checkActive = setInterval(async () => {
        try {
            const response = await fetch(`${CONFIG.API_URL}/session/check/${window.pendingSession.sessionId}`);
            const data = await response.json();
            
            if (data.status === 'active') {
                clearInterval(checkActive);
                showSessionActive(modal, data);
            }
        } catch (error) {
            console.warn('Error polling for active:', error);
        }
    }, 3000);
    
    // Timeout after 5 minutes
    setTimeout(() => {
        clearInterval(checkActive);
    }, 5 * 60 * 1000);
}

/**
 * Show session is active (Step 5)
 */
function showSessionActive(modal, data) {
    modal.querySelector('#sessionStep4').style.display = 'none';
    modal.querySelector('#sessionStep5').style.display = 'block';
    
    modal.querySelector('#activeModel').textContent = data.tier_name || window.pendingSession?.tierName || 'Private LLM';
    
    // Format expiry
    if (data.expires_at) {
        const expiry = new Date(data.expires_at);
        modal.querySelector('#activeExpiry').textContent = `Expires: ${expiry.toLocaleString()}`;
    }
    
    // Store session info for API calls
    if (data.endpoint) {
        localStorage.setItem('trinity_private_session', JSON.stringify({
            endpoint: data.endpoint,
            expires_at: data.expires_at,
            session_id: data.session_id,
            model: data.model,
            tier_name: data.tier_name
        }));
        
        // Also start the session timer
        import('./sessionTimer.js').then(module => {
            if (data.expires_at) {
                module.startSessionTimer(data.expires_at);
            }
        }).catch(err => console.warn('Session timer not available:', err));
    }
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
 * Update cost breakdown - kept for backwards compatibility
 * but no longer used with new two-step flow
 */
function updateCostBreakdown() {
    // No-op - cost is calculated in showStep2
}

/**
 * Get current funding data
 */
export function getFundingData() {
    return fundingData;
}

/**
 * Check for active private session on load
 */
export function checkActiveSession() {
    const session = localStorage.getItem('trinity_private_session');
    if (session) {
        try {
            const data = JSON.parse(session);
            const expiry = new Date(data.expires_at);
            
            if (expiry > new Date()) {
                // Session still valid, start timer
                import('./sessionTimer.js').then(module => {
                    module.startSessionTimer(data.expires_at);
                }).catch(err => console.warn('Session timer not available:', err));
                
                return data;
            } else {
                // Session expired, clean up
                localStorage.removeItem('trinity_private_session');
            }
        } catch (error) {
            localStorage.removeItem('trinity_private_session');
        }
    }
    return null;
}

/**
 * Get the API URL for current session (private or community)
 */
export function getSessionApiUrl() {
    const session = checkActiveSession();
    if (session && session.endpoint) {
        return session.endpoint;
    }
    return CONFIG.API_URL;
}

/**
 * Cleanup on module unload
 */
export function cleanup() {
    if (updateInterval) {
        clearInterval(updateInterval);
        updateInterval = null;
    }
    if (window.paymentPollingInterval) {
        clearInterval(window.paymentPollingInterval);
    }
}
