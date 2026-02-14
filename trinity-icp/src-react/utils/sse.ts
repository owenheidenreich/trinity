/**
 * SSE stream parser — async generator yielding typed events.
 * Ported from core/sse.js with full TypeScript typing.
 */
import type { SSEEvent } from '../types';
import Logger from './logger';

/**
 * Parse an SSE response body into a stream of typed events.
 * Handles incomplete lines, malformed JSON, and abort signals.
 */
export async function* streamSSE(
  response: Response,
  signal?: AbortSignal
): AsyncGenerator<SSEEvent, void, unknown> {
  const body = response.body;
  if (!body) {
    throw new Error('Response body is null');
  }

  const reader = body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      // Race read against abort signal
      const readPromise = reader.read();
      const result = signal
        ? await Promise.race([
            readPromise,
            new Promise<never>((_, reject) => {
              signal.addEventListener('abort', () =>
                reject(new DOMException('Aborted', 'AbortError')),
                { once: true }
              );
              // If already aborted, reject immediately
              if (signal.aborted) {
                reject(new DOMException('Aborted', 'AbortError'));
              }
            }),
          ])
        : await readPromise;

      if (result.done) break;

      buffer += decoder.decode(result.value, { stream: true });
      const lines = buffer.split('\n');

      // Keep last fragment (may be incomplete)
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith('data: ')) continue;

        const jsonStr = trimmed.slice(6);
        try {
          const event = JSON.parse(jsonStr) as SSEEvent;
          yield event;
        } catch {
          Logger.debug('Skipping malformed SSE JSON:', jsonStr);
        }
      }
    }

    // Flush remaining buffer
    if (buffer.trim().startsWith('data: ')) {
      const jsonStr = buffer.trim().slice(6);
      try {
        const event = JSON.parse(jsonStr) as SSEEvent;
        yield event;
      } catch {
        Logger.debug('Skipping malformed SSE JSON in final flush:', jsonStr);
      }
    }
  } finally {
    reader.releaseLock();
  }
}
