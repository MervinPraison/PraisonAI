/**
 * UIMessage - AI SDK v6 Compatible UI Message Types
 * 
 * Provides types and utilities for working with UI messages in chat applications.
 * Compatible with AI SDK v6's UIMessage format for seamless integration.
 */

// ============================================================================
// Core Types
// ============================================================================

/**
 * UI Message - The main message type for chat UIs.
 * Compatible with AI SDK v6's UIMessage format.
 */
export interface UIMessage<
  METADATA = unknown,
  DATA_PARTS extends UIDataTypes = UIDataTypes,
  TOOLS extends UITools = UITools,
> {
  /** Unique identifier for the message */
  id: string;
  /** Role of the message sender */
  role: 'system' | 'user' | 'assistant';
  /** Optional metadata */
  metadata?: METADATA;
  /** Message parts for rendering */
  parts: Array<UIMessagePart<DATA_PARTS, TOOLS>>;
}

/** Data types that can be used in UI message data parts */
export type UIDataTypes = Record<string, unknown>;

/** UI Tool definition */
export type UITool = {
  input: unknown;
  output: unknown | undefined;
};

/** UI Tools map */
export type UITools = Record<string, UITool>;

/** All possible UI message part types */
export type UIMessagePart<
  DATA_TYPES extends UIDataTypes = UIDataTypes,
  TOOLS extends UITools = UITools,
> =
  | TextUIPart
  | ReasoningUIPart
  | ToolUIPart<TOOLS>
  | SourceUrlUIPart
  | SourceDocumentUIPart
  | FileUIPart
  | DataUIPart<DATA_TYPES>
  | StepStartUIPart;

// ============================================================================
// Part Types
// ============================================================================

/** Text part of a message */
export interface TextUIPart {
  type: 'text';
  text: string;
  state?: 'streaming' | 'done';
  providerMetadata?: Record<string, unknown>;
}

/** Reasoning part of a message */
export interface ReasoningUIPart {
  type: 'reasoning';
  text: string;
  state?: 'streaming' | 'done';
  providerMetadata?: Record<string, unknown>;
}

/** Tool invocation part */
export interface ToolUIPart<TOOLS extends UITools = UITools> {
  type: 'tool';
  toolInvocationId: string;
  toolName: keyof TOOLS & string;
  state: 'input-streaming' | 'input-available' | 'output-streaming' | 'output-available' | 'error';
  input?: TOOLS[keyof TOOLS]['input'];
  output?: TOOLS[keyof TOOLS]['output'];
  error?: string;
  /** Whether this tool needs approval before execution */
  needsApproval?: boolean;
  /** Approval status */
  approvalStatus?: 'pending' | 'approved' | 'denied';
}

/** Source URL part */
export interface SourceUrlUIPart {
  type: 'source-url';
  sourceId: string;
  url: string;
  title?: string;
  providerMetadata?: Record<string, unknown>;
}

/** Source document part */
export interface SourceDocumentUIPart {
  type: 'source-document';
  sourceId: string;
  mediaType: string;
  title?: string;
  providerMetadata?: Record<string, unknown>;
}

/** File part */
export interface FileUIPart {
  type: 'file';
  mediaType: string;
  url?: string;
  data?: string;
  filename?: string;
}

/** Data part for custom data */
export interface DataUIPart<DATA_TYPES extends UIDataTypes = UIDataTypes> {
  type: 'data';
  dataType: keyof DATA_TYPES & string;
  data: DATA_TYPES[keyof DATA_TYPES];
}

/** Step start marker */
export interface StepStartUIPart {
  type: 'step-start';
  stepNumber: number;
}

// ============================================================================
// Model Message Types (for conversion)
// ============================================================================

export interface ModelMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | ModelMessageContent[];
  name?: string;
  toolCallId?: string;
  toolCalls?: ToolCall[];
}

export type ModelMessageContent =
  | { type: 'text'; text: string }
  | { type: 'image'; image: string | Uint8Array; mimeType?: string }
  | { type: 'file'; data: string | Uint8Array; mimeType: string }
  | { type: 'tool-call'; toolCallId: string; toolName: string; args: unknown }
  | { type: 'tool-result'; toolCallId: string; toolName: string; result: unknown; isError?: boolean };

