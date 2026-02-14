/**
 * MathBlock — renders KaTeX math expressions.
 * Used by MarkdownRenderer for both inline and display math.
 */
import { useMemo } from 'react';
import katex from 'katex';

interface MathBlockProps {
  expression: string;
  display?: boolean;
}

const MACROS: Record<string, string> = {
  '\\R': '\\mathbb{R}',
  '\\N': '\\mathbb{N}',
  '\\Z': '\\mathbb{Z}',
  '\\Q': '\\mathbb{Q}',
  '\\C': '\\mathbb{C}',
};

export function MathBlock({ expression, display = false }: MathBlockProps) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(expression, {
        displayMode: display,
        throwOnError: false,
        macros: MACROS,
      });
    } catch {
      // HTML-escape fallback to prevent XSS
      const escaped = expression
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
      return display ? `$$${escaped}$$` : `$${escaped}$`;
    }
  }, [expression, display]);

  if (display) {
    return <div className="math-block" dangerouslySetInnerHTML={{ __html: html }} />;
  }

  return <span className="math-inline" dangerouslySetInnerHTML={{ __html: html }} />;
}

export default MathBlock;
