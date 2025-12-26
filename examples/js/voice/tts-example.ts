/**
 * Voice/TTS Example
 */

import { createOpenAIVoice } from '../../../src/praisonai-ts/src';
import { writeFileSync } from 'fs';

async function main() {
  const voice = createOpenAIVoice({
    apiKey: process.env.OPENAI_API_KEY
  });

  // Check available voices
  const speakers = await voice.getSpeakers();
  console.log('Available voices:', speakers.map(s => s.name).join(', '));

  // Generate speech
  console.log('Generating speech...');
  const audio = await voice.speak('Hello! Welcome to PraisonAI TypeScript SDK.', {
    voice: 'nova',
    speed: 1.0,
    format: 'mp3'
  });

  // Save to file
  writeFileSync('output.mp3', audio);
  console.log('Audio saved to output.mp3');
}

main().catch(console.error);
