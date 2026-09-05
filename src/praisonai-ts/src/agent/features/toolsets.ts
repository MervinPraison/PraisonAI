/**
 * Named toolset groups on an Agent (Python parity: `Agent(toolsets=[...])`,
 * `agent/agent.py` lines 2358-2392, over `toolsets.py`).
 *
 * `toolsets: ['web']` resolves the named group to its tool names, drops the
 * ones the agent already has, and attaches the rest. Resolution and
 * attachment are deliberately split:
 *
 * - {@link resolveToolsetToolNames} runs in the CONSTRUCTOR and throws on an
 *   unknown toolset name, exactly as Python does — a typo must not survive
 *   until the first model turn.
 * - {@link loadToolsetTools} runs on first use, because each builtin lives
 *   behind a dynamic import and pulling four provider SDKs into the module
 *   graph for an agent that never calls one is a cost nobody asked for.
 *
 * A Python tool name with no TypeScript builtin is reported and skipped:
 * `resolveToolsetBuiltinIds` never invents a tool, and silently pretending a
 * toolset was attached would be worse than saying it was not.
 */

import { resolveToolsetsForModel, toolsetToolId } from '../../toolsets';

/**
 * Python tool name → the TypeScript builtin module and factory that provides
 * it. Keyed by the registry id `toolsetToolId()` returns, so the two mappings
 * cannot drift apart.
 */
const BUILTIN_TOOL_FACTORIES: Readonly<Record<string, { module: string; entry: string }>> = Object.freeze({
  'tavily-search': { module: 'tavily', entry: 'tavilySearch' },
  exa: { module: 'exa', entry: 'exaSearch' },
  'code-execution': { module: 'code-execution', entry: 'codeExecution' },
  'firecrawl-scrape': { module: 'firecrawl', entry: 'firecrawlScrape' },
  'firecrawl-crawl': { module: 'firecrawl', entry: 'firecrawlCrawl' },
});

/**
 * The tool names a list of toolsets resolves to, ordered for `model`'s family
 * (Python `resolve_toolsets_for_model`). Throws on an unknown toolset name.
 */
export function resolveToolsetToolNames(names: readonly string[], model?: string): string[] {
  if (names.length === 0) return [];
  return resolveToolsetsForModel([...names], model ?? null);
}

/** A tool object the Agent can accept (`name` + `execute`). */
export interface ToolsetTool {
  name: string;
  description?: string;
  parameters?: Record<string, unknown>;
  execute: (...args: unknown[]) => unknown;
}

async function loadFactory(module: string, entry: string): Promise<((config?: unknown) => unknown) | null> {
  for (const suffix of ['/index.js', '', '.js']) {
    const specifier = ['..', '..', 'tools', 'builtins', module].join('/') + (suffix === '/index.js' ? '' : suffix);
    try {
      const loaded: Record<string, unknown> = await import(specifier);
      if (typeof loaded[entry] === 'function') return loaded[entry] as (config?: unknown) => unknown;
    } catch {
      // Try the next specifier shape; the caller is told if none worked.
    }
  }
  return null;
}

/**
 * Instantiate the TypeScript builtins behind `toolNames`, skipping those the
 * agent already has. `onWarning` is called once per name that has no
 * TypeScript builtin, so a partially-supported toolset is audible.
 */
export async function loadToolsetTools(
  toolNames: readonly string[],
  existingToolNames: ReadonlySet<string>,
  onWarning: (message: string) => void = () => {}
): Promise<ToolsetTool[]> {
  const tools: ToolsetTool[] = [];
  const seenIds = new Set<string>();
  const missing: string[] = [];

  for (const toolName of toolNames) {
    if (existingToolNames.has(toolName)) continue;
    const id = toolsetToolId(toolName);
    if (id === null) {
      missing.push(toolName);
      continue;
    }
    if (seenIds.has(id)) continue;
    seenIds.add(id);
    const spec = BUILTIN_TOOL_FACTORIES[id];
    if (!spec) {
      missing.push(toolName);
      continue;
    }
    const factory = await loadFactory(spec.module, spec.entry);
    if (!factory) {
      onWarning(`The toolset tool "${toolName}" could not be loaded from the "${spec.module}" builtin.`);
      continue;
    }
    const tool = factory() as ToolsetTool;
    if (!tool || typeof tool.execute !== 'function' || existingToolNames.has(tool.name)) continue;
    tools.push(tool);
  }

  if (missing.length > 0) {
    onWarning(
      `These toolset tools have no TypeScript builtin and were not attached: ${missing.join(', ')}.`
    );
  }
  return tools;
}
