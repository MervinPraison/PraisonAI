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
const AGENT_PY_MAX_AUTO_LINES = 100;
const PR_MAX_AUTO_ADDITIONS = 800;
const PR_MAX_AUTO_FILES = 30;
const MANUAL_ONLY_LABELS = new Set(['security', 'breaking-change', 'needs-manual-review', 'release']);
const WORKFLOW_ONLY_LABEL = 'merge-gate-ci-only';
const CI_ONLY_PATH_PREFIXES = ['.github/workflows/', '.github/actions/', '.github/scripts/merge-gate'];
const SDK_PATH_PREFIXES = ['src/praisonai-agents/', 'src/praisonai/'];
const SENSITIVE_PATH_PATTERNS = [
  /^\.github\/workflows\//,
  /praisonaiagents\/(auth|approval|policy|sandbox)\//,
  /^src\/praisonai-agents\/pyproject\.toml$/,
  /^src\/praisonai\/pyproject\.toml$/,
  /\.env(\.|$)/,
  /credentials\.json$/i,
];
const REQUIRED_SDK_CHECK_PATTERNS = [/test/i, /smoke/i, /core/i, /python package/i, /comprehensive/i, /optimized/i];
const SECRET_PATTERNS = [
  /sk-[a-zA-Z0-9]{20,}/,
  /AKIA[0-9A-Z]{16}/,
  /ghp_[a-zA-Z0-9]{36,}/,
  /github_pat_/,
  /Bearer eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+/,
  /-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----/,
];
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

function isClaudeTriggerNoise(c) {
  const body = c.body || '';
  if (body.includes('Merge gate scan')) return true;
  if (body.includes('MERGE_GATE_VERDICT')) return true;
  if (body.includes('Merged by **Claude PR merge gate**')) return true;
  return false;
}

function hasRecentClaudeTrigger(comments, minutes = 35) {
  const cutoff = Date.now() - minutes * 60 * 1000;
  return comments.some((c) => {
    if (!CLAUDE_TRIGGER_LOGINS.includes(c.user.login)) return false;
    if (isClaudeTriggerNoise(c)) return false;
    if (!(c.body || '').includes('@claude')) return false;
    return new Date(c.created_at).getTime() > cutoff;
  });
}

function isConflictRebaseTriggerComment(c) {
  if (!AUTO_ACTORS.includes(c.user.login)) return false;
  const body = (c.body || '').toLowerCase();
  return body.includes('@claude') && body.includes('merge conflict');
}

function isConflictRebaseCompletionComment(c) {
  const login = (c.user?.login || '').toLowerCase();
  if (!login.includes('praisonai-triage') && !login.includes('github-actions')) return false;
  const body = (c.body || '').toLowerCase();
  return (
    body.includes('rebase complete') ||
    body.includes('rebase onto') ||
    (body.includes('conflict') && body.includes('resolved'))
  );
}

function conflictRebaseQuiescent(comments, headPushedAt) {
  const conflictTriggers = comments.filter(isConflictRebaseTriggerComment);
  if (conflictTriggers.length === 0) return true;

  const latestConflict = conflictTriggers.reduce((a, b) =>
    new Date(a.created_at) > new Date(b.created_at) ? a : b
  );
  const conflictTime = new Date(latestConflict.created_at).getTime();

  const rebaseDone = comments.some(
    (c) =>
      new Date(c.created_at).getTime() > conflictTime && isConflictRebaseCompletionComment(c)
  );
  if (!rebaseDone) return false;

  return finalClaudeCompletedOnSha(comments, headPushedAt);
}

function hasRecentConflictComment(comments, headPushedAt = null) {
  const cutoff = Date.now() - CONFLICT_COOLDOWN_MS;
  const hasRecentTrigger = comments.some((c) => {
    if (!isConflictRebaseTriggerComment(c)) return false;
    return new Date(c.created_at).getTime() > cutoff;
  });
  if (!hasRecentTrigger) return false;

  if (headPushedAt && conflictRebaseQuiescent(comments, headPushedAt)) {
    return false;
  }
  return true;
}

function isBotReviewer(login, userType) {
  const lower = (login || '').toLowerCase();
  if (userType === 'Bot') return true;
  if (lower.endsWith('[bot]')) return true;
  return ['coderabbit', 'qodo', 'gemini', 'copilot', 'greptile'].some((p) => lower.includes(p));
}

function latestReviewsByUser(reviews) {
  const latestByUser = new Map();
  for (const r of reviews) {
    const login = r.user?.login;
    if (!login) continue;
    const prev = latestByUser.get(login);
    if (!prev || new Date(r.submitted_at) > new Date(prev.submitted_at)) {
      latestByUser.set(login, r);
    }
  }
  return latestByUser;
}