export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;
  };
}

// ============================================================================
// Conversion Functions
// ============================================================================

/**
 * Convert UI messages to model messages for AI SDK functions.
 * 
 * @example
 * ```typescript
 * const modelMessages = await convertToModelMessages(uiMessages);
 * const result = await generateText({ model, messages: modelMessages });
 * ```
 */
export async function convertToModelMessages(
  messages: Array<Omit<UIMessage, 'id'>>,
  options?: {
    tools?: Record<string, unknown>;
    ignoreIncompleteToolCalls?: boolean;
  }
): Promise<ModelMessage[]> {
  const modelMessages: ModelMessage[] = [];

  for (const message of messages) {
    switch (message.role) {
      case 'system': {
        const textParts = message.parts.filter(
          (part): part is TextUIPart => part.type === 'text'
        );
        if (textParts.length > 0) {
          modelMessages.push({
            role: 'system',
            content: textParts.map(p => p.text).join(''),
          });
        }
        break;
      }

      case 'user': {
        const content: ModelMessageContent[] = [];
        for (const part of message.parts) {
          if (part.type === 'text') {
            content.push({ type: 'text', text: part.text });
          } else if (part.type === 'file') {
            content.push({
              type: 'file',
              data: part.data || '',
              mimeType: part.mediaType,
            });
          }
        }
        if (content.length > 0) {
          modelMessages.push({
            role: 'user',
            content: content.length === 1 && content[0].type === 'text'
              ? content[0].text
              : content,
          });
        }
        break;
      }

      case 'assistant': {
        const content: ModelMessageContent[] = [];
        const toolCalls: ToolCall[] = [];
        
        for (const part of message.parts) {
          if (part.type === 'text') {
            content.push({ type: 'text', text: part.text });
          } else if (part.type === 'tool') {
            // Skip incomplete tool calls if requested
            if (options?.ignoreIncompleteToolCalls &&
                (part.state === 'input-streaming' || part.state === 'input-available')) {
              continue;
            }
            
            toolCalls.push({
              id: part.toolInvocationId,
              type: 'function',
              function: {
                name: part.toolName,
                arguments: JSON.stringify(part.input || {}),
              },
            });
          }
        }

        if (content.length > 0 || toolCalls.length > 0) {
          modelMessages.push({
            role: 'assistant',
            content: content.length === 1 && content[0].type === 'text'
              ? content[0].text
              : content.length > 0 ? content : '',
            ...(toolCalls.length > 0 ? { toolCalls } : {}),
          });
        }

        // Add tool results as separate messages
        for (const part of message.parts) {
          if (part.type === 'tool' && part.state === 'output-available' && part.output !== undefined) {
            modelMessages.push({
              role: 'tool',
              content: typeof part.output === 'string' ? part.output : JSON.stringify(part.output),
              toolCallId: part.toolInvocationId,
            });
          }
        }
        break;
      }
    }
  }

  return modelMessages;
}

/**
 * Convert model messages to UI messages.
 */
export function convertToUIMessages(
  messages: ModelMessage[],
  generateId: () => string = () => crypto.randomUUID()
): UIMessage[] {
  const uiMessages: UIMessage[] = [];

  for (const message of messages) {
    const parts: UIMessagePart[] = [];

    if (typeof message.content === 'string') {
      parts.push({ type: 'text', text: message.content, state: 'done' });
    } else if (Array.isArray(message.content)) {
      for (const content of message.content) {
        if (content.type === 'text') {
          parts.push({ type: 'text', text: content.text, state: 'done' });
        }
      }
    }

    if (message.toolCalls) {
      for (const toolCall of message.toolCalls) {
        parts.push({
          type: 'tool',
          toolInvocationId: toolCall.id,
          toolName: toolCall.function.name,
          state: 'input-available',
          input: JSON.parse(toolCall.function.arguments || '{}'),
        });
      }
    }

    if (message.role !== 'tool') {
      uiMessages.push({
        id: generateId(),
        role: message.role as 'system' | 'user' | 'assistant',
        parts,
      });
    }
  }

  return uiMessages;
}

// ============================================================================
// Validation
// ============================================================================

