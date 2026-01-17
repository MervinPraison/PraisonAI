/**
 * Built-in Tools - Common utility tools
 * 
 * Provides file, search, and web scraping tools.
 */

import { randomUUID } from 'crypto';

/**
 * Tool result
 */
export interface ToolResult<T = any> {
    success: boolean;
    data?: T;
    error?: string;
}

// ============================================================================
// FILE TOOLS
// ============================================================================

/**
 * Read file tool
 */
export async function readFile(path: string): Promise<ToolResult<string>> {
    try {
        const fs = await import('fs').then(m => m.promises);
        const content = await fs.readFile(path, 'utf-8');
        return { success: true, data: content };
    } catch (error) {
        return { success: false, error: String(error) };
    }
}

/**
 * Write file tool
 */
export async function writeFile(path: string, content: string): Promise<ToolResult<void>> {
    try {
        const fs = await import('fs').then(m => m.promises);
        await fs.writeFile(path, content, 'utf-8');
        return { success: true };
    } catch (error) {
        return { success: false, error: String(error) };
    }
}

/**
 * List directory tool
 */
export async function listDir(path: string): Promise<ToolResult<string[]>> {
    try {
        const fs = await import('fs').then(m => m.promises);
        const entries = await fs.readdir(path);
        return { success: true, data: entries };
    } catch (error) {
        return { success: false, error: String(error) };
    }
}

/**
 * File exists tool
 */
export async function fileExists(path: string): Promise<ToolResult<boolean>> {
    try {
        const fs = await import('fs').then(m => m.promises);
        await fs.access(path);
        return { success: true, data: true };
    } catch {
        return { success: true, data: false };
    }
}

/**
 * Get file stats
 */
export async function fileStats(path: string): Promise<ToolResult<{ size: number; isDirectory: boolean; mtime: number }>> {
    try {
        const fs = await import('fs').then(m => m.promises);
        const stats = await fs.stat(path);
        return {
            success: true,
            data: {
                size: stats.size,
                isDirectory: stats.isDirectory(),
                mtime: stats.mtime.getTime(),
            },
        };
    } catch (error) {
        return { success: false, error: String(error) };
    }
}

// ============================================================================
// SEARCH TOOLS
// ============================================================================

/**
 * Simple text search in content
 */
