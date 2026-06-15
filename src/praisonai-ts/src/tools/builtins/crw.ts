/**
 * fastCRW Tool
 *
 * Web scraping, crawling, and content extraction.
 * Firecrawl-compatible web scraper; single binary; self-host or cloud.
 * Reuses @mendable/firecrawl-js pointed at the fastCRW API.
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';
import { MissingDependencyError, MissingEnvVarError } from '../registry/types';

/** Default fastCRW cloud base URL. Override via CRW_API_URL for self-host. */
const DEFAULT_CRW_API_URL = 'https://fastcrw.com/api';

export const CRW_METADATA: ToolMetadata = {
  id: 'crw',
  displayName: 'fastCRW',
  description: 'Firecrawl-compatible web scraping, crawling, and content extraction for LLM-ready data',
  tags: ['scrape', 'crawl', 'extract', 'web'],
  requiredEnv: ['CRW_API_KEY'],
  optionalEnv: ['CRW_API_URL'],
  install: {
    npm: 'npm install @mendable/firecrawl-js',
    pnpm: 'pnpm add @mendable/firecrawl-js',
    yarn: 'yarn add @mendable/firecrawl-js',
    bun: 'bun add @mendable/firecrawl-js',
  },
  docsSlug: 'tools/crw',
  capabilities: {
    crawl: true,
    extract: true,
  },
  packageName: '@mendable/firecrawl-js',
};

export interface CrwScrapeConfig {
  formats?: ('markdown' | 'html' | 'rawHtml' | 'links' | 'screenshot')[];
  onlyMainContent?: boolean;
  includeTags?: string[];
  excludeTags?: string[];
  waitFor?: number;
}

export interface CrwCrawlConfig {
  limit?: number;
  maxDepth?: number;
  includePaths?: string[];
  excludePaths?: string[];
  allowBackwardLinks?: boolean;
  allowExternalLinks?: boolean;
}

export interface CrwScrapeInput {
  url: string;
}

export interface CrwCrawlInput {
  url: string;
}

export interface CrwScrapeResult {
  content: string;
  markdown?: string;
  html?: string;
  links?: string[];
  metadata?: Record<string, unknown>;
}

export interface CrwCrawlResult {
  pages: Array<{
    url: string;
    content: string;
    markdown?: string;
  }>;
}

async function loadCrwPackage() {
  if (!process.env.CRW_API_KEY) {
    throw new MissingEnvVarError(
      CRW_METADATA.id,
      'CRW_API_KEY',
      CRW_METADATA.docsSlug
    );
  }

  try {
    return await import('@mendable/firecrawl-js');
  } catch {
    throw new MissingDependencyError(
      CRW_METADATA.id,
      CRW_METADATA.packageName,
      CRW_METADATA.install,
      CRW_METADATA.requiredEnv,
      CRW_METADATA.docsSlug
    );
  }
}

/**
 * Create a fastCRW Scrape tool.
 *
 * Scrapes a single web page using the Firecrawl-compatible fastCRW API,
 * returning LLM-ready content in markdown and optionally HTML, links, and metadata.
 *
 * @param config - Optional scraping configuration (formats, content filters, wait time).
 * @returns A PraisonTool that scrapes a single web page.
 *
 * @example
 * ```typescript
 * import { crwScrape } from 'praisonai';
 *
 * const scraper = crwScrape({ formats: ['markdown', 'links'], onlyMainContent: true });
 * const result = await scraper.execute({ url: 'https://example.com' });
 * console.log(result.content);
 * ```
 */
export function crwScrape(config?: CrwScrapeConfig): PraisonTool<CrwScrapeInput, CrwScrapeResult> {
  return {
    name: 'crwScrape',
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
    execute: async (input: CrwScrapeInput, context?: ToolExecutionContext): Promise<CrwScrapeResult> => {
      const pkg = await loadCrwPackage();

      // fastCRW is Firecrawl-compatible: reuse the Firecrawl client with a custom apiUrl
      const FirecrawlApp = (pkg as Record<string, unknown>).default || pkg;
      if (typeof FirecrawlApp === 'function') {
        const app = new (FirecrawlApp as new (options: { apiKey: string; apiUrl: string }) => {
          scrapeUrl: (url: string, options?: CrwScrapeConfig) => Promise<{ data?: { markdown?: string; html?: string; links?: string[]; metadata?: Record<string, unknown> } }>;
        })({ apiKey: process.env.CRW_API_KEY!, apiUrl: process.env.CRW_API_URL || DEFAULT_CRW_API_URL });

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
 * Create a fastCRW Crawl tool.
 *
 * Crawls a website starting from a URL, following links and extracting content
 * from multiple pages using the Firecrawl-compatible fastCRW API.
 *
 * @param config - Optional crawl configuration (depth limits, path filters, link policies).
 * @returns A PraisonTool that crawls a website and extracts content from multiple pages.
 *
 * @example
 * ```typescript
 * import { crwCrawl } from 'praisonai';
 *
 * const crawler = crwCrawl({ limit: 10, maxDepth: 2, includePaths: ['/docs'] });
 * const result = await crawler.execute({ url: 'https://example.com' });
 * console.log(result.pages.length, 'pages crawled');
 * ```
 */
export function crwCrawl(config?: CrwCrawlConfig): PraisonTool<CrwCrawlInput, CrwCrawlResult> {
  return {
    name: 'crwCrawl',
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
    execute: async (input: CrwCrawlInput, context?: ToolExecutionContext): Promise<CrwCrawlResult> => {
      const pkg = await loadCrwPackage();

      const FirecrawlApp = (pkg as Record<string, unknown>).default || pkg;
      if (typeof FirecrawlApp === 'function') {
        const app = new (FirecrawlApp as new (options: { apiKey: string; apiUrl: string }) => {
          crawlUrl: (url: string, options?: CrwCrawlConfig) => Promise<{ data?: Array<{ url: string; markdown?: string }> }>;
        })({ apiKey: process.env.CRW_API_KEY!, apiUrl: process.env.CRW_API_URL || DEFAULT_CRW_API_URL });

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
export function createCrwScrapeTool(config?: CrwScrapeConfig): PraisonTool<unknown, unknown> {
  return crwScrape(config) as PraisonTool<unknown, unknown>;
}

export function createCrwCrawlTool(config?: CrwCrawlConfig): PraisonTool<unknown, unknown> {
  return crwCrawl(config) as PraisonTool<unknown, unknown>;
}
