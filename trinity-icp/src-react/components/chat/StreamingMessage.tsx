/**
 * StreamingMessage — AI message during active streaming.
 * Splits tokens into stable (completed code blocks, memoized) and tail (re-renders each token).
 * Includes smooth typing animation for natural feel.
 */
import { useMemo, useState, useEffect, useRef } from 'react';
import { splitAtCompletedBlocks } from '../../utils/markdown';
import { MarkdownRenderer, MemoizedMarkdown } from './MarkdownRenderer';
import { StreamingCodeCard } from './CodeBlock';
import { TypingIndicator } from './TypingIndicator';
import type { AgentPhase } from '../../types';
import styles from '../../styles/components/Message.module.css';

const TYPE_SPEED_MS = 12; // ms per character reveal
const CHARS_PER_TICK = 4; // characters revealed per tick

interface StreamingMessageProps {
  tokens: string;
  isStreaming: boolean;
  phase?: AgentPhase | null;
}

export function StreamingMessage({ tokens, isStreaming, phase }: StreamingMessageProps) {
  const [displayedLength, setDisplayedLength] = useState(0);
  const rafRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Typing animation: gradually reveal characters
  useEffect(() => {
    if (displayedLength < tokens.length) {
      rafRef.current = setTimeout(() => {
        setDisplayedLength((prev) => Math.min(prev + CHARS_PER_TICK, tokens.length));
      }, TYPE_SPEED_MS);
      return () => {
        if (rafRef.current) clearTimeout(rafRef.current);
      };
    }
  }, [displayedLength, tokens.length]);

  // When tokens grow, the animation continues naturally
  // When streaming stops, instantly show any remaining
  useEffect(() => {
    if (!isStreaming && displayedLength < tokens.length) {
      setDisplayedLength(tokens.length);
    }
  }, [isStreaming, tokens.length, displayedLength]);

  // When tab returns from background, snap to current position
  // (setTimeout-based animation freezes in background tabs)
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible' && tokens.length > 0) {
        setDisplayedLength(tokens.length);
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [tokens.length]);

  const displayedTokens = tokens.substring(0, displayedLength);

  const { stableText, tailText, streamingBlock } = useMemo(
    () => splitAtCompletedBlocks(displayedTokens),
    [displayedTokens]
  );

  if (isStreaming && !tokens) {
    return (
      <div className={`${styles.message} ${styles.assistant}`}>
        <TypingIndicator phase={phase} />
      </div>
    );
  }

  return (
    <div className={`${styles.message} ${styles.assistant}`}>
      {stableText && (
        <MemoizedMarkdown content={stableText} className={styles.content} />
      )}
      {tailText && (
        <MarkdownRenderer content={tailText} className={styles.content} />
      )}
      {isStreaming && <span className={styles.cursor} />}
      {streamingBlock && (
        <StreamingCodeCard
          language={streamingBlock.lang}
          code={streamingBlock.code}
          lineCount={streamingBlock.lines}
        />
      )}
    </div>
  );
}

export default StreamingMessage;
