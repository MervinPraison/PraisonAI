/**
 * AI SDK Adapter Tests
 */

import {
  toAISDKPrompt,
  toAISDKTools,
  fromAISDKToolCall,
  fromAISDKResult,
  fromAISDKStreamChunk,
  mapFinishReason,
  mapFinishReasonToProvider,
  toAISDKToolChoice,
  createSimplePrompt,
} from '../../../../src/llm/providers/ai-sdk/adapter';

import type { Message, ToolDefinition } from '../../../../src/llm/providers/types';

describe('toAISDKPrompt', () => {
  it('should convert system message', () => {
    const messages: Message[] = [
      { role: 'system', content: 'You are helpful' }
    ];
    
    const result = toAISDKPrompt(messages);
    
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      role: 'system',
      content: 'You are helpful'
    });
  });

  it('should convert user message', () => {
    const messages: Message[] = [
      { role: 'user', content: 'Hello!' }
    ];
    
    const result = toAISDKPrompt(messages);
    
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      role: 'user',
      content: [{ type: 'text', text: 'Hello!' }]
    });
  });

  it('should convert assistant message with text', () => {
    const messages: Message[] = [
      { role: 'assistant', content: 'Hi there!' }
    ];
    
    const result = toAISDKPrompt(messages);
    
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      role: 'assistant',
      content: [{ type: 'text', text: 'Hi there!' }]
    });
  });

  it('should convert assistant message with tool calls', () => {
    const messages: Message[] = [
      {
        role: 'assistant',
        content: null,
        tool_calls: [{
          id: 'call_123',
          type: 'function',
          function: {
            name: 'get_weather',
            arguments: '{"city": "London"}'
          }
        }]
      }
    ];
    
    const result = toAISDKPrompt(messages);
    
    expect(result).toHaveLength(1);
    expect(result[0].role).toBe('assistant');
    expect((result[0] as any).content).toHaveLength(1);
    expect((result[0] as any).content[0]).toEqual({
      type: 'tool-call',
      toolCallId: 'call_123',
      toolName: 'get_weather',
      args: { city: 'London' }
    });
  });

  it('should convert tool message', () => {
    const messages: Message[] = [
      {
        role: 'tool',
        content: '{"temperature": 20}',
        tool_call_id: 'call_123',
        name: 'get_weather'
      }
    ];
    
    const result = toAISDKPrompt(messages);
    
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      role: 'tool',
      content: [{
        type: 'tool-result',
        toolCallId: 'call_123',
        toolName: 'get_weather',
        result: { temperature: 20 }
      }]
    });
  });

  it('should handle null content', () => {
    const messages: Message[] = [
      { role: 'user', content: null }
    ];
    
    const result = toAISDKPrompt(messages);
    
    expect(result[0]).toEqual({
      role: 'user',
      content: [{ type: 'text', text: '' }]
    });
  });
});

describe('toAISDKTools', () => {
  it('should convert tool definitions', async () => {
    const tools: ToolDefinition[] = [
      {
        name: 'get_weather',
        description: 'Get the weather for a city',
        parameters: {
          type: 'object',
          properties: {
            city: { type: 'string' }
          },
          required: ['city']
        }
      }
    ];
    
    const result = await toAISDKTools(tools);
    
    // Check that tool was created with description
    expect(result.get_weather).toBeDefined();
    expect(result.get_weather.description).toBe('Get the weather for a city');
  });

  it('should handle tools without parameters', async () => {
    const tools: ToolDefinition[] = [
      { name: 'get_time' }
    ];
    
    const result = await toAISDKTools(tools);
    
    expect(result.get_time).toBeDefined();
  });
});

describe('fromAISDKToolCall', () => {
  it('should convert AI SDK tool call to praisonai format', () => {
    const toolCall = {
      toolCallId: 'call_123',
      toolName: 'get_weather',
      args: { city: 'London' }
    };
    
    const result = fromAISDKToolCall(toolCall);
    
    expect(result).toEqual({
      id: 'call_123',
      type: 'function',
      function: {
        name: 'get_weather',
        arguments: '{"city":"London"}'
      }
    });
  });

  it('should handle string args', () => {
    const toolCall = {
      toolCallId: 'call_123',
      toolName: 'test',
      args: '{"key": "value"}'
    };
    
    const result = fromAISDKToolCall(toolCall);
    
    expect(result.function.arguments).toBe('{"key": "value"}');
  });
});

describe('fromAISDKResult', () => {
  it('should convert AI SDK result to praisonai format', () => {
    const result = fromAISDKResult({
      text: 'Hello!',
      usage: { promptTokens: 10, completionTokens: 5 },
      finishReason: 'stop'
    });
    
    expect(result.text).toBe('Hello!');
    expect(result.usage).toEqual({
      promptTokens: 10,
      completionTokens: 5,
      totalTokens: 15
    });
    expect(result.finishReason).toBe('stop');
  });

  it('should handle missing usage', () => {
    const result = fromAISDKResult({
      text: 'Hello!',
      finishReason: 'stop'
    });
    
    expect(result.usage).toEqual({
      promptTokens: 0,
      completionTokens: 0,
      totalTokens: 0
    });
  });

  it('should handle tool calls', () => {
    const result = fromAISDKResult({
      text: '',
      toolCalls: [{
        toolCallId: 'call_123',
        toolName: 'test',
        args: {}
      }],
      finishReason: 'tool_calls'
    });
    
    expect(result.toolCalls).toHaveLength(1);
    expect(result.toolCalls![0].id).toBe('call_123');
    expect(result.finishReason).toBe('tool_calls');
  });
});

