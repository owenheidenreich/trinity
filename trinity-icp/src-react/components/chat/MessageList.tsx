/**
 * MessageList — scrollable message container with auto-scroll.
 *
 * Auto-scroll behavior:
 *  - Always scrolls to bottom when a new message is added (user sent)
 *  - Always scrolls to bottom when streaming starts (AI typing indicator)
 *  - Follows streaming tokens as they arrive
 *  - User can scroll up to disengage auto-scroll
 *  - Scrolling back near the bottom re-engages auto-scroll
 */
import { useRef, useEffect, useCallback } from 'react';
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
  const shouldAutoScrollRef = useRef(true);
  const prevMessageCountRef = useRef(messages.length);
  const wasStreamingRef = useRef(false);
  // Track whether a programmatic scroll is in progress so the onScroll
  // handler doesn't accidentally disable auto-scroll.
  const programmaticScrollRef = useRef(false);

  // ---- Scroll helper ----
  const scrollToBottom = useCallback((instant = false) => {
    const container = containerRef.current;
    if (!container) return;
    programmaticScrollRef.current = true;
    container.scrollTo({
      top: container.scrollHeight,
      behavior: instant ? 'instant' : 'smooth',
    });
    // Clear the programmatic flag after the scroll settles.
    // Smooth scrolls can take ~300-400ms; use a generous timeout.
    setTimeout(() => {
      programmaticScrollRef.current = false;
    }, instant ? 50 : 400);
  }, []);

  // ---- Force scroll when messages.length grows (user sent / AI finalized) ----
  useEffect(() => {
    if (messages.length > prevMessageCountRef.current) {
      shouldAutoScrollRef.current = true;
      // rAF lets the new DOM node paint before we measure scrollHeight
      requestAnimationFrame(() => scrollToBottom());
    }
    prevMessageCountRef.current = messages.length;
  }, [messages.length, scrollToBottom]);

  // ---- Force scroll when a new stream starts ----
  useEffect(() => {
    if (isStreaming && !wasStreamingRef.current) {
      shouldAutoScrollRef.current = true;
      requestAnimationFrame(() => scrollToBottom());
    }
    wasStreamingRef.current = isStreaming;
  }, [isStreaming, scrollToBottom]);

  // ---- Follow streaming tokens while auto-scroll is engaged ----
  useEffect(() => {
    if (shouldAutoScrollRef.current && streamingTokens) {
      scrollToBottom();
    }
  }, [streamingTokens, scrollToBottom]);

  // ---- Detect manual scroll: opt-out when scrolled up, opt-in near bottom ----
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleScroll = () => {
      // Ignore scroll events caused by our own programmatic scrollTo
      if (programmaticScrollRef.current) return;

      const distFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      if (distFromBottom > 200) {
        shouldAutoScrollRef.current = false;
      } else if (distFromBottom < 40) {
        shouldAutoScrollRef.current = true;
      }
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  // ---- Re-sync scroll when tab returns from background ----
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        requestAnimationFrame(() => {
          shouldAutoScrollRef.current = true;
          scrollToBottom();
        });
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [scrollToBottom]);

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
