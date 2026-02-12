// ============================================================================
// CODE BLOCK PARSER — Extract code blocks from raw markdown
// ============================================================================
// Parses fenced code blocks from markdown text. Supports:
//   ```python:app.py         → language: python, filename: app.py
//   ```javascript            → language: javascript, filename: code_1.js
//   ```                      → language: text, filename: code_1.txt
// ============================================================================

import { LANG_EXTENSIONS, generateSmartFilename } from './codeUtils.js';

/**
 * Extract all complete fenced code blocks from markdown text.
 * @param {string} markdown - Raw markdown string
 * @returns {Array<{code: string, language: string, filename: string, displayName: string, index: number}>}
 */
export function extractCodeBlocks(markdown) {
    if (!markdown) return [];

    const blocks = [];
    // Match complete fenced code blocks: ```lang:filename\ncode\n```
    const regex = /```(\S*?)(?::(\S+))?\s*\n([\s\S]*?)```/g;
    let match;
    let idx = 0;

    while ((match = regex.exec(markdown)) !== null) {
        const language = match[1] || 'text';
        const explicitFilename = match[2] || null;
        const code = match[3];
        idx++;

        let filename, displayName;
        if (explicitFilename) {
            filename = explicitFilename;
            // Derive display name from explicit filename (strip extension)
            displayName = explicitFilename.replace(/\.\w+$/, '').replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        } else {
            const smart = generateSmartFilename(code, language, idx);
            filename = smart.filename;
            displayName = smart.displayName;
        }

        blocks.push({ code, language, filename, displayName, index: idx });
    }

    return blocks;
}

/**
 * Count how many code blocks are currently complete (have closing ```) 
 * versus in-progress (opened but not closed yet) in the markdown.
 * @param {string} markdown - Partial or full markdown text
 * @returns {{ complete: number, inProgress: boolean, partialCode: string, partialLang: string }}
 */
export function getCodeBlockStatus(markdown) {
    if (!markdown) return { complete: 0, inProgress: false, partialCode: '', partialLang: '' };

    const blocks = extractCodeBlocks(markdown);
    const complete = blocks.length;

    // Check if there's an unclosed code block
    // Count total ``` markers (not inside complete blocks)
    const allFences = markdown.match(/```/g) || [];
    const inProgress = allFences.length % 2 === 1; // Odd means one is unclosed

    let partialCode = '';
    let partialLang = '';
    if (inProgress) {
        // Find the last unclosed ```
        const lastOpen = markdown.lastIndexOf('```');
        const afterFence = markdown.substring(lastOpen + 3);
        const firstNewline = afterFence.indexOf('\n');
        if (firstNewline >= 0) {
            const infoString = afterFence.substring(0, firstNewline).trim();
            const colonIdx = infoString.indexOf(':');
            partialLang = colonIdx >= 0 ? infoString.substring(0, colonIdx) : infoString;
            partialCode = afterFence.substring(firstNewline + 1);
        } else {
            partialLang = afterFence.trim();
        }
    }

    return { complete, inProgress, partialCode, partialLang: partialLang || 'text' };
}
