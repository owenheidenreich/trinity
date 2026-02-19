/**
 * Store type definitions — shape of the Zustand state.
 */
import type { ChatMessage, UserMemory, ChatListItem } from '../types';

/** Full store state shape */
export interface StoreState {
  // ===== Chat State =====
  chatStarted: boolean;
  chatHistory: ChatMessage[];
  currentChatId: string | null;
  currentUserId: string | null;
  allChats: ChatListItem[];

  // ===== Authentication State =====
  isAuthenticated: boolean;
  principal: string | null;
  username: string | null;
  authenticatedSince: number | null;

  // ===== User Memory =====
  userMemory: UserMemory | null;

  // ===== Context Memory =====
  contextMemory: ChatMessage[];
  CONTEXT_WINDOW_SIZE: number;

  // ===== UI State =====
  isGenerating: boolean;
  isLoadingChat: boolean;

  // ===== Actions =====
  reset: () => void;
  generateChatId: () => string;
  getUserId: () => string | null;
  addMessage: (role: 'user' | 'assistant', content: string) => ChatMessage;
  updateContextMemory: (message: ChatMessage) => void;
  getContextForLLM: () => {
    recentMessages: ChatMessage[];
    totalConversationLength: number;
    totalTokens: number;
  };

  // ===== Setters =====
  setAuthenticated: (principal: string, authenticatedSince: number) => void;
  clearAuthentication: () => void;
  setUserMemory: (memory: UserMemory | null) => void;
  setAllChats: (chats: ChatListItem[]) => void;
  setChatHistory: (messages: ChatMessage[]) => void;
  setContextMemory: (messages: ChatMessage[]) => void;
  setGenerating: (isGenerating: boolean) => void;
  setLoadingChat: (isLoadingChat: boolean) => void;
  setCurrentChatId: (chatId: string | null) => void;
  setChatStarted: (started: boolean) => void;
  removeLastMessage: () => ChatMessage | null;
  getLastUserMessage: () => ChatMessage | null;

  // ===== Memory Actions =====
  updateMemoryFact: (factId: number, updates: { text?: string; category?: string; importance?: number }) => void;
  deleteMemoryFact: (factId: number) => void;
}
