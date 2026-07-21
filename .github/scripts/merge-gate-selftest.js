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

const withClaudeReply = [
  ...finals,
  {
    user: { login: 'praisonai-triage-agent[bot]' },
    body: "**Claude finished @MervinPraison's task** —— [View job](https://github.com/)",
    created_at: '2026-06-12T08:30:00Z',
  },
];
assert('not stale when Claude replied after FINAL', !mg.isStaleFinalAfterPush(withClaudeReply, '2026-06-12T09:00:00Z'));
assert('claude final reply detected', mg.isClaudeFinalReplyComment(withClaudeReply[1]));

assert('cancelled detect-and-trigger does not block', mg.OPTIONAL_CANCELLED_CHECKS.has('detect-and-trigger'));

const coreGreenRuns = [
  { name: 'test-core', status: 'completed', conclusion: 'success' },
  { name: 'test-core (cli)', status: 'completed', conclusion: 'success' },
  { name: 'smoke', status: 'completed', conclusion: 'cancelled' },
  { name: 'test-windows', status: 'completed', conclusion: 'cancelled' },
];
assert('core green allows cancelled smoke', mg.isAcceptableCheckConclusion(
  { name: 'smoke', status: 'completed', conclusion: 'cancelled' },
  coreGreenRuns
));
assert('core green allows cancelled test-windows', mg.isAcceptableCheckConclusion(
  { name: 'test-windows', status: 'completed', conclusion: 'cancelled' },
  coreGreenRuns
));
assert('cancelled smoke blocks when core missing', !mg.isAcceptableCheckConclusion(
  { name: 'smoke', status: 'completed', conclusion: 'cancelled' },
  [{ name: 'smoke', status: 'completed', conclusion: 'cancelled' }]
));
assert('cancelled smoke blocks when core failed', !mg.isAcceptableCheckConclusion(
  { name: 'smoke', status: 'completed', conclusion: 'cancelled' },
  [
    { name: 'test-core', status: 'completed', conclusion: 'failure' },
    { name: 'smoke', status: 'completed', conclusion: 'cancelled' },
  ]
));
assert('bestRunsByName prefers success over cancelled', (() => {
  const best = mg.bestRunsByName([
    { name: 'smoke', conclusion: 'cancelled' },
    { name: 'smoke', conclusion: 'success' },
  ]);
  return best.length === 1 && best[0].conclusion === 'success';
})());
assert('bestRunsByName prefers pending over completed cancelled', (() => {
  const best = mg.bestRunsByName([
    { name: 'smoke', status: 'completed', conclusion: 'cancelled' },
    { name: 'smoke', status: 'in_progress', conclusion: null },
  ]);
  return best.length === 1 && best[0].status === 'in_progress';
})());
assert('bestRunsByName keeps pending regardless of order', (() => {
  const best = mg.bestRunsByName([
    { name: 'smoke', status: 'in_progress', conclusion: null },
    { name: 'smoke', status: 'completed', conclusion: 'success' },
  ]);
  return best.length === 1 && best[0].status === 'in_progress';
})());
assert('allChecksGreenOnSha style: pending re-run blocks despite core green', (() => {
  const runs = mg.bestRunsByName([
    { name: 'test-core', status: 'completed', conclusion: 'success' },
    { name: 'smoke', status: 'completed', conclusion: 'cancelled' },
    { name: 'smoke', status: 'queued', conclusion: null },
  ]);
  const smoke = runs.find((r) => r.name === 'smoke');
  return smoke.status !== 'completed';
})());

// Stale-FINAL recovery guards (PR #2560 push loop)
const nowMs = Date.now();
const iso = (ms) => new Date(ms).toISOString();
const firstFinal = {
  user: { login: 'MervinPraison' },
  body: '@claude You are the FINAL architecture reviewer.',
  created_at: iso(nowMs - 20 * 60 * 1000),
};
const pushSoonAfter = mg.shouldSkipStaleFinalRecovery(
  [firstFinal],
  iso(nowMs - 16 * 60 * 1000)
);
assert('debounce push soon after FINAL', pushSoonAfter.skip && pushSoonAfter.reason.includes('soon after'));

const secondFinal = {
  user: { login: 'MervinPraison' },
  body: '@claude You are the FINAL architecture reviewer.',
  created_at: iso(nowMs - 20 * 60 * 1000),
};
const capped = mg.shouldSkipStaleFinalRecovery(
  [firstFinal, secondFinal],
  iso(nowMs - 2 * 60 * 1000)
);
assert('hourly cap blocks third FINAL in window', capped.skip && capped.reason.includes('capped'));

const botPush = mg.shouldSkipStaleFinalRecovery(
  [firstFinal],
  iso(nowMs - 16 * 60 * 1000),
  'praisonai-triage-agent[bot]'
);
assert('skip when automation pushed head', botPush.skip && botPush.reason.includes('automation'));

assert('claude automation login', mg.isClaudeAutomationLogin('praisonai-triage-agent[bot]'));

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

const fallbackApprove = [
  {
    body: 'MERGE_GATE_VERDICT: APPROVE\n\nAutomated fallback — Claude assess did not post a verdict comment.',
    created_at: '2026-06-12T10:00:00Z',
  },
];
assert(
  'automated fallback APPROVE ignored when Opus required',
  mg.findMergeGateVerdict(fallbackApprove, null, '2026-06-12T09:00:00Z', { excludeAutomatedFallback: true }) === null
);
assert(
  'automated fallback APPROVE still visible without Opus-only filter',
  mg.findMergeGateVerdict(fallbackApprove, null, '2026-06-12T09:00:00Z') === 'APPROVE'
);

const fallbackBlockNewFormat = [
  {
    body: 'MERGE_GATE_VERDICT: BLOCK\n\nAutomated fallback — Opus merge gate assessment did not complete.',
    created_at: '2026-06-12T10:00:00Z',
  },
];
assert(
  'new-format fallback BLOCK ignored when Opus required',
  mg.findMergeGateVerdict(fallbackBlockNewFormat, null, '2026-06-12T09:00:00Z', { excludeAutomatedFallback: true }) === null
);
assert(
  'new-format fallback BLOCK detected by marker helper',
  mg.isAutomatedFallbackVerdict(fallbackBlockNewFormat[0].body)
);
assert(
  'findMergeGateVerdict null-safe with explicit null options',
  mg.findMergeGateVerdict(fallbackApprove, null, '2026-06-12T09:00:00Z', null) === 'APPROVE'
);

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

// Conflict rebase clears after bot completion + FINAL on HEAD (within 12h cooldown)
const conflictNowMs = Date.now();
const conflictIso = (offsetMs) => new Date(conflictNowMs + offsetMs).toISOString();
const conflictTrigger = {
  user: { login: 'MervinPraison' },
  body: '@claude this PR has merge conflicts with main. Please rebase',
  created_at: conflictIso(-30 * 60 * 1000),
};
const rebaseDone = {
  user: { login: 'praisonai-triage-agent[bot]' },
  body: 'Rebase complete — PR #2308 onto latest main',
  created_at: conflictIso(-29 * 60 * 1000),
};
const finalAfterRebase = {
  user: { login: 'MervinPraison' },
  body: '@claude You are the FINAL architecture reviewer.',
  created_at: conflictIso(-20 * 60 * 1000),
};
const headAfterRebase = conflictIso(-21 * 60 * 1000);
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
