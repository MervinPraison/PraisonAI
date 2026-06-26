/**
 * Idempotent CodeRabbit/Qodo kick for bot-opened PRs.
 * @see .github/workflows/auto-pr-comment.yml, claude.yml, bot-pr-recovery.yml
 */

const KICK_AUTHORS = new Set(['MervinPraison', 'github-actions[bot]']);
const BOT_PR_AUTHORS = new Set(['praisonai-triage-agent[bot]', 'github-actions[bot]']);

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

function chainKickPosted(comments) {
  return comments.some(
    (c) =>
      KICK_AUTHORS.has(c.user?.login) &&
      (c.body || '').includes('@coderabbitai review')
  );
}

function isBotOpenedPr(pr) {
  if (BOT_PR_AUTHORS.has(pr.user?.login)) return true;
  return pr.user?.type === 'Bot';
}

async function kickReviewChain(github, owner, repo, prNumber, core) {
  const comments = await listAllComments(github, owner, repo, prNumber);
  if (chainKickPosted(comments)) {
    core?.info?.(`Review chain already kicked on PR #${prNumber}`);
    return { kicked: false, reason: 'already_kicked' };
  }

  await github.rest.issues.createComment({
    owner,
    repo,
    issue_number: prNumber,
    body: '@coderabbitai review',
  });
  await github.rest.issues.createComment({
    owner,
    repo,
    issue_number: prNumber,
    body: '/review',
  });
  core?.info?.(`Kicked review chain for PR #${prNumber}`);
  return { kicked: true };
}

async function findOpenPrForIssue(github, owner, repo, issueNumber) {
  const prefix = `claude/issue-${issueNumber}-`;
  const { data: prs } = await github.rest.pulls.list({
    owner,
    repo,
    state: 'open',
    sort: 'created',
    direction: 'desc',
    per_page: 30,
  });
  return prs.find((p) => (p.head?.ref || '').startsWith(prefix)) || null;
}

async function kickReviewChainForIssue(github, owner, repo, issueNumber, core) {
  const pr = await findOpenPrForIssue(github, owner, repo, issueNumber);
  if (!pr) {
    core?.info?.(`No open PR for issue #${issueNumber}, skipping review kick`);
    return { kicked: false, reason: 'no_pr' };
  }
  const result = await kickReviewChain(github, owner, repo, pr.number, core);
  return { ...result, prNumber: pr.number };
}

async function recoverStalledBotPrs(github, owner, repo, options, core) {
  const { prNumber = null, minAgeMs = 10 * 60 * 1000, maxRecover = 10 } = options || {};
  let prs;
  if (prNumber) {
    const { data } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
    prs = [data];
  } else {
    const { data } = await github.rest.pulls.list({ owner, repo, state: 'open', per_page: 100 });
    prs = data;
  }

  const cutoff = Date.now() - minAgeMs;
  let recovered = 0;
  for (const pr of prs) {
    if (recovered >= maxRecover) break;
    if (!prNumber) {
      if (!isBotOpenedPr(pr)) continue;
      if (new Date(pr.created_at).getTime() > cutoff) continue;
    }
    const comments = await listAllComments(github, owner, repo, pr.number);
    if (chainKickPosted(comments)) continue;
    await kickReviewChain(github, owner, repo, pr.number, core);
    recovered += 1;
  }
  core?.info?.(`Recovery complete (${recovered} PR(s) kicked)`);
  return recovered;
}

module.exports = {
  KICK_AUTHORS,
  BOT_PR_AUTHORS,
  listAllComments,
  chainKickPosted,
  isBotOpenedPr,
  kickReviewChain,
  findOpenPrForIssue,
  kickReviewChainForIssue,
  recoverStalledBotPrs,
};
