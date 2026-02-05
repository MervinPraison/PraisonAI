/**
 * Configuration Module for PraisonAI TypeScript SDK
 * 
 * Python parity with praisonaiagents/config module
 * 
 * Provides:
 * - Feature configuration interfaces (MemoryConfig, KnowledgeConfig, etc.)
 * - Preset registries (MEMORY_PRESETS, OUTPUT_PRESETS, etc.)
 * - Resolver functions (resolve_memory, resolve_output, etc.)
 * - Parse utilities (detect_url_scheme, is_path_like, etc.)
 */

// ============================================================================
// Enums (Python parity)
// ============================================================================

/**
 * Memory storage backends.
 * Python parity: praisonaiagents/config/feature_configs.py:40-47
 */
export enum MemoryBackend {
  FILE = 'file',
  SQLITE = 'sqlite',
  REDIS = 'redis',
  POSTGRES = 'postgres',
  MEM0 = 'mem0',
  MONGODB = 'mongodb',
}

/**
 * Chunking strategies for knowledge/RAG.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export enum ChunkingStrategy {
  FIXED = 'fixed',
  SEMANTIC = 'semantic',
  SENTENCE = 'sentence',
  PARAGRAPH = 'paragraph',
}

/**
 * Guardrail actions on failure.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export enum GuardrailAction {
  RAISE = 'raise',
  SKIP = 'skip',
  RETRY = 'retry',
  WARN = 'warn',
}

/**
 * Web search providers.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export enum WebSearchProvider {
  DUCKDUCKGO = 'duckduckgo',
  TAVILY = 'tavily',
  GOOGLE = 'google',
  BING = 'bing',
  SERPER = 'serper',
}

/**
 * Output presets.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export enum OutputPreset {
  SILENT = 'silent',
  STATUS = 'status',
  TRACE = 'trace',
  VERBOSE = 'verbose',
  DEBUG = 'debug',
  STREAM = 'stream',
  JSON = 'json',
}

/**
 * Execution presets.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export enum ExecutionPreset {
  FAST = 'fast',
  BALANCED = 'balanced',
  THOROUGH = 'thorough',
  UNLIMITED = 'unlimited',
}

/**
 * Array mode for parameter resolution.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export enum ArrayMode {
  FIRST = 'first',
  LAST = 'last',
  MERGE = 'merge',
  ALL = 'all',
}

// ============================================================================
// Config Interfaces (Python parity)
// ============================================================================

/**
 * Memory configuration.
 * Python parity: praisonaiagents/config/feature_configs.py:117-180
 */
export interface MemoryConfig {
  backend?: MemoryBackend | string;
  userId?: string;
  sessionId?: string;
  autoMemory?: boolean;
  history?: boolean;
  historyLimit?: number;
  learn?: boolean | LearnConfig;
  storePath?: string;
}

/**
 * Learn configuration for continuous learning.
 * Python parity: praisonaiagents/config/feature_configs.py:60-114
 */
export interface LearnConfig {
  persona?: boolean;
  insights?: boolean;
  thread?: boolean;
  patterns?: boolean;
  decisions?: boolean;
  feedback?: boolean;
  improvements?: boolean;
  scope?: 'private' | 'shared';
  storePath?: string;
  autoConsolidate?: boolean;
  retentionDays?: number;
}