function hasHumanChangesRequested(reviews) {
  for (const [login, review] of latestReviewsByUser(reviews)) {
    if (review.state !== 'CHANGES_REQUESTED') continue;
    if (!isBotReviewer(login, review.user?.type)) return true;
  }
  return false;
}

function hasAnyChangesRequested(reviews) {
  for (const [, review] of latestReviewsByUser(reviews)) {
    if (review.state === 'CHANGES_REQUESTED') return true;
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
    if (isClaudeTriggerNoise(c)) return false;
    if (!(c.body || '').includes('@claude')) return false;
    return new Date(c.created_at).getTime() >= headTime - 60000;
  });
  return !claudeSinceHead;
}

function needsStaleFinalRecovery(comments, headPushedAt) {
  return (
    hasFinalClaudeReviewTrigger(comments) &&
    isStaleFinalAfterPush(comments, headPushedAt)
  );
}

function shouldSkipFinalRecovery(comments, headPushedAt) {
  const isStale = isStaleFinalAfterPush(comments, headPushedAt);
  if (isStale) return false;
  return hasRecentClaudeTrigger(comments, 35);
}

function finalClaudeCompletedOnSha(comments, headPushedAt) {
  if (!hasFinalClaudeReviewTrigger(comments)) return false;
  if (isStaleFinalAfterPush(comments, headPushedAt)) return false;
  return true;
}

const FINAL_CLAUDE_REVIEW_BODY =
  '@claude You are the FINAL architecture reviewer. If the branch is under MervinPraison/PraisonAI (not a fork), you are able to make modifications to this branch and push directly. SCOPE: Focus ONLY on Python packages (praisonaiagents, praisonai). Do NOT modify praisonai-rust or praisonai-ts. Read ALL comments above from Gemini, Qodo, CodeRabbit, and Copilot carefully before responding.\n\n**Phase 1: Review per AGENTS.md**\n1. Protocol-driven: check heavy implementations vs core SDK\n2. Backward compatible: ensure zero feature regressions\n3. Performance: no hot-path regressions\n4. SDK value: review in depth whether the change genuinely adds value to the SDK — never add features for the sake of adding them. It must strengthen the SDK (simpler, more user-friendly, robust, world-class, secure). If it does not clearly add value, request changes or recommend rejecting/closing rather than merging scope creep\n5. Do not bloat the Agent class with additional params — only if absolutely required; we already support many params.\n\n**Phase 2: FIX Valid Issues**\n5. For any VALID bugs or architectural flaws found by Gemini, CodeRabbit, Qodo, Copilot, or any other reviewer: implement the fix\n6. Push all code fixes directly to THIS branch (do NOT create a new PR)\n7. Comment a summary of exact files modified and what you skipped\n\n**Phase 3: Final Verdict**\n8. If all issues are resolved, approve the PR / close the Issue\n9. If blocking issues remain, request changes / leave clear action items';

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

function claudeRunBlocksPr(run, headRef) {
  if (!run || run.event === 'issues') return false;
  if (!headRef) return true;
  return run.head_branch === headRef;
}

function hasBlockingClaudeRunForPr(runs, headRef) {
  return (runs || []).some((r) => claudeRunBlocksPr(r, headRef));
}

async function hasInProgressClaudeAssistant(github, owner, repo, prNumber = null) {
  try {
    const { data } = await github.rest.actions.listWorkflowRuns({
      owner,
      repo,
      workflow_id: 'claude.yml',
      status: 'in_progress',
      per_page: 20,
    });
    const runs = (data.workflow_runs || []).filter((r) => r.event !== 'issues');
    if (runs.length === 0) return false;
    if (prNumber == null) return runs.length > 0;

    const { data: pr } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
    const headRef = pr.head.ref;
    return hasBlockingClaudeRunForPr(runs, headRef);
  } catch {
    return false;
  }
}

function isCiOnlyChange(files) {
  if (!files.length) return false;
  return files.every((f) => CI_ONLY_PATH_PREFIXES.some((p) => f.filename.startsWith(p)));
}

async function resolvePrNumberFromWorkflowRun(github, owner, repo, workflowRun) {
  const linked = workflowRun.pull_requests || [];
  if (linked.length > 0 && linked[0].number) return linked[0].number;
  const branch = workflowRun.head_branch;
  if (!branch) return null;
  const { data } = await github.rest.pulls.list({
    owner,
    repo,
    state: 'open',
    head: `${owner}:${branch}`,
    per_page: 1,
  });
  return data[0]?.number || null;
}

