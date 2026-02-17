/**
 * API request/response types — typed contracts for all endpoints.
 */
import type { ChatMessage } from './message';

/** Request body for /generate/agent (post-intelligence-overhaul) */
export interface GenerateRequest {
  prompt: string;
  principal: string;
  context_messages: Pick<ChatMessage, 'role' | 'content'>[];
  chat_id: string;
  message_index: number;
}

/** Response from /health endpoint */
export interface HealthCheckResponse {
  status: string;
  model?: string;
  uptime?: number;
  version?: string;
  gpu_type?: string;
  provider_id?: string;
  ollama_connected?: boolean;
  features?: Record<string, boolean>;
  build_timestamp?: string;
}

/** Request body for /chat/autosave */
export interface AutosaveRequest {
  chatId: string;
  title: string;
  messages: Pick<ChatMessage, 'role' | 'content' | 'timestamp'>[];
  metadata: {
    createdAt: number;
    updatedAt: number;
    messageCount: number;
    appVersion: string;
  };
}

/** Response from /chat/list — matches backend camelCase format */
export interface ChatListItem {
  chatId: string;
  title: string;
  messageCount: number;
  createdAt: number;
  lastUpdated: number;
  pinned?: boolean;
  isArchived?: boolean;
  cid?: string;
}

/** Response from /chat/<id> */
export interface ChatLoadResponse {
  chatId: string;
  title: string;
  messages: ChatMessage[];
  metadata: Record<string, unknown>;
}

/** Response from /user/memory */
export interface UserMemory {
  facts: MemoryFact[];
  preferences: Record<string, unknown>;
}

export interface MemoryFact {
  text?: string;
  fact?: string;
  category: string;
  importance?: number;
  source_chat_id?: string;
  created_at: number;
  deleted?: boolean;
  deleted_at?: number;
  last_mentioned?: number;
  invalid_at?: number | null;
}

/** ICP authentication headers */
export type AuthHeaders = Record<string, string> & {
  'Content-Type': string;
  'ICP-Principal': string;
  'ICP-Signature': string;
  'ICP-Timestamp': string;
  'ICP-PublicKey': string;
  'ICP-Nonce': string;
};
