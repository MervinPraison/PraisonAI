/**
 * AnyAPI Tools
 *
 * Hundreds of scraping and data APIs behind one key and one normalized JSON schema,
 * priced per request in USD.
 * Package: @getanyapi/sdk
 *
 * The catalog is large and grows, so this exposes the discover-then-run loop rather
 * than one tool per platform: search the catalog, read one API's schema, run it.
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';
import { MissingDependencyError, MissingEnvVarError } from '../registry/types';

export const ANYAPI_METADATA: ToolMetadata = {
  id: 'anyapi',
  displayName: 'AnyAPI',
  description: 'Hundreds of scraping and data APIs behind one key and one normalized JSON schema, priced per request in USD',
  tags: ['search', 'scrape', 'data', 'social', 'web', 'marketplace'],
  requiredEnv: ['ANYAPI_API_KEY'],
  optionalEnv: [],
  install: {
    npm: 'npm install @getanyapi/sdk',
    pnpm: 'pnpm add @getanyapi/sdk',
    yarn: 'yarn add @getanyapi/sdk',
    bun: 'bun add @getanyapi/sdk',
  },
  docsSlug: 'tools/anyapi',
  capabilities: {
    search: true,
    extract: true,
  },
  packageName: '@getanyapi/sdk',
};

export interface AnyapiSearchApisConfig {
  /** Maximum number of APIs to return. */
  limit?: number;
  /** Restrict results to one catalog category. */
  category?: string;
}

export interface AnyapiRunApiConfig {
  /** Cap the result rows returned. Shrinks the response, not the USD price. */
  maxItems?: number;
  /** Keep only these keys on each result item. Shrinks the response, not the USD price. */
  fields?: string[];
}

export interface AnyapiSearchApisInput {
  query: string;
}

export interface AnyapiApiSummary {
  slug: string;
  name: string;
  category: string;
  description: string;
  /** Most USD one request can cost on the cheapest route: the price of a flat offer, the ceiling of a linear one. */
  maxCostUsd: number;
  /** USD ceiling for one request if AnyAPI has to fail over to another route. */
  failoverMaxUsd: number;
  /** Search relevance score, higher is a closer match. */
  relevance: number;
}

export interface AnyapiSearchApisResult {
  apis: AnyapiApiSummary[];
  total: number;
}

export interface AnyapiGetApiInput {
  slug: string;
}

export interface AnyapiGetApiResult {
  slug: string;
  name: string;
  category: string;
  description: string;
  /** Most USD one request can cost on the cheapest route: the price of a flat offer, the ceiling of a linear one. */
  maxCostUsd: number;
  /** USD ceiling for one request if AnyAPI has to fail over to another route. */
  failoverMaxUsd: number;
  /** JSON Schema for the normalized input this API accepts. */
  inputSchema?: Record<string, unknown>;
  /** JSON Schema for the normalized output this API returns. */
  outputSchema?: Record<string, unknown>;
}

export interface AnyapiRunApiInput {
  slug: string;
  input?: Record<string, unknown>;
}

export interface AnyapiRunApiResult {
  /** Normalized output, or null when the API found no matching result. */
  data: unknown;
  /** False when the API ran successfully but had nothing to return. */
  found: boolean;
  /** USD charged for this call. */
  costUsd: number;
  /** Number of result rows returned. */
  items: number;
}

/** The slice of the AnyAPI discovery pricing shape these tools read. */
interface AnyapiDiscoveryPricing {
  from: { maxUsd: number };
  failoverMaxUsd: number;
}

interface AnyapiSearchHit {
  slug: string;
  name: string;
  category: string;
  description: string;
  pricing: AnyapiDiscoveryPricing;
  relevance: number;
}

interface AnyapiCatalogEntry {
  slug: string;
  name: string;
  category: string;
  description: string;
  pricing: AnyapiDiscoveryPricing;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
}

interface AnyapiRunEnvelope {
  output: unknown;
  costUsd: number;
  items: number;
}

/** The three client methods these tools call. See the @getanyapi/sdk type definitions. */
interface AnyapiClient {
  search(options: { query: string; category?: string; limit?: number }): Promise<{ results: AnyapiSearchHit[]; total: number }>;
  describe(slug: string): Promise<AnyapiCatalogEntry>;
  run(slug: string, input: unknown, options?: { fields?: string[]; maxItems?: number }): Promise<AnyapiRunEnvelope>;
}

async function loadAnyapiPackage() {
  if (!process.env.ANYAPI_API_KEY) {
    throw new MissingEnvVarError(
      ANYAPI_METADATA.id,
      'ANYAPI_API_KEY',
      ANYAPI_METADATA.docsSlug
    );
  }

  try {
    // @ts-ignore - optional dependency
    return await import('@getanyapi/sdk');
  } catch {
    throw new MissingDependencyError(
      ANYAPI_METADATA.id,
      ANYAPI_METADATA.packageName,
      ANYAPI_METADATA.install,
      ANYAPI_METADATA.requiredEnv,
      ANYAPI_METADATA.docsSlug
    );
  }
}

/**
 * Build an AnyAPI client. Throws rather than degrading to an empty result: a run
 * reports the USD it charged, and a fabricated zero would misreport money.
 */
