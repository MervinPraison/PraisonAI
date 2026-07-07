/**
 * Sync pipeline stage/blocker labels on open PRs.
 * @see .github/workflows/pipeline-status-sync.yml
 */

const mergeGate = require('./merge-gate.js');
const chain = require('./bot-pr-review-chain.js');
const ciFix = require('./ci-failure-claude.js');

const PIPELINE_PREFIX = 'pipeline/';
const STAGE_LABELS = [
  'pipeline/reviews-pending',
  'pipeline/final-claude-pending',
  'pipeline/awaiting-merge-gate',
  'pipeline/merge-ready',
  'pipeline/merged',
];
const BLOCKER_LABELS = [
  'pipeline/blocked:ci',
  'pipeline/blocked:conflict',
  'pipeline/blocked:manual-review',
  'pipeline/blocked:cooldown',
  'pipeline/blocked:stale-final',
  'pipeline/blocked:no-final',
];
const ALL_PIPELINE_LABELS = [...STAGE_LABELS, ...BLOCKER_LABELS];

const LABEL_SPECS = [
  { name: 'pipeline/reviews-pending', color: 'fbca04', description: 'Waiting for CodeRabbit/Qodo/Copilot reviews' },
  { name: 'pipeline/final-claude-pending', color: 'd4c5f9', description: 'Reviews done; waiting for FINAL @claude' },
  { name: 'pipeline/awaiting-merge-gate', color: 'c5def5', description: 'FINAL done; waiting for merge gate / CI' },
  { name: 'pipeline/merge-ready', color: '0e8a16', description: 'Eligible for merge gate auto-merge' },
  { name: 'pipeline/merged', color: '6f42c1', description: 'Merged via pipeline' },
  { name: 'pipeline/blocked:ci', color: 'd93f0b', description: 'Blocked: CI not green on HEAD' },
  { name: 'pipeline/blocked:conflict', color: 'b60205', description: 'Blocked: merge conflict or rebase pending' },
  { name: 'pipeline/blocked:manual-review', color: 'e99695', description: 'Blocked: requires manual review' },
  { name: 'pipeline/blocked:cooldown', color: 'fef2c0', description: 'Blocked: post-push or @claude cooldown' },
  { name: 'pipeline/blocked:stale-final', color: 'f9d0c4', description: 'Blocked: FINAL stale after new commits' },
  { name: 'pipeline/blocked:no-final', color: 'ededed', description: 'Blocked: no FINAL @claude trigger yet' },
];

function deriveStage(comments, evalResult) {
  if (evalResult.ready) return 'pipeline/merge-ready';
  if (!chain.chainKickPosted(comments)) return 'pipeline/reviews-pending';
  if (!mergeGate.hasFinalClaudeReviewTrigger(comments)) return 'pipeline/final-claude-pending';
  return 'pipeline/awaiting-merge-gate';
}

function reasonToBlockerLabel(reason) {
  const r = (reason || '').toLowerCase();
  if (r.includes('ci not green') || r.includes('sdk code changed but no ci')) return 'pipeline/blocked:ci';
  if (
    r.includes('conflict') ||
    r.includes('mergestate=dirty') ||
    r.includes('not mergeable')
  ) return 'pipeline/blocked:conflict';
  if (
    r.includes('manual') ||
    r.includes('requires manual') ||
    r.includes('sensitive path') ||
    r.includes('no-auto-merge') ||
    r.includes('manual-only label') ||
    r.includes('without test') ||
    r.includes('files changed') ||
    r.includes('possible secret') ||
    r.includes('agent.py')
  ) return 'pipeline/blocked:manual-review';
  if (r.includes('recent @claude') || r.includes('post-push buffer')) return 'pipeline/blocked:cooldown';
  if (r.includes('stale final')) return 'pipeline/blocked:stale-final';
  if (r.includes('no final claude')) return 'pipeline/blocked:no-final';
  if (r.includes('final claude not complete')) return 'pipeline/blocked:stale-final';
  if (r.includes('claude.yml in progress') || r.includes('claude-merge-gate-active')) {
    return null;
  }
  return null;
}

function deriveBlockerLabels(evalResult) {
  if (evalResult.ready) return [];
  const labels = new Set();
  for (const reason of evalResult.reasons || []) {
    const mapped = reasonToBlockerLabel(reason);
    if (mapped && mapped.startsWith('pipeline/blocked:')) labels.add(mapped);
  }
  return [...labels];
}

function computePipelineLabels(comments, evalResult) {
  const stage = deriveStage(comments, evalResult);
  const blockers = stage === 'pipeline/merge-ready' ? [] : deriveBlockerLabels(evalResult);
  return { stage, blockers, all: [stage, ...blockers] };
}

