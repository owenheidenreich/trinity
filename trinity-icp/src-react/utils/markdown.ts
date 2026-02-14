/**
 * Markdown + Math rendering pipeline.
 * THE single rendering pipeline — all messages go through this.
 *
 * Flow: raw text → preprocessToolCalls → protectMath → marked.parse
 *       → DOMPurify.sanitize → restoreMath (with KaTeX pre-render)
 *
 * Ported from utils/math.js + ui/editMessage.js.
 */
import { Marked } from 'marked';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js';
import katex from 'katex';

// Configure marked with highlight.js
const marked = new Marked({
  gfm: true,
  breaks: true,
});

marked.use({
  renderer: {
    code(code: string, infostring?: string): string {
      const lang = infostring?.split(/\s+/)[0];
      const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext';
      const highlighted = hljs.highlight(code, { language }).value;
      return `<pre><code class="hljs language-${language}" data-language="${lang ?? ''}">${highlighted}</code></pre>`;
    },
  },
});

// KaTeX macros for common math sets
const KATEX_MACROS: Record<string, string> = {
  '\\R': '\\mathbb{R}',
  '\\N': '\\mathbb{N}',
  '\\Z': '\\mathbb{Z}',
  '\\Q': '\\mathbb{Q}',
  '\\C': '\\mathbb{C}',
};

/** HTML-escape a string to prevent XSS in fallback paths. */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ===== Math Protection =====

type MathBlockMap = Map<string, string>;

interface ProtectResult {
  processed: string;
  mathBlocks: MathBlockMap;
}

/** Detect if content contains math delimiters */
export function containsMath(content: string): boolean {
  return (
    /\$\$[\s\S]+?\$\$/.test(content) || // block math
    /\$[^$\n]+?\$/.test(content) || // inline math
    /\\\[[\s\S]+?\\\]/.test(content) || // \[...\]
    /\\\([\s\S]+?\\\)/.test(content) // \(...\)
  );
}

/**
 * Protect math expressions from markdown parser mangling.
 * Replaces math with placeholders, returns map for restoration.
 */
export function protectMath(content: string): ProtectResult {
  const mathBlocks: MathBlockMap = new Map();
  let blockIndex = 0;
  let inlineIndex = 0;
  let processed = content;

  // Normalize \[...\] → $$...$$ and \(...\) → $...$
  processed = processed.replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$');
  processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$');

  // Protect block math: $$...$$
  processed = processed.replace(/\$\$([\s\S]+?)\$\$/g, (_match, math: string) => {
    const placeholder = `%%MATH_BLOCK_${blockIndex}%%`;
    mathBlocks.set(placeholder, math);
    blockIndex++;
    return placeholder;
  });

  // Protect inline math: $...$  (skip currency like $100)
  processed = processed.replace(
    /(?<!\w)\$([^$\n]+?)\$(?!\w)/g,
    (_match, math: string) => {
      // Skip currency patterns
      if (/^\d/.test(math)) return _match;
      const placeholder = `%%MATH_INLINE_${inlineIndex}%%`;
      mathBlocks.set(placeholder, math);
      inlineIndex++;
      return placeholder;
    }
  );

  return { processed, mathBlocks };
}

/**
 * Restore math placeholders with KaTeX-rendered HTML.
 * Pre-renders to avoid flash during streaming.
 */
export function restoreMath(
  html: string,
  mathBlocks: MathBlockMap,
  preRender = true
): string {
  let result = html;

  for (const [placeholder, math] of mathBlocks) {
    const isBlock = placeholder.includes('MATH_BLOCK');

    if (preRender) {
      try {
        const rendered = katex.renderToString(math, {
          displayMode: isBlock,
          throwOnError: false,
          macros: KATEX_MACROS,
        });
        result = result.replace(
          placeholder,
          isBlock
            ? `<div class="math-block">${rendered}</div>`
            : `<span class="math-inline">${rendered}</span>`
        );
      } catch {
        // Fallback to raw math on KaTeX error — HTML-escape to prevent XSS
        const escaped = escapeHtml(math);
        const fallback = isBlock ? '$$' + escaped + '$$' : '$' + escaped + '$';
        result = result.replace(placeholder, () => fallback);
      }
    } else {
      const escaped = escapeHtml(math);
      const fallback = isBlock ? '$$' + escaped + '$$' : '$' + escaped + '$';
      result = result.replace(placeholder, () => fallback);
    }
  }

  return result;
}

// ===== Tool Call Preprocessing =====

/**
 * Convert <tool_call> XML blocks to renderable markdown.
 * - code_display → fenced code block with correct language
 * - all others (calculator, web_search, etc.) → stripped entirely
 * Ported from ui/editMessage.js with full streaming support.
 */
