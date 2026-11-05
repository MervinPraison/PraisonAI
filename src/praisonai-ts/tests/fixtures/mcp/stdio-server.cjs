const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const { ListToolsRequestSchema, CallToolRequestSchema, InitializeRequestSchema, McpError, ErrorCode } = require('@modelcontextprotocol/sdk/types.js');
const noTools = process.env.PRAISON_MCP_FIXTURE_NO_TOOLS === '1';
const server = new Server({ name: 'offline-echo', version: '1.0.0' }, { capabilities: noTools ? {} : { tools: {} } });
if (process.env.PRAISON_MCP_FIXTURE_HANDSHAKE_FILE) {
  server.setRequestHandler(InitializeRequestSchema, async request => {
    require('node:fs').writeFileSync(process.env.PRAISON_MCP_FIXTURE_HANDSHAKE_FILE, String(process.pid));
    await new Promise(resolve => setTimeout(resolve, 1000));
    return { protocolVersion: request.params.protocolVersion, capabilities: { tools: {} }, serverInfo: { name: 'offline-echo', version: '1.0.0' } };
  });
}
if (!noTools) {
server.setRequestHandler(ListToolsRequestSchema, async () => {
  if (process.env.PRAISON_MCP_FIXTURE_EXIT_ON_LIST === '1') process.exit(0);
  if (process.env.PRAISON_MCP_FIXTURE_SLOW_LIST === '1') await new Promise(resolve => setTimeout(resolve, 300));
  return { tools: [{ name: 'echo', inputSchema: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] } }] };
});
server.setRequestHandler(CallToolRequestSchema, async request => {
  if (request.params.name === 'fail') throw new McpError(ErrorCode.InvalidParams, 'fixture tool error');
  if (request.params.arguments.delay) await new Promise(resolve => setTimeout(resolve, request.params.arguments.delay));
  return { content: [{ type: 'text', text: request.params.name === 'environment' ? process.env.PRAISON_MCP_FIXTURE_VALUE : request.params.arguments.text }] };
});
}
server.connect(new StdioServerTransport()).catch(error => { console.error(error); process.exitCode = 1; });
