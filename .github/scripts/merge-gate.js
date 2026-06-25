/**
 * Shared merge-gate helpers for claude-merge-gate.yml
 * @see .github/workflows/claude-merge-gate.yml
 */

const CLAUDE_TRIGGER_LOGINS = ['MervinPraison', 'github-actions[bot]'];
const AUTO_ACTORS = CLAUDE_TRIGGER_LOGINS;
const CONFLICT_COOLDOWN_MS = 12 * 60 * 60 * 1000;
const CLAUDE_ACTIVE_MS = 35 * 60 * 1000;
const POST_PUSH_BUFFER_MS = 5 * 60 * 1000;
const ALLOWED_MERGE_STATES = new Set(['CLEAN', 'UNSTABLE']);
const BLOCK_LABELS = new Set([
  'claude-conflict-pending',
  'claude-merge-gate-active',
  'no-auto-merge',
  'auto-merged-by-gate',
]);
const BOT_REVIEWER_PATTERNS = [
  'coderabbit',
  'qodo',
  'gemini',
  'copilot',
  'greptile',
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function isFinalClaudeTriggerComment(c) {
  const body = (c.body || '').toLowerCase();
  if (!AUTO_ACTORS.includes(c.user.login)) return false;
  if (!body.includes('@claude')) return false;
  if (body.includes('merge conflict')) return false;
  return body.includes('final architecture reviewer') || body.includes('lead engineer');
}

function hasRecentClaudeTrigger(comments, minutes = 35) {
  const cutoff = Date.now() - minutes * 60 * 1000;
  return comments.some((c) => {
    if (!CLAUDE_TRIGGER_LOGINS.includes(c.user.login)) return false;
    if (!(c.body || '').includes('@claude')) return false;
    return new Date(c.created_at).getTime() > cutoff;
  });
}

function hasRecentConflictComment(comments) {
  const cutoff = Date.now() - CONFLICT_COOLDOWN_MS;
  return comments.some((c) => {
    if (!AUTO_ACTORS.includes(c.user.login)) return false;
    const body = (c.body || '').toLowerCase();
    if (!body.includes('@claude') || !body.includes('merge conflict')) return false;
    return new Date(c.created_at).getTime() > cutoff;
  });
}

function isBotReviewer(login, userType) {
  const lower = (login || '').toLowerCase();
  if (userType === 'Bot') return true;
  if (lower.endsWith('[bot]')) return true;
  return ['coderabbit', 'qodo', 'gemini', 'copilot', 'greptile'].some((p) => lower.includes(p));
}

function hasHumanChangesRequested(reviews) {
  const latestByUser = new Map();
  for (const r of reviews) {
    const login = r.user?.login;
    if (!login) continue;
    const prev = latestByUser.get(login);
    if (!prev || new Date(r.submitted_at) > new Date(prev.submitted_at)) {
      latestByUser.set(login, r);
    }
  }
  for (const [login, review] of latestByUser) {
    if (review.state !== 'CHANGES_REQUESTED') continue;
    if (!isBotReviewer(login, review.user?.type)) return true;
  }
  return false;
}

function hasFinalClaudeReviewTrigger(comments) {
  return comments.some(isFinalClaudeTriggerComment);
}

function isStaleFinalAfterPush(comments, headPushedAt) {
  if (!headPushedAt) return false;
  const headTime = new Date(headPushedAt).getTime();
  const finals = comments.filter(isFinalClaudeTriggerComment);
  if (finals.length === 0) return true;
  const latestFinal = finals.reduce((a, b) =>
    new Date(a.created_at) > new Date(b.created_at) ? a : b
  );
  const finalTime = new Date(latestFinal.created_at).getTime();
  if (headTime <= finalTime + 60000) return false;
  const claudeSinceHead = comments.some((c) => {
    if (!CLAUDE_TRIGGER_LOGINS.includes(c.user.login)) return false;
    if (!(c.body || '').includes('@claude')) return false;
    return new Date(c.created_at).getTime() >= headTime - 60000;
  });
  return !claudeSinceHead;
}

function finalClaudeCompletedOnSha(comments, headPushedAt) {
  if (!hasFinalClaudeReviewTrigger(comments)) return false;
  if (isStaleFinalAfterPush(comments, headPushedAt)) return false;
  return true;
}

async function getMergeState(github, owner, repo, prNumber) {
  const query = `
    query($owner: String!, $repo: String!, $number: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
          mergeStateStatus
          maintainerCanModify
          isDraft
          headRefOid
          headRef { repository { nameWithOwner } }
        }
      }
    }
  `;
  for (let attempt = 0; attempt < 3; attempt++) {
    const result = await github.graphql(query, { owner, repo, number: prNumber });
    const prGql = result.repository.pullRequest;
    const status = (prGql?.mergeStateStatus || '').toUpperCase();
    if (status && status !== 'UNKNOWN') {
      return {
        status,
        isDraft: prGql.isDraft,
        headRepo: prGql.headRef?.repository?.nameWithOwner,
        headSha: prGql.headRefOid,
        maintainerCanModify: prGql.maintainerCanModify === true,
      };
    }
    if (attempt < 2) await sleep(10000);
  }
  const { data: pr } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
  return {
    status: (pr.mergeable_state || '').toUpperCase(),
    isDraft: pr.draft,
    headRepo: pr.head.repo?.full_name,
    headSha: pr.head.sha,
    maintainerCanModify: pr.maintainer_can_modify === true,
  };
}

async function allChecksGreenOnSha(github, owner, repo, sha, core) {
  const { data } = await github.rest.checks.listForRef({
    owner,
    repo,
    ref: sha,
    per_page: 100,
  });
  const runs = (data.check_runs || []).filter((r) => r.head_sha === sha);
  if (runs.length === 0) {
    core?.info?.(`No check runs on ${sha.slice(0, 7)} — allowing (e.g. docs-only PR)`);
    return true;
  }
  for (const run of runs) {
    if (run.status !== 'completed') {
      core?.info?.(`Check pending: ${run.name} (${run.status})`);
      return false;
    }
    const ok = ['success', 'neutral', 'skipped'].includes(run.conclusion);
    if (!ok) {
      core?.info?.(`Check failed: ${run.name} (${run.conclusion})`);
      return false;
    }
  }
  return true;
}

async function hasInProgressClaudeAssistant(github, owner, repo) {
  try {
    const { data } = await github.rest.actions.listWorkflowRuns({
      owner,
      repo,
      workflow_id: 'claude.yml',
      status: 'in_progress',
      per_page: 5,
    });
    return (data.total_count || 0) > 0;
  } catch {
    return false;
  }
}

async function listAllComments(github, owner, repo, issueNumber) {
  if (typeof github.paginate === 'function') {
    return github.paginate(github.rest.issues.listComments, {
      owner,
      repo,
      issue_number: issueNumber,
      per_page: 100,
    });
  }
  const { data } = await github.rest.issues.listComments({
    owner,
    repo,
    issue_number: issueNumber,
    per_page: 100,
  });
  return data;
}

async function getHeadCommitDate(github, owner, repo, prNumber) {
  try {
    let commits;
    if (typeof github.paginate === 'function') {
      commits = await github.paginate(github.rest.pulls.listCommits, {
        owner,
        repo,
        pull_number: prNumber,
        per_page: 100,
      });
    } else {
      const { data } = await github.rest.pulls.listCommits({
        owner,
        repo,
        pull_number: prNumber,
        per_page: 100,
      });
      commits = data;
    }
    const last = commits[commits.length - 1];
    return last?.commit?.committer?.date || last?.commit?.author?.date || null;
  } catch {
    return null;
  }
}

async function loadPrContext(github, owner, repo, prNumber) {
  const { data: pr } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
  const { data: issue } = await github.rest.issues.get({ owner, repo, issue_number: prNumber });
  const comments = await listAllComments(github, owner, repo, prNumber);
  const { data: reviews } = await github.rest.pulls.listReviews({
    owner,
    repo,
    pull_number: prNumber,
    per_page: 100,
  });
  const mergeState = await getMergeState(github, owner, repo, prNumber);
  const headSha = mergeState.headSha || pr.head.sha;
  const headCommitDate = await getHeadCommitDate(github, owner, repo, prNumber);
  const headPushedAt = headCommitDate || pr.updated_at;

  return {
    pr,
    issue,
    comments,
    reviews,
    mergeState,
    headSha,
    headPushedAt,
    labels: issue.labels.map((l) => l.name),
    baseRepo: `${owner}/${repo}`,
  };
}

async function evaluatePipelineQuiescent(github, owner, repo, prNumber, core, options = {}) {
  const { forMergeStep = false, skipGlobalClaudeRunCheck = false } = options;
  const ctx = await loadPrContext(github, owner, repo, prNumber);
  const reasons = [];

  if (ctx.pr.draft) reasons.push('draft');
  if (ctx.pr.state !== 'open') reasons.push('not open');
  if (ctx.labels.includes('auto-merged-by-gate')) reasons.push('already merged by gate');
  if (ctx.labels.includes('no-auto-merge')) reasons.push('no-auto-merge label');
  if (ctx.labels.includes('claude-conflict-pending')) reasons.push('claude-conflict-pending');
  if (!forMergeStep && ctx.labels.includes('claude-merge-gate-active')) {
    reasons.push('claude-merge-gate-active');
  }

  const { status, headRepo, maintainerCanModify } = ctx.mergeState;
  if (!ALLOWED_MERGE_STATES.has(status)) reasons.push(`mergeState=${status}`);

  if (headRepo && headRepo !== ctx.baseRepo) {
    reasons.push('fork PR');
  }

  if (hasRecentConflictComment(ctx.comments)) reasons.push('recent merge-conflict @claude');
  if (hasRecentClaudeTrigger(ctx.comments, 35)) reasons.push('recent @claude within 35min');

  if (!skipGlobalClaudeRunCheck && (await hasInProgressClaudeAssistant(github, owner, repo))) {
    reasons.push('claude.yml in progress');
  }

  const headTime = new Date(ctx.headPushedAt).getTime();
  if (Date.now() - headTime < POST_PUSH_BUFFER_MS) reasons.push('post-push buffer (<5min)');

  if (!finalClaudeCompletedOnSha(ctx.comments, ctx.headPushedAt)) {
    if (!hasFinalClaudeReviewTrigger(ctx.comments)) {
      reasons.push('no FINAL Claude review trigger');
    } else if (isStaleFinalAfterPush(ctx.comments, ctx.headPushedAt)) {
      reasons.push('stale FINAL after new commits (needs @claude re-review)');
    } else {
      reasons.push('FINAL Claude not complete on HEAD');
    }
  }

  if (hasHumanChangesRequested(ctx.reviews)) reasons.push('human CHANGES_REQUESTED');

  const checksOk = await allChecksGreenOnSha(github, owner, repo, ctx.headSha, core);
  if (!checksOk) reasons.push('CI not green on HEAD');

  if (ctx.pr.mergeable === false) reasons.push('not mergeable');

  const ready = reasons.length === 0;
  return {
    ready,
    reasons,
    headSha: ctx.headSha,
    prNumber,
  };
}

function findMergeGateVerdict(comments, minCreatedAt = null) {
  const minTime = minCreatedAt ? new Date(minCreatedAt).getTime() : 0;
  const gateComments = comments
    .filter((c) => {
      if (!(c.body || '').includes('MERGE_GATE_VERDICT:')) return false;
      if (minTime && new Date(c.created_at).getTime() < minTime) return false;
      return true;
    })
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  if (gateComments.length === 0) return null;
  const body = gateComments[0].body || '';
  if (body.includes('MERGE_GATE_VERDICT: APPROVE')) return 'APPROVE';
  if (body.includes('MERGE_GATE_VERDICT: BLOCK')) return 'BLOCK';
  return null;
}

module.exports = {
  CLAUDE_TRIGGER_LOGINS,
  AUTO_ACTORS,
  isFinalClaudeTriggerComment,
  hasRecentClaudeTrigger,
  hasRecentConflictComment,
  hasHumanChangesRequested,
  hasFinalClaudeReviewTrigger,
  finalClaudeCompletedOnSha,
  getMergeState,
  allChecksGreenOnSha,
  hasInProgressClaudeAssistant,
  listAllComments,
  getHeadCommitDate,
  isStaleFinalAfterPush,
  loadPrContext,
  evaluatePipelineQuiescent,
  findMergeGateVerdict,
};
