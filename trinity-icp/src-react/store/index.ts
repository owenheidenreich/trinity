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
  CONTEXT_WINDOW_SIZE: 50,

  // ===== UI State =====
  isGenerating: false,
  isLoadingChat: false,

  // ===== Pagination =====
  hasMoreMessages: false,
  oldestMessageId: null as number | null,

  // ===== Actions =====

  reset: () =>
    set(() => ({
      chatStarted: false,
      chatHistory: [],
      contextMemory: [],
      currentChatId: null,
      hasMoreMessages: false,
      oldestMessageId: null,
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
    const state = get();
    const chatId = state.currentChatId ?? state.generateChatId();
    const message: ChatMessage = {
      id: -(Date.now() + Math.floor(Math.random() * 1000)),
      chatId,
      role,
      content,
      createdAt: Date.now(),
      status: 'pending',
      timestamp: Date.now(),
    };

    const newChatHistory = [...state.chatHistory, message];
    const newContextMemory = [...state.contextMemory, message];

    // Maintain context window size
    while (newContextMemory.length > state.CONTEXT_WINDOW_SIZE) {
      newContextMemory.shift();
    }

    set({
      chatHistory: newChatHistory,
      contextMemory: newContextMemory,
      chatStarted: true,
      currentChatId: chatId,
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
      hasMoreMessages: false,
      oldestMessageId: null,
    }),

  setUserMemory: (memory) => set({ userMemory: memory }),
  setAllChats: (chats) => set({ allChats: chats }),
  setChatHistory: (messages) => set({ chatHistory: messages }),
  setContextMemory: (messages) => set({ contextMemory: messages }),
  setGenerating: (isGenerating) => set({ isGenerating }),
  setLoadingChat: (isLoadingChat) => set({ isLoadingChat }),
  setCurrentChatId: (chatId) => set({ currentChatId: chatId }),
  setChatStarted: (started) => set({ chatStarted: started }),

  setHasMoreMessages: (has) => set({ hasMoreMessages: has }),
  setOldestMessageId: (id) => set({ oldestMessageId: id }),
  prependMessages: (messages) => {
    const state = get();
    const merged = [...messages, ...state.chatHistory];
    set({
      chatHistory: merged,
      contextMemory: merged.slice(-state.CONTEXT_WINDOW_SIZE),
    });
  },

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

  // ===== Memory Actions =====

  updateMemoryFact: (factId, updates) => {
    const state = get();
    if (!state.userMemory) return;
    const facts = [...state.userMemory.facts];
    const idx = facts.findIndex((f) => Number(f.fact_id) === Number(factId));
    if (idx < 0) return;
    const existing = facts[idx];
    if (!existing) return;
    facts[idx] = { ...existing, ...updates };
    set({ userMemory: { ...state.userMemory, facts } });
  },

  deleteMemoryFact: (factId) => {
    const state = get();
    if (!state.userMemory) return;
    const facts = [...state.userMemory.facts];
    const idx = facts.findIndex((f) => Number(f.fact_id) === Number(factId));
    if (idx < 0) return;
    const existing = facts[idx];
    if (!existing) return;
    facts[idx] = { ...existing, deleted: true, deleted_at: Date.now() };
    set({ userMemory: { ...state.userMemory, facts } });
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
