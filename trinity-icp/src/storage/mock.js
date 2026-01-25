// ============================================================================
// Trinity Frontend - MockStorage Module
// ============================================================================
// Test mode storage using localStorage (simulates backend)
// ============================================================================

export const MockStorage = {
    // Store test data in localStorage (simulates backend storage)
    prefix: 'trinity_test_',
    
    saveChat(chatId, chatData) {
        const key = `${this.prefix}chat_${chatId}`;
        localStorage.setItem(key, JSON.stringify(chatData));
        console.log('💾 [TEST] Chat saved to localStorage:', chatId);
        return { success: true, chatId };
    },
    
    loadChat(chatId) {
        const key = `${this.prefix}chat_${chatId}`;
        const data = localStorage.getItem(key);
        if (data) {
            console.log('📂 [TEST] Chat loaded from localStorage:', chatId);
            return JSON.parse(data);
        }
        return null;
    },
    
    listChats() {
        const chats = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key.startsWith(`${this.prefix}chat_`)) {
                const chatId = key.replace(`${this.prefix}chat_`, '');
                const data = JSON.parse(localStorage.getItem(key));
                chats.push({
                    chatId,
                    title: data.title || 'Untitled Chat',
                    timestamp: data.timestamp || Date.now(),
                    messageCount: data.messages?.length || 0,
                    lastUpdated: data.lastUpdated || data.timestamp || Date.now(),
                    isArchived: data.isArchived || false,
                    archivedAt: data.archivedAt || null
                });
            }
        }
        console.log(`📂 [TEST] Listed ${chats.length} chats from localStorage`);
        return chats.sort((a, b) => b.timestamp - a.timestamp);
    },
    
    deleteChat(chatId) {
        const key = `${this.prefix}chat_${chatId}`;
        localStorage.removeItem(key);
        console.log('🗑️ [TEST] Chat deleted from localStorage:', chatId);
        return { success: true };
    },
    
    archiveChat(chatId) {
        // In test mode, just mark as archived in localStorage
        const key = `${this.prefix}chat_${chatId}`;
        const data = this.loadChat(chatId);
        if (data) {
            data.isArchived = true;
            data.archivedAt = Date.now();
            data.mockCID = `test-cid-${chatId}-${Date.now()}`;
            localStorage.setItem(key, JSON.stringify(data));
            console.log('📦 [TEST] Chat archived (mock CID):', data.mockCID);
            return { success: true, filepointId: data.mockCID };
        }
        return { success: false, error: 'Chat not found' };
    },
    
    clearAll() {
        const keysToRemove = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.startsWith(this.prefix)) {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach(key => localStorage.removeItem(key));
        console.log(`🗑️ [TEST] Cleared ${keysToRemove.length} test items`);
    }
};

export default MockStorage;
