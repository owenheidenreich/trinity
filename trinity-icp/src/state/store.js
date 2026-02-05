/**
 * Trinity State Store (Zustand)
 * Centralized state management with reactive updates
 */
import { create } from 'zustand';

// Create Zustand store
const useStore = create((set, get) => ({
    // ========== Chat State ==========
    chatStarted: false,
    chatHistory: [],
    currentChatId: null,
    currentUserId: null,
    allChats: [],
    archivedChats: [],
    
    // ========== Authentication State ==========
    isAuthenticated: false,
    principal: null,
    authenticatedSince: null,
    
    // ========== User Memory ==========
    userMemory: null, // { facts: [], preferences: {} }
    
    // ========== Context Memory ==========
    contextMemory: [],
    CONTEXT_WINDOW_SIZE: 6,
    
    // ========== Conversation Summarization ==========
    conversationSummary: null,
    lastSummaryAt: 0,
    SUMMARY_INTERVAL: 15,
    
    // ========== Autosave Tracking ==========
    autosaveStatus: 'idle',
    unsavedChanges: false,
    lastActivityTime: null,
    
    // ========== UI State ==========
    isGenerating: false,
    isLoadingChat: false,
    keyboardOpen: false,
    initialViewportHeight: typeof window !== 'undefined' && window.visualViewport 
        ? window.visualViewport.height 
        : (typeof window !== 'undefined' ? window.innerHeight : 0),
    
    // ========== Interval Tracking ==========
    healthCheckIntervalId: null,
    
    // ========== Test Mode ==========
    testResponseIndex: 0,
    
    // ========== Actions ==========
    
    /**
     * Reset state for new chat
     */
    reset: () => set(state => ({
        chatStarted: false,
        chatHistory: [],
        contextMemory: [],
        currentChatId: get().generateChatId(),
        unsavedChanges: false,
        conversationSummary: null,
        lastSummaryAt: 0
    })),
    
    /**
     * Generate unique chat ID
     */
    generateChatId: () => {
        return 'chat-' + Date.now() + '-' + Math.random().toString(36).substring(2, 11);
    },
    
    /**
     * Get or create user ID
     */
    getUserId: () => {
        const state = get();
        if (state.currentUserId) return state.currentUserId;
        
        if (typeof localStorage === 'undefined') return null;
        
        let userId = localStorage.getItem('trinity_user_id');
        if (!userId) {
            userId = 'user-' + Math.random().toString(36).substring(2, 11);
            localStorage.setItem('trinity_user_id', userId);
        }
        set({ currentUserId: userId });
        return userId;
    },
    
    /**
     * Add message to chat history and context
     */
    addMessage: (role, content) => {
        const message = {
            id: 'msg-' + Date.now() + '-' + Math.random().toString(36).substring(2, 11),
            role,
            content,
            timestamp: Date.now()
        };
        
        const state = get();
        const newChatHistory = [...state.chatHistory, message];
        const newContextMemory = [...state.contextMemory, message];
        
        // Maintain context window size
        if (newContextMemory.length > state.CONTEXT_WINDOW_SIZE) {
            newContextMemory.shift();
        }
        
        set({
            chatHistory: newChatHistory,
            contextMemory: newContextMemory,
            unsavedChanges: true,
            lastActivityTime: Date.now(),
            chatStarted: true
        });
        
        return message;
    },
    
    /**
     * Update context memory with new message
     */
    updateContextMemory: (message) => {
        const state = get();
        const newContextMemory = [...state.contextMemory, message];
        
        if (newContextMemory.length > state.CONTEXT_WINDOW_SIZE) {
            newContextMemory.shift();
        }
        
        set({ contextMemory: newContextMemory });
    },
    
    /**
     * Get context for LLM
     */
    getContextForLLM: () => {
        const state = get();
        const context = [];
        
        // Include conversation summary if it exists
        if (state.conversationSummary) {
            context.push({
                role: 'system',
                content: `Earlier conversation summary:\n${state.conversationSummary}`
            });
        }
        
        // Include recent messages
        context.push(...state.contextMemory);
        
        return {
            recentMessages: context,
            totalConversationLength: state.chatHistory.length,
            totalTokens: state.chatHistory.reduce((sum, msg) => 
                sum + msg.content.split(/\s+/).length, 0
            ),
            compressionRatio: state.conversationSummary 
                ? `${state.lastSummaryAt}:1` 
                : 'none'
        };
    },
    
    // ========== Setters ==========
    
    setAuthenticated: (principal, authenticatedSince) => set({
        isAuthenticated: true,
        principal,
        authenticatedSince
    }),
    
    clearAuthentication: () => set({
        isAuthenticated: false,
        principal: null,
        authenticatedSince: null
    }),
    
    setUserMemory: (memory) => set({ userMemory: memory }),
    
    setAllChats: (chats) => set({ allChats: chats }),
    
    setArchivedChats: (chats) => set({ archivedChats: chats }),
    
    setChatHistory: (messages) => set({ chatHistory: messages }),
    
    setContextMemory: (messages) => set({ contextMemory: messages }),
    
    setGenerating: (isGenerating) => set({ isGenerating }),
    
    setLoadingChat: (isLoadingChat) => set({ isLoadingChat }),
    
    setAutosaveStatus: (status) => set({ autosaveStatus: status }),
    
    setUnsavedChanges: (unsaved) => set({ unsavedChanges: unsaved }),
    
    setConversationSummary: (summary, lastSummaryAt) => set({
        conversationSummary: summary,
        lastSummaryAt
    }),
    
    setCurrentChatId: (chatId) => set({ currentChatId: chatId }),
    
    setChatStarted: (started) => set({ chatStarted: started }),
    
    setHealthCheckInterval: (intervalId) => set({ healthCheckIntervalId: intervalId }),
    
    clearHealthCheckInterval: () => {
        const state = get();
        if (state.healthCheckIntervalId) {
            clearInterval(state.healthCheckIntervalId);
            set({ healthCheckIntervalId: null });
        }
    },
    
    incrementTestResponseIndex: () => set(state => ({ 
        testResponseIndex: state.testResponseIndex + 1 
    })),
    
    setKeyboardOpen: (isOpen) => set({ keyboardOpen: isOpen }),
    
    /**
     * Remove the last message from chat history
     */
    removeLastMessage: () => {
        const state = get();
        if (state.chatHistory.length === 0) return null;
        
        const removedMessage = state.chatHistory[state.chatHistory.length - 1];
        const newChatHistory = state.chatHistory.slice(0, -1);
        const newContextMemory = state.contextMemory.filter(m => m.id !== removedMessage.id);
        
        set({
            chatHistory: newChatHistory,
            contextMemory: newContextMemory,
            unsavedChanges: true
        });
        
        return removedMessage;
    },
    
    /**
     * Get the last user message from chat history
     */
    getLastUserMessage: () => {
        const state = get();
        for (let i = state.chatHistory.length - 1; i >= 0; i--) {
            if (state.chatHistory[i].role === 'user') {
                return state.chatHistory[i];
            }
        }
        return null;
    }
}));

