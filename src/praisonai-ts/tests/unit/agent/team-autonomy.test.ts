/**
 * A team-wide `autonomy` propagates to members that declared none.
 *
 * The ledger note said "TypeScript Agents have no autonomy to propagate to
 * yet". That was stale: agent/features/autonomy.ts has levels, presets and
 * approval integration, and Agent has resolved `autonomy` all along.
 */
import { Agent } from '../../../src/agent/simple';
import { AgentTeam } from '../../../src/agent/team';

const level = (agent: any) => agent._autonomyConfig?.level;

function member(config: Record<string, unknown> = {}) {
  return new Agent({ instructions: 'x', llm: 'gpt-4o', ...config } as any);
}

describe('team-wide autonomy', () => {
  it('reaches every member that declared none', () => {
    const a = member(), b = member();
    new AgentTeam({ agents: [a, b], autonomy: 'full_auto' } as any);
    expect(level(a)).toBe('full_auto');
    expect(level(b)).toBe('full_auto');
  });

  it("a member's own autonomy wins over the team's", () => {
    // An autonomy level is a permission boundary. Silently WIDENING one an
    // agent declared for itself is the direction that causes harm.
    const own = member({ autonomy: 'suggest' });
    new AgentTeam({ agents: [own], autonomy: 'full_auto' } as any);
    expect(level(own)).toBe('suggest');
  });

  it('control: no team autonomy leaves members untouched', () => {
    const a = member();
    new AgentTeam({ agents: [a] } as any);
    expect(level(a)).toBeUndefined();
  });

  it('control: autonomy=false is not a propagation', () => {
    const a = member();
    new AgentTeam({ agents: [a], autonomy: false } as any);
    expect(level(a)).toBeUndefined();
  });

  it('a preset name resolves to its level', () => {
    const a = member();
    new AgentTeam({ agents: [a], autonomy: 'suggest' } as any);
    expect(level(a)).toBe('suggest');
  });

  it('a propagated prompting level creates the approval gate it needs', () => {
    // A member with no approval manager and no autonomy of its own must, once
    // it adopts a team-wide `suggest`, get the SAME gate the constructor would
    // build -- otherwise the level is recorded and nothing ever prompts.
    const a = member();
    expect((a as any).approvalManager).toBeUndefined();
    new AgentTeam({ agents: [a], autonomy: 'suggest' } as any);
    expect(level(a)).toBe('suggest');
    expect((a as any).approvalManager).toBeDefined();
    expect((a as any)._doomLoop).toBeDefined();
  });

  it('a member built with autonomy already has its own gate, matching adoption', () => {
    // Control: the constructor path and the adoption path agree on the shape.
    const own = member({ autonomy: 'suggest' });
    expect((own as any).approvalManager).toBeDefined();
    expect((own as any)._doomLoop).toBeDefined();
  });
});