async function listPullFiles(github, owner, repo, prNumber) {
  if (typeof github.paginate === 'function') {
    return github.paginate(github.rest.pulls.listFiles, {
      owner,
      repo,
      pull_number: prNumber,
      per_page: 100,
    });
  }
  const { data } = await github.rest.pulls.listFiles({
    owner,
    repo,
    pull_number: prNumber,
    per_page: 100,
  });
  return data;
}

function countNewAgentParams(patch) {
  if (!patch) return 0;
  return patch
    .split('\n')
    .filter((l) => l.startsWith('+') && !l.startsWith('+++'))
    .filter((l) => {
      const t = l.slice(1).trim();
      if (!t || t.startsWith('#') || t.startsWith('"""') || t.startsWith("'''")) return false;
      if (/^(def|class|@|return\b|if\b|elif\b|else\b|for\b|while\b)/.test(t)) return false;
      if (/^\w+\s*[:=]/.test(t) && !t.startsWith('self.')) return true;
      return false;
    }).length;
}

function getAgentPyChangeFromFiles(files) {
  const agentFile = files.find((f) => f.filename.endsWith('praisonaiagents/agent/agent.py'));
  if (!agentFile) {
    return { touched: false, additions: 0, newParams: 0 };
  }
  return {
    touched: true,
    additions: agentFile.additions || 0,
    newParams: countNewAgentParams(agentFile.patch || ''),
  };
}

async function getAgentPyChange(github, owner, repo, prNumber) {
  const files = await listPullFiles(github, owner, repo, prNumber);
  return getAgentPyChangeFromFiles(files);
}

function touchesSdk(files) {
  return files.some((f) => SDK_PATH_PREFIXES.some((p) => f.filename.startsWith(p)));
}

function hasManualOnlyLabel(labels) {
  return labels.some((l) => MANUAL_ONLY_LABELS.has(l));
}

function sensitivePathReasons(files, labels = []) {
  if (labels.includes(WORKFLOW_ONLY_LABEL) && isCiOnlyChange(files)) {
    return [];
  }
  const reasons = [];
  for (const f of files) {
    if (SENSITIVE_PATH_PATTERNS.some((p) => p.test(f.filename))) {
      reasons.push(`sensitive path: ${f.filename}`);
      break;
    }
  }
  return reasons;
}

function prSizeReasons(files) {
  const reasons = [];
  const totalAdditions = files.reduce((sum, f) => sum + (f.additions || 0), 0);
  if (totalAdditions > PR_MAX_AUTO_ADDITIONS) {
    reasons.push(`PR +${totalAdditions} lines (>${PR_MAX_AUTO_ADDITIONS}) requires manual review`);
  }
  if (files.length > PR_MAX_AUTO_FILES) {
    reasons.push(`${files.length} files changed (>${PR_MAX_AUTO_FILES}) requires manual review`);
  }
  return reasons;
}

function missingTestsReason(files) {
  const sdkAdds = files.filter(
    (f) =>
      f.filename.startsWith('src/praisonai-agents/') &&
      f.filename.endsWith('.py') &&
      !f.filename.endsWith('__init__.py') &&
      (f.additions || 0) > 0
  );
  if (sdkAdds.length === 0) return null;
  const hasTestChange = files.some(
    (f) => /\/tests?\//.test(f.filename) || /test_.*\.py$/.test(f.filename) || /_test\.py$/.test(f.filename)
  );
  if (!hasTestChange) return 'SDK code added without test file changes — requires manual review';
  return null;
}