// Export non-hook API for use in non-React code
export const State = {
    // Get current state snapshot
    get: () => useStore.getState(),
    
    // Subscribe to changes
    subscribe: useStore.subscribe,
    
    // Selector helper
    select: (selector) => selector(useStore.getState()),
    
    // Computed properties (proxied from store)
    get isAuthenticated() { return useStore.getState().isAuthenticated; },
    get principal() { return useStore.getState().principal; },
    get authenticatedSince() { return useStore.getState().authenticatedSince; },
    get chatHistory() { return useStore.getState().chatHistory; },
    get contextMemory() { return useStore.getState().contextMemory; },
    get currentChatId() { return useStore.getState().currentChatId; },
    get currentUserId() { return useStore.getState().currentUserId; },
    get allChats() { return useStore.getState().allChats; },
    get archivedChats() { return useStore.getState().archivedChats; },
    get userMemory() { return useStore.getState().userMemory; },
    get isGenerating() { return useStore.getState().isGenerating; },
    get isLoadingChat() { return useStore.getState().isLoadingChat; },
    get chatStarted() { return useStore.getState().chatStarted; },
    get autosaveStatus() { return useStore.getState().autosaveStatus; },
    get unsavedChanges() { return useStore.getState().unsavedChanges; },
    get lastActivityTime() { return useStore.getState().lastActivityTime; },
    get conversationSummary() { return useStore.getState().conversationSummary; },
    get lastSummaryAt() { return useStore.getState().lastSummaryAt; },
    get CONTEXT_WINDOW_SIZE() { return useStore.getState().CONTEXT_WINDOW_SIZE; },
    get SUMMARY_INTERVAL() { return useStore.getState().SUMMARY_INTERVAL; },
    get healthCheckIntervalId() { return useStore.getState().healthCheckIntervalId; },
    get keyboardOpen() { return useStore.getState().keyboardOpen; },
    get initialViewportHeight() { return useStore.getState().initialViewportHeight; },
    get testResponseIndex() { return useStore.getState().testResponseIndex; },
    
    // Action proxies
    reset() { return useStore.getState().reset(); },
    generateChatId() { return useStore.getState().generateChatId(); },
    getUserId() { return useStore.getState().getUserId(); },
    addMessage(role, content) { return useStore.getState().addMessage(role, content); },
    updateContextMemory(message) { return useStore.getState().updateContextMemory(message); },
    getContextForLLM() { return useStore.getState().getContextForLLM(); },
    setAuthenticated(principal, authenticatedSince) { 
        return useStore.getState().setAuthenticated(principal, authenticatedSince); 
    },
    clearAuthentication() { return useStore.getState().clearAuthentication(); },
    setUserMemory(memory) { return useStore.getState().setUserMemory(memory); },
    setAllChats(chats) { return useStore.getState().setAllChats(chats); },
    setArchivedChats(chats) { return useStore.getState().setArchivedChats(chats); },
    setChatHistory(messages) { return useStore.getState().setChatHistory(messages); },
    setContextMemory(messages) { return useStore.getState().setContextMemory(messages); },
    setGenerating(isGenerating) { return useStore.getState().setGenerating(isGenerating); },
    setAutosaveStatus(status) { return useStore.getState().setAutosaveStatus(status); },
    setUnsavedChanges(unsaved) { return useStore.getState().setUnsavedChanges(unsaved); },
    setConversationSummary(summary, lastSummaryAt) { 
        return useStore.getState().setConversationSummary(summary, lastSummaryAt); 
    },
    setCurrentChatId(chatId) { return useStore.getState().setCurrentChatId(chatId); },
    setChatStarted(started) { return useStore.getState().setChatStarted(started); },
    setHealthCheckInterval(intervalId) { 
        return useStore.getState().setHealthCheckInterval(intervalId); 
    },
    clearHealthCheckInterval() { return useStore.getState().clearHealthCheckInterval(); },
    incrementTestResponseIndex() { return useStore.getState().incrementTestResponseIndex(); },
    setKeyboardOpen(isOpen) { return useStore.getState().setKeyboardOpen(isOpen); },
    setLoadingChat(isLoading) { return useStore.getState().setLoadingChat(isLoading); },
    removeLastMessage() { return useStore.getState().removeLastMessage(); },
    getLastUserMessage() { return useStore.getState().getLastUserMessage(); }
};

// Export hook for React components (future use)
export { useStore };

export default State;
