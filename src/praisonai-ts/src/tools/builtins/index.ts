/**
 * Built-in Tools - Main Exports
 * 
 * All built-in tool adapters with lazy loading.
 */

// Tool metadata exports
export { CODE_EXECUTION_METADATA } from './code-execution';
export { TAVILY_METADATA } from './tavily';
export { EXA_METADATA } from './exa';
export { PERPLEXITY_METADATA } from './perplexity';
export { PARALLEL_METADATA } from './parallel';
export { FIRECRAWL_METADATA } from './firecrawl';
export { SUPERAGENT_METADATA } from './superagent';
export { VALYU_METADATA } from './valyu';
export { BEDROCK_AGENTCORE_METADATA } from './bedrock-agentcore';
export { AIRWEAVE_METADATA } from './airweave';
export { CODE_MODE_METADATA } from './code-mode';

// Code Execution
export { codeExecution, createCodeExecutionTool } from './code-execution';
export type { CodeExecutionConfig, CodeExecutionInput, CodeExecutionOutput } from './code-execution';

// Tavily
export { tavilySearch, tavilyExtract, tavilyCrawl, createTavilySearchTool, createTavilyExtractTool, createTavilyCrawlTool } from './tavily';
export type { TavilySearchConfig, TavilySearchInput, TavilySearchResult, TavilyExtractConfig, TavilyExtractInput, TavilyExtractResult, TavilyCrawlConfig, TavilyCrawlInput, TavilyCrawlResult } from './tavily';

// Exa
export { exaSearch, createExaSearchTool } from './exa';
export type { ExaSearchConfig, ExaSearchInput, ExaSearchResult } from './exa';

// Perplexity
export { perplexitySearch, createPerplexitySearchTool } from './perplexity';
export type { PerplexitySearchConfig, PerplexitySearchInput, PerplexitySearchResult } from './perplexity';

// Parallel
export { parallelSearch, createParallelSearchTool } from './parallel';
export type { ParallelSearchConfig, ParallelSearchInput, ParallelSearchResult } from './parallel';

// Firecrawl
export { firecrawlScrape, firecrawlCrawl, createFirecrawlScrapeTool, createFirecrawlCrawlTool } from './firecrawl';
export type { FirecrawlScrapeConfig, FirecrawlScrapeInput, FirecrawlScrapeResult, FirecrawlCrawlConfig, FirecrawlCrawlInput, FirecrawlCrawlResult } from './firecrawl';

// Superagent
export { superagentGuard, superagentRedact, superagentVerify, createSuperagentGuardTool, createSuperagentRedactTool, createSuperagentVerifyTool } from './superagent';
export type { GuardConfig, GuardInput, GuardResult, RedactConfig, RedactInput, RedactResult, VerifyConfig, VerifyInput, VerifyResult } from './superagent';

// Valyu
export {
  valyuWebSearch, valyuFinanceSearch, valyuPaperSearch, valyuBioSearch,
  valyuPatentSearch, valyuSecSearch, valyuEconomicsSearch, valyuCompanyResearch,
  createValyuWebSearchTool, createValyuFinanceSearchTool, createValyuPaperSearchTool,
  createValyuBioSearchTool, createValyuPatentSearchTool, createValyuSecSearchTool,
  createValyuEconomicsSearchTool, createValyuCompanyResearchTool
} from './valyu';
export type { ValyuSearchConfig, ValyuSearchInput, ValyuSearchResult } from './valyu';

// Bedrock AgentCore
export {
  bedrockCodeInterpreter, bedrockBrowserNavigate, bedrockBrowserClick, bedrockBrowserFill,
  createBedrockCodeInterpreterTool, createBedrockBrowserNavigateTool,
  createBedrockBrowserClickTool, createBedrockBrowserFillTool
} from './bedrock-agentcore';
export type { CodeInterpreterConfig, CodeInterpreterInput, CodeInterpreterResult, BrowserConfig, BrowserNavigateInput, BrowserClickInput, BrowserFillInput, BrowserResult } from './bedrock-agentcore';

// Airweave
export { airweaveSearch, createAirweaveSearchTool } from './airweave';
export type { AirweaveSearchConfig, AirweaveSearchInput, AirweaveSearchResult } from './airweave';

// Code Mode
export { codeMode, createCodeModeTool } from './code-mode';
export type { CodeModeConfig, CodeModeInput, CodeModeResult } from './code-mode';

// Custom Tools
export { registerCustomTool, createCustomTool, registerNpmTool, registerLocalTool, Tool } from './custom';
export type { CustomToolConfig } from './custom';

// All metadata for registration
export const ALL_BUILTIN_METADATA = [
  // Lazy import to avoid loading all modules at once
] as const;

/**
 * Get all built-in tool metadata
 */
export async function getAllBuiltinMetadata() {
  const { CODE_EXECUTION_METADATA } = await import('./code-execution');
  const { TAVILY_METADATA } = await import('./tavily');
  const { EXA_METADATA } = await import('./exa');
  const { PERPLEXITY_METADATA } = await import('./perplexity');
  const { PARALLEL_METADATA } = await import('./parallel');
  const { FIRECRAWL_METADATA } = await import('./firecrawl');
  const { SUPERAGENT_METADATA } = await import('./superagent');
  const { VALYU_METADATA } = await import('./valyu');
  const { BEDROCK_AGENTCORE_METADATA } = await import('./bedrock-agentcore');
  const { AIRWEAVE_METADATA } = await import('./airweave');
  const { CODE_MODE_METADATA } = await import('./code-mode');

  return [
    CODE_EXECUTION_METADATA,
    TAVILY_METADATA,
    EXA_METADATA,
    PERPLEXITY_METADATA,
    PARALLEL_METADATA,
    FIRECRAWL_METADATA,
    SUPERAGENT_METADATA,
    VALYU_METADATA,
    BEDROCK_AGENTCORE_METADATA,
    AIRWEAVE_METADATA,
    CODE_MODE_METADATA,
  ];
}