function secretScanReasons(files) {
  for (const f of files) {
    if (/\/tests?\//.test(f.filename) || /test_.*\.py$/.test(f.filename)) continue;
    const patch = f.patch || '';
    if (!patch) continue;
    for (const pattern of SECRET_PATTERNS) {
      if (pattern.test(patch)) {
        return [`possible secret in diff (${f.filename}) — requires manual review`];
      }
    }
  }
  return [];
}

async function sdkTestChecksReason(github, owner, repo, sha, files, core) {
  if (!touchesSdk(files)) return null;
  const { data } = await github.rest.checks.listForRef({
    owner,
    repo,
    ref: sha,
    per_page: 100,
  });
  const runs = (data.check_runs || []).filter((r) => r.head_sha === sha);
  if (runs.length === 0) {
    return 'SDK code changed but no CI checks on HEAD';
  }
  const testRuns = runs.filter((r) => REQUIRED_SDK_CHECK_PATTERNS.some((p) => p.test(r.name || '')));
  if (testRuns.length === 0) {
    return 'SDK code changed but no test check runs on HEAD';
  }
  core?.info?.(`SDK test checks on HEAD: ${testRuns.map((r) => r.name).join(', ')}`);
  return null;
}

function manualReviewReasonForAgentPy(agentChange) {
  if (!agentChange.touched) return null;
  if (agentChange.additions > AGENT_PY_MAX_AUTO_LINES) {
    return `agent.py +${agentChange.additions} lines (>${AGENT_PY_MAX_AUTO_LINES}) requires manual review`;
  }
  if (agentChange.newParams > 0) {
    return `agent.py adds ${agentChange.newParams} new Agent param(s) — requires manual review`;
  }
  return null;
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
  const {
    forMergeStep = false,
    skipGlobalClaudeRunCheck = false,
    skipRecentClaudeCooldown = false,
  } = options;
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

  if (hasRecentConflictComment(ctx.comments, ctx.headPushedAt)) {
    reasons.push('recent merge-conflict @claude');
  }
  if (!skipRecentClaudeCooldown && hasRecentClaudeTrigger(ctx.comments, 35)) {
    reasons.push('recent @claude within 35min');
  }

  if (!skipGlobalClaudeRunCheck && (await hasInProgressClaudeAssistant(github, owner, repo, prNumber))) {
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

  if (hasAnyChangesRequested(ctx.reviews)) reasons.push('CHANGES_REQUESTED review');

  if (hasManualOnlyLabel(ctx.labels)) {
    const manualLabel = ctx.labels.find((l) => MANUAL_ONLY_LABELS.has(l));
    reasons.push(`manual-only label: ${manualLabel}`);
  }

  const pullFiles = await listPullFiles(github, owner, repo, prNumber);

  const agentChange = getAgentPyChangeFromFiles(pullFiles);
  const agentManual = manualReviewReasonForAgentPy(agentChange);
  if (agentManual) reasons.push(agentManual);

  reasons.push(...sensitivePathReasons(pullFiles, ctx.labels));
  reasons.push(...prSizeReasons(pullFiles));
  reasons.push(...secretScanReasons(pullFiles));

  const testsReason = missingTestsReason(pullFiles);
  if (testsReason) reasons.push(testsReason);

  const sdkCheckReason = await sdkTestChecksReason(github, owner, repo, ctx.headSha, pullFiles, core);
  if (sdkCheckReason) reasons.push(sdkCheckReason);

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

async function selectMergeGateCandidates(github, owner, repo, prNumbers, maxCandidates, core) {
  const readyList = [];
  const skipped = [];
  for (const num of prNumbers) {
    const result = await evaluatePipelineQuiescent(github, owner, repo, num, core);
    if (result.ready) {
      readyList.push({ pr_number: num, head_sha: result.headSha });
    } else {
      skipped.push({ pr: num, reasons: result.reasons });
    }
  }
  readyList.sort((a, b) => a.pr_number - b.pr_number);
  return {
    candidates: readyList.slice(0, maxCandidates),
    skipped,
  };
}

function findMergeGateVerdict(comments, minCreatedAt = null, headPushedAt = null) {
  const minTime = minCreatedAt ? new Date(minCreatedAt).getTime() : 0;
  const headTime = headPushedAt ? new Date(headPushedAt).getTime() - 60000 : 0;
  const gateComments = comments
    .filter((c) => {
      if (!(c.body || '').includes('MERGE_GATE_VERDICT:')) return false;
      const created = new Date(c.created_at).getTime();
      if (minTime && created < minTime) return false;
      if (headTime && created < headTime) return false;
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
  isClaudeTriggerNoise,
  hasRecentClaudeTrigger,
  hasRecentConflictComment,
  isConflictRebaseTriggerComment,
  isConflictRebaseCompletionComment,
  conflictRebaseQuiescent,
  hasHumanChangesRequested,
  hasAnyChangesRequested,
  hasFinalClaudeReviewTrigger,
  finalClaudeCompletedOnSha,
  getMergeState,
  allChecksGreenOnSha,
  hasInProgressClaudeAssistant,
  claudeRunBlocksPr,
  hasBlockingClaudeRunForPr,
  isCiOnlyChange,
  resolvePrNumberFromWorkflowRun,
  WORKFLOW_ONLY_LABEL,
  getAgentPyChange,
  getAgentPyChangeFromFiles,
  manualReviewReasonForAgentPy,
  countNewAgentParams,
  listPullFiles,
  touchesSdk,
  hasManualOnlyLabel,
  sensitivePathReasons,
  prSizeReasons,
  missingTestsReason,
  secretScanReasons,
  sdkTestChecksReason,
  listAllComments,
  getHeadCommitDate,
  isStaleFinalAfterPush,
  needsStaleFinalRecovery,
  shouldSkipFinalRecovery,
  FINAL_CLAUDE_REVIEW_BODY,
  loadPrContext,
  evaluatePipelineQuiescent,
  selectMergeGateCandidates,
  findMergeGateVerdict,
};
