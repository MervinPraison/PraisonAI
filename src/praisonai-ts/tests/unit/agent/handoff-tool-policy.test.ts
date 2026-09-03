/**
 * HandoffToolPolicy parity tests - Python `HandoffToolPolicy` (mode +
 * blocked_tools) and how `Handoff.execute` applies it to the target's tools.
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import {
  Handoff,
  HandoffError,
  HandoffToolPolicyMode,
  DEFAULT_HANDOFF_TOOL_POLICY,
  resolveHandoffToolPolicy,
  handoffToolName,
  listAgentTools,
  type HandoffContext,
} from '../../../src/agent/handoff';
import { tool, ToolRegistry } from '../../../src/tools/decorator';
import { resetParityNotices } from '../../../src/utils/parity-notice';

process.env.PRAISONAI_PARITY_SILENT = '1';

const SEARCH = { name: 'search' };
const WRITE = { name: 'write' };
const SHELL = { name: 'shell' };

/**
 * A target whose tools live in a plain `tools` array and whose `chat` has
 * no options slot: the boundary is enforced by scoping `tools` for the call.
 */
function arrayAgent(name: string, tools: unknown[]) {
  const agent: any = {
    name,
    tools,
    seen: [] as unknown[][],
    calls: [] as unknown[][],
    async chat(...args: unknown[]) {
      agent.calls.push(args);
      agent.seen.push([...agent.tools]);
      return { text: `${name} ok` };
    },
  };
  return agent;
}

/** A source agent: only its tool names matter. */
function sourceWith(tools: unknown[]) {
  return { name: 'source', tools, chat: async () => ({ text: '' }) };
}

const ctx = (extra: Partial<HandoffContext> = {}): HandoffContext => ({
  messages: [],
  lastMessage: 'go',
  ...extra,
});

const names = (tools: unknown[]) => tools.map(handoffToolName);

