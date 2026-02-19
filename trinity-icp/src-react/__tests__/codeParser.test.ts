/**
 * Tests for utils/codeParser — code block extraction and status detection.
 */
import { describe, it, expect } from 'vitest';
import {
  extractCodeBlocks,
  getCodeBlockStatus,
  getExtension,
  LANG_EXTENSIONS,
} from '../utils/codeParser';

describe('extractCodeBlocks', () => {
  it('extracts a single code block with language', () => {
    const md = 'Hello\n```python\nprint("hi")\n```\nBye';
    const blocks = extractCodeBlocks(md);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]!.language).toBe('python');
    expect(blocks[0]!.code).toBe('print("hi")');
    expect(blocks[0]!.index).toBe(0);
  });

  it('extracts multiple code blocks', () => {
    const md = '```js\nconst a = 1;\n```\nsome text\n```rust\nfn main() {}\n```';
    const blocks = extractCodeBlocks(md);
    expect(blocks).toHaveLength(2);
    expect(blocks[0]!.language).toBe('js');
    expect(blocks[1]!.language).toBe('rust');
  });

  it('handles code blocks with filename syntax', () => {
    const md = '```python:utils.py\ndef helper(): pass\n```';
    const blocks = extractCodeBlocks(md);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]!.filename).toBe('utils.py');
  });

  it('handles code blocks without language', () => {
    const md = '```\nplain text\n```';
    const blocks = extractCodeBlocks(md);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]!.language).toBe('');
  });

  it('returns empty array when no code blocks', () => {
    const md = 'Just some regular text.';
    expect(extractCodeBlocks(md)).toHaveLength(0);
  });

  it('generates smart filenames from class names', () => {
    const md = '```python\nclass MyHandler:\n    pass\n```';
    const blocks = extractCodeBlocks(md);
    expect(blocks[0]!.filename).toMatch(/my_handler\.py/);
  });

  it('generates smart filenames from function names', () => {
    const md = '```javascript\nfunction calculateTotal() {}\n```';
    const blocks = extractCodeBlocks(md);
    expect(blocks[0]!.filename).toMatch(/calculate_total\.js/);
  });
});

describe('getCodeBlockStatus', () => {
  it('detects no code blocks', () => {
    const status = getCodeBlockStatus('Just text');
    expect(status.complete).toBe(0);
    expect(status.inProgress).toBe(false);
  });

  it('detects completed code block', () => {
    const status = getCodeBlockStatus('```python\ncode\n```');
    expect(status.complete).toBe(1);
    expect(status.inProgress).toBe(false);
  });

  it('detects in-progress code block', () => {
    const status = getCodeBlockStatus('text\n```python\npartial code here');
    expect(status.complete).toBe(0);
    expect(status.inProgress).toBe(true);
    expect(status.partialLang).toBe('python');
    expect(status.partialCode).toContain('partial code here');
  });

  it('handles mixed complete and in-progress', () => {
    const md = '```js\ndone\n```\ntext\n```python\nstill writing';
    const status = getCodeBlockStatus(md);
    expect(status.complete).toBe(1);
    expect(status.inProgress).toBe(true);
    expect(status.partialLang).toBe('python');
  });
});

describe('getExtension', () => {
  it('returns correct extension for known languages', () => {
    expect(getExtension('python')).toBe('py');
    expect(getExtension('javascript')).toBe('js');
    expect(getExtension('typescript')).toBe('ts');
    expect(getExtension('rust')).toBe('rs');
    expect(getExtension('go')).toBe('go');
  });

  it('is case insensitive', () => {
    expect(getExtension('Python')).toBe('py');
    expect(getExtension('JAVASCRIPT')).toBe('js');
  });

  it('supports common short aliases', () => {
    expect(getExtension('py')).toBe('py');
    expect(getExtension('js')).toBe('js');
    expect(getExtension('ts')).toBe('ts');
  });

  it('defaults to txt for unknown languages', () => {
    expect(getExtension('brainfuck')).toBe('txt');
    expect(getExtension('')).toBe('txt');
  });
});

describe('LANG_EXTENSIONS', () => {
  it('has entries for common languages', () => {
    const expectedLangs = [
      'python', 'javascript', 'typescript', 'java', 'go',
      'rust', 'html', 'css', 'json', 'bash',
    ];
    for (const lang of expectedLangs) {
      expect(LANG_EXTENSIONS).toHaveProperty(lang);
    }
  });
});
