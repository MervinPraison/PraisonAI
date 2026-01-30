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
  steps?: Task[];
}

/**
 * Simple YAML parser for workflow files
 */
function parseWorkflowYaml(content: string): WorkflowDefinition {
  const result: WorkflowDefinition = {};
  const lines = content.split('\n');
  let currentSection: string | null = null;
  let currentItem: any = null;
  let currentKey: string | null = null;
  
  for (const line of lines) {
    if (!line.trim() || line.trim().startsWith('#')) continue;
    
    const indent = line.search(/\S/);
    const trimmed = line.trim();
    
    // Top-level keys
    if (indent === 0 && trimmed.includes(':')) {
      const colonIdx = trimmed.indexOf(':');
      const key = trimmed.slice(0, colonIdx).trim();
      const value = trimmed.slice(colonIdx + 1).trim();
      
      if (value) {
        (result as any)[key] = value;
      } else {
        currentSection = key;
        if (key === 'agents') result.agents = {};
        if (key === 'steps') result.steps = [];
      }
    } else if (indent > 0 && currentSection) {
      // Handle list items (steps)
      if (trimmed.startsWith('- ')) {
        if (currentSection === 'steps') {
          currentItem = {};
          result.steps!.push(currentItem);
          
          // Parse inline values after -
          const afterDash = trimmed.slice(2).trim();
          if (afterDash.includes(':')) {
            const colonIdx = afterDash.indexOf(':');
            const key = afterDash.slice(0, colonIdx).trim();
            const value = afterDash.slice(colonIdx + 1).trim();
            currentItem[key] = value;
          }
        }
      } else if (trimmed.includes(':') && currentItem) {
        const colonIdx = trimmed.indexOf(':');
        const key = trimmed.slice(0, colonIdx).trim();
        const value = trimmed.slice(colonIdx + 1).trim();
        currentItem[key] = value || [];
      }
    }
  }
  
  return result;
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

    for (const step of steps) {
      if (outputFormat !== 'json') {
        await pretty.info(`Running step: ${step.name}`);
      }

      // For now, we'll simulate step execution
      // In a full implementation, this would create agents and execute tasks
      results[step.name] = {
        status: 'completed',
        output: `Step ${step.name} completed`
      };
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