/**
 * Knowledge/RAG configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface KnowledgeConfig {
  sources?: string[];
  rerank?: boolean;
  topK?: number;
  chunkingStrategy?: ChunkingStrategy | string;
  chunkSize?: number;
  chunkOverlap?: number;
}

/**
 * Planning configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface PlanningConfig {
  reasoning?: boolean;
  autoApprove?: boolean;
  readOnly?: boolean;
  maxSteps?: number;
}

/**
 * Multi-agent planning configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface MultiAgentPlanningConfig extends PlanningConfig {
  sharedContext?: boolean;
  coordinationMode?: 'sequential' | 'parallel' | 'hierarchical';
}

/**
 * Reflection configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface ReflectionConfig {
  minIterations?: number;
  maxIterations?: number;
  threshold?: number;
}

/**
 * Guardrail configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface GuardrailConfig {
  maxRetries?: number;
  onFail?: GuardrailAction | string;
  validators?: Array<(input: string) => boolean | Promise<boolean>>;
}

/**
 * Web configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface WebConfig {
  search?: boolean;
  fetch?: boolean;
  searchProvider?: WebSearchProvider | string;
  maxResults?: number;
}

/**
 * Output configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface OutputConfig {
  verbose?: boolean;
  markdown?: boolean;
  stream?: boolean;
  metrics?: boolean;
  reasoningSteps?: boolean;
  actionsTrace?: boolean;
  statusTrace?: boolean;
  simpleOutput?: boolean;
  jsonOutput?: boolean;
  showParameters?: boolean;
}

/**
 * Execution configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface ExecutionConfig {
  maxIter?: number;
  maxRetryLimit?: number;
  maxRpm?: number;
  maxExecutionTime?: number;
}

/**
 * Template configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface TemplateConfig {
  systemPrompt?: string;
  userPromptTemplate?: string;
  responseFormat?: string;
}

/**
 * Caching configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface CachingConfig {
  enabled?: boolean;
  promptCaching?: boolean;
  ttl?: number;
}

/**
 * Hooks configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface HooksConfig {
  beforeTool?: Array<(toolName: string, args: any) => void | Promise<void>>;
  afterTool?: Array<(toolName: string, result: any) => void | Promise<void>>;
  beforeAgent?: Array<(agentName: string, input: string) => void | Promise<void>>;
  afterAgent?: Array<(agentName: string, output: string) => void | Promise<void>>;
}

/**
 * Skills configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface SkillsConfig {
  paths?: string[];
  autoDiscover?: boolean;
  allowedTools?: string[];
}

/**
 * Session configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface SessionConfig {
  sessionId?: string;
  userId?: string;
  metadata?: Record<string, any>;
  ttl?: number;
}

/**
 * Defaults configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface DefaultsConfig {
  llm?: string;
  temperature?: number;
  maxTokens?: number;
  verbose?: boolean;
}

/**
 * Plugins configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface PluginsConfig {
  paths?: string[];
  autoLoad?: boolean;
  disabled?: string[];
}

/**
 * Praison configuration (main config).
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface PraisonConfig {
  defaults?: DefaultsConfig;
  memory?: MemoryConfig;
  knowledge?: KnowledgeConfig;
  planning?: PlanningConfig;
  reflection?: ReflectionConfig;
  guardrails?: GuardrailConfig;
  web?: WebConfig;
  output?: OutputConfig;
  execution?: ExecutionConfig;
  caching?: CachingConfig;
  hooks?: HooksConfig;
  skills?: SkillsConfig;
  plugins?: PluginsConfig;
}

/**
 * Multi-agent execution configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface MultiAgentExecutionConfig {
  maxIter?: number;
  maxRetries?: number;
}

/**
 * Multi-agent hooks configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface MultiAgentHooksConfig extends HooksConfig {
  beforeHandoff?: Array<(from: string, to: string) => void | Promise<void>>;
  afterHandoff?: Array<(from: string, to: string, result: any) => void | Promise<void>>;
}

/**
 * Multi-agent memory configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface MultiAgentMemoryConfig extends MemoryConfig {
  sharedMemory?: boolean;
  isolatedSessions?: boolean;
}

/**
 * Multi-agent output configuration.
 * Python parity: praisonaiagents/config/feature_configs.py
 */
export interface MultiAgentOutputConfig {
  verbose?: number;
  stream?: boolean;
}

// ============================================================================
// Presets (Python parity with praisonaiagents/config/presets.py)
// ============================================================================

/**
 * Memory presets.
 * Python parity: praisonaiagents/config/presets.py:18-33
 */
export const MEMORY_PRESETS: Record<string, Partial<MemoryConfig>> = {
  file: { backend: MemoryBackend.FILE },
  sqlite: { backend: MemoryBackend.SQLITE },
  redis: { backend: MemoryBackend.REDIS },
  postgres: { backend: MemoryBackend.POSTGRES },
  postgresql: { backend: MemoryBackend.POSTGRES },
  mem0: { backend: MemoryBackend.MEM0 },
  mongodb: { backend: MemoryBackend.MONGODB },
  learn: { backend: MemoryBackend.FILE, learn: true },
  history: { backend: MemoryBackend.FILE, history: true, historyLimit: 10 },
  session: { backend: MemoryBackend.FILE, history: true, historyLimit: 10 },
  chat: { backend: MemoryBackend.FILE, history: true, historyLimit: 20 },
};

/**
 * Memory URL schemes.
 * Python parity: praisonaiagents/config/presets.py:35-43
 */
export const MEMORY_URL_SCHEMES: Record<string, string> = {
  postgresql: 'postgres',
  postgres: 'postgres',
  redis: 'redis',
  rediss: 'redis',
  sqlite: 'sqlite',
  mongodb: 'mongodb',
  'mongodb+srv': 'mongodb',
};

