/**
 * AudioAgent - Speech synthesis and transcription agent
 * 
 * Wraps AI SDK's generateSpeech and transcribe functions for
 * text-to-speech and speech-to-text capabilities.
 * 
 * Requires AI SDK: npm install ai @ai-sdk/openai
 * 
 * @example Text-to-Speech
 * ```typescript
 * import { AudioAgent } from 'praisonai';
 * 
 * const agent = new AudioAgent({
 *   provider: 'openai',
 *   voice: 'alloy'
 * });
 * 
 * const audio = await agent.speak('Hello, world!');
 * // Returns audio buffer
 * ```
 * 
 * @example Speech-to-Text
 * ```typescript
 * const agent = new AudioAgent({ provider: 'openai' });
 * 
 * const text = await agent.transcribe('./audio.mp3');
 * console.log(text); // "Hello, world!"
 * ```
 */

import { randomUUID } from 'crypto';

/**
 * Supported audio providers
 */
export type AudioProvider = 'openai' | 'elevenlabs' | 'google' | 'deepgram' | 'groq';

/**
 * Voice options by provider
 */
export type OpenAIVoice = 'alloy' | 'echo' | 'fable' | 'onyx' | 'nova' | 'shimmer';
export type ElevenLabsVoice = string; // Voice ID from ElevenLabs

/**
 * Audio format options
 */
export type AudioFormat = 'mp3' | 'opus' | 'aac' | 'flac' | 'wav' | 'pcm';

/**
 * Configuration for AudioAgent
 */
export interface AudioAgentConfig {
    /** Name of the agent */
    name?: string;
    /** Audio provider (default: 'openai') */
    provider?: AudioProvider;
    /** Voice to use for TTS */
    voice?: string;
    /** TTS model to use (provider-specific) */
    model?: string;
    /** Audio output format */
    format?: AudioFormat;
    /** Speed multiplier for TTS (0.25 to 4.0) */
    speed?: number;
    /** Language for transcription */
    language?: string;
    /** Enable verbose logging */
    verbose?: boolean;
}

/**
 * Options for speak method
 */
export interface SpeakOptions {
    /** Override voice for this call */
    voice?: string;
    /** Override model for this call */
    model?: string;
    /** Override format for this call */
    format?: AudioFormat;
    /** Override speed for this call */
    speed?: number;
}

/**
 * Options for transcribe method
 */
export interface TranscribeOptions {
    /** Language hint for transcription */
    language?: string;
    /** Include word-level timestamps */
    timestamps?: boolean;
    /** Return detailed segments */
    segments?: boolean;
}

/**
 * Result from speak method
 */
export interface SpeakResult {
    /** Audio data as Buffer or ArrayBuffer */
    audio: Buffer | ArrayBuffer;
    /** Duration in seconds (if available) */
    duration?: number;
    /** Audio format */
    format: string;
}

/**
 * Result from transcribe method
 */
export interface TranscribeResult {
    /** Transcribed text */
    text: string;
    /** Detected language */
    language?: string;
    /** Duration in seconds */
    duration?: number;
    /** Word-level timestamps (if requested) */
    words?: Array<{ word: string; start: number; end: number }>;
    /** Segments (if requested) */
    segments?: Array<{ text: string; start: number; end: number }>;
}

/**
 * AudioAgent - Speech synthesis and transcription
 */
export class AudioAgent {
    readonly id: string;
    readonly name: string;
    private config: Required<Omit<AudioAgentConfig, 'name'>>;

    constructor(config: AudioAgentConfig = {}) {
        this.id = randomUUID();
        this.name = config.name ?? `AudioAgent_${randomUUID().slice(0, 8)}`;
        this.config = {
            provider: config.provider ?? 'openai',
            voice: config.voice ?? 'alloy',
            model: config.model ?? this.getDefaultModel(config.provider ?? 'openai'),
            format: config.format ?? 'mp3',
            speed: config.speed ?? 1.0,
            language: config.language ?? 'en',
            verbose: config.verbose ?? false,
        };
    }

    /**
     * Get default TTS model for provider
     */
    private getDefaultModel(provider: AudioProvider): string {
        switch (provider) {
            case 'openai':
                return 'tts-1';
            case 'elevenlabs':
                return 'eleven_multilingual_v2';
            case 'google':
                return 'text-to-speech';
            case 'deepgram':
                return 'aura-asteria-en';
            case 'groq':
                return 'whisper-large-v3';
            default:
                return 'tts-1';
        }
    }

    /**
     * Generate speech from text (Text-to-Speech)
     * 
     * @param text - Text to convert to speech
     * @param options - Override options for this call
     * @returns Audio data with metadata
     * 
     * @example
     * ```typescript
     * const result = await agent.speak('Hello, world!');
     * fs.writeFileSync('output.mp3', result.audio);
     * ```
     */
    async speak(text: string, options?: SpeakOptions): Promise<SpeakResult> {
        const voice = options?.voice ?? this.config.voice;
        const model = options?.model ?? this.config.model;
        const speed = options?.speed ?? this.config.speed;

        if (this.config.verbose) {
            console.log(`[AudioAgent] Speaking with ${this.config.provider}/${model}, voice: ${voice}`);
        }

        try {
            // Lazy import AI SDK
            const { experimental_generateSpeech: generateSpeech } = await import('ai');

            // Get provider-specific speech model
            const speechModel = await this.getSpeechModel(model, voice);

            const result = await generateSpeech({
                model: speechModel,
                text,
                voice,
                // Note: speed is provider-specific, may not be supported by all
            });

            // Handle both Buffer and audio file object types
            const audioData = result.audio instanceof Buffer
                ? result.audio
                : ((result.audio as any).arrayBuffer
                    ? await (result.audio as any).arrayBuffer()
                    : result.audio);

            return {
                audio: audioData as Buffer,
                format: this.config.format,
                duration: (result as any).duration, // If available
            };
        } catch (error: any) {
            // Check for common issues
            if (error.message?.includes('Cannot find module')) {
                throw new Error(
                    `AI SDK not installed. Run: npm install ai @ai-sdk/${this.config.provider}`
                );
            }
            throw error;
        }
    }

