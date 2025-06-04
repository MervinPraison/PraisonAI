import { Agent } from '../../src/agent';
import { MCP, MCPTool } from '../../src/tools/mcpSse';

async function main() {
  // Connect to the running SSE server
  const mcp = new MCP('http://127.0.0.1:8080/sse');
  await mcp.initialize();

  // Create tool functions that call the remote MCP tools
  const toolFunctions: Record<string, (...args: any[]) => Promise<any>> = {};
  for (const tool of mcp) {
    const paramNames = Object.keys((tool as any).inputSchema?.properties || {});
    toolFunctions[tool.name] = async (...args: any[]) => {
      const params: Record<string, any> = {};
      for (let i = 0; i < args.length; i++) {
        params[paramNames[i] || `arg${i}`] = args[i];
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

  const result = await agent.start('Say hello to John and tell the weather in London.');
  console.log('\nFinal Result:', result);
}

if (require.main === module) {
  main();
}
