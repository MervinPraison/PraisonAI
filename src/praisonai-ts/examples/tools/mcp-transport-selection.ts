import { Agent, MCP, TransportType } from 'praisonai-ts';

async function main() {
  // Example 1: Automatic transport detection (default behavior)
  const mcpAuto = new MCP('http://127.0.0.1:8080/sse'); // Will use SSE
  await mcpAuto.initialize();
  console.log(`Auto-detected transport: ${mcpAuto.transportType}`);

  // Example 2: Explicit SSE transport
  const mcpSSE = new MCP('http://127.0.0.1:8080/api', 'sse');
  await mcpSSE.initialize();
  console.log(`Explicit SSE transport: ${mcpSSE.transportType}`);

  // Example 3: Explicit HTTP-Streaming transport
  const mcpHTTP = new MCP('http://127.0.0.1:8080/stream', 'http-streaming');
  await mcpHTTP.initialize();
  console.log(`Explicit HTTP-Streaming transport: ${mcpHTTP.transportType}`);

  // Example 4: Auto-detection with non-SSE URL
  const mcpAutoHTTP = new MCP('http://127.0.0.1:8080/api'); // Will use HTTP-Streaming
  await mcpAutoHTTP.initialize();
  console.log(`Auto-detected transport for non-SSE URL: ${mcpAutoHTTP.transportType}`);

  // Create tool execution functions
  const toolFunctions = Object.fromEntries(
    [...mcpAuto].map(tool => [
      tool.name,
      async (args: any) => tool.execute(args)
    ])
  );

  // Create agent with MCP tools
  const agent = new Agent({
    instructions: 'You are a helpful assistant with access to MCP tools.',
    name: 'MCPTransportAgent',
    tools: mcpAuto.toOpenAITools(),
    toolFunctions
  });

  // Use the agent
  const response = await agent.runSync('What tools are available?');
  console.log('Agent response:', response);

  // Cleanup
  await mcpAuto.close();
  await mcpSSE.close();
  await mcpHTTP.close();
  await mcpAutoHTTP.close();
}

// Run the example
main().catch(console.error);