    /**
     * Get provider-specific speech model
     */
    private async getSpeechModel(model: string, voice: string): Promise<any> {
        switch (this.config.provider) {
            case 'openai': {
                const { openai } = await import('@ai-sdk/openai');
                return openai.speech(model);
            }
            case 'elevenlabs': {
                // @ts-ignore - optional dependency
                const elevenlabsModule = await import('@ai-sdk/elevenlabs').catch(() => null);
                if (!elevenlabsModule) throw new Error('Install @ai-sdk/elevenlabs for ElevenLabs support');
                return elevenlabsModule.elevenlabs.speech(model);
            }
            case 'google': {
                const { google } = await import('@ai-sdk/google');
                return (google as any).speech?.(model) ?? google(model);
            }
            default:
                throw new Error(`Provider ${this.config.provider} not supported for TTS`);
        }
    }

    /**
     * Transcribe audio to text (Speech-to-Text)
     * 
     * @param audioInput - Audio file path, URL, or Buffer
     * @param options - Transcription options
     * @returns Transcribed text with metadata
     * 
     * @example From file
     * ```typescript
     * const result = await agent.transcribe('./audio.mp3');
     * console.log(result.text);
     * ```
     * 
     * @example From Buffer
     * ```typescript
     * const audioBuffer = fs.readFileSync('./audio.mp3');
     * const result = await agent.transcribe(audioBuffer);
     * ```
     */
    async transcribe(
        audioInput: string | Buffer | ArrayBuffer,
        options?: TranscribeOptions
    ): Promise<TranscribeResult> {
        const language = options?.language ?? this.config.language;

        if (this.config.verbose) {
            console.log(`[AudioAgent] Transcribing with ${this.config.provider}`);
        }

        try {
            // Lazy import AI SDK
            const { experimental_transcribe: transcribe } = await import('ai');

            // Convert input to appropriate format
            const audio = await this.prepareAudioInput(audioInput);

            // Get provider-specific transcription model
            const transcriptionModel = await this.getTranscriptionModel();

            const result = await transcribe({
                model: transcriptionModel,
                audio,
                // language, // If supported by provider
            });

            return {
                text: result.text,
                language: (result as any).language,
                duration: (result as any).duration,
                words: options?.timestamps ? (result as any).words : undefined,
                segments: options?.segments ? (result as any).segments : undefined,
            };
        } catch (error: any) {
            if (error.message?.includes('Cannot find module')) {
                throw new Error(
                    `AI SDK not installed. Run: npm install ai @ai-sdk/${this.config.provider}`
                );
            }
            throw error;
        }
    }

    /**
     * Prepare audio input for transcription
     */
    private async prepareAudioInput(input: string | Buffer | ArrayBuffer): Promise<any> {
        if (typeof input === 'string') {
            // Check if it's a URL
            if (input.startsWith('http://') || input.startsWith('https://')) {
                return { type: 'url', url: input };
            }

            // Assume it's a file path - load with fs
            const fs = await import('fs').catch(() => null);
            if (!fs) {
                throw new Error('File loading requires Node.js fs module');
            }

            const buffer = fs.readFileSync(input);
            return { type: 'buffer', data: buffer };
        }

        // Already a buffer
        return { type: 'buffer', data: input };
    }

    /**
     * Get provider-specific transcription model
     */
    private async getTranscriptionModel(): Promise<any> {
        switch (this.config.provider) {
            case 'openai': {
                const { openai } = await import('@ai-sdk/openai');
                return openai.transcription('whisper-1');
            }
            case 'groq': {
                // @ts-ignore - optional dependency
                const groqModule = await import('@ai-sdk/groq').catch(() => null);
                if (!groqModule) throw new Error('Install @ai-sdk/groq for Groq support');
                return (groqModule.groq as any).transcription?.('whisper-large-v3') ?? groqModule.groq('whisper-large-v3');
            }
            case 'deepgram': {
                // @ts-ignore - optional dependency
                const deepgramModule = await import('@ai-sdk/deepgram').catch(() => null);
                if (!deepgramModule) throw new Error('Install @ai-sdk/deepgram for Deepgram support');
                return (deepgramModule.deepgram as any).transcription?.('nova-2') ?? deepgramModule.deepgram('nova-2');
            }
            default:
                throw new Error(`Provider ${this.config.provider} not supported for transcription`);
        }
    }

    /**
     * Chat method for agent-like interface
     * Determines whether to speak or transcribe based on input
     */
    async chat(input: string): Promise<string> {
        // If input looks like a file path, transcribe it
        if (input.endsWith('.mp3') || input.endsWith('.wav') ||
            input.endsWith('.m4a') || input.endsWith('.ogg') ||
            input.startsWith('http')) {
            const result = await this.transcribe(input);
            return result.text;
        }

        // Otherwise, speak the text and return info
        const result = await this.speak(input);
        return `[Audio generated: ${result.format}, ${result.audio.byteLength} bytes]`;
    }
}

/**
 * Factory function to create AudioAgent
 */
export function createAudioAgent(config?: AudioAgentConfig): AudioAgent {
    return new AudioAgent(config);
}

// Default export
export default AudioAgent;
