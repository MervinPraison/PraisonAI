import { Agent } from '../../../src/agent';

describe('Agent Integration', () => {
  let agent: Agent;

  beforeEach(() => {
    agent = new Agent({
      name: 'IntegrationTestAgent',
      instructions: 'Test agent with tools'
    });
  });

  describe('Agent Creation', () => {
    it('should create agent with name and instructions', () => {
      expect(agent).toBeDefined();
    });

    it('should create agent with tools', () => {
      const toolAgent = new Agent({
        name: 'ToolAgent',
        instructions: 'Agent with tools',
        tools: [
          {
            name: 'calculator',
            description: 'Performs calculations',
            parameters: { type: 'object', properties: {} },
            execute: async () => '42'
          }
        ]
      });
      expect(toolAgent).toBeDefined();
    });

    it('should create agent with custom LLM', () => {
      const customAgent = new Agent({
        name: 'CustomAgent',
        instructions: 'Custom LLM agent',
        llm: 'openai/gpt-4o-mini'
      });
      expect(customAgent).toBeDefined();
    });
  });
});
