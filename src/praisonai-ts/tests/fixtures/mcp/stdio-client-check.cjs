const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const childProcess = require('node:child_process');
const nativeSpawn = childProcess.spawn;
const spawned = [];
childProcess.spawn = function (...args) { const child = nativeSpawn.apply(this, args); spawned.push(child); return child; };
const scenario = process.argv[2];
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-mcp-'));
const handshakeFile = path.join(directory, 'handshake');
const { MCPClient } = require('../../../src/mcp');
const client = new MCPClient({ transport: 'stdio', command: process.execPath, args: [path.join(__dirname, 'stdio-server.cjs')], env: { PRAISON_MCP_FIXTURE_VALUE: 'retained', PRAISON_MCP_FIXTURE_NO_TOOLS: scenario === 'no-tools' ? '1' : '0', PRAISON_MCP_FIXTURE_SLOW_LIST: scenario === 'discovery-timeout' ? '1' : '0', PRAISON_MCP_FIXTURE_HANDSHAKE_FILE: scenario === 'handshake-disconnect' ? handshakeFile : '', PRAISON_MCP_FIXTURE_EXIT_ON_LIST: process.argv[2] === 'startup-close' ? '1' : '0' }, timeout: scenario.startsWith('request-') ? 1000 : 5000, requestTimeout: ['request-timeout', 'discovery-timeout'].includes(scenario) ? 100 : 3000 });
const deadline = setTimeout(() => { client.disconnect().finally(() => process.exit(2)); }, 10000);
process.on('uncaughtException', error => { console.error(error); client.disconnect().finally(() => process.exit(1)); });
(async () => {
  try {
    if (scenario === 'handshake-disconnect' || scenario === 'early-disconnect') {
      const connecting = client.connect();
      // Observe rejection immediately so cancellation never creates an unhandled rejection.
      const rejected = assert.rejects(connecting, /closed|disconnect/i);
      if (scenario === 'handshake-disconnect') {
        const limit = Date.now() + 4000;
        while (!fs.existsSync(handshakeFile) && Date.now() < limit) await new Promise(resolve => setTimeout(resolve, 10));
        assert.ok(fs.existsSync(handshakeFile), 'peer must enter the delayed handshake');
      }
      await client.disconnect();
      await rejected;
      assert.equal(client.isConnected(), false);
      assert.equal(spawned.length, scenario === 'early-disconnect' ? 0 : 1);
      for (const peer of spawned) {
        assert.equal(typeof peer.pid, 'number');
        assert.throws(() => process.kill(peer.pid, 0), { code: 'ESRCH' });
      }
      return;
    }
    if (scenario === 'discovery-timeout') {
      await assert.rejects(client.connect(), /timed out/i);
      assert.equal(client.isConnected(), false);
      assert.equal(spawned.length, 1);
      assert.throws(() => process.kill(spawned[0].pid, 0), { code: 'ESRCH' });
      return;
    }
    if (process.argv[2] === 'startup-close') {
      await assert.rejects(client.connect(), /closed/i);
      assert.equal(client.isConnected(), false);
      return;
    }
    await client.connect();
    switch (process.argv[2]) {
      case 'no-tools':
        assert.deepEqual(await client.listTools(), []);
        assert.equal(client.isConnected(), true);
        break;
      case 'request-long':
        assert.equal((await client.callTool('echo', { text: 'slow result', delay: 1500 })).content[0].text, 'slow result');
        break;
      case 'request-timeout':
        await assert.rejects(client.callTool('echo', { text: 'late', delay: 500 }), /timed out/i);
        break;
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
    childProcess.spawn = nativeSpawn;
    await client.disconnect();
    assert.equal(client.isConnected(), false);
    fs.rmSync(directory, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
