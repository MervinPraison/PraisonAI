/**
 * ImageAgent - Agent for image generation and analysis
 */

import { type LLMProvider, type Message } from '../llm/providers';
import { resolveBackend } from '../llm/backend-resolver';

export interface ImageGenerationConfig {
  prompt: string;
  size?: '256x256' | '512x512' | '1024x1024' | '1792x1024' | '1024x1792';
  quality?: 'standard' | 'hd';
  style?: 'vivid' | 'natural';
  n?: number;
}

export interface ImageAnalysisConfig {
  imageUrl: string;
  prompt?: string;
  detail?: 'low' | 'high' | 'auto';
}

export interface ImageAgentConfig {
  name?: string;
  llm?: string;
  imageModel?: string;
  verbose?: boolean;
}

/**
 * ImageAgent - Agent for image generation and analysis
 */
export class ImageAgent {
  readonly name: string;
  private provider: LLMProvider | null = null;
  private providerPromise: Promise<LLMProvider> | null = null;
  private llmModel: string;
  private imageModel: string;
  private verbose: boolean;

  constructor(config: ImageAgentConfig = {}) {
    this.name = config.name || `ImageAgent_${Math.random().toString(36).substr(2, 9)}`;
    this.llmModel = config.llm || 'openai/gpt-4o-mini';
    this.imageModel = config.imageModel || 'dall-e-3';
    this.verbose = config.verbose ?? false;
  }

  /**
   * Get the LLM provider (lazy initialization with AI SDK backend)
   */
  private async getProvider(): Promise<LLMProvider> {
    if (this.provider) {
      return this.provider;
    }

    if (!this.providerPromise) {
      this.providerPromise = (async () => {
        const result = await resolveBackend(this.llmModel, {
          attribution: { agentId: this.name },
        });
        this.provider = result.provider;
        return result.provider;
      })();
    }

    return this.providerPromise;
  }

  /**
   * Analyze an image
   */
  async analyze(config: ImageAnalysisConfig): Promise<string> {
    const prompt = config.prompt || 'Describe this image in detail.';
    
    const messages: Message[] = [
      {
        role: 'user',
        content: [
          { type: 'text', text: prompt },
          { 
            type: 'image_url', 
            image_url: { 
              url: config.imageUrl,
              detail: config.detail || 'auto'
            } 
          }
        ] as any
      }
    ];

    const provider = await this.getProvider();
    const result = await provider.generateText({ messages });
    
    if (this.verbose) {
      console.log(`[ImageAgent] Analysis: ${result.text.substring(0, 100)}...`);
    }

    return result.text;
  }

  /**
   * Generate an image (requires OpenAI DALL-E)
   */
  async generate(config: ImageGenerationConfig): Promise<string[]> {
    // This would require direct OpenAI API call for image generation
    // For now, return a placeholder
    if (this.verbose) {
      console.log(`[ImageAgent] Generating image: ${config.prompt}`);
    }

    throw new Error('Image generation requires direct OpenAI API integration. Use the OpenAI SDK directly for DALL-E.');
  }

  /**
   * Chat with image context
   */
  async chat(prompt: string, imageUrl?: string): Promise<string> {
    if (imageUrl) {
      return this.analyze({ imageUrl, prompt });
    }

    const provider = await this.getProvider();
    const result = await provider.generateText({
      messages: [{ role: 'user', content: prompt }]
    });

    return result.text;
  }

  /**
   * Compare two images
   */
  async compare(imageUrl1: string, imageUrl2: string, prompt?: string): Promise<string> {
    const comparePrompt = prompt || 'Compare these two images and describe the differences and similarities.';
    
    const messages: Message[] = [
      {
        role: 'user',
        content: [
          { type: 'text', text: comparePrompt },
          { type: 'image_url', image_url: { url: imageUrl1 } },
          { type: 'image_url', image_url: { url: imageUrl2 } }
        ] as any
      }
    ];

    const provider = await this.getProvider();
    const result = await provider.generateText({ messages });
    return result.text;
  }
}

/**
 * Create an ImageAgent
 */
export function createImageAgent(config?: ImageAgentConfig): ImageAgent {
  return new ImageAgent(config);
}
