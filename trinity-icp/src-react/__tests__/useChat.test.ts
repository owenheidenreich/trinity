/**
 * useChat hook tests.
 * Tests the SSE streaming flow, abort, error handling, and continuation.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useChat } from '../hooks/useChat';

// ── Mocks ──────────────────────────────────────────────────────────────────

const mockSetGenerating = vi.fn();

// Mock zustand store
const mockState: Record<string, unknown> = {
  principal: 'test-principal',
  contextMemory: [
    { role: 'user', content: 'Hello' },
    { role: 'assistant', content: 'Hi there' },
  ],
  currentChatId: 'chat-123',
  chatHistory: [
    { role: 'user', content: 'Hello' },
    { role: 'assistant', content: 'Hi there' },
  ],
  setGenerating: mockSetGenerating,
  userMemory: { name: 'Test User' },
  generateChatId: vi.fn(() => 'chat-generated'),
};

vi.mock('../store', () => {
  const setState = (partial: Record<string, unknown> | ((state: Record<string, unknown>) => Record<string, unknown>)) => {
    const next = typeof partial === 'function' ? partial(mockState) : partial;
    Object.assign(mockState, next);
  };

  const store = Object.assign(
    (selector: (s: Record<string, unknown>) => unknown) => selector(mockState),
    { getState: () => mockState, setState }
  );
  return { useStore: store };
});

// Mock logger to suppress output
vi.mock('../utils/logger', () => ({
  default: {
    debug: vi.fn(),
    info: vi.fn(),
    log: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

// Mock config
vi.mock('../config', () => ({
  default: { API_URL: 'http://localhost:5000' },
}));

// ── Helpers ────────────────────────────────────────────────────────────────

function createSSEResponse(events: string[]): Response {
  const text = events.join('\n') + '\n';
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text));
      controller.close();
    },
  });

  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

function makeBuildAuthHeaders() {
  return vi.fn().mockResolvedValue({
    'Content-Type': 'application/json',
    'ICP-Principal': 'test-principal',
    'ICP-Signature': 'abcdef',
    'ICP-Timestamp': '12345',
    'ICP-PublicKey': 'pubkey',
    'ICP-Nonce': 'nonce123',
  });
}

// ── Tests ──────────────────────────────────────────────────────────────────

describe('useChat', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockState.currentChatId = 'chat-123';
    (mockState.generateChatId as ReturnType<typeof vi.fn>).mockReturnValue('chat-generated');
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    mockSetGenerating.mockClear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('initializes with default state', () => {
    const { result } = renderHook(() => useChat());
    expect(result.current.tokens).toBe('');
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.phase).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.agentResponse).toBeNull();
  });

  it('exposes send, stop, continueGeneration, clearError', () => {
    const { result } = renderHook(() => useChat());
    expect(typeof result.current.send).toBe('function');
    expect(typeof result.current.stop).toBe('function');
    expect(typeof result.current.continueGeneration).toBe('function');
    expect(typeof result.current.clearError).toBe('function');
  });

  it('streams tokens from backend', async () => {
    const sseResponse = createSSEResponse([
      'data: {"token": "Hello"}',
      'data: {"token": " world"}',
      'data: {"done": true, "done_reason": "stop"}',
    ]);
    fetchSpy.mockResolvedValue(sseResponse);

    const { result } = renderHook(() => useChat());
    const buildAuth = makeBuildAuthHeaders();

    await act(async () => {
      await result.current.send('Hello', buildAuth);
    });

    expect(result.current.tokens).toBe('Hello world');
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.agentResponse).toEqual(
      expect.objectContaining({ done_reason: 'stop' })
    );
  });

  it('sends correct request body', async () => {
    const sseResponse = createSSEResponse([
      'data: {"done": true, "done_reason": "stop"}',
    ]);
    fetchSpy.mockResolvedValue(sseResponse);

    const { result } = renderHook(() => useChat());
    const buildAuth = makeBuildAuthHeaders();

    await act(async () => {
      await result.current.send('Test prompt', buildAuth);
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      'http://localhost:5000/generate/agent',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"prompt":"Test prompt"'),
      })
    );

    const callBody = JSON.parse((fetchSpy.mock.calls[0]?.[1] as { body: string })?.body ?? '{}');
    expect(callBody).toMatchObject({
      prompt: 'Test prompt',
      principal: 'test-principal',
      chat_id: 'chat-123',
      message_index: 2,
      context_messages: [
        { role: 'user', content: 'Hello' },
        { role: 'assistant', content: 'Hi there' },
      ],
    });
  });

  it('generates a chat id when none exists', async () => {
    mockState.currentChatId = null;
    (mockState.generateChatId as ReturnType<typeof vi.fn>).mockReturnValue('chat-new');

    const sseResponse = createSSEResponse([
      'data: {"done": true, "done_reason": "stop"}',
    ]);
    fetchSpy.mockResolvedValue(sseResponse);

    const { result } = renderHook(() => useChat());
    const buildAuth = makeBuildAuthHeaders();

    await act(async () => {
      await result.current.send('Test prompt', buildAuth);
    });

    const callBody = JSON.parse((fetchSpy.mock.calls[0]?.[1] as { body: string })?.body ?? '{}');
    expect(callBody.chat_id).toBe('chat-new');
    expect(mockState.currentChatId).toBe('chat-new');
  });

  it('handles phase events', async () => {
    const sseResponse = createSSEResponse([
      'data: {"phase": "thinking", "message": "Analyzing..."}',
      'data: {"token": "result"}',
      'data: {"done": true, "done_reason": "stop"}',
    ]);
    fetchSpy.mockResolvedValue(sseResponse);

    const { result } = renderHook(() => useChat());
    const buildAuth = makeBuildAuthHeaders();

    await act(async () => {
      await result.current.send('Hello', buildAuth);
    });

    expect(result.current.tokens).toBe('result');
  });

  it('handles backend error events', async () => {
    const sseResponse = createSSEResponse([
      'data: {"error": "Model overloaded"}',
    ]);
    fetchSpy.mockResolvedValue(sseResponse);

    const { result } = renderHook(() => useChat());
    const buildAuth = makeBuildAuthHeaders();

    await act(async () => {
      await result.current.send('Hello', buildAuth);
    });

    expect(result.current.error).toBeTruthy();
    expect(result.current.error?.message).toBe('Model overloaded');
  });

  it('handles HTTP error response', async () => {
    fetchSpy.mockResolvedValue(
      new Response('Not Found', { status: 404, statusText: 'Not Found' })
    );

    const { result } = renderHook(() => useChat());
    const buildAuth = makeBuildAuthHeaders();

    await act(async () => {
      await result.current.send('Hello', buildAuth);
    });

    expect(result.current.error).toBeTruthy();
    expect(result.current.error?.message).toContain('404');
  });

  it('handles 429 rate limiting', async () => {
    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ retry_after: 30 }), {
        status: 429,
        statusText: 'Too Many Requests',
      })
    );

    const { result } = renderHook(() => useChat());
    const buildAuth = makeBuildAuthHeaders();

    await act(async () => {
      await result.current.send('Hello', buildAuth);
    });

    expect(result.current.error).toBeTruthy();
    expect(result.current.error?.message).toContain('Rate limited');
    expect(result.current.error?.message).toContain('30');
  });

  it('handles auth header failure', async () => {
    const noAuthHeaders = vi.fn().mockResolvedValue(null);

    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.send('Hello', noAuthHeaders);
    });

    expect(result.current.error?.message).toBe('Authentication required');
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('clearError resets error state', async () => {
    fetchSpy.mockResolvedValue(
      new Response('Error', { status: 500, statusText: 'Server Error' })
    );

    const { result } = renderHook(() => useChat());
    const buildAuth = makeBuildAuthHeaders();

    await act(async () => {
      await result.current.send('Hello', buildAuth);
    });

    expect(result.current.error).toBeTruthy();

    act(() => {
      result.current.clearError();
    });

    expect(result.current.error).toBeNull();
  });

  it('stop aborts the stream gracefully', async () => {
    const encoder = new TextEncoder();

    fetchSpy.mockImplementation((_url: string, _init: RequestInit) => {
      return Promise.resolve(
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(encoder.encode('data: {"token": "partial"}\n'));
              // Don't close - simulate long stream
            },
          }),
          { status: 200 }
        )
      );
    });

    const { result } = renderHook(() => useChat());
    const buildAuth = makeBuildAuthHeaders();

    // Start streaming without awaiting (it won't finish until aborted)
    let sendPromise: Promise<{ success: boolean; error?: string }>;
    act(() => {
      sendPromise = result.current.send('Hello', buildAuth);
    });

    // Give it a moment to start processing
    await new Promise((r) => setTimeout(r, 50));

    // Abort
    act(() => {
      result.current.stop();
    });

    // Wait for send to complete
    await act(async () => {
      await sendPromise!;
    });

    // Should NOT have an error (AbortError is swallowed)
    expect(result.current.error).toBeNull();
    expect(result.current.isStreaming).toBe(false);
  });

  it('continueGeneration sends continuation prompt', async () => {
    // First send to set up tokensRef
    const initialResponse = createSSEResponse([
      'data: {"token": "Hello world this is a long response"}',
      'data: {"done": true, "done_reason": "length"}',
    ]);
    fetchSpy.mockResolvedValueOnce(initialResponse);

    const { result } = renderHook(() => useChat());
    const buildAuth = makeBuildAuthHeaders();

    await act(async () => {
      await result.current.send('Generate something', buildAuth);
    });

    expect(result.current.tokens).toBe('Hello world this is a long response');

    // Now continue
    const continuationResponse = createSSEResponse([
      'data: {"token": " and more"}',
      'data: {"done": true, "done_reason": "stop"}',
    ]);
    fetchSpy.mockResolvedValueOnce(continuationResponse);

    await act(async () => {
      await result.current.continueGeneration(buildAuth);
    });

    expect(result.current.tokens).toBe(
      'Hello world this is a long response and more'
    );
    expect(result.current.agentResponse?.done_reason).toBe('stop');
  });

  it('calls setGenerating during streaming', async () => {
    const sseResponse = createSSEResponse([
      'data: {"done": true, "done_reason": "stop"}',
    ]);
    fetchSpy.mockResolvedValue(sseResponse);

    const { result } = renderHook(() => useChat());
    const buildAuth = makeBuildAuthHeaders();

    await act(async () => {
      await result.current.send('Hello', buildAuth);
    });

    // setGenerating(true) at start, setGenerating(false) at end
    expect(mockSetGenerating).toHaveBeenCalledWith(true);
    expect(mockSetGenerating).toHaveBeenCalledWith(false);
  });
});
