/**
 * Exa Web Search Tool
 * 
 * AI-powered web search with semantic understanding.
 * Package: @exalabs/ai-sdk
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';
import { MissingDependencyError, MissingEnvVarError } from '../registry/types';

export const EXA_METADATA: ToolMetadata = {
  id: 'exa',
  displayName: 'Exa Web Search',
  description: 'AI-powered web search with semantic understanding and content extraction',
  tags: ['search', 'web', 'semantic'],
  requiredEnv: ['EXA_API_KEY'],
  optionalEnv: [],
  install: {
    npm: 'npm install @exalabs/ai-sdk',
    pnpm: 'pnpm add @exalabs/ai-sdk',
    yarn: 'yarn add @exalabs/ai-sdk',
    bun: 'bun add @exalabs/ai-sdk',
  },
  docsSlug: 'tools/exa',
  capabilities: {
    search: true,
    extract: true,
  },
  packageName: '@exalabs/ai-sdk',
};

export interface ExaSearchConfig {
  type?: 'auto' | 'neural' | 'fast' | 'deep';
  category?: 'company' | 'research paper' | 'news' | 'pdf' | 'github' | 'personal site' | 'linkedin profile' | 'financial report';
  numResults?: number;
  includeDomains?: string[];
  excludeDomains?: string[];
  startPublishedDate?: string;
  endPublishedDate?: string;
  includeText?: string[];
  excludeText?: string[];
  userLocation?: string;
  contents?: {
    text?: { maxCharacters?: number; includeHtmlTags?: boolean };
    summary?: { query?: string } | boolean;
    livecrawl?: 'never' | 'fallback' | 'always' | 'preferred';
    livecrawlTimeout?: number;
  };
}

export interface ExaSearchInput {
  query: string;
}

export interface ExaSearchResult {
  results: Array<{
    title: string;
    url: string;
    text?: string;
    summary?: string;
    publishedDate?: string;
    author?: string;
    score?: number;
  }>;
}

async function loadExaPackage() {
  if (!process.env.EXA_API_KEY) {
    throw new MissingEnvVarError(
      EXA_METADATA.id,
      'EXA_API_KEY',
      EXA_METADATA.docsSlug
    );
  }

  try {
    // @ts-ignore - optional dependency
    return await import('@exalabs/ai-sdk');
  } catch {
    throw new MissingDependencyError(
      EXA_METADATA.id,
      EXA_METADATA.packageName,
      EXA_METADATA.install,
      EXA_METADATA.requiredEnv,
      EXA_METADATA.docsSlug
    );
  }
}

/**
 * Create an Exa Web Search tool
 */
export function exaSearch(config?: ExaSearchConfig): PraisonTool<ExaSearchInput, ExaSearchResult> {
  return {
    name: 'webSearch',
    description: 'Search the web using Exa AI-powered search. Returns semantically relevant results with content.',
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
    execute: async (input: ExaSearchInput, _context?: ToolExecutionContext): Promise<ExaSearchResult> => {
      const pkg = await loadExaPackage();
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const tool: any = pkg.webSearch(config);
      
      if (tool && typeof tool.execute === 'function') {
        const result = await tool.execute(input, { toolCallId: 'exa-search', messages: [] });
        return result as ExaSearchResult;
      }
      
      return { results: [] };
    },
  };
}

/**
 * Factory function for registry
 */
export function createExaSearchTool(config?: ExaSearchConfig): PraisonTool<unknown, unknown> {
  return exaSearch(config) as PraisonTool<unknown, unknown>;
}
