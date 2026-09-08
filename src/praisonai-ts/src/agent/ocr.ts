/**
 * OCRAgent - Optical Character Recognition agent
 * 
 * Python parity with praisonaiagents/agent/ocr_agent.py
 * Extracts text from documents and images using AI models.
 */

// ============================================================================
// Configuration Types
// ============================================================================

/**
 * Configuration for OCR settings.
 * Python parity with OCRConfig dataclass.
 */
export interface OCRConfig {
  /** Include base64 images in response */
  includeImageBase64?: boolean;
  /** Specific pages to extract (for PDFs) */
  pages?: number[];
  /** Maximum images per page */
  imageLimit?: number;
  /** Timeout in seconds */
  timeout?: number;
  /** Custom API endpoint URL */
  apiBase?: string;
  /** API key for the provider */
  apiKey?: string;
}

/**
 * Page result from OCR extraction.
 */
export interface OCRPage {
  /** Page index (0-based) */
  index: number;
  /** Extracted text as markdown */
  markdown: string;
  /** Base64 images if requested */
  images?: string[];
}

/**
 * Result of OCR extraction.
 */
export interface OCRResult {
  /** Combined extracted text */
  text: string;
  /** Per-page results */
  pages: OCRPage[];
  /** Additional metadata */
  metadata?: Record<string, any>;
}

/**
 * Request handed to an {@link OCRExtractor}.
 */
export interface OCRExtractRequest {
  /** URL or path the caller asked to read. */
  source: string;
  /** Provider document reference derived from `source`. */
  document: { type: string; [key: string]: string };
  /** Model to use for this extraction. */
  model: string;
  /** Resolved OCR options for this extraction. */
  options: Required<OCRConfig>;
  /** Custom API endpoint URL, if configured. */
  baseUrl?: string;
  /** API key, if configured. */
  apiKey?: string;
}

/**
 * A pluggable OCR backend. Supplying one is the only way to make
 * `OCRAgent.extract()` return text.
 */
export type OCRExtractor = (request: OCRExtractRequest) => Promise<OCRResult>;

/**
 * Configuration for creating an OCRAgent.
 */
export interface OCRAgentConfig {
  /**
   * OCR backend that performs the extraction.
   *
   * Without one, `extract()` throws. It used to return
   * `"[OCR extraction from <source> - requires API integration]"` and log
   * `✓ OCR complete`, so a caller could not tell a fabricated document
   * from a real one.
   */
  extractor?: OCRExtractor;
  /** Agent name */
  name?: string;
  /** Optional instructions */
  instructions?: string;
  /** LLM model (e.g., "mistral/mistral-ocr-latest") */
  llm?: string;
  /** Alias for llm parameter */
  model?: string;
  /** Custom API endpoint URL */
  baseUrl?: string;
  /** API key for the provider */
  apiKey?: string;
  /** OCR configuration */
  ocr?: boolean | OCRConfig;
  /** Verbosity level for output */
  verbose?: boolean | number;
}

// ============================================================================
// Default Configuration
// ============================================================================

const DEFAULT_OCR_CONFIG: Required<OCRConfig> = {
  includeImageBase64: false,
  pages: [],
  imageLimit: 0,
  timeout: 600,
  apiBase: '',
  apiKey: '',
};

// ============================================================================
// OCRAgent Class
// ============================================================================

/**
 * A specialized agent for OCR (Optical Character Recognition).
 * 
 * Extracts text from documents (PDFs) and images using AI models.
 * 
 * Supported Providers:
 * - Mistral: `mistral/mistral-ocr-latest`
 * 
 * @example
 * ```typescript
 * import { OCRAgent } from 'praisonai';
 * 
 * const agent = new OCRAgent({ llm: 'mistral/mistral-ocr-latest' });
 * 
 * // Extract from PDF URL
 * const result = await agent.extract('https://example.com/document.pdf');
 * console.log(result.text);
 * 
 * // Extract from image URL
 * const result2 = await agent.extract('https://example.com/image.png');
 * for (const page of result2.pages) {
 *   console.log(page.markdown);
 * }
 * ```
 */
export class OCRAgent {
  static readonly DEFAULT_MODEL = 'mistral/mistral-ocr-latest';

