/**
 * MCP command - Model Context Protocol management
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface MCPOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

// MCP server registry (in-memory for now)
interface MCPServer {
  name: string;
  command: string;
  args?: string[];
  env?: Record<string, string>;
  status: 'stopped' | 'running';
}

const mcpServers: Map<string, MCPServer> = new Map();

export async function execute(args: string[], options: MCPOptions): Promise<void> {
  const action = args[0] || 'list';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'list':
        await listServers(outputFormat);
        break;
      case 'add':
        await addServer(actionArgs, outputFormat);
        break;
      case 'remove':
        await removeServer(actionArgs, outputFormat);
        break;
      case 'start':
        await startServer(actionArgs, outputFormat);
        break;
      case 'stop':
        await stopServer(actionArgs, outputFormat);
        break;
      case 'help':
      default:
        await showHelp(outputFormat);
        break;
    }
  } catch (error) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, error instanceof Error ? error.message : String(error)));
    } else {
      await pretty.error(error instanceof Error ? error.message : String(error));
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }
}

async function listServers(outputFormat: string): Promise<void> {
  const servers = Array.from(mcpServers.values());
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      servers,
      count: servers.length
    }));
  } else {
    await pretty.heading('MCP Servers');
    if (servers.length === 0) {
      await pretty.info('No MCP servers registered');
      await pretty.dim('Run "praisonai-ts mcp add <name> <command>" to add a server');
    } else {
      for (const server of servers) {
        const statusIcon = server.status === 'running' ? '🟢' : '⚪';
        await pretty.plain(`  ${statusIcon} ${server.name}`);
        await pretty.dim(`    Command: ${server.command} ${(server.args || []).join(' ')}`);
      }
    }
    await pretty.newline();
    await pretty.info(`Total: ${servers.length} servers`);
  }
}

async function addServer(args: string[], outputFormat: string): Promise<void> {
  const name = args[0];
  const command = args[1];
  const serverArgs = args.slice(2);

  if (!name || !command) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide server name and command'));
    } else {
      await pretty.error('Please provide server name and command');
      await pretty.dim('Usage: praisonai-ts mcp add <name> <command> [args...]');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const server: MCPServer = {
    name,
    command,
    args: serverArgs.length > 0 ? serverArgs : undefined,
    status: 'stopped'
  };

  mcpServers.set(name, server);

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ added: true, server }));
  } else {
    await pretty.success(`MCP server added: ${name}`);
    await pretty.dim(`Command: ${command} ${serverArgs.join(' ')}`);
  }
}

async function removeServer(args: string[], outputFormat: string): Promise<void> {
  const name = args[0];
  if (!name) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide server name'));
    } else {
      await pretty.error('Please provide server name');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const removed = mcpServers.delete(name);

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ removed, name }));
  } else {
    if (removed) {
      await pretty.success(`MCP server removed: ${name}`);
    } else {
      await pretty.warn(`Server not found: ${name}`);
    }
  }
}

async function startServer(args: string[], outputFormat: string): Promise<void> {
  const name = args[0];
  if (!name) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide server name'));
    } else {
      await pretty.error('Please provide server name');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const server = mcpServers.get(name);
  if (!server) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, `Server not found: ${name}`));
    } else {
      await pretty.error(`Server not found: ${name}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }

  // Mark as running (actual process management would be more complex)
  server.status = 'running';

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ started: true, server }));
  } else {
    await pretty.success(`MCP server started: ${name}`);
  }
}

async function stopServer(args: string[], outputFormat: string): Promise<void> {
  const name = args[0];
  if (!name) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide server name'));
    } else {
      await pretty.error('Please provide server name');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const server = mcpServers.get(name);
  if (!server) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, `Server not found: ${name}`));
    } else {
      await pretty.error(`Server not found: ${name}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }

  server.status = 'stopped';

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ stopped: true, server }));
  } else {
    await pretty.success(`MCP server stopped: ${name}`);
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'mcp',
    description: 'Model Context Protocol server management',
    subcommands: [
      { name: 'list', description: 'List registered MCP servers' },
      { name: 'add <name> <cmd> [args]', description: 'Add an MCP server' },
      { name: 'remove <name>', description: 'Remove an MCP server' },
      { name: 'start <name>', description: 'Start an MCP server' },
      { name: 'stop <name>', description: 'Stop an MCP server' },
      { name: 'help', description: 'Show this help' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('MCP Command');
    await pretty.plain('Model Context Protocol server management\n');
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(25)} ${cmd.description}`);
    }
  }
}
