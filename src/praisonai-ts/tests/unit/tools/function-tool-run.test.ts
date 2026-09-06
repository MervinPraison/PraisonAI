/**
 * `FunctionTool.run()` — Python parity with `tools/decorator.py`
 * `FunctionTool.run(**kwargs)`, the name ported code calls.
 *
 * Python's `run()` returns the FULL result (the compact model-facing view is
 * `to_model_output`). Unlike Python's, this `run()` also passes through the
 * approval / restart-safety gates: Python can afford a raw `run()` because
 * `@tool(approval=...)` also registers the requirement in a process-wide
 * ApprovalRegistry keyed by tool name, which TypeScript does not have.
 */

import { describe, it, expect, beforeEach, afterEach } from '@jest/globals';
import { tool, FunctionTool, ToolNotRestartSafeError } from '../../../src/tools/decorator';
import {
  ApprovalManager, setApprovalManager, ToolApprovalDeniedError,
} from '../../../src/ai/tool-approval';

function denyingManager(): ApprovalManager {
  const m = new ApprovalManager();
  m.onApprovalRequest(async () => false);
  return m;
}

function approvingManager(): ApprovalManager {
  const m = new ApprovalManager();
  m.onApprovalRequest(async () => true);
  return m;
}

describe('FunctionTool.run()', () => {
  afterEach(() => setApprovalManager(new ApprovalManager()));

  it('exists and returns the full result, where execute() returns the model view', async () => {
    const t = tool({
      name: 'lookup',
      description: 'Look something up',
      execute: async () => ({ rows: [1, 2, 3], meta: { ms: 12 } }),
      toModelOutput: (r: any) => ({ count: r.rows.length }),
    });

    expect(typeof t.run).toBe('function');
    await expect(t.run({})).resolves.toEqual({ rows: [1, 2, 3], meta: { ms: 12 } });
    // Control: execute() still applies toModelOutput, unchanged.
    await expect(t.execute({})).resolves.toEqual({ count: 3 });
  });

  it('run() passes params through like execute()', async () => {
    const t = tool({
      name: 'add',
      description: 'add',
      execute: async ({ a, b }: { a: number; b: number }) => a + b,
    });
    await expect(t.run({ a: 2, b: 3 })).resolves.toBe(5);
  });

  it('run() is gated by approval, not a second ungated door', async () => {
    const calls: string[] = [];
    const gated = tool({
      name: 'refund_order',
      description: 'Refund an order',
      approval: true,
      execute: async () => { calls.push('ran'); return 'refunded'; },
    });

    setApprovalManager(denyingManager());
    await expect(gated.run({ orderId: '1' })).rejects.toBeInstanceOf(ToolApprovalDeniedError);
    await expect(gated.execute({ orderId: '1' })).rejects.toBeInstanceOf(ToolApprovalDeniedError);
    expect(calls).toEqual([]);

    // Control 1: the same tool runs once approval is granted.
    setApprovalManager(approvingManager());
    await expect(gated.run({ orderId: '1' })).resolves.toBe('refunded');
    expect(calls).toEqual(['ran']);

    // Control 2: a tool with no approval requirement is never gated.
    const open = tool({ name: 'read_note', description: 'read', execute: async () => 'note' });
    setApprovalManager(denyingManager());
    await expect(open.run({})).resolves.toBe('note');
  });

  it('run() honours the restart-safety gate', async () => {
    const effectful = tool({
      name: 'charge_card',
      description: 'charge',
      restartSafe: false,
      execute: async () => 'charged',
    });
    await expect(effectful.run({}, { resumed: true })).rejects.toBeInstanceOf(ToolNotRestartSafeError);
    // Control: a normal (non-resumed) call runs.
    await expect(effectful.run({})).resolves.toBe('charged');
  });

  it('validate() reports what is wrong instead of just a name check', () => {
    const t = tool({ name: 'fine', description: 'fine', execute: async () => 1 });
    expect(t.validate()).toBe(true);
    const broken = new FunctionTool({ name: '', description: '', execute: async () => 1 } as any);
    expect(() => broken.validate()).toThrow(/non-empty string 'name'/);
  });
});

describe('FunctionTool is deliberately NOT callable', () => {
  it('stays an object, because Agent branches on typeof tool === "function"', () => {
    const t = tool({ name: 'x', description: 'x', approval: true, execute: async () => 1 });
    // `Agent.processToolInputs` (src/agent/simple.ts) tests `typeof tool ===
    // 'function'` BEFORE the object branch, and the function branch invokes
    // the callable directly instead of going through execute(). A callable
    // FunctionTool would therefore be routed around its own approval gate.
    expect(typeof t).toBe('object');
    expect(typeof (t as any).execute).toBe('function');
    expect(typeof (t as any).run).toBe('function');
  });
});
