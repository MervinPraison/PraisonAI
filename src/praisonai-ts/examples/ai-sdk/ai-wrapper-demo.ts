/**
 * AI SDK Wrapper Demo
 * 
 * Demonstrates the new AI SDK wrapper functions in praisonai-ts.
 * These wrappers provide a stable interface over the AI SDK primitives.
 */

import {
  // Core text generation
  aiGenerateText,
  aiStreamText,
  // Object generation
  aiGenerateObject,
  // Image generation
  aiGenerateImage,
  // Embeddings
  aiEmbed,
  // Tools
  defineTool,
  createToolSet,
  // Models
  getModel,
  MODEL_ALIASES,
  // Middleware
  createCachingMiddleware,
  // Multimodal
  createImagePart,
  createMultimodalMessage,
  // MCP
  createMCP,
  // Server adapters
  createExpressHandler,
  // Next.js
  createRouteHandler,
  // Agent loop
  createAgentLoop,
  stopWhenNoToolCalls,
} from '../../src';

// Also import the Agent class for comparison
import { Agent } from '../../src';

async function main() {
  console.log('=== PraisonAI TypeScript - AI SDK Wrapper Demo ===\n');

  // -------------------------------------------------------------------------
  // 1. Simple Text Generation
  // -------------------------------------------------------------------------
  console.log('1. Simple Text Generation');
  console.log('-------------------------');
  
  try {
    const result = await aiGenerateText({
      model: 'gpt-4o-mini',
      prompt: 'What is 2 + 2? Answer in one word.',
    });
    console.log('Result:', result.text);
    console.log('Usage:', result.usage);
  } catch (error: any) {
    console.log('Skipped (AI SDK not installed):', error.message);
  }

  // -------------------------------------------------------------------------
  // 2. Streaming Text Generation
  // -------------------------------------------------------------------------
  console.log('\n2. Streaming Text Generation');
  console.log('----------------------------');
  
  try {
    const stream = await aiStreamText({
      model: 'gpt-4o-mini',
      prompt: 'Count from 1 to 5.',
    });
    
    process.stdout.write('Streaming: ');
    for await (const chunk of stream.textStream) {
      process.stdout.write(chunk);
    }
    console.log('\n');
  } catch (error: any) {
    console.log('Skipped (AI SDK not installed):', error.message);
  }

  // -------------------------------------------------------------------------
  // 3. Structured Object Generation
  // -------------------------------------------------------------------------
  console.log('3. Structured Object Generation');
  console.log('-------------------------------');
  
  try {
    // Using a simple JSON schema (Zod would be better in production)
    const result = await aiGenerateObject({
      model: 'gpt-4o-mini',
      schema: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          age: { type: 'number' },
          city: { type: 'string' },
        },
        required: ['name', 'age', 'city'],
      },
      prompt: 'Generate a fictional person.',
    });
    console.log('Generated object:', result.object);
  } catch (error: any) {
    console.log('Skipped (AI SDK not installed):', error.message);
  }

  // -------------------------------------------------------------------------
  // 4. Tool Definition
  // -------------------------------------------------------------------------
  console.log('\n4. Tool Definition');
  console.log('------------------');
  
  const weatherTool = defineTool({
    description: 'Get weather for a city',
    parameters: {
      type: 'object',
      properties: {
        city: { type: 'string', description: 'City name' },
      },
      required: ['city'],
    },
    execute: async ({ city }) => {
      return { temperature: 20, unit: 'celsius', city };
    },
  });
  
  console.log('Weather tool defined:', weatherTool.description);

  // -------------------------------------------------------------------------
  // 5. Tool Set Creation
  // -------------------------------------------------------------------------
  console.log('\n5. Tool Set Creation');
  console.log('--------------------');
  
  const tools = createToolSet({
    weather: weatherTool,
    calculator: defineTool({
      description: 'Perform calculations',
      parameters: {
        type: 'object',
        properties: {
          expression: { type: 'string' },
        },
        required: ['expression'],
      },
      execute: async ({ expression }) => {
        return { result: eval(expression) };
      },
    }),
  });
  
  console.log('Tools created:', Object.keys(tools));

  // -------------------------------------------------------------------------
  // 6. Model Aliases
  // -------------------------------------------------------------------------
  console.log('\n6. Model Aliases');
  console.log('----------------');
  console.log('Available aliases:', Object.keys(MODEL_ALIASES).slice(0, 10), '...');

  // -------------------------------------------------------------------------
  // 7. Multimodal Message Creation
  // -------------------------------------------------------------------------
  console.log('\n7. Multimodal Message Creation');
  console.log('------------------------------');
  
  const imagePart = createImagePart('https://example.com/image.png');
  console.log('Image part type:', imagePart.type);
  
  const multimodalMsg = createMultimodalMessage(
    'What is in this image?',
    ['https://example.com/image.png']
  );
  console.log('Multimodal message role:', multimodalMsg.role);
  console.log('Content parts:', multimodalMsg.content.length);

  // -------------------------------------------------------------------------
  // 8. Agent Loop (Manual Control)
  // -------------------------------------------------------------------------
  console.log('\n8. Agent Loop (Manual Control)');
  console.log('------------------------------');
  
  const loop = createAgentLoop({
    model: 'gpt-4o-mini',
    system: 'You are a helpful assistant.',
    tools: {
      greet: defineTool({
        description: 'Greet someone',
        parameters: {
          type: 'object',
          properties: { name: { type: 'string' } },
          required: ['name'],
        },
        execute: async ({ name }) => `Hello, ${name}!`,
      }),
    },
    maxSteps: 3,
    stopWhen: stopWhenNoToolCalls(),
  });
  
  console.log('Agent loop created with max 3 steps');
  console.log('Stop condition: when no tool calls');

  // -------------------------------------------------------------------------
  // 9. Server Handler Creation
  // -------------------------------------------------------------------------
  console.log('\n9. Server Handler Creation');
  console.log('--------------------------');
  
  const expressHandler = createExpressHandler({
    handler: async (input) => {
      return { text: `Echo: ${input.message}` };
    },
    streaming: false,
    cors: true,
  });
  console.log('Express handler created');

  // -------------------------------------------------------------------------
  // 10. Next.js Route Handler
  // -------------------------------------------------------------------------
  console.log('\n10. Next.js Route Handler');
  console.log('-------------------------');
  
  const routeHandler = createRouteHandler({
    handler: async (input) => {
      return { text: `Response: ${input.prompt}` };
    },
    streaming: true,
  });
  console.log('Next.js route handler created');

  // -------------------------------------------------------------------------
  // 11. Comparison with Agent Class
  // -------------------------------------------------------------------------
  console.log('\n11. Comparison with Agent Class');
  console.log('-------------------------------');
  console.log('The Agent class provides a higher-level abstraction:');
  console.log('- Automatic tool calling');
  console.log('- Session persistence');
  console.log('- Multi-agent orchestration');
  console.log('');
  console.log('The AI SDK wrappers provide lower-level control:');
  console.log('- Direct access to generateText/streamText');
  console.log('- Manual agent loops');
  console.log('- Server adapters for various frameworks');

  // -------------------------------------------------------------------------
  // Summary
  // -------------------------------------------------------------------------
  console.log('\n=== Summary ===');
  console.log('New AI SDK wrapper exports:');
  console.log('- aiGenerateText, aiStreamText');
  console.log('- aiGenerateObject, aiStreamObject');
  console.log('- aiGenerateImage');
  console.log('- aiEmbed, aiEmbedMany');
  console.log('- defineTool, createToolSet');
  console.log('- createAgentLoop');
  console.log('- createHttpHandler, createExpressHandler, createHonoHandler, createFastifyHandler, createNestHandler');
  console.log('- createRouteHandler (Next.js)');
  console.log('- createMCP (MCP client)');
  console.log('- createSlackBot, createNLPostgres, createComputerUse (integrations)');
}

main().catch(console.error);
