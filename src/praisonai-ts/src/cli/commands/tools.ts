/**
 * Tools command - List, manage, and test AI SDK tools
 * 
 * Subcommands:
 *   list     - List all available tools
 *   info     - Get detailed info about a tool
 *   doctor   - Check tool dependencies and env vars
 *   example  - Show usage example for a tool
 *   add      - Register a custom tool from npm/local
 *   test     - Test a tool (dry-run or live)
 */

import { getRegistry, FunctionTool } from '../../tools/decorator';
import { getToolsRegistry } from '../../tools/registry/registry';
import { registerBuiltinTools } from '../../tools/tools';
import { getAllBuiltinMetadata } from '../../tools/builtins';
import type { ToolMetadata } from '../../tools/registry/types';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface ToolsOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  live?: boolean;
  tag?: string;
}

// Ensure built-in tools are registered
let builtinsRegistered = false;
function ensureBuiltinsRegistered() {
  if (!builtinsRegistered) {
    registerBuiltinTools();
    builtinsRegistered = true;
  }
}

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
    case 'doctor':
      await toolDoctor(options, outputFormat);
      break;
    case 'example':
      await toolExample(args.slice(1), options, outputFormat);
      break;
    case 'add':
      await toolAdd(args.slice(1), options, outputFormat);
      break;
    case 'test':
      await toolTest(args.slice(1), options, outputFormat);
      break;
    default:
      if (outputFormat === 'json') {
        outputJson(formatError(ERROR_CODES.INVALID_ARGS, `Unknown subcommand: ${subcommand}`));
      } else {
        await pretty.error(`Unknown subcommand: ${subcommand}`);
        await pretty.plain('Available subcommands: list, info, doctor, example, add, test');
      }
      process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }
}

async function listTools(options: ToolsOptions, outputFormat: string): Promise<void> {
  ensureBuiltinsRegistered();
  
  // Get all built-in tool metadata
  const builtinMetadata = await getAllBuiltinMetadata();
  
  // Get registered tools from decorator registry (legacy)
  const decoratorRegistry = getRegistry();
  const registeredTools = decoratorRegistry.list();
  
  // Filter by tag if specified
  let filteredMetadata = builtinMetadata;
  if (options.tag) {
    filteredMetadata = builtinMetadata.filter(m => m.tags.includes(options.tag!));
  }

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      builtinTools: filteredMetadata.map(m => ({
        id: m.id,
        name: m.displayName,
        description: m.description,
        tags: m.tags,
        packageName: m.packageName,
        requiredEnv: m.requiredEnv,
        capabilities: m.capabilities,
      })),
      registeredTools: registeredTools.map((t: FunctionTool) => ({
        name: t.name,
        description: t.description,
      })),
      count: filteredMetadata.length + registeredTools.length
    }));
  } else {
    await pretty.heading('AI SDK Tools Registry');
    
    await pretty.plain('\nBuilt-in Tools:');
    for (const meta of filteredMetadata) {
      const tags = meta.tags.slice(0, 3).join(', ');
      await pretty.plain(`  • ${meta.id} (${meta.displayName})`);
      await pretty.dim(`    ${meta.description}`);
      await pretty.dim(`    Tags: ${tags} | Package: ${meta.packageName}`);
    }
    
    if (registeredTools.length > 0) {
      await pretty.newline();
      await pretty.plain('Custom Registered Tools:');
      for (const tool of registeredTools) {
        await pretty.plain(`  • ${tool.name}`);
        if (tool.description) {
          await pretty.dim(`    ${tool.description}`);
        }
      }
    }
    
    await pretty.newline();
    await pretty.info(`Total: ${filteredMetadata.length + registeredTools.length} tools`);
    await pretty.dim('\nUse "praisonai-ts tools info <id>" for details');
    await pretty.dim('Use "praisonai-ts tools doctor" to check dependencies');
  }
}

