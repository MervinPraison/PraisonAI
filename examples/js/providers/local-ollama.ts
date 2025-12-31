/**
 * Local Ollama Provider Example
 * 
 * Demonstrates using local Ollama models with PraisonAI.
 * 
 * Setup:
 * 1. Install Ollama: https://ollama.ai
 * 2. Pull a model: ollama pull llama3.2
 * 3. Run this example
 * 
 * Optional env var:
 * - OLLAMA_BASE_URL (default: http://localhost:11434)
 */

import { Agent } from 'praisonai';

async function main() {
  // Ollama with llama3.2
  const ollamaAgent = new Agent({
    name: 'LocalLlama',
    instructions: 'You are a helpful local AI assistant running on Ollama.',
    llm: 'ollama/llama3.2',
    llmConfig: {
      baseUrl: process.env.OLLAMA_BASE_URL || 'http://localhost:11434'
    }
  });

  console.log('Testing Ollama local model...\n');

  try {
    const response = await ollamaAgent.chat('Hello! What model are you running?');
    console.log('Response:', response);
  } catch (error: any) {
    console.log('Note: Ollama not running or model not pulled.');
    console.log('Start Ollama and run: ollama pull llama3.2');
    console.log('Error:', error.message);
  }
}

main().catch(console.error);
