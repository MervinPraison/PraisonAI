/**
 * Parity tests for src/approval/backends.ts against praisonaiagents/approval/backends.py.
 */

import { describe, it, expect } from '@jest/globals';
import { Writable } from 'stream';
import {
  AutoApproveBackend,
  ConsoleBackend,
  CallbackBackend,
  AgentApproval,
  approvalRequest,
  approvalDecision,
  buildPermissionTarget,
  derivePattern,
  suggestScopePattern,
  setApprovalBackend,
  getApprovalBackend,
  approvalHandlerFromBackend,
  toApprovalBackendRequest,
  type ApprovalBackendRequest,
} from '../../../src/approval/backends';
import { ApprovalManager } from '../../../src/ai/tool-approval';

function request(overrides: Partial<ApprovalBackendRequest> = {}): ApprovalBackendRequest {
  return approvalRequest({
    toolName: 'execute_command',
    arguments: { command: 'git status -s' },
    riskLevel: 'high',
    agentName: 'worker',
    ...overrides,
  });
}

/** A ConsoleBackend whose answers are scripted and whose output is captured. */
function scriptedConsole(answers: string[]) {
  const out: string[] = [];
  const output = new Writable({
    write(chunk, _enc, cb) {
      out.push(String(chunk));
      cb();
    },
  });
  const questions: string[] = [];
  const backend = new ConsoleBackend({
    output,
    colors: false,
    reader: async (q) => {
      questions.push(q);
      return answers.shift() ?? '';
    },
    syncReader: (q) => {
      questions.push(q);
      return answers.shift() ?? '';
    },
  });
  return { backend, out, questions };
}

describe('approvalRequest / approvalDecision factories', () => {
  it('apply the Python dataclass defaults', () => {
    const req = approvalRequest({ toolName: 't', arguments: {}, riskLevel: 'low' });
    expect(req.agentName).toBeNull();
    expect(req.sessionId).toBeNull();
    expect(req.context).toEqual({});
    expect(req.approvalId).toMatch(/^[0-9a-f]{32}$/);
    expect(req.authorizedReviewers).toBeNull();
    expect(req.liveness).toBeNull();

    const d = approvalDecision({ approved: true });
    expect(d).toEqual({
      approved: true,
      reason: '',
      modifiedArgs: {},
      approver: null,
      metadata: {},
      scope: 'once',
      scopePattern: null,
      feedback: null,
    });
  });
});

describe('AutoApproveBackend', () => {
  it('approves everything, async and sync, as "system"', async () => {
    const backend = new AutoApproveBackend();
    for (const risk of ['low', 'medium', 'high', 'critical']) {
      const req = request({ riskLevel: risk, toolName: 'delete_file', arguments: { path: '/' } });
      const asyncDecision = await backend.requestApproval(req);
      const syncDecision = backend.requestApprovalSync(req);
      for (const d of [asyncDecision, syncDecision]) {
        expect(d.approved).toBe(true);
        expect(d.reason).toBe('auto-approved');
        expect(d.approver).toBe('system');
        expect(d.scope).toBe('once');
      }
    }
  });
});

