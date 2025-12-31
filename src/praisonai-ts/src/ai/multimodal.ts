/**
 * Multimodal - AI SDK Wrapper
 * 
 * Provides utilities for multimodal inputs (images, files, PDFs).
 */

import * as fs from 'fs';
import * as path from 'path';

export type InputPart = TextPart | ImagePart | FilePart | PdfPart;

export interface TextPart {
  type: 'text';
  text: string;
}

export interface ImagePart {
  type: 'image';
  /** Image data as URL, base64 string, or Uint8Array */
  image: string | Uint8Array | URL;
  /** MIME type (auto-detected if not provided) */
  mimeType?: string;
}

export interface FilePart {
  type: 'file';
  /** File data as URL, base64 string, or Uint8Array */
  data: string | Uint8Array | URL;
  /** MIME type (required) */
  mimeType: string;
  /** File name (optional) */
  name?: string;
}

export interface PdfPart {
  type: 'pdf';
  /** PDF data as URL, base64 string, or Uint8Array */
  data: string | Uint8Array | URL;
  /** Page range to extract (optional) */
  pages?: { start?: number; end?: number };
  /** Extract text only (default: false) */
  textOnly?: boolean;
}

/**
 * Create a text part.
 */
export function createTextPart(text: string): TextPart {
  return { type: 'text', text };
}

/**
 * Create an image part from various sources.
 * 
 * @example From URL
 * ```typescript
 * const imagePart = createImagePart('https://example.com/image.png');
 * ```
 * 
 * @example From base64
 * ```typescript
 * const imagePart = createImagePart('data:image/png;base64,...');
 * ```
 * 
 * @example From file path
 * ```typescript
 * const imagePart = await createImagePart('./image.png');
 * ```
 */
export function createImagePart(
  source: string | Uint8Array | URL,
  mimeType?: string
): ImagePart {
  // If it's a file path, read it
  if (typeof source === 'string' && !source.startsWith('http') && !source.startsWith('data:')) {
    if (fs.existsSync(source)) {
      const buffer = fs.readFileSync(source);
      const detectedMime = mimeType || detectImageMimeType(source);
      return {
        type: 'image',
        image: buffer,
        mimeType: detectedMime,
      };
    }
  }

  return {
    type: 'image',
    image: source,
    mimeType,
  };
}

/**
 * Create a file part from various sources.
 * 
 * @example
 * ```typescript
 * const filePart = createFilePart('./document.txt', 'text/plain');
 * ```
 */
export function createFilePart(
  source: string | Uint8Array | URL,
  mimeType: string,
  name?: string
): FilePart {
  // If it's a file path, read it
  if (typeof source === 'string' && !source.startsWith('http') && !source.startsWith('data:')) {
    if (fs.existsSync(source)) {
      const buffer = fs.readFileSync(source);
      return {
        type: 'file',
        data: buffer,
        mimeType,
        name: name || path.basename(source),
      };
    }
  }

  return {
    type: 'file',
    data: source,
    mimeType,
    name,
  };
}

/**
 * Create a PDF part from various sources.
 * 
 * @example
 * ```typescript
 * const pdfPart = createPdfPart('./document.pdf');
 * ```
 * 
 * @example With page range
 * ```typescript
 * const pdfPart = createPdfPart('./document.pdf', { pages: { start: 1, end: 5 } });
 * ```
 */
export function createPdfPart(
  source: string | Uint8Array | URL,
  options?: { pages?: { start?: number; end?: number }; textOnly?: boolean }
): PdfPart {
  // If it's a file path, read it
  if (typeof source === 'string' && !source.startsWith('http') && !source.startsWith('data:')) {
    if (fs.existsSync(source)) {
      const buffer = fs.readFileSync(source);
      return {
        type: 'pdf',
        data: buffer,
        pages: options?.pages,
        textOnly: options?.textOnly,
      };
    }
  }

  return {
    type: 'pdf',
    data: source,
    pages: options?.pages,
    textOnly: options?.textOnly,
  };
}

/**
 * Convert input parts to AI SDK message content format.
 */
export function toMessageContent(parts: InputPart[]): any[] {
  return parts.map(part => {
    switch (part.type) {
      case 'text':
        return { type: 'text', text: part.text };
      case 'image':
        return {
          type: 'image',
          image: part.image,
          mimeType: part.mimeType,
        };
      case 'file':
        return {
          type: 'file',
          data: part.data,
          mimeType: part.mimeType,
        };
      case 'pdf':
        // PDFs are treated as files with application/pdf mime type
        return {
          type: 'file',
          data: part.data,
          mimeType: 'application/pdf',
        };
      default:
        return part;
    }
  });
}

/**
 * Create a multimodal message with text and images.
 * 
 * @example
 * ```typescript
 * const message = createMultimodalMessage(
 *   'What is in this image?',
 *   ['https://example.com/image.png']
 * );
 * ```
 */
export function createMultimodalMessage(
  text: string,
  images: (string | Uint8Array | URL)[],
  role: 'user' | 'assistant' = 'user'
): { role: string; content: any[] } {
  const content: any[] = [];
  
  // Add images first
  for (const image of images) {
    content.push(createImagePart(image));
  }
  
  // Add text
  content.push(createTextPart(text));
  
  return {
    role,
    content: toMessageContent(content as InputPart[]),
  };
}

/**
 * Detect image MIME type from file extension.
 */
function detectImageMimeType(filePath: string): string {
  const ext = path.extname(filePath).toLowerCase();
  const mimeTypes: Record<string, string> = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
    '.bmp': 'image/bmp',
    '.ico': 'image/x-icon',
  };
  return mimeTypes[ext] || 'image/png';
}

/**
 * Convert a base64 string to Uint8Array.
 */
export function base64ToUint8Array(base64: string): Uint8Array {
  // Handle data URLs
  const base64Data = base64.includes(',') ? base64.split(',')[1] : base64;
  const binaryString = atob(base64Data);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes;
}

/**
 * Convert Uint8Array to base64 string.
 */
export function uint8ArrayToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Check if a string is a valid URL.
 */
export function isUrl(str: string): boolean {
  try {
    new URL(str);
    return true;
  } catch {
    return false;
  }
}

/**
 * Check if a string is a data URL.
 */
export function isDataUrl(str: string): boolean {
  return str.startsWith('data:');
}