describe('mapFinishReason', () => {
  it('should map stop reasons', () => {
    expect(mapFinishReason('stop')).toBe('stop');
    expect(mapFinishReason('end_turn')).toBe('stop');
    expect(mapFinishReason('end')).toBe('stop');
  });

  it('should map length reasons', () => {
    expect(mapFinishReason('length')).toBe('length');
    expect(mapFinishReason('max_tokens')).toBe('length');
  });

  it('should map tool call reasons', () => {
    expect(mapFinishReason('tool_calls')).toBe('tool-calls');
    expect(mapFinishReason('tool-calls')).toBe('tool-calls');
    expect(mapFinishReason('function_call')).toBe('tool-calls');
  });

  it('should map content filter', () => {
    expect(mapFinishReason('content_filter')).toBe('content-filter');
    expect(mapFinishReason('content-filter')).toBe('content-filter');
  });

  it('should return unknown for undefined', () => {
    expect(mapFinishReason(undefined)).toBe('unknown');
    expect(mapFinishReason('something_else')).toBe('unknown');
  });
});

describe('mapFinishReasonToProvider', () => {
  it('should map to provider format with underscores', () => {
    expect(mapFinishReasonToProvider('tool_calls')).toBe('tool_calls');
    expect(mapFinishReasonToProvider('tool-calls')).toBe('tool_calls');
    expect(mapFinishReasonToProvider('content_filter')).toBe('content_filter');
    expect(mapFinishReasonToProvider('content-filter')).toBe('content_filter');
  });

  it('should default to stop for undefined', () => {
    expect(mapFinishReasonToProvider(undefined)).toBe('stop');
  });
});

describe('fromAISDKStreamChunk', () => {
  it('should convert text delta', () => {
    const chunk = fromAISDKStreamChunk({
      type: 'text-delta',
      textDelta: 'Hello'
    });
    
    expect(chunk).toEqual({ type: 'text', text: 'Hello' });
  });

  it('should convert tool call start', () => {
    const chunk = fromAISDKStreamChunk({
      type: 'tool-call-streaming-start',
      toolCallId: 'call_123',
      toolName: 'test'
    });
    
    expect(chunk).toEqual({
      type: 'tool-call-start',
      toolCallId: 'call_123',
      toolName: 'test'
    });
  });

  it('should convert tool call delta', () => {
    const chunk = fromAISDKStreamChunk({
      type: 'tool-call-delta',
      toolCallId: 'call_123',
      argsTextDelta: '{"key":'
    });
    
    expect(chunk).toEqual({
      type: 'tool-call-delta',
      toolCallId: 'call_123',
      argsTextDelta: '{"key":'
    });
  });

  it('should convert finish', () => {
    const chunk = fromAISDKStreamChunk({
      type: 'finish',
      finishReason: 'stop',
      usage: { promptTokens: 10, completionTokens: 5 }
    });
    
    expect(chunk).toEqual({
      type: 'finish',
      finishReason: 'stop',
      usage: {
        promptTokens: 10,
        completionTokens: 5,
        totalTokens: 15
      }
    });
  });

  it('should return null for unknown chunk types', () => {
    const chunk = fromAISDKStreamChunk({
      type: 'unknown-type'
    });
    
    expect(chunk).toBeNull();
  });
});

describe('toAISDKToolChoice', () => {
  it('should pass through string values', () => {
    expect(toAISDKToolChoice('auto')).toBe('auto');
    expect(toAISDKToolChoice('none')).toBe('none');
    expect(toAISDKToolChoice('required')).toBe('required');
  });

  it('should pass through tool object', () => {
    const choice = { type: 'tool' as const, toolName: 'test' };
    expect(toAISDKToolChoice(choice)).toEqual(choice);
  });

  it('should return undefined for undefined', () => {
    expect(toAISDKToolChoice(undefined)).toBeUndefined();
  });
});

describe('createSimplePrompt', () => {
  it('should create prompt with user message', () => {
    const result = createSimplePrompt('Hello!');
    
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      role: 'user',
      content: [{ type: 'text', text: 'Hello!' }]
    });
  });

  it('should include system prompt if provided', () => {
    const result = createSimplePrompt('Hello!', 'You are helpful');
    
    expect(result).toHaveLength(2);
    expect(result[0]).toEqual({
      role: 'system',
      content: 'You are helpful'
    });
    expect(result[1]).toEqual({
      role: 'user',
      content: [{ type: 'text', text: 'Hello!' }]
    });
  });
});
