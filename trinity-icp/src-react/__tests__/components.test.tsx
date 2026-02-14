/**
 * Component tests — CodeBlock, StreamingCodeCard.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
// React import needed for JSX transform

// Mock the codeParser utilities BEFORE importing components
// Path relative to test file: __tests__/ → utils/
vi.mock('../utils/codeParser', () => ({
  copyToClipboard: vi.fn().mockResolvedValue(true),
  downloadCode: vi.fn(),
  // Pass through any other exports as stubs
  parseCodeBlocks: vi.fn().mockReturnValue([]),
  getLanguageExtension: vi.fn().mockReturnValue('txt'),
  splitAtCompletedBlocks: vi.fn().mockReturnValue({ stable: '', tail: '' }),
}));

import { CodeBlock, StreamingCodeCard } from '../components/chat/CodeBlock';
import { copyToClipboard, downloadCode } from '../utils/codeParser';

// Cast to mocks for assertions
const mockCopyToClipboard = copyToClipboard as ReturnType<typeof vi.fn>;
const mockDownloadCode = downloadCode as ReturnType<typeof vi.fn>;

describe('CodeBlock', () => {
  const defaultProps = {
    code: 'console.log("hello");',
    language: 'javascript',
  };

  beforeEach(() => {
    mockCopyToClipboard.mockClear();
    mockDownloadCode.mockClear();
    // Provide URL.createObjectURL for jsdom
    if (!globalThis.URL.createObjectURL) {
      globalThis.URL.createObjectURL = vi.fn().mockReturnValue('blob:mock');
    }
    if (!globalThis.URL.revokeObjectURL) {
      globalThis.URL.revokeObjectURL = vi.fn();
    }
  });

  it('renders code and language', () => {
    render(<CodeBlock {...defaultProps} />);
    expect(screen.getByText('javascript')).toBeTruthy();
    expect(screen.getByText('console.log("hello");')).toBeTruthy();
  });

  it('shows filename when provided', () => {
    render(<CodeBlock {...defaultProps} filename="app.js" />);
    expect(screen.getByText('javascript — app.js')).toBeTruthy();
  });

  it('collapses and expands on toggle', () => {
    render(<CodeBlock {...defaultProps} />);

    // Initially expanded
    expect(screen.getByText('Collapse')).toBeTruthy();
    expect(screen.getByText('console.log("hello");')).toBeTruthy();

    // Collapse
    fireEvent.click(screen.getByText('Collapse'));
    expect(screen.getByText(/Show.*1 lines/)).toBeTruthy();
    expect(screen.queryByText('console.log("hello");')).toBeNull();

    // Expand
    fireEvent.click(screen.getByText(/Show/));
    expect(screen.getByText('console.log("hello");')).toBeTruthy();
  });

  it('copies code to clipboard', async () => {
    render(<CodeBlock {...defaultProps} />);

    fireEvent.click(screen.getByText('Copy'));
    expect(mockCopyToClipboard).toHaveBeenCalledWith('console.log("hello");');

    await waitFor(() => {
      expect(screen.getByText('Copied!')).toBeTruthy();
    });
  });

  it('downloads code', () => {
    render(<CodeBlock {...defaultProps} filename="app.js" />);
    fireEvent.click(screen.getByText('Download'));
    expect(mockDownloadCode).toHaveBeenCalledWith(
      'console.log("hello");',
      'javascript',
      'app.js'
    );
  });

  it('renders highlighted HTML when provided', () => {
    const html = '<span class="hl-keyword">const</span> x = 1;';
    render(<CodeBlock {...defaultProps} highlightedHtml={html} />);
    const codeEl = document.querySelector('code');
    expect(codeEl?.innerHTML).toBe(html);
  });
});

describe('StreamingCodeCard', () => {
  it('renders language and line count', () => {
    render(
      <StreamingCodeCard
        language="python"
        code="print('hello')"
        lineCount={5}
      />
    );
    expect(screen.getByText('python')).toBeTruthy();
    expect(screen.getByText('5 lines...')).toBeTruthy();
  });

  it('defaults to "code" for empty language', () => {
    render(<StreamingCodeCard language="" code="x = 1" lineCount={1} />);
    expect(screen.getByText('code')).toBeTruthy();
  });
});
