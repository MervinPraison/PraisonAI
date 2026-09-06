/**
 * Workflow command - Execute a multi-agent workflow
 */

import * as fs from 'fs';
import * as path from 'path';
import { resolveConfig } from '../config/resolve';
import { printSuccess, printError, outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES, normalizeError } from '../output/errors';

export interface WorkflowOptions {
  parallel?: boolean;
  model?: string;
  verbose?: boolean;
  profile?: string;
  config?: string;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

interface Task {
  name: string;
  agent?: string;
  task?: string;
  depends_on?: string[];
}

interface WorkflowDefinition {
  name?: string;
  description?: string;
  agents?: Record<string, any>;
  steps?: Task[] | string;
}

/**
 * Simple YAML parser for workflow files
 */
function parseWorkflowYaml(content: string): WorkflowDefinition {
  const result: WorkflowDefinition = {};
  const lines = content.split('\n');
  let currentSection: string | null = null;
  let currentItem: any = null;
  let currentAgentKey: string | null = null;

  for (const line of lines) {
    if (!line.trim() || line.trim().startsWith('#')) continue;

    const indent = line.search(/\S/);
    const trimmed = line.trim();

    // Top-level keys
    if (indent === 0 && trimmed.includes(':')) {
      const colonIdx = trimmed.indexOf(':');
      const key = trimmed.slice(0, colonIdx).trim();
      const value = trimmed.slice(colonIdx + 1).trim();

      // A scalar value on a section key (e.g. `steps: foo`) must not silently
      // become the section: it would pass the array guards downstream and then
      // blow up with `steps.map is not a function`. Only a bare `steps:` opens
      // the list section; anything else stays a scalar the caller can reject.
      currentAgentKey = null;
      if (value) {
        (result as any)[key] = value;
        currentSection = null;
      } else {
        currentSection = key;
        if (key === 'agents') result.agents = {};
        if (key === 'steps') result.steps = [];
      }
    } else if (indent > 0 && currentSection === 'steps' && Array.isArray(result.steps)) {
      // Handle list items (steps)
      if (trimmed.startsWith('- ')) {
        currentItem = {};
        result.steps.push(currentItem);

        // Parse inline values after -
        const afterDash = trimmed.slice(2).trim();
        if (afterDash.includes(':')) {
          const colonIdx = afterDash.indexOf(':');
          const key = afterDash.slice(0, colonIdx).trim();
          const value = afterDash.slice(colonIdx + 1).trim();
          currentItem[key] = parseScalarOrList(value);
        }
      } else if (trimmed.includes(':') && currentItem) {
        const colonIdx = trimmed.indexOf(':');
        const key = trimmed.slice(0, colonIdx).trim();
        const value = trimmed.slice(colonIdx + 1).trim();
        currentItem[key] = parseScalarOrList(value);
      }
    } else if (indent > 0 && currentSection === 'agents' && result.agents) {
      // An agents block is a map of agent name -> { instructions, llm, ... }.
      // Without reading it, every step ran with the generic fallback and a
      // typo'd or missing agent reference was never caught.
      const colonIdx = trimmed.indexOf(':');
      if (colonIdx === -1) continue;
      const key = trimmed.slice(0, colonIdx).trim();
      const value = trimmed.slice(colonIdx + 1).trim();
      if (indent <= 2 || currentAgentKey === null) {
        // Top of an agent definition: `writer:` (or `writer: gpt-4o` shorthand).
        currentAgentKey = key;
        result.agents[key] = value ? { llm: value } : {};
      } else if (currentAgentKey) {
        result.agents[currentAgentKey][key] = value;
      }
    }
  }

  return result;
}

/**
 * Inline `[a, b]` lists (e.g. `depends_on: [one, two]`) become arrays; a bare
 * `depends_on:` becomes an empty array; everything else stays a string.
 */
function parseScalarOrList(value: string): string | string[] {
  if (!value) return [];
  const list = value.match(/^\[(.*)\]$/);
  if (list) {
    return list[1]
      .split(',')
      .map(v => v.trim())
      .filter(Boolean);
  }
  return value;
}

export async function execute(args: string[], options: WorkflowOptions): Promise<void> {
  const workflowFile = args[0];
  
  if (!workflowFile) {
    if (options.json || options.output === 'json') {
      printError(ERROR_CODES.MISSING_ARG, 'Please provide a workflow file path');
    } else {
      await pretty.error('Please provide a workflow file path');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  // Resolve config
  const config = resolveConfig({
    configPath: options.config,
    profile: options.profile,
    model: options.model,
    verbose: options.verbose
  });

  const startTime = Date.now();
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    // Read and parse workflow file
    const filePath = path.resolve(workflowFile);
    if (!fs.existsSync(filePath)) {
      throw new Error(`Workflow file not found: ${filePath}`);
    }

    const content = fs.readFileSync(filePath, 'utf-8');
    const workflow = parseWorkflowYaml(content);

    if (outputFormat !== 'json') {
      await pretty.heading(`Executing workflow: ${workflow.name || 'Unnamed'}`);
      if (workflow.description) {
        await pretty.info(workflow.description);
      }
    }

    // Execute workflow steps
    const results: Record<string, any> = {};
    const steps = workflow.steps || [];

    // A scalar `steps: foo` parses to a string, whose `.length` passes the
    // empty check below and then throws `steps.map is not a function`. Reject
    // anything that is not a real list up front, with a diagnosable message.
    if (!Array.isArray(steps) || steps.length === 0) {
      throw new Error(
        `No steps found in ${filePath}. A workflow needs a 'steps:' list, ` +
        `each entry naming an 'agent' and a 'task'.`
      );
    }

    // A declared `agents:` block that names an agent a step never references,
    // or a step referencing an agent the block never declares, is a wrong-schema
    // file -- flag it rather than silently running with the generic fallback.
    const declaredAgents = workflow.agents || {};
    if (Object.keys(declaredAgents).length) {
      for (const step of steps) {
        if (step.agent && !(step.agent in declaredAgents)) {
          throw new Error(
            `Step '${step.name}' references agent '${step.agent}', ` +
            `which is not defined in the workflow's 'agents:' block.`
          );
        }
      }
    }

    const { Agent } = await import('../../agent');

    // Every step used to be marked 'completed' without an agent being built or
    // a model being called, so a typo'd agent name, a missing task or an absent
    // API key all reported success. Steps run in declaration order so each can
    // see what came before; --parallel runs them together without that context.
    const failures: Array<{ step: string; error: string }> = [];
    const outputs: Record<string, string> = {};

    // A step's context is its declared `depends_on` outputs when given, else
    // every earlier step's output. Honouring depends_on means a dependent no
    // longer receives unrelated steps' text.
    const contextFor = (step: Task): string[] => {
      if (options.parallel) return [];
      const deps = Array.isArray(step.depends_on) ? step.depends_on : [];
      if (deps.length) {
        return deps.map(d => outputs[d]).filter((o): o is string => o != null);
      }
      return Object.values(outputs);
    };

    const runStep = async (step: Task, context: string[]): Promise<string> => {
      if (outputFormat !== 'json') {
        await pretty.info(`Running step: ${step.name}`);
      }
      if (!step.task) {
        throw new Error(`Step '${step.name}' has no 'task' to run`);
      }
      const declared: any = declaredAgents[step.agent || ''] || {};
      const agent = new Agent({
        name: step.agent || step.name,
        instructions: declared.instructions || declared.role ||
          'You are a helpful AI assistant executing one step of a workflow.',
        llm: declared.llm || config.model,
        verbose: config.verbose,
      });
      const prompt = context.length
        ? `${context.join('\n\n')}\n\n${step.task}`
        : step.task;
      const output = await agent.start(prompt);
      return String(output ?? '');
    };

    const record = (step: Task, outcome: PromiseSettledResult<string>) => {
      if (outcome.status === 'fulfilled') {
        results[step.name] = { status: 'completed', output: outcome.value };
        outputs[step.name] = outcome.value;
      } else {
        const message = outcome.reason instanceof Error
          ? outcome.reason.message : String(outcome.reason);
        results[step.name] = { status: 'failed', error: message };
        failures.push({ step: step.name, error: message });
      }
    };

    if (options.parallel) {
      const settled = await Promise.allSettled(steps.map(step => runStep(step, [])));
      steps.forEach((step, i) => record(step, settled[i]));
    } else {
      for (const step of steps) {
        const settled = await Promise.allSettled([runStep(step, contextFor(step))]);
        record(step, settled[0]);
        // A failed step stops a sequential run; carrying on would feed the next
        // step context that was never produced.
        if (failures.length) break;
      }
    }

    if (failures.length) {
      throw new Error(
        `${failures.length} of ${steps.length} step(s) failed: ` +
        failures.map(f => `${f.step}: ${f.error}`).join('; ')
      );
    }

    const duration = Date.now() - startTime;

    if (outputFormat === 'json') {
      outputJson(formatSuccess(
        {
          workflow: workflow.name || 'Unnamed',
          steps: steps.length,
          results
        },
        {
          duration_ms: duration,
          model: config.model
        }
      ));
    } else {
      await pretty.success(`Workflow completed in ${duration}ms`);
      await pretty.newline();
      await pretty.keyValue({
        'Steps executed': steps.length,
        'Duration': `${duration}ms`
      });
    }

  } catch (error) {
    const cliError = normalizeError(error);
    
    if (outputFormat === 'json') {
      outputJson(formatError(cliError.code, cliError.message, cliError.details));
    } else {
      await pretty.error(cliError.message);
      if (config.verbose && error instanceof Error && error.stack) {
        await pretty.dim(error.stack);
      }
    }
    
    process.exit(cliError.exitCode);
  }
}