/**
 * Output presets.
 * Python parity: praisonaiagents/config/presets.py:60-185
 */
export const OUTPUT_PRESETS: Record<string, Partial<OutputConfig>> = {
  silent: {
    verbose: false,
    markdown: false,
    stream: false,
    metrics: false,
    reasoningSteps: false,
    actionsTrace: false,
  },
  status: {
    verbose: false,
    markdown: false,
    stream: false,
    metrics: false,
    reasoningSteps: false,
    actionsTrace: true,
    simpleOutput: true,
  },
  trace: {
    verbose: false,
    markdown: false,
    stream: false,
    metrics: false,
    reasoningSteps: false,
    actionsTrace: true,
    statusTrace: true,
  },
  verbose: {
    verbose: true,
    markdown: true,
    stream: false,
    metrics: false,
    reasoningSteps: false,
  },
  debug: {
    verbose: false,
    markdown: false,
    stream: false,
    metrics: true,
    reasoningSteps: true,
    actionsTrace: true,
    statusTrace: true,
    showParameters: true,
  },
  stream: {
    verbose: true,
    markdown: true,
    stream: true,
    metrics: false,
    reasoningSteps: false,
  },
  json: {
    verbose: false,
    markdown: false,
    stream: false,
    metrics: false,
    reasoningSteps: false,
    actionsTrace: true,
    jsonOutput: true,
  },
  plain: {
    verbose: false,
    markdown: false,
    stream: false,
    metrics: false,
    reasoningSteps: false,
    actionsTrace: false,
  },
  minimal: {
    verbose: false,
    markdown: false,
    stream: false,
    metrics: false,
    reasoningSteps: false,
  },
  normal: {
    verbose: true,
    markdown: true,
    stream: false,
    metrics: false,
    reasoningSteps: false,
  },
  actions: {
    verbose: false,
    markdown: false,
    stream: false,
    metrics: false,
    reasoningSteps: false,
    actionsTrace: true,
    simpleOutput: true,
  },
  text: {
    verbose: false,
    markdown: false,
    stream: false,
    metrics: false,
    reasoningSteps: false,
    actionsTrace: true,
    simpleOutput: true,
  },
};

/**
 * Execution presets.
 * Python parity: praisonaiagents/config/presets.py:198-223
 */
export const EXECUTION_PRESETS: Record<string, Partial<ExecutionConfig>> = {
  fast: {
    maxIter: 10,
    maxRetryLimit: 1,
    maxRpm: undefined,
    maxExecutionTime: undefined,
  },
  balanced: {
    maxIter: 20,
    maxRetryLimit: 2,
    maxRpm: undefined,
    maxExecutionTime: undefined,
  },
  thorough: {
    maxIter: 50,
    maxRetryLimit: 5,
    maxRpm: undefined,
    maxExecutionTime: undefined,
  },
  unlimited: {
    maxIter: 1000,
    maxRetryLimit: 10,
    maxRpm: undefined,
    maxExecutionTime: undefined,
  },
};

/**
 * Web presets.
 * Python parity: praisonaiagents/config/presets.py:230-240
 */
export const WEB_PRESETS: Record<string, Partial<WebConfig>> = {
  duckduckgo: { search: true, fetch: true, searchProvider: WebSearchProvider.DUCKDUCKGO },
  tavily: { search: true, fetch: true, searchProvider: WebSearchProvider.TAVILY },
  google: { search: true, fetch: true, searchProvider: WebSearchProvider.GOOGLE },
  bing: { search: true, fetch: true, searchProvider: WebSearchProvider.BING },
  serper: { search: true, fetch: true, searchProvider: WebSearchProvider.SERPER },
  search_only: { search: true, fetch: false },
  fetch_only: { search: false, fetch: true },
};

/**
 * Planning presets.
 * Python parity: praisonaiagents/config/presets.py:247-251
 */
export const PLANNING_PRESETS: Record<string, Partial<PlanningConfig>> = {
  reasoning: { reasoning: true, autoApprove: false, readOnly: false },
  read_only: { reasoning: false, autoApprove: false, readOnly: true },
  auto: { reasoning: false, autoApprove: true, readOnly: false },
};

/**
 * Reflection presets.
 * Python parity: praisonaiagents/config/presets.py:258-262
 */
