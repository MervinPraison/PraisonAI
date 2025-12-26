/**
 * YAML Workflow Parser Unit Tests
 */

import { 
  parseYAMLWorkflow, 
  createWorkflowFromYAML, 
  validateWorkflowDefinition,
  YAMLWorkflowDefinition 
} from '../../../src/workflows/yaml-parser';

describe('parseYAMLWorkflow', () => {
  it('should parse basic workflow definition', () => {
    const yaml = `
name: test-workflow
description: A test workflow
version: 1.0.0
steps:
  - name: step1
    type: agent
    agent: researcher
  - name: step2
    type: tool
    tool: search
`;
    
    const result = parseYAMLWorkflow(yaml);
    
    expect(result.name).toBe('test-workflow');
    expect(result.description).toBe('A test workflow');
    expect(result.version).toBe('1.0.0');
    expect(result.steps.length).toBe(2);
  });

  it('should parse step properties', () => {
    const yaml = `
name: workflow
steps:
  - name: process
    type: agent
    agent: processor
    onError: retry
    maxRetries: 3
    timeout: 5000
`;
    
    const result = parseYAMLWorkflow(yaml);
    const step = result.steps[0];
    
    expect(step.name).toBe('process');
    expect(step.type).toBe('agent');
    expect(step.agent).toBe('processor');
    expect(step.onError).toBe('retry');
    expect(step.maxRetries).toBe(3);
    expect(step.timeout).toBe(5000);
  });

  it('should handle condition steps', () => {
    const yaml = `
name: conditional
steps:
  - name: check
    type: condition
    condition: result.success === true
`;
    
    const result = parseYAMLWorkflow(yaml);
    
    expect(result.steps[0].type).toBe('condition');
    expect(result.steps[0].condition).toBe('result.success === true');
  });

  it('should ignore comments', () => {
    const yaml = `
# This is a comment
name: workflow
# Another comment
steps:
  - name: step1
    type: agent
    agent: test
`;
    
    const result = parseYAMLWorkflow(yaml);
    expect(result.name).toBe('workflow');
    expect(result.steps.length).toBe(1);
  });
});

describe('validateWorkflowDefinition', () => {
  it('should pass for valid workflow', () => {
    const definition: YAMLWorkflowDefinition = {
      name: 'valid-workflow',
      steps: [
        { name: 'step1', type: 'agent', agent: 'test' }
      ]
    };
    
    const errors = validateWorkflowDefinition(definition);
    expect(errors.length).toBe(0);
  });

  it('should fail for missing name', () => {
    const definition: YAMLWorkflowDefinition = {
      name: '',
      steps: [{ name: 'step1', type: 'agent', agent: 'test' }]
    };
    
    const errors = validateWorkflowDefinition(definition);
    expect(errors).toContain('Workflow must have a name');
  });

  it('should fail for empty steps', () => {
    const definition: YAMLWorkflowDefinition = {
      name: 'workflow',
      steps: []
    };
    
    const errors = validateWorkflowDefinition(definition);
    expect(errors).toContain('Workflow must have at least one step');
  });

  it('should fail for duplicate step names', () => {
    const definition: YAMLWorkflowDefinition = {
      name: 'workflow',
      steps: [
        { name: 'step1', type: 'agent', agent: 'a' },
        { name: 'step1', type: 'agent', agent: 'b' }
      ]
    };
    
    const errors = validateWorkflowDefinition(definition);
    expect(errors).toContain('Duplicate step name: step1');
  });

  it('should fail for agent type without agent field', () => {
    const definition: YAMLWorkflowDefinition = {
      name: 'workflow',
      steps: [
        { name: 'step1', type: 'agent' }
      ]
    };
    
    const errors = validateWorkflowDefinition(definition);
    expect(errors.some(e => e.includes('agent type requires'))).toBe(true);
  });

  it('should fail for tool type without tool field', () => {
    const definition: YAMLWorkflowDefinition = {
      name: 'workflow',
      steps: [
        { name: 'step1', type: 'tool' }
      ]
    };
    
    const errors = validateWorkflowDefinition(definition);
    expect(errors.some(e => e.includes('tool type requires'))).toBe(true);
  });
});

describe('createWorkflowFromYAML', () => {
  it('should create executable workflow', () => {
    const definition: YAMLWorkflowDefinition = {
      name: 'test-workflow',
      steps: [
        { name: 'greet', type: 'agent', agent: 'greeter' }
      ]
    };

    const mockAgent = {
      chat: async (input: string) => `Hello, ${input}!`
    };

    const { workflow, errors } = createWorkflowFromYAML(
      definition,
      { greeter: mockAgent },
      {}
    );

    expect(errors.length).toBe(0);
    expect(workflow.name).toBe('test-workflow');
    expect(workflow.stepCount).toBe(1);
  });

  it('should report errors for missing agents', () => {
    const definition: YAMLWorkflowDefinition = {
      name: 'workflow',
      steps: [
        { name: 'step1', type: 'agent', agent: 'nonexistent' }
      ]
    };

    const { errors } = createWorkflowFromYAML(definition, {}, {});

    expect(errors.some(e => e.includes('not found'))).toBe(true);
  });

  it('should report errors for missing tools', () => {
    const definition: YAMLWorkflowDefinition = {
      name: 'workflow',
      steps: [
        { name: 'step1', type: 'tool', tool: 'nonexistent' }
      ]
    };

    const { errors } = createWorkflowFromYAML(definition, {}, {});

    expect(errors.some(e => e.includes('not found'))).toBe(true);
  });

  it('should create workflow with tool steps', async () => {
    const definition: YAMLWorkflowDefinition = {
      name: 'tool-workflow',
      steps: [
        { name: 'search', type: 'tool', tool: 'searcher' }
      ]
    };

    const mockTool = {
      execute: async (input: any) => `Found: ${input}`
    };

    const { workflow, errors } = createWorkflowFromYAML(
      definition,
      {},
      { searcher: mockTool }
    );

    expect(errors.length).toBe(0);
    expect(workflow.stepCount).toBe(1);
  });

  it('should handle condition steps', () => {
    const definition: YAMLWorkflowDefinition = {
      name: 'conditional-workflow',
      steps: [
        { name: 'check', type: 'condition', condition: 'input.valid === true' }
      ]
    };

    const { workflow, errors } = createWorkflowFromYAML(definition, {}, {});

    expect(errors.length).toBe(0);
    expect(workflow.stepCount).toBe(1);
  });
});
