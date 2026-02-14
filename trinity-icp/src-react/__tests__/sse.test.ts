/**
 * SSE stream parser tests.
 */
import { describe, it, expect, vi } from 'vitest';
import { streamSSE } from '../utils/sse';

/** Helper to create a ReadableStream from SSE lines */
function createSSEStream(lines: string[]): Response {
  const data = lines.join('\n') + '\n';
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(data));
      controller.close();
    },
  });
  return { body: stream } as unknown as Response;
}

/** Helper that pushes chunks incrementally */
function createChunkedSSEStream(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let idx = 0;
  const stream = new ReadableStream({
    pull(controller) {
      if (idx < chunks.length) {
        controller.enqueue(encoder.encode(chunks[idx]!));
        idx++;
      } else {
        controller.close();
      }
    },
  });
  return { body: stream } as unknown as Response;
}

describe('streamSSE', () => {
  it('parses a single token event', async () => {
    const response = createSSEStream(['data: {"token":"Hello"}']);
    const events = [];
    for await (const event of streamSSE(response)) {
      events.push(event);
    }
    expect(events).toHaveLength(1);
    expect(events[0]).toEqual({ token: 'Hello' });
  });

  it('parses multiple events', async () => {
    const response = createSSEStream([
      'data: {"token":"Hello"}',
      'data: {"token":" world"}',
      'data: {"done":true,"done_reason":"stop"}',
    ]);
    const events = [];
    for await (const event of streamSSE(response)) {
      events.push(event);
    }
    expect(events).toHaveLength(3);
    expect(events[0]!.token).toBe('Hello');
    expect(events[1]!.token).toBe(' world');
    expect(events[2]!.done).toBe(true);
    expect(events[2]!.done_reason).toBe('stop');
  });

  it('skips non-data lines', async () => {
    const response = createSSEStream([
      'event: message',
      'data: {"token":"Hello"}',
      ': comment line',
      'id: 123',
      'data: {"done":true}',
    ]);
    const events = [];
    for await (const event of streamSSE(response)) {
      events.push(event);
    }
    expect(events).toHaveLength(2);
  });

  it('skips malformed JSON gracefully', async () => {
    const spy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const response = createSSEStream([
      'data: {"token":"ok"}',
      'data: NOT JSON',
      'data: {"done":true}',
    ]);
    const events = [];
    for await (const event of streamSSE(response)) {
      events.push(event);
    }
    expect(events).toHaveLength(2);
    spy.mockRestore();
  });

  it('handles chunked data across boundaries', async () => {
    // Split the SSE line across two chunks
    const response = createChunkedSSEStream([
      'data: {"tok',
      'en":"split"}\n',
    ]);
    const events = [];
    for await (const event of streamSSE(response)) {
      events.push(event);
    }
    expect(events).toHaveLength(1);
    expect(events[0]!.token).toBe('split');
  });

  it('throws on null body', async () => {
    const response = { body: null } as unknown as Response;
    await expect(async () => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      for await (const _event of streamSSE(response)) {
        // noop
      }
    }).rejects.toThrow('Response body is null');
  });

  it('handles phase events', async () => {
    const response = createSSEStream([
      'data: {"phase":"searching","message":"Looking it up..."}',
      'data: {"token":"result"}',
    ]);
    const events = [];
    for await (const event of streamSSE(response)) {
      events.push(event);
    }
    expect(events[0]!.phase).toBe('searching');
    expect(events[0]!.message).toBe('Looking it up...');
  });

  it('handles error events', async () => {
    const response = createSSEStream([
      'data: {"error":"Model overloaded"}',
    ]);
    const events = [];
    for await (const event of streamSSE(response)) {
      events.push(event);
    }
    expect(events[0]!.error).toBe('Model overloaded');
  });

  it('aborts on signal', async () => {
    const controller = new AbortController();
    const encoder = new TextEncoder();

    // Create a stream that never closes (to test abort)
    const stream = new ReadableStream({
      start() {
        // Intentionally keep open
      },
      pull(ctrl) {
        ctrl.enqueue(encoder.encode('data: {"token":"a"}\n'));
        // Abort after first chunk
        setTimeout(() => controller.abort(), 10);
        return new Promise(() => {
          // Never resolve — simulate slow stream
        });
      },
    });
    const response = { body: stream } as unknown as Response;

    const events = [];
    await expect(async () => {
      for await (const event of streamSSE(response, controller.signal)) {
        events.push(event);
      }
    }).rejects.toThrow('Aborted');
  });

  it('handles empty stream', async () => {
    const response = createSSEStream([]);
    const events = [];
    for await (const event of streamSSE(response)) {
      events.push(event);
    }
    expect(events).toHaveLength(0);
  });
});
