/**
 * MessageList — scrollable message container with auto-scroll.
 */
import { useRef, useEffect } from 'react';
import { Message } from './Message';
import { StreamingMessage } from './StreamingMessage';
import { ContinueButton } from './ContinueButton';
import type { ChatMessage, AgentPhase, AgentResponse } from '../../types';

interface MessageListProps {
  messages: ChatMessage[];
  streamingTokens: string;
  isStreaming: boolean;
  phase: AgentPhase | null;
  agentResponse: AgentResponse | null;
  onEdit?: (messageIndex: number, content: string) => void;
  onContinue?: () => void;
}

export function MessageList({
  messages,
  streamingTokens,
  isStreaming,
  phase,
  agentResponse,
  onEdit,
  onContinue,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const isNearBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight < 100;
    if (isNearBottom) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages.length, streamingTokens]);

  // Re-sync scroll when tab returns from background
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        // Allow a tick for React to reconcile, then scroll to bottom
        requestAnimationFrame(() => {
          bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
        });
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, []);

  const showContinue =
    !isStreaming && agentResponse?.done_reason === 'length' && onContinue;

  return (
    <div ref={containerRef} style={{ overflow: 'auto', flex: 1, padding: '24px' }}>
      {messages.map((msg, index) => (
        <Message
          key={msg.id}
          role={msg.role}
          content={msg.content}
          onEdit={
            msg.role === 'user' && onEdit
              ? (content) => onEdit(index, content)
              : undefined
          }
        />
      ))}
      {(isStreaming || streamingTokens) &&
        !messages.some(
          (m) => m.content === streamingTokens && m.role === 'assistant'
        ) && (
          <StreamingMessage
            tokens={streamingTokens}
            isStreaming={isStreaming}
            phase={phase}
          />
        )}
      {showContinue && (
        <div style={{ maxWidth: 'var(--chat-max-width)', margin: '0 auto' }}>
          <ContinueButton onContinue={onContinue} />
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

export default MessageList;
