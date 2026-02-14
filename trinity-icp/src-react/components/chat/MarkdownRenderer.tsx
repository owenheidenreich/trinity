/**
 * MarkdownRenderer — THE single rendering pipeline.
 * Every message goes through this, whether streaming or static.
 *
 * raw text → preprocessToolCalls → protectMath → marked.parse
 *          → DOMPurify.sanitize → restoreMath (with KaTeX pre-render)
 */
import { useMemo } from 'react';
import { parseMarkdownWithMath } from '../../utils/markdown';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  const html = useMemo(() => parseMarkdownWithMath(content), [content]);

  return (
    <div
      className={className}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

/** Memoized version — never re-renders if content hasn't changed */
export const MemoizedMarkdown = ({ content, className }: MarkdownRendererProps) => {
  return useMemo(
    () => <MarkdownRenderer content={content} className={className} />,
    [content, className]
  );
};

export default MarkdownRenderer;
