/**
 * Airweave Tool
 * 
 * Context retrieval and semantic search across connected data sources.
 * Package: @airweave/sdk
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';
import { MissingDependencyError, MissingEnvVarError } from '../registry/types';

export const AIRWEAVE_METADATA: ToolMetadata = {
  id: 'airweave',
  displayName: 'Airweave',
  description: 'Context retrieval and semantic search across connected data sources for RAG applications',
  tags: ['rag', 'semantic-search', 'retrieval', 'context'],
  requiredEnv: ['AIRWEAVE_API_KEY'],
  optionalEnv: ['AIRWEAVE_BASE_URL'],
  install: {
    npm: 'npm install @airweave/sdk',
    pnpm: 'pnpm add @airweave/sdk',
    yarn: 'yarn add @airweave/sdk',
    bun: 'bun add @airweave/sdk',
  },
  docsSlug: 'tools/airweave',
  capabilities: {
    rag: true,
    search: true,
  },
  packageName: '@airweave/sdk',
};

export interface AirweaveSearchConfig {
  limit?: number;
  threshold?: number;
  sources?: string[];
}

export interface AirweaveSearchInput {
  query: string;
}

export interface AirweaveSearchResult {
  results: Array<{
    content: string;
    source: string;
    score: number;
    metadata?: Record<string, unknown>;
  }>;
}

async function loadAirweavePackage() {
  if (!process.env.AIRWEAVE_API_KEY) {
    throw new MissingEnvVarError(
      AIRWEAVE_METADATA.id,
      'AIRWEAVE_API_KEY',
      AIRWEAVE_METADATA.docsSlug
    );
  }

  try {
    return await import('@airweave/sdk');
  } catch {
    throw new MissingDependencyError(
      AIRWEAVE_METADATA.id,
      AIRWEAVE_METADATA.packageName,
      AIRWEAVE_METADATA.install,
      AIRWEAVE_METADATA.requiredEnv,
      AIRWEAVE_METADATA.docsSlug
    );
  }
}

/**
 * Create an Airweave Search tool
 */
export function airweaveSearch(config?: AirweaveSearchConfig): PraisonTool<AirweaveSearchInput, AirweaveSearchResult> {
  return {
    name: 'airweaveSearch',
    description: 'Search across connected data sources using semantic search. Returns relevant context for RAG applications.',
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
    execute: async (input: AirweaveSearchInput, context?: ToolExecutionContext): Promise<AirweaveSearchResult> => {
      const pkg = await loadAirweavePackage();
      
      // Airweave SDK uses a client-based API
      const AirweaveClient = (pkg as Record<string, unknown>).AirweaveClient || 
                             (pkg as Record<string, unknown>).Airweave ||
                             (pkg as Record<string, unknown>).default;
      
      if (AirweaveClient && typeof AirweaveClient === 'function') {
        const client = new (AirweaveClient as new (options: { apiKey: string; baseUrl?: string }) => {
          search: (query: string, options?: AirweaveSearchConfig) => Promise<{ results: Array<{ content: string; source: string; score: number; metadata?: Record<string, unknown> }> }>;
        })({
          apiKey: process.env.AIRWEAVE_API_KEY!,
          baseUrl: process.env.AIRWEAVE_BASE_URL,
        });
        
        const result = await client.search(input.query, config);
        return {
          results: result.results || [],
        };
      }
      
      return { results: [] };
    },
  };
}

/**
 * Factory function for registry
 */
export function createAirweaveSearchTool(config?: AirweaveSearchConfig): PraisonTool<unknown, unknown> {
  return airweaveSearch(config) as PraisonTool<unknown, unknown>;
}
