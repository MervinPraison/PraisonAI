/**
 * Speech & Transcription - AI SDK v6 Compatible
 * 
 * Provides speech generation and transcription utilities.
 */

// ============================================================================
// Types
// ============================================================================

export interface GenerateSpeechOptions {
  /** Model to use (e.g., 'openai/tts-1', 'elevenlabs/eleven_multilingual_v2') */
  model: string;
  /** Text to convert to speech */
  text: string;
  /** Voice to use */
  voice?: string;
  /** Speed multiplier (0.25 to 4.0) */
  speed?: number;
  /** Output format */
  format?: 'mp3' | 'opus' | 'aac' | 'flac' | 'wav' | 'pcm';
  /** Additional provider options */
  providerOptions?: Record<string, unknown>;
}

export interface GenerateSpeechResult {
  /** Audio data as Uint8Array */
  audio: Uint8Array;
  /** Audio format */
  format: string;
  /** Duration in seconds (if available) */
  durationSeconds?: number;
  /** Provider metadata */
  providerMetadata?: Record<string, unknown>;
}

export interface TranscribeOptions {
  /** Model to use (e.g., 'openai/whisper-1') */
  model: string;
  /** Audio data - can be Uint8Array, ArrayBuffer, Buffer, base64 string, or URL */
  audio: Uint8Array | ArrayBuffer | Buffer | string;
  /** Language hint (ISO 639-1 code) */
  language?: string;
  /** Prompt to guide transcription */
  prompt?: string;
  /** Temperature for sampling */
  temperature?: number;
  /** Output format */
  format?: 'json' | 'text' | 'srt' | 'verbose_json' | 'vtt';
  /** Additional provider options */
  providerOptions?: Record<string, unknown>;
}

export interface TranscribeResult {
  /** Transcribed text */
  text: string;
  /** Detected language */
  language?: string;
  /** Duration in seconds */
  durationSeconds?: number;
  /** Segments with timestamps */
  segments?: TranscriptionSegment[];
  /** Provider metadata */
  providerMetadata?: Record<string, unknown>;
}

export interface TranscriptionSegment {
  /** Segment ID */
  id: number;
  /** Start time in seconds */
  start: number;
  /** End time in seconds */
  end: number;
  /** Segment text */
  text: string;
  /** Confidence score */
  confidence?: number;
}

// ============================================================================
// Speech Generation
// ============================================================================

/**
 * Generate speech from text.
 * 
 * @example
 * ```typescript
 * const result = await generateSpeech({
 *   model: 'openai/tts-1',
 *   text: 'Hello, world!',
 *   voice: 'alloy'
 * });
 * 
 * // Save to file
 * await fs.writeFile('speech.mp3', result.audio);
 * ```
 */
export async function generateSpeech(options: GenerateSpeechOptions): Promise<GenerateSpeechResult> {
  const [provider, model] = parseModel(options.model);
  
  switch (provider) {
    case 'openai':
      return generateSpeechOpenAI(model, options);
    case 'elevenlabs':
      return generateSpeechElevenLabs(model, options);
    default:
      // Try AI SDK
      return generateSpeechAISDK(options);
  }
}

async function generateSpeechOpenAI(model: string, options: GenerateSpeechOptions): Promise<GenerateSpeechResult> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error('OPENAI_API_KEY environment variable is required for OpenAI speech generation');
  }

  const response = await fetch('https://api.openai.com/v1/audio/speech', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: model || 'tts-1',
      input: options.text,
      voice: options.voice || 'alloy',
      speed: options.speed,
      response_format: options.format || 'mp3',
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`OpenAI speech generation failed: ${response.status} - ${error}`);
  }

  const arrayBuffer = await response.arrayBuffer();
  return {
    audio: new Uint8Array(arrayBuffer),
    format: options.format || 'mp3',
  };
}

