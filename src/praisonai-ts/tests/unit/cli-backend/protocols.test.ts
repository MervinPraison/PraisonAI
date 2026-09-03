/**
 * Parity tests for src/cli-backend/protocols.ts against praisonaiagents/cli_backend/protocols.py.
 */

import { describe, it, expect } from '@jest/globals';
import {
  CliBackendConfig,
  CliSessionBinding,
  CliBackendResult,
  CliBackendDelta,
  type CliBackendProtocol,
} from '../../../src/cli-backend/protocols';

describe('CliBackendConfig', () => {
  it('defaults match the Python dataclass', () => {
    const cfg = new CliBackendConfig({ command: 'claude' });
    expect(cfg.command).toBe('claude');
    expect(cfg.args).toEqual([]);
    expect(cfg.resumeArgs).toBeNull();
    expect(cfg.sessionArg).toBeNull();
    expect(cfg.sessionMode).toBe('none');
    expect(cfg.sessionIdFields).toEqual([]);
    expect(cfg.output).toBe('text');
    expect(cfg.input).toBe('arg');
    expect(cfg.maxPromptArgChars).toBeNull();
    expect(cfg.modelArg).toBeNull();
    expect(cfg.modelAliases).toEqual({});
    expect(cfg.systemPromptArg).toBeNull();
    expect(cfg.systemPromptWhen).toBe('always');
    expect(cfg.systemPromptMode).toBe('append');
    expect(cfg.imageArg).toBeNull();
    expect(cfg.imageMode).toBe('repeat');
    expect(cfg.clearEnv).toEqual([]);
    expect(cfg.env).toEqual({});
    expect(cfg.liveSession).toBeNull();
    expect(cfg.bundleMcp).toBe(false);
    expect(cfg.bundleMcpMode).toBeNull();
    expect(cfg.serialize).toBe(false);
    expect(cfg.noOutputTimeoutMs).toBeNull();
    expect(cfg.timeoutMs).toBe(300_000);
  });

  it('requires a command like the Python positional field', () => {
    expect(() => new CliBackendConfig({ command: '' })).toThrow('non-empty command');
  });

  it('projects onto the external-agents.ts ExternalAgentConfig shape', () => {
    const cfg = new CliBackendConfig({ command: 'codex', args: ['-q'], env: { A: '1' }, timeoutMs: 1000 });
    expect(cfg.toExternalAgentConfig()).toEqual({
      name: 'codex',
      command: 'codex',
      args: ['-q'],
      cwd: undefined,
      env: { A: '1' },
      timeout: 1000,
    });
    expect(cfg.toExternalAgentConfig('my-codex', '/tmp').name).toBe('my-codex');
  });
});

describe('CliSessionBinding / CliBackendResult / CliBackendDelta', () => {
  it('CliSessionBinding defaults match Python', () => {
    const b = new CliSessionBinding();
    expect(b.sessionId).toBeNull();
    expect(b.authProfileId).toBeNull();
    expect(b.systemPromptHash).toBeNull();
    expect(b.mcpConfigHash).toBeNull();
    expect(b.isResume).toBe(false);
    expect(new CliSessionBinding({ sessionId: 's', isResume: true }).isResume).toBe(true);
  });

  it('CliBackendResult defaults and bridge from ExternalAgentResult', () => {
    const r = new CliBackendResult({ content: 'hi' });
    expect(r.metadata).toEqual({});
    expect(r.sessionId).toBeNull();
    expect(r.error).toBeNull();

    const ok = CliBackendResult.fromExternalAgentResult({ success: true, output: 'out', exitCode: 0, duration: 12 }, 'sess');
    expect(ok.content).toBe('out');
    expect(ok.error).toBeNull();
    expect(ok.sessionId).toBe('sess');
    expect(ok.metadata).toEqual({ success: true, exit_code: 0, duration_ms: 12 });

    const failed = CliBackendResult.fromExternalAgentResult({ success: false, output: '', exitCode: 2, duration: 1 });
    expect(failed.error).toBe('exit code 2');
    const failedMsg = CliBackendResult.fromExternalAgentResult({ success: false, output: '', error: 'boom', exitCode: 1, duration: 1 });
    expect(failedMsg.error).toBe('boom');
  });

  it('CliBackendDelta defaults and bridge from StreamEvent', () => {
    const d = new CliBackendDelta({ type: 'text' });
    expect(d.content).toBe('');
    expect(d.metadata).toEqual({});
    expect(CliBackendDelta.fromStreamEvent({ type: 'text', content: 'abc' })).toMatchObject({ type: 'text', content: 'abc' });
    const json = CliBackendDelta.fromStreamEvent({ type: 'json', data: { tool: 'x' } });
    expect(json.type).toBe('tool_call');
    expect(json.metadata).toEqual({ data: { tool: 'x' } });
    expect(CliBackendDelta.fromStreamEvent({ type: 'error', error: 'bad' })).toMatchObject({ type: 'error', content: 'bad' });
  });

  it('CliBackendProtocol is satisfiable structurally', async () => {
    const backend: CliBackendProtocol = {
      config: new CliBackendConfig({ command: 'echo' }),
      capabilities: () => ({ basicChat: true }),
      execute: async (prompt) => new CliBackendResult({ content: prompt.toUpperCase() }),
      async *stream(prompt) {
        yield new CliBackendDelta({ type: 'text', content: prompt });
      },
    };
    expect((await backend.execute('hi', { session: new CliSessionBinding() })).content).toBe('HI');
    const deltas = [];
    for await (const d of backend.stream('x')) deltas.push(d.content);
    expect(deltas).toEqual(['x']);
    expect(backend.capabilities().basicChat).toBe(true);
  });
});
