/**
 * AI SDK Adapter
 * 
 * Converts between praisonai-ts message/tool formats and AI SDK formats.
 * Handles prompt construction, tool definitions, and result parsing.
 */

import type { Message, ToolDefinition, ToolCall, GenerateTextResult, TokenUsage as PraisonTokenUsage } from '../types';
import type { 
  AISDKToolDefinition, 
  AISDKToolCall, 
  AISDKToolResult,
  TokenUsage,
  FinishReason,
  PraisonStreamChunk
} from './types';

/**
 * AI SDK prompt message types (simplified for compatibility)
 */
export interface AISDKSystemMessage {
  role: 'system';
  content: string;
}

export interface AISDKUserMessage {
  role: 'user';
  content: Array<{ type: 'text'; text: string }>;
}

export interface AISDKAssistantMessage {
  role: 'assistant';
  content: Array<
    | { type: 'text'; text: string }
    | { type: 'tool-call'; toolCallId: string; toolName: string; args: unknown }
  >;
}

export interface AISDKToolMessage {
  role: 'tool';
  content: Array<{
    type: 'tool-result';
    toolCallId: string;
    toolName: string;
    result: unknown;
  }>;
}

export type AISDKMessage = 
  | AISDKSystemMessage 
  | AISDKUserMessage 
  | AISDKAssistantMessage 
  | AISDKToolMessage;

/**
 * Convert praisonai-ts messages to AI SDK prompt format
 */
export function toAISDKPrompt(messages: Message[]): AISDKMessage[] {
  return messages.map(msg => {
    switch (msg.role) {
      case 'system':
        return {
          role: 'system' as const,
          content: msg.content || ''
        };
        
      case 'user':
        return {
          role: 'user' as const,
          content: [{ type: 'text' as const, text: msg.content || '' }]
        };
        
      case 'assistant':
        if (msg.tool_calls && msg.tool_calls.length > 0) {
          return {
            role: 'assistant' as const,
            content: msg.tool_calls.map(tc => ({
              type: 'tool-call' as const,
              toolCallId: tc.id,
              toolName: tc.function.name,
              args: safeParseJSON(tc.function.arguments)
            }))
          };
        }
        return {
          role: 'assistant' as const,
          content: [{ type: 'text' as const, text: msg.content || '' }]
        };
        
      case 'tool':
        return {
          role: 'tool' as const,
          content: [{
            type: 'tool-result' as const,
            toolCallId: msg.tool_call_id || '',
            toolName: msg.name || '',
            result: safeParseJSON(msg.content || '')
          }]
        };
        
      default:
        // Fallback to user message for unknown roles
        return {
          role: 'user' as const,
          content: [{ type: 'text' as const, text: msg.content || '' }]
        };
    }
  });
}

/**
 * Convert praisonai-ts tool definitions to AI SDK format
 * AI SDK expects tools created with the tool() helper from @ai-sdk/provider-utils
 */
export async function toAISDKTools(tools: ToolDefinition[]): Promise<Record<string, any>> {
  const result: Record<string, any> = {};
  
  // Import the tool helper from @ai-sdk/provider-utils
  let toolHelper: any;
  let jsonSchemaHelper: any;
  try {
    const providerUtils = await import('@ai-sdk/provider-utils');
    toolHelper = providerUtils.tool;
    jsonSchemaHelper = providerUtils.jsonSchema;
  } catch {
    toolHelper = null;
    jsonSchemaHelper = null;
  }
  
  for (const toolDef of tools) {
    // Build a proper JSON Schema for the tool parameters
    const params = toolDef.parameters || {};
    const schema = {
      type: 'object' as const,
      properties: params.properties || {},
      required: params.required || [],
      ...(params.additionalProperties !== undefined 
        ? { additionalProperties: params.additionalProperties } 
        : {}),
    };
    
    if (toolHelper && jsonSchemaHelper) {
      // Use AI SDK's tool() helper for proper tool creation
      result[toolDef.name] = toolHelper({
        description: toolDef.description || '',
        parameters: jsonSchemaHelper(schema),
      });
    } else {
      // Fallback format - create tool-like object manually
      result[toolDef.name] = {
        description: toolDef.description || '',
        parameters: schema,
      };
    }
  }
  
  return result;
}