export const REFLECTION_PRESETS: Record<string, Partial<ReflectionConfig>> = {
  minimal: { minIterations: 1, maxIterations: 1 },
  standard: { minIterations: 1, maxIterations: 3 },
  thorough: { minIterations: 2, maxIterations: 5 },
};

/**
 * Guardrail presets.
 * Python parity: praisonaiagents/config/presets.py:269-273
 */
export const GUARDRAIL_PRESETS: Record<string, Partial<GuardrailConfig>> = {
  strict: { maxRetries: 5, onFail: GuardrailAction.RAISE },
  permissive: { maxRetries: 1, onFail: GuardrailAction.SKIP },
  safety: { maxRetries: 3, onFail: GuardrailAction.RETRY },
};

/**
 * Context presets.
 * Python parity: praisonaiagents/config/presets.py:280-284
 */
export const CONTEXT_PRESETS: Record<string, Record<string, string>> = {
  sliding_window: { strategy: 'sliding_window' },
  summarize: { strategy: 'summarize' },
  truncate: { strategy: 'truncate' },
};

/**
 * Autonomy presets.
 * Python parity: praisonaiagents/config/presets.py:291-295
 */
export const AUTONOMY_PRESETS: Record<string, Record<string, string>> = {
  suggest: { mode: 'suggest' },
  auto_edit: { mode: 'auto_edit' },
  full_auto: { mode: 'full_auto' },
};

/**
 * Caching presets.
 * Python parity: praisonaiagents/config/presets.py:302-306
 */
export const CACHING_PRESETS: Record<string, Partial<CachingConfig>> = {
  enabled: { enabled: true, promptCaching: undefined },
  disabled: { enabled: false, promptCaching: undefined },
  prompt: { enabled: true, promptCaching: true },
};

/**
 * Multi-agent output presets.
 * Python parity: praisonaiagents/config/presets.py:313-317
 */
export const MULTI_AGENT_OUTPUT_PRESETS: Record<string, Partial<MultiAgentOutputConfig>> = {
  verbose: { verbose: 2, stream: true },
  minimal: { verbose: 1, stream: true },
  silent: { verbose: 0, stream: false },
};

/**
 * Multi-agent execution presets.
 * Python parity: praisonaiagents/config/presets.py:324-329
 */
export const MULTI_AGENT_EXECUTION_PRESETS: Record<string, Partial<MultiAgentExecutionConfig>> = {
  fast: { maxIter: 5, maxRetries: 2 },
  balanced: { maxIter: 10, maxRetries: 5 },
  thorough: { maxIter: 20, maxRetries: 5 },
  unlimited: { maxIter: 100, maxRetries: 10 },
};

/**
 * Knowledge presets.
 * Python parity: praisonaiagents/config/presets.py:355-357
 */
export const KNOWLEDGE_PRESETS: Record<string, Partial<KnowledgeConfig>> = {
  auto: { sources: [] },
};

// ============================================================================
// Resolver Functions (Python parity with praisonaiagents/config/param_resolver.py)
// ============================================================================

