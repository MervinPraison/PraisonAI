/**
 * MCP Filesystem Server Example
 * 
 * Demonstrates using MCP to connect to a filesystem server.
 * 
 * Prerequisites:
 *   npm install praisonai-ts
 *   export OPENAI_API_KEY=your-api-key
 * 
 * Run:
 *   npx ts-node filesystem-mcp.ts
 */

import { Agent, createMCP } from '../../../src/praisonai-ts/src';

async function main() {
  console.log('=== MCP Filesystem Server Example ===\n');

  // Connect to MCP filesystem server
  const mcp = await createMCP({
    transport: {
      type: 'stdio',
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-filesystem', '.'],
    },
  });

  console.log('Connected to MCP filesystem server\n');

  // Get tools from MCP server
  const tools = await mcp.tools();
  console.log('Available tools:', Object.keys(tools));

  // Create agent with MCP tools
  const agent = new Agent({
    name: 'FileAgent',
    instructions: 'You help manage files using the filesystem tools.',
    tools: Object.values(tools),
  });

  // Ask the agent to list files
  const response = await agent.chat('List all TypeScript files in the current directory');
  console.log('\nResponse:', response);

  // Cleanup
  await mcp.close();
}

main().catch(console.error);
