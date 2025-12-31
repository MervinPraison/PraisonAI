/**
 * Tools Facade - Simple API for accessing all built-in tools
 * 
 * Usage:
 *   import { tools } from 'praisonai';
 *   const agent = new Agent({ tools: [tools.tavily(), tools.codeExecution()] });
 */

import type { PraisonTool, ToolFactory } from './registry/types';
import { getToolsRegistry } from './registry/registry';

// Import all tool factories
import { codeExecution, CODE_EXECUTION_METADATA, createCodeExecutionTool } from './builtins/code-execution';
import { tavilySearch, tavilyExtract, tavilyCrawl, TAVILY_METADATA, createTavilySearchTool, createTavilyExtractTool, createTavilyCrawlTool } from './builtins/tavily';
import { exaSearch, EXA_METADATA, createExaSearchTool } from './builtins/exa';
import { perplexitySearch, PERPLEXITY_METADATA, createPerplexitySearchTool } from './builtins/perplexity';
import { parallelSearch, PARALLEL_METADATA, createParallelSearchTool } from './builtins/parallel';
import { firecrawlScrape, firecrawlCrawl, FIRECRAWL_METADATA, createFirecrawlScrapeTool, createFirecrawlCrawlTool } from './builtins/firecrawl';
import { superagentGuard, superagentRedact, superagentVerify, SUPERAGENT_METADATA, createSuperagentGuardTool, createSuperagentRedactTool, createSuperagentVerifyTool } from './builtins/superagent';
import {
  valyuWebSearch, valyuFinanceSearch, valyuPaperSearch, valyuBioSearch,
  valyuPatentSearch, valyuSecSearch, valyuEconomicsSearch, valyuCompanyResearch,
  VALYU_METADATA,
  createValyuWebSearchTool, createValyuFinanceSearchTool, createValyuPaperSearchTool,
  createValyuBioSearchTool, createValyuPatentSearchTool, createValyuSecSearchTool,
  createValyuEconomicsSearchTool, createValyuCompanyResearchTool
} from './builtins/valyu';
import {
  bedrockCodeInterpreter, bedrockBrowserNavigate, bedrockBrowserClick, bedrockBrowserFill,
  BEDROCK_AGENTCORE_METADATA,
  createBedrockCodeInterpreterTool, createBedrockBrowserNavigateTool,
  createBedrockBrowserClickTool, createBedrockBrowserFillTool
} from './builtins/bedrock-agentcore';
import { airweaveSearch, AIRWEAVE_METADATA, createAirweaveSearchTool } from './builtins/airweave';
import { codeMode, CODE_MODE_METADATA, createCodeModeTool } from './builtins/code-mode';
import { registerCustomTool, createCustomTool, registerNpmTool, registerLocalTool } from './builtins/custom';

// Type imports
import type { CodeExecutionConfig } from './builtins/code-execution';
import type { TavilySearchConfig, TavilyExtractConfig, TavilyCrawlConfig } from './builtins/tavily';
import type { ExaSearchConfig } from './builtins/exa';
import type { PerplexitySearchConfig } from './builtins/perplexity';
import type { ParallelSearchConfig } from './builtins/parallel';
import type { FirecrawlScrapeConfig, FirecrawlCrawlConfig } from './builtins/firecrawl';
import type { GuardConfig, RedactConfig, VerifyConfig } from './builtins/superagent';
import type { ValyuSearchConfig } from './builtins/valyu';
import type { CodeInterpreterConfig, BrowserConfig } from './builtins/bedrock-agentcore';
import type { AirweaveSearchConfig } from './builtins/airweave';
import type { CodeModeConfig } from './builtins/code-mode';
import type { CustomToolConfig } from './builtins/custom';

/**
 * Register all built-in tools with the global registry
 */