async function toolInfo(args: string[], options: ToolsOptions, outputFormat: string): Promise<void> {
  ensureBuiltinsRegistered();
  const toolId = args[0];
  
  if (!toolId) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a tool ID'));
    } else {
      await pretty.error('Please provide a tool ID');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  // Look for tool in built-in metadata
  const builtinMetadata = await getAllBuiltinMetadata();
  const metadata = builtinMetadata.find(m => m.id === toolId);
  
  // Also check decorator registry
  const decoratorRegistry = getRegistry();
  const registeredTool = decoratorRegistry.get(toolId);

  if (!metadata && !registeredTool) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.TOOL_NOT_FOUND, `Tool not found: ${toolId}`));
    } else {
      await pretty.error(`Tool not found: ${toolId}`);
      await pretty.dim('Use "praisonai-ts tools list" to see available tools');
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      tool: metadata ? {
        id: metadata.id,
        name: metadata.displayName,
        description: metadata.description,
        tags: metadata.tags,
        packageName: metadata.packageName,
        requiredEnv: metadata.requiredEnv,
        optionalEnv: metadata.optionalEnv,
        install: metadata.install,
        capabilities: metadata.capabilities,
        docsSlug: metadata.docsSlug,
      } : {
        name: registeredTool!.name,
        description: registeredTool!.description,
        type: 'registered'
      }
    }));
  } else {
    if (metadata) {
      await pretty.heading(`Tool: ${metadata.displayName}`);
      await pretty.keyValue({
        'ID': metadata.id,
        'Description': metadata.description,
        'Package': metadata.packageName,
        'Tags': metadata.tags.join(', '),
        'Docs': `https://docs.praison.ai/js/${metadata.docsSlug}`,
      });
      
      await pretty.newline();
      await pretty.plain('Required Environment Variables:');
      if (metadata.requiredEnv.length > 0) {
        for (const env of metadata.requiredEnv) {
          const isSet = !!process.env[env];
          await pretty.plain(`  ${isSet ? '✓' : '✗'} ${env}`);
        }
      } else {
        await pretty.dim('  None');
      }
      
      await pretty.newline();
      await pretty.plain('Installation:');
      await pretty.plain(`  ${metadata.install.npm}`);
      
      await pretty.newline();
      await pretty.plain('Capabilities:');
      const caps = Object.entries(metadata.capabilities)
        .filter(([_, v]) => v)
        .map(([k]) => k);
      await pretty.plain(`  ${caps.join(', ') || 'None specified'}`);
    } else {
      await pretty.heading(`Tool: ${registeredTool!.name}`);
      await pretty.keyValue({
        'Name': registeredTool!.name,
        'Type': 'Custom Registered',
        'Description': registeredTool!.description || 'No description'
      });
    }
  }
}

