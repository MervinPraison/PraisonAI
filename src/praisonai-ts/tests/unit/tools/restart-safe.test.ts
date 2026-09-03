/**
 * restartSafe - Python parity with `tool(restart_safe=...)` and the durable
 * resume gate in praisonaiagents/agent/durable.py `_is_restart_safe`.
 */

import { describe, it, expect, beforeEach, jest } from '@jest/globals';
import {
  tool,
  ToolRegistry,
  ToolNotRestartSafeError,
  isReadOnlyToolName,
} from '../../../src/tools/decorator';
import { resetParityNotices, unhonouredOptions } from '../../../src/utils/parity-notice';

process.env.PRAISONAI_PARITY_SILENT = '1';

describe('restartSafe', () => {
  beforeEach(() => {
    resetParityNotices();
  });

  describe('isRestartSafe', () => {
    it('honours an explicit true / false declaration', () => {
      expect(tool({ name: 'send_email', execute: () => 1, restartSafe: true }).isRestartSafe).toBe(true);
      expect(tool({ name: 'get_weather', execute: () => 1, restartSafe: false }).isRestartSafe).toBe(false);
    });

    it('falls back to the read-only name heuristic when undeclared', () => {
      expect(tool({ name: 'get_weather', execute: () => 1 }).isRestartSafe).toBe(true);
      expect(tool({ name: 'search_docs', execute: () => 1 }).isRestartSafe).toBe(true);
      expect(tool({ name: 'write_file', execute: () => 1 }).isRestartSafe).toBe(false);
      expect(tool({ name: 'run_command', execute: () => 1 }).isRestartSafe).toBe(false);
      expect(tool({ name: 'deploy', execute: () => 1 }).isRestartSafe).toBe(false);
    });

    it('fails closed on a malformed (non-boolean) declaration', () => {
      const t = tool({ name: 'get_weather', execute: () => 1, restartSafe: 'True' as unknown as boolean });
      expect(t.isRestartSafe).toBe(false);
    });

    it('mirrors Python _is_read_only_tool markers', () => {
      expect(isReadOnlyToolName('read_file')).toBe(true);
      expect(isReadOnlyToolName('list_dir')).toBe(true);
      expect(isReadOnlyToolName('')).toBe(true);
      for (const name of ['write', 'edit', 'append', 'delete', 'remove', 'create', 'mkdir', 'rm', 'put', 'post', 'patch',
        'update', 'insert', 'save', 'move', 'rename', 'chmod', 'chown', 'exec', 'run', 'shell', 'bash', 'command',
        'kill', 'apply_patch', 'install', 'deploy']) {
        expect(isReadOnlyToolName(`my_${name}_tool`)).toBe(false);
      }
    });

    it('is not reported as unhonoured', () => {
      tool({ name: 'x', execute: () => 1, restartSafe: false });
      expect(unhonouredOptions()).toEqual([]);
    });
  });

  describe('execute with { resumed: true }', () => {
    it('refuses to re-run a tool declared restartSafe: false', async () => {
      const fn = jest.fn(() => 'sent');
      const t = tool({ name: 'send_email', execute: fn, restartSafe: false });
      await expect(t.execute({}, { resumed: true })).rejects.toBeInstanceOf(ToolNotRestartSafeError);
      await expect(t.execute({}, { resumed: true })).rejects.toThrow(/send_email.*not declared restartSafe.*not re-executed on resume/);
      expect(fn).not.toHaveBeenCalled();
    });

    it('re-runs a tool declared restartSafe: true', async () => {
      const fn = jest.fn(() => 'sent');
      const t = tool({ name: 'send_email', execute: fn, restartSafe: true });
      expect(await t.execute({}, { resumed: true })).toBe('sent');
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('re-runs an undeclared read-only tool but refuses an undeclared effectful one', async () => {
      const read = jest.fn(() => 'data');
      const write = jest.fn(() => 'written');
      expect(await tool({ name: 'read_file', execute: read }).execute({}, { resumed: true })).toBe('data');
      await expect(tool({ name: 'write_file', execute: write }).execute({}, { resumed: true })).rejects.toBeInstanceOf(ToolNotRestartSafeError);
      expect(write).not.toHaveBeenCalled();
    });

    it('control: the same effectful tool runs normally when not resumed', async () => {
      const fn = jest.fn(() => 'sent');
      const t = tool({ name: 'send_email', execute: fn, restartSafe: false });
      expect(await t.execute({})).toBe('sent');
      expect(await t.execute({}, { resumed: false })).toBe('sent');
      expect(await t.executeRaw({}, { runId: 'r1' })).toBe('sent');
      expect(fn).toHaveBeenCalledTimes(3);
    });

    it('exposes the Python NotSafelyResumable fields on the error', async () => {
      const t = tool({ name: 'send_email', execute: () => 1, restartSafe: false });
      const err = await t.execute({}, { resumed: true }).catch(e => e);
      expect(err).toMatchObject({
        name: 'ToolNotRestartSafeError',
        toolName: 'send_email',
        errorType: 'NotSafelyResumable',
        notSafelyResumable: true,
        restartSafe: false,
      });
    });
  });

  describe('ToolRegistry.listRestartSafe', () => {
    it('lists only tools that may be replayed', () => {
      const registry = new ToolRegistry();
      const safe = tool({ name: 'send_email', execute: () => 1, restartSafe: true });
      const unsafe = tool({ name: 'get_weather', execute: () => 1, restartSafe: false });
      const readOnly = tool({ name: 'search', execute: () => 1 });
      const effectful = tool({ name: 'delete_row', execute: () => 1 });
      registry.register(safe).register(unsafe).register(readOnly).register(effectful);
      expect(registry.listRestartSafe().map(t => t.name).sort()).toEqual(['search', 'send_email']);
      // control: list() still returns everything
      expect(registry.list()).toHaveLength(4);
    });
  });
});