/**
 * Validate UI messages array.
 */
export function validateUIMessages(messages: unknown[]): messages is UIMessage[] {
  if (!Array.isArray(messages)) return false;
  
  for (const msg of messages) {
    if (!msg || typeof msg !== 'object') return false;
    const m = msg as Record<string, unknown>;
    if (typeof m.id !== 'string') return false;
    if (!['system', 'user', 'assistant'].includes(m.role as string)) return false;
    if (!Array.isArray(m.parts)) return false;
  }
  
  return true;
}

/**
 * Safe validation that returns result object.
 */
export function safeValidateUIMessages(messages: unknown[]): {
  success: boolean;
  value?: UIMessage[];
  error?: string;
} {
  try {
    if (validateUIMessages(messages)) {
      return { success: true, value: messages };
    }
    return { success: false, error: 'Invalid UI messages format' };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Create a text UI message.
 */
export function createTextMessage(
  role: 'user' | 'assistant',
  text: string,
  id?: string
): UIMessage {
  return {
    id: id || crypto.randomUUID(),
    role,
    parts: [{ type: 'text', text, state: 'done' }],
  };
}

/**
 * Create a system message.
 */
export function createSystemMessage(text: string, id?: string): UIMessage {
  return {
    id: id || crypto.randomUUID(),
    role: 'system',
    parts: [{ type: 'text', text, state: 'done' }],
  };
}

/**
 * Check if a message has pending tool approvals.
 */
export function hasPendingApprovals(message: UIMessage): boolean {
  return message.parts.some(
    part => part.type === 'tool' && part.needsApproval && part.approvalStatus === 'pending'
  );
}

/**
 * Get tool parts that need approval.
 */
export function getToolsNeedingApproval(message: UIMessage): ToolUIPart[] {
  return message.parts.filter(
    (part): part is ToolUIPart => 
      part.type === 'tool' && part.needsApproval === true && part.approvalStatus === 'pending'
  );
}

/**
 * Create an approval response for a tool.
 */
export function createApprovalResponse(
  toolInvocationId: string,
  approved: boolean
): { toolInvocationId: string; approved: boolean } {
  return { toolInvocationId, approved };
}

// ============================================================================
// Stream Response Helpers
// ============================================================================

export interface UIMessageStreamOptions {
  /** Called when a message is created */
  onMessage?: (message: UIMessage) => void;
  /** Called when a part is added */
  onPart?: (part: UIMessagePart) => void;
  /** Called on error */
  onError?: (error: Error) => void;
  /** Called when stream completes */
  onFinish?: (messages: UIMessage[]) => void;
}

/**
 * Create a UI message stream response for Next.js route handlers.
 * 
 * @example
 * ```typescript
 * // In app/api/chat/route.ts
 * export async function POST(req: Request) {
 *   const { messages } = await req.json();
 *   const result = await streamText({ model, messages });
 *   return toUIMessageStreamResponse(result);
 * }
 * ```
 */
export function toUIMessageStreamResponse(
  stream: AsyncIterable<any>,
  options?: {
    headers?: Record<string, string>;
    status?: number;
  }
): Response {
  const encoder = new TextEncoder();
  
  const readable = new ReadableStream({
    async start(controller) {
      try {
        for await (const chunk of stream) {
          const data = JSON.stringify(chunk);
          controller.enqueue(encoder.encode(`data: ${data}\n\n`));
        }
        controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        controller.close();
      } catch (error) {
        controller.error(error);
      }
    },
  });

  return new Response(readable, {
    status: options?.status || 200,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      ...options?.headers,
    },
  });
}

/**
 * Pipe UI message stream to a Node.js response.
 */
export function pipeUIMessageStreamToResponse(
  stream: AsyncIterable<any>,
  response: { write: (chunk: string) => void; end: () => void }
): void {
  (async () => {
    try {
      for await (const chunk of stream) {
        const data = JSON.stringify(chunk);
        response.write(`data: ${data}\n\n`);
      }
      response.write('data: [DONE]\n\n');
      response.end();
    } catch (error) {
      response.write(`data: ${JSON.stringify({ error: String(error) })}\n\n`);
      response.end();
    }
  })();
}