async function generateSpeechElevenLabs(model: string, options: GenerateSpeechOptions): Promise<GenerateSpeechResult> {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  if (!apiKey) {
    throw new Error('ELEVENLABS_API_KEY environment variable is required for ElevenLabs speech generation');
  }

  const voiceId = options.voice || '21m00Tcm4TlvDq8ikWAM'; // Default: Rachel
  const response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`, {
    method: 'POST',
    headers: {
      'xi-api-key': apiKey,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      text: options.text,
      model_id: model || 'eleven_multilingual_v2',
      voice_settings: {
        stability: 0.5,
        similarity_boost: 0.75,
      },
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`ElevenLabs speech generation failed: ${response.status} - ${error}`);
  }

  const arrayBuffer = await response.arrayBuffer();
  return {
    audio: new Uint8Array(arrayBuffer),
    format: 'mp3',
  };
}

async function generateSpeechAISDK(options: GenerateSpeechOptions): Promise<GenerateSpeechResult> {
  try {
    const ai = await import('ai');
    if ('generateSpeech' in ai) {
      const result = await (ai as any).generateSpeech(options);
      return {
        audio: result.audio,
        format: options.format || 'mp3',
        durationSeconds: result.durationSeconds,
        providerMetadata: result.providerMetadata,
      };
    }
  } catch {
    // AI SDK not available or doesn't support speech
  }
  
  throw new Error(`Speech generation not supported for model: ${options.model}`);
}

// ============================================================================
// Transcription
// ============================================================================

/**
 * Transcribe audio to text.
 * 
 * @example
 * ```typescript
 * const result = await transcribe({
 *   model: 'openai/whisper-1',
 *   audio: await fs.readFile('audio.mp3')
 * });
 * 
 * console.log(result.text);
 * ```
 */
export async function transcribe(options: TranscribeOptions): Promise<TranscribeResult> {
  const [provider, model] = parseModel(options.model);
  
  switch (provider) {
    case 'openai':
      return transcribeOpenAI(model, options);
    default:
      // Try AI SDK
      return transcribeAISDK(options);
  }
}

async function transcribeOpenAI(model: string, options: TranscribeOptions): Promise<TranscribeResult> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error('OPENAI_API_KEY environment variable is required for OpenAI transcription');
  }

  // Convert audio to appropriate format
  let audioData: Uint8Array;
  if (typeof options.audio === 'string') {
    if (options.audio.startsWith('http')) {
      const response = await fetch(options.audio);
      audioData = new Uint8Array(await response.arrayBuffer());
    } else {
      // Assume base64
      audioData = Uint8Array.from(atob(options.audio), c => c.charCodeAt(0));
    }
  } else if (options.audio instanceof ArrayBuffer) {
    audioData = new Uint8Array(options.audio);
  } else {
    audioData = options.audio as Uint8Array;
  }

  const formData = new FormData();
  formData.append('file', new Blob([audioData.buffer as ArrayBuffer]), 'audio.mp3');
  formData.append('model', model || 'whisper-1');
  if (options.language) formData.append('language', options.language);
  if (options.prompt) formData.append('prompt', options.prompt);
  if (options.temperature) formData.append('temperature', String(options.temperature));
  formData.append('response_format', options.format === 'verbose_json' ? 'verbose_json' : 'json');

  const response = await fetch('https://api.openai.com/v1/audio/transcriptions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`OpenAI transcription failed: ${response.status} - ${error}`);
  }

  const data = await response.json();
  
  if (options.format === 'verbose_json') {
    return {
      text: data.text,
      language: data.language,
      durationSeconds: data.duration,
      segments: data.segments?.map((s: any, i: number) => ({
        id: i,
        start: s.start,
        end: s.end,
        text: s.text,
      })),
    };
  }

  return {
    text: data.text,
  };
}

async function transcribeAISDK(options: TranscribeOptions): Promise<TranscribeResult> {
  try {
    const ai = await import('ai');
    if ('transcribe' in ai) {
      const result = await (ai as any).transcribe(options);
      return {
        text: result.text,
        language: result.language,
        durationSeconds: result.durationSeconds,
        segments: result.segments,
        providerMetadata: result.providerMetadata,
      };
    }
  } catch {
    // AI SDK not available or doesn't support transcription
  }
  
  throw new Error(`Transcription not supported for model: ${options.model}`);
}

// ============================================================================
// Utilities
// ============================================================================

function parseModel(model: string): [string, string] {
  if (model.includes('/')) {
    const [provider, ...rest] = model.split('/');
    return [provider.toLowerCase(), rest.join('/')];
  }
  
  // Infer provider from model name
  if (model.startsWith('tts-') || model.startsWith('whisper')) {
    return ['openai', model];
  }
  if (model.startsWith('eleven_')) {
    return ['elevenlabs', model];
  }
  
  return ['openai', model];
}

/**
 * Available speech models.
 */
export const SPEECH_MODELS = {
  openai: {
    'tts-1': { description: 'Standard TTS model', voices: ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'] },
    'tts-1-hd': { description: 'High-definition TTS model', voices: ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'] },
  },
  elevenlabs: {
    'eleven_multilingual_v2': { description: 'Multilingual model', voices: [] },
    'eleven_turbo_v2': { description: 'Fast model', voices: [] },
  },
};

/**
 * Available transcription models.
 */
export const TRANSCRIPTION_MODELS = {
  openai: {
    'whisper-1': { description: 'Whisper large-v2 model', languages: 'auto-detect' },
  },
};
