/**
 * Valyu Domain Search Tools
 * 
 * Specialized search for finance, papers, bio, patents, SEC, economics, and company research.
 * Package: @valyu/ai-sdk
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';
import { MissingDependencyError, MissingEnvVarError } from '../registry/types';

export const VALYU_METADATA: ToolMetadata = {
  id: 'valyu',
  displayName: 'Valyu Domain Search',
  description: 'Specialized search for finance, academic papers, bio, patents, SEC filings, economics, and company research',
  tags: ['search', 'finance', 'papers', 'patents', 'sec', 'economics', 'research'],
  requiredEnv: ['VALYU_API_KEY'],
  optionalEnv: [],
  install: {
    npm: 'npm install @valyu/ai-sdk',
    pnpm: 'pnpm add @valyu/ai-sdk',
    yarn: 'yarn add @valyu/ai-sdk',
    bun: 'bun add @valyu/ai-sdk',
  },
  docsSlug: 'tools/valyu',
  capabilities: {
    search: true,
  },
  packageName: '@valyu/ai-sdk',
};

export interface ValyuSearchConfig {
  maxNumResults?: number;
}

export interface ValyuSearchInput {
  query: string;
}

export interface ValyuSearchResult {
  results: Array<{
    title: string;
    url: string;
    content: string;
    source?: string;
  }>;
}

async function loadValyuPackage() {
  if (!process.env.VALYU_API_KEY) {
    throw new MissingEnvVarError(
      VALYU_METADATA.id,
      'VALYU_API_KEY',
      VALYU_METADATA.docsSlug
    );
  }

  try {
    // @ts-ignore - optional dependency
    return await import('@valyu/ai-sdk');
  } catch {
    throw new MissingDependencyError(
      VALYU_METADATA.id,
      VALYU_METADATA.packageName,
      VALYU_METADATA.install,
      VALYU_METADATA.requiredEnv,
      VALYU_METADATA.docsSlug
    );
  }
}

// Helper to create a Valyu search tool
function createValyuTool(
  name: string,
  description: string,
  searchFnName: string,
  config?: ValyuSearchConfig
): PraisonTool<ValyuSearchInput, ValyuSearchResult> {
  return {
    name,
    description,
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
    execute: async (input: ValyuSearchInput, context?: ToolExecutionContext): Promise<ValyuSearchResult> => {
      const pkg = await loadValyuPackage();
      const searchFn = (pkg as Record<string, unknown>)[searchFnName];
      
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
 * Create a Valyu Web Search tool
 */
export function valyuWebSearch(config?: ValyuSearchConfig): PraisonTool<ValyuSearchInput, ValyuSearchResult> {
  return createValyuTool(
    'valyuWebSearch',
    'Search the web using Valyu for general information.',
    'webSearch',
    config
  );
}

/**
 * Create a Valyu Finance Search tool
 */
export function valyuFinanceSearch(config?: ValyuSearchConfig): PraisonTool<ValyuSearchInput, ValyuSearchResult> {
  return createValyuTool(
    'valyuFinanceSearch',
    'Search financial data including stock prices, earnings, insider transactions, dividends, balance sheets, and income statements.',
    'financeSearch',
    config
  );
}

/**
 * Create a Valyu Paper Search tool
 */
export function valyuPaperSearch(config?: ValyuSearchConfig): PraisonTool<ValyuSearchInput, ValyuSearchResult> {
  return createValyuTool(
    'valyuPaperSearch',
    'Search academic papers from PubMed, arXiv, bioRxiv, medRxiv, and other scholarly sources.',
    'paperSearch',
    config
  );
}

/**
 * Create a Valyu Bio Search tool
 */
export function valyuBioSearch(config?: ValyuSearchConfig): PraisonTool<ValyuSearchInput, ValyuSearchResult> {
  return createValyuTool(
    'valyuBioSearch',
    'Search clinical trials, FDA drug labels, and peer-reviewed biomedical research.',
    'bioSearch',
    config
  );
}

/**
 * Create a Valyu Patent Search tool
 */
export function valyuPatentSearch(config?: ValyuSearchConfig): PraisonTool<ValyuSearchInput, ValyuSearchResult> {
  return createValyuTool(
    'valyuPatentSearch',
    'Search USPTO full-text patents and related intellectual property.',
    'patentSearch',
    config
  );
}

/**
 * Create a Valyu SEC Search tool
 */
export function valyuSecSearch(config?: ValyuSearchConfig): PraisonTool<ValyuSearchInput, ValyuSearchResult> {
  return createValyuTool(
    'valyuSecSearch',
    'Search SEC filings including 10-K, 10-Q, 8-K, and regulatory disclosures.',
    'secSearch',
    config
  );
}

/**
 * Create a Valyu Economics Search tool
 */
export function valyuEconomicsSearch(config?: ValyuSearchConfig): PraisonTool<ValyuSearchInput, ValyuSearchResult> {
  return createValyuTool(
    'valyuEconomicsSearch',
    'Search economic indicators from BLS, FRED, World Bank, USAspending, and more.',
    'economicsSearch',
    config
  );
}

/**
 * Create a Valyu Company Research tool
 */
export function valyuCompanyResearch(config?: ValyuSearchConfig): PraisonTool<ValyuSearchInput, ValyuSearchResult> {
  return createValyuTool(
    'valyuCompanyResearch',
    'Comprehensive company research and intelligence reports.',
    'companyResearch',
    config
  );
}

/**
 * Factory functions for registry
 */
export function createValyuWebSearchTool(config?: ValyuSearchConfig): PraisonTool<unknown, unknown> {
  return valyuWebSearch(config) as PraisonTool<unknown, unknown>;
}

export function createValyuFinanceSearchTool(config?: ValyuSearchConfig): PraisonTool<unknown, unknown> {
  return valyuFinanceSearch(config) as PraisonTool<unknown, unknown>;
}

export function createValyuPaperSearchTool(config?: ValyuSearchConfig): PraisonTool<unknown, unknown> {
  return valyuPaperSearch(config) as PraisonTool<unknown, unknown>;
}

export function createValyuBioSearchTool(config?: ValyuSearchConfig): PraisonTool<unknown, unknown> {
  return valyuBioSearch(config) as PraisonTool<unknown, unknown>;
}

export function createValyuPatentSearchTool(config?: ValyuSearchConfig): PraisonTool<unknown, unknown> {
  return valyuPatentSearch(config) as PraisonTool<unknown, unknown>;
}

export function createValyuSecSearchTool(config?: ValyuSearchConfig): PraisonTool<unknown, unknown> {
  return valyuSecSearch(config) as PraisonTool<unknown, unknown>;
}

export function createValyuEconomicsSearchTool(config?: ValyuSearchConfig): PraisonTool<unknown, unknown> {
  return valyuEconomicsSearch(config) as PraisonTool<unknown, unknown>;
}

export function createValyuCompanyResearchTool(config?: ValyuSearchConfig): PraisonTool<unknown, unknown> {
  return valyuCompanyResearch(config) as PraisonTool<unknown, unknown>;
}
