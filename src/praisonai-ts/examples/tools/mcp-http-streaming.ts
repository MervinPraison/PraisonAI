/**
 * Example demonstrating MCP with HTTP-Streaming transport in TypeScript.
 * 
 * This example shows:
 * 1. Auto-detection of transport based on URL
 * 2. Explicit transport selection
 * 3. Backward compatibility with existing code
 */

import { Agent } from '../../agent';
import { MCP, createMCPClient } from '../../tools/mcp';

async function main() {
  console.log('MCP HTTP-Streaming Transport Examples\n');

  // Example 1: Auto-detection - SSE endpoint (backward compatible)
  console.log('Example 1: Auto-detection with SSE endpoint');
  try {
    const mcpSseAuto = new MCP('http://localhost:8080/sse');
    await mcpSseAuto.initialize();
    console.log(`✓ Transport detected: ${mcpSseAuto.getTransportType()}`);
    console.log(`  Tools available: ${mcpSseAuto.tools.length}`);
    await mcpSseAuto.close();
  } catch (error) {
    console.log(`Note: ${error instanceof Error ? error.message : error}`);
  }

  // Example 2: Auto-detection - HTTP endpoint
  console.log('\nExample 2: Auto-detection with HTTP endpoint');
  try {
    const mcpHttpAuto = new MCP('http://localhost:8080/api');
    await mcpHttpAuto.initialize();
    console.log(`✓ Transport detected: ${mcpHttpAuto.getTransportType()}`);
    console.log(`  Tools available: ${mcpHttpAuto.tools.length}`);
    await mcpHttpAuto.close();
  } catch (error) {
    console.log(`Note: ${error instanceof Error ? error.message : error}`);
  }

  // Example 3: Explicit SSE transport
  console.log('\nExample 3: Explicit SSE transport selection');
  try {
    const mcpSseExplicit = new MCP('http://localhost:8080/api', {
      transport: 'sse'
    });
    await mcpSseExplicit.initialize();
    console.log(`✓ Transport selected: ${mcpSseExplicit.getTransportType()}`);
    await mcpSseExplicit.close();
  } catch (error) {
    console.log(`Note: ${error instanceof Error ? error.message : error}`);
  }

  // Example 4: Explicit HTTP-streaming transport
  console.log('\nExample 4: Explicit HTTP-streaming transport selection');
  try {
    const mcpHttpExplicit = new MCP('http://localhost:8080/sse', {
      transport: 'http-streaming'
    });
    await mcpHttpExplicit.initialize();
    console.log(`✓ Transport selected: ${mcpHttpExplicit.getTransportType()}`);
    await mcpHttpExplicit.close();
  } catch (error) {
    console.log(`Note: ${error instanceof Error ? error.message : error}`);
  }

  // Example 5: HTTP-streaming with options
  console.log('\nExample 5: HTTP-streaming with custom options');
  try {
    const mcpHttpOptions = new MCP('http://localhost:8080/api', {
      transport: 'http-streaming',
      debug: true,
      timeout: 30000,
      headers: {
        'Authorization': 'Bearer your-token-here'
      }
    });
    await mcpHttpOptions.initialize();
    console.log(`✓ Transport configured: ${mcpHttpOptions.getTransportType()}`);
    const stats = mcpHttpOptions.getStats();
    console.log(`  Connection stats:`, stats);
    await mcpHttpOptions.close();
  } catch (error) {
    console.log(`Note: ${error instanceof Error ? error.message : error}`);
  }

  // Example 6: Using with Agent
  console.log('\nExample 6: Using MCP with Agent');
  try {
    // Create MCP client
    const mcp = await createMCPClient('http://localhost:8080/api', {
      transport: 'http-streaming'
    });

    // Create tool functions for the agent
    const toolFunctions: Record<string, Function> = {};
    for (const tool of mcp) {
      toolFunctions[tool.name] = async (...args: any[]) => {
        const params = args[0] || {};
        return tool.execute(params);
      };
    }

    // Create agent with MCP tools
    const agent = new Agent({
      name: 'MCP Assistant',
      instructions: 'You are a helpful assistant that can use MCP tools.',
      model: 'openai/gpt-4o-mini',
      tools: mcp.toOpenAITools(),
      toolFunctions
    });

    console.log('✓ Agent created with MCP tools');
    console.log(`  Available tools: ${mcp.tools.map(t => t.name).join(', ')}`);

    // Clean up
    await mcp.close();
  } catch (error) {
    console.log(`Note: ${error instanceof Error ? error.message : error}`);
  }

  // Example 7: Backward compatibility check
  console.log('\nExample 7: Backward compatibility');
  try {
    // Old style import still works
    const { MCP: MCPOld } = await import('../../tools/mcpSse');
    const oldClient = new MCPOld('http://localhost:8080/sse');
    console.log('✓ Old import style still works');
  } catch (error) {
    console.log(`Note: ${error instanceof Error ? error.message : error}`);
  }

  console.log('\n' + '='.repeat(60));
  console.log('Summary: HTTP-Streaming support with full backward compatibility!');
  console.log('- Auto-detection: URLs ending with /sse use SSE transport');
  console.log('- Explicit control: Use transport option for manual selection');
  console.log('- All existing code continues to work without modification');
  console.log('='.repeat(60));
}

// Run the examples
main().catch(console.error);