export function registerBuiltinTools(): void {
  const registry = getToolsRegistry();

  // Code Execution
  registry.register(CODE_EXECUTION_METADATA, createCodeExecutionTool as ToolFactory);

  // Tavily - register with both base ID and specific IDs
  registry.register(TAVILY_METADATA, createTavilySearchTool as ToolFactory);
  registry.register({ ...TAVILY_METADATA, id: 'tavily-search' }, createTavilySearchTool as ToolFactory);
  registry.register({ ...TAVILY_METADATA, id: 'tavily-extract' }, createTavilyExtractTool as ToolFactory);
  registry.register({ ...TAVILY_METADATA, id: 'tavily-crawl' }, createTavilyCrawlTool as ToolFactory);

  // Exa
  registry.register(EXA_METADATA, createExaSearchTool as ToolFactory);

  // Perplexity
  registry.register(PERPLEXITY_METADATA, createPerplexitySearchTool as ToolFactory);

  // Parallel
  registry.register(PARALLEL_METADATA, createParallelSearchTool as ToolFactory);

  // Firecrawl
  registry.register({ ...FIRECRAWL_METADATA, id: 'firecrawl-scrape' }, createFirecrawlScrapeTool as ToolFactory);
  registry.register({ ...FIRECRAWL_METADATA, id: 'firecrawl-crawl' }, createFirecrawlCrawlTool as ToolFactory);

  // Superagent
  registry.register({ ...SUPERAGENT_METADATA, id: 'superagent-guard' }, createSuperagentGuardTool as ToolFactory);
  registry.register({ ...SUPERAGENT_METADATA, id: 'superagent-redact' }, createSuperagentRedactTool as ToolFactory);
  registry.register({ ...SUPERAGENT_METADATA, id: 'superagent-verify' }, createSuperagentVerifyTool as ToolFactory);

  // Valyu
  registry.register({ ...VALYU_METADATA, id: 'valyu-web' }, createValyuWebSearchTool as ToolFactory);
  registry.register({ ...VALYU_METADATA, id: 'valyu-finance' }, createValyuFinanceSearchTool as ToolFactory);
  registry.register({ ...VALYU_METADATA, id: 'valyu-paper' }, createValyuPaperSearchTool as ToolFactory);
  registry.register({ ...VALYU_METADATA, id: 'valyu-bio' }, createValyuBioSearchTool as ToolFactory);
  registry.register({ ...VALYU_METADATA, id: 'valyu-patent' }, createValyuPatentSearchTool as ToolFactory);
  registry.register({ ...VALYU_METADATA, id: 'valyu-sec' }, createValyuSecSearchTool as ToolFactory);
  registry.register({ ...VALYU_METADATA, id: 'valyu-economics' }, createValyuEconomicsSearchTool as ToolFactory);
  registry.register({ ...VALYU_METADATA, id: 'valyu-company' }, createValyuCompanyResearchTool as ToolFactory);

  // Bedrock AgentCore
  registry.register({ ...BEDROCK_AGENTCORE_METADATA, id: 'bedrock-code-interpreter' }, createBedrockCodeInterpreterTool as ToolFactory);
  registry.register({ ...BEDROCK_AGENTCORE_METADATA, id: 'bedrock-browser-navigate' }, createBedrockBrowserNavigateTool as ToolFactory);
  registry.register({ ...BEDROCK_AGENTCORE_METADATA, id: 'bedrock-browser-click' }, createBedrockBrowserClickTool as ToolFactory);
  registry.register({ ...BEDROCK_AGENTCORE_METADATA, id: 'bedrock-browser-fill' }, createBedrockBrowserFillTool as ToolFactory);

  // Airweave
  registry.register(AIRWEAVE_METADATA, createAirweaveSearchTool as ToolFactory);

  // Code Mode
  registry.register(CODE_MODE_METADATA, createCodeModeTool as ToolFactory);
}

/**
 * Tools facade - provides simple access to all built-in tools
 */
