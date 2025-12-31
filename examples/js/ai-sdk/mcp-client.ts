/**
 * MCP Client Example (AI SDK v6 Parity)
 * 
 * Demonstrates Model Context Protocol client with HTTP/SSE transports.
 * 
 * Run: npx ts-node mcp-client.ts
 * Note: Requires an MCP server running
 */

import { 
  createMCP,
  closeMCPClient,
  type MCPConfig,
} from '../../../src/praisonai-ts/src';

async function main() {
  console.log('=== MCP Client Example ===\n');

  // Example configurations for different transports
  const configs: Record<string, MCPConfig> = {
    // HTTP transport (recommended for production)
    http: {
      transport: {
        type: 'http',
        url: 'https://mcp-server.example.com/mcp',
        headers: { Authorization: 'Bearer token' },
      },
      name: 'http-client',
    },
    // SSE transport
    sse: {
      transport: {
        type: 'sse',
        url: 'https://mcp-server.example.com/sse',
      },
      name: 'sse-client',
    },
    // Stdio transport (for local servers)
    stdio: {
      transport: {
        type: 'stdio',
        command: 'npx',
        args: ['-y', '@modelcontextprotocol/server-everything'],
      },
      name: 'stdio-client',
    },
  };

  console.log('MCP Transport Configurations:');
  console.log('');
  console.log('1. HTTP Transport (recommended):');
  console.log(`   ${JSON.stringify(configs.http.transport, null, 2)}`);
  console.log('');
  console.log('2. SSE Transport:');
  console.log(`   ${JSON.stringify(configs.sse.transport, null, 2)}`);
  console.log('');
  console.log('3. Stdio Transport (local):');
  console.log(`   ${JSON.stringify(configs.stdio.transport, null, 2)}`);

  console.log('\n--- Example Usage ---\n');
  console.log(`
// Create MCP client
const client = await createMCP({
  transport: {
    type: 'http',
    url: 'https://your-mcp-server.com/mcp',
    headers: { Authorization: 'Bearer your-token' },
  }
});

// Get available tools
const tools = await client.tools();
console.log('Available tools:', Object.keys(tools));

// List resources
const resources = await client.listResources();
console.log('Resources:', resources);

// List prompts
const prompts = await client.listPrompts();
console.log('Prompts:', prompts);

// Close when done
await closeMCPClient('default');
`);

  console.log('\n✅ MCP Client demo completed!');
  console.log('Note: To run with a real MCP server, uncomment the connection code.');
}

main().catch(console.error);
