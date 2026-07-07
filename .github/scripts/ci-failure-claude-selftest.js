#!/usr/bin/env node
/**
 * Run: node .github/scripts/ci-failure-claude-selftest.js
 */
const ciFix = require('./ci-failure-claude.js');
const mergeGate = require('./merge-gate.js');

let failed = 0;
function assert(name, cond) {
  if (!cond) {
    console.error('FAIL:', name);
    failed += 1;
  } else {
    console.log('ok:', name);
  }
}

const LOG_2767 = `
test-core (cli)	UNKNOWN STEP	2026-07-07T17:21:49.8096670Z FAILED (0.0100s) tests/unit/cli/test_typer_cli.py::TestConfigCommand::test_config_list - ValueError: I/O operation on closed file.
test-core (cli)	UNKNOWN STEP	2026-07-07T17:21:49.8097323Z ============= 1 failed, 1401 passed, 1 skipped in 88.86s (0:01:28) =============
test-core (cli)	UNKNOWN STEP	2026-07-07T17:21:49.8693341Z ##[error]Process completed with exit code 1.
`;

const parsed = ciFix.parsePytestFailures(LOG_2767);
assert('parses pytest failure from log', parsed.length === 1);
assert(
  'extracts test path',
  parsed[0]?.testId === 'tests/unit/cli/test_typer_cli.py::TestConfigCommand::test_config_list'
);
assert(
  'extracts error message',
  parsed[0]?.error.includes('ValueError: I/O operation on closed file')
);

const comment = ciFix.buildCiFixComment({
  headSha: 'dfb81bb0ae7f36bf8d66d8f45053464c18c005a3',
  failedChecks: [
    {
      name: 'test-core (cli)',
      workflow: 'Core Tests',
      html_url: 'https://github.com/MervinPraison/PraisonAI/actions/runs/28885180173/job/85683605433',
    },
  ],
  failureSummaries: [{ jobName: 'test-core (cli)', failures: parsed }],
});
assert('comment includes @claude', comment.includes('@claude'));
assert('comment includes short sha', comment.includes('dfb81bb0'));
assert('comment includes test path', comment.includes('test_typer_cli.py::TestConfigCommand::test_config_list'));
assert('comment includes job url', comment.includes('85683605433'));
assert('comment requires critical review verdict', comment.includes('Critical review first'));
assert('comment forbids weakening tests', comment.includes('do not weaken, skip, or delete tests'));
assert('comment mentions SDK guardrails', comment.includes('SDK guardrails'));
assert('comment asks for legitimacy verdict', comment.includes('legitimate fix'));

const headSha = 'dfb81bb0ae7f36bf8d66d8f45053464c18c005a3';
const commentsWithFix = [
  {
    user: { login: 'MervinPraison' },
    body: '@claude CI failed on HEAD `dfb81bb0`. Please fix...',
    created_at: '2026-07-07T18:00:00Z',
  },
];
assert('sha dedup detects existing comment', ciFix.hasCiFixCommentForSha(commentsWithFix, headSha));

const skipNoFinal = ciFix.shouldSkipCiFix({
  comments: [],
  headSha,
  labels: [],
  hasFinal: false,
  claudeInProgress: false,
  failedChecks: [{ name: 'test-core' }],
});
assert('skips when final not posted', skipNoFinal.skip && skipNoFinal.reason.includes('final'));

const skipPending = ciFix.shouldSkipCiFix({
  comments: [],
  headSha,
  labels: [ciFix.CI_FIX_LABEL],
  hasFinal: true,
  claudeInProgress: false,
  failedChecks: [{ name: 'test-core' }],
});
assert('skips when ci fix pending label', skipPending.skip && skipPending.reason.includes('pending'));

const failedRuns = mergeGate.listFailedChecksOnSha([
  { status: 'completed', conclusion: 'success', name: 'smoke' },
  { status: 'completed', conclusion: 'failure', name: 'test-core (cli)' },
  { status: 'in_progress', conclusion: null, name: 'pending-job' },
]);
assert('listFailedChecksOnSha finds failures only', failedRuns.length === 1);
assert('failed check name', failedRuns[0].name === 'test-core (cli)');

const blockedRuns = mergeGate.listFailedChecksOnSha([
  { status: 'completed', conclusion: 'success', name: 'smoke' },
  { status: 'completed', conclusion: 'timed_out', name: 'test-core (llm)' },
  { status: 'completed', conclusion: 'action_required', name: 'test-core (mcp)' },
  { status: 'completed', conclusion: 'cancelled', name: 'real-test' },
  { status: 'completed', conclusion: 'cancelled', name: 'detect-and-trigger' },
  { status: 'completed', conclusion: 'neutral', name: 'informational' },
  { status: 'in_progress', conclusion: null, name: 'pending-job' },
]);
const blockedNames = blockedRuns.map((r) => r.name);
assert('mirrors green logic: timed_out is failed', blockedNames.includes('test-core (llm)'));
assert('mirrors green logic: action_required is failed', blockedNames.includes('test-core (mcp)'));
assert('mirrors green logic: non-optional cancelled is failed', blockedNames.includes('real-test'));
assert('optional cancelled (detect-and-trigger) not failed', !blockedNames.includes('detect-and-trigger'));
assert('neutral not counted as failed', !blockedNames.includes('informational'));
assert('pending not counted as failed', !blockedNames.includes('pending-job'));

process.exit(failed ? 1 : 0);
