/**
 * Whimsical Loading Messages
 * 
 * Generates fun "verb+ing the noun..." style messages
 * to keep users entertained during AI thinking phases.
 */

// Loading phrases by phase: [verb, noun]
const LOADING_PHRASES = {
    classifying: [
        ['Examining', 'question'],
        ['Pondering', 'complexity'],
        ['Measuring', 'depths'],
        ['Sensing', 'nuances'],
        ['Calibrating', 'response'],
    ],
    searching: [
        ['Scouring', 'web'],
        ['Exploring', 'internet'],
        ['Hunting', 'sources'],
        ['Mining', 'data'],
        ['Consulting', 'oracles'],
        ['Diving into', 'archives'],
        ['Querying', 'databases'],
        ['Surfing', 'information waves'],
    ],
    understanding: [
        ['Pondering', 'question'],
        ['Untangling', 'meaning'],
        ['Deciphering', 'intent'],
        ['Absorbing', 'context'],
        ['Contemplating', 'puzzle'],
        ['Grasping', 'essence'],
        ['Meditating on', 'problem'],
        ['Processing', 'inquiry'],
    ],
    planning: [
        ['Drafting', 'blueprint'],
        ['Mapping', 'approach'],
        ['Charting', 'course'],
        ['Sketching', 'strategy'],
        ['Weaving', 'plan'],
        ['Plotting', 'solution'],
        ['Architecting', 'response'],
        ['Orchestrating', 'thoughts'],
    ],
    executing: [
        ['Brewing', 'answer'],
        ['Crafting', 'response'],
        ['Forging', 'solution'],
        ['Weaving', 'words'],
        ['Painting', 'picture'],
        ['Composing', 'symphony'],
        ['Building', 'masterpiece'],
        ['Assembling', 'thoughts'],
        ['Writing', 'story'],
        ['Creating', 'magic'],
    ],
    critiquing: [
        ['Polishing', 'prose'],
        ['Inspecting', 'work'],
        ['Reviewing', 'craftsmanship'],
        ['Examining', 'details'],
        ['Questioning', 'assumptions'],
        ['Testing', 'logic'],
        ['Scrutinizing', 'reasoning'],
        ['Evaluating', 'quality'],
    ],
    refining: [
        ['Perfecting', 'response'],
        ['Enhancing', 'answer'],
        ['Elevating', 'prose'],
        ['Sharpening', 'edge'],
        ['Polishing', 'gem'],
        ['Refining', 'gold'],
        ['Buffing', 'brilliance'],
        ['Distilling', 'essence'],
    ],
};

const DEFAULT_PHRASES = [
    ['Processing', 'request'],
    ['Working on', 'task'],
    ['Thinking about', 'problem'],
    ['Considering', 'options'],
];

// Track which messages we've used to avoid immediate repeats
let usedIndices = {};

/**
 * Get a random loading message for a phase
 * @param {string} phase - The current phase (understanding, executing, etc.)
 * @returns {string} A message like "Pondering the question..."
 */
export function getLoadingMessage(phase) {
    const phrases = LOADING_PHRASES[phase] || DEFAULT_PHRASES;
    
    // Get a random index, avoiding the last used one for this phase
    let index;
    do {
        index = Math.floor(Math.random() * phrases.length);
    } while (index === usedIndices[phase] && phrases.length > 1);
    
    usedIndices[phase] = index;
    
    const [verb, noun] = phrases[index];
    return `${verb} the ${noun}`;
}

/**
 * Create the thinking indicator HTML
 * @param {string} message - The loading message
 * @param {string} phase - The current phase
 * @returns {string} HTML string
 */
export function createThinkingIndicator(message, phase) {
    const phaseName = phase ? phase.charAt(0).toUpperCase() + phase.slice(1) : '';
    
    return `
        <div class="thinking-indicator">
            ${phase ? `<span class="phase-badge">${phaseName}</span>` : ''}
            <div class="thinking-message active">
                ${message}<span class="thinking-dots"><span></span><span></span><span></span></span>
            </div>
        </div>
    `;
}

/**
 * Update thinking message with fade animation
 * @param {HTMLElement} container - The container element
 * @param {string} newMessage - New message to display
 * @param {string} phase - Current phase
 */
export function updateThinkingMessage(container, newMessage, phase) {
    const messageEl = container.querySelector('.thinking-message');
    const badgeEl = container.querySelector('.phase-badge');
    
    if (messageEl) {
        // Fade out
        messageEl.classList.remove('active');
        
        setTimeout(() => {
            // Update content
            messageEl.innerHTML = `${newMessage}<span class="thinking-dots"><span></span><span></span><span></span></span>`;
            
            // Update phase badge
            if (badgeEl && phase) {
                badgeEl.textContent = phase.charAt(0).toUpperCase() + phase.slice(1);
            }
            
            // Fade in
            messageEl.classList.add('active');
        }, 300);
    }
}

/**
 * Message rotator for long operations
 */
export class MessageRotator {
    constructor(container, phase, intervalMs = 4000) {
        this.container = container;
        this.phase = phase;
        this.intervalMs = intervalMs;
        this.intervalId = null;
    }
    
    start() {
        this.rotate(); // Initial message
        this.intervalId = setInterval(() => this.rotate(), this.intervalMs);
    }
    
    rotate() {
        const message = getLoadingMessage(this.phase);
        updateThinkingMessage(this.container, message, this.phase);
    }
    
    setPhase(newPhase) {
        this.phase = newPhase;
        this.rotate(); // Immediately show new phase message
    }
    
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }
}

export default {
    getLoadingMessage,
    createThinkingIndicator,
    updateThinkingMessage,
    MessageRotator
};