describe('ConsoleBackend', () => {
  it('approves once on "y" (and "o"), with the Python reason and approver', async () => {
    const { backend, out, questions } = scriptedConsole(['y']);
    const decision = await backend.requestApproval(request());
    expect(decision.approved).toBe(true);
    expect(decision.reason).toBe('User approved (once)');
    expect(decision.approver).toBe('console');
    expect(decision.scope).toBe('once');
    expect(decision.scopePattern).toBeNull();
    const rendered = out.join('');
    expect(rendered).toContain('Tool Approval Required');
    expect(rendered).toContain('Function: execute_command');
    expect(rendered).toContain('Risk Level: HIGH');
    expect(rendered).toContain('Agent: worker');
    expect(rendered).toContain('command: git status -s');
    expect(questions[0]).toContain('[a] always (bash:git status *)');

    const once = scriptedConsole(['o']);
    expect((await once.backend.requestApproval(request())).scope).toBe('once');
  });

  it('denies on "n", on an empty answer (Python default) and on an unknown answer', async () => {
    for (const answer of ['n', '', 'zzz']) {
      const { backend } = scriptedConsole([answer]);
      const decision = await backend.requestApproval(request());
      expect(decision.approved).toBe(false);
      expect(decision.reason).toBe('User denied');
      expect(decision.approver).toBe('console');
      expect(decision.feedback).toBeNull();
    }
  });

  it('"s" approves for the session and "a" for always with the suggested pattern', async () => {
    const session = await scriptedConsole(['s']).backend.requestApproval(request());
    expect(session.approved).toBe(true);
    expect(session.scope).toBe('session');
    expect(session.reason).toBe('User approved (session)');

    const always = await scriptedConsole(['a']).backend.requestApproval(request());
    expect(always.approved).toBe(true);
    expect(always.scope).toBe('always');
    expect(always.scopePattern).toBe('bash:git status *');
  });

  it('"d" denies and captures redirect feedback', async () => {
    const { backend, questions } = scriptedConsole(['d', 'use ls instead']);
    const decision = await backend.requestApproval(request());
    expect(decision.approved).toBe(false);
    expect(decision.feedback).toBe('use ls instead');
    expect(decision.reason).toBe('User denied: use ls instead');
    expect(questions[1]).toContain('What should the agent do instead?');

    const empty = await scriptedConsole(['d', '  ']).backend.requestApproval(request());
    expect(empty.feedback).toBeNull();
    expect(empty.reason).toBe('User denied');
  });

  it('requestApprovalSync uses the injected sync reader', () => {
    const { backend } = scriptedConsole(['y']);
    expect(backend.requestApprovalSync(request()).approved).toBe(true);
    const deny = scriptedConsole(['n']);
    expect(deny.backend.requestApprovalSync(request()).approved).toBe(false);
  });

  it('a reader failure (EOF / interrupt) becomes a denial, never an approval', async () => {
    const backend = new ConsoleBackend({
      output: new Writable({ write: (_c, _e, cb) => cb() }),
      colors: false,
      reader: async () => {
        throw new Error('EOF');
      },
    });
    const decision = await backend.requestApproval(request());
    expect(decision.approved).toBe(false);
  });

  it('shows the diff instead of arguments when context.diff is present, bounded to maxLines', async () => {
    const diff = ['--- a', '+++ b', '@@ -1 +1 @@', '-old', '+new', ' ctx'].join('\n');
    const { backend, out } = scriptedConsole(['n']);
    await backend.requestApproval(request({ context: { diff } }));
    const rendered = out.join('');
    expect(rendered).toContain('Diff:');
    expect(rendered).toContain('+new');
    expect(rendered).not.toContain('Arguments:');

    const long = Array.from({ length: 50 }, (_, i) => `+line${i}`).join('\n');
    const markup = ConsoleBackend.renderDiffMarkup(long, 40, false);
    expect(markup).toContain('... (diff truncated)');
    expect(markup).not.toContain('line45');
    expect(ConsoleBackend.renderDiffMarkup('+a', 40, true)).toContain('\x1b[32m+a\x1b[0m');
  });

  it('truncates long argument values to 97 chars + "..." like Python', async () => {
    const { backend, out } = scriptedConsole(['n']);
    await backend.requestApproval(request({ arguments: { command: 'x'.repeat(150) } }));
    expect(out.join('')).toContain(`command: ${'x'.repeat(97)}...`);
    expect(out.join('')).not.toContain('x'.repeat(98));
  });
});

describe('permission target / reusable pattern (Python approval/utils.py, permissions/arity.py)', () => {
  it('buildPermissionTarget mirrors the Python mapping', () => {
    expect(buildPermissionTarget('execute_command', { command: 'git status -s' })).toBe('bash:git status -s');
    expect(buildPermissionTarget('execute_command', {})).toBe('tool:execute_command');
    expect(buildPermissionTarget('edit_file', { file_path: 'src/app.py' })).toBe('edit:src/app.py');
    expect(buildPermissionTarget('move_file', { src: 'a', dst: 'b' })).toBe('move:a');
    expect(buildPermissionTarget('apply_patch', { patch: '...' })).toBe('tool:apply_patch');
    expect(buildPermissionTarget('search_web')).toBe('tool:search_web');
  });

  it('derivePattern follows the Python docstring examples', () => {
    expect(derivePattern('bash:git status')).toBe('bash:git status *');
    expect(derivePattern('bash:npm run build')).toBe('bash:npm run *');
    expect(derivePattern('bash:git')).toBe('bash:git');
    expect(derivePattern('bash:cd /tmp && rm x')).toBe('bash:cd /tmp && rm x');
    expect(derivePattern('read:/etc/hosts')).toBe('read:/etc/hosts');
    expect(derivePattern('bash:ls -la')).toBe('bash:ls *');
    expect(derivePattern('bash:git *')).toBe('bash:git *');
    expect(derivePattern('bash:docker compose up -d')).toBe('bash:docker compose *');
    expect(derivePattern('bash:pytest tests/')).toBe('bash:pytest *');
    expect(derivePattern('shell:')).toBe('shell:');
  });

  it('suggestScopePattern composes the two', () => {
    expect(suggestScopePattern(request())).toBe('bash:git status *');
    expect(suggestScopePattern(request({ toolName: 'search_web', arguments: {} }))).toBe('tool:search_web');
  });
});

