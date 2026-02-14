/**
 * SSE event types — the contract between backend and frontend.
 * When backend changes event format, TypeScript catches it at build time.
 */

/** SSE event emitted during streaming (post-intelligence-overhaul contract) */
export interface SSEEvent {
  /** Streaming token (individual chunk) */
  token?: string;
  /** Stream complete flag */
  done?: boolean;
  /** Why the stream ended */
  done_reason?: 'stop' | 'length';
  /** Agent phase name (e.g. 'searching', 'executing') */
  phase?: string;
  /** Phase description message */
  message?: string;
  /** Error message from backend */
  error?: string;
  /** Agent response metadata (present on done events) */
  response?: AgentResponse;
}

/** A single chat message */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

/** Agent metadata returned on stream completion (single-pass pipeline) */
export interface AgentResponse {
  answer?: string;
  search_performed?: boolean;
  search_query?: string;
  total_time_seconds?: number;
  done_reason: 'stop' | 'length';
  model?: string;
}

/** Agent phase during streaming */
export interface AgentPhase {
  name: string;
  message?: string;
}

/** Done reason when stream completes */
export type DoneReason = 'stop' | 'length';
