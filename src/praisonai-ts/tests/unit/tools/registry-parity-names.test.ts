/**
 * The snake_case Python-parity names must resolve to the registry whose
 * SEMANTICS match `praisonaiagents/tools/registry.py` — the name-keyed one in
 * `tools/decorator.ts` — not to the factory registry in `tools/registry/`.
 *
 * Python reference:
 *   register_tool(tool, name=None, trust_level=None, dynamic_schema_overrides=None)
 *   get_tool(name) -> BaseTool | Callable | None
 *   validate_tool(tool) -> bool, raises ToolValidationError
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import {
  get_registry, register_tool, get_tool, validate_tool,
  has_tool, remove_tool, list_tools,
  ToolRegistry, FunctionTool, tool,
} from '../../../src/tools';
import { ToolValidationError } from '../../../src/tools/base';
import {
  ToolsRegistry, getToolsRegistry, resetToolsRegistry,
  registerToolFactory, createToolInstance, tryCreateToolInstance,
  ToolNotRegisteredError, ToolConstructionError,
} from '../../../src/tools/registry';

describe('Python-named tool helpers route to the Python-shaped registry', () => {
  beforeEach(() => {
    get_registry().clear();
    resetToolsRegistry();
  });

  it('get_registry() is the name-keyed ToolRegistry, not the factory ToolsRegistry', () => {
    expect(get_registry()).toBeInstanceOf(ToolRegistry);
    // Control: the factory registry is still reachable, under its own name.
    expect(getToolsRegistry()).toBeInstanceOf(ToolsRegistry);
    expect(get_registry() as unknown).not.toBe(getToolsRegistry() as unknown);
  });

  it('register_tool(myFunction) takes the callable you already have', async () => {
    function greet(name: string, greeting: string) {
      return `${greeting}, ${name}!`;
    }
    register_tool(greet);

    const registered = get_tool('greet');
    expect(registered).toBeInstanceOf(FunctionTool);
    // Named arguments from the model are mapped back onto positional params.
    await expect(registered!.execute({ name: 'Ada', greeting: 'Hi' })).resolves.toBe('Hi, Ada!');
    expect(registered!.getParameters().properties).toHaveProperty('greeting');
  });

  it('register_tool leaves a destructuring or single-object function alone', async () => {
    // Positional mapping would be wrong here: the function wants the whole
    // object, so the wrapper must hand it over untouched.
    const lookup = async ({ city }: { city: string }) => `weather in ${city}`;
    Object.defineProperty(lookup, 'name', { value: 'lookup' });
    register_tool(lookup);
    await expect(get_tool('lookup')!.execute({ city: 'Paris' })).resolves.toBe('weather in Paris');

    // Control: a positional signature IS mapped.
    function shout(word: string) { return word.toUpperCase(); }
    register_tool(shout);
    await expect(get_tool('shout')!.execute({ word: 'hi' })).resolves.toBe('HI');
  });

  it('register_tool passes a FunctionTool through unchanged', () => {
    const t = tool({ name: 'echo', description: 'echo', execute: async (p: any) => p });
    register_tool(t);
    expect(get_tool('echo')).toBe(t);
  });

  it('register_tool honours name, trustLevel and dynamicSchemaOverrides', () => {
    const t = tool({ name: 'original', description: 'd', execute: async () => 'x' });
    register_tool(t, {
      name: 'renamed',
      trustLevel: 'external',
      dynamicSchemaOverrides: (schema) => ({ ...schema, properties: { extra: { type: 'string' } } }),
    });
    expect(get_tool('renamed')).toBe(t);
    expect(get_registry().getTrustLevel('renamed')).toBe('external');
    expect(get_registry().getDefinitions()[0].parameters.properties).toHaveProperty('extra');
    // Control: an unknown trust level is rejected rather than silently kept.
    expect(() => get_registry().register(t, { name: 'x', trustLevel: 'sort-of' })).toThrow(/Invalid trustLevel/);
  });

  it('get_tool(name) LOOKS UP a tool and returns undefined when absent', () => {
    expect(get_tool('never-registered')).toBeUndefined();
    // Control: a registered name resolves.
    register_tool(tool({ name: 'present', description: 'd', execute: async () => 1 }));
    expect(get_tool('present')).toBeDefined();
  });

  it('has_tool / remove_tool / list_tools mirror the Python helpers', () => {
    register_tool(tool({ name: 'tmp', description: 'd', execute: async () => 1 }));
    expect(has_tool('tmp')).toBe(true);
    expect(list_tools()).toContain('tmp');
    expect(remove_tool('tmp')).toBe(true);
    expect(has_tool('tmp')).toBe(false);
    // Control: removing something absent reports false rather than throwing.
    expect(remove_tool('tmp')).toBe(false);
  });

  it('register_tool skips a duplicate name (Python) instead of throwing', () => {
    const first = tool({ name: 'dup', description: 'd', execute: async () => 'first' });
    const second = tool({ name: 'dup', description: 'd', execute: async () => 'second' });
    register_tool(first);
    expect(() => register_tool(second)).not.toThrow();
    expect(get_tool('dup')).toBe(first);
    // Control: overwrite is opt-in, and the direct registry API still throws.
    register_tool(second, { overwrite: true });
    expect(get_tool('dup')).toBe(second);
    expect(() => get_registry().register(first)).toThrow(/already registered/);
  });

  it('validate_tool(tool) takes the tool object and raises on a malformed one', () => {
    const broken = tool({ name: '', description: 'd', execute: async () => 1 });
    expect(() => validate_tool(broken)).toThrow(ToolValidationError);
    // Control: a well-formed tool validates to true.
    expect(validate_tool(tool({ name: 'ok', description: 'd', execute: async () => 1 }))).toBe(true);
    // Control: a non-tool is still rejected.
    expect(() => validate_tool(42)).toThrow(ToolValidationError);
  });
});

describe('factory registry keeps its own, unambiguous names', () => {
  beforeEach(() => resetToolsRegistry());

  const meta = {
    id: 'demo', displayName: 'Demo', description: 'demo', tags: [],
    packageName: 'path', requiredEnv: [], capabilities: {}, install: { npm: 'npm i path' },
  } as any;

  it('a broken tool is distinguishable from a missing one', () => {
    registerToolFactory({ ...meta, id: 'broken' }, () => { throw new Error('no API key'); });

    // Was: both cases returned null, so a build failure looked like "not found".
    expect(() => createToolInstance('broken')).toThrow(ToolConstructionError);
    expect(() => tryCreateToolInstance('broken')).toThrow(/failed to build: no API key/);

    // Control: a genuinely unregistered id.
    expect(tryCreateToolInstance('absent')).toBeNull();
    expect(() => createToolInstance('absent')).toThrow(ToolNotRegisteredError);
  });

  it('registerToolFactory feeds the factory registry, not the Python one', () => {
    registerToolFactory(meta, () => ({ name: 'demo', execute: async () => 'ok' }) as any);
    expect(getToolsRegistry().has('demo')).toBe(true);
    // Control: the Python-named registry is untouched by a factory registration.
    expect(get_tool('demo')).toBeUndefined();
  });
});