/**
 * Convert AI SDK tool call to praisonai-ts format
 */
export function fromAISDKToolCall(toolCall: AISDKToolCall): ToolCall {
  return {
    id: toolCall.toolCallId,
    type: 'function',
    function: {
      name: toolCall.toolName,
      arguments: typeof toolCall.args === 'string' 
        ? toolCall.args 
        : JSON.stringify(toolCall.args)
    }
  };
}

/**
 * Convert praisonai-ts tool result to AI SDK format
 */
export function toAISDKToolResult(
  toolCallId: string,
  toolName: string,
  result: unknown
): AISDKToolResult {
  return {
    toolCallId,
    toolName,
    result
  };
}

/**
 * Extract text content from AI SDK response content
 */
export function extractTextFromContent(content: unknown[]): string {
  if (!Array.isArray(content)) {
    return '';
  }
  
  return content
    .filter((part): part is { type: 'text'; text: string } => 
      typeof part === 'object' && 
      part !== null && 
      'type' in part && 
      part.type === 'text' &&
      'text' in part
    )
    .map(part => part.text)
    .join('');
}

/**
 * Extract tool calls from AI SDK response content
 */
export function extractToolCallsFromContent(content: unknown[]): ToolCall[] {
  if (!Array.isArray(content)) {
    return [];
  }
  
  return content
    .filter((part): part is { type: 'tool-call'; toolCallId: string; toolName: string; args: unknown } =>
      typeof part === 'object' &&
      part !== null &&
      'type' in part &&
      part.type === 'tool-call'
    )
    .map(part => fromAISDKToolCall({
      toolCallId: part.toolCallId,
      toolName: part.toolName,
      args: part.args
    }));
}

/**
 * Convert AI SDK generate result to praisonai-ts format
 */
export function fromAISDKResult(result: {
  text?: string;
  content?: unknown[];
  toolCalls?: AISDKToolCall[];
  usage?: { promptTokens: number; completionTokens: number };
  finishReason?: string;
}): GenerateTextResult {
  // Extract text from content or use text directly
  let text = result.text || '';
  if (!text && result.content) {
    text = extractTextFromContent(result.content);
  }
  
  // Extract tool calls
  let toolCalls: ToolCall[] = [];
  if (result.toolCalls && result.toolCalls.length > 0) {
    toolCalls = result.toolCalls.map(fromAISDKToolCall);
  } else if (result.content) {
    toolCalls = extractToolCallsFromContent(result.content);
  }
  
  // Map usage - provide defaults if not available
  const usage: PraisonTokenUsage = result.usage ? {
    promptTokens: result.usage.promptTokens,
    completionTokens: result.usage.completionTokens,
    totalTokens: result.usage.promptTokens + result.usage.completionTokens
  } : {
    promptTokens: 0,
    completionTokens: 0,
    totalTokens: 0
  };
  
  // Map finish reason to praisonai-ts format
  const finishReason = mapFinishReasonToProvider(result.finishReason);
  
  return {
    text,
    toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
    usage,
    finishReason,
    raw: result
  };
}

/**
 * Map AI SDK finish reason to internal format
 */
export function mapFinishReason(reason?: string): FinishReason {
  if (!reason) return 'unknown';
  
  switch (reason.toLowerCase()) {
    case 'stop':
    case 'end_turn':
    case 'end':
      return 'stop';
    case 'length':
    case 'max_tokens':
      return 'length';
    case 'tool_calls':
    case 'tool-calls':
    case 'function_call':
      return 'tool-calls';
    case 'content_filter':
    case 'content-filter':
      return 'content-filter';
    case 'error':
      return 'error';
    case 'cancelled':
    case 'canceled':
      return 'cancelled';
    default:
      return 'unknown';
  }
}

