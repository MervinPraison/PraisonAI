/**
 * Multimodal Image Analysis Example
 * 
 * Demonstrates analyzing images with a vision-capable model.
 * 
 * Prerequisites:
 *   npm install praisonai-ts
 *   export OPENAI_API_KEY=your-api-key
 * 
 * Run:
 *   npx ts-node image-analysis.ts
 */

import { Agent } from '../../../src/praisonai-ts/src';

async function main() {
  console.log('=== Multimodal Image Analysis Example ===\n');

  // Create an agent with a vision-capable model
  const agent = new Agent({
    name: 'VisionAgent',
    llm: 'gpt-4o', // Vision-capable model
    instructions: 'You analyze images and describe what you see in detail.',
  });

  // For multimodal, we describe the image in the prompt
  // The agent will use its vision capabilities
  const imageUrl = 'https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/300px-PNG_transparency_demonstration_1.png';
  
  console.log('Analyzing image...\n');
  console.log('Image URL:', imageUrl, '\n');
  
  // Ask the agent to analyze (in production, use multimodal message format)
  const response = await agent.chat(
    `Please analyze this image: ${imageUrl}\nDescribe what you see in detail.`
  );
  
  console.log('Analysis:', response);
}

main().catch(console.error);
