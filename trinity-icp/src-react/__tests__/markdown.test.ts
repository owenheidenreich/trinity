/**
 * Tests for utils/markdown — math protection, tool call preprocessing, rendering pipeline.
 */
import { describe, it, expect } from 'vitest';
import {
  containsMath,
  protectMath,
  restoreMath,
  preprocessToolCalls,
  parseMarkdownWithMath,
  splitAtCompletedBlocks,
} from '../utils/markdown';

describe('containsMath', () => {
  it('detects block math with $$', () => {
    expect(containsMath('Result: $$x^2 + y^2 = z^2$$')).toBe(true);
  });

  it('detects inline math with $', () => {
    expect(containsMath('The value is $\\alpha + \\beta$.')).toBe(true);
  });

  it('detects \\[...\\] delimiters', () => {
    expect(containsMath('Equation: \\[E = mc^2\\]')).toBe(true);
  });

  it('detects \\(...\\) delimiters', () => {
    expect(containsMath('Inline \\(x + 1\\) here')).toBe(true);
  });

  it('returns false for plain text', () => {
    expect(containsMath('Just regular text')).toBe(false);
  });

  it('returns false for currency amounts', () => {
    // Single $ without matching closer should not match inline regex
    expect(containsMath('Price is $100')).toBe(false);
  });
});

describe('protectMath', () => {
  it('protects block math with placeholders', () => {
    const { processed, mathBlocks } = protectMath('Before $$x^2$$ after');
    expect(processed).toContain('%%MATH_BLOCK_0%%');
    expect(processed).not.toContain('$$');
    expect(mathBlocks.get('%%MATH_BLOCK_0%%')).toBe('x^2');
  });

  it('protects inline math with placeholders', () => {
    const { processed, mathBlocks } = protectMath('Inline $\\alpha$ here');
    expect(processed).toContain('%%MATH_INLINE_0%%');
    expect(mathBlocks.get('%%MATH_INLINE_0%%')).toBe('\\alpha');
  });

  it('normalizes \\[...\\] to block math', () => {
    const { processed } = protectMath('Equation \\[E = mc^2\\]');
    expect(processed).toContain('%%MATH_BLOCK_0%%');
  });

  it('normalizes \\(...\\) to inline math', () => {
    const { processed } = protectMath('Value \\(x + 1\\)');
    expect(processed).toContain('%%MATH_INLINE_0%%');
  });

  it('skips currency patterns', () => {
    const { processed, mathBlocks } = protectMath('Costs $100 today');
    expect(mathBlocks.size).toBe(0);
    expect(processed).toContain('$100');
  });

  it('handles multiple math blocks', () => {
    const { mathBlocks } = protectMath('$$a$$ and $$b$$');
    expect(mathBlocks.size).toBe(2);
  });
});

describe('restoreMath', () => {
  it('restores math with KaTeX rendering', () => {
    const mathBlocks = new Map<string, string>();
    mathBlocks.set('%%MATH_BLOCK_0%%', 'x^2');
    const result = restoreMath('Result: %%MATH_BLOCK_0%%', mathBlocks, true);
    expect(result).toContain('math-block');
    expect(result).toContain('katex');
  });

  it('restores inline math with KaTeX rendering', () => {
    const mathBlocks = new Map<string, string>();
    mathBlocks.set('%%MATH_INLINE_0%%', '\\alpha');
    const result = restoreMath('Value %%MATH_INLINE_0%%', mathBlocks, true);
    expect(result).toContain('math-inline');
    expect(result).toContain('katex');
  });

  it('falls back to raw math when preRender is false', () => {
    const mathBlocks = new Map<string, string>();
    mathBlocks.set('%%MATH_BLOCK_0%%', 'x^2');
    const result = restoreMath('%%MATH_BLOCK_0%%', mathBlocks, false);
    expect(result).toContain('$$x^2$$');
  });
});

describe('preprocessToolCalls', () => {
  it('converts code_display tool call to fenced code block', () => {
    const input = '<tool_call name="code_display"><language>python</language><code>print("hello")</code></tool_call>';
    const result = preprocessToolCalls(input);
    expect(result).toContain('```python');
    expect(result).toContain('print("hello")');
    expect(result).toContain('```');
    expect(result).not.toContain('<tool_call');
  });

  it('converts write_file tool call to fenced code block with filename', () => {
    const input = '<tool_call name="write_file"><path>scripts/output.py</path><content>for i in range(3):\\n    print(i)</content></tool_call>';
    const result = preprocessToolCalls(input);
    expect(result).toContain('```python:output.py');
    expect(result).toContain('for i in range(3):');
    expect(result).toContain('```');
    expect(result).not.toContain('<tool_call');
  });

  it('strips non-display tool calls', () => {
    const input = 'Before <tool_call name="calculator"><expression>2+2</expression></tool_call> after';
    const result = preprocessToolCalls(input);
    expect(result).not.toContain('<tool_call');
    expect(result).not.toContain('calculator');
    expect(result).toContain('Before');
    expect(result).toContain('after');
  });

  it('passes through text without tool calls unchanged', () => {
    const input = 'Just regular text';
    expect(preprocessToolCalls(input)).toBe(input);
  });
});

describe('parseMarkdownWithMath', () => {
  it('returns empty string for empty input', () => {
    expect(parseMarkdownWithMath('')).toBe('');
  });

  it('renders basic markdown', () => {
    const result = parseMarkdownWithMath('**bold** and *italic*');
    expect(result).toContain('<strong>bold</strong>');
    expect(result).toContain('<em>italic</em>');
  });

  it('renders math within markdown', () => {
    const result = parseMarkdownWithMath('The formula is $$E = mc^2$$.');
    expect(result).toContain('katex');
    expect(result).toContain('math-block');
  });

  it('renders inline code', () => {
    const result = parseMarkdownWithMath('Use `console.log()` here');
    expect(result).toContain('<code>');
    expect(result).toContain('console.log()');
  });

  it('sanitizes XSS attempts', () => {
    const result = parseMarkdownWithMath('<script>alert("xss")</script>');
    expect(result).not.toContain('<script>');
  });
});

describe('splitAtCompletedBlocks', () => {
  it('returns full text as tail when no code blocks', () => {
    const result = splitAtCompletedBlocks('Just text');
    expect(result.stableText).toBe('');
    expect(result.tailText).toBe('Just text');
    expect(result.streamingBlock).toBeNull();
  });

  it('splits at completed code block boundary', () => {
    const text = '```js\nconst a = 1;\n```\nMore text here';
    const result = splitAtCompletedBlocks(text);
    expect(result.stableText).toBe('```js\nconst a = 1;\n```');
    expect(result.tailText).toBe('\nMore text here');
    expect(result.streamingBlock).toBeNull();
  });

  it('detects streaming code block', () => {
    const text = '```js\ndone\n```\n```python\nstill writing';
    const result = splitAtCompletedBlocks(text);
    expect(result.stableText).toBe('```js\ndone\n```');
    expect(result.streamingBlock).not.toBeNull();
    expect(result.streamingBlock!.lang).toBe('python');
    expect(result.streamingBlock!.code).toContain('still writing');
  });
});
