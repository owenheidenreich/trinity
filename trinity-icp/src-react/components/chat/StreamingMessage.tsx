/**
 * StreamingMessage — AI message during active streaming.
 * Splits tokens into stable (completed code blocks, memoized) and tail (re-renders each token).
 */
import { useMemo } from 'react';
import { splitAtCompletedBlocks } from '../../utils/markdown';
import { MarkdownRenderer, MemoizedMarkdown } from './MarkdownRenderer';
import { StreamingCodeCard } from './CodeBlock';
import { TypingIndicator } from './TypingIndicator';
import type { AgentPhase } from '../../types';
import styles from '../../styles/components/Message.module.css';

interface StreamingMessageProps {
  tokens: string;
  isStreaming: boolean;
  phase?: AgentPhase | null;
}

export function StreamingMessage({ tokens, isStreaming, phase }: StreamingMessageProps) {
  const { stableText, tailText, streamingBlock } = useMemo(
    () => splitAtCompletedBlocks(tokens),
    [tokens]
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
