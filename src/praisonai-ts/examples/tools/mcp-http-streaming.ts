/**
 * Example demonstrating HTTP-Streaming support for MCP in PraisonAI TypeScript
 * 
 * This example shows how to use the new HTTP-Streaming transport with backward compatibility.
 */

import { Agent } from '../../src/agents/Agent';
import { MCP } from '../../src/tools/mcp';

async function main() {
  console.log('MCP HTTP-Streaming Examples');
  console.log('===========================\n');

  // Example 1: Auto-detection (backward compatible)
  console.log('Example 1: Auto-detection of transport');
  console.log('--------------------------------------');

  // URLs ending with /sse will use SSE transport
  const mcpSse = new MCP('http://localhost:8080/sse'); // Auto-detects SSE
  await mcpSse.initialize();
  console.log(`SSE transport detected: ${mcpSse.transport}`);

  // Other HTTP URLs will use HTTP-Streaming transport
  const mcpHttp = new MCP('http://localhost:8080/stream'); // Auto-detects HTTP-Streaming
  await mcpHttp.initialize();
  console.log(`HTTP-Streaming transport detected: ${mcpHttp.transport}`);

  // Example 2: Explicit transport selection
  console.log('\nExample 2: Explicit transport selection');
  console.log('---------------------------------------');

  // Force SSE transport
  const mcpForceSse = new MCP('http://localhost:8080/api', { transport: 'sse' });
  await mcpForceSse.initialize();
  console.log(`Forced SSE transport: ${mcpForceSse.transport}`);

  // Force HTTP-Streaming transport
  const mcpForceHttp = new MCP('http://localhost:8080/api', { transport: 'http-streaming' });
  await mcpForceHttp.initialize();
  console.log(`Forced HTTP-Streaming transport: ${mcpForceHttp.transport}`);

  // Example 3: Using with an Agent
  console.log('\nExample 3: Using with an Agent');
  console.log('------------------------------');

  const agent = new Agent({
    name: 'Assistant',
    instructions: 'You are a helpful assistant with access to MCP tools',
    llm: { model: 'gpt-4o-mini' }
  });

  // Initialize MCP with HTTP-Streaming
  const mcp = new MCP('http://localhost:8080/stream', { 
    transport: 'http-streaming',
    debug: true 
  });

  try {
    await mcp.initialize();
    
    // Add MCP tools to agent
    for (const tool of mcp.tools) {
      agent.addTool(tool);
    }
    
    console.log(`Added ${mcp.tools.length} tools to agent`);
    
    // Use the agent
    const response = await agent.start('What tools do you have available?');
    console.log('Agent response:', response);
  } catch (error) {
    console.log('Note: Server not running. This is just an example.');
    console.log('Error:', error);
  }

  // Example 4: Complete backward compatibility
  console.log('\nExample 4: Complete backward compatibility');
  console.log('------------------------------------------');

  // Import the old MCP class directly (still works)
  const { MCP: MCPSse } = await import('../../src/tools/mcpSse');
  
  const legacyMcp = new MCPSse('http://localhost:8080/sse');
  console.log('Legacy SSE-only MCP class still works!');

  // Clean up
  await mcpSse.close();
  await mcpHttp.close();
  await mcpForceSse.close();
  await mcpForceHttp.close();
  await mcp.close();
  await legacyMcp.close();

  console.log('\nAll examples demonstrate backward compatibility!');
  console.log('Existing code requires ZERO changes.');
}

main().catch(console.error);