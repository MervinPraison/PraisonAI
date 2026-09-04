/**
 * Multimodal message assembly for `Task(images=[...])`.
 *
 * Port of `praisonaiagents/agents/agents.py::get_multimodal_message`: a local
 * file is inlined as a `data:` URI, anything else is passed through as a remote
 * image URL, and the text prompt leads the content list.
 *
 * One documented gap: Python's `.mp4` branch decodes the video with OpenCV and
 * appends one frame per second. There is no equivalent decoder in this package,
 * so a local video contributes a text note naming the file instead of silently
 * producing an unusable `data:video/...` URI. Pass extracted frames as images
 * to get the Python behaviour.
 */

import * as fs from 'fs';
import * as path from 'path';

/** One part of an OpenAI-style multimodal message. */
export type MessageContentPart =
    | { type: 'text'; text: string }
    | { type: 'image_url'; image_url: { url: string } };

const VIDEO_EXTENSIONS: ReadonlySet<string> = new Set(['.mp4', '.mov', '.avi', '.mkv', '.webm']);

/**
 * Map an image extension to its registered media type. `.jpg` is `image/jpeg`
 * and `.svg` is `image/svg+xml`; a bare `image/<ext>` is not a registered type
 * and some providers reject the resulting data URI.
 */
const IMAGE_MIME_TYPES: Readonly<Record<string, string>> = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp',
    '.svg': 'image/svg+xml',
};

/** The filesystem calls this module needs; injectable so tests need no disk. */
export interface ImageFileSystem {
    existsSync(p: string): boolean;
    readFileSync(p: string): Buffer;
}

const realFs: ImageFileSystem = {
    existsSync: (p) => fs.existsSync(p),
    readFileSync: (p) => fs.readFileSync(p),
};

/** The note used in place of Python's OpenCV frame extraction. */
export function videoNote(file: string): string {
    return `[video: ${file}] frame extraction is not available in the TypeScript SDK; pass extracted frames as images instead.`;
}

/**
 * Build the message content for `text` plus `images`.
 *
 * With no images this is a single text part, which is what makes the option
 * observable: the same prompt with `images` gains one `image_url` part per
 * entry.
 */
export function buildMultimodalContent(
    text: string,
    images: readonly string[],
    fileSystem: ImageFileSystem = realFs
): MessageContentPart[] {
    const content: MessageContentPart[] = [{ type: 'text', text }];
    for (const image of images) {
        if (!fileSystem.existsSync(image)) {
            content.push({ type: 'image_url', image_url: { url: image } });
            continue;
        }
        const ext = path.extname(image).toLowerCase();
        if (VIDEO_EXTENSIONS.has(ext)) {
            content.push({ type: 'text', text: videoNote(image) });
            continue;
        }
        const encoded = fileSystem.readFileSync(image).toString('base64');
        content.push({
            type: 'image_url',
            image_url: { url: `data:${IMAGE_MIME_TYPES[ext] ?? 'image/png'};base64,${encoded}` },
        });
    }
    return content;
}