/**
 * Map AI SDK finish reason to praisonai-ts provider format
 * Uses underscore format for tool_calls as expected by GenerateTextResult
 */
export function mapFinishReasonToProvider(reason?: string): 'stop' | 'length' | 'tool_calls' | 'content_filter' | 'error' {
  if (!reason) return 'stop';
  
  switch (reason.toLowerCase()) {
    case 'stop':
    case 'end_turn':
    case 'end':
      return 'stop';
    case 'length':
    case 'max_tokens':
      return 'length';
    case 'tool_calls':
    case 'tool-calls':
    case 'function_call':
      return 'tool_calls';
    case 'content_filter':
    case 'content-filter':
      return 'content_filter';
    case 'error':
    case 'cancelled':
    case 'canceled':
    default:
      return 'error';
  }
}

/**
 * Convert AI SDK stream chunk to praisonai-ts format
 */
export function fromAISDKStreamChunk(chunk: {
  type: string;
  textDelta?: string;
  toolCallId?: string;
  toolName?: string;
  argsTextDelta?: string;
  args?: unknown;
  finishReason?: string;
  usage?: { promptTokens: number; completionTokens: number };
}): PraisonStreamChunk | null {
  switch (chunk.type) {
    case 'text-delta':
      if (chunk.textDelta) {
        return { type: 'text', text: chunk.textDelta };
      }
      return null;
      
    case 'tool-call':
      if (chunk.toolCallId && chunk.toolName) {
        return {
          type: 'tool-call-end',
          toolCallId: chunk.toolCallId,
          args: chunk.args
        };
      }
      return null;
      
    case 'tool-call-streaming-start':
      if (chunk.toolCallId && chunk.toolName) {
        return {
          type: 'tool-call-start',
          toolCallId: chunk.toolCallId,
          toolName: chunk.toolName
        };
      }
      return null;
      
    case 'tool-call-delta':
      if (chunk.toolCallId && chunk.argsTextDelta) {
        return {
          type: 'tool-call-delta',
          toolCallId: chunk.toolCallId,
          argsTextDelta: chunk.argsTextDelta
        };
      }
      return null;
      
    case 'finish':
    case 'step-finish':
      return {
        type: 'finish',
        finishReason: mapFinishReason(chunk.finishReason),
        usage: chunk.usage ? {
          promptTokens: chunk.usage.promptTokens,
          completionTokens: chunk.usage.completionTokens,
          totalTokens: chunk.usage.promptTokens + chunk.usage.completionTokens
        } : undefined
      };
      
    default:
      return null;
  }
}

/**
 * Map praisonai-ts tool choice to AI SDK format
 */
export function toAISDKToolChoice(
  toolChoice?: 'auto' | 'none' | 'required' | { type: 'tool'; toolName: string }
): 'auto' | 'none' | 'required' | { type: 'tool'; toolName: string } | undefined {
  if (!toolChoice) return undefined;
  
  if (typeof toolChoice === 'string') {
    return toolChoice;
  }
  
  return toolChoice;
}

/**
 * Safely parse JSON, returning the original string if parsing fails
 */
function safeParseJSON(str: string): unknown {
  if (typeof str !== 'string') {
    return str;
  }
  
  try {
    return JSON.parse(str);
  } catch {
    return str;
  }
}

/**
 * Create a simple prompt from a string
 */
export function createSimplePrompt(prompt: string, systemPrompt?: string): AISDKMessage[] {
  const messages: AISDKMessage[] = [];
  
  if (systemPrompt) {
    messages.push({
      role: 'system',
      content: systemPrompt
    });
  }
  
  messages.push({
    role: 'user',
    content: [{ type: 'text', text: prompt }]
  });
  
  return messages;
}
