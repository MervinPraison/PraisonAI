/**
 * Document Readers - Parse various document formats
 * 
 * Provides readers for text, markdown, PDF, HTML, and code files.
 * Uses lazy loading for heavy parsers (PDF).
 * 
 * @example
 * ```typescript
 * import { TextReader, MarkdownReader, createReader } from 'praisonai';
 * 
 * const reader = createReader('markdown');
 * const content = await reader.read('docs/guide.md');
 * ```
 */

import { randomUUID } from 'crypto';

/**
 * Parsed document result
 */
export interface ParsedDocument {
    /** Document ID */
    id: string;
    /** Document title/name */
    title: string;
    /** Plain text content */
    content: string;
    /** Original format */
    format: string;
    /** Document metadata */
    metadata: {
        source: string;
        size: number;
        pageCount?: number;
        wordCount: number;
        charCount: number;
        headers?: string[];
        links?: string[];
    };
    /** Sections/chunks */
    sections?: Array<{ title?: string; content: string; level?: number }>;
}

/**
 * Reader interface
 */
export interface Reader {
    /** Supported file extensions */
    extensions: string[];
    /** Read from file path */
    read(path: string): Promise<ParsedDocument>;
    /** Parse content directly */
    parse(content: string, source?: string): ParsedDocument;
}

/**
 * TextReader - Plain text files
 */
export class TextReader implements Reader {
    extensions = ['txt', 'text'];

    async read(path: string): Promise<ParsedDocument> {
        // Lazy load fs
        const fs = await import('fs').then(m => m.promises).catch(() => null);
        if (!fs) throw new Error('File system not available');

        const content = await fs.readFile(path, 'utf-8');
        return this.parse(content, path);
    }

    parse(content: string, source?: string): ParsedDocument {
        const lines = content.split('\n');
        const title = source?.split('/').pop() ?? 'Untitled';

        return {
            id: randomUUID(),
            title,
            content,
            format: 'text',
            metadata: {
                source: source ?? 'unknown',
                size: content.length,
                wordCount: content.split(/\s+/).filter(Boolean).length,
                charCount: content.length,
            },
            sections: [{ content }],
        };
    }
}

/**
 * MarkdownReader - Markdown files
 */
export class MarkdownReader implements Reader {
    extensions = ['md', 'markdown', 'mdx'];

    async read(path: string): Promise<ParsedDocument> {
        const fs = await import('fs').then(m => m.promises).catch(() => null);
        if (!fs) throw new Error('File system not available');

        const content = await fs.readFile(path, 'utf-8');
        return this.parse(content, path);
    }

    parse(content: string, source?: string): ParsedDocument {
        const title = this.extractTitle(content) ?? source?.split('/').pop() ?? 'Untitled';
        const headers = this.extractHeaders(content);
        const links = this.extractLinks(content);
        const sections = this.extractSections(content);
        const plainText = this.stripMarkdown(content);

        return {
            id: randomUUID(),
            title,
            content: plainText,
            format: 'markdown',
            metadata: {
                source: source ?? 'unknown',
                size: content.length,
                wordCount: plainText.split(/\s+/).filter(Boolean).length,
                charCount: plainText.length,
                headers,
                links,
            },
            sections,
        };
    }

