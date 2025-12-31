/**
 * OpenAI-Compatible Provider Example
 * 
 * Demonstrates using any OpenAI-compatible API endpoint.
 * Works with LM Studio, vLLM, LocalAI, and other compatible servers.
 * 
 * Required env vars:
 * - OPENAI_COMPATIBLE_BASE_URL (e.g., http://localhost:1234/v1)
 * - OPENAI_COMPATIBLE_API_KEY (optional, use 'not-needed' for local)
 */

import { Agent } from 'praisonai';

async function main() {
  // LM Studio example (local)
  const lmStudioAgent = new Agent({
    name: 'LocalAssistant',
    instructions: 'You are a helpful local AI assistant.',
    llm: 'openai-compatible/local-model',
    llmConfig: {
      baseUrl: process.env.LM_STUDIO_BASE_URL || 'http://localhost:1234/v1',
      apiKey: 'not-needed'
    }
  });

  // Custom OpenAI-compatible endpoint
  const customAgent = new Agent({
    name: 'CustomAssistant',
    instructions: 'You are a helpful assistant.',
    llm: 'openai-compatible/my-model',
    llmConfig: {
      baseUrl: process.env.OPENAI_COMPATIBLE_BASE_URL || 'http://localhost:8000/v1',
      apiKey: process.env.OPENAI_COMPATIBLE_API_KEY || 'not-needed'
    }
  });

  console.log('Testing OpenAI-compatible endpoint...\n');

  try {
    const response = await lmStudioAgent.chat('Hello! What model are you?');
    console.log('Response:', response);
  } catch (error: any) {
    console.log('Note: LM Studio not running. Start it with a model loaded.');
    console.log('Error:', error.message);
  }
}

main().catch(console.error);
