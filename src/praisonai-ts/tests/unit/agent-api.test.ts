/**
 * Agent API Tests - Unified Agent, Agents, db(), tools
 */

import { Agent, Agents, PraisonAIAgents, db, Workflow } from '../../src';

describe('Agent API', () => {
  describe('Agent constructor', () => {
    it('should create agent with instructions', () => {
      const agent = new Agent({ instructions: 'You are helpful' });
      expect(agent).toBeDefined();
      expect(agent.getInstructions()).toBe('You are helpful');
    });

    it('should auto-generate name if not provided', () => {
      const agent = new Agent({ instructions: 'Test' });
      expect(agent.name).toMatch(/^Agent_/);
    });

    it('should use provided name', () => {
      const agent = new Agent({ instructions: 'Test', name: 'MyAgent' });
      expect(agent.name).toBe('MyAgent');
    });

    it('should support role/goal/backstory mode', () => {
      const agent = new Agent({
        instructions: '',
        role: 'researcher',
        goal: 'find information',
        backstory: 'expert in research'
      });
      const instructions = agent.getInstructions();
      expect(instructions).toContain('researcher');
      expect(instructions).toContain('find information');
      expect(instructions).toContain('expert in research');
    });

    it('should have sessionId', () => {
      const agent = new Agent({ instructions: 'Test' });
      expect(agent.getSessionId()).toBeDefined();
      expect(typeof agent.getSessionId()).toBe('string');
    });

    it('should use provided sessionId', () => {
      const agent = new Agent({ instructions: 'Test', sessionId: 'my-session' });
      expect(agent.getSessionId()).toBe('my-session');
    });

    it('should have runId', () => {
      const agent = new Agent({ instructions: 'Test' });
      expect(agent.getRunId()).toBeDefined();
      expect(typeof agent.getRunId()).toBe('string');
    });

    it('should accept db adapter', () => {
      const dbAdapter = db('memory:');
      const agent = new Agent({ 
        instructions: 'Test', 
        db: dbAdapter 
      });
      expect(agent).toBeDefined();
    });
  });

  describe('Agents alias', () => {
    it('should export Agents as alias for PraisonAIAgents', () => {
      expect(Agents).toBe(PraisonAIAgents);
    });

    it('should support array syntax', () => {
      const a1 = new Agent({ instructions: 'Agent 1' });
      const a2 = new Agent({ instructions: 'Agent 2' });
      const agents = new Agents([a1, a2]);
      expect(agents).toBeDefined();
    });

    it('should support config object syntax', () => {
      const a1 = new Agent({ instructions: 'Agent 1' });
      const a2 = new Agent({ instructions: 'Agent 2' });
      const agents = new Agents({
        agents: [a1, a2],
        process: 'sequential'
      });
      expect(agents).toBeDefined();
    });
  });
});

describe('db() factory', () => {
  it('should create memory adapter by default', () => {
    const adapter = db();
    expect(adapter).toBeDefined();
  });

  it('should parse memory: URL', () => {
    const adapter = db('memory:');
    expect(adapter).toBeDefined();
  });

  it('should parse :memory: URL', () => {
    const adapter = db(':memory:');
    expect(adapter).toBeDefined();
  });

  it('should accept config object', () => {
    const adapter = db({ type: 'memory' });
    expect(adapter).toBeDefined();
  });

  it('should throw on invalid URL', () => {
    expect(() => db('invalid://url')).toThrow();
  });
});

describe('Tool auto-schema', () => {
  it('should accept plain functions as tools', () => {
    const getWeather = (city: string) => `Weather in ${city}: 20°C`;
    
    const agent = new Agent({
      instructions: 'Weather assistant',
      tools: [getWeather]
    });
    
    expect(agent).toBeDefined();
  });

  it('should accept multiple function tools', () => {
    const getWeather = (city: string) => `Weather: 20°C`;
    const getTime = () => new Date().toISOString();
    
    const agent = new Agent({
      instructions: 'Assistant',
      tools: [getWeather, getTime]
    });
    
    expect(agent).toBeDefined();
  });
});

describe('Workflow.agent()', () => {
  it('should add agent step to workflow', () => {
    const agent = new Agent({ instructions: 'Test' });
    const workflow = new Workflow('Test')
      .agent(agent, 'Do something');
    
    expect(workflow.stepCount).toBe(1);
  });

  it('should chain multiple agent steps', () => {
    const a1 = new Agent({ instructions: 'Agent 1' });
    const a2 = new Agent({ instructions: 'Agent 2' });
    
    const workflow = new Workflow('Test')
      .agent(a1, 'Step 1')
      .agent(a2, 'Step 2');
    
    expect(workflow.stepCount).toBe(2);
  });

  it('should mix agent and function steps', () => {
    const agent = new Agent({ instructions: 'Test' });
    
    const workflow = new Workflow('Test')
      .step('preprocess', async (input) => input.toUpperCase())
      .agent(agent, 'Process')
      .step('postprocess', async (input) => input.trim());
    
    expect(workflow.stepCount).toBe(3);
  });
});
