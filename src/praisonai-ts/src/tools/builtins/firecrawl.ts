/**
 * Firecrawl Tool
 * 
 * Web scraping, crawling, and content extraction.
 * Package: @mendable/firecrawl-js
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';
import { MissingDependencyError, MissingEnvVarError } from '../registry/types';

export const FIRECRAWL_METADATA: ToolMetadata = {
  id: 'firecrawl',
  displayName: 'Firecrawl',
  description: 'Web scraping, crawling, and content extraction for LLM-ready data',
  tags: ['scrape', 'crawl', 'extract', 'web'],
  requiredEnv: ['FIRECRAWL_API_KEY'],
  optionalEnv: [],
  install: {
    npm: 'npm install @mendable/firecrawl-js',
    pnpm: 'pnpm add @mendable/firecrawl-js',
    yarn: 'yarn add @mendable/firecrawl-js',
    bun: 'bun add @mendable/firecrawl-js',
  },
  docsSlug: 'tools/firecrawl',
  capabilities: {
    crawl: true,
    extract: true,
  },
  packageName: '@mendable/firecrawl-js',
};

export interface FirecrawlScrapeConfig {
  formats?: ('markdown' | 'html' | 'rawHtml' | 'links' | 'screenshot')[];
  onlyMainContent?: boolean;
  includeTags?: string[];
  excludeTags?: string[];
  waitFor?: number;
}

export interface FirecrawlCrawlConfig {
  limit?: number;
  maxDepth?: number;
  includePaths?: string[];
  excludePaths?: string[];
  allowBackwardLinks?: boolean;
  allowExternalLinks?: boolean;
}

export interface FirecrawlScrapeInput {
  url: string;
}

export interface FirecrawlCrawlInput {
  url: string;
}

export interface FirecrawlScrapeResult {
  content: string;
  markdown?: string;
  html?: string;
  links?: string[];
  metadata?: Record<string, unknown>;
}

export interface FirecrawlCrawlResult {
  pages: Array<{
    url: string;
    content: string;
    markdown?: string;
  }>;
}

async function loadFirecrawlPackage() {
  if (!process.env.FIRECRAWL_API_KEY) {
    throw new MissingEnvVarError(
      FIRECRAWL_METADATA.id,
      'FIRECRAWL_API_KEY',
      FIRECRAWL_METADATA.docsSlug
    );
  }

  try {
    return await import('@mendable/firecrawl-js');
  } catch {
    throw new MissingDependencyError(
      FIRECRAWL_METADATA.id,
      FIRECRAWL_METADATA.packageName,
      FIRECRAWL_METADATA.install,
      FIRECRAWL_METADATA.requiredEnv,
      FIRECRAWL_METADATA.docsSlug
    );
  }
}

/**
 * Create a Firecrawl Scrape tool
 */
export function firecrawlScrape(config?: FirecrawlScrapeConfig): PraisonTool<FirecrawlScrapeInput, FirecrawlScrapeResult> {
  return {
    name: 'firecrawlScrape',
    description: 'Scrape a single web page and extract its content in LLM-ready format.',
    parameters: {
      type: 'object',
      properties: {
        url: {
          type: 'string',
          description: 'The URL to scrape',
        },
      },
      required: ['url'],
    },
    execute: async (input: FirecrawlScrapeInput, context?: ToolExecutionContext): Promise<FirecrawlScrapeResult> => {
      const pkg = await loadFirecrawlPackage();
      
      // Firecrawl uses a class-based API
      const FirecrawlApp = (pkg as Record<string, unknown>).default || pkg;
      if (typeof FirecrawlApp === 'function') {
        const app = new (FirecrawlApp as new (options: { apiKey: string }) => {
          scrapeUrl: (url: string, options?: FirecrawlScrapeConfig) => Promise<{ data?: { markdown?: string; html?: string; links?: string[]; metadata?: Record<string, unknown> } }>;
        })({ apiKey: process.env.FIRECRAWL_API_KEY! });
        
        const result = await app.scrapeUrl(input.url, config);
        return {
          content: result.data?.markdown || '',
          markdown: result.data?.markdown,
          html: result.data?.html,
          links: result.data?.links,
          metadata: result.data?.metadata,
        };
      }
      
      return { content: '' };
    },
  };
}

/**
 * Create a Firecrawl Crawl tool
 */
export function firecrawlCrawl(config?: FirecrawlCrawlConfig): PraisonTool<FirecrawlCrawlInput, FirecrawlCrawlResult> {
  return {
    name: 'firecrawlCrawl',
    description: 'Crawl a website and extract content from multiple pages.',
    parameters: {
      type: 'object',
      properties: {
        url: {
          type: 'string',
          description: 'The starting URL to crawl',
        },
      },
      required: ['url'],
    },
    execute: async (input: FirecrawlCrawlInput, context?: ToolExecutionContext): Promise<FirecrawlCrawlResult> => {
      const pkg = await loadFirecrawlPackage();
      
      const FirecrawlApp = (pkg as Record<string, unknown>).default || pkg;
      if (typeof FirecrawlApp === 'function') {
        const app = new (FirecrawlApp as new (options: { apiKey: string }) => {
          crawlUrl: (url: string, options?: FirecrawlCrawlConfig) => Promise<{ data?: Array<{ url: string; markdown?: string }> }>;
        })({ apiKey: process.env.FIRECRAWL_API_KEY! });
        
        const result = await app.crawlUrl(input.url, config);
        return {
          pages: (result.data || []).map(page => ({
            url: page.url,
            content: page.markdown || '',
            markdown: page.markdown,
          })),
        };
      }
      
      return { pages: [] };
    },
  };
}

/**
 * Factory functions for registry
 */
export function createFirecrawlScrapeTool(config?: FirecrawlScrapeConfig): PraisonTool<unknown, unknown> {
  return firecrawlScrape(config) as PraisonTool<unknown, unknown>;
}

export function createFirecrawlCrawlTool(config?: FirecrawlCrawlConfig): PraisonTool<unknown, unknown> {
  return firecrawlCrawl(config) as PraisonTool<unknown, unknown>;
}
