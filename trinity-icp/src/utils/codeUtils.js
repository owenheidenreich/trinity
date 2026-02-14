// ============================================================================
// CODE UTILITIES — Shared helpers for code blocks
// ============================================================================
// Extracted to avoid circular imports between messages.js and codePanel.js

import Logger from '../core/logger.js';

/**
 * Language → file extension mapping for downloads
 */
export const LANG_EXTENSIONS = {
    python: 'py', py: 'py', javascript: 'js', js: 'js', typescript: 'ts', ts: 'ts',
    java: 'java', c: 'c', cpp: 'cpp', 'c++': 'cpp', csharp: 'cs', 'c#': 'cs',
    go: 'go', rust: 'rs', ruby: 'rb', php: 'php', swift: 'swift', kotlin: 'kt',
    html: 'html', css: 'css', json: 'json', yaml: 'yaml', yml: 'yml',
    bash: 'sh', shell: 'sh', sh: 'sh', sql: 'sql', r: 'r', lua: 'lua',
    perl: 'pl', scala: 'scala', dart: 'dart', xml: 'xml', markdown: 'md', md: 'md',
    toml: 'toml', ini: 'ini', dockerfile: 'Dockerfile', makefile: 'Makefile',
};

/**
 * Copy text to clipboard using the textarea/execCommand method.
 * (Clipboard API is blocked by ICP permissions policy)
 */
export function copyToClipboard(text, btn, defaultLabel = 'Copy') {
    try {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;opacity:0';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(textArea);
        if (!ok) throw new Error('execCommand copy failed');
        if (btn) {
            btn.textContent = 'Copied!';
            btn.classList.add('copied');
            setTimeout(() => { btn.textContent = defaultLabel; btn.classList.remove('copied'); }, 2000);
        }
    } catch (err) {
        Logger.error('Failed to copy:', err);
        if (btn) {
            btn.textContent = 'Failed';
            setTimeout(() => { btn.textContent = defaultLabel; }, 2000);
        }
    }
}

/**
 * Download code as a file.
 * @param {string} code - The raw code text
 * @param {string} language - Programming language
 * @param {string} [filename] - Optional explicit filename
 */
export function downloadCode(code, language, filename) {
    if (!filename) {
        const ext = LANG_EXTENSIONS[(language || '').toLowerCase()] || 'txt';
        filename = `code.${ext}`;
    }
    const blob = new Blob([code], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

/**
 * Get a file icon character based on language.
 */
export function getFileIcon(language) {
    const lang = (language || '').toLowerCase();
    const icons = {
        python: '🐍', py: '🐍',
        javascript: '📜', js: '📜', typescript: '📘', ts: '📘',
        html: '🌐', css: '🎨',
        json: '📋', yaml: '📋', yml: '📋', toml: '📋',
        bash: '⚙️', shell: '⚙️', sh: '⚙️',
        dockerfile: '🐳', makefile: '⚙️',
        rust: '🦀', go: '🐹',
    };
    return icons[lang] || '📄';
}

/**
 * Auto-generate a descriptive filename from code content.
 * Tries to extract function/class/module names from the code.
 * @param {string} code - The raw code text
 * @param {string} language - The programming language
 * @param {number} index - The code block index (for fallback naming)
 * @returns {{ displayName: string, filename: string }}
 */
export function generateSmartFilename(code, language, index) {
    const ext = LANG_EXTENSIONS[(language || '').toLowerCase()] || 'txt';
    const lang = (language || '').toLowerCase();

    // Try to extract meaningful names from the code
    let name = null;

    // Python: def func_name / class ClassName
    if (lang === 'python' || lang === 'py') {
        const classMatch = code.match(/^class\s+(\w+)/m);
        const funcMatch = code.match(/^def\s+(\w+)/m);
        const mainMatch = code.match(/if\s+__name__\s*==\s*['"]__main__['"]/);
        if (classMatch) name = classMatch[1];
        else if (mainMatch && funcMatch) name = funcMatch[1];
        else if (funcMatch) name = funcMatch[1];
    }
    // JavaScript/TypeScript: function name / class Name / export default
    else if (['javascript', 'js', 'typescript', 'ts'].includes(lang)) {
        const classMatch = code.match(/(?:export\s+)?class\s+(\w+)/);
        const funcMatch = code.match(/(?:export\s+)?(?:async\s+)?function\s+(\w+)/);
        const constMatch = code.match(/(?:export\s+)?const\s+(\w+)\s*=/);
        if (classMatch) name = classMatch[1];
        else if (funcMatch) name = funcMatch[1];
        else if (constMatch) name = constMatch[1];
    }
    // Java/C#/Kotlin: class/interface Name
    else if (['java', 'csharp', 'cs', 'kotlin', 'kt'].includes(lang)) {
        const classMatch = code.match(/(?:public\s+)?class\s+(\w+)/);
        if (classMatch) name = classMatch[1];
    }
    // Go: func name / package name
    else if (lang === 'go') {
        const funcMatch = code.match(/func\s+(\w+)/);
        if (funcMatch) name = funcMatch[1];
    }
    // Rust: fn name / struct Name
    else if (lang === 'rust' || lang === 'rs') {
        const structMatch = code.match(/(?:pub\s+)?struct\s+(\w+)/);
        const fnMatch = code.match(/(?:pub\s+)?fn\s+(\w+)/);
        if (structMatch) name = structMatch[1];
        else if (fnMatch) name = fnMatch[1];
    }
    // HTML: look for <title>
    else if (lang === 'html') {
        const titleMatch = code.match(/<title>([^<]+)<\/title>/i);
        if (titleMatch) name = titleMatch[1].trim().replace(/\s+/g, '_');
    }

    // Convert camelCase/PascalCase to readable display name
    if (name) {
        const displayName = name
            .replace(/([a-z])([A-Z])/g, '$1 $2')   // camelCase → camel Case
            .replace(/_/g, ' ')                       // snake_case → snake case
            .replace(/\b\w/g, c => c.toUpperCase());  // capitalize words
        const filename = `${name.toLowerCase()}.${ext}`;
        return { displayName, filename };
    }

    // Fallback
    return {
        displayName: `Code ${index}`,
        filename: `code_${index}.${ext}`
    };
}
