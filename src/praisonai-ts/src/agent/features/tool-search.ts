/**
 * Progressive tool disclosure (Python parity: `tools/tool_search.py`,
 * `Agent(tool_search=...)`).
 *
 * A large tool list costs context on every single request, whether or not the
 * model uses any of it. With tool search on, deferrable tools are replaced in
 * the request by three bridge tools -- `tool_search`, `tool_describe`,
 * `tool_call` -- and the model discovers what it needs, when it needs it.
 *
 * The architecture invariants are Python's, and each one is load-bearing:
 *
 * 1. Core tools never defer ({@link PRAISONAI_CORE_TOOLS}).
 * 2. Unknown tools stay visible -- a tool is never silently dropped.
 * 3. The catalog is stateless: rebuilt from the current tool defs every turn.
 * 4. Bridge dispatch reads the PRE-assembly deferrable set.
 * 5. The catalog is scoped to this agent's own tools.
 * 6. `tool_call` is unwrapped BEFORE hooks, approval and events, so they see
 *    the real tool name rather than the bridge.
 * 7. In `auto` mode tools defer only once their schemas cross
 *    `thresholdPct` of the context window.
 * 8. BM25 is inlined -- no new dependency -- with a substring fallback.
 */

import { ToolSearchConfig } from '../../config';

/** An OpenAI function schema, as the Agent stores them. */
export type ToolDef = Record<string, any>;

/** Tools that never defer (Python `PRAISONAI_CORE_TOOLS`). */
export const PRAISONAI_CORE_TOOLS: ReadonlySet<string> = new Set([
  // File operations
  'read_file', 'write_file', 'list_files', 'get_file_info',
  'copy_file', 'move_file', 'delete_file',
  // Shell operations
  'execute_command', 'list_processes', 'kill_process', 'get_system_info',
  // Web operations
  'search_web', 'web_search', 'internet_search', 'web_crawl', 'crawl_web',
  // Schedule operations
  'schedule_add', 'schedule_list', 'schedule_remove',
  // Memory operations
  'store_memory', 'search_memory',
  // Human-in-the-loop clarification
  'clarify',
]);

/** The three bridge tool names. */
export const BRIDGE_TOOL_NAMES: ReadonlySet<string> = new Set(['tool_search', 'tool_describe', 'tool_call']);

function functionOf(toolDef: ToolDef): Record<string, any> {
  const fn = toolDef?.function;
  return fn && typeof fn === 'object' ? fn : {};
}

function nameOf(toolDef: ToolDef): string {
  const name = functionOf(toolDef).name;
  return typeof name === 'string' ? name : '';
}

/** Python `_is_tool_deferrable`. */
function isToolDeferrable(toolDef: ToolDef): boolean {
  if (toolDef?.__praisonai_deferrable__ === true) return true;
  const fn = functionOf(toolDef);
  if (fn.deferrable === true) return true;
  // Prefix only: a substring test would defer unrelated tools by accident.
  return nameOf(toolDef).startsWith('mcp_');
}

/** Split tools into "never defer" and "may defer" (Python `classify_tools`). */
export function classifyTools(
  toolDefs: readonly ToolDef[],
  config: ToolSearchConfig
): { core: ToolDef[]; deferrable: ToolDef[] } {
  const coreNames = config.coreTools ?? PRAISONAI_CORE_TOOLS;
  const core: ToolDef[] = [];
  const deferrable: ToolDef[] = [];
  for (const toolDef of toolDefs) {
    const name = nameOf(toolDef);
    if (coreNames.has(name)) {
      core.push(toolDef);
    } else if (isToolDeferrable(toolDef)) {
      deferrable.push(toolDef);
    } else {
      // Invariant 2: an unknown tool stays visible rather than vanishing.
      core.push(toolDef);
    }
  }
  return { core, deferrable };
}

/** Rough schema cost (Python `estimate_tool_schema_tokens`: ~3.5 chars/token). */
export function estimateToolSchemaTokens(toolDefs: readonly ToolDef[]): number {
  if (toolDefs.length === 0) return 0;
  let totalChars = 0;
  for (const toolDef of toolDefs) {
    try {
      totalChars += JSON.stringify(toolDef).length;
    } catch {
      totalChars += String(toolDef).length;
    }
  }
  return Math.trunc(totalChars / 3.5);
}

/** Python `should_defer_tools`: the `auto` threshold rule. */
export function shouldDeferTools(
  deferrable: readonly ToolDef[],
  config: ToolSearchConfig,
  contextLength?: number
): boolean {
  const enabled = config.enabled;
  if (enabled === 'off' || enabled === false) return false;
  if (enabled === 'on' || enabled === true) return true;
  if (enabled !== 'auto') return false;
  if (deferrable.length === 0) return false;
  const contextLimit = contextLength ?? 20000;
  const thresholdTokens = Math.trunc(contextLimit * (config.thresholdPct / 100));
  return estimateToolSchemaTokens(deferrable) >= thresholdTokens;
}

