/**
 * Post @claude comments with CI failure details for internal PRs.
 * @see .github/workflows/ci-failure-claude.yml
 */

const mergeGate = require('./merge-gate.js');

const CI_FIX_LABEL = 'claude-ci-fix-pending';
const COOLDOWN_MS = 12 * 60 * 60 * 1000;
const AUTO_ACTORS = mergeGate.AUTO_ACTORS;
const MAX_FAILURES = 15;
const MAX_JOBS_TO_FETCH = 5;

function shortSha(headSha) {
  return (headSha || '').slice(0, 8);
}

function ciFixShaMarker(headSha) {
  return `ci failed on head \`${shortSha(headSha)}`.toLowerCase();
}

function isCiFixComment(comment) {
  const body = (comment.body || '').toLowerCase();
  return body.includes('@claude') && body.includes('ci failed on head');
}

function hasCiFixCommentForSha(comments, headSha) {
  const marker = shortSha(headSha).toLowerCase();
  return comments.some((c) => {
    if (!AUTO_ACTORS.includes(c.user.login)) return false;
    if (!isCiFixComment(c)) return false;
    return (c.body || '').toLowerCase().includes(marker);
  });
}

function hasRecentCiFixComment(comments, headSha) {
  const cutoff = Date.now() - COOLDOWN_MS;
  const marker = shortSha(headSha).toLowerCase();
  return comments.some((c) => {
    if (!AUTO_ACTORS.includes(c.user.login)) return false;
    if (!isCiFixComment(c)) return false;
    const body = (c.body || '').toLowerCase();
    if (body.includes(marker)) return true;
    return new Date(c.created_at).getTime() > cutoff;
  });
}

function shouldSkipCiFix({ comments, headSha, labels, hasFinal, claudeInProgress, failedChecks }) {
  if (!failedChecks.length) return { skip: true, reason: 'no failed checks' };
  if (labels.includes(CI_FIX_LABEL)) return { skip: true, reason: 'ci fix pending' };
  if (!hasFinal) return { skip: true, reason: 'awaiting final claude review trigger' };
  if (claudeInProgress) return { skip: true, reason: 'claude in progress' };
  if (hasCiFixCommentForSha(comments, headSha)) {
    return { skip: true, reason: 'already commented for this sha' };
  }
  if (hasRecentCiFixComment(comments, headSha)) {
    return { skip: true, reason: 'recent ci fix comment cooldown' };
  }
  return { skip: false };
}

function parsePytestFailures(logText) {
  if (!logText) return [];
  const lines = logText.split('\n');
  const failures = [];
  const seen = new Set();

  for (let i = lines.length - 1; i >= 0 && failures.length < MAX_FAILURES; i -= 1) {
    const line = lines[i].trim();
    if (!line) continue;

    const pytestMatch = line.match(
      /FAILED\s*(?:\([^)]+\))?\s+(tests\/[^\s]+(?:::[^\s-]+)*)\s*-\s*(.+)/i
    );
    if (pytestMatch) {
      const testId = pytestMatch[1];
      if (!seen.has(testId)) {
        seen.add(testId);
        failures.push({ testId, error: pytestMatch[2].trim() });
      }
      continue;
    }

    const errorMatch = line.match(/##\[error\](.+)/);
    if (errorMatch && /tests\//.test(errorMatch[1])) {
      const msg = errorMatch[1].trim();
      if (!seen.has(msg)) {
        seen.add(msg);
        failures.push({ testId: msg, error: msg });
      }
    }
  }

  return failures;
}

async function fetchJobFailureSummary(github, owner, repo, jobId, jobName) {
  try {
    const response = await github.rest.actions.downloadJobLogsForWorkflowRun({
      owner,
      repo,
      job_id: jobId,
    });
    let logText = typeof response.data === 'string' ? response.data : String(response.data || '');
    if (logText.length > 100000) {
      logText = logText.slice(-100000);
    }
    return { jobName, jobId, failures: parsePytestFailures(logText) };
  } catch (err) {
    return { jobName, jobId, failures: [], error: err.message };
  }
}

function mapFailedChecks(runs) {
  return runs.map((run) => ({
    name: run.name,
    id: run.id,
    html_url: run.html_url || run.details_url,
    workflow: run.app?.slug || run.check_suite?.app?.slug || run.name,
  }));
}

function buildCiFixComment({ headSha, failedChecks, failureSummaries }) {
  const parts = [
    `@claude CI failed on HEAD \`${shortSha(headSha)}\`. Please fix the failures below and push to this branch.`,
    '',
    '## Failed checks',
  ];

  for (const check of failedChecks) {
    parts.push(`- **${check.workflow || check.name}** / \`${check.name}\` — ${check.html_url}`);
  }

  parts.push('', '## Failures (extracted)');
  let idx = 0;
  for (const summary of failureSummaries) {
    for (const failure of summary.failures) {
      idx += 1;
      if (idx > MAX_FAILURES) break;
      parts.push(`${idx}. \`${failure.testId}\` — \`${failure.error}\``);
      parts.push(`   - Job: \`${summary.jobName}\``);
    }
    if (idx >= MAX_FAILURES) break;
  }

  if (idx === 0) {
    parts.push('_(Could not extract pytest details — see job logs above.)_');
  }

  const exampleTest = failureSummaries.find((s) => s.failures.length)?.failures[0]?.testId;
  parts.push(
    '',
    '## Critical review first',
    'Before changing code or tests, decide **which side is wrong**:',
    '1. **Legitimate feature change** — the PR intent is correct but implementation or tests need updating. Preserve SDK guarantees; update tests only when behaviour intentionally changed and document why.',
    '2. **Regression / bug in this PR** — the failure exposes a real breakage introduced here. Fix the implementation; **do not weaken, skip, or delete tests** just to go green.',
    '3. **Pre-existing flake or unrelated failure** — say so explicitly; prefer fixing the root cause over masking it.',
    '',
    '**SDK guardrails (AGENTS.md):**',
    '- Do not disturb core SDK contracts to accommodate a wrapper/feature change.',
    '- Tests must continue to guard backward compatibility and hot-path behaviour — passing CI by lowering test standards is not acceptable.',
    '- If the feature does not genuinely add SDK value, recommend reverting or narrowing scope instead of patching around failures.',
    '',
    '## What to do',
    '1. State your verdict: **legitimate fix**, **regression fix**, or **needs human review** — and why (1–3 sentences).',
    '2. Fix root cause with **minimal changes**; never bloat the Agent class with extra params.',
    exampleTest
      ? `3. Run failing tests locally, e.g. \`pytest ${exampleTest} -q\`, plus any related SDK tests touched by the PR.`
      : '3. Run failing tests locally with targeted pytest, plus any related SDK tests touched by the PR.',
    '4. Push to this branch and comment: files changed, review verdict, and why tests still protect SDK behaviour.',
  );

  return parts.join('\n');
}