async function ensurePipelineLabels(github, owner, repo, core) {
  let existing;
  if (typeof github.paginate === 'function') {
    existing = await github.paginate(github.rest.issues.listLabelsForRepo, {
      owner,
      repo,
      per_page: 100,
    });
  } else {
    ({ data: existing } = await github.rest.issues.listLabelsForRepo({
      owner,
      repo,
      per_page: 100,
    }));
  }
  const names = new Set(existing.map((l) => l.name));
  for (const spec of LABEL_SPECS) {
    if (names.has(spec.name)) continue;
    try {
      await github.rest.issues.createLabel({
        owner,
        repo,
        name: spec.name,
        color: spec.color,
        description: spec.description,
      });
      core?.info?.(`Created label ${spec.name}`);
    } catch (err) {
      if (err.status !== 422) throw err;
      core?.info?.(`Label ${spec.name} already exists`);
    }
  }
}

async function syncPipelineLabels(github, owner, repo, prNumber, core) {
  const ctx = await mergeGate.loadPrContext(github, owner, repo, prNumber);
  if (ctx.pr.state !== 'open') return { synced: false, reason: 'not_open' };

  const evalResult = await mergeGate.evaluatePipelineQuiescent(
    github, owner, repo, prNumber, core
  );
  const { stage, blockers, all } = computePipelineLabels(ctx.comments, evalResult);

  const current = ctx.labels.filter((l) => l.startsWith(PIPELINE_PREFIX));
  const desired = new Set(all);
  const toRemove = current.filter((l) => !desired.has(l) && l !== 'pipeline/merged');
  const toAdd = all.filter((l) => !current.includes(l));

  for (const name of toRemove) {
    try {
      await github.rest.issues.removeLabel({ owner, repo, issue_number: prNumber, name });
    } catch (err) {
      if (err.status !== 404) throw err;
    }
  }
  if (toAdd.length) {
    await github.rest.issues.addLabels({
      owner,
      repo,
      issue_number: prNumber,
      labels: toAdd,
    });
  }

  core?.info?.(`PR #${prNumber}: stage=${stage} blockers=[${blockers.join(', ')}]`);

  const ciNotGreen = (evalResult.reasons || []).some((r) =>
    r.toLowerCase().includes('ci not green')
  );
  if (ciNotGreen || blockers.includes('pipeline/blocked:ci')) {
    await ciFix.maybeTriggerCiFixClaude(github, owner, repo, prNumber, core);
  } else {
    await ciFix.maybeClearCiFixLabel(
      github, owner, repo, prNumber, ctx.labels, ctx.headSha, core
    );
  }

  return {
    synced: true,
    stage,
    blockers,
    ready: evalResult.ready,
    reasons: evalResult.reasons,
    labels: ctx.labels,
    createdAt: new Date(ctx.pr.created_at).getTime(),
  };
}

async function dispatchMergeGateForOldestReady(github, owner, repo, readyCandidates, core) {
  if (!readyCandidates.length) return 0;
  readyCandidates.sort((a, b) => a.createdAt - b.createdAt);
  for (const cand of readyCandidates) {
    if ((cand.labels || []).includes('claude-merge-gate-active')) {
      core?.info?.(`Skip dispatch PR #${cand.prNumber}: merge gate already active`);
      continue;
    }
    await github.rest.repos.createDispatchEvent({
      owner,
      repo,
      event_type: 'claude-merge-gate',
      client_payload: { pr_number: cand.prNumber },
    });
    core?.info?.(`Dispatched merge gate for ready PR #${cand.prNumber}`);
    return cand.prNumber;
  }
  return 0;
}

async function syncOpenPullRequests(github, owner, repo, options, core) {
  const { maxPrs = 20, dispatchMergeGate = true } = options || {};
  await ensurePipelineLabels(github, owner, repo, core);
  let prs;
  if (maxPrs <= 100) {
    ({ data: prs } = await github.rest.pulls.list({
      owner,
      repo,
      state: 'open',
      per_page: 100,
    }));
  } else {
    prs = await github.paginate(github.rest.pulls.list, {
      owner,
      repo,
      state: 'open',
      per_page: 100,
    });
  }
  let synced = 0;
  const readyCandidates = [];
  for (const pr of prs) {
    if (synced >= maxPrs) break;
    if (pr.draft) continue;
    if (pr.head?.repo?.full_name && pr.head.repo.full_name !== `${owner}/${repo}`) continue;
    const result = await syncPipelineLabels(github, owner, repo, pr.number, core);
    if (result.ready) {
      readyCandidates.push({
        prNumber: pr.number,
        createdAt: result.createdAt || new Date(pr.created_at).getTime(),
        labels: result.labels || [],
      });
    }
    synced += 1;
  }
  let dispatched = 0;
  if (dispatchMergeGate && readyCandidates.length) {
    dispatched = await dispatchMergeGateForOldestReady(
      github, owner, repo, readyCandidates, core
    );
  }
  core?.info?.(`Pipeline label sync complete (${synced} PR(s), dispatched=${dispatched || 'none'})`);
  return synced;
}

module.exports = {
  STAGE_LABELS,
  BLOCKER_LABELS,
  ALL_PIPELINE_LABELS,
  deriveStage,
  deriveBlockerLabels,
  computePipelineLabels,
  ensurePipelineLabels,
  syncPipelineLabels,
  syncOpenPullRequests,
  dispatchMergeGateForOldestReady,
};
