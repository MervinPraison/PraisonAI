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

function makeGithub(prs) {
  let listArgs = null;
  return {
    get __listArgs() { return listArgs; },
    paginate: async (fn, args) => (await fn(args)).data,
    rest: {
      issues: {
        listLabelsForRepo: async () => ({ data: [] }),
        createLabel: async () => ({}),
      },
      pulls: {
        list: async (args) => {
          listArgs = args;
          const sorted = [...prs].sort((a, b) =>
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          );
          return { data: args.direction === 'asc' ? sorted : [...sorted].reverse() };
        },
      },
    },
  };
}

function makeSyncFn(readyByNumber) {
  const seen = [];
  const fn = async (github, owner, repo, prNumber) => {
    seen.push(prNumber);
    return { synced: true, ready: readyByNumber.has(prNumber), createdAt: prNumber, labels: [] };
  };
  fn.seen = seen;
  return fn;
}

async function testSyncLoop() {
  const prs = [
    { number: 1, draft: false, created_at: '2026-01-01T00:00:00Z', head: { repo: { full_name: 'MervinPraison/PraisonAI' } } },
    { number: 2, draft: true, created_at: '2026-01-02T00:00:00Z', head: { repo: { full_name: 'MervinPraison/PraisonAI' } } },
    { number: 3, draft: false, created_at: '2026-01-03T00:00:00Z', head: { repo: { full_name: 'forkuser/PraisonAI' } } },
    { number: 4, draft: false, created_at: '2026-01-04T00:00:00Z', head: { repo: { full_name: 'MervinPraison/PraisonAI' } } },
  ];
  const github = makeGithub(prs);
  const syncFn = makeSyncFn(new Set());

  const synced = await ps.syncOpenPullRequests(
    github, 'MervinPraison', 'PraisonAI', { maxPrs: 30, dispatchMergeGate: false, syncFn }, null
  );

  assert('sync loop requests oldest-first ordering', github.__listArgs && github.__listArgs.direction === 'asc');
  assert('sync loop skips drafts', !syncFn.seen.includes(2));
  assert('sync loop labels fork PR', syncFn.seen.includes(3));
  assert('sync loop labels upstream PRs', syncFn.seen.includes(1) && syncFn.seen.includes(4));
  assert('sync loop returns count of non-draft PRs', synced === 3);
}

async function testForkDispatchExclusion() {
  const prs = [
    { number: 1, draft: false, created_at: '2026-01-01T00:00:00Z', head: { repo: { full_name: 'MervinPraison/PraisonAI' } } },
    { number: 3, draft: false, created_at: '2026-01-03T00:00:00Z', head: { repo: { full_name: 'forkuser/PraisonAI' } } },
  ];
  const github = makeGithub(prs);
  const syncFn = makeSyncFn(new Set([1, 3]));
  let candidates = null;
  const dispatchFn = async (g, o, r, cands) => { candidates = cands; return cands[0]?.prNumber || 0; };

  await ps.syncOpenPullRequests(
    github, 'MervinPraison', 'PraisonAI', { maxPrs: 30, dispatchMergeGate: true, syncFn, dispatchFn }, null
  );

  const numbers = (candidates || []).map((c) => c.prNumber);
  assert('dispatch candidates exclude fork head PRs even when ready', !numbers.includes(3));
  assert('dispatch candidates include ready upstream head PR', numbers.includes(1));
}

async function testSyncBudgetEligibility() {
  const prs = [];
  for (let i = 1; i <= 5; i++) {
    prs.push({
      number: i,
      draft: false,
      created_at: `2026-01-0${i}T00:00:00Z`,
      head: { repo: { full_name: i === 1 ? 'MervinPraison/PraisonAI' : 'forkuser/PraisonAI' } },
    });
  }
  const github = makeGithub(prs);
  const syncFn = makeSyncFn(new Set());

  const synced = await ps.syncOpenPullRequests(
    github, 'MervinPraison', 'PraisonAI', { maxPrs: 2, dispatchMergeGate: false, syncFn }, null
  );

  assert('budget respects maxPrs limit', synced === 2);
  assert('oldest upstream PR reached first within budget (not starved by forks)', syncFn.seen[0] === 1);
}

(async () => {
  await testSyncLoop();
  await testForkDispatchExclusion();
  await testSyncBudgetEligibility();
  process.exit(failed ? 1 : 0);
})();
