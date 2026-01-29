/**
 * Trinity Private Session Timer
 * 
 * Manages countdown timer for private LLM sessions with:
 * - Real-time countdown display
 * - 5-minute warning with option to add time
 * - Automatic session termination
 * 
 * @module modules/sessionTimer
 */

// Session state
let sessionData = null;
let timerInterval = null;
let warningShown = false;

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
        startTime: Date.now()
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
 * Show 5-minute warning modal
 */
function showTimeWarning() {
    const modal = document.createElement('div');
    modal.id = 'timeWarningModal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal warning-modal">
            <h3 style="color: #f59e0b; margin-bottom: 12px;">⚠️ 5 Minutes Remaining</h3>
            <p style="font-size: 12px; color: #888; margin-bottom: 20px;">
                Your private session will end soon. Would you like to add more time?
            </p>
            
            <div class="warning-actions">
                <button class="btn-add-time" onclick="window.showAddTimeModal()">
                    Add More Time
                </button>
                <button class="btn-dismiss" onclick="document.getElementById('timeWarningModal').remove()">
                    Let it End
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
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
    
    // Show session ended notification
    showSessionEndedModal();
    
    // Clear session data
    sessionData = null;
    warningShown = false;
    
    console.log('🔓 Private session ended');
}

/**
 * Show session ended modal
 */
function showSessionEndedModal() {
    const modal = document.createElement('div');
    modal.id = 'sessionEndedModal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal">
            <h3 style="margin-bottom: 12px;">Session Ended</h3>
            <p style="font-size: 12px; color: #888; margin-bottom: 20px;">
                Your private session has ended. You're now using the community LLM.
            </p>
            
            <button class="btn-primary" onclick="document.getElementById('sessionEndedModal').remove()">
                Continue with Community LLM
            </button>
            
            <button class="btn-secondary" onclick="window.location.reload()">
                Start New Private Session
            </button>
        </div>
    `;
    
    document.body.appendChild(modal);
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
