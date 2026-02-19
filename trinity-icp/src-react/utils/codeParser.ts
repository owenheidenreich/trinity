/**
 * Code block parser — extract and detect code blocks in markdown.
 * Ported from utils/codeBlockParser.js with types.
 */

export interface CodeBlock {
  code: string;
  language: string;
  filename: string;
  displayName: string;
  index: number;
}

export interface CodeBlockStatus {
  complete: number;
  inProgress: boolean;
  partialCode: string;
  partialLang: string;
}

/**
 * Extract all complete code blocks from markdown text.
 * Supports ```language:filename syntax.
 */
export function extractCodeBlocks(markdown: string): CodeBlock[] {
  const blocks: CodeBlock[] = [];
  const regex = /```(\S*?)(?::(\S+))?\s*\n([\s\S]*?)```/g;
  let match: RegExpExecArray | null;
  let index = 0;

  while ((match = regex.exec(markdown)) !== null) {
    const language = match[1] ?? '';
    const filename = match[2] ?? '';
    const code = match[3] ?? '';

    const smartName = generateSmartFilename(code, language, index);

    blocks.push({
      code: code.trim(),
      language: language.toLowerCase(),
      filename: filename || smartName.filename,
      displayName: filename || smartName.displayName,
      index,
    });
    index++;
  }

  return blocks;
}

/**
 * Get the status of code blocks in streaming text.
 * Detects whether a code block is currently in progress (unclosed fence).
 */
export function getCodeBlockStatus(markdown: string): CodeBlockStatus {
  const fenceMatches = markdown.match(/```/g);
  const fenceCount = fenceMatches?.length ?? 0;
  const complete = Math.floor(fenceCount / 2);
  const inProgress = fenceCount % 2 === 1;

  let partialCode = '';
  let partialLang = '';

  if (inProgress) {
    // Extract the unclosed code block
    const lastFenceIdx = markdown.lastIndexOf('```');
    const afterFence = markdown.substring(lastFenceIdx + 3);
    const langMatch = afterFence.match(/^(\S*)\s*\n?/);
    partialLang = langMatch?.[1] ?? '';
    const codeStart = afterFence.indexOf('\n');
    partialCode = codeStart >= 0 ? afterFence.substring(codeStart + 1) : '';
  }

  return { complete, inProgress, partialCode, partialLang };
}

// ===== Code Utilities (from codeUtils.js) =====

/** Language → file extension mapping */
export const LANG_EXTENSIONS: Record<string, string> = {
  python: 'py',
  py: 'py',
  javascript: 'js',
  js: 'js',
  typescript: 'ts',
  ts: 'ts',
  java: 'java',
  cpp: 'cpp',
  'c++': 'cpp',
  c: 'c',
  csharp: 'cs',
  'c#': 'cs',
  go: 'go',
  rust: 'rs',
  ruby: 'rb',
  php: 'php',
  swift: 'swift',
  kotlin: 'kt',
  scala: 'scala',
  html: 'html',
  css: 'css',
  scss: 'scss',
  less: 'less',
  json: 'json',
  yaml: 'yml',
  yml: 'yml',
  xml: 'xml',
  sql: 'sql',
  shell: 'sh',
  bash: 'sh',
  zsh: 'sh',
  sh: 'sh',
  powershell: 'ps1',
  dockerfile: 'Dockerfile',
  markdown: 'md',
  md: 'md',
  plaintext: 'txt',
  text: 'txt',
  toml: 'toml',
  ini: 'ini',
  lua: 'lua',
  r: 'r',
  matlab: 'm',
  perl: 'pl',
  haskell: 'hs',
  elixir: 'ex',
  erlang: 'erl',
  clojure: 'clj',
  dart: 'dart',
  vue: 'vue',
  svelte: 'svelte',
  tsx: 'tsx',
  jsx: 'jsx',
};

/** Get file extension for a language */
export function getExtension(language: string): string {
  return LANG_EXTENSIONS[language.toLowerCase()] ?? 'txt';
}

/** Generate a smart filename by analyzing code content */
function generateSmartFilename(
  code: string,
  language: string,
  index: number
): { displayName: string; filename: string } {
  const ext = getExtension(language);
  const lang = language.toLowerCase();

  // Try to extract meaningful names from code
  const patterns: Record<string, RegExp[]> = {
    python: [/class\s+(\w+)/, /def\s+(\w+)/],
    javascript: [/class\s+(\w+)/, /function\s+(\w+)/, /const\s+(\w+)\s*=/],
    typescript: [/class\s+(\w+)/, /function\s+(\w+)/, /const\s+(\w+)\s*=/],
    java: [/class\s+(\w+)/],
    go: [/func\s+(\w+)/, /type\s+(\w+)/],
    rust: [/fn\s+(\w+)/, /struct\s+(\w+)/, /impl\s+(\w+)/],
    html: [/<title>([^<]+)<\/title>/i],
  };

  const langPatterns = patterns[lang];
  if (langPatterns) {
    for (const pattern of langPatterns) {
      const match = code.match(pattern);
      if (match?.[1]) {
        const name = match[1];
        // Convert camelCase to display name
        const displayName = name.replace(/([A-Z])/g, ' $1').trim();
        return {
          displayName,
          filename: `${camelToSnake(name)}.${ext}`,
        };
      }
    }
  }

  return {
    displayName: `Code ${index + 1}`,
    filename: `code_${index + 1}.${ext}`,
  };
}

function camelToSnake(str: string): string {
  return str.replace(/([A-Z])/g, '_$1').toLowerCase().replace(/^_/, '');
}

/** Copy text to clipboard with fallback */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback for environments where Clipboard API is blocked
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand('copy');
      return true;
    } catch {
      return false;
    } finally {
      document.body.removeChild(textarea);
    }
  }
}

/** Download code as a file */
export function downloadCode(
  code: string,
  language: string,
  filename?: string
): void {
  const ext = getExtension(language);
  const fname = filename ?? `code.${ext}`;
  const blob = new Blob([code], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fname;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
