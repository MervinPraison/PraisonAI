#!/usr/bin/env node
/**
 * Local self-test for merge-gate.js heuristics (no GitHub API).
 * Run: node .github/scripts/merge-gate-selftest.js
 */
const mg = require('./merge-gate.js');

let failed = 0;
function assert(name, cond) {
  if (!cond) {
    console.error('FAIL:', name);
    failed++;
  } else {
    console.log('ok:', name);
  }
}

// Stale FINAL: push after FINAL, no @claude since head
const finals = [
  { user: { login: 'github-actions[bot]' }, body: '@claude FINAL architecture reviewer', created_at: '2026-06-12T08:00:00Z' },
];
assert('stale when head after final', mg.isStaleFinalAfterPush(finals, '2026-06-12T09:00:00Z'));

const withRecovery = [
  ...finals,
  { user: { login: 'github-actions[bot]' }, body: '@claude FINAL architecture reviewer', created_at: '2026-06-12T09:30:00Z' },
];
assert('not stale when @claude after head', !mg.isStaleFinalAfterPush(withRecovery, '2026-06-12T09:00:00Z'));

// Bot CHANGES_REQUESTED then APPROVE
const reviews = [
  { user: { login: 'coderabbit[bot]', type: 'Bot' }, state: 'CHANGES_REQUESTED', submitted_at: '2026-06-12T08:00:00Z' },
  { user: { login: 'coderabbit[bot]', type: 'Bot' }, state: 'APPROVED', submitted_at: '2026-06-12T09:00:00Z' },
];
assert('bot approve clears CR', !mg.hasAnyChangesRequested(reviews));
assert('human CR blocks', mg.hasAnyChangesRequested([
  { user: { login: 'MervinPraison', type: 'User' }, state: 'CHANGES_REQUESTED', submitted_at: '2026-06-12T09:00:00Z' },
]));

// Verdict after HEAD
const verdictComments = [
  { body: 'MERGE_GATE_VERDICT: APPROVE', created_at: '2026-06-12T08:00:00Z' },
];
assert('verdict before head rejected', mg.findMergeGateVerdict(verdictComments, null, '2026-06-12T09:00:00Z') === null);
assert('verdict after head accepted', mg.findMergeGateVerdict(
  [{ body: 'MERGE_GATE_VERDICT: APPROVE', created_at: '2026-06-12T10:00:00Z' }],
  null,
  '2026-06-12T09:00:00Z'
) === 'APPROVE');

const noise = [{ user: { login: 'MervinPraison' }, body: '**Merge gate scan** — wait for `@claude`', created_at: new Date().toISOString() }];
assert('diagnostic comment not a trigger', !mg.hasRecentClaudeTrigger(noise, 35));

// Cooldown skip requires an actual verdict on HEAD, not just a FINAL trigger comment
const recentFinalOnHead = [
  {
    user: { login: 'MervinPraison' },
    body: '@claude You are the FINAL architecture reviewer.',
    created_at: '2026-06-27T10:00:00Z',
  },
];
assert(
  'final trigger alone does not count as verdict on head',
  mg.findMergeGateVerdict(recentFinalOnHead, null, '2026-06-27T09:55:00Z') === null
);
const recentVerdictOnHead = [
  ...recentFinalOnHead,
  {
    user: { login: 'github-actions[bot]' },
    body: 'MERGE_GATE_VERDICT: APPROVE',
    created_at: '2026-06-27T10:05:00Z',
  },
];
assert(
  'verdict on head skips cooldown gate',
  mg.findMergeGateVerdict(recentVerdictOnHead, null, '2026-06-27T09:55:00Z') === 'APPROVE'
);

// Sensitive + secrets
assert('workflow path sensitive', mg.sensitivePathReasons([{ filename: '.github/workflows/foo.yml' }]).length === 1);
assert('ci-only label exempts workflows', mg.sensitivePathReasons(
  [{ filename: '.github/workflows/foo.yml' }],
  [mg.WORKFLOW_ONLY_LABEL]
).length === 0);
assert('ci-only label not exempt mixed changes', mg.sensitivePathReasons(
  [{ filename: '.github/workflows/foo.yml' }, { filename: 'src/foo.py' }],
  [mg.WORKFLOW_ONLY_LABEL]
).length === 1);
assert('secret in patch', mg.secretScanReasons([{ filename: 'x.py', patch: '+key = "ghp_abcdefghijklmnopqrstuvwxyz1234567890"' }]).length === 1);

// Claude run scoping — other PR branches must not block
assert('other branch claude does not block', !mg.hasBlockingClaudeRunForPr(
  [{ event: 'issue_comment', head_branch: 'other-branch' }],
  'my-branch'
));
assert('same branch claude blocks', mg.hasBlockingClaudeRunForPr(
  [{ event: 'issue_comment', head_branch: 'my-branch' }],
  'my-branch'
));
assert('issues event never blocks', !mg.hasBlockingClaudeRunForPr(
  [{ event: 'issues', head_branch: 'my-branch' }],
  'my-branch'
));

// Conflict rebase clears after bot completion + FINAL on HEAD
const conflictTrigger = {
  user: { login: 'MervinPraison' },
  body: '@claude this PR has merge conflicts with main. Please rebase',
  created_at: '2026-06-26T10:30:38Z',
};
const rebaseDone = {
  user: { login: 'praisonai-triage-agent[bot]' },
  body: 'Rebase complete — PR #2308 onto latest main',
  created_at: '2026-06-26T10:30:55Z',
};
const finalAfterRebase = {
  user: { login: 'MervinPraison' },
  body: '@claude You are the FINAL architecture reviewer.',
  created_at: '2026-06-26T10:39:43Z',
};
const headAfterRebase = '2026-06-26T10:39:25Z';
const rebaseComments = [conflictTrigger, rebaseDone, finalAfterRebase];
assert('conflict blocks before rebase done', mg.hasRecentConflictComment([conflictTrigger], headAfterRebase));
assert('conflict clears after rebase + FINAL on HEAD', !mg.hasRecentConflictComment(rebaseComments, headAfterRebase));
assert('conflict still blocks without FINAL on HEAD', mg.hasRecentConflictComment(
  [conflictTrigger, rebaseDone],
  headAfterRebase
));

// Tests heuristic
assert('sdk without tests', mg.missingTestsReason([{ filename: 'src/praisonai-agents/a/b.py', additions: 3 }]) !== null);
assert('sdk with tests ok', mg.missingTestsReason([
  { filename: 'src/praisonai-agents/a/b.py', additions: 3 },
  { filename: 'src/praisonai-agents/tests/test_x.py', additions: 10 },
]) === null);

// PR size
assert('large PR blocked', mg.prSizeReasons([{ additions: 900 }]).length > 0);

assert('internal PR link accepted', mg.isInternalPullRequestLink(
  { base: { repo: { full_name: 'MervinPraison/PraisonAI' } } },
  'MervinPraison',
  'PraisonAI'
));
assert('fork sync PR link rejected', !mg.isInternalPullRequestLink(
  { number: 21, base: { repo: { full_name: 'Milkmange/PraisonAI' } } },
  'MervinPraison',
  'PraisonAI'
));

process.exit(failed ? 1 : 0);