describe('HandoffToolPolicy (Python parity)', () => {
  beforeEach(() => resetParityNotices());

  describe('HandoffToolPolicyMode', () => {
    it('has exactly the Python literal values', () => {
      expect(HandoffToolPolicyMode.INTERSECT).toBe('intersect');
      expect(HandoffToolPolicyMode.PASSTHROUGH).toBe('passthrough');
      expect(Object.values(HandoffToolPolicyMode).sort()).toEqual(['intersect', 'passthrough']);
    });
  });

  describe('resolveHandoffToolPolicy', () => {
    it('defaults to intersect mode with nothing blocked, like HandoffToolPolicy()', () => {
      expect(DEFAULT_HANDOFF_TOOL_POLICY).toEqual({ mode: 'intersect', blockedTools: [] });
      expect(resolveHandoffToolPolicy()).toEqual({ mode: 'intersect', blockedTools: [] });
      expect(resolveHandoffToolPolicy({})).toEqual({ mode: 'intersect', blockedTools: [] });
    });

    it('keeps an explicit mode and copies blockedTools', () => {
      const blocked = ['shell'];
      const resolved = resolveHandoffToolPolicy({ mode: 'passthrough', blockedTools: blocked });
      expect(resolved).toEqual({ mode: 'passthrough', blockedTools: ['shell'] });
      expect(resolved.blockedTools).not.toBe(blocked);
    });

    it('rejects an unknown mode', () => {
      expect(() => resolveHandoffToolPolicy({ mode: 'allow' as any })).toThrow(HandoffError);
    });
  });

  describe('handoffToolName / listAgentTools', () => {
    it('reads every tool shape the agents hold', () => {
      function lookup() {}
      expect(handoffToolName(lookup)).toBe('lookup');
      expect(handoffToolName({ name: 'search' })).toBe('search');
      expect(handoffToolName({ type: 'function', function: { name: 'write' } })).toBe('write');
      expect(handoffToolName(tool({ name: 'shell', execute: async () => 1 }))).toBe('shell');
      expect(handoffToolName('raw')).toBe('raw');
    });

    it('prefers a tools array, then getTools(), then nothing', () => {
      expect(listAgentTools({ name: 'a', chat: async () => '', tools: [SEARCH] })).toEqual([SEARCH]);
      expect(listAgentTools({ name: 'b', chat: async () => '', getTools: () => [WRITE] })).toEqual([WRITE]);
      expect(listAgentTools({ name: 'c', chat: async () => '' })).toEqual([]);
      expect(listAgentTools(undefined)).toEqual([]);
    });
  });

  describe('HandoffConfig.toolPolicy', () => {
    it("defaults to Python's HandoffToolPolicy()", () => {
      const h = new Handoff({ agent: arrayAgent('t', []) });
      expect(h.config.toolPolicy).toEqual({ mode: 'intersect', blockedTools: [] });
    });

    it('is taken from the nested config block when not given at the top level', () => {
      const h = new Handoff({ agent: arrayAgent('t', []), config: { toolPolicy: { mode: 'passthrough' } } });
      expect(h.config.toolPolicy.mode).toBe('passthrough');
    });

    it('top-level toolPolicy wins over the nested block', () => {
      const h = new Handoff({
        agent: arrayAgent('t', []),
        toolPolicy: { blockedTools: ['shell'] },
        config: { toolPolicy: { mode: 'passthrough', blockedTools: ['write'] } },
      });
      expect(h.config.toolPolicy).toEqual({ mode: 'intersect', blockedTools: ['shell'] });
    });
  });

  describe('computeEffectiveTools', () => {
    const target = () => arrayAgent('target', [SEARCH, WRITE, SHELL]);

    it('intersect (default): only tools the source also has', () => {
      const h = new Handoff({ agent: target() });
      expect(names(h.computeEffectiveTools(sourceWith([SEARCH, SHELL, { name: 'other' }]))!)).toEqual(['search', 'shell']);
    });

    it('intersect: blockedTools are stripped even when shared', () => {
      const h = new Handoff({ agent: target(), toolPolicy: { blockedTools: ['shell'] } });
      expect(names(h.computeEffectiveTools(sourceWith([SEARCH, SHELL]))!)).toEqual(['search']);
    });

    it('intersect: an empty intersection is [] (no tools), never a fallback to the full set', () => {
      const h = new Handoff({ agent: target() });
      expect(h.computeEffectiveTools(sourceWith([{ name: 'unrelated' }]))).toEqual([]);
    });

    it('intersect: no source agent means no shared tools, so none at all', () => {
      const h = new Handoff({ agent: target() });
      expect(h.computeEffectiveTools(undefined)).toEqual([]);
    });

    it('passthrough with nothing blocked is unrestricted (null)', () => {
      const h = new Handoff({ agent: target(), toolPolicy: { mode: 'passthrough' } });
      expect(h.computeEffectiveTools(sourceWith([]))).toBeNull();
    });

    it('passthrough with blockedTools keeps everything else, ignoring the source', () => {
      const h = new Handoff({ agent: target(), toolPolicy: { mode: 'passthrough', blockedTools: ['write'] } });
      expect(names(h.computeEffectiveTools(sourceWith([]))!)).toEqual(['search', 'shell']);
    });

    it('returns the target\'s own tool objects, not copies', () => {
      const t = target();
      const h = new Handoff({ agent: t });
      const [first] = h.computeEffectiveTools(sourceWith([SEARCH]))!;
      expect(first).toBe(t.tools[0]);
    });
  });

  describe('execute applies the policy to what the target sees', () => {
    it('control: passthrough leaves the target with its full tool set and a bare chat(prompt)', async () => {
      const t = arrayAgent('target', [SEARCH, WRITE, SHELL]);
      const h = new Handoff({ agent: t, toolPolicy: { mode: 'passthrough' } });
      const result = await h.execute(ctx({ sourceAgent: sourceWith([SEARCH]) }));
      expect(result.response).toBe('target ok');
      expect(names(t.seen[0])).toEqual(['search', 'write', 'shell']);
      expect(t.calls[0]).toEqual(['go']);
    });

    it('intersect (default): the target only sees the shared tools during the call', async () => {
      const t = arrayAgent('target', [SEARCH, WRITE, SHELL]);
      const h = new Handoff({ agent: t });
      await h.execute(ctx({ sourceAgent: sourceWith([WRITE, SHELL]) }));
      expect(names(t.seen[0])).toEqual(['write', 'shell']);
    });

    it('intersect + blockedTools: shared but blocked tools are gone too', async () => {
      const t = arrayAgent('target', [SEARCH, WRITE, SHELL]);
      const h = new Handoff({ agent: t, toolPolicy: { blockedTools: ['shell'] } });
      await h.execute(ctx({ sourceAgent: sourceWith([WRITE, SHELL]) }));
      expect(names(t.seen[0])).toEqual(['write']);
    });

    it('intersect without a source agent: the target runs with no tools', async () => {
      const t = arrayAgent('target', [SEARCH, WRITE, SHELL]);
      const h = new Handoff({ agent: t });
      await h.execute(ctx());
      expect(t.seen[0]).toEqual([]);
    });

    it('passthrough + blockedTools: everything but the blocked tools', async () => {
      const t = arrayAgent('target', [SEARCH, WRITE, SHELL]);
      const h = new Handoff({ agent: t, toolPolicy: { mode: 'passthrough', blockedTools: ['write'] } });
      await h.execute(ctx());
      expect(names(t.seen[0])).toEqual(['search', 'shell']);
    });

    it('restores the target\'s tools after the call, and after a failure', async () => {
      const original = [SEARCH, WRITE, SHELL];
      const t = arrayAgent('target', original);
      const h = new Handoff({ agent: t });
      await h.execute(ctx({ sourceAgent: sourceWith([SEARCH]) }));
      expect(t.tools).toBe(original);

      const failing = arrayAgent('boom', original);
      failing.chat = async () => { throw new Error('down'); };
      const h2 = new Handoff({ agent: failing });
      await expect(h2.execute(ctx({ sourceAgent: sourceWith([SEARCH]) }))).rejects.toThrow('down');
      expect(failing.tools).toBe(original);
    });

    it('simple-Agent-style target: the filtered set goes through the per-call `tools` option', async () => {
      const original = [SEARCH, WRITE, SHELL];
      const calls: unknown[][] = [];
      let toolsDuringCall: unknown[] | undefined;
      const t: any = {
        name: 'simple',
        tools: original,
        // Same arity as Agent.chat(prompt, previousResult?, signal?, options?)
        async chat(prompt: string, previousResult?: string, signal?: AbortSignal, options?: any) {
          calls.push([prompt, previousResult, signal, options]);
          toolsDuringCall = t.tools;
          return 'simple ok';
        },
      };
      const h = new Handoff({ agent: t, toolPolicy: { blockedTools: ['shell'] } });
      const result = await h.execute(ctx({ sourceAgent: sourceWith([SEARCH, SHELL]) }));
      expect(result.response).toBe('simple ok');
      expect(calls[0][0]).toBe('go');
      expect(names((calls[0][3] as any).tools)).toEqual(['search']);
      // The agent's own list is untouched: the override is per call.
      expect(toolsDuringCall).toBe(original);
    });

    it('EnhancedAgent-style target: its ToolRegistry is scoped to the filtered set and restored', async () => {
      const search = tool({ name: 'search', execute: async () => 's' });
      const write = tool({ name: 'write', execute: async () => 'w' });
      const registry = new ToolRegistry().register(search).register(write);
      let seen: string[] = [];
      const t: any = {
        name: 'enhanced',
        toolRegistry: registry,
        getTools() { return t.toolRegistry.list(); },
        async chat() {
          seen = t.toolRegistry.list().map((x: any) => x.name);
          return { text: 'enhanced ok' };
        },
      };
      const h = new Handoff({ agent: t });
      await h.execute(ctx({ sourceAgent: sourceWith([{ name: 'write' }]) }));
      expect(seen).toEqual(['write']);
      expect(t.toolRegistry).toBe(registry);
      expect(registry.list().map(x => x.name)).toEqual(['search', 'write']);
    });
  });
});
