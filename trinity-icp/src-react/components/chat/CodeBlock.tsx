/**
 * CodeBlock — syntax-highlighted, collapsible, copyable, downloadable code block.
 * Self-contained component replacing scattered enhanceCodeBlocks() + addDownloadSection() logic.
 */
import { useState, useCallback, useRef } from 'react';
import { copyToClipboard } from '../../utils/codeParser';
import styles from '../../styles/components/CodeBlock.module.css';

interface CodeBlockProps {
  code: string;
  language: string;
  filename?: string;
  highlightedHtml?: string;
}

export function CodeBlock({ code, language, filename, highlightedHtml }: CodeBlockProps) {
  const [collapsed, setCollapsed] = useState(true);
  const [copyLabel, setCopyLabel] = useState('Copy');
  const codeRef = useRef<HTMLDivElement>(null);

  const handleCopy = useCallback(async () => {
    const success = await copyToClipboard(code);
    if (success) {
      setCopyLabel('Copied!');
      setTimeout(() => setCopyLabel('Copy'), 2000);
    }
  }, [code]);

  const toggleCollapse = useCallback(() => {
    setCollapsed((prev) => !prev);
  }, []);

  const displayLang = language || 'text';
  const lineCount = code.split('\n').length;

  return (
    <div className={`${styles.container} ${collapsed ? styles.collapsed : ''}`}>
      <div className={styles.header}>
        <span className={styles.language}>
          {displayLang}
          {filename && ` — ${filename}`}
        </span>
        <div className={styles.headerActions}>
          <button className={styles.headerBtn} onClick={toggleCollapse}>
            {collapsed ? `Show (${lineCount} lines)` : 'Collapse'}
          </button>
          <button className={styles.headerBtn} onClick={handleCopy}>
            {copyLabel}
          </button>
        </div>
      </div>
      {!collapsed && (
        <div className={styles.code} ref={codeRef}>
          {highlightedHtml ? (
            <pre>
              <code dangerouslySetInnerHTML={{ __html: highlightedHtml }} />
            </pre>
          ) : (
            <pre><code>{code}</code></pre>
          )}
        </div>
      )}
    </div>
  );
}

/** Streaming code card — shows in-progress code block during streaming */
export function StreamingCodeCard({
  language,
  code,
  lineCount,
}: {
  language: string;
  code: string;
  lineCount: number;
}) {
  const [collapsed, setCollapsed] = useState(true);

  const toggleCollapse = useCallback(() => {
    setCollapsed((prev) => !prev);
  }, []);

  return (
    <div className={`${styles.container} ${styles.streamingCard} ${collapsed ? styles.collapsed : ''}`}>
      <div className={styles.header}>
        <span className={styles.language}>{language || 'code'}</span>
        <div className={styles.headerActions}>
          <button className={styles.headerBtn} onClick={toggleCollapse}>
            {collapsed ? `Show (${lineCount} lines...)` : 'Collapse'}
          </button>
          <span className={styles.lineCount}>{lineCount} lines...</span>
        </div>
      </div>
      {!collapsed && (
        <div className={styles.code}>
          <pre><code>{code}</code></pre>
        </div>
      )}
    </div>
  );
}

export default CodeBlock;