/** One catalog row the model can search. */
export interface CatalogEntry {
  name: string;
  description: string;
}

function catalogOf(deferrable: readonly ToolDef[]): CatalogEntry[] {
  const catalog: CatalogEntry[] = [];
  for (const toolDef of deferrable) {
    const fn = functionOf(toolDef);
    const name = typeof fn.name === 'string' ? fn.name : '';
    if (!name) continue;
    catalog.push({ name, description: typeof fn.description === 'string' ? fn.description : '' });
  }
  return catalog;
}

function tokenize(text: string): string[] {
  if (!text) return [];
  return text.toLowerCase().match(/\b[a-z0-9_]+\b/g) ?? [];
}

/**
 * BM25 over the tool catalog, inlined so tool search adds no dependency
 * (Python `BM25ToolSearcher`, same k1/b constants).
 */
export class BM25ToolSearcher {
  private readonly termFrequencies: Array<Map<string, number>> = [];
  private readonly docFrequencies = new Map<string, number>();
  private readonly totalDocs: number;
  private readonly avgDocLength: number;

  constructor(private readonly catalog: readonly CatalogEntry[]) {
    this.totalDocs = catalog.length;
    let totalLength = 0;
    for (const item of catalog) {
      const tokens = tokenize(`${item.name} ${item.description}`);
      const tf = new Map<string, number>();
      for (const token of tokens) tf.set(token, (tf.get(token) ?? 0) + 1);
      this.termFrequencies.push(tf);
      totalLength += tokens.length;
      for (const token of new Set(tokens)) {
        this.docFrequencies.set(token, (this.docFrequencies.get(token) ?? 0) + 1);
      }
    }
    this.avgDocLength = catalog.length > 0 ? totalLength / catalog.length : 0;
  }

  search(query: string, limit: number = 5): CatalogEntry[] {
    const queryTokens = tokenize(query);
    if (queryTokens.length === 0 || this.avgDocLength === 0) return [];
    const k1 = 1.5;
    const b = 0.75;
    const scored: Array<{ score: number; item: CatalogEntry }> = [];
    for (let i = 0; i < this.catalog.length; i++) {
      const tf = this.termFrequencies[i];
      let docLength = 0;
      for (const count of tf.values()) docLength += count;
      let score = 0;
      for (const token of queryTokens) {
        const termFreq = tf.get(token);
        if (termFreq === undefined) continue;
        const df = this.docFrequencies.get(token) ?? 0;
        const idf = Math.log((this.totalDocs - df + 0.5) / (df + 0.5));
        score += idf * (termFreq * (k1 + 1)) / (termFreq + k1 * (1 - b + b * (docLength / this.avgDocLength)));
      }
      if (score > 0) scored.push({ score, item: this.catalog[i] });
    }
    scored.sort((a, b2) => b2.score - a.score);
    return scored.slice(0, limit).map((s) => s.item);
  }
}

/** Python `search_catalog`: BM25 for a substantial query, substring otherwise. */
export function searchCatalog(
  deferrable: readonly ToolDef[],
  query: string,
  limit: number = 5
): CatalogEntry[] {
  if (deferrable.length === 0 || query.trim().length === 0) return [];
  const catalog = catalogOf(deferrable);
  if (catalog.length === 0) return [];

  if (query.trim().length >= 3) {
    const results = new BM25ToolSearcher(catalog).search(query, limit);
    if (results.length > 0) return results;
  }

  const queryLower = query.toLowerCase();
  const matches: CatalogEntry[] = [];
  for (const item of catalog) {
    if (item.name.toLowerCase().includes(queryLower) || item.description.toLowerCase().includes(queryLower)) {
      matches.push(item);
      if (matches.length >= limit) break;
    }
  }
  return matches;
}

