/**
 * Tavily Tools (Search, Extract, Crawl, Map)
 * 
 * Web search, content extraction, crawling, and site mapping.
 * Package: @tavily/ai-sdk (uses @tavily/core internally)
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';
import { MissingDependencyError, MissingEnvVarError } from '../registry/types';

export const TAVILY_METADATA: ToolMetadata = {
  id: 'tavily',
  displayName: 'Tavily',
  description: 'Web search, content extraction, crawling, and site mapping powered by Tavily',
  tags: ['search', 'web', 'extract', 'crawl'],
  requiredEnv: ['TAVILY_API_KEY'],
  optionalEnv: [],
  install: {
    npm: 'npm install @tavily/ai-sdk',
    pnpm: 'pnpm add @tavily/ai-sdk',
    yarn: 'yarn add @tavily/ai-sdk',
    bun: 'bun add @tavily/ai-sdk',
  },
  docsSlug: 'tools/tavily',
  capabilities: {
    search: true,
    extract: true,
    crawl: true,
  },
  packageName: '@tavily/ai-sdk',
};

// Search types
export interface TavilySearchConfig {
  apiKey?: string;
  searchDepth?: 'basic' | 'advanced';
  topic?: 'general' | 'news' | 'finance';
  includeAnswer?: boolean;
  maxResults?: number;
  includeImages?: boolean;
  timeRange?: 'year' | 'month' | 'week' | 'day';
  includeDomains?: string[];
  excludeDomains?: string[];
}

export interface TavilySearchInput {
  query: string;
  searchDepth?: 'basic' | 'advanced';
  timeRange?: 'year' | 'month' | 'week' | 'day';
}

export interface TavilySearchResult {
  results: Array<{
    title: string;
    url: string;
    content: string;
    score?: number;
  }>;
  answer?: string;
  images?: Array<{ url: string; description?: string }>;
  query?: string;
  responseTime?: number;
}

// Extract types
export interface TavilyExtractConfig {
  apiKey?: string;
  extractDepth?: 'basic' | 'advanced';
}

export interface TavilyExtractInput {
  urls: string[];
  extractDepth?: 'basic' | 'advanced';
  query?: string;
}

export interface TavilyExtractResult {
  results: Array<{
    url: string;
    rawContent: string;
  }>;
}

// Crawl types
export interface TavilyCrawlConfig {
  apiKey?: string;
  maxDepth?: number;
  extractDepth?: 'basic' | 'advanced';
  instructions?: string;
  allowExternal?: boolean;
}

export interface TavilyCrawlInput {
  url: string;
  maxDepth?: number;
  extractDepth?: 'basic' | 'advanced';
  instructions?: string;
  allowExternal?: boolean;
}

export interface TavilyCrawlResult {
  baseUrl: string;
  results: Array<{
    url: string;
    rawContent: string;
  }>;
}

// Helper to check env and load package
async function loadTavilyPackage() {
  if (!process.env.TAVILY_API_KEY) {
    throw new MissingEnvVarError(
      TAVILY_METADATA.id,
      'TAVILY_API_KEY',
      TAVILY_METADATA.docsSlug
    );
  }

  try {
    // @ts-ignore - optional dependency
    return await import('@tavily/ai-sdk');
  } catch {
    throw new MissingDependencyError(
      TAVILY_METADATA.id,
      TAVILY_METADATA.packageName,
      TAVILY_METADATA.install,
      TAVILY_METADATA.requiredEnv,
      TAVILY_METADATA.docsSlug
    );
  }
}

/**
 * Create a Tavily Search tool
 * Returns a PraisonTool that can be used with agents or directly
 */
export function tavilySearch(config?: TavilySearchConfig): PraisonTool<TavilySearchInput, TavilySearchResult> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let cachedTool: any = null;

  return {
    name: 'tavilySearch',
    description: 'Search the web for information using Tavily. Returns relevant results with content snippets and optional AI-generated answers.',
    parameters: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'The search query',
        },
        searchDepth: {
          type: 'string',
          description: 'Search depth: basic or advanced',
          enum: ['basic', 'advanced'],
        },
        timeRange: {
          type: 'string',
          description: 'Time range filter: year, month, week, or day',
          enum: ['year', 'month', 'week', 'day'],
        },
      },
      required: ['query'],
    },
    execute: async (input: TavilySearchInput, _context?: ToolExecutionContext): Promise<TavilySearchResult> => {
      const pkg = await loadTavilyPackage();
      
      // Create the AI SDK tool with config
      if (!cachedTool) {
        cachedTool = pkg.tavilySearch({
          apiKey: config?.apiKey || process.env.TAVILY_API_KEY,
          searchDepth: config?.searchDepth,
          topic: config?.topic,
          includeAnswer: config?.includeAnswer,
          maxResults: config?.maxResults,
          includeImages: config?.includeImages,
          timeRange: config?.timeRange,
          includeDomains: config?.includeDomains,
          excludeDomains: config?.excludeDomains,
        });
      }
      
      // AI SDK tools have execute method - call with required params
      const result = await cachedTool.execute(
        { query: input.query, searchDepth: input.searchDepth, timeRange: input.timeRange },
        { toolCallId: 'tavily-search', messages: [] }
      );
      
      // Transform to our result type
      return {
        results: (result.results || []).map((r: { title: string; url: string; content: string; score?: number }) => ({
          title: r.title,
          url: r.url,
          content: r.content,
          score: r.score,
        })),
        answer: result.answer,
        images: result.images,
        query: result.query,
        responseTime: result.responseTime,
      };
    },
  };
}