export function preprocessToolCalls(content: string): string {
  if (!content || !content.includes('<tool_call')) return content;

  let text = content;

  // code_display (complete) → fenced code block
  // Handles proper </tool_call>, malformed <tool_call> closing, AND missing closing tag
  text = text.replace(
    /<tool_call\s+name="code_display"[^>]*>\s*<language>([^<]*)<\/language>\s*<code>([\s\S]*?)<\/code>(?:\s*<execute>[^<]*<\/execute>)?(?:\s*<\/?tool_call\s*>)?/gi,
    (_, lang: string, code: string) =>
      '\n```' + (lang || 'text') + '\n' + code.trim() + '\n```\n'
  );

  // In-progress code_display (no </code> yet, genuinely still streaming)
  text = text.replace(
    /<tool_call\s+name="code_display"[^>]*>\s*<language>([^<]*)<\/language>\s*<code>([\s\S]*)$/gi,
    (_match: string, lang: string, rest: string) => {
      const codeEndIdx = rest.indexOf('</code>');
      if (codeEndIdx >= 0) {
        const code = rest.substring(0, codeEndIdx);
        const after = rest.substring(codeEndIdx + 7);
        return (
          '\n```' + (lang || 'text') + '\n' + code.trim() + '\n```\n' +
          after.replace(/^\s*(?:<\/?tool_call[^>]*>)?\s*/, '')
        );
      }
      return '\n```' + (lang || 'text') + '\n' + rest.trim() + '\n';
    }
  );

  // Strip other complete tool_call blocks (calculator, web_search, etc.)
  text = text.replace(/<tool_call[^>]*>[\s\S]*?<\/tool_call>/gi, '');

  // Strip orphaned non-code tool_call tags and their immediate XML children
  text = text.replace(
    /<tool_call\s+name="(?!code_display)[^"]*"[^>]*>(?:\s*<[a-z_]+>[^<]*<\/[a-z_]+>)*\s*/gi,
    ''
  );

  // Strip any remaining bare <tool_call> or </tool_call> tags
  text = text.replace(/<\/?\s*tool_call[^>]*>/gi, '');

  return text;
}

// ===== Main Pipeline =====

/**
 * Parse raw text through the full rendering pipeline.
 * This is THE single rendering function for all messages.
 *
 * raw text → preprocessToolCalls → protectMath → marked.parse
 *          → DOMPurify.sanitize → restoreMath
 */
export function parseMarkdownWithMath(raw: string): string {
  if (!raw) return '';

  // Step 1: Preprocess tool calls (XML → fenced code blocks)
  let content = preprocessToolCalls(raw);

  // Step 2: Protect math from markdown parser
  const { processed, mathBlocks } = protectMath(content);

  // Step 3: Parse markdown to HTML
  content = marked.parse(processed) as string;

  // Step 4: Sanitize (XSS prevention)
  content = DOMPurify.sanitize(content, {
    ADD_TAGS: ['span', 'div'],
    ADD_ATTR: ['class', 'data-language'],
    ALLOW_DATA_ATTR: true,
  });

  // Step 5: Restore math with KaTeX pre-rendering
  if (mathBlocks.size > 0) {
    content = restoreMath(content, mathBlocks, true);
  }

  return content;
}

/**
 * Split streaming text at the last completed code block boundary.
 * Returns stable text (fully rendered once, memoized) and tail text (re-renders each token).
 */
export function splitAtCompletedBlocks(text: string): {
  stableText: string;
  tailText: string;
  streamingBlock: { lang: string; code: string; lines: number } | null;
} {
  const fenceRegex = /```[\s\S]*?```/g;
  let lastEnd = 0;
  let match: RegExpExecArray | null;

  while ((match = fenceRegex.exec(text)) !== null) {
    lastEnd = match.index + match[0].length;
  }

  const stableText = text.substring(0, lastEnd);
  const tail = text.substring(lastEnd);

  // Check if tail contains an unclosed code block
  const fenceIdx = tail.indexOf('```');
  let streamingBlock: { lang: string; code: string; lines: number } | null = null;

  if (fenceIdx >= 0) {
    const afterFence = tail.substring(fenceIdx + 3);
    const langMatch = afterFence.match(/^(\S*)\s*\n?/);
    const lang = langMatch?.[1] ?? '';
    const codeStart = afterFence.indexOf('\n');
    const code = codeStart >= 0 ? afterFence.substring(codeStart + 1) : '';
    streamingBlock = {
      lang,
      code,
      lines: code.split('\n').length,
    };
  }

  const tailText = fenceIdx >= 0 ? tail.substring(0, fenceIdx) : tail;

  return { stableText, tailText, streamingBlock };
}
