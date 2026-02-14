/**
 * MarkdownRenderer — THE single rendering pipeline.
 * Every message goes through this, whether streaming or static.
 *
 * raw text → preprocessToolCalls → protectMath → marked.parse
 *          → DOMPurify.sanitize → restoreMath (with KaTeX pre-render)
 *
 * Code blocks are extracted and rendered as interactive <CodeBlock> components
 * with collapse, copy, and download functionality.
 */
import { useMemo } from 'react';
import { parseMarkdownWithMath } from '../../utils/markdown';
import { CodeBlock } from './CodeBlock';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

interface RenderSegment {
  type: 'html' | 'code';
  html?: string;
  code?: string;
  language?: string;
  highlightedHtml?: string;
}

/**
 * Split rendered HTML into segments: interleave HTML prose with CodeBlock components.
 * Finds <pre><code ...>...</code></pre> blocks and extracts them.
 */
function splitHtmlIntoSegments(html: string): RenderSegment[] {
  const segments: RenderSegment[] = [];
  // Match <pre><code class="hljs language-xxx" data-language="xxx">...</code></pre>
  const codeBlockRegex = /<pre><code\s+class="hljs\s+language-(\S*)"(?:\s+data-language="([^"]*)")?>([\s\S]*?)<\/code><\/pre>/g;

  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = codeBlockRegex.exec(html)) !== null) {
    // Add HTML before this code block
    if (match.index > lastIndex) {
      const before = html.substring(lastIndex, match.index);
      if (before.trim()) {
        segments.push({ type: 'html', html: before });
      }
    }

    // Extract code: un-escape HTML entities in the highlighted code to get raw text
    const highlightedHtml = match[3] ?? '';
    const lang = match[2] || match[1] || '';
    // Decode HTML entities to get raw code for copy/download
    const rawCode = highlightedHtml
      .replace(/<[^>]+>/g, '') // strip HTML tags from highlighting
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'");

    segments.push({
      type: 'code',
      code: rawCode,
      language: lang,
      highlightedHtml,
    });

    lastIndex = match.index + match[0].length;
  }

  // Add remaining HTML after last code block
  if (lastIndex < html.length) {
    const remaining = html.substring(lastIndex);
    if (remaining.trim()) {
      segments.push({ type: 'html', html: remaining });
    }
  }

  return segments;
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  const segments = useMemo(() => {
    const html = parseMarkdownWithMath(content);
    const segs = splitHtmlIntoSegments(html);
    // If no code blocks found, return single HTML segment for simplicity
    if (segs.length === 0) return [{ type: 'html' as const, html }];
    return segs;
  }, [content]);

  // Fast path: no code blocks, just render HTML
  if (segments.length === 1 && segments[0]!.type === 'html') {
    return (
      <div
        className={className}
        dangerouslySetInnerHTML={{ __html: segments[0]!.html ?? '' }}
      />
    );
  }

  return (
    <div className={className}>
      {segments.map((seg, i) =>
        seg.type === 'html' ? (
          <div key={i} dangerouslySetInnerHTML={{ __html: seg.html ?? '' }} />
        ) : (
          <CodeBlock
            key={i}
            code={seg.code ?? ''}
            language={seg.language ?? ''}
            highlightedHtml={seg.highlightedHtml}
          />
        )
      )}
    </div>
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