async function toolDoctor(options: ToolsOptions, outputFormat: string): Promise<void> {
  ensureBuiltinsRegistered();
  const builtinMetadata = await getAllBuiltinMetadata();
  
  const results: Array<{
    id: string;
    name: string;
    installed: boolean;
    missingEnv: string[];
    installCmd?: string;
  }> = [];

  for (const meta of builtinMetadata) {
    // Check env vars
    const missingEnv = meta.requiredEnv.filter(env => !process.env[env]);
    
    // Check if package is installed (check node_modules)
    let installed = false;
    try {
      // First try require.resolve for CJS packages
      require.resolve(meta.packageName);
      installed = true;
    } catch {
      // For ESM packages, check if the package directory exists
      try {
        const path = await import('path');
        const fs = await import('fs');
        const packagePath = path.join(process.cwd(), 'node_modules', ...meta.packageName.split('/'));
        installed = fs.existsSync(packagePath);
      } catch {
        installed = false;
      }
    }

    results.push({
      id: meta.id,
      name: meta.displayName,
      installed,
      missingEnv,
      installCmd: installed ? undefined : meta.install.npm,
    });
  }

  const allGood = results.every(r => r.installed && r.missingEnv.length === 0);
  const installedCount = results.filter(r => r.installed).length;
  const envIssues = results.filter(r => r.missingEnv.length > 0).length;

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      status: allGood ? 'healthy' : 'issues_found',
      summary: {
        total: results.length,
        installed: installedCount,
        notInstalled: results.length - installedCount,
        missingEnvVars: envIssues,
      },
      tools: results,
    }));
  } else {
    await pretty.heading('Tools Health Check');
    
    await pretty.newline();
    await pretty.plain(`Summary: ${installedCount}/${results.length} packages installed, ${envIssues} with missing env vars`);
    await pretty.newline();

    for (const result of results) {
      const status = result.installed && result.missingEnv.length === 0 ? '✓' : '✗';
      await pretty.plain(`${status} ${result.id} (${result.name})`);
      
      if (!result.installed) {
        await pretty.dim(`    Package not installed: ${result.installCmd}`);
      }
      
      if (result.missingEnv.length > 0) {
        await pretty.dim(`    Missing env vars: ${result.missingEnv.join(', ')}`);
      }
    }

    await pretty.newline();
    if (allGood) {
      await pretty.info('All tools are ready to use!');
    } else {
      await pretty.warn('Some tools need attention. Install packages and set env vars as needed.');
    }
  }
}

async function toolExample(args: string[], options: ToolsOptions, outputFormat: string): Promise<void> {
  const toolId = args[0];
  
  if (!toolId) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a tool ID'));
    } else {
      await pretty.error('Please provide a tool ID');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  // Tool examples
  const examples: Record<string, string> = {
    'code-execution': `
import { Agent, tools } from 'praisonai';

const agent = new Agent({
  name: 'CodeRunner',
  instructions: 'You can execute Python code to solve problems.',
  tools: [tools.codeExecution()],
});

const result = await agent.run('Calculate the factorial of 10');
console.log(result.text);
`,
    'tavily': `
import { Agent, tools } from 'praisonai';

const agent = new Agent({
  name: 'Researcher',
  instructions: 'Search the web for information.',
  tools: [tools.tavily()],
});

const result = await agent.run('What are the latest AI developments?');
console.log(result.text);
`,
    'exa': `
import { Agent, tools } from 'praisonai';

const agent = new Agent({
  name: 'WebSearcher',
  instructions: 'Search the web using semantic search.',
  tools: [tools.exa()],
});

const result = await agent.run('Find AI companies in Europe');
console.log(result.text);
`,
    'superagent': `
import { Agent, tools } from 'praisonai';

const agent = new Agent({
  name: 'SecureAgent',
  instructions: 'Process text securely.',
  tools: [
    tools.guard(),   // Check for prompt injection
    tools.redact(),  // Remove PII
    tools.verify(),  // Verify claims
  ],
});

const result = await agent.run('Check this text for security issues');
console.log(result.text);
`,
    'valyu': `
import { Agent, tools } from 'praisonai';

const agent = new Agent({
  name: 'FinanceResearcher',
  instructions: 'Research financial data.',
  tools: [
    tools.valyuFinanceSearch(),
    tools.valyuSecSearch(),
  ],
});

const result = await agent.run('What is Apple stock price trend?');
console.log(result.text);
`,
  };

  const example = examples[toolId];
  
  if (!example) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.TOOL_NOT_FOUND, `No example for tool: ${toolId}`));
    } else {
      await pretty.error(`No example available for: ${toolId}`);
      await pretty.dim(`Available examples: ${Object.keys(examples).join(', ')}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ toolId, example: example.trim() }));
  } else {
    await pretty.heading(`Example: ${toolId}`);
    await pretty.plain(example);
  }
}

async function toolAdd(args: string[], options: ToolsOptions, outputFormat: string): Promise<void> {
  const packageOrPath = args[0];
  
  if (!packageOrPath) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a package name or path'));
    } else {
      await pretty.error('Please provide a package name or path');
      await pretty.dim('Usage: praisonai-ts tools add <package-name>');
      await pretty.dim('       praisonai-ts tools add ./path/to/tool.js');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  try {
    const { registerNpmTool, registerLocalTool } = await import('../../tools/builtins/custom');
    
    const isLocalPath = packageOrPath.startsWith('./') || packageOrPath.startsWith('/');
    const tool = isLocalPath 
      ? await registerLocalTool(packageOrPath)
      : await registerNpmTool(packageOrPath);

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        registered: true,
        tool: {
          name: tool.name,
          description: tool.description,
          source: isLocalPath ? 'local' : 'npm',
        }
      }));
    } else {
      await pretty.info(`Successfully registered tool: ${tool.name}`);
      await pretty.dim(`Description: ${tool.description}`);
    }
  } catch (error) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.RUNTIME_ERROR, `Failed to register tool: ${error}`));
    } else {
      await pretty.error(`Failed to register tool: ${error}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }
}

