/**
 * Parallel Web Search Tool
 * 
 * Web search with extraction and ctx-zip capabilities.
 * Package: @parallel-web/ai-sdk-tools
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';
import { MissingDependencyError, MissingEnvVarError } from '../registry/types';

export const PARALLEL_METADATA: ToolMetadata = {
  id: 'parallel',
  displayName: 'Parallel Web Search',
  description: 'Web search with extraction and context compression capabilities',
  tags: ['search', 'web', 'extraction'],
  requiredEnv: ['PARALLEL_API_KEY'],
  optionalEnv: [],
  install: {
    npm: 'npm install @parallel-web/ai-sdk-tools',
    pnpm: 'pnpm add @parallel-web/ai-sdk-tools',
    yarn: 'yarn add @parallel-web/ai-sdk-tools',
    bun: 'bun add @parallel-web/ai-sdk-tools',
  },
  docsSlug: 'tools/parallel',
  capabilities: {
    search: true,
    extract: true,
  },
  packageName: '@parallel-web/ai-sdk-tools',
};

export interface ParallelSearchConfig {
  maxResults?: number;
  includeContent?: boolean;
}

export interface ParallelSearchInput {
  query: string;
}

export interface ParallelSearchResult {
  results: Array<{
    title: string;
    url: string;
    content?: string;
  }>;
}

async function loadParallelPackage() {
  if (!process.env.PARALLEL_API_KEY) {
    throw new MissingEnvVarError(
      PARALLEL_METADATA.id,
      'PARALLEL_API_KEY',
      PARALLEL_METADATA.docsSlug
    );
  }

  try {
    // @ts-ignore - optional dependency
    return await import('@parallel-web/ai-sdk-tools');
  } catch {
    throw new MissingDependencyError(
      PARALLEL_METADATA.id,
      PARALLEL_METADATA.packageName,
      PARALLEL_METADATA.install,
      PARALLEL_METADATA.requiredEnv,
      PARALLEL_METADATA.docsSlug
    );
  }
}

/**
 * Create a Parallel Search tool
 */
export function parallelSearch(config?: ParallelSearchConfig): PraisonTool<ParallelSearchInput, ParallelSearchResult> {
  return {
    name: 'parallelSearch',
    description: 'Search the web using Parallel with content extraction capabilities.',
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
    execute: async (input: ParallelSearchInput, context?: ToolExecutionContext): Promise<ParallelSearchResult> => {
      const pkg = await loadParallelPackage();
      
      const searchFn = (pkg as Record<string, unknown>).parallelSearch || (pkg as Record<string, unknown>).search;
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
export function createParallelSearchTool(config?: ParallelSearchConfig): PraisonTool<unknown, unknown> {
  return parallelSearch(config) as PraisonTool<unknown, unknown>;
}