    private extractTitle(content: string): string | undefined {
        const match = content.match(/^#\s+(.+)$/m);
        return match?.[1];
    }

    private extractHeaders(content: string): string[] {
        const matches = content.matchAll(/^(#{1,6})\s+(.+)$/gm);
        return Array.from(matches).map(m => m[2]);
    }

    private extractLinks(content: string): string[] {
        const matches = content.matchAll(/\[([^\]]+)\]\(([^)]+)\)/g);
        return Array.from(matches).map(m => m[2]);
    }

    private extractSections(content: string): Array<{ title?: string; content: string; level?: number }> {
        const sections: Array<{ title?: string; content: string; level?: number }> = [];
        const lines = content.split('\n');
        let currentSection: { title?: string; content: string; level?: number } = { content: '' };

        for (const line of lines) {
            const headerMatch = line.match(/^(#{1,6})\s+(.+)$/);
            if (headerMatch) {
                if (currentSection.content.trim()) {
                    sections.push({ ...currentSection, content: currentSection.content.trim() });
                }
                currentSection = {
                    title: headerMatch[2],
                    content: '',
                    level: headerMatch[1].length,
                };
            } else {
                currentSection.content += line + '\n';
            }
        }

        if (currentSection.content.trim()) {
            sections.push({ ...currentSection, content: currentSection.content.trim() });
        }

        return sections;
    }

    private stripMarkdown(content: string): string {
        return content
            .replace(/^#{1,6}\s+/gm, '') // Headers
            .replace(/\*\*(.+?)\*\*/g, '$1') // Bold
            .replace(/\*(.+?)\*/g, '$1') // Italic
            .replace(/`(.+?)`/g, '$1') // Inline code
            .replace(/```[\s\S]*?```/g, '') // Code blocks
            .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1') // Links
            .replace(/^\s*[-*+]\s+/gm, '') // Lists
            .replace(/^\s*\d+\.\s+/gm, '') // Numbered lists
            .replace(/^>\s+/gm, '') // Blockquotes
            .trim();
    }
}

/**
 * HTMLReader - HTML files
 */
export class HTMLReader implements Reader {
    extensions = ['html', 'htm'];

    async read(path: string): Promise<ParsedDocument> {
        const fs = await import('fs').then(m => m.promises).catch(() => null);
        if (!fs) throw new Error('File system not available');

        const content = await fs.readFile(path, 'utf-8');
        return this.parse(content, path);
    }

    parse(content: string, source?: string): ParsedDocument {
        const title = this.extractTitle(content) ?? source?.split('/').pop() ?? 'Untitled';
        const plainText = this.stripHTML(content);
        const links = this.extractLinks(content);

        return {
            id: randomUUID(),
            title,
            content: plainText,
            format: 'html',
            metadata: {
                source: source ?? 'unknown',
                size: content.length,
                wordCount: plainText.split(/\s+/).filter(Boolean).length,
                charCount: plainText.length,
                links,
            },
        };
    }

    private extractTitle(content: string): string | undefined {
        const match = content.match(/<title>([^<]+)<\/title>/i);
        return match?.[1];
    }

    private extractLinks(content: string): string[] {
        const matches = content.matchAll(/href="([^"]+)"/g);
        return Array.from(matches).map(m => m[1]);
    }

    private stripHTML(content: string): string {
        return content
            .replace(/<script[\s\S]*?<\/script>/gi, '')
            .replace(/<style[\s\S]*?<\/style>/gi, '')
            .replace(/<[^>]+>/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    }
}

/**
 * CodeReader - Source code files
 */
export class CodeReader implements Reader {
    extensions = ['ts', 'js', 'py', 'go', 'rs', 'java', 'cpp', 'c', 'rb', 'php'];

    async read(path: string): Promise<ParsedDocument> {
        const fs = await import('fs').then(m => m.promises).catch(() => null);
        if (!fs) throw new Error('File system not available');

        const content = await fs.readFile(path, 'utf-8');
        return this.parse(content, path);
    }

    parse(content: string, source?: string): ParsedDocument {
        const title = source?.split('/').pop() ?? 'Untitled';
        const language = this.detectLanguage(source ?? '');
        const sections = this.extractFunctions(content, language);

        return {
            id: randomUUID(),
            title,
            content,
            format: 'code',
            metadata: {
                source: source ?? 'unknown',
                size: content.length,
                wordCount: content.split(/\s+/).filter(Boolean).length,
                charCount: content.length,
                headers: sections.map(s => s.title).filter(Boolean) as string[],
            },
            sections,
        };
    }

    private detectLanguage(path: string): string {
        const ext = path.split('.').pop()?.toLowerCase();
        const langMap: Record<string, string> = {
            ts: 'typescript', js: 'javascript', py: 'python',
            go: 'go', rs: 'rust', java: 'java', cpp: 'cpp',
            c: 'c', rb: 'ruby', php: 'php',
        };
        return langMap[ext ?? ''] ?? 'unknown';
    }

    private extractFunctions(content: string, language: string): Array<{ title?: string; content: string }> {
        const sections: Array<{ title?: string; content: string }> = [];

        // Simple function extraction (works for most languages)
        const patterns = [
            /(?:function|def|fn|func)\s+(\w+)/g,
            /(?:class)\s+(\w+)/g,
            /(?:const|let|var)\s+(\w+)\s*=/g,
        ];

        for (const pattern of patterns) {
            const matches = content.matchAll(pattern);
            for (const match of matches) {
                sections.push({ title: match[1], content: match[0] });
            }
        }

        if (sections.length === 0) {
            sections.push({ content });
        }

        return sections;
    }
}

/**
 * PDFReader - PDF files (lazy loads pdf-parse)
 */
export class PDFReader implements Reader {
    extensions = ['pdf'];
    private pdfParse: any = null;

    async read(path: string): Promise<ParsedDocument> {
        const fs = await import('fs').then(m => m.promises).catch(() => null);
        if (!fs) throw new Error('File system not available');

        const buffer = await fs.readFile(path);
        return this.parseBuffer(buffer, path);
    }

    parse(content: string, source?: string): ParsedDocument {
        // PDF needs binary, this is for text fallback
        return {
            id: randomUUID(),
            title: source?.split('/').pop() ?? 'Untitled',
            content,
            format: 'pdf',
            metadata: {
                source: source ?? 'unknown',
                size: content.length,
                wordCount: content.split(/\s+/).filter(Boolean).length,
                charCount: content.length,
            },
        };
    }

    async parseBuffer(buffer: Buffer, source?: string): Promise<ParsedDocument> {
        // Lazy load pdf-parse
        if (!this.pdfParse) {
            try {
                // @ts-ignore - dynamic import
                this.pdfParse = (await import('pdf-parse')).default;
            } catch {
                throw new Error('pdf-parse not installed. Install with: npm install pdf-parse');
            }
        }

        const data = await this.pdfParse(buffer);
        const title = source?.split('/').pop() ?? 'Untitled PDF';

        return {
            id: randomUUID(),
            title,
            content: data.text,
            format: 'pdf',
            metadata: {
                source: source ?? 'unknown',
                size: buffer.length,
                pageCount: data.numpages,
                wordCount: data.text.split(/\s+/).filter(Boolean).length,
                charCount: data.text.length,
            },
        };
    }
}

/**
 * Create a reader by type
 */
export function createReader(type: 'text' | 'markdown' | 'html' | 'code' | 'pdf'): Reader {
    switch (type) {
        case 'text': return new TextReader();
        case 'markdown': return new MarkdownReader();
        case 'html': return new HTMLReader();
        case 'code': return new CodeReader();
        case 'pdf': return new PDFReader();
        default: return new TextReader();
    }
}

/**
 * Get reader for file path
 */
export function getReaderForPath(path: string): Reader {
    const ext = path.split('.').pop()?.toLowerCase() ?? '';

    const readers = [
        new MarkdownReader(),
        new HTMLReader(),
        new CodeReader(),
        new PDFReader(),
        new TextReader(),
    ];

    return readers.find(r => r.extensions.includes(ext)) ?? new TextReader();
}

/**
 * Read any supported file
 */
export async function readDocument(path: string): Promise<ParsedDocument> {
    const reader = getReaderForPath(path);
    return reader.read(path);
}

// Default exports
export default {
    TextReader,
    MarkdownReader,
    HTMLReader,
    CodeReader,
    PDFReader,
    createReader,
    getReaderForPath,
    readDocument,
};
