/**
 * math.js - KaTeX Math Rendering Utility
 * 
 * Renders LaTeX math expressions in message content.
 * Supports:
 * - Inline math: $expression$ or \(expression\)
 * - Block math: $$expression$$ or \[expression\]
 */

/**
 * Render math expressions in an HTML element
 * Uses KaTeX's auto-render extension
 * 
 * @param {HTMLElement} element - The DOM element to process
 */
export function renderMath(element) {
    if (!window.renderMathInElement) {
        console.warn('⚠️ KaTeX auto-render not loaded yet');
        return;
    }

    try {
        // Debug: Check for math content before rendering
        const textContent = element.textContent || '';
        const hasDollarSign = textContent.includes('$');
        const hasBackslash = textContent.includes('\\');
        
        if (hasDollarSign || hasBackslash) {
            console.log('📐 renderMath called - found potential math:', 
                hasDollarSign ? '$ found' : '',
                hasBackslash ? '\\ found' : '',
                'First 100 chars:', textContent.substring(0, 100)
            );
        }
        
        window.renderMathInElement(element, {
            // Delimiters for math expressions
            delimiters: [
                { left: '$$', right: '$$', display: true },   // Block math
                { left: '$', right: '$', display: false },     // Inline math
                { left: '\\[', right: '\\]', display: true },  // Block math (LaTeX style)
                { left: '\\(', right: '\\)', display: false }, // Inline math (LaTeX style)
            ],
            // Don't throw on errors, show error message instead
            throwOnError: false,
            // Trust HTML (we sanitize with DOMPurify first)
            trust: true,
            // Strict mode off for better compatibility
            strict: false,
            // Output format
            output: 'html',
            // Enable certain macros
            macros: {
                '\\R': '\\mathbb{R}',
                '\\N': '\\mathbb{N}',
                '\\Z': '\\mathbb{Z}',
                '\\Q': '\\mathbb{Q}',
                '\\C': '\\mathbb{C}',
            }
        });
        
        // Check if any KaTeX spans were created
        const katexElements = element.querySelectorAll('.katex');
        if (katexElements.length > 0) {
            console.log('✅ KaTeX rendered', katexElements.length, 'math expressions');
        } else if (hasDollarSign) {
            console.log('⚠️ $ found but no KaTeX elements created - raw text:', textContent.substring(0, 200));
        }
    } catch (error) {
        console.warn('Math rendering error:', error);
    }
}

/**
 * Check if content contains math expressions
 * 
 * @param {string} content - The text content to check
 * @returns {boolean} - True if math expressions are detected
 */
export function containsMath(content) {
    if (!content) return false;
    
    // Check for common math delimiters
    const mathPatterns = [
        /\$\$.+?\$\$/s,           // Block math $$...$$
        /\$[^$\n]+?\$/,           // Inline math $...$
        /\\\[.+?\\\]/s,           // Block math \[...\]
        /\\\(.+?\\\)/s,           // Inline math \(...\)
    ];
    
    return mathPatterns.some(pattern => pattern.test(content));
}

/**
 * Pre-process content to protect math from markdown parsing
 * This prevents marked from mangling math expressions
 * 
 * @param {string} content - The raw content
 * @returns {object} - { processed: string, mathBlocks: Map }
 */
export function protectMath(content) {
    const mathBlocks = new Map();
    let counter = 0;
    
    // First, convert \( \) and \[ \] to $ notation for consistent handling
    // This handles the escaped parenthesis LaTeX notation
    let processed = content;
    
    // Convert \[...\] to $$...$$ (block math)
    processed = processed.replace(/\\\[([\s\S]+?)\\\]/g, (match, inner) => {
        return `$$${inner}$$`;
    });
    
    // Convert \(...\) to $...$ (inline math)
    processed = processed.replace(/\\\(([\s\S]+?)\\\)/g, (match, inner) => {
        return `$${inner}$`;
    });
    
    // Protect block math first ($$...$$)
    processed = processed.replace(/\$\$([\s\S]+?)\$\$/g, (match) => {
        const placeholder = `%%MATH_BLOCK_${counter}%%`;
        mathBlocks.set(placeholder, match);
        counter++;
        return placeholder;
    });
    
    // Protect inline math ($...$) - be careful not to match currency
    processed = processed.replace(/\$([^$\n]+?)\$/g, (match, inner) => {
        // Skip if it looks like currency (e.g., $100, $50.00)
        if (/^\d+(\.\d{2})?$/.test(inner.trim())) {
            return match;
        }
        const placeholder = `%%MATH_INLINE_${counter}%%`;
        mathBlocks.set(placeholder, match);
        counter++;
        return placeholder;
    });
    
    return { processed, mathBlocks };
}

/**
 * Restore protected math blocks after markdown parsing
 * 
 * @param {string} html - The HTML after markdown parsing
 * @param {Map} mathBlocks - The protected math blocks
 * @returns {string} - HTML with math restored
 */
export function restoreMath(html, mathBlocks) {
    let result = html;
    for (const [placeholder, math] of mathBlocks) {
        result = result.replace(placeholder, math);
    }
    return result;
}

export default {
    renderMath,
    containsMath,
    protectMath,
    restoreMath
};
