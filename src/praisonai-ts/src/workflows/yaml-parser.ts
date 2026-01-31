/**
 * YAML Workflow Parser
 * Parse YAML workflow definitions into executable workflows
 */

import { AgentFlow, Task, TaskConfig } from './index';

export interface YAMLWorkflowDefinition {
  name: string;
  description?: string;
  version?: string;
  steps: YAMLStepDefinition[];
  metadata?: Record<string, any>;
}

export interface YAMLStepDefinition {
  name: string;
  type: 'agent' | 'tool' | 'condition' | 'parallel' | 'loop';
  agent?: string;
  tool?: string;
  input?: string | Record<string, any>;
  output?: string;
  condition?: string;
  onError?: 'fail' | 'skip' | 'retry';
  maxRetries?: number;
  timeout?: number;
  steps?: YAMLStepDefinition[]; // For parallel/loop
  loopCondition?: string;
  maxIterations?: number;
}

export interface ParsedWorkflow {
  workflow: AgentFlow;
  definition: YAMLWorkflowDefinition;
  errors: string[];
}

/**
 * Parse YAML string into workflow definition
 */
export function parseYAMLWorkflow(yamlContent: string): YAMLWorkflowDefinition {
  // Simple YAML parser for workflow definitions
  // For production, use js-yaml package
  const lines = yamlContent.split('\n');
  const result: YAMLWorkflowDefinition = {
    name: '',
    steps: []
  };

  let currentStep: Partial<YAMLStepDefinition> | null = null;
  let indent = 0;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const currentIndent = line.search(/\S/);
    
    // Parse key-value pairs
    const colonIndex = trimmed.indexOf(':');
    if (colonIndex === -1) continue;

    const key = trimmed.substring(0, colonIndex).trim();
    const value = trimmed.substring(colonIndex + 1).trim();

    if (currentIndent === 0) {
      // Top-level keys
      if (key === 'name') result.name = value;
      else if (key === 'description') result.description = value;
      else if (key === 'version') result.version = value;
      else if (key === 'steps') {
        // Steps array starts
        indent = currentIndent;
      }
    } else if (trimmed.startsWith('- name:')) {
      // New step
      if (currentStep && currentStep.name) {
        result.steps.push(currentStep as YAMLStepDefinition);
      }
      currentStep = {
        name: value,
        type: 'agent'
      };
    } else if (currentStep) {
      // Step properties
      if (key === 'type') currentStep.type = value as any;
      else if (key === 'agent') currentStep.agent = value;
      else if (key === 'tool') currentStep.tool = value;
      else if (key === 'input') currentStep.input = value;
      else if (key === 'output') currentStep.output = value;
      else if (key === 'condition') currentStep.condition = value;
      else if (key === 'onError') currentStep.onError = value as any;
      else if (key === 'maxRetries') currentStep.maxRetries = parseInt(value);
      else if (key === 'timeout') currentStep.timeout = parseInt(value);
      else if (key === 'loopCondition') currentStep.loopCondition = value;
      else if (key === 'maxIterations') currentStep.maxIterations = parseInt(value);
    }
  }

  // Add last step
  if (currentStep && currentStep.name) {
    result.steps.push(currentStep as YAMLStepDefinition);
  }

  return result;
}

/**
 * Create executable workflow from YAML definition
 */
export function createWorkflowFromYAML(
  definition: YAMLWorkflowDefinition,
  agents: Record<string, any> = {},
  tools: Record<string, any> = {}
): ParsedWorkflow {
  const errors: string[] = [];
  const workflow = new AgentFlow(definition.name);

  for (const stepDef of definition.steps) {
    try {
      const stepConfig = createStepConfig(stepDef, agents, tools, errors);
      if (stepConfig) {
        workflow.addStep(stepConfig);
      }
    } catch (error: any) {
      errors.push(`Error creating step ${stepDef.name}: ${error.message}`);
    }
  }

  return { workflow, definition, errors };
}

