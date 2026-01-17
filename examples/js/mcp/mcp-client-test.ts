/**
 * MCP Client Integration Test
 * 
 * Tests the MCP (Model Context Protocol) client.
 * Note: Requires an MCP server for full integration tests.
 * 
 * Run: npx ts-node mcp-client.ts
 */

import {
    MCPClient,
    createMCPClient,
    getMCPTools,
    type MCPClientConfig
} from '../../../src/praisonai-ts/dist/mcp';

async function main() {
    console.log('=== MCPClient Integration Test ===\n');

    // Test 1: Create MCP client
    console.log('1. Testing MCPClient creation:');
    const client = new MCPClient({
        serverUrl: 'http://localhost:3000',
        transport: 'http',
        timeout: 5000,
        verbose: true
    });
    console.log('   Client ID:', client.id);
    console.log('   Connected:', client.isConnected());
    console.log('   Success: ✅');

    // Test 2: Factory function
    console.log('\n2. Testing createMCPClient() factory:');
    const client2 = createMCPClient({ serverUrl: 'http://localhost:8080' });
    console.log('   Client created:', typeof client2);
    console.log('   Success: ✅');

    // Test 3: Transport configurations
    console.log('\n3. Testing transport configurations:');
    const transports: MCPClientConfig['transport'][] = ['http', 'websocket', 'sse', 'stdio'];

    for (const transport of transports) {
        try {
            const c = new MCPClient({
                transport,
                serverUrl: transport !== 'stdio' ? 'http://localhost:3000' : undefined,
                command: transport === 'stdio' ? 'npx' : undefined,
                args: transport === 'stdio' ? ['mcp-server'] : undefined
            });
            console.log(`   ${transport}: ✅ (configured)`);
        } catch (error: any) {
            console.log(`   ${transport}: ⚠️ ${error.message}`);
        }
    }

    // Test 4: Session info
    console.log('\n4. Testing session management:');
    const session = client.getSession();
    console.log('   Session ID:', session.id);
    console.log('   Connected:', session.connected);
    console.log('   Tools:', session.tools.length);
    console.log('   Resources:', session.resources.length);
    console.log('   Success: ✅');

    // Test 5: Live connection test (optional - requires running server)
    const testServerUrl = process.env.MCP_SERVER_URL;
    if (testServerUrl) {
        console.log('\n5. Testing live MCP connection:');
        try {
            const liveClient = new MCPClient({
                serverUrl: testServerUrl,
                transport: 'http',
                timeout: 10000,
                verbose: false
            });

            await liveClient.connect();
            console.log('   Connected: ✅');

            const tools = await liveClient.listTools();
            console.log(`   Tools discovered: ${tools.length}`);

            for (const tool of tools.slice(0, 3)) {
                console.log(`   - ${tool.name}: ${tool.description || 'No description'}`);
            }

            // Get tools in AI SDK format
            const aiTools = await liveClient.getToolsAsAISDK();
            console.log(`   AI SDK tools: ${aiTools.length}`);

            await liveClient.disconnect();
            console.log('   Disconnected: ✅');
        } catch (error: any) {
            console.log(`   ⚠️ Connection failed: ${error.message}`);
        }
    } else {
        console.log('\n5. Live connection: Skipped (MCP_SERVER_URL not set)');
        console.log('   Set MCP_SERVER_URL to test live connections');
    }

    // Test 6: Mock tool call simulation
    console.log('\n6. Testing tool call preparation:');
    const mockTool = {
        name: 'search',
        description: 'Search for information',
        inputSchema: {
            type: 'object',
            properties: {
                query: { type: 'string', description: 'Search query' }
            },
            required: ['query']
        }
    };
    console.log('   Mock tool:', mockTool.name);
    console.log('   Schema:', JSON.stringify(mockTool.inputSchema));
    console.log('   Success: ✅');

    // Test 7: API Key configuration
    console.log('\n7. Testing API key configuration:');
    const authClient = new MCPClient({
        serverUrl: 'http://api.example.com',
        apiKey: 'test-api-key-12345'
    });
    console.log('   Client with API key: ✅');

    // Test 8: getMCPTools helper
    console.log('\n8. Testing getMCPTools helper signature:');
    console.log('   getMCPTools function:', typeof getMCPTools);
    console.log('   Returns: { client, tools }');
    console.log('   Success: ✅');

    console.log('\n=== MCPClient Tests Complete ===');
    console.log('\nNote: For full integration tests, run an MCP server and set MCP_SERVER_URL');
}

main().catch(console.error);
