/**
 * Tools command - List or manage tools
 */

import { getRegistry, FunctionTool } from '../../tools/decorator';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface ToolsOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

interface ToolInfo {
  name: string;
  description?: string;
  parameters?: unknown;
}

// Built-in tools that are always available
const BUILTIN_TOOLS: ToolInfo[] = [
  { name: 'arxiv_search', description: 'Search arXiv for academic papers' },
  { name: 'web_search', description: 'Search the web for information' },
  { name: 'calculator', description: 'Perform mathematical calculations' },
  { name: 'code_executor', description: 'Execute code snippets' },
  { name: 'file_reader', description: 'Read file contents' },
  { name: 'file_writer', description: 'Write content to files' }
];

export async function execute(args: string[], options: ToolsOptions): Promise<void> {
  const subcommand = args[0] || 'list';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  switch (subcommand) {
    case 'list':
      await listTools(options, outputFormat);
      break;
    case 'info':
      await toolInfo(args.slice(1), options, outputFormat);
      break;
    default:
      if (outputFormat === 'json') {
        outputJson(formatError(ERROR_CODES.INVALID_ARGS, `Unknown subcommand: ${subcommand}`));
      } else {
        await pretty.error(`Unknown subcommand: ${subcommand}`);
      }
      process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }
}

async function listTools(options: ToolsOptions, outputFormat: string): Promise<void> {
  // Get registered tools from registry
  const registry = getRegistry();
  const registeredTools = registry.list();
  
  // Combine built-in and registered tools
  const allTools: ToolInfo[] = [
    ...BUILTIN_TOOLS,
    ...registeredTools.map((t: FunctionTool) => ({
      name: t.name,
      description: t.description,
      parameters: t.parameters
    }))
  ];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      tools: allTools.map(t => ({
        name: t.name,
        description: t.description,
        parameters: options.verbose ? t.parameters : undefined
      })),
      count: allTools.length
    }));
  } else {
    await pretty.heading('Available Tools');
    
    await pretty.plain('Built-in Tools:');
    for (const tool of BUILTIN_TOOLS) {
      await pretty.plain(`  • ${tool.name}`);
      if (tool.description) {
        await pretty.dim(`    ${tool.description}`);
      }
    }
    
    if (registeredTools.length > 0) {
      await pretty.newline();
      await pretty.plain('Registered Tools:');
      for (const tool of registeredTools) {
        await pretty.plain(`  • ${tool.name}`);
        if (tool.description) {
          await pretty.dim(`    ${tool.description}`);
        }
      }
    }
    
    await pretty.newline();
    await pretty.info(`Total: ${allTools.length} tools`);
  }
}

async function toolInfo(args: string[], options: ToolsOptions, outputFormat: string): Promise<void> {
  const toolName = args[0];
  
  if (!toolName) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a tool name'));
    } else {
      await pretty.error('Please provide a tool name');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  // Look for tool in built-in and registered tools
  const builtinTool = BUILTIN_TOOLS.find(t => t.name === toolName);
  const registry = getRegistry();
  const registeredTool = registry.get(toolName);
  
  const tool = builtinTool || (registeredTool ? {
    name: registeredTool.name,
    description: registeredTool.description,
    parameters: registeredTool.parameters
  } : null);

  if (!tool) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.TOOL_NOT_FOUND, `Tool not found: ${toolName}`));
    } else {
      await pretty.error(`Tool not found: ${toolName}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      tool: {
        name: tool.name,
        description: tool.description,
        parameters: tool.parameters,
        type: builtinTool ? 'builtin' : 'registered'
      }
    }));
  } else {
    await pretty.heading(`Tool: ${tool.name}`);
    await pretty.keyValue({
      'Name': tool.name,
      'Type': builtinTool ? 'Built-in' : 'Registered',
      'Description': tool.description || 'No description'
    });
    
    if (tool.parameters && options.verbose) {
      await pretty.newline();
      await pretty.plain('Parameters:');
      await pretty.plain(JSON.stringify(tool.parameters, null, 2));
    }
  }
}
