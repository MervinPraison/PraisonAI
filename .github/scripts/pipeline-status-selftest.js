#!/usr/bin/env node
/**
 * Run: node .github/scripts/pipeline-status-selftest.js
 */
const ps = require('./pipeline-status.js');
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

const kickComments = [
  { user: { login: 'MervinPraison' }, body: '@coderabbitai review' },
  { user: { login: 'MervinPraison' }, body: '/review' },
];

const finalComment = {
  user: { login: 'MervinPraison' },
  body: '@claude You are the FINAL architecture reviewer.',
  created_at: '2026-06-26T10:00:00Z',
};

assert(
  'reviews pending when not kicked',
  ps.deriveStage([], { ready: false, reasons: ['no FINAL Claude review trigger'] })
    === 'pipeline/reviews-pending'
);
assert(
  'final pending after kick',
  ps.deriveStage(kickComments, { ready: false, reasons: ['no FINAL Claude review trigger'] })
    === 'pipeline/final-claude-pending'
);
assert(
  'awaiting merge gate after final',
  ps.deriveStage(
    [...kickComments, finalComment],
    { ready: false, reasons: ['recent @claude within 35min'] }
  ) === 'pipeline/awaiting-merge-gate'
);
assert(
  'merge ready',
  ps.deriveStage([...kickComments, finalComment], { ready: true, reasons: [] })
    === 'pipeline/merge-ready'
);

const blockers = ps.deriveBlockerLabels({
  ready: false,
  reasons: ['CI not green on HEAD', 'SDK code added without test file changes — requires manual review'],
});
assert('maps ci blocker', blockers.includes('pipeline/blocked:ci'));
assert('maps manual blocker', blockers.includes('pipeline/blocked:manual-review'));
assert(
  'maps vendor tool to wrong-repo blocker',
  ps.deriveBlockerLabels({
    ready: false,
    reasons: ['new vendor tool module in core (src/.../fxmacrodata_tools.py) — belongs in PraisonAI-Tools'],
  }).includes('pipeline/blocked:wrong-repo')
);
assert(
  'maps wrong FINAL vendor approval to wrong-repo',
  ps.deriveBlockerLabels({
    ready: false,
    reasons: ['FINAL approved vendor tool in core (wrong verdict) — re-trigger FINAL'],
  }).includes('pipeline/blocked:wrong-repo')
);
assert(
  'core vendor tag when added *_tools.py',
  mg.shouldTagCoreVendorToolMisroute(
    [{ status: 'added', filename: 'src/praisonai-agents/praisonaiagents/tools/fxmacrodata_tools.py' }],
    []
  )
);

assert(
  'internal link matches upstream base',
  mg.isInternalPullRequestLink(
    { base: { repo: { full_name: 'MervinPraison/PraisonAI' } } },
    'MervinPraison',
    'PraisonAI'
  )
);
assert(
  'fork sync link rejected',
  !mg.isInternalPullRequestLink(
    { number: 21, base: { repo: { full_name: 'Milkmange/PraisonAI' } } },
    'MervinPraison',
    'PraisonAI'
  )
);

assert(
  'external example only path',
  mg.isExternalExampleOnlyChange([{ filename: 'examples/tools/external/arxiv/tool.py' }])
);
assert(
  'mixed paths not external-example only',
  !mg.isExternalExampleOnlyChange([
    { filename: 'examples/tools/external/foo.py' },
    { filename: 'src/praisonai-agents/foo.py' },
  ])
);

assert(
  'upstream head repo',
  ps.isUpstreamHeadRepo(
    { head: { repo: { full_name: 'MervinPraison/PraisonAI' } } },
    'MervinPraison',
    'PraisonAI'
  )
);
assert(
  'fork head repo still synced (not upstream)',
  !ps.isUpstreamHeadRepo(
    { head: { repo: { full_name: 'ai-mrscraper/PraisonAI' } } },
    'MervinPraison',
    'PraisonAI'
  )
);

process.exit(failed ? 1 : 0);
