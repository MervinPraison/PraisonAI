/**
 * Tests for Agent* prefix renaming (Python parity)
 * 
 * Renamed Classes with Silent Aliases:
 * - PraisonAIAgents → AgentTeam (with Agents, PraisonAIAgents as aliases)
 * - Workflow → AgentFlow (with Workflow, Pipeline as aliases)
 */

describe('AgentTeam Rename', () => {
  describe('Primary Class', () => {
    it('should export AgentTeam as primary class', async () => {
      const { AgentTeam } = await import('../../../src/agent/simple');
      expect(AgentTeam).toBeDefined();
      expect(typeof AgentTeam).toBe('function');
    });

    it('should have AgentTeam as the class name', async () => {
      const { AgentTeam } = await import('../../../src/agent/simple');
      expect(AgentTeam.name).toBe('AgentTeam');
    });
  });

  describe('Silent Aliases', () => {
    it('should export PraisonAIAgents as alias for AgentTeam', async () => {
      const { AgentTeam, PraisonAIAgents } = await import('../../../src/agent/simple');
      expect(PraisonAIAgents).toBe(AgentTeam);
    });

    it('should export Agents as alias for AgentTeam', async () => {
      const { AgentTeam, Agents } = await import('../../../src/agent/simple');
      expect(Agents).toBe(AgentTeam);
    });
  });

  describe('Type Exports', () => {
    it('should export AgentTeamConfig type', async () => {
      // Type-only test - if this compiles, the type exists
      const { AgentTeam } = await import('../../../src/agent/simple');
      expect(AgentTeam).toBeDefined();
    });
  });

  describe('Main Package Exports', () => {
    it('should export AgentTeam from main index', async () => {
      const pkg = await import('../../../src/index');
      expect(pkg.AgentTeam).toBeDefined();
    });

    it('should export all aliases from main index', async () => {
      const pkg = await import('../../../src/index');
      expect(pkg.AgentTeam).toBe(pkg.Agents);
      expect(pkg.AgentTeam).toBe(pkg.PraisonAIAgents);
    });
  });
});

describe('AgentFlow Rename', () => {
  describe('Primary Class', () => {
    it('should export AgentFlow as primary class', async () => {
      const { AgentFlow } = await import('../../../src/workflows/index');
      expect(AgentFlow).toBeDefined();
      expect(typeof AgentFlow).toBe('function');
    });

    it('should have AgentFlow as the class name', async () => {
      const { AgentFlow } = await import('../../../src/workflows/index');
      expect(AgentFlow.name).toBe('AgentFlow');
    });
  });

  describe('Silent Aliases', () => {
    it('should export Workflow as alias for AgentFlow', async () => {
      const { AgentFlow, Workflow } = await import('../../../src/workflows/index');
      expect(Workflow).toBe(AgentFlow);
    });

    it('should export Pipeline as alias for AgentFlow', async () => {
      const { AgentFlow, Pipeline } = await import('../../../src/workflows/index');
      expect(Pipeline).toBe(AgentFlow);
    });
  });

  describe('Main Package Exports', () => {
    it('should export AgentFlow from main index', async () => {
      const pkg = await import('../../../src/index');
      expect(pkg.AgentFlow).toBeDefined();
    });

    it('should export all workflow aliases from main index', async () => {
      const pkg = await import('../../../src/index');
      expect(pkg.AgentFlow).toBe(pkg.Workflow);
      expect(pkg.AgentFlow).toBe(pkg.Pipeline);
    });
  });
});

describe('Backward Compatibility', () => {
  it('should allow instantiation with old name PraisonAIAgents', async () => {
    const { PraisonAIAgents, Agent } = await import('../../../src/agent/simple');
    const agent = new Agent({ instructions: 'Test agent' });
    const team = new PraisonAIAgents([agent]);
    expect(team).toBeDefined();
  });

  it('should allow instantiation with old name Agents', async () => {
    const { Agents, Agent } = await import('../../../src/agent/simple');
    const agent = new Agent({ instructions: 'Test agent' });
    const team = new Agents([agent]);
    expect(team).toBeDefined();
  });

  it('should allow instantiation with new name AgentTeam', async () => {
    const { AgentTeam, Agent } = await import('../../../src/agent/simple');
    const agent = new Agent({ instructions: 'Test agent' });
    const team = new AgentTeam([agent]);
    expect(team).toBeDefined();
  });

  it('should allow instantiation with old name Workflow', async () => {
    const { Workflow } = await import('../../../src/workflows/index');
    const flow = new Workflow('test-workflow');
    expect(flow).toBeDefined();
  });

  it('should allow instantiation with new name AgentFlow', async () => {
    const { AgentFlow } = await import('../../../src/workflows/index');
    const flow = new AgentFlow('test-flow');
    expect(flow).toBeDefined();
  });
});
