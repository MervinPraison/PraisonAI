/**
 * RealtimeAgent - Real-time voice/audio interaction agent
 * 
 * Python parity with praisonaiagents/agent/realtime_agent.py
 * Enables real-time voice conversations using WebSocket connections.
 */

// ============================================================================
// Configuration Types
// ============================================================================

/**
 * Configuration for Realtime settings.
 */
export interface RealtimeConfig {
  /** Voice to use for responses */
  voice?: 'alloy' | 'echo' | 'fable' | 'onyx' | 'nova' | 'shimmer';
  /** Audio input format */
  inputFormat?: 'pcm16' | 'g711_ulaw' | 'g711_alaw';
  /** Audio output format */
  outputFormat?: 'pcm16' | 'g711_ulaw' | 'g711_alaw';
  /** Sample rate in Hz */
  sampleRate?: number;
  /** Enable voice activity detection */
  vadEnabled?: boolean;
  /** VAD threshold */
  vadThreshold?: number;
  /** Timeout in seconds */
  timeout?: number;
}

/**
 * Event types for realtime sessions.
 */
export type RealtimeEventType = 
  | 'session.created'
  | 'session.updated'
  | 'input_audio_buffer.append'
  | 'input_audio_buffer.commit'
  | 'input_audio_buffer.clear'
  | 'response.create'
  | 'response.done'
  | 'response.audio.delta'
  | 'response.audio.done'
  | 'response.text.delta'
  | 'response.text.done'
  | 'error';

/**
 * Realtime event.
 */
export interface RealtimeEvent {
  type: RealtimeEventType;
  data?: any;
  timestamp?: number;
}

/**
 * Configuration for creating a RealtimeAgent.
 */
export interface RealtimeAgentConfig {
  /** Agent name */
  name?: string;
  /** Model to use */
  llm?: string;
  /** Realtime configuration */
  realtime?: boolean | RealtimeConfig;
  /** System instructions */
  instructions?: string;
  /** Enable verbose output */
  verbose?: boolean;
  /** API key */
  apiKey?: string;
}

// ============================================================================
// Default Configuration
// ============================================================================

const DEFAULT_REALTIME_CONFIG: Required<RealtimeConfig> = {
  voice: 'alloy',
  inputFormat: 'pcm16',
  outputFormat: 'pcm16',
  sampleRate: 24000,
  vadEnabled: true,
  vadThreshold: 0.5,
  timeout: 300,
};

// ============================================================================
// RealtimeAgent Class
// ============================================================================

/**
 * Agent for real-time voice conversations.
 * 
 * Uses WebSocket connections for low-latency audio streaming.
 * 
 * @example
 * ```typescript
 * import { RealtimeAgent } from 'praisonai';
 * 
 * const agent = new RealtimeAgent({
 *   instructions: 'You are a helpful voice assistant',
 *   realtime: { voice: 'nova' }
 * });
 * 
 * // Connect to realtime session
 * await agent.connect();
 * 
 * // Send audio
 * agent.sendAudio(audioBuffer);
 * 
 * // Listen for responses
 * agent.on('response.audio.delta', (event) => {
 *   playAudio(event.data);
 * });
 * ```
 */
export class RealtimeAgent {
  static readonly DEFAULT_MODEL = 'gpt-4o-realtime-preview';

  readonly name: string;
  private readonly llm: string;
  private readonly instructions?: string;
  private readonly verbose: boolean;
  private readonly realtimeConfig: Required<RealtimeConfig>;
  private readonly apiKey?: string;
  private connected: boolean = false;
  private eventHandlers: Map<RealtimeEventType, Array<(event: RealtimeEvent) => void>> = new Map();

