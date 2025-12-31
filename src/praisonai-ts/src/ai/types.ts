/**
 * Shared Types for AI Module
 */

export interface Message {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | ContentPart[];
  name?: string;
  toolCallId?: string;
  toolCalls?: ToolCallPart[];
}

export type ContentPart = TextPart | ImagePart | FilePart | ToolCallPart | ToolResultPart;

export interface TextPart {
  type: 'text';
  text: string;
}

export interface ImagePart {
  type: 'image';
  image: string | Uint8Array | URL;
  mimeType?: string;
}

export interface FilePart {
  type: 'file';
  data: string | Uint8Array | URL;
  mimeType: string;
  name?: string;
}

export interface ToolCallPart {
  type: 'tool-call';
  toolCallId: string;
  toolName: string;
  args: Record<string, unknown>;
}

export interface ToolResultPart {
  type: 'tool-result';
  toolCallId: string;
  toolName: string;
  result: unknown;
  isError?: boolean;
}

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface ProviderMetadata {
  [key: string]: unknown;
}