function createStepConfig(
  stepDef: YAMLStepDefinition,
  agents: Record<string, any>,
  tools: Record<string, any>,
  errors: string[]
): TaskConfig | null {
  const { name, type, agent, tool, onError, maxRetries, timeout, condition } = stepDef;

  let execute: any;

  switch (type) {
    case 'agent':
      if (!agent) {
        errors.push(`Step ${name}: agent type requires 'agent' field`);
        return null;
      }
      const agentInstance = agents[agent];
      if (!agentInstance) {
        errors.push(`Step ${name}: agent '${agent}' not found`);
        return null;
      }
      execute = async (input: any) => {
        if (typeof agentInstance.chat === 'function') {
          return agentInstance.chat(typeof input === 'string' ? input : JSON.stringify(input));
        }
        return agentInstance(input);
      };
      break;

    case 'tool':
      if (!tool) {
        errors.push(`Step ${name}: tool type requires 'tool' field`);
        return null;
      }
      const toolInstance = tools[tool];
      if (!toolInstance) {
        errors.push(`Step ${name}: tool '${tool}' not found`);
        return null;
      }
      execute = async (input: any) => {
        if (typeof toolInstance.execute === 'function') {
          return toolInstance.execute(input);
        }
        if (typeof toolInstance.run === 'function') {
          return toolInstance.run(input);
        }
        return toolInstance(input);
      };
      break;

    case 'condition':
      execute = async (input: any, context: any) => {
        // Evaluate condition and return input or skip
        if (condition) {
          // Simple condition evaluation
          const result = evaluateCondition(condition, input, context);
          return result ? input : null;
        }
        return input;
      };
      break;

    default:
      execute = async (input: any) => input;
  }

  return {
    name,
    execute,
    onError,
    maxRetries,
    timeout,
    condition: condition ? (context) => evaluateCondition(condition, null, context) : undefined
  };
}

function evaluateCondition(condition: string, input: any, context: any): boolean {
  // Simple condition evaluation
  // Supports: "result.success", "input.length > 0", etc.
  try {
    // Create a safe evaluation context
    const evalContext = {
      input,
      context,
      result: context?.get?.('lastResult'),
      ...context?.metadata
    };

    // Simple expression evaluation
    if (condition.includes('===')) {
      const [left, right] = condition.split('===').map(s => s.trim());
      return getNestedValue(evalContext, left) === parseValue(right);
    }
    if (condition.includes('!==')) {
      const [left, right] = condition.split('!==').map(s => s.trim());
      return getNestedValue(evalContext, left) !== parseValue(right);
    }
    if (condition.includes('>')) {
      const [left, right] = condition.split('>').map(s => s.trim());
      return getNestedValue(evalContext, left) > parseValue(right);
    }
    if (condition.includes('<')) {
      const [left, right] = condition.split('<').map(s => s.trim());
      return getNestedValue(evalContext, left) < parseValue(right);
    }

    // Boolean check
    return !!getNestedValue(evalContext, condition);
  } catch {
    return false;
  }
}

function getNestedValue(obj: any, path: string): any {
  return path.split('.').reduce((current, key) => current?.[key], obj);
}

function parseValue(value: string): any {
  value = value.trim();
  if (value === 'true') return true;
  if (value === 'false') return false;
  if (value === 'null') return null;
  if (value.startsWith('"') && value.endsWith('"')) return value.slice(1, -1);
  if (value.startsWith("'") && value.endsWith("'")) return value.slice(1, -1);
  const num = Number(value);
  if (!isNaN(num)) return num;
  return value;
}

/**
 * Load workflow from YAML file
 */
export async function loadWorkflowFromFile(
  filePath: string,
  agents: Record<string, any> = {},
  tools: Record<string, any> = {}
): Promise<ParsedWorkflow> {
  const fs = await import('fs/promises');
  const content = await fs.readFile(filePath, 'utf-8');
  const definition = parseYAMLWorkflow(content);
  return createWorkflowFromYAML(definition, agents, tools);
}

/**
 * Validate YAML workflow definition
 */
export function validateWorkflowDefinition(definition: YAMLWorkflowDefinition): string[] {
  const errors: string[] = [];

  if (!definition.name) {
    errors.push('Workflow must have a name');
  }

  if (!definition.steps || definition.steps.length === 0) {
    errors.push('Workflow must have at least one step');
  }

  const stepNames = new Set<string>();
  for (const step of definition.steps) {
    if (!step.name) {
      errors.push('Each step must have a name');
    } else if (stepNames.has(step.name)) {
      errors.push(`Duplicate step name: ${step.name}`);
    } else {
      stepNames.add(step.name);
    }

    if (!step.type) {
      errors.push(`Step ${step.name}: must have a type`);
    }

    if (step.type === 'agent' && !step.agent) {
      errors.push(`Step ${step.name}: agent type requires 'agent' field`);
    }

    if (step.type === 'tool' && !step.tool) {
      errors.push(`Step ${step.name}: tool type requires 'tool' field`);
    }
  }

  return errors;
}