  constructor(config: RealtimeAgentConfig) {
    this.name = config.name || 'RealtimeAgent';
    this.llm = config.llm || process.env.OPENAI_REALTIME_MODEL || RealtimeAgent.DEFAULT_MODEL;
    this.instructions = config.instructions;
    this.verbose = config.verbose ?? true;
    this.apiKey = config.apiKey || process.env.OPENAI_API_KEY;

    // Resolve realtime configuration
    if (config.realtime === undefined || config.realtime === true || config.realtime === false) {
      this.realtimeConfig = { ...DEFAULT_REALTIME_CONFIG };
    } else {
      this.realtimeConfig = { ...DEFAULT_REALTIME_CONFIG, ...config.realtime };
    }
  }

  private log(message: string): void {
    if (this.verbose) {
      console.log(message);
    }
  }

  /**
   * Connect to the realtime session.
   */
  async connect(): Promise<void> {
    this.log('Connecting to realtime session...');
    
    // Placeholder - real implementation would establish WebSocket connection
    this.connected = true;
    this.emit({ type: 'session.created', timestamp: Date.now() });
    
    this.log('Connected to realtime session');
  }

  /**
   * Disconnect from the realtime session.
   */
  async disconnect(): Promise<void> {
    this.log('Disconnecting from realtime session...');
    this.connected = false;
  }

  /**
   * Check if connected.
   */
  isConnected(): boolean {
    return this.connected;
  }

  /**
   * Send audio data to the session.
   */
  sendAudio(audioData: ArrayBuffer | Uint8Array): void {
    if (!this.connected) {
      throw new Error('Not connected to realtime session');
    }
    
    this.emit({
      type: 'input_audio_buffer.append',
      data: audioData,
      timestamp: Date.now(),
    });
  }

  /**
   * Commit the audio buffer for processing.
   */
  commitAudio(): void {
    if (!this.connected) {
      throw new Error('Not connected to realtime session');
    }
    
    this.emit({
      type: 'input_audio_buffer.commit',
      timestamp: Date.now(),
    });
  }

  /**
   * Clear the audio buffer.
   */
  clearAudio(): void {
    if (!this.connected) {
      throw new Error('Not connected to realtime session');
    }
    
    this.emit({
      type: 'input_audio_buffer.clear',
      timestamp: Date.now(),
    });
  }

  /**
   * Send a text message.
   */
  async sendText(text: string): Promise<void> {
    if (!this.connected) {
      throw new Error('Not connected to realtime session');
    }
    
    this.log(`Sending text: ${text}`);
    
    this.emit({
      type: 'response.create',
      data: { text },
      timestamp: Date.now(),
    });
  }

  /**
   * Register an event handler.
   */
  on(eventType: RealtimeEventType, handler: (event: RealtimeEvent) => void): void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, []);
    }
    this.eventHandlers.get(eventType)!.push(handler);
  }

  /**
   * Remove an event handler.
   */
  off(eventType: RealtimeEventType, handler: (event: RealtimeEvent) => void): void {
    const handlers = this.eventHandlers.get(eventType);
    if (handlers) {
      const index = handlers.indexOf(handler);
      if (index !== -1) {
        handlers.splice(index, 1);
      }
    }
  }

  /**
   * Emit an event to handlers.
   */
  private emit(event: RealtimeEvent): void {
    const handlers = this.eventHandlers.get(event.type);
    if (handlers) {
      for (const handler of handlers) {
        handler(event);
      }
    }
  }

  /**
   * Get the current configuration.
   */
  getConfig(): Required<RealtimeConfig> {
    return { ...this.realtimeConfig };
  }

  /**
   * Update the session configuration.
   */
  async updateConfig(config: Partial<RealtimeConfig>): Promise<void> {
    Object.assign(this.realtimeConfig, config);
    
    if (this.connected) {
      this.emit({
        type: 'session.updated',
        data: this.realtimeConfig,
        timestamp: Date.now(),
      });
    }
  }
}

// ============================================================================
// Factory Function
// ============================================================================

/**
 * Create a RealtimeAgent instance.
 */
export function createRealtimeAgent(config: RealtimeAgentConfig): RealtimeAgent {
  return new RealtimeAgent(config);
}
