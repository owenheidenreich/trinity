/**
 * Input Validation Utilities
 * Client-side validation for security and data integrity
 */

const Validation = {
    /**
     * Validate chat ID format
     * Expected: chat-{timestamp}-{random} e.g., "chat-1737817234567-ab3cd9efg"
     * @param {string} chatId - Chat ID to validate
     * @returns {boolean} Whether the chat ID is valid
     */
    isValidChatId(chatId) {
        if (!chatId || typeof chatId !== 'string') return false;
        // Allow: letters, numbers, hyphens, underscores (max 64 chars)
        return /^[a-zA-Z0-9_-]{1,64}$/.test(chatId);
    },

    /**
     * Validate principal ID format
     * Expected: ICP principal format (base32 with hyphens)
     * @param {string} principal - Principal ID to validate
     * @returns {boolean} Whether the principal is valid
     */
    isValidPrincipal(principal) {
        if (!principal || typeof principal !== 'string') return false;
        // Principal format: groups of 5 lowercase alphanumeric chars separated by hyphens
        // Example: "abc12-def34-ghi56-jkl78-mno90-pqr12-stu34-vwx56-yza"
        return /^[a-z0-9]{5}(-[a-z0-9]{5}){1,10}(-[a-z0-9]{1,5})?$/.test(principal);
    },

    /**
     * Validate CID format (IPFS content identifier)
     * @param {string} cid - Content ID to validate
     * @returns {boolean} Whether the CID is valid
     */
    isValidCid(cid) {
        if (!cid || typeof cid !== 'string') return false;
        // CIDv0: starts with Qm, 46 chars; CIDv1: starts with bafy, variable length
        return /^(Qm[a-zA-Z0-9]{44}|bafy[a-zA-Z0-9]{50,60})$/.test(cid);
    },

    /**
     * Sanitize user input text (removes control chars, limits length)
     * @param {string} text - Input text to sanitize
     * @param {number} maxLength - Maximum allowed length (default 50000)
     * @returns {string} Sanitized text
     */
    sanitizeText(text, maxLength = 50000) {
        if (!text || typeof text !== 'string') return '';
        // Remove control characters except newlines and tabs
        let sanitized = text.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '');
        // Limit length
        if (sanitized.length > maxLength) {
            sanitized = sanitized.substring(0, maxLength);
        }
        return sanitized;
    },

    /**
     * Validate message structure
     * @param {Object} message - Message object to validate
     * @returns {boolean} Whether the message is valid
     */
    isValidMessage(message) {
        if (!message || typeof message !== 'object') return false;
        if (!['user', 'assistant', 'system'].includes(message.role)) return false;
        if (!message.content || typeof message.content !== 'string') return false;
        if (message.content.length > 100000) return false; // 100KB limit per message
        return true;
    },

    /**
     * Validate chat data structure before saving
     * @param {Object} chatData - Chat data to validate
     * @returns {{valid: boolean, error?: string}} Validation result
     */
    validateChatData(chatData) {
        if (!chatData || typeof chatData !== 'object') {
            return { valid: false, error: 'Chat data must be an object' };
        }

        if (chatData.chatId && !this.isValidChatId(chatData.chatId)) {
            return { valid: false, error: 'Invalid chat ID format' };
        }

        if (chatData.messages) {
            if (!Array.isArray(chatData.messages)) {
                return { valid: false, error: 'Messages must be an array' };
            }
            if (chatData.messages.length > 1000) {
                return { valid: false, error: 'Too many messages (max 1000)' };
            }
            for (let i = 0; i < chatData.messages.length; i++) {
                if (!this.isValidMessage(chatData.messages[i])) {
                    return { valid: false, error: `Invalid message at index ${i}` };
                }
            }
        }

        return { valid: true };
    }
};

export default Validation;