/**
 * Resolve memory configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_memory(
  input: boolean | string | MemoryConfig | undefined
): MemoryConfig | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true) {
    return { backend: MemoryBackend.FILE };
  }
  if (typeof input === 'string') {
    return MEMORY_PRESETS[input] ?? { backend: input as MemoryBackend };
  }
  return input;
}

/**
 * Resolve output configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_output(
  input: boolean | string | OutputConfig | undefined
): OutputConfig | undefined {
  if (input === undefined || input === false) {
    return OUTPUT_PRESETS.silent;
  }
  if (input === true) {
    return OUTPUT_PRESETS.verbose;
  }
  if (typeof input === 'string') {
    return OUTPUT_PRESETS[input] ?? OUTPUT_PRESETS.silent;
  }
  return input;
}

/**
 * Resolve execution configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_execution(
  input: boolean | string | ExecutionConfig | undefined
): ExecutionConfig | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true) {
    return EXECUTION_PRESETS.balanced;
  }
  if (typeof input === 'string') {
    return EXECUTION_PRESETS[input] ?? EXECUTION_PRESETS.balanced;
  }
  return input;
}

/**
 * Resolve web configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_web(
  input: boolean | string | WebConfig | undefined
): WebConfig | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true) {
    return { search: true, fetch: true, searchProvider: WebSearchProvider.DUCKDUCKGO };
  }
  if (typeof input === 'string') {
    return WEB_PRESETS[input] ?? { searchProvider: input as WebSearchProvider };
  }
  return input;
}

/**
 * Resolve planning configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_planning(
  input: boolean | string | PlanningConfig | undefined
): PlanningConfig | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true) {
    return { reasoning: true, autoApprove: false };
  }
  if (typeof input === 'string') {
    return PLANNING_PRESETS[input] ?? { reasoning: true };
  }
  return input;
}

/**
 * Resolve reflection configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_reflection(
  input: boolean | string | ReflectionConfig | undefined
): ReflectionConfig | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true) {
    return REFLECTION_PRESETS.standard;
  }
  if (typeof input === 'string') {
    return REFLECTION_PRESETS[input] ?? REFLECTION_PRESETS.standard;
  }
  return input;
}

/**
 * Resolve knowledge configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_knowledge(
  input: boolean | string | string[] | KnowledgeConfig | undefined
): KnowledgeConfig | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true) {
    return { sources: [] };
  }
  if (typeof input === 'string') {
    return KNOWLEDGE_PRESETS[input] ?? { sources: [input] };
  }
  if (Array.isArray(input)) {
    return { sources: input };
  }
  return input;
}

/**
 * Resolve context configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_context(
  input: boolean | string | Record<string, any> | undefined
): Record<string, any> | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true) {
    return CONTEXT_PRESETS.sliding_window;
  }
  if (typeof input === 'string') {
    return CONTEXT_PRESETS[input] ?? { strategy: input };
  }
  return input;
}

/**
 * Resolve autonomy configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_autonomy(
  input: boolean | string | Record<string, any> | undefined
): Record<string, any> | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true) {
    return AUTONOMY_PRESETS.suggest;
  }
  if (typeof input === 'string') {
    return AUTONOMY_PRESETS[input] ?? { mode: input };
  }
  return input;
}

/**
 * Resolve caching configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_caching(
  input: boolean | string | CachingConfig | undefined
): CachingConfig | undefined {
  if (input === undefined || input === false) {
    return { enabled: false };
  }
  if (input === true) {
    return { enabled: true };
  }
  if (typeof input === 'string') {
    return CACHING_PRESETS[input] ?? { enabled: true };
  }
  return input;
}

/**
 * Resolve hooks configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_hooks(
  input: boolean | HooksConfig | undefined
): HooksConfig | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true) {
    return {};
  }
  return input;
}

/**
 * Resolve skills configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_skills(
  input: boolean | string[] | SkillsConfig | undefined
): SkillsConfig | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true) {
    return { autoDiscover: true };
  }
  if (Array.isArray(input)) {
    return { paths: input };
  }
  return input;
}

/**
 * Resolve routing configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_routing(
  input: boolean | string | Record<string, any> | undefined
): Record<string, any> | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true) {
    return { enabled: true };
  }
  if (typeof input === 'string') {
    return { strategy: input };
  }
  return input;
}

/**
 * Resolve guardrails configuration from various input types.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve_guardrails(
  input: boolean | string | GuardrailConfig | undefined
): GuardrailConfig | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true) {
    return GUARDRAIL_PRESETS.safety;
  }
  if (typeof input === 'string') {
    return GUARDRAIL_PRESETS[input] ?? GUARDRAIL_PRESETS.safety;
  }
  return input;
}

/**
 * Unified resolver function.
 * Python parity: praisonaiagents/config/param_resolver.py
 */
export function resolve<T>(
  type: string,
  input: any,
  presets?: Record<string, T>
): T | undefined {
  if (input === undefined || input === false) {
    return undefined;
  }
  if (input === true && presets) {
    const defaultKey = Object.keys(presets)[0];
    return presets[defaultKey];
  }
  if (typeof input === 'string' && presets) {
    return presets[input];
  }
  return input as T;
}

// ============================================================================
// Parse Utilities (Python parity with praisonaiagents/config/parse_utils.py)
// ============================================================================

/**
 * Detect URL scheme from a connection string.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function detect_url_scheme(url: string): string | undefined {
  const match = url.match(/^([a-zA-Z][a-zA-Z0-9+.-]*):\/\//);
  if (match) {
    const scheme = match[1].toLowerCase();
    return MEMORY_URL_SCHEMES[scheme] ?? scheme;
  }
  return undefined;
}

/**
 * Check if a string looks like a file path.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function is_path_like(value: string): boolean {
  return (
    value.startsWith('/') ||
    value.startsWith('./') ||
    value.startsWith('../') ||
    value.startsWith('~') ||
    /^[a-zA-Z]:[\\\/]/.test(value) ||
    value.includes('/')
  );
}

/**
 * Suggest similar preset names for typos.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function suggest_similar(
  input: string,
  options: string[],
  maxDistance: number = 2
): string[] {
  const suggestions: string[] = [];
  const inputLower = input.toLowerCase();
  
  for (const option of options) {
    const optionLower = option.toLowerCase();
    
    // Exact prefix match
    if (optionLower.startsWith(inputLower) || inputLower.startsWith(optionLower)) {
      suggestions.push(option);
      continue;
    }
    
    // Simple Levenshtein distance check
    const distance = levenshteinDistance(inputLower, optionLower);
    if (distance <= maxDistance) {
      suggestions.push(option);
    }
  }
  
  return suggestions;
}

/**
 * Simple Levenshtein distance implementation.
 */
