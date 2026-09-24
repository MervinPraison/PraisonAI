/**
 * Regression guard: managed agent events must be exported from the package
 * root (Python parity with praisonaiagents top-level exports).
 *
 * Enums (ManagedEventType, ManagedStopReason) must survive at runtime — they
 * are values, not just types, so a `export type` re-export would erase them.
 */

import * as fs from 'fs';
import * as path from 'path';

import * as root from '../../../src/index';

describe('managed events package-root exports (Python parity)', () => {
  it('exports ToolUseEvent as a usable class', () => {
    expect(typeof (root as any).ToolUseEvent).toBe('function');
    const e = new (root as any).ToolUseEvent({ name: 'bash' });
    expect(e.type).toBe('agent.tool_use');
    expect(e.name).toBe('bash');
  });

  it('exports the managed event classes', () => {
    for (const name of [
      'ManagedEvent',
      'AgentMessageEvent',
      'ToolUseEvent',
      'CustomToolUseEvent',
      'ToolConfirmationEvent',
      'SessionIdleEvent',
      'SessionRunningEvent',
      'SessionErrorEvent',
      'UsageEvent',
      'isManagedBackend',
    ]) {
      expect(typeof (root as any)[name]).toBe('function');
    }
  });

  it('exports the managed enums as runtime values', () => {
    expect((root as any).ManagedEventType.AGENT_TOOL_USE).toBe('agent.tool_use');
    expect((root as any).ManagedStopReason.END_TURN).toBe('end_turn');
  });

  const distCjs = path.resolve(__dirname, '../../../dist/index.js');
  const describeBuilt = fs.existsSync(distCjs) ? describe : describe.skip;

  describeBuilt('compiled CommonJS entrypoint (published surface)', () => {
    const built = require(distCjs);

    it('exports ToolUseEvent as a usable class', () => {
      expect(typeof built.ToolUseEvent).toBe('function');
      const e = new built.ToolUseEvent({ name: 'bash' });
      expect(e.type).toBe('agent.tool_use');
    });

    it('exports the managed enums as runtime values', () => {
      expect(built.ManagedEventType.AGENT_TOOL_USE).toBe('agent.tool_use');
      expect(built.ManagedStopReason.END_TURN).toBe('end_turn');
    });
  });
});
