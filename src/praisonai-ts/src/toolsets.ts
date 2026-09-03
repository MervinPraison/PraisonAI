/**
 * Named toolset groups for organising tools into reusable collections.
 *
 * Port of `praisonaiagents/toolsets.py`. Toolsets are named groups of tool
 * names that can be enabled as a unit and composed via `includes`
 * (recursive, with cycle detection).
 *
 * ```ts
 * import { registerToolset, resolveToolset } from 'praisonai/toolsets';
 * registerToolset('web', ['internet_search', 'crawl4ai']);
 * registerToolset('files', ['read_file', 'write_file']);
 * registerToolset('research', undefined, ['web', 'files']);
 * resolveToolset('research'); // ['internet_search', 'crawl4ai', 'read_file', 'write_file']
 * ```
 *
 * Prebuilt toolsets carry the same Python tool names as
 * `toolsets.py::_load_prebuilt_toolsets`, so `resolveToolset('web')` returns
 * the same list on both sides. Only some of those names have a TypeScript
 * builtin under `src/tools/builtins`; {@link TOOLSET_TOOL_ID_MAP} records the
 * mapping and {@link resolveToolsetBuiltinIds} yields only the registry ids
 * that exist here — resolution never invents a tool.
 *
 * Python's `threading.RLock` / double-checked singleton are omitted: the
 * registry is single-threaded in JavaScript.
 */

import { resolveHarness } from './model-harness/profiles';

/** Constructor options for {@link ToolsetSpec} (Python dataclass fields). */
export interface ToolsetSpecConfig {
  /** Unique name for the toolset. */
  name: string;
  /** Tool names included directly in this toolset. Default `[]`. */
  tools?: string[];
  /** Other toolset names to include (recursive composition). Default `[]`. */
  includes?: string[];
  /** Optional description of the toolset's purpose. Default `""`. */
  description?: string;
}

/**
 * Specification for a named toolset group.
 *
 * Python parity: `toolsets.py::ToolsetSpec`.
 */
export class ToolsetSpec {
  name: string;
  tools: string[];
  includes: string[];
  description: string;

  constructor(config: ToolsetSpecConfig) {
    this.name = config.name;
    this.tools = config.tools ? [...config.tools] : [];
    this.includes = config.includes ? [...config.includes] : [];
    this.description = config.description ?? '';
  }
}

/**
 * Python prebuilt tool name → TypeScript builtin registry id
 * (`src/tools/builtins`, as registered by `registerBuiltinTools()`).
 *
 * Only names with a real TypeScript builtin appear here. Python names such as
 * `internet_search`, `duckduckgo`, `read_file` or `execute_command` have no
 * TypeScript builtin and are deliberately absent.
 */
export const TOOLSET_TOOL_ID_MAP: Readonly<Record<string, string>> = Object.freeze({
  tavily_search: 'tavily-search',
  exa_search: 'exa',
  execute_code: 'code-execution',
  scrape_page: 'firecrawl-scrape',
  crawl: 'firecrawl-crawl',
});

/** TypeScript builtin registry id for a Python tool name, or `null` when none exists. */
export function toolsetToolId(toolName: string): string | null {
  return Object.prototype.hasOwnProperty.call(TOOLSET_TOOL_ID_MAP, toolName)
    ? TOOLSET_TOOL_ID_MAP[toolName]
    : null;
}

/** Order-preserving de-duplication (Python `seen` / `unique_tools` loop). */
function uniqueInOrder(items: string[]): string[] {
  const seen = new Set<string>();
  const unique: string[] = [];
  for (const item of items) {
    if (!seen.has(item)) {
      seen.add(item);
      unique.push(item);
    }
  }
  return unique;
}

const EDIT_PRIMITIVES: ReadonlySet<string> = new Set(['edit_file', 'apply_patch']);

/**
 * Registry for managing named toolset groups.
 *
 * Python parity: `toolsets.py::ToolsetRegistry`. Provides registration and
 * resolution of toolset groups, with support for recursive composition via
 * includes.
 */
export class ToolsetRegistry {
  private readonly _toolsets = new Map<string, ToolsetSpec>();
  private _prebuiltLoaded = false;

  /**
   * Register a named toolset (Python `register_toolset`).
   *
   * As in Python, registering a name that already exists is a silent no-op
   * unless `overwrite` is true. Nothing is thrown.
   */
  registerToolset(
    name: string,
    tools: string[] | null = null,
    includes: string[] | null = null,
    description: string = '',
    overwrite: boolean = false,
  ): void {
    if (this._toolsets.has(name) && !overwrite) {
      return;
    }
    this._toolsets.set(
      name,
      new ToolsetSpec({
        name,
        tools: tools && tools.length ? [...tools] : [],
        includes: includes && includes.length ? [...includes] : [],
        description,
      }),
    );
  }

  /** Remove a toolset; true if removed, false if not found (Python `unregister_toolset`). */
  unregisterToolset(name: string): boolean {
    return this._toolsets.delete(name);
  }

