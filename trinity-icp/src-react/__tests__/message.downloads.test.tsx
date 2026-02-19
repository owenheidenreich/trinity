import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Message } from '../components/chat/Message';

describe('Message download cards', () => {
  it('builds a downloadable file card from write_file tool output', () => {
    const content =
      '<tool_call name="write_file"><path>scripts/output.py</path><content>for i in range(2):\n    print("yo")</content></tool_call>';

    render(<Message role="assistant" content={content} />);

    expect(screen.getByText('output.py')).toBeInTheDocument();
    expect(screen.getAllByText('Download').length).toBeGreaterThan(0);
  });

  it('offers download cards for one-line python fenced code blocks', () => {
    const content = '```python\nprint("yo")\n```';

    render(<Message role="assistant" content={content} />);

    expect(screen.getByText('code_1.py')).toBeInTheDocument();
  });
});
