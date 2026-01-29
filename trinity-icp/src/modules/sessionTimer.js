/**
 * Trinity Private Session Timer
 * 
 * Manages countdown timer for private LLM sessions with:
 * - Real-time countdown display
 * - 5-minute warning with archive reminder (user-responsible archiving)
 * - Automatic session termination
 * 
 * @module modules/sessionTimer
 */

// Session state
let sessionData = null;
let timerInterval = null;
let warningShown = false;

/**
 * Start a private session timer from ISO expiry string
 * Called from funding.js when session becomes active
 * @param {string} expiresAt - ISO timestamp when session ends
 */
export function startSessionTimer(expiresAt) {
    const endTime = new Date(expiresAt).getTime();
    const session = localStorage.getItem('trinity_private_session');
    let tierName = 'Private';
    
    if (session) {
        try {
            const data = JSON.parse(session);
            tierName = data.tier_name || 'Private';
        } catch (e) {}
    }
    
    startSession({
        endTime: endTime,
        tier: tierName,
        startTime: Date.now()
    });
}

/**
 * Start a private session timer
 * @param {Object} session - Session details
 * @param {number} session.endTime - Unix timestamp when session ends
 * @param {string} session.tier - Tier name (Starter, Standard, Professional)
 * @param {string} session.deploymentUri - Akash deployment URI
 */
export function startSession(session) {
    sessionData = {
        ...session,
        startTime: session.startTime || Date.now()
    };
    warningShown = false;
    
    // Show session UI
    showSessionUI();
    
    // Start timer
    timerInterval = setInterval(tick, 1000);
    tick(); // Initial update
    
    console.log('🔒 Private session started:', session);
}

/**
 * Timer tick - called every second
 */
function tick() {
    if (!sessionData) return;
    
    const remaining = sessionData.endTime - Date.now();
    const minutes = Math.floor(remaining / 60000);
    
    // 5-minute warning
    if (minutes <= 5 && minutes > 0 && !warningShown) {
        showTimeWarning();
        warningShown = true;
    }
    
    // Session ended
    if (remaining <= 0) {
        endSession();
        return;
    }
    
    updateTimerUI(remaining);
}

/**
 * Update the timer display
 */
function updateTimerUI(remainingMs) {
    const hours = Math.floor(remainingMs / 3600000);
    const minutes = Math.floor((remainingMs % 3600000) / 60000);
    const seconds = Math.floor((remainingMs % 60000) / 1000);
    
    const timeStr = hours > 0 
        ? `${hours}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`
        : `${minutes}:${seconds.toString().padStart(2, '0')}`;
    
    // Update session bar
    const timerEl = document.getElementById('sessionTimer');
    if (timerEl) {
        timerEl.textContent = timeStr;
    }
    
    // Update progress bar
    const progressEl = document.getElementById('sessionProgress');
    if (progressEl && sessionData.startTime) {
        const totalDuration = sessionData.endTime - sessionData.startTime;
        const elapsed = Date.now() - sessionData.startTime;
        const percentage = Math.min(100, (elapsed / totalDuration) * 100);
        progressEl.style.width = `${percentage}%`;
    }
    
    // Color coding for urgency
    if (remainingMs < 5 * 60000) { // Less than 5 minutes
        const barEl = document.getElementById('sessionBar');
        if (barEl) barEl.classList.add('critical');
    }
}

/**
 * Show the session UI bar
 */
function showSessionUI() {
    // Check if session bar already exists
    let sessionBar = document.getElementById('sessionBar');
    
    if (!sessionBar) {
        sessionBar = document.createElement('div');
        sessionBar.id = 'sessionBar';
        sessionBar.className = 'session-bar';
        sessionBar.innerHTML = `
            <div class="session-info">
                <span class="session-lock">🔒</span>
                <span class="session-tier" id="sessionTier">${sessionData?.tier || 'Private'} Session</span>
            </div>
            <div class="session-timer-wrapper">
                <span class="session-timer" id="sessionTimer">--:--:--</span>
                <span class="session-label">remaining</span>
            </div>
            <div class="session-progress-bar">
                <div class="session-progress" id="sessionProgress" style="width: 0%"></div>
            </div>
            <button class="session-add-time" id="addTimeBtn">+ Add Time</button>
        `;
        
        // Insert at top of main content
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.insertBefore(sessionBar, mainContent.firstChild);
        }
        
        // Wire up add time button
        document.getElementById('addTimeBtn')?.addEventListener('click', showAddTimeModal);
    }
    
    sessionBar.style.display = 'flex';
}

/**
 * Show 5-minute warning modal with archive reminder
 * User is responsible for archiving before session ends
 */