/**
 * Create a Tavily Extract tool
 */
export function tavilyExtract(config?: TavilyExtractConfig): PraisonTool<TavilyExtractInput, TavilyExtractResult> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let cachedTool: any = null;

  return {
    name: 'tavilyExtract',
    description: 'Extract structured content from web pages using Tavily. Provide URLs to extract their content.',
    parameters: {
      type: 'object',
      properties: {
        urls: {
          type: 'array',
          description: 'URLs to extract content from',
          items: { type: 'string' },
        },
        extractDepth: {
          type: 'string',
          description: 'Extraction depth: basic or advanced',
          enum: ['basic', 'advanced'],
        },
        query: {
          type: 'string',
          description: 'Optional query to focus extraction',
        },
      },
      required: ['urls'],
    },
    execute: async (input: TavilyExtractInput, _context?: ToolExecutionContext): Promise<TavilyExtractResult> => {
      const pkg = await loadTavilyPackage();
      
      if (!cachedTool) {
        cachedTool = pkg.tavilyExtract({
          apiKey: config?.apiKey || process.env.TAVILY_API_KEY,
          extractDepth: config?.extractDepth,
        });
      }
      
      const result = await cachedTool.execute(
        { urls: input.urls, extractDepth: input.extractDepth, query: input.query },
        { toolCallId: 'tavily-extract', messages: [] }
      );
      
      return {
        results: (result.results || []).map((r: { url: string; rawContent: string }) => ({
          url: r.url,
          rawContent: r.rawContent,
        })),
      };
    },
  };
}

/**
 * Create a Tavily Crawl tool
 */
export function tavilyCrawl(config?: TavilyCrawlConfig): PraisonTool<TavilyCrawlInput, TavilyCrawlResult> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let cachedTool: any = null;

  return {
    name: 'tavilyCrawl',
    description: 'Crawl a website using Tavily. Discovers and extracts content from multiple pages starting from a base URL.',
    parameters: {
      type: 'object',
      properties: {
        url: {
          type: 'string',
          description: 'The starting URL to crawl',
        },
        maxDepth: {
          type: 'number',
          description: 'Maximum crawl depth',
        },
        extractDepth: {
          type: 'string',
          description: 'Extraction depth: basic or advanced',
          enum: ['basic', 'advanced'],
        },
        instructions: {
          type: 'string',
          description: 'Instructions for the crawler',
        },
        allowExternal: {
          type: 'boolean',
          description: 'Allow crawling external links',
        },
      },
      required: ['url'],
    },
    execute: async (input: TavilyCrawlInput, _context?: ToolExecutionContext): Promise<TavilyCrawlResult> => {
      const pkg = await loadTavilyPackage();
      
      if (!cachedTool) {
        cachedTool = pkg.tavilyCrawl({
          apiKey: config?.apiKey || process.env.TAVILY_API_KEY,
          maxDepth: config?.maxDepth,
          extractDepth: config?.extractDepth,
          instructions: config?.instructions,
          allowExternal: config?.allowExternal,
        });
      }
      
      const result = await cachedTool.execute(
        { url: input.url, maxDepth: input.maxDepth, extractDepth: input.extractDepth, instructions: input.instructions, allowExternal: input.allowExternal },
        { toolCallId: 'tavily-crawl', messages: [] }
      );
      
      return {
        baseUrl: result.baseUrl || input.url,
        results: (result.results || []).map((r: { url: string; rawContent: string }) => ({
          url: r.url,
          rawContent: r.rawContent,
        })),
      };
    },
  };
}

/**
 * Get the raw AI SDK tool for use with generateText
 * This returns the native @tavily/ai-sdk tool
 */
export async function getTavilyAISDKTool(type: 'search' | 'extract' | 'crawl' | 'map' = 'search', config?: TavilySearchConfig) {
  const pkg = await loadTavilyPackage();
  const apiKey = config?.apiKey || process.env.TAVILY_API_KEY;
  
  switch (type) {
    case 'search':
      return pkg.tavilySearch({ apiKey, searchDepth: config?.searchDepth, topic: config?.topic });
    case 'extract':
      return pkg.tavilyExtract({ apiKey });
    case 'crawl':
      return pkg.tavilyCrawl({ apiKey });
    case 'map':
      return pkg.tavilyMap({ apiKey });
    default:
      return pkg.tavilySearch({ apiKey });
  }
}

/**
 * Factory functions for registry
 */
export function createTavilySearchTool(config?: TavilySearchConfig): PraisonTool<unknown, unknown> {
  return tavilySearch(config) as PraisonTool<unknown, unknown>;
}

export function createTavilyExtractTool(config?: TavilyExtractConfig): PraisonTool<unknown, unknown> {
  return tavilyExtract(config) as PraisonTool<unknown, unknown>;
}

export function createTavilyCrawlTool(config?: TavilyCrawlConfig): PraisonTool<unknown, unknown> {
  return tavilyCrawl(config) as PraisonTool<unknown, unknown>;
}
