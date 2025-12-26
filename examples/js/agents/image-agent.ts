/**
 * Image Agent Example
 * Demonstrates image analysis capabilities
 */

import { ImageAgent, createImageAgent } from 'praisonai';

async function main() {
  const agent = createImageAgent({
    name: 'VisionAgent',
    llm: 'openai/gpt-4o-mini',
    verbose: true
  });

  console.log('Image Agent created:', agent.name);

  // Note: For actual image analysis, provide a real image URL
  // const analysis = await agent.analyze({
  //   imageUrl: 'https://example.com/image.jpg',
  //   prompt: 'Describe this image in detail'
  // });
  // console.log('Analysis:', analysis);

  // Chat without image
  const response = await agent.chat('What types of images can you analyze?');
  console.log('Response:', response);
}

main().catch(console.error);
