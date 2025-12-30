/**
 * AI SDK Tool Calling Example
 * 
 * Demonstrates tool calling using the AI SDK backend.
 * 
 * Usage:
 *   npx ts-node examples/ai-sdk/tool-calling.ts
 * 
 * Required environment variables:
 *   OPENAI_API_KEY - Your OpenAI API key
 */

import { createAISDKBackend } from '../../src/llm/providers/ai-sdk';
import type { ToolDefinition, Message } from '../../src/llm/providers/types';

// Define tools
const tools: ToolDefinition[] = [
  {
    name: 'get_weather',
    description: 'Get the current weather for a location',
    parameters: {
      type: 'object',
      properties: {
        location: {
          type: 'string',
          description: 'The city and country, e.g., "London, UK"'
        },
        unit: {
          type: 'string',
          enum: ['celsius', 'fahrenheit'],
          description: 'Temperature unit'
        }
      },
      required: ['location']
    }
  },
  {
    name: 'get_time',
    description: 'Get the current time for a timezone',
    parameters: {
      type: 'object',
      properties: {
        timezone: {
          type: 'string',
          description: 'The timezone, e.g., "America/New_York"'
        }
      },
      required: ['timezone']
    }
  }
];

// Mock tool execution
function executeTool(name: string, args: Record<string, unknown>): string {
  switch (name) {
    case 'get_weather':
      return JSON.stringify({
        location: args.location,
        temperature: 22,
        unit: args.unit || 'celsius',
        condition: 'Partly cloudy'
      });
    case 'get_time':
      return JSON.stringify({
        timezone: args.timezone,
        time: new Date().toLocaleTimeString('en-US', { 
          timeZone: args.timezone as string 
        })
      });
    default:
      return JSON.stringify({ error: 'Unknown tool' });
  }
}

async function main() {
  console.log('AI SDK Tool Calling Example\n');

  const backend = createAISDKBackend('openai/gpt-4o-mini', {
    timeout: 30000,
  });

  console.log(`Provider: ${backend.providerId}`);
  console.log(`Model: ${backend.modelId}\n`);

  // Initial conversation
  const messages: Message[] = [
    { role: 'system', content: 'You are a helpful assistant with access to weather and time tools.' },
    { role: 'user', content: 'What is the weather in London and what time is it in New York?' }
  ];

  console.log('User:', messages[1].content);
  console.log('\n--- First LLM Call ---\n');

  // First call - model should request tool calls
  let result = await backend.generateText({
    messages,
    tools,
    toolChoice: 'auto',
  });

  console.log('Finish Reason:', result.finishReason);

  // Handle tool calls
  if (result.toolCalls && result.toolCalls.length > 0) {
    console.log(`\nTool Calls: ${result.toolCalls.length}`);
    
    // Add assistant message with tool calls
    messages.push({
      role: 'assistant',
      content: null,
      tool_calls: result.toolCalls
    });

    // Execute each tool and add results
    for (const toolCall of result.toolCalls) {
      const args = JSON.parse(toolCall.function.arguments);
      console.log(`\n  Executing: ${toolCall.function.name}`);
      console.log(`  Arguments: ${JSON.stringify(args)}`);
      
      const toolResult = executeTool(toolCall.function.name, args);
      console.log(`  Result: ${toolResult}`);
      
      messages.push({
        role: 'tool',
        content: toolResult,
        tool_call_id: toolCall.id,
        name: toolCall.function.name
      });
    }

    console.log('\n--- Second LLM Call (with tool results) ---\n');

    // Second call with tool results
    result = await backend.generateText({
      messages,
      tools,
    });
  }

  console.log('Final Response:', result.text);
  console.log('\nUsage:', result.usage);
}

main().catch(console.error);
