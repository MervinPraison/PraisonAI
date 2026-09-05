/**
 * Per-call options of `Agent.chat` (Python parity: `agent/chat_mixin.py`
 * `chat()` / `_chat_impl()`).
 *
 * Four behaviours live here, each a direct port of what Python does with the
 * keyword argument of the same name:
 *
 * - `attachments`: images for THIS turn only. Python's
 *   `_build_multimodal_prompt` turns the text prompt plus a list of paths,
 *   URLs or data URIs into an OpenAI multimodal `content` array. The text
 *   still goes into history on its own; the attachment never does.
 * - `reasoningSteps`: Python forces a single NON-streaming completion for the
 *   turn (`llm/llm.py`: "If reasoning_steps is True, do a single
 *   non-streaming call"), because a reasoning response is only readable whole.
 * - `taskName` / `taskDescription` / `taskId`: metadata that Python threads
 *   through the whole turn into `display_interaction` and the interaction
 *   callbacks. Here the equivalent observer channel is the hooks manager, so
 *   the three travel on the `agent_start` / `agent_complete` hook contexts and
 *   are readable afterwards via `Agent.getTaskContext()`.
 * - `config`: Python only forwards it, unchanged, to a managed backend's
 *   `execute()` (`execution_mixin.py::_delegate_to_backend`). So does this.
 */

/** A text part of a multimodal prompt (OpenAI `content` array). */
export interface PromptTextPart {
  type: 'text';
  text: string;
}

/** An image part of a multimodal prompt (OpenAI `content` array). */
export interface PromptImagePart {
  type: 'image_url';
  image_url: { url: string };
}

export type PromptPart = PromptTextPart | PromptImagePart;

/**
 * Task metadata for one turn (Python's `task_name` / `task_description` /
 * `task_id` triple). `undefined` when the caller named none of the three.
 */
export interface TaskContext {
  name?: string;
  description?: string;
  id?: string;
}

/** Python's `_build_multimodal_prompt` extension → media-type table. */
const IMAGE_MEDIA_TYPES: Readonly<Record<string, string>> = Object.freeze({
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
});

/** Build the {@link TaskContext} for a turn, or `undefined` when unused. */
export function resolveTaskContext(opts: {
  taskName?: string;
  taskDescription?: string;
  taskId?: string;
}): TaskContext | undefined {
  const { taskName, taskDescription, taskId } = opts;
  if (taskName === undefined && taskDescription === undefined && taskId === undefined) return undefined;
  const context: TaskContext = {};
  if (taskName !== undefined) context.name = taskName;
  if (taskDescription !== undefined) context.description = taskDescription;
  if (taskId !== undefined) context.id = taskId;
  return context;
}

/**
 * Merge a {@link TaskContext} into a hook/observer payload. Absent fields are
 * not written, so a hook can tell "no task metadata" from "an empty name".
 */
export function withTaskContext<T extends Record<string, unknown>>(
  payload: T,
  task: TaskContext | undefined
): T {
  if (!task) return payload;
  const merged = { ...payload } as Record<string, unknown>;
  if (task.name !== undefined) merged.taskName = task.name;
  if (task.description !== undefined) merged.taskDescription = task.description;
  if (task.id !== undefined) merged.taskId = task.id;
  return merged as T;
}

/**
 * Python `_build_multimodal_prompt`: a string when there is nothing to
 * attach, otherwise the OpenAI multimodal `content` array with the text first.
 *
 * A local image file is read and inlined as a base64 data URI; an
 * `http(s)://` or `data:` attachment is passed through as a URL. Anything
 * else (a missing file, a non-image extension, an unreadable file) is
 * reported through `onWarning` and skipped -- exactly Python's behaviour,
 * which logs and continues rather than failing the turn.
 *
 * `readFile` is injectable so a test need not touch the filesystem.
 */
export async function buildMultimodalPrompt(
  prompt: string,
  attachments: readonly string[] | undefined,
  options: {
    onWarning?: (message: string) => void;
    readFile?: (file: string) => Buffer | null | Promise<Buffer | null>;
  } = {}
): Promise<string | PromptPart[]> {
  if (!attachments || attachments.length === 0) return prompt;

  const warn = options.onWarning ?? (() => {});
  const read = options.readFile ?? defaultReadFile;
  const content: PromptPart[] = [{ type: 'text', text: prompt }];

  for (const attachment of attachments) {
    if (typeof attachment !== 'string' || attachment.length === 0) {
      warn(`Ignoring an attachment that is not a path, URL or data URI: ${String(attachment)}`);
      continue;
    }
    if (/^(https?:\/\/|data:)/.test(attachment)) {
      content.push({ type: 'image_url', image_url: { url: attachment } });
      continue;
    }
    const ext = extensionOf(attachment);
    const mediaType = IMAGE_MEDIA_TYPES[ext];
    if (!mediaType) {
      warn(`Ignoring attachment "${attachment}": only ${Object.keys(IMAGE_MEDIA_TYPES).join(', ')} images are supported.`);
      continue;
    }
    const bytes = await read(attachment);
    if (bytes === null) {
      warn(`Failed to load attachment "${attachment}"; it is not readable.`);
      continue;
    }
    content.push({
      type: 'image_url',
      image_url: { url: `data:${mediaType};base64,${bytes.toString('base64')}` },
    });
  }

  return content;
}

function extensionOf(file: string): string {
  const dot = file.lastIndexOf('.');
  const slash = Math.max(file.lastIndexOf('/'), file.lastIndexOf('\\'));
  return dot > slash ? file.slice(dot).toLowerCase() : '';
}

async function defaultReadFile(file: string): Promise<Buffer | null> {
  try {
    // A computed specifier, not require(): the esm-shim gives any file using
    // require() a createRequire banner, which is a top-level await, and esbuild
    // refuses that at the chrome58 floor the mobile app ships against. This
    // keeps `fs` off the graph AND the file bannerless.
    const fs: typeof import('fs') = await import(/* @vite-ignore */ ['n', 'ode:fs'].join(''));
    if (!fs.existsSync(file) || !fs.statSync(file).isFile()) return null;
    return fs.readFileSync(file);
  } catch {
    return null;
  }
}