async function createAnyapiClient(): Promise<AnyapiClient> {
  const pkg = await loadAnyapiPackage();
  const AnyAPI = (pkg as Record<string, unknown>).AnyAPI;

  if (typeof AnyAPI !== 'function') {
    throw new MissingDependencyError(
      ANYAPI_METADATA.id,
      ANYAPI_METADATA.packageName,
      ANYAPI_METADATA.install,
      ANYAPI_METADATA.requiredEnv,
      ANYAPI_METADATA.docsSlug
    );
  }

  return new (AnyAPI as new (options: { apiKey: string }) => AnyapiClient)({
    apiKey: process.env.ANYAPI_API_KEY!,
  });
}

/**
 * Most APIs answer with a `{ found, data }` envelope; a few return the data object
 * directly. Normalize both into one shape for the caller.
 */
function readOutput(output: unknown): { found: boolean; data: unknown } {
  if (output && typeof output === 'object' && 'found' in output) {
    const envelope = output as { found: boolean; data: unknown };
    return { found: envelope.found, data: envelope.data };
  }
  return { found: output !== null && output !== undefined, data: output };
}

/**
 * Create an AnyAPI catalog search tool
 */
export function anyapiSearchApis(config?: AnyapiSearchApisConfig): PraisonTool<AnyapiSearchApisInput, AnyapiSearchApisResult> {
  return {
    name: 'anyapiSearchApis',
    description: 'Search the AnyAPI catalog for an API that can answer a data request, ranked by relevance. Returns each API slug, description and the most USD one request can cost. Start here, then call anyapiGetApi for its input schema.',
    parameters: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'What the data is needed for, in plain words, for example "instagram profile" or "google maps reviews"',
        },
      },
      required: ['query'],
    },
    execute: async (input: AnyapiSearchApisInput, context?: ToolExecutionContext): Promise<AnyapiSearchApisResult> => {
      const client = await createAnyapiClient();
      const found = await client.search({
        query: input.query,
        category: config?.category,
        limit: config?.limit,
      });

      return {
        apis: found.results.map(hit => ({
          slug: hit.slug,
          name: hit.name,
          category: hit.category,
          description: hit.description,
          maxCostUsd: hit.pricing.from.maxUsd,
          failoverMaxUsd: hit.pricing.failoverMaxUsd,
          relevance: hit.relevance,
        })),
        total: found.total,
      };
    },
  };
}

/**
 * Create an AnyAPI API definition tool
 */
export function anyapiGetApi(): PraisonTool<AnyapiGetApiInput, AnyapiGetApiResult> {
  return {
    name: 'anyapiGetApi',
    description: 'Get the full definition of one AnyAPI API by slug: its normalized input and output JSON Schema, and the most USD one request can cost. Call this before anyapiRunApi to learn what input the API accepts.',
    parameters: {
      type: 'object',
      properties: {
        slug: {
          type: 'string',
          description: 'The API slug from anyapiSearchApis, for example "instagram.profile"',
        },
      },
      required: ['slug'],
    },
    execute: async (input: AnyapiGetApiInput, context?: ToolExecutionContext): Promise<AnyapiGetApiResult> => {
      const client = await createAnyapiClient();
      const entry = await client.describe(input.slug);

      return {
        slug: entry.slug,
        name: entry.name,
        category: entry.category,
        description: entry.description,
        maxCostUsd: entry.pricing.from.maxUsd,
        failoverMaxUsd: entry.pricing.failoverMaxUsd,
        inputSchema: entry.inputSchema,
        outputSchema: entry.outputSchema,
      };
    },
  };
}

/**
 * Create an AnyAPI run tool
 */
export function anyapiRunApi(config?: AnyapiRunApiConfig): PraisonTool<AnyapiRunApiInput, AnyapiRunApiResult> {
  return {
    name: 'anyapiRunApi',
    description: 'Run an AnyAPI API by slug with normalized input. Returns the normalized output and the USD cost of the call. Get the input shape from anyapiGetApi first.',
    parameters: {
      type: 'object',
      properties: {
        slug: {
          type: 'string',
          description: 'The API slug to run, for example "instagram.profile"',
        },
        input: {
          type: 'object',
          description: 'The normalized input for this API, matching the inputSchema from anyapiGetApi',
        },
      },
      required: ['slug'],
    },
    execute: async (input: AnyapiRunApiInput, context?: ToolExecutionContext): Promise<AnyapiRunApiResult> => {
      const client = await createAnyapiClient();
      const result = await client.run(input.slug, input.input ?? {}, {
        fields: config?.fields,
        maxItems: config?.maxItems,
      });
      const { found, data } = readOutput(result.output);

      return {
        data,
        found,
        costUsd: result.costUsd,
        items: result.items,
      };
    },
  };
}

/**
 * Factory functions for registry
 */
export function createAnyapiSearchApisTool(config?: AnyapiSearchApisConfig): PraisonTool<unknown, unknown> {
  return anyapiSearchApis(config) as PraisonTool<unknown, unknown>;
}

export function createAnyapiGetApiTool(): PraisonTool<unknown, unknown> {
  return anyapiGetApi() as PraisonTool<unknown, unknown>;
}

export function createAnyapiRunApiTool(config?: AnyapiRunApiConfig): PraisonTool<unknown, unknown> {
  return anyapiRunApi(config) as PraisonTool<unknown, unknown>;
}