function levenshteinDistance(a: string, b: string): number {
  const matrix: number[][] = [];
  
  for (let i = 0; i <= b.length; i++) {
    matrix[i] = [i];
  }
  for (let j = 0; j <= a.length; j++) {
    matrix[0][j] = j;
  }
  
  for (let i = 1; i <= b.length; i++) {
    for (let j = 1; j <= a.length; j++) {
      if (b.charAt(i - 1) === a.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j] + 1
        );
      }
    }
  }
  
  return matrix[b.length][a.length];
}

/**
 * Clean triple backticks from code blocks.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function clean_triple_backticks(text: string): string {
  return text.replace(/```[\w]*\n?/g, '').replace(/```/g, '').trim();
}

/**
 * Check if a string is a policy string.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function is_policy_string(value: string): boolean {
  const policyPatterns = [
    /^(allow|deny|require):/i,
    /^(if|when|unless):/i,
    /^(max|min|limit):/i,
  ];
  return policyPatterns.some(pattern => pattern.test(value));
}

/**
 * Parse a policy string into structured format.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function parse_policy_string(
  value: string
): { action: string; condition?: string; value?: string } | undefined {
  const match = value.match(/^(\w+):(.+)$/);
  if (match) {
    return {
      action: match[1].toLowerCase(),
      value: match[2].trim(),
    };
  }
  return undefined;
}

/**
 * Validate configuration against schema.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function validate_config(
  config: Record<string, any>,
  schema: Record<string, { type: string; required?: boolean }>
): { valid: boolean; errors: string[] } {
  const errors: string[] = [];
  
  for (const [key, spec] of Object.entries(schema)) {
    if (spec.required && !(key in config)) {
      errors.push(`Missing required field: ${key}`);
    }
    if (key in config && config[key] !== undefined) {
      const actualType = typeof config[key];
      if (actualType !== spec.type && spec.type !== 'any') {
        errors.push(`Invalid type for ${key}: expected ${spec.type}, got ${actualType}`);
      }
    }
  }
  
  return { valid: errors.length === 0, errors };
}

/**
 * Apply default configuration values.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function apply_config_defaults<T extends Record<string, any>>(
  config: Partial<T>,
  defaults: T
): T {
  return { ...defaults, ...config };
}

/**
 * Get configuration from environment or defaults.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function get_config(key: string, defaultValue?: string): string | undefined {
  if (typeof process !== 'undefined' && process.env) {
    return process.env[key] ?? defaultValue;
  }
  return defaultValue;
}

/**
 * Get configuration path.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function get_config_path(): string {
  return get_config('PRAISONAI_CONFIG_PATH', '.praison/config.json') ?? '.praison/config.json';
}

/**
 * Get default value for a configuration key.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function get_default(key: string): any {
  const defaults: Record<string, any> = {
    llm: 'gpt-4o-mini',
    temperature: 0.7,
    maxTokens: 4096,
    verbose: false,
    output: 'silent',
  };
  return defaults[key];
}

/**
 * Get defaults configuration.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function get_defaults_config(): DefaultsConfig {
  return {
    llm: get_default('llm'),
    temperature: get_default('temperature'),
    maxTokens: get_default('maxTokens'),
    verbose: get_default('verbose'),
  };
}

/**
 * Get plugins configuration.
 * Python parity: praisonaiagents/config/parse_utils.py
 */
export function get_plugins_config(): PluginsConfig {
  return {
    paths: [],
    autoLoad: false,
    disabled: [],
  };
}

// ============================================================================
// Error Classes
// ============================================================================

/**
 * Configuration validation error.
 * Python parity: praisonaiagents/config
 */
export class ConfigValidationError extends Error {
  constructor(
    message: string,
    public readonly field?: string,
    public readonly value?: any
  ) {
    super(message);
    this.name = 'ConfigValidationError';
  }
}