export const tools = {
  // Code Execution (Vercel Sandbox)
  codeExecution: (config?: CodeExecutionConfig) => codeExecution(config),
  executeCode: (config?: CodeExecutionConfig) => codeExecution(config), // Alias

  // Tavily
  tavily: (config?: TavilySearchConfig) => tavilySearch(config),
  tavilySearch: (config?: TavilySearchConfig) => tavilySearch(config),
  tavilyExtract: (config?: TavilyExtractConfig) => tavilyExtract(config),
  tavilyCrawl: (config?: TavilyCrawlConfig) => tavilyCrawl(config),

  // Exa
  exa: (config?: ExaSearchConfig) => exaSearch(config),
  exaSearch: (config?: ExaSearchConfig) => exaSearch(config),

  // Perplexity
  perplexity: (config?: PerplexitySearchConfig) => perplexitySearch(config),
  perplexitySearch: (config?: PerplexitySearchConfig) => perplexitySearch(config),

  // Parallel
  parallel: (config?: ParallelSearchConfig) => parallelSearch(config),
  parallelSearch: (config?: ParallelSearchConfig) => parallelSearch(config),

  // Firecrawl
  firecrawl: (config?: FirecrawlScrapeConfig) => firecrawlScrape(config),
  firecrawlScrape: (config?: FirecrawlScrapeConfig) => firecrawlScrape(config),
  firecrawlCrawl: (config?: FirecrawlCrawlConfig) => firecrawlCrawl(config),

  // Superagent (Security)
  guard: (config?: GuardConfig) => superagentGuard(config),
  redact: (config?: RedactConfig) => superagentRedact(config),
  verify: (config?: VerifyConfig) => superagentVerify(config),
  superagentGuard: (config?: GuardConfig) => superagentGuard(config),
  superagentRedact: (config?: RedactConfig) => superagentRedact(config),
  superagentVerify: (config?: VerifyConfig) => superagentVerify(config),

  // Valyu (Domain Search)
  valyuWebSearch: (config?: ValyuSearchConfig) => valyuWebSearch(config),
  valyuFinanceSearch: (config?: ValyuSearchConfig) => valyuFinanceSearch(config),
  valyuPaperSearch: (config?: ValyuSearchConfig) => valyuPaperSearch(config),
  valyuBioSearch: (config?: ValyuSearchConfig) => valyuBioSearch(config),
  valyuPatentSearch: (config?: ValyuSearchConfig) => valyuPatentSearch(config),
  valyuSecSearch: (config?: ValyuSearchConfig) => valyuSecSearch(config),
  valyuEconomicsSearch: (config?: ValyuSearchConfig) => valyuEconomicsSearch(config),
  valyuCompanyResearch: (config?: ValyuSearchConfig) => valyuCompanyResearch(config),

  // Bedrock AgentCore
  bedrockCodeInterpreter: (config?: CodeInterpreterConfig) => bedrockCodeInterpreter(config),
  bedrockBrowserNavigate: (config?: BrowserConfig) => bedrockBrowserNavigate(config),
  bedrockBrowserClick: (config?: BrowserConfig) => bedrockBrowserClick(config),
  bedrockBrowserFill: (config?: BrowserConfig) => bedrockBrowserFill(config),

  // Airweave
  airweave: (config?: AirweaveSearchConfig) => airweaveSearch(config),
  airweaveSearch: (config?: AirweaveSearchConfig) => airweaveSearch(config),

  // Code Mode
  codeMode: (config?: CodeModeConfig) => codeMode(config),

  // Custom Tools
  custom: <TInput = unknown, TOutput = unknown>(config: CustomToolConfig<TInput, TOutput>) => 
    createCustomTool(config),
  register: <TInput = unknown, TOutput = unknown>(config: CustomToolConfig<TInput, TOutput>) => 
    registerCustomTool(config),
  fromNpm: (packageName: string, toolName?: string) => registerNpmTool(packageName, toolName),
  fromLocal: (filePath: string, toolName?: string) => registerLocalTool(filePath, toolName),

  // Registry access
  getRegistry: () => getToolsRegistry(),
  list: () => getToolsRegistry().list(),
  get: (id: string) => getToolsRegistry().getMetadata(id),
  create: <TConfig = unknown>(id: string, config?: TConfig) => getToolsRegistry().create(id, config),
};

// Export the tools object as default
export default tools;