export function searchText(content: string, query: string, options?: { caseSensitive?: boolean }): ToolResult<{ matches: number; lines: number[] }> {
    const caseSensitive = options?.caseSensitive ?? false;
    const searchContent = caseSensitive ? content : content.toLowerCase();
    const searchQuery = caseSensitive ? query : query.toLowerCase();

    const lines = content.split('\n');
    const matchingLines: number[] = [];
    let matches = 0;

    for (let i = 0; i < lines.length; i++) {
        const line = caseSensitive ? lines[i] : lines[i].toLowerCase();
        const lineMatches = (line.match(new RegExp(searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) ?? []).length;
        if (lineMatches > 0) {
            matchingLines.push(i + 1);
            matches += lineMatches;
        }
    }

    return { success: true, data: { matches, lines: matchingLines } };
}

/**
 * Grep-like search in files
 */
export async function grepFiles(
    pattern: string,
    paths: string[],
    options?: { caseSensitive?: boolean }
): Promise<ToolResult<Array<{ file: string; line: number; content: string }>>> {
    try {
        const fs = await import('fs').then(m => m.promises);
        const results: Array<{ file: string; line: number; content: string }> = [];

        const regex = new RegExp(pattern, options?.caseSensitive ? 'g' : 'gi');

        for (const path of paths) {
            try {
                const content = await fs.readFile(path, 'utf-8');
                const lines = content.split('\n');

                for (let i = 0; i < lines.length; i++) {
                    if (regex.test(lines[i])) {
                        results.push({
                            file: path,
                            line: i + 1,
                            content: lines[i].trim(),
                        });
                    }
                    regex.lastIndex = 0;
                }
            } catch {
                // Skip files that can't be read
            }
        }

        return { success: true, data: results };
    } catch (error) {
        return { success: false, error: String(error) };
    }
}

// ============================================================================
// WEB TOOLS
// ============================================================================

/**
 * Fetch URL content
 */
export async function fetchUrl(url: string, options?: { headers?: Record<string, string> }): Promise<ToolResult<string>> {
    try {
        const response = await fetch(url, {
            headers: options?.headers,
        });

        if (!response.ok) {
            return { success: false, error: `HTTP ${response.status}` };
        }

        const content = await response.text();
        return { success: true, data: content };
    } catch (error) {
        return { success: false, error: String(error) };
    }
}

/**
 * Simple HTML to text converter
 */
export function htmlToText(html: string): string {
    return html
        .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
        .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
        .replace(/<[^>]+>/g, ' ')
        .replace(/\s+/g, ' ')
        .replace(/&nbsp;/g, ' ')
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .trim();
}

/**
 * Scrape webpage
 */
export async function scrapeUrl(url: string): Promise<ToolResult<{ title: string; text: string; links: string[] }>> {
    const result = await fetchUrl(url);
    if (!result.success) return result as ToolResult<any>;

    const html = result.data!;

    // Extract title
    const titleMatch = html.match(/<title[^>]*>([^<]+)<\/title>/i);
    const title = titleMatch ? titleMatch[1].trim() : '';

    // Extract links
    const linkRegex = /href=["']([^"']+)["']/gi;
    const links: string[] = [];
    let match;
    while ((match = linkRegex.exec(html)) !== null) {
        if (match[1].startsWith('http')) {
            links.push(match[1]);
        }
    }

    // Convert to text
    const text = htmlToText(html);

    return {
        success: true,
        data: { title, text: text.slice(0, 10000), links: links.slice(0, 100) },
    };
}

// ============================================================================
// UTILITY TOOLS
// ============================================================================

/**
 * Execute shell command (safe version - read-only commands)
 */
export async function shell(command: string): Promise<ToolResult<string>> {
    // Only allow safe read-only commands
    const safeCommands = ['ls', 'cat', 'head', 'tail', 'wc', 'grep', 'find', 'echo', 'date', 'pwd', 'which'];
    const firstWord = command.split(/\s+/)[0];

    if (!safeCommands.includes(firstWord)) {
        return { success: false, error: `Command not allowed: ${firstWord}` };
    }

    try {
        const { exec } = await import('child_process');
        const { promisify } = await import('util');
        const execAsync = promisify(exec);

        const { stdout, stderr } = await execAsync(command, { timeout: 5000 });
        return { success: true, data: stdout || stderr };
    } catch (error: any) {
        return { success: false, error: error.message ?? String(error) };
    }
}

/**
 * JSON parse tool
 */
export function parseJson<T = any>(text: string): ToolResult<T> {
    try {
        const data = JSON.parse(text);
        return { success: true, data };
    } catch (error) {
        return { success: false, error: String(error) };
    }
}

/**
 * Current time tool
 */
export function getCurrentTime(): ToolResult<{ iso: string; unix: number; formatted: string }> {
    const now = new Date();
    return {
        success: true,
        data: {
            iso: now.toISOString(),
            unix: now.getTime(),
            formatted: now.toLocaleString(),
        },
    };
}

// ============================================================================
// TOOL REGISTRY
// ============================================================================

/**
 * Built-in tools registry
 */
export const builtinTools = {
    // File tools
    readFile,
    writeFile,
    listDir,
    fileExists,
    fileStats,
    // Search tools
    searchText,
    grepFiles,
    // Web tools
    fetchUrl,
    scrapeUrl,
    htmlToText,
    // Utility tools
    shell,
    parseJson,
    getCurrentTime,
};

// Default export
export default builtinTools;
