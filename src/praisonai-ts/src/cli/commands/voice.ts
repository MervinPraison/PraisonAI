/**
 * Voice command - Text-to-speech and speech-to-text with full operations
 */

import * as fs from 'fs';
import * as path from 'path';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface VoiceOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  voice?: string;
  model?: string;
  file?: string;
}

export async function execute(args: string[], options: VoiceOptions): Promise<void> {
  const action = args[0] || 'help';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'speak':
        await speakText(actionArgs, options, outputFormat);
        break;
      case 'transcribe':
        await transcribeAudio(actionArgs, options, outputFormat);
        break;
      case 'voices':
        await listVoices(outputFormat);
        break;
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

async function speakText(args: string[], options: VoiceOptions, outputFormat: string): Promise<void> {
  const text = args.join(' ');

  if (!text) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Usage: voice speak <text>'));
    } else {
      await pretty.error('Usage: voice speak <text>');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const voice = options.voice || 'alloy';
  const outputFile = options.file || `speech_${Date.now()}.mp3`;

  if (outputFormat !== 'json') {
    await pretty.info(`Generating speech with voice: ${voice}`);
  }

  try {
    const OpenAI = (await import('openai')).default;
    const client = new OpenAI();

    const response = await client.audio.speech.create({
      model: 'tts-1',
      voice: voice as any,
      input: text,
    });

    const buffer = Buffer.from(await response.arrayBuffer());
    fs.writeFileSync(outputFile, buffer);

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        text,
        voice,
        file: outputFile,
        size: buffer.length
      }));
    } else {
      await pretty.success(`Speech saved to: ${outputFile}`);
      await pretty.dim(`Size: ${buffer.length} bytes`);
    }
  } catch (error: any) {
    if (error.code === 'MODULE_NOT_FOUND' || error.message?.includes('Cannot find module')) {
      throw new Error('Voice features require the OpenAI SDK. Run: npm install openai');
    }
    throw error;
  }
}

async function transcribeAudio(args: string[], options: VoiceOptions, outputFormat: string): Promise<void> {
  const audioFile = args[0];

  if (!audioFile) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Usage: voice transcribe <audio-file>'));
    } else {
      await pretty.error('Usage: voice transcribe <audio-file>');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  if (!fs.existsSync(audioFile)) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, `File not found: ${audioFile}`));
    } else {
      await pretty.error(`File not found: ${audioFile}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }

  if (outputFormat !== 'json') {
    await pretty.info(`Transcribing: ${audioFile}`);
  }

  try {
    const OpenAI = (await import('openai')).default;
    const client = new OpenAI();

    const file = fs.createReadStream(audioFile);
    const response = await client.audio.transcriptions.create({
      model: 'whisper-1',
      file: file as any,
    });

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        file: audioFile,
        text: response.text
      }));
    } else {
      await pretty.heading('Transcription');
      await pretty.plain(response.text);
    }
  } catch (error: any) {
    if (error.code === 'MODULE_NOT_FOUND' || error.message?.includes('Cannot find module')) {
      throw new Error('Voice features require the OpenAI SDK. Run: npm install openai');
    }
    throw error;
  }
}

async function listVoices(outputFormat: string): Promise<void> {
  const voices = [
    { id: 'alloy', description: 'Neutral and balanced' },
    { id: 'echo', description: 'Warm and engaging' },
    { id: 'fable', description: 'Expressive and dynamic' },
    { id: 'onyx', description: 'Deep and authoritative' },
    { id: 'nova', description: 'Friendly and bright' },
    { id: 'shimmer', description: 'Clear and optimistic' }
  ];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ voices }));
  } else {
    await pretty.heading('Available Voices');
    for (const v of voices) {
      await pretty.plain(`  • ${v.id.padEnd(12)} ${v.description}`);
    }
  }
}

async function showInfo(outputFormat: string): Promise<void> {
  const info = {
    feature: 'Voice',
    description: 'Text-to-speech and speech-to-text using OpenAI',
    models: {
      tts: 'tts-1 (Text-to-Speech)',
      stt: 'whisper-1 (Speech-to-Text)'
    },
    capabilities: [
      'Generate speech from text',
      'Transcribe audio files',
      '6 voice options',
      'MP3 output format'
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(info));
  } else {
    await pretty.heading('Voice');
    await pretty.plain(info.description);
    await pretty.newline();
    await pretty.plain('Models:');
    await pretty.dim(`  TTS: ${info.models.tts}`);
    await pretty.dim(`  STT: ${info.models.stt}`);
  }
}

async function listProviders(outputFormat: string): Promise<void> {
  const providers = [
    { name: 'openai', description: 'OpenAI TTS and Whisper', available: true }
  ];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ providers }));
  } else {
    await pretty.heading('Voice Providers');
    for (const p of providers) {
      await pretty.plain(`  ✓ ${p.name.padEnd(15)} ${p.description}`);
    }
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'voice',
    description: 'Text-to-speech and speech-to-text',
    subcommands: [
      { name: 'speak <text>', description: 'Convert text to speech' },
      { name: 'transcribe <file>', description: 'Transcribe audio to text' },
      { name: 'voices', description: 'List available voices' },
      { name: 'providers', description: 'List voice providers' },
      { name: 'help', description: 'Show this help' }
    ],
    flags: [
      { name: '--voice <name>', description: 'Voice to use (alloy, echo, fable, onyx, nova, shimmer)' },
      { name: '--file <path>', description: 'Output file path for speech' }
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
      await pretty.plain(`  ${cmd.name.padEnd(25)} ${cmd.description}`);
    }
    await pretty.newline();
    await pretty.plain('Flags:');
    for (const flag of help.flags) {
      await pretty.plain(`  ${flag.name.padEnd(20)} ${flag.description}`);
    }
    await pretty.newline();
    await pretty.dim('Examples:');
    await pretty.dim('  praisonai-ts voice speak "Hello World" --voice nova');
    await pretty.dim('  praisonai-ts voice transcribe audio.mp3');
    await pretty.dim('  praisonai-ts voice voices');
  }
}
