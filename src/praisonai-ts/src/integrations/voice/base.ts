/**
 * Base Voice - Abstract class for voice/TTS integrations
 * Matches mastra's MastraVoice pattern
 */

export interface VoiceConfig {
  apiKey?: string;
  model?: string;
  voice?: string;
}

export interface SpeakOptions {
  voice?: string;
  speed?: number;
  pitch?: number;
  format?: 'mp3' | 'wav' | 'ogg' | 'opus';
}

export interface ListenOptions {
  language?: string;
  model?: string;
}

export interface Speaker {
  id: string;
  name: string;
  language?: string;
  gender?: 'male' | 'female' | 'neutral';
}

/**
 * Abstract base class for voice providers
 */
export abstract class BaseVoiceProvider {
  readonly name: string;
  protected apiKey?: string;
  protected defaultVoice?: string;

  constructor(config: VoiceConfig & { name?: string }) {
    this.name = config.name || 'VoiceProvider';
    this.apiKey = config.apiKey;
    this.defaultVoice = config.voice;
  }

  /**
   * Convert text to speech
   */
  abstract speak(text: string, options?: SpeakOptions): Promise<Buffer | ReadableStream>;

  /**
   * Convert speech to text
   */
  abstract listen(audio: Buffer | ReadableStream, options?: ListenOptions): Promise<string>;

  /**
   * Get available voices/speakers
   */
  abstract getSpeakers(): Promise<Speaker[]>;

  /**
   * Check if provider is available
   */
  abstract isAvailable(): Promise<boolean>;
}

/**
 * OpenAI Voice Provider (TTS and Whisper)
 */
export class OpenAIVoiceProvider extends BaseVoiceProvider {
  private baseUrl: string;

  constructor(config: VoiceConfig = {}) {
    super({ ...config, name: 'OpenAIVoice' });
    this.apiKey = config.apiKey || process.env.OPENAI_API_KEY;
    this.defaultVoice = config.voice || 'alloy';
    this.baseUrl = 'https://api.openai.com/v1';
  }

  async speak(text: string, options?: SpeakOptions): Promise<Buffer> {
    if (!this.apiKey) {
      throw new Error('OpenAI API key required for TTS');
    }

    const response = await fetch(`${this.baseUrl}/audio/speech`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'tts-1',
        input: text,
        voice: options?.voice || this.defaultVoice,
        speed: options?.speed || 1.0,
        response_format: options?.format || 'mp3'
      })
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`OpenAI TTS error: ${response.status} - ${error}`);
    }

    const arrayBuffer = await response.arrayBuffer();
    return Buffer.from(arrayBuffer);
  }

  async listen(audio: Buffer | ReadableStream, options?: ListenOptions): Promise<string> {
    if (!this.apiKey) {
      throw new Error('OpenAI API key required for Whisper');
    }

    const formData = new FormData();
    
    // Convert Buffer to Blob
    const audioBlob = audio instanceof Buffer 
      ? new Blob([new Uint8Array(audio)], { type: 'audio/mp3' })
      : audio;
    
    formData.append('file', audioBlob as Blob, 'audio.mp3');
    formData.append('model', options?.model || 'whisper-1');
    if (options?.language) {
      formData.append('language', options.language);
    }

    const response = await fetch(`${this.baseUrl}/audio/transcriptions`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`
      },
      body: formData
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`OpenAI Whisper error: ${response.status} - ${error}`);
    }

    const result = await response.json();
    return result.text;
  }

  async getSpeakers(): Promise<Speaker[]> {
    return [
      { id: 'alloy', name: 'Alloy', gender: 'neutral' },
      { id: 'echo', name: 'Echo', gender: 'male' },
      { id: 'fable', name: 'Fable', gender: 'neutral' },
      { id: 'onyx', name: 'Onyx', gender: 'male' },
      { id: 'nova', name: 'Nova', gender: 'female' },
      { id: 'shimmer', name: 'Shimmer', gender: 'female' }
    ];
  }

  async isAvailable(): Promise<boolean> {
    return !!this.apiKey;
  }
}

/**
 * ElevenLabs Voice Provider
 */
export class ElevenLabsVoiceProvider extends BaseVoiceProvider {
  private baseUrl: string;

  constructor(config: VoiceConfig = {}) {
    super({ ...config, name: 'ElevenLabsVoice' });
    this.apiKey = config.apiKey || process.env.ELEVENLABS_API_KEY;
    this.baseUrl = 'https://api.elevenlabs.io/v1';
  }

  async speak(text: string, options?: SpeakOptions): Promise<Buffer> {
    if (!this.apiKey) {
      throw new Error('ElevenLabs API key required');
    }

    const voiceId = options?.voice || this.defaultVoice || '21m00Tcm4TlvDq8ikWAM'; // Rachel

    const response = await fetch(`${this.baseUrl}/text-to-speech/${voiceId}`, {
      method: 'POST',
      headers: {
        'xi-api-key': this.apiKey,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        text,
        model_id: 'eleven_monolingual_v1',
        voice_settings: {
          stability: 0.5,
          similarity_boost: 0.5
        }
      })
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`ElevenLabs error: ${response.status} - ${error}`);
    }

    const arrayBuffer = await response.arrayBuffer();
    return Buffer.from(arrayBuffer);
  }

  async listen(_audio: Buffer | ReadableStream, _options?: ListenOptions): Promise<string> {
    throw new Error('ElevenLabs does not support speech-to-text');
  }

  async getSpeakers(): Promise<Speaker[]> {
    if (!this.apiKey) {
      return [];
    }

    const response = await fetch(`${this.baseUrl}/voices`, {
      headers: {
        'xi-api-key': this.apiKey
      }
    });

    if (!response.ok) {
      return [];
    }

    const data = await response.json();
    return (data.voices || []).map((v: any) => ({
      id: v.voice_id,
      name: v.name,
      gender: v.labels?.gender
    }));
  }

  async isAvailable(): Promise<boolean> {
    return !!this.apiKey;
  }
}

// Factory functions
export function createOpenAIVoice(config?: VoiceConfig): OpenAIVoiceProvider {
  return new OpenAIVoiceProvider(config);
}

export function createElevenLabsVoice(config?: VoiceConfig): ElevenLabsVoiceProvider {
  return new ElevenLabsVoiceProvider(config);
}
