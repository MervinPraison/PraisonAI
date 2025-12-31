/**
 * Generate Image - AI SDK Wrapper
 * 
 * Provides generateImage function for image generation.
 */

// Lazy load AI SDK
let aiSdk: any = null;
let aiSdkLoaded = false;

async function loadAISDK() {
  if (aiSdkLoaded) return aiSdk;
  try {
    aiSdk = await import('ai');
    aiSdkLoaded = true;
    return aiSdk;
  } catch {
    return null;
  }
}

export interface GenerateImageOptions {
  /** Model to use (e.g., 'dall-e-3', 'google/imagen-3') */
  model: string;
  /** Text prompt for image generation */
  prompt: string;
  /** Number of images to generate */
  n?: number;
  /** Image size (e.g., '1024x1024') */
  size?: `${number}x${number}`;
  /** Aspect ratio (e.g., '16:9') */
  aspectRatio?: `${number}:${number}`;
  /** Seed for reproducibility */
  seed?: number;
  /** Maximum retries */
  maxRetries?: number;
  /** Abort signal */
  abortSignal?: AbortSignal;
  /** Additional headers */
  headers?: Record<string, string>;
  /** Provider-specific options */
  providerOptions?: Record<string, unknown>;
}

export interface GeneratedImage {
  /** Base64-encoded image data */
  base64: string;
  /** Image as Uint8Array */
  uint8Array: Uint8Array;
  /** MIME type */
  mimeType?: string;
}

export interface GenerateImageResult {
  /** Generated images */
  images: GeneratedImage[];
  /** Warnings */
  warnings?: any[];
}

/**
 * Resolve model string to AI SDK image model instance
 */
async function resolveImageModel(modelString: string) {
  let provider = 'openai';
  let modelId = modelString;
  
  if (modelString.includes('/')) {
    const parts = modelString.split('/');
    provider = parts[0].toLowerCase();
    modelId = parts.slice(1).join('/');
  } else {
    if (modelString.startsWith('imagen')) provider = 'google';
    else if (modelString.startsWith('dall-e')) provider = 'openai';
  }

  let providerModule: any;
  try {
    switch (provider) {
      case 'openai':
        providerModule = await import('@ai-sdk/openai');
        return providerModule.openai.image(modelId);
      case 'google':
        providerModule = await import('@ai-sdk/google');
        return providerModule.google.image(modelId);
      default:
        providerModule = await import('@ai-sdk/openai');
        return providerModule.openai.image(modelId);
    }
  } catch (error: any) {
    throw new Error(`Failed to load image provider '${provider}': ${error.message}`);
  }
}

/**
 * Generate images using an image model.
 * 
 * @example Generate with DALL-E
 * ```typescript
 * const result = await generateImage({
 *   model: 'dall-e-3',
 *   prompt: 'A futuristic city at sunset',
 *   size: '1024x1024'
 * });
 * 
 * // Save the image
 * fs.writeFileSync('image.png', result.images[0].uint8Array);
 * ```
 * 
 * @example Generate with Google Imagen
 * ```typescript
 * const result = await generateImage({
 *   model: 'google/imagen-3',
 *   prompt: 'A beautiful landscape',
 *   aspectRatio: '16:9'
 * });
 * ```
 */
export async function generateImage(options: GenerateImageOptions): Promise<GenerateImageResult> {
  const sdk = await loadAISDK();
  if (!sdk) {
    throw new Error('AI SDK not available. Install with: npm install ai @ai-sdk/openai');
  }

  const model = await resolveImageModel(options.model);

  const result = await sdk.generateImage({
    model,
    prompt: options.prompt,
    n: options.n,
    size: options.size,
    aspectRatio: options.aspectRatio,
    seed: options.seed,
    maxRetries: options.maxRetries,
    abortSignal: options.abortSignal,
    headers: options.headers,
    providerOptions: options.providerOptions,
  });

  return {
    images: result.images || [],
    warnings: result.warnings,
  };
}
