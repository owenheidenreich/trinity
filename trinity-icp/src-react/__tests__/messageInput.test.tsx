/**
 * MessageInput component tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
// React import required for JSX transform in test environment
import { MessageInput } from '../components/chat/MessageInput';

vi.mock('../../styles/components/MessageInput.module.css', () => ({
  default: {
    container: 'container',
    attachBtn: 'attachBtn',
    textareaWrapper: 'textareaWrapper',
    textarea: 'textarea',
    sendBtn: 'sendBtn',
    stopBtn: 'stopBtn',
    filePreview: 'filePreview',
    filePreviewClose: 'filePreviewClose',
  },
}));

describe('MessageInput', () => {
  let onSend: ReturnType<typeof vi.fn>;
  let onStop: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    onSend = vi.fn();
    onStop = vi.fn();
  });

  function renderInput(overrides = {}) {
    return render(
      <MessageInput
        onSend={onSend}
        onStop={onStop}
        isGenerating={false}
        {...overrides}
      />
    );
  }

  it('renders textarea with placeholder', () => {
    renderInput();
    expect(screen.getByPlaceholderText('Ask anything...')).toBeTruthy();
  });

  it('shows send button when not generating', () => {
    renderInput();
    // Send button rendered with up arrow ▲ (unicode 9650)
    const sendBtn = screen.getByRole('button', { name: /▲/ });
    expect(sendBtn).toBeTruthy();
  });

  it('shows stop button when generating', () => {
    renderInput({ isGenerating: true });
    // Stop button rendered with square ■ (unicode 9632)
    const stopBtn = screen.getByRole('button', { name: /■/ });
    expect(stopBtn).toBeTruthy();
  });

  it('calls onStop when stop button clicked', () => {
    renderInput({ isGenerating: true });
    const stopBtn = screen.getByRole('button', { name: /■/ });
    fireEvent.click(stopBtn);
    expect(onStop).toHaveBeenCalledOnce();
  });

  it('does not call onSend with empty input', () => {
    renderInput();
    // Send button should be disabled with no input
    const buttons = screen.getAllByRole('button');
    const sendBtn = buttons.find(
      (b) => b.textContent?.includes('▲')
    );
    if (sendBtn) {
      fireEvent.click(sendBtn);
    }
    expect(onSend).not.toHaveBeenCalled();
  });

  it('calls onSend with trimmed text on button click', async () => {
    renderInput();
    const textarea = screen.getByPlaceholderText('Ask anything...');

    await userEvent.type(textarea, 'Hello world');

    const buttons = screen.getAllByRole('button');
    const sendBtn = buttons.find(
      (b) => b.textContent?.includes('▲')
    );
    fireEvent.click(sendBtn!);

    expect(onSend).toHaveBeenCalledWith('Hello world', undefined);
  });

  it('sends on Enter key (without Shift)', async () => {
    renderInput();
    const textarea = screen.getByPlaceholderText('Ask anything...');

    await userEvent.type(textarea, 'Test message');
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(onSend).toHaveBeenCalledWith('Test message', undefined);
  });

  it('does NOT send on Shift+Enter', async () => {
    renderInput();
    const textarea = screen.getByPlaceholderText('Ask anything...');

    await userEvent.type(textarea, 'Line 1');
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });

    expect(onSend).not.toHaveBeenCalled();
  });

  it('does not send on Enter while generating', async () => {
    renderInput({ isGenerating: true });
    const textarea = screen.getByPlaceholderText('Ask anything...');

    await userEvent.type(textarea, 'Hello');
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(onSend).not.toHaveBeenCalled();
  });

  it('clears input after sending', async () => {
    renderInput();
    const textarea = screen.getByPlaceholderText(
      'Ask anything...'
    ) as HTMLTextAreaElement;

    await userEvent.type(textarea, 'Test');
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(textarea.value).toBe('');
  });

  it('disables textarea when disabled prop is true', () => {
    renderInput({ disabled: true });
    const textarea = screen.getByPlaceholderText('Ask anything...');
    expect(textarea).toBeDisabled();
  });

  it('renders attach button', () => {
    renderInput();
    const attachBtn = screen.getByTitle('Attach file');
    expect(attachBtn).toBeTruthy();
  });
});
