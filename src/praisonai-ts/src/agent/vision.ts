/**
 * VisionAgent - Image analysis and understanding agent
 * 
 * Python parity with praisonaiagents/agent/vision_agent.py
 * Analyzes images using vision-capable LLMs.
 */

import { Agent } from './simple';

// ============================================================================
// Configuration Types
// ============================================================================

/**
 * Configuration for Vision settings.
 */
export interface VisionConfig {
  /** Maximum image size in pixels */
  maxImageSize?: number;
  /** Image quality for processing */
  quality?: 'low' | 'high' | 'auto';
  /** Detail level for analysis */
  detail?: 'low' | 'high' | 'auto';
  /** Timeout in seconds */
  timeout?: number;
}

/**
 * Result of vision analysis.
 */
export interface VisionResult {
  /** Analysis description */
  description: string;
  /** Detected objects */
  objects?: string[];
  /** Detected text (if any) */
  text?: string;
  /** Confidence score */
  confidence?: number;
  /** Additional metadata */
  metadata?: Record<string, any>;
}

/**
 * Configuration for creating a VisionAgent.
 */
export interface VisionAgentConfig {
  /** Agent name */
  name?: string;
  /** LLM model (must support vision) */
  llm?: string;
  /** Vision configuration */
  vision?: boolean | VisionConfig;
  /** System instructions */
  instructions?: string;
  /** Enable verbose output */
  verbose?: boolean;
}

// ============================================================================
// Default Configuration
// ============================================================================

const DEFAULT_VISION_CONFIG: Required<VisionConfig> = {
  maxImageSize: 4096,
  quality: 'auto',
  detail: 'auto',
  timeout: 60,
};

// ============================================================================
// VisionAgent Class
// ============================================================================

/**
 * Agent for image analysis and understanding.
 * 
 * Uses vision-capable LLMs to analyze images and answer questions about them.
 * 
 * @example
 * ```typescript
 * import { VisionAgent } from 'praisonai';
 * 
 * const agent = new VisionAgent({ llm: 'gpt-4o' });
 * 
 * // Analyze an image
 * const result = await agent.analyze('https://example.com/image.jpg');
 * console.log(result.description);
 * 
 * // Ask a question about an image
 * const answer = await agent.ask('What objects are in this image?', 'https://example.com/image.jpg');
 * ```
 */
export class VisionAgent {
  static readonly DEFAULT_MODEL = 'gpt-4o';

  readonly name: string;
  private readonly llm: string;
  private readonly instructions?: string;
  private readonly verbose: boolean;
  private readonly visionConfig: Required<VisionConfig>;
  private readonly agent: Agent;

  constructor(config: VisionAgentConfig) {
    this.name = config.name || 'VisionAgent';
    this.llm = config.llm || process.env.OPENAI_MODEL_NAME || VisionAgent.DEFAULT_MODEL;
    this.instructions = config.instructions;
    this.verbose = config.verbose ?? true;

    // Resolve vision configuration
    if (config.vision === undefined || config.vision === true || config.vision === false) {
      this.visionConfig = { ...DEFAULT_VISION_CONFIG };
    } else {
      this.visionConfig = { ...DEFAULT_VISION_CONFIG, ...config.vision };
    }

    // Create underlying agent
    this.agent = new Agent({
      name: this.name,
      instructions: this.buildSystemPrompt(),
      llm: this.llm,
      verbose: this.verbose,
    });
  }

  private buildSystemPrompt(): string {
    let prompt = `You are an expert image analyst with vision capabilities.
You can analyze images, describe their contents, identify objects, read text, and answer questions about visual content.
Provide detailed and accurate descriptions.`;

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
   * Analyze an image and return a detailed description.
   * 
   * @param imageUrl - URL of the image to analyze
   * @returns VisionResult with description and detected elements
   */
  async analyze(imageUrl: string): Promise<VisionResult> {
    this.log(`Analyzing image: ${imageUrl}`);

    const response = await this.agent.chat(
      `Analyze this image in detail: ${imageUrl}`
    );

    return {
      description: response,
      metadata: { imageUrl, model: this.llm },
    };
  }

  /**
   * Ask a question about an image.
   * 
   * @param question - Question to ask about the image
   * @param imageUrl - URL of the image
   * @returns Answer to the question
   */
  async ask(question: string, imageUrl: string): Promise<string> {
    this.log(`Asking about image: ${question}`);

    const response = await this.agent.chat(
      `Looking at this image (${imageUrl}), ${question}`
    );

    return response;
  }

  /**
   * Describe the contents of an image.
   * 
   * @param imageUrl - URL of the image
   * @returns Description of the image
   */
  async describe(imageUrl: string): Promise<string> {
    const result = await this.analyze(imageUrl);
    return result.description;
  }

  /**
   * Detect objects in an image.
   * 
   * @param imageUrl - URL of the image
   * @returns List of detected objects
   */
  async detectObjects(imageUrl: string): Promise<string[]> {
    const response = await this.agent.chat(
      `List all objects you can identify in this image (${imageUrl}). Return as a comma-separated list.`
    );

    return response.split(',').map(s => s.trim()).filter(Boolean);
  }

  /**
   * Extract text from an image.
   * 
   * @param imageUrl - URL of the image
   * @returns Extracted text
   */
  async extractText(imageUrl: string): Promise<string> {
    const response = await this.agent.chat(
      `Extract and return all visible text from this image (${imageUrl}).`
    );

    return response;
  }
}

// ============================================================================
// Factory Function
// ============================================================================

/**
 * Create a VisionAgent instance.
 */
export function createVisionAgent(config: VisionAgentConfig): VisionAgent {
  return new VisionAgent(config);
}