/** The three bridge tool schemas (Python `bridge_tool_schemas`). */
export function bridgeToolSchemas(): ToolDef[] {
  return [
    {
      type: 'function',
      function: {
        name: 'tool_search',
        description: 'Search for available tools by name or functionality. Use this to discover what tools are available before using them.',
        parameters: {
          type: 'object',
          properties: {
            query: { type: 'string', description: 'Search query describing the tool functionality you need' },
            limit: { type: 'integer', description: 'Maximum number of results to return', default: 5, minimum: 1, maximum: 20 },
          },
          required: ['query'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: 'tool_describe',
        description: 'Get the full schema and documentation for a specific tool. Use this after tool_search to understand how to use a tool.',
        parameters: {
          type: 'object',
          properties: {
            tool_name: { type: 'string', description: 'Exact name of the tool to describe' },
          },
          required: ['tool_name'],
        },
      },
    },
    {
      type: 'function',
      function: {
        name: 'tool_call',
        description: 'Execute a tool with the given arguments. Use this after tool_describe to actually run the tool.',
        parameters: {
          type: 'object',
          properties: {
            tool_name: { type: 'string', description: 'Exact name of the tool to execute' },
            tool_args: { type: 'object', description: 'Arguments to pass to the tool', additionalProperties: true },
          },
          required: ['tool_name', 'tool_args'],
        },
      },
    },
  ];
}

/** What the turn needs to know once tools have been assembled. */
export interface ToolSearchAssembly {
  /** The tool list actually sent to the model. */
  tools: ToolDef[];
  /** Whether deferrable tools were replaced by the bridge. */
  bridgeMode: boolean;
  /** Tools kept out of the request; the bridge resolves calls against these. */
  deferrableTools: ToolDef[];
  /** Name/description rows the model can search. */
  catalog: CatalogEntry[];
  config: ToolSearchConfig;
}

/**
 * Decide between bridge mode and pass-through, and build the tool list for
 * the request (Python `assemble_tool_defs`).
 */
export function assembleToolDefs(
  toolDefs: readonly ToolDef[] | undefined,
  config: ToolSearchConfig,
  contextLength?: number
): ToolSearchAssembly {
  const tools = toolDefs ? [...toolDefs] : [];
  const passThrough: ToolSearchAssembly = {
    tools, bridgeMode: false, deferrableTools: [], catalog: [], config,
  };
  if (config.enabled === 'off' || config.enabled === false) return passThrough;

  const { core, deferrable } = classifyTools(tools, config);
  if (deferrable.length === 0 || !shouldDeferTools(deferrable, config, contextLength)) return passThrough;

  return {
    tools: [...core, ...bridgeToolSchemas()],
    bridgeMode: true,
    deferrableTools: deferrable,
    catalog: catalogOf(deferrable),
    config,
  };
}

/** Python `dispatch_tool_search`. */
export function dispatchToolSearch(
  query: string,
  limit: number | undefined,
  deferrable: readonly ToolDef[],
  config: ToolSearchConfig
): Record<string, unknown> {
  let searchLimit = limit ?? config.searchDefaultLimit;
  searchLimit = Math.min(searchLimit, config.maxSearchLimit);
  searchLimit = Math.max(searchLimit, 1);
  return {
    query,
    results: searchCatalog(deferrable, query, searchLimit),
    total_available: deferrable.length,
  };
}

/** Python `dispatch_tool_describe`. */
export function dispatchToolDescribe(
  toolName: string,
  deferrable: readonly ToolDef[]
): Record<string, unknown> {
  for (const toolDef of deferrable) {
    if (nameOf(toolDef) === toolName) {
      return { tool_name: toolName, schema: toolDef, found: true };
    }
  }
  return {
    tool_name: toolName,
    error: `Tool '${toolName}' not found in available tools`,
    found: false,
  };
}

/**
 * Unwrap a `tool_call` bridge invocation into the real call
 * (Python `resolve_underlying_call`). Anything else is returned unchanged.
 */
export function resolveUnderlyingCall(
  toolName: string,
  toolArgs: Record<string, unknown>
): { name: string; args: Record<string, unknown> } {
  if (toolName !== 'tool_call') return { name: toolName, args: toolArgs };
  if (toolArgs === null || typeof toolArgs !== 'object' || Array.isArray(toolArgs)) {
    throw new TypeError(
      'tool_call expects an object for tool_args. Ensure the model output is properly formatted.'
    );
  }
  const realName = toolArgs.tool_name;
  if (typeof realName !== 'string' || realName.length === 0) {
    throw new Error("tool_call requires a 'tool_name' parameter");
  }
  const realArgs = toolArgs.tool_args;
  return {
    name: realName,
    args: realArgs !== null && typeof realArgs === 'object' && !Array.isArray(realArgs)
      ? (realArgs as Record<string, unknown>)
      : {},
  };
}

/**
 * Resolve the constructor option into a config, or `undefined` when tool
 * search is off. Mirrors `ToolSearchConfig.fromRaw` plus the `false` fast path.
 */
export function resolveToolSearch(
  input: boolean | string | Record<string, unknown> | undefined | null
): ToolSearchConfig | undefined {
  if (input === undefined || input === null || input === false) return undefined;
  const config = ToolSearchConfig.fromRaw(input);
  if (config.enabled === 'off' || config.enabled === false) return undefined;
  return config;
}
