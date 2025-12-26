/**
 * Voice command - Text-to-speech and speech-to-text
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface VoiceOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  provider?: string;
}

export async function execute(args: string[], options: VoiceOptions): Promise<void> {
  const action = args[0] || 'help';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'providers':
        await listProviders(outputFormat);
        break;
      case 'info':
        await showInfo(outputFormat);
        break;
      case 'help':
      default:
        await showHelp(outputFormat);
        break;
    }
  } catch (error) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, error instanceof Error ? error.message : String(error)));
    } else {
      await pretty.error(error instanceof Error ? error.message : String(error));
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }
}

async function showInfo(outputFormat: string): Promise<void> {
  const info = {
    feature: 'Voice',
    description: 'Text-to-speech and speech-to-text capabilities',
    providers: [
      { name: 'OpenAIVoiceProvider', description: 'OpenAI TTS and Whisper' },
      { name: 'ElevenLabsVoiceProvider', description: 'ElevenLabs voice synthesis' }
    ],
    capabilities: [
      'Text-to-speech conversion',
      'Speech-to-text transcription',
      'Multiple voice options',
      'Streaming audio support'
    ],
    sdkUsage: `
import { createOpenAIVoice, createElevenLabsVoice } from 'praisonai';

// Create OpenAI voice provider
const voice = createOpenAIVoice({ apiKey: process.env.OPENAI_API_KEY });

// Text to speech
const audio = await voice.speak({ text: 'Hello world', voice: 'alloy' });

// Speech to text
const text = await voice.listen({ audio: audioBuffer });
`
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(info));
  } else {
    await pretty.heading('Voice');
    await pretty.plain(info.description);
    await pretty.newline();
    await pretty.plain('Providers:');
    for (const p of info.providers) {
      await pretty.plain(`  • ${p.name}: ${p.description}`);
    }
    await pretty.newline();
    await pretty.plain('Capabilities:');
    for (const cap of info.capabilities) {
      await pretty.plain(`  • ${cap}`);
    }
  }
}

async function listProviders(outputFormat: string): Promise<void> {
  const providers = [
    { name: 'openai', description: 'OpenAI TTS and Whisper', available: true },
    { name: 'elevenlabs', description: 'ElevenLabs voice synthesis', available: true }
  ];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ providers }));
  } else {
    await pretty.heading('Voice Providers');
    for (const p of providers) {
      const status = p.available ? '✓' : '✗';
      await pretty.plain(`  ${status} ${p.name.padEnd(15)} ${p.description}`);
    }
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'voice',
    description: 'Text-to-speech and speech-to-text capabilities',
    subcommands: [
      { name: 'info', description: 'Show voice feature information' },
      { name: 'providers', description: 'List available voice providers' },
      { name: 'help', description: 'Show this help' }
    ],
    flags: [
      { name: '--provider', description: 'Voice provider (openai, elevenlabs)' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Voice Command');
    await pretty.plain(help.description);
    await pretty.newline();
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(20)} ${cmd.description}`);
    }
    await pretty.newline();
    await pretty.plain('Flags:');
    for (const flag of help.flags) {
      await pretty.plain(`  ${flag.name.padEnd(20)} ${flag.description}`);
    }
  }
}