  readonly name: string;
  private readonly instructions?: string;
  private readonly llm: string;
  private readonly baseUrl?: string;
  private readonly apiKey?: string;
  private readonly ocrConfig: Required<OCRConfig>;
  private readonly verbose: boolean | number;
  private readonly extractor?: OCRExtractor;

  constructor(config: OCRAgentConfig) {
    // Handle model alias
    const llm = config.llm ?? config.model;
    
    this.name = config.name || 'OCRAgent';
    this.instructions = config.instructions;
    this.llm = llm || process.env.PRAISONAI_OCR_MODEL || OCRAgent.DEFAULT_MODEL;
    this.baseUrl = config.baseUrl;
    this.apiKey = config.apiKey;
    this.verbose = config.verbose ?? true;
    this.extractor = config.extractor;

    // Resolve OCR configuration
    this.ocrConfig = this.resolveOCRConfig(config.ocr);
  }

  private resolveOCRConfig(ocr?: boolean | OCRConfig): Required<OCRConfig> {
    if (ocr === undefined || ocr === true || ocr === false) {
      return { ...DEFAULT_OCR_CONFIG };
    }
    return { ...DEFAULT_OCR_CONFIG, ...ocr };
  }

  private buildDocument(source: string): { type: string; [key: string]: string } {
    const sourceLower = source.toLowerCase();
    const imageExtensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp'];
    
    if (imageExtensions.some(ext => sourceLower.includes(ext))) {
      return { type: 'image_url', image_url: source };
    }
    return { type: 'document_url', document_url: source };
  }

  private log(message: string): void {
    if (this.verbose) {
      console.log(message);
    }
  }

  /**
   * Extract text from a document or image.
   * 
   * @param source - URL or path to document/image
   * @param options - Override options for this extraction
   * @returns OCRResult with pages, markdown content, and metadata
   */
  async extract(
    source: string,
    options?: {
      includeImageBase64?: boolean;
      pages?: number[];
      imageLimit?: number;
      model?: string;
    }
  ): Promise<OCRResult> {
    const model = options?.model || this.llm;
    
    this.log(`Extracting text with ${model}...`);

    // Build document reference
    const document = this.buildDocument(source);

    // No backend, no result. This deliberately throws instead of returning a
    // shaped placeholder: the previous code produced
    // `"[OCR extraction from <source> - requires API integration]"`, logged
    // `✓ OCR complete`, and handed downstream code something that looked
    // exactly like a successful extraction.
    if (!this.extractor) {
      throw new Error(
        `OCRAgent has no extractor configured, so '${source}' was not read. ` +
          "Pass one explicitly, e.g. `new OCRAgent({ extractor: myMistralOcrCall })`. " +
          `Intended model: ${model}.`
      );
    }

    const result = await this.extractor({
      source,
      document,
      model,
      options: {
        ...this.ocrConfig,
        includeImageBase64: options?.includeImageBase64 ?? this.ocrConfig.includeImageBase64,
        pages: options?.pages ?? this.ocrConfig.pages,
        imageLimit: options?.imageLimit ?? this.ocrConfig.imageLimit,
      },
      baseUrl: this.baseUrl,
      apiKey: this.apiKey,
    });

    this.log('✓ OCR complete');
    return result;
  }

  /**
   * Async version of extract() - same implementation since extract is already async.
   */
  async aextract(
    source: string,
    options?: {
      includeImageBase64?: boolean;
      pages?: number[];
      imageLimit?: number;
      model?: string;
    }
  ): Promise<OCRResult> {
    return this.extract(source, options);
  }

  /**
   * Quick OCR - extract and return markdown text.
   * 
   * @param source - URL or path to document/image
   * @returns Extracted text as markdown string
   */
  async read(source: string): Promise<string> {
    const result = await this.extract(source);
    
    // Combine all pages into markdown
    if (result.pages && result.pages.length > 0) {
      return result.pages
        .map(page => page.markdown)
        .filter(Boolean)
        .join('\n\n');
    }
    return result.text;
  }

  /**
   * Async version of read().
   */
  async aread(source: string): Promise<string> {
    return this.read(source);
  }
}

// ============================================================================
// Factory Function
// ============================================================================

/**
 * Create an OCRAgent instance.
 * 
 * @param config - OCRAgent configuration
 * @returns OCRAgent instance
 */
export function createOCRAgent(config: OCRAgentConfig): OCRAgent {
  return new OCRAgent(config);
}