  /**
   * Get a defensive copy of a toolset, or `null` if not found
   * (Python `get_toolset` returns `None`).
   */
  getToolset(name: string): ToolsetSpec | null {
    this._ensurePrebuiltLoaded();
    const spec = this._toolsets.get(name);
    if (spec === undefined) return null;
    return new ToolsetSpec({
      name: spec.name,
      tools: [...spec.tools],
      includes: [...spec.includes],
      description: spec.description,
    });
  }

  /** All registered toolset names, in registration order (Python `list_toolsets`). */
  listToolsets(): string[] {
    this._ensurePrebuiltLoaded();
    return Array.from(this._toolsets.keys());
  }

  /**
   * Resolve a toolset name to a flat, de-duplicated list of tool names
   * (Python `resolve_toolset`).
   *
   * @throws Error `Toolset not found: <name>` or
   *   `Circular dependency detected in toolset: <name>` (Python `ValueError`).
   */
  resolveToolset(name: string): string[] {
    this._ensurePrebuiltLoaded();
    return uniqueInOrder(this._resolveToolsetRecursive(name, new Set()));
  }

  /**
   * Resolve a toolset, honouring the model-family preferred edit format
   * (Python `resolve_toolset_for_model`).
   *
   * Behaves exactly like {@link resolveToolset} but, when the resolved
   * harness profile expresses a preferred edit primitive and both primitives
   * are present, the preferred one is advertised first. Falsy or unknown
   * models reproduce {@link resolveToolset} byte-for-byte.
   */
  resolveToolsetForModel(name: string, model: string | null = null): string[] {
    const tools = this.resolveToolset(name);
    if (!model) return tools;
    return ToolsetRegistry._applyPreferredEditOrder(tools, model);
  }

  /**
   * Resolve multiple toolsets to a flat, de-duplicated list of tool names
   * (Python `resolve_toolsets`).
   */
  resolveToolsets(names: string[]): string[] {
    const all: string[] = [];
    for (const name of names) {
      all.push(...this.resolveToolset(name));
    }
    return uniqueInOrder(all);
  }

  /**
   * Resolve multiple toolsets, honouring the model's preferred edit format
   * (Python `resolve_toolsets_for_model`).
   */
  resolveToolsetsForModel(names: string[], model: string | null = null): string[] {
    const tools = this.resolveToolsets(names);
    if (!model) return tools;
    return ToolsetRegistry._applyPreferredEditOrder(tools, model);
  }

  /**
   * TypeScript-only: resolve toolsets to the builtin registry ids that exist
   * under `src/tools/builtins` (see {@link TOOLSET_TOOL_ID_MAP}). Tool names
   * with no TypeScript builtin are dropped, so the result may be shorter than
   * {@link resolveToolsets} — or empty for toolsets such as `files`.
   */
  resolveToolsetBuiltinIds(names: string[]): string[] {
    const ids: string[] = [];
    for (const toolName of this.resolveToolsets(names)) {
      const id = toolsetToolId(toolName);
      if (id !== null) ids.push(id);
    }
    return uniqueInOrder(ids);
  }

  /**
   * Reorder edit primitives so the model's preferred one is advertised first
   * (Python `_apply_preferred_edit_order`). Never throws; any resolution
   * error leaves `tools` unchanged.
   */
  private static _applyPreferredEditOrder(tools: string[], model: string): string[] {
    let preferred: string | null;
    try {
      preferred = resolveHarness(model).preferredEditFormat;
    } catch {
      preferred = null;
    }
    if (!preferred || !tools.includes(preferred)) return tools;
    if (!tools.some((t) => EDIT_PRIMITIVES.has(t) && t !== preferred)) return tools;

    const reordered: string[] = [];
    let inserted = false;
    for (const tool of tools) {
      if (EDIT_PRIMITIVES.has(tool)) {
        if (!inserted) {
          reordered.push(preferred);
          reordered.push(...tools.filter((t) => EDIT_PRIMITIVES.has(t) && t !== preferred));
          inserted = true;
        }
        continue;
      }
      reordered.push(tool);
    }
    return reordered;
  }

  /** Recursive helper with cycle detection (Python `_resolve_toolset_recursive`). */
  private _resolveToolsetRecursive(name: string, visited: Set<string>): string[] {
    if (visited.has(name)) {
      throw new Error(`Circular dependency detected in toolset: ${name}`);
    }
    const toolset = this._toolsets.get(name);
    if (toolset === undefined) {
      throw new Error(`Toolset not found: ${name}`);
    }
    visited.add(name);

    const all = [...toolset.tools];
    for (const includeName of toolset.includes) {
      all.push(...this._resolveToolsetRecursive(includeName, new Set(visited)));
    }
    return all;
  }

  /** Ensure prebuilt toolsets are loaded exactly once (Python `_ensure_prebuilt_loaded`). */
  private _ensurePrebuiltLoaded(): void {
    if (!this._prebuiltLoaded) {
      this._loadPrebuiltToolsets();
      this._prebuiltLoaded = true;
    }
  }

