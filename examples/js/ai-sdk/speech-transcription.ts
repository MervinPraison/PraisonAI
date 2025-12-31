/**
 * Speech & Transcription Example (AI SDK v6 Parity)
 * 
 * Demonstrates speech generation and transcription wrappers.
 * 
 * Run: npx ts-node speech-transcription.ts
 * Required: OPENAI_API_KEY or ELEVENLABS_API_KEY
 */

import { 
  generateSpeech,
  transcribe,
  SPEECH_MODELS,
  TRANSCRIPTION_MODELS,
} from '../../../src/praisonai-ts/src';

async function main() {
  console.log('=== Speech & Transcription Example ===\n');

  // Show available models
  console.log('1. Available Speech Models:');
  Object.entries(SPEECH_MODELS).forEach(([key, value]) => {
    console.log(`   ${key}: ${value}`);
  });

  console.log('\n2. Available Transcription Models:');
  Object.entries(TRANSCRIPTION_MODELS).forEach(([key, value]) => {
    console.log(`   ${key}: ${value}`);
  });

  // Example: Generate speech (requires API key)
  console.log('\n3. Speech Generation Example:');
  console.log(`
// Generate speech from text
const result = await generateSpeech({
  text: 'Hello, this is a test of speech synthesis.',
  model: 'openai/tts-1',
  voice: 'alloy',
});

// Save to file
await fs.writeFile('output.mp3', result.audio);
console.log('Audio saved to output.mp3');
`);

  // Example: Transcribe audio (requires API key)
  console.log('4. Transcription Example:');
  console.log(`
// Transcribe audio file
const result = await transcribe({
  audio: await fs.readFile('audio.mp3'),
  model: 'openai/whisper-1',
});

console.log('Transcription:', result.text);
console.log('Language:', result.language);
console.log('Duration:', result.durationInSeconds, 'seconds');

// With segments
if (result.segments) {
  result.segments.forEach(seg => {
    console.log(\`[\${seg.start}s - \${seg.end}s]: \${seg.text}\`);
  });
}
`);

  // Live test if API key is available
  if (process.env.OPENAI_API_KEY) {
    console.log('\n5. Live Speech Generation Test:');
    try {
      const result = await generateSpeech({
        text: 'Hello from PraisonAI!',
        model: 'openai/tts-1',
        voice: 'alloy',
      });
      console.log(`   ✅ Generated ${result.audio.length} bytes of audio`);
    } catch (error: any) {
      console.log(`   ⚠️ Speech generation failed: ${error.message}`);
    }
  } else {
    console.log('\n5. Live Test: Skipped (OPENAI_API_KEY not set)');
  }

  console.log('\n✅ Speech & Transcription demo completed!');
}

main().catch(console.error);