function showTimeWarning() {
    const modal = document.createElement('div');
    modal.id = 'timeWarningModal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal warning-modal">
            <h3 style="color: #f59e0b; margin-bottom: 12px;">5 Minutes Remaining</h3>
            
            <div style="background: #2d2d2d; border: 1px solid #fbbf24; border-radius: 6px; padding: 12px; margin-bottom: 16px;">
                <p style="font-size: 12px; color: #fbbf24; margin-bottom: 8px;">
                    Archive your chats now!
                </p>
                <p style="font-size: 11px; color: #888;">
                    Your private session is ending soon. Click the archive button in the sidebar to save your chats to Filecoin before the session expires.
                </p>
            </div>
            
            <p style="font-size: 11px; color: #888; margin-bottom: 16px;">
                After the session ends, you will return to the free community LLM.
            </p>
            
            <div class="warning-actions">
                <button class="btn-dismiss" onclick="document.getElementById('timeWarningModal').remove()" style="background: #3d3d3d; color: #fff; border: none; padding: 10px 24px; border-radius: 6px; cursor: pointer;">
                    Got it
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
    
    // Auto-dismiss after 30 seconds
    setTimeout(() => {
        modal.remove();
    }, 30000);
}

/**
 * Show add time modal
 */
window.showAddTimeModal = function() {
    // Remove warning modal if exists
    document.getElementById('timeWarningModal')?.remove();
    
    const modal = document.createElement('div');
    modal.id = 'addTimeModal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal">
            <button class="modal-close" onclick="document.getElementById('addTimeModal').remove()">×</button>
            <h3 style="margin-bottom: 16px;">Add Session Time</h3>
            
            <div class="add-time-options">
                <button class="time-option" data-hours="1">
                    <span class="time-duration">+1 Hour</span>
                    <span class="time-cost">~0.4 AKT</span>
                </button>
                <button class="time-option" data-hours="2">
                    <span class="time-duration">+2 Hours</span>
                    <span class="time-cost">~0.8 AKT</span>
                </button>
                <button class="time-option" data-hours="4">
                    <span class="time-duration">+4 Hours</span>
                    <span class="time-cost">~1.6 AKT</span>
                </button>
            </div>
            
            <p style="font-size: 10px; color: #666; margin-top: 16px; text-align: center;">
                Send AKT to extend your session. Time is added immediately upon payment.
            </p>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Wire up time options
    modal.querySelectorAll('.time-option').forEach(btn => {
        btn.addEventListener('click', () => {
            const hours = parseInt(btn.dataset.hours);
            requestAddTime(hours);
            modal.remove();
        });
    });
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
};

/**
 * Request additional time (triggers payment flow)
 */
function requestAddTime(hours) {
    // TODO: Implement payment flow for adding time
    // 1. Calculate cost based on current tier
    // 2. Show payment address/QR
    // 3. Monitor for payment
    // 4. Extend session.endTime upon confirmation
    
    console.log(`Requesting ${hours} additional hours`);
    alert(`Adding ${hours} hour(s) - payment integration coming soon!`);
}

/**
 * End the session
 */
function endSession() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
    
    // Hide session bar
    const sessionBar = document.getElementById('sessionBar');
    if (sessionBar) {
        sessionBar.classList.add('ending');
        setTimeout(() => sessionBar.remove(), 500);
    }
    
    // Clear local storage
    localStorage.removeItem('trinity_private_session');
    
    // Show session ended notification
    showSessionEndedModal();
    
    // Clear session data
    sessionData = null;
    warningShown = false;
    
    console.log('🔓 Private session ended');
}

/**
 * Show session ended modal with archive reminder
 */
function showSessionEndedModal() {
    const modal = document.createElement('div');
    modal.id = 'sessionEndedModal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal">
            <h3 style="margin-bottom: 12px;">Session Ended</h3>
            <p style="font-size: 12px; color: #888; margin-bottom: 16px;">
                Your private session has ended. You're now using the community LLM.
            </p>
            
            <div style="background: #2d2d2d; border-radius: 6px; padding: 12px; margin-bottom: 16px;">
                <p style="font-size: 11px; color: #888;">
                    If you didn't archive your chats, they may still be accessible in the sidebar. Use the archive button to save them permanently.
                </p>
            </div>
            
            <button class="btn-primary" onclick="document.getElementById('sessionEndedModal').remove()" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #fff; border: none; padding: 12px 24px; border-radius: 6px; cursor: pointer; width: 100%;">
                Continue with Community LLM
            </button>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
}

/**
 * Get current session data
 */
export function getSessionData() {
    return sessionData;
}

/**
 * Check if a private session is active
 */
export function isSessionActive() {
    return sessionData !== null && sessionData.endTime > Date.now();
}

/**
 * Cleanup
 */
export function cleanup() {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
    sessionData = null;
}
