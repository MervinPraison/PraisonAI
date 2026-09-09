/**
 * A team-wide `toolsRunOn` places every member's tools in ONE shared sandbox.
 *
 * The ledger note said this "needs one shared sandbox for the whole team;
 * TypeScript has no compute providers yet" -- true until #5003 and #5007. A
 * single ToolPlace instance handed to every member is exactly that.
 */
import { Agent } from '../../../src/agent/simple';
import { AgentTeam } from '../../../src/agent/team';
import '../../../src/compute';

function agent() {
  return new Agent({ instructions: 'x', llm: 'gpt-4o' });
}

describe('team-wide tool placement', () => {
  it('every member gets a place', () => {
    const a = agent(), b = agent();
    new AgentTeam({ agents: [a, b], toolsRunOn: 'local' } as any);
    expect(a.getToolPlace()?.placeName).toBe('local');
    expect(b.getToolPlace()?.placeName).toBe('local');
  });

  it('members share ONE instance, not one each', () => {
    // Separate instances would multiply cost and lose state tools leave for
    // each other -- "one shared sandbox" is the whole point.
    const a = agent(), b = agent();
    new AgentTeam({ agents: [a, b], toolsRunOn: 'local' } as any);
    expect(a.getToolPlace()).toBe(b.getToolPlace());
  });

  it("a member's own toolsRunOn wins over the team default", () => {
    // An explicit choice on the member is more specific than the team's
    // default; silently overriding it would be the surprising direction.
    const own = new Agent({ instructions: 'x', llm: 'gpt-4o', toolsRunOn: 'local' });
    const ownPlace = own.getToolPlace();
    new AgentTeam({ agents: [own], toolsRunOn: 'docker' } as any);
    expect(own.getToolPlace()).toBe(ownPlace);
  });

  it('control: no toolsRunOn leaves members unplaced', () => {
    const a = agent();
    new AgentTeam({ agents: [a] } as any);
    expect(a.getToolPlace()).toBeUndefined();
  });

  it('control: toolsRunOn=false is not a placement', () => {
    const a = agent();
    new AgentTeam({ agents: [a], toolsRunOn: false } as any);
    expect(a.getToolPlace()).toBeUndefined();
  });

  it('an unknown place is refused rather than silently ignored', () => {
    expect(() => new AgentTeam({ agents: [agent()], toolsRunOn: 'nowhere' } as any)).toThrow();
  });
});