async function maybeClearCiFixLabel(github, owner, repo, prNumber, labels, headSha, core) {
  if (!labels.includes(CI_FIX_LABEL)) return false;
  const ciGreen = await mergeGate.allChecksGreenOnSha(github, owner, repo, headSha, core);
  if (!ciGreen) return false;
  try {
    await github.rest.issues.removeLabel({
      owner,
      repo,
      issue_number: prNumber,
      name: CI_FIX_LABEL,
    });
    core?.info?.(`Removed ${CI_FIX_LABEL} from PR #${prNumber}`);
  } catch (err) {
    if (err.status !== 404) throw err;
  }
  return true;
}

async function maybeTriggerCiFixClaude(github, owner, repo, prNumber, core, opts = {}) {
  const baseRepo = `${owner}/${repo}`;
  const ctx = await mergeGate.loadPrContext(github, owner, repo, prNumber);
  const pr = ctx.pr;

  if (pr.state !== 'open') return { skipped: true, reason: 'not open' };
  if (pr.draft) return { skipped: true, reason: 'draft' };

  const headRepo = pr.head.repo?.full_name;
  if (headRepo && headRepo !== baseRepo && !pr.maintainer_can_modify) {
    return { skipped: true, reason: 'fork without maintainer edits' };
  }

  const headSha = pr.head.sha;
  const labels = ctx.labels;

  if (await maybeClearCiFixLabel(github, owner, repo, prNumber, labels, headSha, core)) {
    return { skipped: true, reason: 'ci green, label cleared' };
  }

  const ciGreen = await mergeGate.allChecksGreenOnSha(github, owner, repo, headSha, core);
  if (ciGreen) return { skipped: true, reason: 'ci green' };

  const runs = await mergeGate.listChecksOnSha(github, owner, repo, headSha);
  const failedRuns = mergeGate.listFailedChecksOnSha(runs);
  if (failedRuns.length === 0) {
    return { skipped: true, reason: 'no failed checks yet (may be pending)' };
  }

  const hasFinal = mergeGate.hasFinalClaudeReviewTrigger(ctx.comments);
  const claudeInProgress = await mergeGate.hasInProgressClaudeAssistant(
    github, owner, repo, prNumber
  );
  const skip = shouldSkipCiFix({
    comments: ctx.comments,
    headSha,
    labels,
    hasFinal,
    claudeInProgress,
    failedChecks: failedRuns,
  });
  if (skip.skip) return { skipped: true, reason: skip.reason };

  const failedChecks = mapFailedChecks(failedRuns);
  const failureSummaries = [];
  for (const check of failedChecks.slice(0, MAX_JOBS_TO_FETCH)) {
    failureSummaries.push(
      await fetchJobFailureSummary(github, owner, repo, check.id, check.name)
    );
  }

  const body = buildCiFixComment({ headSha, failedChecks, failureSummaries });

  await github.rest.issues.createComment({
    owner,
    repo,
    issue_number: prNumber,
    body,
  });
  await github.rest.issues.addLabels({
    owner,
    repo,
    issue_number: prNumber,
    labels: [CI_FIX_LABEL],
  });

  core?.info?.(`Posted CI fix @claude on PR #${prNumber} (${shortSha(headSha)})`);
  return { triggered: true, headSha: shortSha(headSha) };
}

async function processWorkflowRunFailure(github, owner, repo, workflowRun, core) {
  if (workflowRun.conclusion !== 'failure') {
    return { skipped: true, reason: `conclusion=${workflowRun.conclusion}` };
  }
  const allowed = ['Core Tests', 'Optimized Test Suite'];
  if (!allowed.includes(workflowRun.name)) {
    return { skipped: true, reason: `workflow ${workflowRun.name}` };
  }
  const prNumber = await mergeGate.resolvePrNumberFromWorkflowRun(
    github, owner, repo, workflowRun
  );
  if (!prNumber) return { skipped: true, reason: 'no linked PR' };
  return maybeTriggerCiFixClaude(github, owner, repo, prNumber, core);
}

module.exports = {
  CI_FIX_LABEL,
  COOLDOWN_MS,
  ciFixShaMarker,
  isCiFixComment,
  hasCiFixCommentForSha,
  hasRecentCiFixComment,
  shouldSkipCiFix,
  parsePytestFailures,
  fetchJobFailureSummary,
  buildCiFixComment,
  maybeClearCiFixLabel,
  maybeTriggerCiFixClaude,
  processWorkflowRunFailure,
};
