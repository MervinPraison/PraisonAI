const assert = require('node:assert/strict');
const path = require('node:path');
const { MCPClient } = require('../../../src/mcp');
const client = new MCPClient({ transport: 'stdio', command: process.execPath, args: [path.join(__dirname, 'stdio-server.cjs')], env: { PRAISON_MCP_FIXTURE_VALUE: 'retained', PRAISON_MCP_FIXTURE_EXIT_ON_LIST: process.argv[2] === 'startup-close' ? '1' : '0' }, timeout: 5000 });
const deadline = setTimeout(() => { client.disconnect().finally(() => process.exit(2)); }, 10000);
process.on('uncaughtException', error => { console.error(error); client.disconnect().finally(() => process.exit(1)); });
(async () => {
  try {
    if (process.argv[2] === 'startup-close') {
      await assert.rejects(client.connect(), /closed/i);
      assert.equal(client.isConnected(), false);
      return;
    }
    await client.connect();
    switch (process.argv[2]) {
      case 'handshake':
        assert.equal(client.getSession().serverInfo?.name, 'offline-echo');
        assert.deepEqual((await client.listTools()).map(tool => tool.name), ['echo']);
        break;
      case 'result':
        assert.deepEqual(await client.callTool('echo', { text: 'hello' }), { content: [{ type: 'text', text: 'hello' }] });
        break;
      case 'concurrent': {
        const [slow, fast] = await Promise.all([client.callTool('echo', { text: 'slow', delay: 30 }), client.callTool('echo', { text: 'fast' })]);
        assert.equal(slow.content[0].text, 'slow');
        assert.equal(fast.content[0].text, 'fast');
        break;
      }
      case 'large': {
        const text = '你好🙂'.repeat(20000);
        assert.equal((await client.callTool('echo', { text })).content[0].text, text);
        break;
      }
      case 'error':
        await assert.rejects(client.callTool('fail', {}), /fixture tool error/);
        break;
      case 'environment':
        assert.equal((await client.callTool('environment', {})).content[0].text, 'retained');
        break;
    }
  } finally {
    clearTimeout(deadline);
    await client.disconnect();
    assert.equal(client.isConnected(), false);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
