/**
 * Regression tests for src/agent/features/autonomy.ts security fixes:
 * - AUTO_EDIT_TOOL_PATTERN must not auto-approve unrelated tools via an open suffix.
 * - DoomLoopTracker.actionKey must keep nested arguments distinct.
 */

import { describe, it, expect } from '@jest/globals';
import {
  AUTO_EDIT_TOOL_PATTERN,
  isAutoApprovedByLevel,
  DoomLoopTracker,
} from '../../../src/agent/features/autonomy';

describe('AUTO_EDIT_TOOL_PATTERN', () => {
  it('auto-approves reads and file edits', () => {
    for (const name of ['read', 'edit', 'write', 'read_file', 'write_text', 'multi_edit', 'str_replace']) {
      expect(AUTO_EDIT_TOOL_PATTERN.test(name)).toBe(true);
    }
  });

  it('does not auto-approve unrelated tools sharing a verb prefix', () => {
    for (const name of ['write_to_s3', 'update_iam_policy', 'get_secret', 'read_credentials', 'delete_bucket']) {
      expect(AUTO_EDIT_TOOL_PATTERN.test(name)).toBe(false);
      expect(isAutoApprovedByLevel('auto_edit', name)).toBe(false);
    }
  });
});

describe('DoomLoopTracker.actionKey', () => {
  it('distinguishes calls that differ only in a nested argument', () => {
    const a = DoomLoopTracker.actionKey('run', { path: '/x', opts: { recursive: true } });
    const b = DoomLoopTracker.actionKey('run', { path: '/x', opts: { recursive: false } });
    expect(a).not.toBe(b);
  });

  it('is stable regardless of key order', () => {
    const a = DoomLoopTracker.actionKey('run', { a: 1, b: { c: 2, d: 3 } });
    const b = DoomLoopTracker.actionKey('run', { b: { d: 3, c: 2 }, a: 1 });
    expect(a).toBe(b);
  });
});
