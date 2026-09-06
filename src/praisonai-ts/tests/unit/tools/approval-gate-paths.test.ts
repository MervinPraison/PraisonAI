/**
 * Where a `@tool(approval=...)` requirement is actually enforced.
 *
 * Python keeps the requirement in a process-wide ApprovalRegistry keyed by
 * tool NAME (`approval.add_approval_requirement`, called from the `@tool`
 * decorator), so every executor that consults that registry gates the call.
 * TypeScript keeps it on the FunctionTool instance and gates inside
 * `executeRaw`, which `execute()` and `run()` both funnel through.
 *
 * That is only safe if every tool-call path in this package reaches the tool
 * through the instance. These tests walk each real path and prove it does,
 * with a paired control showing the same path succeeding when approval is
 * granted, plus the one shape that WOULD bypass the gate (a bare callable)
 * so the boundary is explicit rather than assumed.
 */

import { describe, it, expect, afterEach, jest } from '@jest/globals';
import { tool } from '../../../src/tools/decorator';
import {
  ApprovalManager, setApprovalManager, ToolApprovalDeniedError,
} from '../../../src/ai/tool-approval';
import { BaseLLM } from '../../../src/llm/index';
import { Agent } from '../../../src/agent/simple';
import { EnhancedAgent } from '../../../src/agent/enhanced';

const mockCreate = jest.fn<(...args: any[]) => any>();
jest.mock('openai', () => ({
  __esModule: true,
  default: class MockOpenAI {
    chat = { completions: { create: (...args: any[]) => mockCreate(...args) } };
  },
}));

process.env.PRAISONAI_PARITY_SILENT = '1';

function manager(decision: boolean): ApprovalManager {
  const m = new ApprovalManager();
  m.onApprovalRequest(async () => decision);
  return m;
}

/** Records whether the underlying implementation ever ran. */
function gatedTool(ran: string[]) {
  return tool({
    name: 'refund_order',
    description: 'Refund an order',
    approval: 'critical',
    parameters: { type: 'object', properties: { orderId: { type: 'string' } }, required: ['orderId'] },
    execute: async () => { ran.push('ran'); return 'refunded'; },
  });
}

function toolReply(name: string, args: string) {
  return {
    model: 'gpt-4o-mini',
    choices: [{
      message: {
        role: 'assistant', content: null,
        tool_calls: [{ id: 'c1', type: 'function', function: { name, arguments: args } }],
      },
      finish_reason: 'tool_calls',
    }],
  };
}

const textReply = (text: string) => ({
  model: 'gpt-4o-mini',
  choices: [{ message: { role: 'assistant', content: text }, finish_reason: 'stop' }],
});

describe('every FunctionTool call path in this package hits the approval gate', () => {
  afterEach(() => {
    setApprovalManager(new ApprovalManager());
    mockCreate.mockReset();
  });

  it('path 1: direct execute()/run() on the instance', async () => {
    const ran: string[] = [];
    const t = gatedTool(ran);

    setApprovalManager(manager(false));
    await expect(t.execute({ orderId: '1' })).rejects.toBeInstanceOf(ToolApprovalDeniedError);
    await expect(t.run({ orderId: '1' })).rejects.toBeInstanceOf(ToolApprovalDeniedError);
    await expect(t.executeRaw({ orderId: '1' })).rejects.toBeInstanceOf(ToolApprovalDeniedError);
    expect(ran).toEqual([]);

    // Control
    setApprovalManager(manager(true));
    await expect(t.execute({ orderId: '1' })).resolves.toBe('refunded');
    expect(ran).toEqual(['ran']);
  });

  it('path 2: BaseLLM.generateWithTools (the tool loop)', async () => {
    const ran: string[] = [];
    const t = gatedTool(ran);

    setApprovalManager(manager(false));
    mockCreate
      .mockResolvedValueOnce(toolReply('refund_order', '{"orderId":"1"}'))
      .mockResolvedValueOnce(textReply('could not refund'));

    const llm = new BaseLLM({ model: 'gpt-4o-mini' });
    const denied = await llm.generateWithTools([{ role: 'user', content: 'refund order 1' }], [t]);

    expect(ran).toEqual([]);
    expect(JSON.stringify(denied.toolCalls[0].result)).toContain('approval denied');

    // Control: same loop, approval granted.
    mockCreate.mockReset();
    setApprovalManager(manager(true));
    mockCreate
      .mockResolvedValueOnce(toolReply('refund_order', '{"orderId":"1"}'))
      .mockResolvedValueOnce(textReply('done'));
    const allowed = await llm.generateWithTools([{ role: 'user', content: 'refund order 1' }], [t]);
    expect(ran).toEqual(['ran']);
    expect(allowed.toolCalls[0].result).toBe('refunded');
  });

  it('path 3: Agent registers the instance method, not the raw function', async () => {
    const ran: string[] = [];
    const t = gatedTool(ran);
    const agent = new Agent({ instructions: 'x', llm: 'gpt-4o-mini', verbose: false, tools: [t] });

    // The implementation Agent will dispatch to for this tool name.
    const registered = (agent as any).toolFunctions['refund_order'] as (args: any) => Promise<unknown>;
    expect(typeof registered).toBe('function');

    setApprovalManager(manager(false));
    await expect(registered({ orderId: '1' })).rejects.toBeInstanceOf(ToolApprovalDeniedError);
    expect(ran).toEqual([]);

    // Control
    setApprovalManager(manager(true));
    await expect(registered({ orderId: '1' })).resolves.toBe('refunded');
    expect(ran).toEqual(['ran']);
  });

  it('path 4: EnhancedAgent tool registry lookup', async () => {
    const ran: string[] = [];
    const t = gatedTool(ran);
    const agent = new EnhancedAgent({ name: 'a', instructions: 'x', tools: [t] });

    const fromRegistry = agent.getTools().find(x => x.name === 'refund_order')!;
    setApprovalManager(manager(false));
    await expect(fromRegistry.execute({ orderId: '1' })).rejects.toBeInstanceOf(ToolApprovalDeniedError);
    expect(ran).toEqual([]);

    // Control
    setApprovalManager(manager(true));
    await expect(fromRegistry.execute({ orderId: '1' })).resolves.toBe('refunded');
  });

  it('boundary: a BARE CALLABLE carries no requirement — which is why FunctionTool is not callable', async () => {
    const ran: string[] = [];
    // A plain function named like the gated tool. Agent's `typeof tool ===
    // "function"` branch invokes it directly, so nothing gates it. This is the
    // shape a callable FunctionTool would have collapsed into.
    const bare = async ({ orderId }: { orderId: string }) => { ran.push(orderId); return 'refunded'; };
    Object.defineProperty(bare, 'name', { value: 'refund_order' });

    const agent = new Agent({ instructions: 'x', llm: 'gpt-4o-mini', verbose: false, tools: [bare as any] });
    const registered = (agent as any).toolFunctions['refund_order'] as (args: any) => Promise<unknown>;

    setApprovalManager(manager(false));
    await expect(registered({ orderId: '1' })).resolves.toBe('refunded');
    expect(ran).toEqual(['1']);
  });
});
