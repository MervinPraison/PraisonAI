import {
  ToolsetRegistry,
  ToolsetSpec,
  TOOLSET_TOOL_ID_MAP,
  toolsetToolId,
  getToolsetRegistry,
  registerToolset,
  resolveToolset,
  resolveToolsets,
  resolveToolsetsForModel,
  listToolsets,
  getToolset,
  unregisterToolset,
  hasToolset,
  resolveToolsetBuiltinIds,
} from '../../../src/toolsets';
import { registerProfile, resetHarnessRegistry, HarnessProfile } from '../../../src/model-harness';

describe('ToolsetSpec', () => {
  it('applies Python dataclass defaults', () => {
    const spec = new ToolsetSpec({ name: 'x' });
    expect(spec).toEqual({ name: 'x', tools: [], includes: [], description: '' });
  });

  it('copies list inputs so callers cannot mutate the spec', () => {
    const tools = ['a'];
    const spec = new ToolsetSpec({ name: 'x', tools });
    tools.push('b');
    expect(spec.tools).toEqual(['a']);
  });
});

describe('ToolsetRegistry', () => {
  let registry: ToolsetRegistry;

  beforeEach(() => {
    registry = new ToolsetRegistry();
    resetHarnessRegistry();
  });

  describe('registration', () => {
    it('registers and resolves a flat toolset', () => {
      registry.registerToolset('web', ['search', 'crawl']);
      expect(registry.resolveToolset('web')).toEqual(['search', 'crawl']);
    });

    it('silently keeps the original when re-registered without overwrite (Python behaviour)', () => {
      registry.registerToolset('web', ['search']);
      expect(() => registry.registerToolset('web', ['other'])).not.toThrow();
      expect(registry.resolveToolset('web')).toEqual(['search']);
    });

    it('replaces the toolset when overwrite is true', () => {
      registry.registerToolset('web', ['search']);
      registry.registerToolset('web', ['other'], null, 'new', true);
      expect(registry.resolveToolset('web')).toEqual(['other']);
      expect(registry.getToolset('web')?.description).toBe('new');
    });

    it('unregisters and reports whether anything was removed', () => {
      registry.registerToolset('web', ['search']);
      expect(registry.unregisterToolset('web')).toBe(true);
      expect(registry.unregisterToolset('web')).toBe(false);
    });

    it('getToolset returns a defensive copy, or null when missing', () => {
      registry.registerToolset('web', ['search']);
      const copy = registry.getToolset('web');
      expect(copy).toBeInstanceOf(ToolsetSpec);
      copy!.tools.push('mutated');
      expect(registry.resolveToolset('web')).toEqual(['search']);
      expect(registry.getToolset('nope')).toBeNull();
    });
  });

  describe('include resolution', () => {
    it('recursively expands includes, preserving order and de-duplicating', () => {
      registry.registerToolset('web', ['search', 'read_file']);
      registry.registerToolset('files', ['read_file', 'write_file']);
      registry.registerToolset('research', ['summarise'], ['web', 'files']);
      registry.registerToolset('deep', null, ['research', 'web']);
      expect(registry.resolveToolset('deep')).toEqual(['summarise', 'search', 'read_file', 'write_file']);
    });

    it('throws for an unknown toolset', () => {
      expect(() => registry.resolveToolset('missing')).toThrow('Toolset not found: missing');
    });

    it('throws for an unknown include nested inside a known toolset', () => {
      registry.registerToolset('outer', ['a'], ['inner']);
      expect(() => registry.resolveToolset('outer')).toThrow('Toolset not found: inner');
    });

    it('detects a direct cycle', () => {
      registry.registerToolset('a', ['x'], ['b']);
      registry.registerToolset('b', ['y'], ['a']);
      expect(() => registry.resolveToolset('a')).toThrow('Circular dependency detected in toolset: a');
    });

    it('detects a self-include cycle', () => {
      registry.registerToolset('loop', ['x'], ['loop']);
      expect(() => registry.resolveToolset('loop')).toThrow('Circular dependency detected in toolset: loop');
    });

    it('allows a diamond (same toolset included twice on different branches) without a false cycle', () => {
      registry.registerToolset('base', ['b']);
      registry.registerToolset('left', ['l'], ['base']);
      registry.registerToolset('right', ['r'], ['base']);
      registry.registerToolset('top', null, ['left', 'right']);
      expect(registry.resolveToolset('top')).toEqual(['l', 'b', 'r']);
    });

    it('resolveToolsets merges several toolsets and de-duplicates across them', () => {
      registry.registerToolset('a', ['x', 'y']);
      registry.registerToolset('b', ['y', 'z']);
      expect(registry.resolveToolsets(['a', 'b'])).toEqual(['x', 'y', 'z']);
    });
  });

  describe('prebuilt toolsets', () => {
    it('loads the Python prebuilt toolsets on first read', () => {
      expect(registry.listToolsets()).toEqual([
        'web', 'files', 'code', 'system', 'scraping', 'research', 'safe', 'development', 'coding',
      ]);
      expect(registry.resolveToolset('web')).toEqual([
        'internet_search', 'duckduckgo', 'searxng_search', 'tavily_search', 'exa_search',
      ]);
    });

    it('resolves the composed research toolset like Python', () => {
      expect(registry.resolveToolset('research')).toEqual([
        'internet_search', 'duckduckgo', 'searxng_search', 'tavily_search', 'exa_search',
        'read_file', 'write_file', 'list_files', 'get_file_info', 'copy_file', 'move_file', 'delete_file',
        'scrape_page', 'extract_links', 'crawl', 'extract_text',
      ]);
    });

    it('has() and size reflect the prebuilt set; clear() resets and reloads lazily', () => {
      expect(registry.has('coding')).toBe(true);
      expect(registry.size).toBe(9);
      expect(String(registry)).toBe('ToolsetRegistry(toolsets=9)');
      registry.registerToolset('custom', ['c']);
      registry.clear();
      expect(registry.has('custom')).toBe(false);
      expect(registry.size).toBe(9);
    });

    it('a user toolset registered before first read is not clobbered by the prebuilt load', () => {
      registry.registerToolset('web', ['mine']);
      expect(registry.resolveToolset('web')).toEqual(['mine']);
    });
  });

  describe('builtin id mapping (TypeScript-only)', () => {
    it('maps only Python names that have a TypeScript builtin', () => {
      expect(toolsetToolId('tavily_search')).toBe('tavily-search');
      expect(toolsetToolId('read_file')).toBeNull();
      expect(toolsetToolId('toString')).toBeNull();
      expect(Object.isFrozen(TOOLSET_TOOL_ID_MAP)).toBe(true);
    });

    it('resolves a toolset to only the builtin ids present', () => {
      expect(registry.resolveToolsetBuiltinIds(['web'])).toEqual(['tavily-search', 'exa']);
      expect(registry.resolveToolsetBuiltinIds(['files'])).toEqual([]);
      expect(registry.resolveToolsetBuiltinIds(['research', 'code'])).toEqual([
        'tavily-search', 'exa', 'firecrawl-scrape', 'firecrawl-crawl', 'code-execution',
      ]);
    });
  });

  describe('model-aware edit ordering', () => {
    it('advertises apply_patch first for Anthropic models', () => {
      expect(registry.resolveToolsetForModel('coding', 'claude-opus-4')).toEqual([
        'read_file', 'apply_patch', 'edit_file', 'grep', 'glob', 'execute_command',
        'todo_add', 'todo_list', 'todo_update',
      ]);
    });

    it('keeps edit_file first for OpenAI models and leaves unknown/falsy models untouched', () => {
      const base = registry.resolveToolset('coding');
      expect(registry.resolveToolsetForModel('coding', 'gpt-4o')).toEqual(base);
      expect(registry.resolveToolsetForModel('coding', 'llama-3')).toEqual(base);
      expect(registry.resolveToolsetForModel('coding', null)).toEqual(base);
      expect(registry.resolveToolsetForModel('coding', '')).toEqual(base);
    });

    it('does nothing when only one edit primitive is present', () => {
      registry.registerToolset('one', ['apply_patch', 'read_file']);
      expect(registry.resolveToolsetForModel('one', 'gpt-4o')).toEqual(['apply_patch', 'read_file']);
      registry.registerToolset('none', ['read_file']);
      expect(registry.resolveToolsetForModel('none', 'claude-3')).toEqual(['read_file']);
    });

    it('honours profiles registered at runtime and keeps every other tool in place', () => {
      registerProfile(['llama'], new HarnessProfile({ name: 'llama', preferredEditFormat: 'apply_patch' }));
      registry.registerToolset('mixed', ['edit_file', 'a', 'apply_patch', 'b']);
      expect(registry.resolveToolsetsForModel(['mixed'], 'LLAMA-3')).toEqual(['apply_patch', 'edit_file', 'a', 'b']);
    });
  });
});

describe('module-level toolset functions', () => {
  beforeEach(() => {
    getToolsetRegistry().clear();
  });

  it('share one global registry', () => {
    expect(getToolsetRegistry()).toBe(getToolsetRegistry());
    registerToolset('mine', ['t1'], null, 'desc');
    expect(hasToolset('mine')).toBe(true);
    expect(getToolset('mine')?.description).toBe('desc');
    expect(resolveToolset('mine')).toEqual(['t1']);
    expect(listToolsets()).toContain('mine');
    expect(resolveToolsets(['mine', 'safe'])).toEqual(['t1', 'internet_search', 'read_file', 'tavily_search']);
    expect(resolveToolsetsForModel(['coding'], 'claude-3')[1]).toBe('apply_patch');
    expect(resolveToolsetBuiltinIds(['safe'])).toEqual(['tavily-search']);
    expect(unregisterToolset('mine')).toBe(true);
    expect(hasToolset('mine')).toBe(false);
  });

  it('propagates the unknown-toolset error through the global helpers', () => {
    expect(() => resolveToolset('nope')).toThrow('Toolset not found: nope');
    expect(() => resolveToolsets(['web', 'nope'])).toThrow('Toolset not found: nope');
  });
});
