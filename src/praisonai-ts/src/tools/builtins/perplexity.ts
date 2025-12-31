/**
 * Perplexity Search Tool
 * 
 * Web search with real-time results powered by Perplexity.
 * Package: @perplexity-ai/ai-sdk
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';
import { MissingDependencyError, MissingEnvVarError } from '../registry/types';

export const PERPLEXITY_METADATA: ToolMetadata = {
  id: 'perplexity',
  displayName: 'Perplexity Search',
  description: 'Web search with real-time results and advanced filtering powered by Perplexity',
  tags: ['search', 'web', 'realtime'],
  requiredEnv: ['PERPLEXITY_API_KEY'],
  optionalEnv: [],
  install: {
    npm: 'npm install @perplexity-ai/ai-sdk',
    pnpm: 'pnpm add @perplexity-ai/ai-sdk',
    yarn: 'yarn add @perplexity-ai/ai-sdk',
    bun: 'bun add @perplexity-ai/ai-sdk',
  },
  docsSlug: 'tools/perplexity',
  capabilities: {
    search: true,
  },
  packageName: '@perplexity-ai/ai-sdk',
};

export interface PerplexitySearchConfig {
  maxResults?: number;
  recencyFilter?: 'hour' | 'day' | 'week' | 'month' | 'year';
  domainFilter?: string[];
}

export interface PerplexitySearchInput {
  query: string;
}

export interface PerplexitySearchResult {
  results: Array<{
    title: string;
    url: string;
    snippet: string;
  }>;
  answer?: string;
}

async function loadPerplexityPackage() {
  if (!process.env.PERPLEXITY_API_KEY) {
    throw new MissingEnvVarError(
      PERPLEXITY_METADATA.id,
      'PERPLEXITY_API_KEY',
      PERPLEXITY_METADATA.docsSlug
    );
  }

  try {
    // @ts-ignore - optional dependency
    return await import('@perplexity-ai/ai-sdk');
  } catch {
    throw new MissingDependencyError(
      PERPLEXITY_METADATA.id,
      PERPLEXITY_METADATA.packageName,
      PERPLEXITY_METADATA.install,
      PERPLEXITY_METADATA.requiredEnv,
      PERPLEXITY_METADATA.docsSlug
    );
  }
}

/**
 * Create a Perplexity Search tool
 */
export function perplexitySearch(config?: PerplexitySearchConfig): PraisonTool<PerplexitySearchInput, PerplexitySearchResult> {
  return {
    name: 'perplexitySearch',
    description: 'Search the web using Perplexity for real-time information and answers.',
    parameters: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'The search query',
        },
      },
      required: ['query'],
    },
    execute: async (input: PerplexitySearchInput, context?: ToolExecutionContext): Promise<PerplexitySearchResult> => {
      const pkg = await loadPerplexityPackage();
      
      // Check for the search function
      const searchFn = (pkg as Record<string, unknown>).perplexitySearch || (pkg as Record<string, unknown>).search;
      if (searchFn && typeof searchFn === 'function') {
        const tool = searchFn(config);
        if (tool && typeof tool.execute === 'function') {
          return await tool.execute(input);
        }
      }
      
      return { results: [] };
    },
  };
}

/**
 * Factory function for registry
 */
export function createPerplexitySearchTool(config?: PerplexitySearchConfig): PraisonTool<unknown, unknown> {
  return perplexitySearch(config) as PraisonTool<unknown, unknown>;
}
