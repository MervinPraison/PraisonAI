/**
 * AudioAgent Integration Test
 * 
 * Tests the AudioAgent for TTS and STT using AI SDK.
 * Requires OPENAI_API_KEY for live tests.
 * 
 * Run: npx ts-node audio-agent.ts
 */

import { AudioAgent, createAudioAgent } from '../../../src/praisonai-ts/dist';
import * as fs from 'fs';
import * as path from 'path';

async function main() {
    console.log('=== AudioAgent Integration Test ===\n');

    // Test 1: Create AudioAgent with defaults
    console.log('1. Testing AudioAgent creation:');
    const agent = new AudioAgent({
        name: 'TestAudioAgent',
        provider: 'openai',
        voice: 'alloy',
        verbose: true
    });
    console.log('   Agent ID:', agent.id);
    console.log('   Agent Name:', agent.name);
    console.log('   Success: ✅');

    // Test 2: Factory function
    console.log('\n2. Testing createAudioAgent() factory:');
    const agent2 = createAudioAgent({ provider: 'openai', voice: 'nova' });
    console.log('   Agent created:', typeof agent2);
    console.log('   Success: ✅');

    // Test 3: Live TTS (requires API key)
    if (process.env.OPENAI_API_KEY) {
        console.log('\n3. Testing Text-to-Speech (live API):');
        try {
            const ttsAgent = new AudioAgent({
                provider: 'openai',
                voice: 'alloy',
                verbose: false
            });

            const result = await ttsAgent.speak('Hello from PraisonAI AudioAgent!');
            console.log('   Audio format:', result.format);
            console.log('   Audio size:', result.audio.byteLength || result.audio.length, 'bytes');

            // Optionally save to file
            const outputPath = path.join(__dirname, 'test-output.mp3');
            if (result.audio instanceof Buffer) {
                fs.writeFileSync(outputPath, result.audio);
                console.log('   Saved to:', outputPath);
            }
            console.log('   Success: ✅');
        } catch (error: any) {
            console.log('   ⚠️ TTS failed:', error.message);
        }

        // Test 4: Live Transcription (requires audio file)
        console.log('\n4. Testing Speech-to-Text (live API):');
        try {
            const sttAgent = new AudioAgent({
                provider: 'openai',
                verbose: false
            });

            // Check if we have the test output from TTS
            const audioPath = path.join(__dirname, 'test-output.mp3');
            if (fs.existsSync(audioPath)) {
                const result = await sttAgent.transcribe(audioPath);
                console.log('   Transcribed text:', result.text);
                console.log('   Language:', result.language || 'auto-detected');
                console.log('   Success: ✅');

                // Cleanup
                fs.unlinkSync(audioPath);
                console.log('   Cleaned up test file');
            } else {
                console.log('   Skipped (no test audio file available)');
            }
        } catch (error: any) {
            console.log('   ⚠️ STT failed:', error.message);
        }

        // Test 5: Chat method (auto-detect mode)
        console.log('\n5. Testing chat() method:');
        try {
            const chatAgent = new AudioAgent({ provider: 'openai', voice: 'echo' });

            // Text input -> TTS
            const chatResult = await chatAgent.chat('Testing audio chat interface');
            console.log('   Chat result:', chatResult);
            console.log('   Success: ✅');
        } catch (error: any) {
            console.log('   ⚠️ Chat failed:', error.message);
        }

    } else {
        console.log('\n3-5. Live API Tests: Skipped (OPENAI_API_KEY not set)');
        console.log('   Set OPENAI_API_KEY to run live tests');
    }

    // Test 6: Different providers (just creation, no live calls)
    console.log('\n6. Testing provider configurations:');
    const providers = ['openai', 'elevenlabs', 'groq', 'deepgram'] as const;

    for (const provider of providers) {
        try {
            const a = new AudioAgent({ provider });
            console.log(`   ${provider}: ✅ (created)`);
        } catch (error: any) {
            console.log(`   ${provider}: ⚠️ ${error.message}`);
        }
    }

    // Test 7: Voice options
    console.log('\n7. Testing OpenAI voice options:');
    const voices = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'];
    for (const voice of voices) {
        const a = new AudioAgent({ provider: 'openai', voice });
        console.log(`   ${voice}: ✅`);
    }

    console.log('\n=== AudioAgent Tests Complete ===');
}

main().catch(console.error);
