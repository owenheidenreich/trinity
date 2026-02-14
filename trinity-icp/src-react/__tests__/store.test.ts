/**
 * Tests for Zustand store — state management, actions, context memory.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { useStore } from '../store';

describe('Trinity Store', () => {
  beforeEach(() => {
    // Reset to initial state before each test
    useStore.setState({
      chatStarted: false,
      chatHistory: [],
      currentChatId: null,
      currentUserId: null,
      allChats: [],
      isAuthenticated: false,
      principal: null,
      authenticatedSince: null,
      userMemory: null,
      contextMemory: [],
      autosaveStatus: 'idle',
      unsavedChanges: false,
      lastActivityTime: null,
      isGenerating: false,
      isLoadingChat: false,
    });
  });

  describe('addMessage', () => {
    it('adds a message to chatHistory', () => {
      const state = useStore.getState();
      const msg = state.addMessage('user', 'Hello');
      expect(msg.role).toBe('user');
      expect(msg.content).toBe('Hello');
      expect(msg.id).toMatch(/^msg-/);
      expect(msg.timestamp).toBeGreaterThan(0);

      const updated = useStore.getState();
      expect(updated.chatHistory).toHaveLength(1);
      expect(updated.chatHistory[0]).toEqual(msg);
    });

    it('sets chatStarted to true', () => {
      const state = useStore.getState();
      state.addMessage('user', 'First message');
      expect(useStore.getState().chatStarted).toBe(true);
    });

    it('marks unsavedChanges', () => {
      const state = useStore.getState();
      state.addMessage('user', 'content');
      expect(useStore.getState().unsavedChanges).toBe(true);
    });

    it('maintains context window size', () => {
      const state = useStore.getState();
      // Add more messages than CONTEXT_WINDOW_SIZE (20) to test truncation
      for (let i = 0; i < 25; i++) {
        state.addMessage('user', `message ${i}`);
      }
      const updated = useStore.getState();
      expect(updated.chatHistory).toHaveLength(25);
      expect(updated.contextMemory).toHaveLength(updated.CONTEXT_WINDOW_SIZE);
    });
  });

  describe('reset', () => {
    it('clears chat state', () => {
      const state = useStore.getState();
      state.addMessage('user', 'test');
      state.reset();

      const updated = useStore.getState();
      expect(updated.chatStarted).toBe(false);
      expect(updated.chatHistory).toHaveLength(0);
      expect(updated.contextMemory).toHaveLength(0);
      expect(updated.unsavedChanges).toBe(false);
    });

    it('generates a new chat id', () => {
      const state = useStore.getState();
      state.setCurrentChatId('old-id');
      state.reset();
      const updated = useStore.getState();
      expect(updated.currentChatId).not.toBe('old-id');
      expect(updated.currentChatId).toMatch(/^chat-/);
    });
  });

  describe('authentication', () => {
    it('sets authenticated state', () => {
      const state = useStore.getState();
      const now = Date.now();
      state.setAuthenticated('test-principal', now);

      const updated = useStore.getState();
      expect(updated.isAuthenticated).toBe(true);
      expect(updated.principal).toBe('test-principal');
      expect(updated.authenticatedSince).toBe(now);
    });

    it('clears authentication', () => {
      const state = useStore.getState();
      state.setAuthenticated('principal', Date.now());
      state.clearAuthentication();

      const updated = useStore.getState();
      expect(updated.isAuthenticated).toBe(false);
      expect(updated.principal).toBeNull();
      expect(updated.authenticatedSince).toBeNull();
    });
  });

  describe('removeLastMessage', () => {
    it('removes the last message', () => {
      const state = useStore.getState();
      state.addMessage('user', 'first');
      state.addMessage('assistant', 'second');

      const removed = useStore.getState().removeLastMessage();
      expect(removed?.content).toBe('second');
      expect(useStore.getState().chatHistory).toHaveLength(1);
    });

    it('returns null when no messages', () => {
      const result = useStore.getState().removeLastMessage();
      expect(result).toBeNull();
    });
  });

  describe('getLastUserMessage', () => {
    it('finds the last user message', () => {
      const state = useStore.getState();
      state.addMessage('user', 'Hello');
      state.addMessage('assistant', 'Hi');
      state.addMessage('user', 'What is 2+2?');

      const last = useStore.getState().getLastUserMessage();
      expect(last?.content).toBe('What is 2+2?');
    });

    it('returns null when no user messages', () => {
      const state = useStore.getState();
      state.addMessage('assistant', 'Hello');
      expect(useStore.getState().getLastUserMessage()).toBeNull();
    });
  });

  describe('getContextForLLM', () => {
    it('returns context info', () => {
      const state = useStore.getState();
      state.addMessage('user', 'Hello world');
      state.addMessage('assistant', 'Hi there');

      const context = useStore.getState().getContextForLLM();
      expect(context.recentMessages).toHaveLength(2);
      expect(context.totalConversationLength).toBe(2);
      expect(context.totalTokens).toBeGreaterThan(0);
    });
  });

  describe('setters', () => {
    it('setGenerating', () => {
      useStore.getState().setGenerating(true);
      expect(useStore.getState().isGenerating).toBe(true);
    });

    it('setLoadingChat', () => {
      useStore.getState().setLoadingChat(true);
      expect(useStore.getState().isLoadingChat).toBe(true);
    });

    it('setAutosaveStatus', () => {
      useStore.getState().setAutosaveStatus('saving');
      expect(useStore.getState().autosaveStatus).toBe('saving');
    });

    it('setAllChats', () => {
      const chats = [{ chatId: '1', title: 'Test', messageCount: 1, createdAt: 0, lastUpdated: 0 }];
      useStore.getState().setAllChats(chats);
      expect(useStore.getState().allChats).toEqual(chats);
    });

    it('setChatHistory', () => {
      const msgs = [{ id: '1', role: 'user' as const, content: 'test', timestamp: 0 }];
      useStore.getState().setChatHistory(msgs);
      expect(useStore.getState().chatHistory).toEqual(msgs);
    });
  });

  describe('generateChatId', () => {
    it('generates unique chat ids', () => {
      const state = useStore.getState();
      const id1 = state.generateChatId();
      const id2 = state.generateChatId();
      expect(id1).toMatch(/^chat-/);
      expect(id2).toMatch(/^chat-/);
      expect(id1).not.toBe(id2);
    });
  });
});
