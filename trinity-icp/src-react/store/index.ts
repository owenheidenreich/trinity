/**
 * Trinity State Store (Zustand + TypeScript)
 * Migrated from state/store.js — same shape, fully typed.
 */
import { create } from 'zustand';
import type { StoreState } from './types';
import type { ChatMessage } from '../types';

const generateId = (prefix: string): string =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;

export const useStore = create<StoreState>((set, get) => ({
  // ===== Chat State =====
  chatStarted: false,
  chatHistory: [],
  currentChatId: null,
  currentUserId: null,
  allChats: [],

  // ===== Authentication State =====
  isAuthenticated: false,
  principal: null,
  username: null,
  authenticatedSince: null,

  // ===== User Memory =====
  userMemory: null,

  // ===== Context Memory =====
  contextMemory: [],
  CONTEXT_WINDOW_SIZE: 20,

  // ===== Autosave Tracking =====
  autosaveStatus: 'idle',
  unsavedChanges: false,
  lastActivityTime: null,

  // ===== UI State =====
  isGenerating: false,
  isLoadingChat: false,

  // ===== Actions =====

  reset: () =>
    set(() => ({
      chatStarted: false,
      chatHistory: [],
      contextMemory: [],
      currentChatId: get().generateChatId(),
      unsavedChanges: false,
    })),

  generateChatId: () => generateId('chat'),

  getUserId: () => {
    const state = get();
    if (state.currentUserId) return state.currentUserId;

    if (typeof localStorage === 'undefined') return null;

    let userId = localStorage.getItem('trinity_user_id');
    if (!userId) {
      userId = generateId('user');
      localStorage.setItem('trinity_user_id', userId);
    }
    set({ currentUserId: userId });
    return userId;
  },

  addMessage: (role, content) => {
    const message: ChatMessage = {
      id: generateId('msg'),
      role,
      content,
      timestamp: Date.now(),
    };

    const state = get();
    const newChatHistory = [...state.chatHistory, message];
    const newContextMemory = [...state.contextMemory, message];

    // Maintain context window size
    while (newContextMemory.length > state.CONTEXT_WINDOW_SIZE) {
      newContextMemory.shift();
    }

    set({
      chatHistory: newChatHistory,
      contextMemory: newContextMemory,
      unsavedChanges: true,
      lastActivityTime: Date.now(),
      chatStarted: true,
    });

    return message;
  },

  updateContextMemory: (message) => {
    const state = get();
    const newContextMemory = [...state.contextMemory, message];

    while (newContextMemory.length > state.CONTEXT_WINDOW_SIZE) {
      newContextMemory.shift();
    }

    set({ contextMemory: newContextMemory });
  },

  getContextForLLM: () => {
    const state = get();
    return {
      recentMessages: [...state.contextMemory],
      totalConversationLength: state.chatHistory.length,
      totalTokens: state.chatHistory.reduce(
        (sum, msg) => sum + msg.content.split(/\s+/).length,
        0
      ),
    };
  },

  // ===== Setters =====

  setAuthenticated: (principal, authenticatedSince) =>
    set({ isAuthenticated: true, principal, authenticatedSince }),

  clearAuthentication: () =>
    set({
      isAuthenticated: false,
      principal: null,
      username: null,
      authenticatedSince: null,
      // Wipe all user data to prevent cross-account leaks
      allChats: [],
      chatHistory: [],
      contextMemory: [],
      currentChatId: null,
      chatStarted: false,
      userMemory: null,
      autosaveStatus: 'idle' as const,
      unsavedChanges: false,
    }),

  setUserMemory: (memory) => set({ userMemory: memory }),
  setAllChats: (chats) => set({ allChats: chats }),
  setChatHistory: (messages) => set({ chatHistory: messages }),
  setContextMemory: (messages) => set({ contextMemory: messages }),
  setGenerating: (isGenerating) => set({ isGenerating }),
  setLoadingChat: (isLoadingChat) => set({ isLoadingChat }),
  setAutosaveStatus: (status) => set({ autosaveStatus: status }),
  setUnsavedChanges: (unsaved) => set({ unsavedChanges: unsaved }),
  setCurrentChatId: (chatId) => set({ currentChatId: chatId }),
  setChatStarted: (started) => set({ chatStarted: started }),

  removeLastMessage: () => {
    const state = get();
    if (state.chatHistory.length === 0) return null;

    const removedMessage = state.chatHistory[state.chatHistory.length - 1]!;
    const newChatHistory = state.chatHistory.slice(0, -1);
    const newContextMemory = state.contextMemory.filter(
      (m) => m.id !== removedMessage.id
    );

    set({
      chatHistory: newChatHistory,
      contextMemory: newContextMemory,
      unsavedChanges: true,
    });

    return removedMessage;
  },

  getLastUserMessage: () => {
    const state = get();
    for (let i = state.chatHistory.length - 1; i >= 0; i--) {
      const msg = state.chatHistory[i];
      if (msg?.role === 'user') return msg;
    }
    return null;
  },
}));

/**
 * Non-hook API for use outside React components.
 * Matches the original State export pattern for compatibility.
 */
export const State = {
  get: () => useStore.getState(),
  subscribe: useStore.subscribe,
} as const;