  /**
   * Load the standard prebuilt toolsets (Python `_load_prebuilt_toolsets`).
   * Tool names are the Python names; see {@link TOOLSET_TOOL_ID_MAP} for which
   * of them have a TypeScript builtin.
   */
  private _loadPrebuiltToolsets(): void {
    this.registerToolset(
      'web',
      ['internet_search', 'duckduckgo', 'searxng_search', 'tavily_search', 'exa_search'],
      null,
      'Web search and crawling tools',
    );
    this.registerToolset(
      'files',
      ['read_file', 'write_file', 'list_files', 'get_file_info', 'copy_file', 'move_file', 'delete_file'],
      null,
      'File system operations',
    );
    this.registerToolset(
      'code',
      ['execute_code', 'analyze_code', 'format_code', 'lint_code'],
      null,
      'Python code execution and analysis',
    );
    this.registerToolset(
      'system',
      ['execute_command', 'list_processes', 'kill_process', 'get_system_info'],
      null,
      'System administration and shell operations',
    );
    this.registerToolset(
      'scraping',
      ['scrape_page', 'extract_links', 'crawl', 'extract_text'],
      null,
      'Web page scraping and content extraction',
    );
    this.registerToolset(
      'research',
      [],
      ['web', 'files', 'scraping'],
      'Complete research workflow with web search, file ops, and scraping',
    );
    this.registerToolset(
      'safe',
      ['internet_search', 'read_file', 'tavily_search'],
      null,
      'Minimal safe toolset for restricted environments',
    );
    this.registerToolset(
      'development',
      [],
      ['code', 'files', 'system'],
      'Complete development workflow with code execution, files, and system access',
    );
    this.registerToolset(
      'coding',
      [
        'read_file', 'edit_file', 'apply_patch',
        'grep', 'glob', 'execute_command',
        'todo_add', 'todo_list', 'todo_update',
      ],
      null,
      'Coding workflow with diff-based edits (edit_file for existing files, apply_patch to create new files), code search, and shell execution',
    );
  }

  /** Clear all registered toolsets; prebuilt toolsets reload on next access (Python `clear`). */
  clear(): void {
    this._toolsets.clear();
    this._prebuiltLoaded = false;
  }

  /** True if a toolset is registered (Python `__contains__`). */
  has(name: string): boolean {
    this._ensurePrebuiltLoaded();
    return this._toolsets.has(name);
  }

  /** Number of registered toolsets (Python `__len__`). */
  get size(): number {
    this._ensurePrebuiltLoaded();
    return this._toolsets.size;
  }

  /** Python `__repr__`. */
  toString(): string {
    return `ToolsetRegistry(toolsets=${this.size})`;
  }
}

let _globalRegistry: ToolsetRegistry | null = null;

/** The global toolset registry singleton (Python `get_toolset_registry`). */
export function getToolsetRegistry(): ToolsetRegistry {
  if (_globalRegistry === null) {
    _globalRegistry = new ToolsetRegistry();
  }
  return _globalRegistry;
}

/** Register a named toolset with the global registry (Python `register_toolset`). */
export function registerToolset(
  name: string,
  tools: string[] | null = null,
  includes: string[] | null = null,
  description: string = '',
  overwrite: boolean = false,
): void {
  getToolsetRegistry().registerToolset(name, tools, includes, description, overwrite);
}

/** Resolve a toolset name to a flat list of tool names (Python `resolve_toolset`). */
export function resolveToolset(name: string): string[] {
  return getToolsetRegistry().resolveToolset(name);
}

/** Resolve multiple toolset names to a flat list of tool names (Python `resolve_toolsets`). */
export function resolveToolsets(names: string[]): string[] {
  return getToolsetRegistry().resolveToolsets(names);
}

/**
 * Resolve multiple toolsets, honouring the model's preferred edit format
 * (Python `resolve_toolsets_for_model`).
 */
export function resolveToolsetsForModel(names: string[], model: string | null = null): string[] {
  return getToolsetRegistry().resolveToolsetsForModel(names, model);
}

/** All registered toolset names (Python `list_toolsets`). */
export function listToolsets(): string[] {
  return getToolsetRegistry().listToolsets();
}

/** Get a toolset by name, or `null` (Python `get_toolset`). */
export function getToolset(name: string): ToolsetSpec | null {
  return getToolsetRegistry().getToolset(name);
}

/** Remove a toolset from the global registry (Python `unregister_toolset`). */
export function unregisterToolset(name: string): boolean {
  return getToolsetRegistry().unregisterToolset(name);
}

/** Check if a toolset is registered (Python `has_toolset`). */
export function hasToolset(name: string): boolean {
  return getToolsetRegistry().has(name);
}

/**
 * TypeScript-only: builtin registry ids for the tools in `names` that exist
 * under `src/tools/builtins`. See {@link ToolsetRegistry.resolveToolsetBuiltinIds}.
 */
export function resolveToolsetBuiltinIds(names: string[]): string[] {
  return getToolsetRegistry().resolveToolsetBuiltinIds(names);
}