async function toolTest(args: string[], options: ToolsOptions, outputFormat: string): Promise<void> {
  const toolId = args[0];
  
  if (!toolId) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a tool ID'));
    } else {
      await pretty.error('Please provide a tool ID');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  ensureBuiltinsRegistered();
  const registry = getToolsRegistry();
  const metadata = registry.getMetadata(toolId);

  if (!metadata) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.TOOL_NOT_FOUND, `Tool not found: ${toolId}`));
    } else {
      await pretty.error(`Tool not found: ${toolId}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }

  // Check dependencies
  const missingEnv = metadata.requiredEnv.filter(env => !process.env[env]);
  
  if (missingEnv.length > 0 && !options.live) {
    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        toolId,
        status: 'dry_run',
        message: 'Dry run completed. Missing env vars for live test.',
        missingEnv,
      }));
    } else {
      await pretty.info(`Dry run for ${toolId}:`);
      await pretty.plain(`  Tool ID: ${metadata.id}`);
      await pretty.plain(`  Package: ${metadata.packageName}`);
      await pretty.warn(`  Missing env vars: ${missingEnv.join(', ')}`);
      await pretty.dim('\nUse --live flag to run actual test (requires env vars)');
    }
    return;
  }

  if (options.live) {
    if (missingEnv.length > 0) {
      if (outputFormat === 'json') {
        outputJson(formatError(ERROR_CODES.MISSING_ARG, `Missing required env vars: ${missingEnv.join(', ')}`));
      } else {
        await pretty.error(`Cannot run live test. Missing env vars: ${missingEnv.join(', ')}`);
      }
      process.exit(EXIT_CODES.RUNTIME_ERROR);
    }

    try {
      const tool = registry.create(toolId);
      await pretty.info(`Live test for ${toolId}...`);
      
      // Simple test execution
      const testInput = { query: 'test' };
      const result = await tool.execute(testInput);
      
      if (outputFormat === 'json') {
        outputJson(formatSuccess({
          toolId,
          status: 'success',
          result,
        }));
      } else {
        await pretty.info('Test passed!');
        await pretty.plain(`Result: ${JSON.stringify(result, null, 2)}`);
      }
    } catch (error) {
      if (outputFormat === 'json') {
        outputJson(formatError(ERROR_CODES.RUNTIME_ERROR, `Test failed: ${error}`));
      } else {
        await pretty.error(`Test failed: ${error}`);
      }
      process.exit(EXIT_CODES.RUNTIME_ERROR);
    }
  } else {
    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        toolId,
        status: 'dry_run',
        message: 'Dry run completed successfully.',
        metadata: {
          id: metadata.id,
          package: metadata.packageName,
          envVars: metadata.requiredEnv,
        }
      }));
    } else {
      await pretty.info(`Dry run for ${toolId}: OK`);
      await pretty.plain(`  Tool is registered and ready`);
      await pretty.dim('\nUse --live flag to run actual API test');
    }
  }
}
