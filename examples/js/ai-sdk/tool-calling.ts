/**
 * AI SDK Tool Calling Example
 * 
 * Demonstrates function/tool calling with Zod schemas.
 * 
 * Usage:
 *   npx ts-node tool-calling.ts
 * 
 * Environment:
 *   OPENAI_API_KEY - Your OpenAI API key
 */

import { generateText, tool } from 'ai';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';

// Define tools with Zod schemas
const tools = {
  get_weather: tool({
    description: 'Get the current weather for a city',
    inputSchema: z.object({
      city: z.string().describe('The city name'),
      unit: z.enum(['celsius', 'fahrenheit']).optional().describe('Temperature unit'),
    }),
    execute: async ({ city, unit = 'celsius' }) => {
      // Mock weather data
      const weather = {
        city,
        temperature: unit === 'celsius' ? 22 : 72,
        unit,
        condition: 'sunny',
        humidity: 45,
      };
      return weather;
    },
  }),
  
  get_time: tool({
    description: 'Get the current time in a timezone',
    inputSchema: z.object({
      timezone: z.string().describe('Timezone like "America/New_York"'),
    }),
    execute: async ({ timezone }) => {
      const time = new Date().toLocaleString('en-US', { timeZone: timezone });
      return { timezone, time };
    },
  }),
};

async function main() {
  console.log('Asking about weather with tool calling...\n');

  const result = await generateText({
    model: openai('gpt-4o-mini'),
    messages: [
      { role: 'user', content: 'What is the weather in Paris and what time is it in New York?' }
    ],
    tools,
    maxSteps: 5, // Allow multiple tool calls
  });

  console.log('Tool Calls:');
  for (const toolCall of result.toolCalls) {
    console.log(`  - ${toolCall.toolName}:`, toolCall.args);
  }

  console.log('\nTool Results:');
  for (const toolResult of result.toolResults) {
    console.log(`  - ${toolResult.toolName}:`, toolResult.result);
  }

  console.log('\nFinal Response:', result.text);
}

main().catch(console.error);
