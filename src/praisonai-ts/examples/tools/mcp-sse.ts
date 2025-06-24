import { Agent } from '../../src/agent';
import { MCP } from '../../src/tools/mcpSse';

async function main() {
  // Connect to the running SSE server
  const mcp = new MCP('http://127.0.0.1:8080/sse');
  try {
    await mcp.initialize();
  } catch (error) {
    console.error('Failed to connect to MCP SSE server:', error);
    console.error('Please ensure the server is running at http://127.0.0.1:8080/sse');
    process.exit(1);
  }

  // Create tool functions that call the remote MCP tools
  const toolFunctions: Record<string, (...args: any[]) => Promise<any>> = {};
  
  if (mcp.tools.length === 0) {
    console.warn('Warning: No MCP tools available. Make sure the MCP server is running.');
  }
  
  for (const tool of mcp) {
    if (!tool || typeof tool.name !== 'string') {
      console.warn('Skipping invalid tool:', tool);
      continue;
    }
    
    const paramNames = Object.keys(tool.schemaProperties || {});
    toolFunctions[tool.name] = async (...args: any[]) => {
      const params: Record<string, any> = {};
      
      if (args.length === 1 && typeof args[0] === 'object' && args[0] !== null) {
        // If single object argument, use it directly as params
        Object.assign(params, args[0]);
      } else {
        // Map positional arguments with validation
        if (args.length > paramNames.length) {
          console.warn(
            `Tool ${tool.name}: Too many arguments provided. Expected ${paramNames.length}, got ${args.length}`
          );
        }
        for (let i = 0; i < Math.min(args.length, paramNames.length); i++) {
          params[paramNames[i]] = args[i];
        }
      }
      return tool.execute(params);
    };
  }

  const agent = new Agent({
    instructions: 'Use the tools to greet people and report the weather.',
    name: 'MCPAgent',
    tools: mcp.toOpenAITools(),
    toolFunctions
  });

  try {
    const result = await agent.start('Say hello to John and tell the weather in London.');
    console.log('\nFinal Result:', result);
  } catch (error) {
    console.error('Agent execution failed:', error);
  } finally {
    // Clean up MCP connection
    await mcp.close();
  }
}

if (require.main === module) {
  main();
}