describe('CallbackBackend', () => {
  it('coerces decisions, booleans and truthy values; async callbacks via requestApproval', async () => {
    const decision = new CallbackBackend(() => approvalDecision({ approved: true, reason: 'cb' }));
    expect(decision.requestApprovalSync(request()).reason).toBe('cb');
    const bool = new CallbackBackend((name) => name === 'execute_command');
    expect(bool.requestApprovalSync(request()).approved).toBe(true);
    expect(bool.requestApprovalSync(request({ toolName: 'other' })).approved).toBe(false);
    const truthy = new CallbackBackend(() => 'yes');
    expect(truthy.requestApprovalSync(request()).approved).toBe(true);
    const asyncCb = new CallbackBackend(async () => false);
    expect((await asyncCb.requestApproval(request())).approved).toBe(false);
    expect(() => asyncCb.requestApprovalSync(request())).toThrow('use requestApproval()');
  });

  it('keeps a partial denial ({ approved: false }, no reason) a denial', async () => {
    // Regression: a non-empty object is truthy, so Boolean(result) once flipped
    // an explicit denial into an approval.
    const denyNoReason = new CallbackBackend(() => ({ approved: false }));
    expect(denyNoReason.requestApprovalSync(request()).approved).toBe(false);
    expect((await denyNoReason.requestApproval(request())).approved).toBe(false);

    const approveNoReason = new CallbackBackend(() => ({ approved: true }));
    expect(approveNoReason.requestApprovalSync(request()).approved).toBe(true);
  });
});

describe('AgentApproval', () => {
  it('approves on APPROVE, denies on DENY or mixed answers, prefers achat over chat', async () => {
    const approver = { name: 'reviewer', achat: async () => 'APPROVE', chat: () => 'DENY' };
    const backend = new AgentApproval(approver);
    const yes = await backend.requestApproval(request());
    expect(yes.approved).toBe(true);
    expect(yes.approver).toBe('reviewer');
    expect(yes.reason).toBe('Agent approved: APPROVE');
    expect(yes.metadata).toEqual({ platform: 'agent', response: 'APPROVE' });

    const mixed = new AgentApproval({ chat: () => 'I would APPROVE but must DENY' });
    expect((await mixed.requestApproval(request())).approved).toBe(false);

    const noChat = new AgentApproval({} as never);
    expect((await noChat.requestApproval(request())).reason).toBe('Approver agent has no chat method');
    expect(String(backend)).toBe('AgentApproval(approver="reviewer")');
    expect(String(new AgentApproval())).toBe('AgentApproval(approver="default")');
  });

  it('requestApprovalSync fails closed with a reason (no blocking event loop)', () => {
    const d = new AgentApproval({ chat: () => 'APPROVE' }).requestApprovalSync(request());
    expect(d.approved).toBe(false);
    expect(d.reason).toContain('requestApproval()');
  });

  it('a throwing approver becomes a denial with the Python reason prefix', async () => {
    const boom = new AgentApproval({
      chat: () => {
        throw new Error('llm down');
      },
    });
    const d = await boom.requestApproval(request());
    expect(d.approved).toBe(false);
    expect(d.reason).toBe('Agent approval error: llm down');
  });
});

describe('ApprovalManager integration', () => {
  it('setApprovalBackend routes ApprovalManager requests through the backend and can be swapped', async () => {
    const manager = new ApprovalManager();
    expect(getApprovalBackend(manager)).toBeNull();

    setApprovalBackend(new AutoApproveBackend(), manager);
    expect(getApprovalBackend(manager)).toBeInstanceOf(AutoApproveBackend);
    expect(await manager.requestApproval({ toolName: 'rm', input: { path: '/' } })).toBe(true);

    const seen: ApprovalBackendRequest[] = [];
    setApprovalBackend(
      {
        async requestApproval(req) {
          seen.push(req);
          return approvalDecision({ approved: false, reason: 'no' });
        },
        requestApprovalSync: () => approvalDecision({ approved: false }),
      },
      manager,
      { riskLevel: 'critical', agentName: 'bot' },
    );
    expect(await manager.requestApproval({ toolName: 'rm', input: { path: '/' }, reason: 'why' })).toBe(false);
    expect(seen).toHaveLength(1);
    expect(seen[0].toolName).toBe('rm');
    expect(seen[0].arguments).toEqual({ path: '/' });
    expect(seen[0].riskLevel).toBe('critical');
    expect(seen[0].agentName).toBe('bot');
    expect(seen[0].context?.reason).toBe('why');

    setApprovalBackend(null, manager);
    expect(getApprovalBackend(manager)).toBeNull();
    expect(await manager.requestApproval({ toolName: 'rm', input: {} })).toBe(false);
  });

  it('approvalHandlerFromBackend and toApprovalBackendRequest wrap non-object input', async () => {
    const handler = approvalHandlerFromBackend(new AutoApproveBackend());
    expect(await handler({ requestId: 'r', toolInvocationId: 'i', toolName: 't', input: 'raw', timestamp: 1 })).toBe(true);
    const converted = toApprovalBackendRequest({ requestId: 'r', toolInvocationId: 'i', toolName: 't', input: 'raw', timestamp: 1 });
    expect(converted.arguments).toEqual({ input: 'raw' });
    expect(converted.riskLevel).toBe('medium');
  });
});
