// ============================================================================
// SSE STREAM READER — Shared async generator for Server-Sent Events
// ============================================================================
// Single implementation for all streaming endpoints (agent, stream, etc.).
// Usage: for await (const data of streamSSE(response)) { ... }
// ============================================================================

/**
 * Async generator that yields parsed SSE data objects from a fetch Response.
 * Handles buffering, line splitting, and JSON parsing.
 *
 * @param {Response} response - A fetch Response with text/event-stream body
 * @param {AbortSignal} [signal] - Optional AbortSignal for cancellation
 * @yields {Object} Parsed JSON data from each SSE `data:` line
 */
export async function* streamSSE(response, signal) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
        while (true) {
            // Race read against abort signal
            let readResult;
            if (signal && signal.aborted) break;

            if (signal) {
                readResult = await Promise.race([
                    reader.read(),
                    new Promise((_, reject) => {
                        signal.addEventListener('abort', () => {
                            reader.cancel();
                            reject(new DOMException('Stream aborted', 'AbortError'));
                        }, { once: true });
                    })
                ]);
            } else {
                readResult = await reader.read();
            }

            const { done, value } = readResult;
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        yield JSON.parse(line.slice(6));
                    } catch {
                        // Malformed JSON line — skip
                    }
                }
            }
        }

        // Flush remaining buffer
        if (buffer.trim().startsWith('data: ')) {
            try {
                yield JSON.parse(buffer.trim().slice(6));
            } catch {
                // Ignore
            }
        }
    } finally {
        reader.releaseLock();
    }
}
