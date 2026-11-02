import { describe, expect, it } from '@jest/globals';
import { spawnSync } from 'child_process';
import { resolve } from 'path';

describe('MCPClient stdio protocol with an SDK server', () => {
  it.each(['handshake', 'result', 'concurrent', 'large', 'error', 'environment', 'startup-close'])('supports %s across a real child process', scenario => {
    // Isolate legacy uncaught JSON parsing errors and supervise stuck handshakes.
    const result = spawnSync(process.execPath, [
      '-r', 'ts-node/register/transpile-only', resolve(__dirname, '../fixtures/mcp/stdio-client-check.cjs'), scenario,
    ], { timeout: 20000, encoding: 'utf-8' });
    expect(result.error).toBeUndefined();
    expect({ status: result.status, stderr: result.stderr.slice(-1500) }).toEqual({ status: 0, stderr: '' });
  }, 25000);
});
