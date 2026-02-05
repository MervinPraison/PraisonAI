/**
 * VideoAgent - Video analysis and processing agent
 * 
 * Python parity with praisonaiagents/agent/video_agent.py
 * Analyzes videos using AI models.
 */

import { Agent } from './simple';

// ============================================================================
// Configuration Types
// ============================================================================

/**
 * Configuration for Video settings.
 */
export interface VideoConfig {
  /** Maximum video duration in seconds */
  maxDuration?: number;
  /** Frame extraction rate (frames per second) */
  frameRate?: number;
  /** Maximum frames to analyze */
  maxFrames?: number;
  /** Timeout in seconds */
  timeout?: number;
  /** Enable audio transcription */
  transcribeAudio?: boolean;
}

/**
 * Result of video analysis.
 */
export interface VideoResult {
  /** Overall description */
  description: string;
  /** Per-frame analysis */
  frames?: Array<{
    timestamp: number;
    description: string;
  }>;
  /** Audio transcription if available */
  transcript?: string;
  /** Duration in seconds */
  duration?: number;
  /** Additional metadata */
  metadata?: Record<string, any>;
}

/**
 * Configuration for creating a VideoAgent.
 */
export interface VideoAgentConfig {
  /** Agent name */
  name?: string;
  /** LLM model */
  llm?: string;
  /** Video configuration */
  video?: boolean | VideoConfig;
  /** System instructions */
  instructions?: string;
  /** Enable verbose output */
  verbose?: boolean;
}

// ============================================================================
// Default Configuration
// ============================================================================

const DEFAULT_VIDEO_CONFIG: Required<VideoConfig> = {
  maxDuration: 300,
  frameRate: 1,
  maxFrames: 30,
  timeout: 600,
  transcribeAudio: true,
};

// ============================================================================
// VideoAgent Class
// ============================================================================

/**
 * Agent for video analysis and processing.
 * 
 * @example
 * ```typescript
 * import { VideoAgent } from 'praisonai';
 * 
 * const agent = new VideoAgent({ llm: 'gpt-4o' });
 * 
 * // Analyze a video
 * const result = await agent.analyze('https://example.com/video.mp4');
 * console.log(result.description);
 * ```
 */
export class VideoAgent {
  static readonly DEFAULT_MODEL = 'gpt-4o';

  readonly name: string;
  private readonly llm: string;
  private readonly instructions?: string;
  private readonly verbose: boolean;
  private readonly videoConfig: Required<VideoConfig>;
  private readonly agent: Agent;

  constructor(config: VideoAgentConfig) {
    this.name = config.name || 'VideoAgent';
    this.llm = config.llm || process.env.OPENAI_MODEL_NAME || VideoAgent.DEFAULT_MODEL;
    this.instructions = config.instructions;
    this.verbose = config.verbose ?? true;

    // Resolve video configuration
    if (config.video === undefined || config.video === true || config.video === false) {
      this.videoConfig = { ...DEFAULT_VIDEO_CONFIG };
    } else {
      this.videoConfig = { ...DEFAULT_VIDEO_CONFIG, ...config.video };
    }

    this.agent = new Agent({
      name: this.name,
      instructions: this.buildSystemPrompt(),
      llm: this.llm,
      verbose: this.verbose,
    });
  }

  private buildSystemPrompt(): string {
    let prompt = `You are an expert video analyst.
You can analyze videos, describe their contents, identify actions and events, and answer questions about video content.`;

    if (this.instructions) {
      prompt += `\n\nAdditional instructions: ${this.instructions}`;
    }

    return prompt;
  }

  private log(message: string): void {
    if (this.verbose) {
      console.log(message);
    }
  }

  /**
   * Analyze a video and return a detailed description.
   */
  async analyze(videoUrl: string): Promise<VideoResult> {
    this.log(`Analyzing video: ${videoUrl}`);

    const response = await this.agent.chat(
      `Analyze this video in detail: ${videoUrl}`
    );

    return {
      description: response,
      metadata: { videoUrl, model: this.llm },
    };
  }

  /**
   * Ask a question about a video.
   */
  async ask(question: string, videoUrl: string): Promise<string> {
    this.log(`Asking about video: ${question}`);

    const response = await this.agent.chat(
      `Looking at this video (${videoUrl}), ${question}`
    );

    return response;
  }

  /**
   * Describe the contents of a video.
   */
  async describe(videoUrl: string): Promise<string> {
    const result = await this.analyze(videoUrl);
    return result.description;
  }

  /**
   * Summarize a video.
   */
  async summarize(videoUrl: string): Promise<string> {
    const response = await this.agent.chat(
      `Provide a concise summary of this video: ${videoUrl}`
    );
    return response;
  }

  /**
   * Extract key moments from a video.
   */
  async extractKeyMoments(videoUrl: string): Promise<string[]> {
    const response = await this.agent.chat(
      `List the key moments or events in this video (${videoUrl}). Return as a numbered list.`
    );
    return response.split('\n').filter(Boolean);
  }
}

// ============================================================================
// Factory Function
// ============================================================================

/**
 * Create a VideoAgent instance.
 */
export function createVideoAgent(config: VideoAgentConfig): VideoAgent {
  return new VideoAgent(config);
}
