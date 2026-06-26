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

function kickAuthored(comment, marker) {
  return (
    KICK_AUTHORS.has(comment.user?.login) &&
    (comment.body || '').includes(marker)
  );
}

function coderabbitKickPosted(comments) {
  return comments.some((c) => kickAuthored(c, '@coderabbitai review'));
}

function qodoKickPosted(comments) {
  return comments.some((c) => kickAuthored(c, '/review'));
}

function chainKickPosted(comments) {
  return coderabbitKickPosted(comments) && qodoKickPosted(comments);
}

function isBotOpenedPr(pr) {
  if (BOT_PR_AUTHORS.has(pr.user?.login)) return true;
  return pr.user?.type === 'Bot';
}

async function kickReviewChain(github, owner, repo, prNumber, core, preFetchedComments = null) {
  const comments = preFetchedComments || await listAllComments(github, owner, repo, prNumber);
  const needCoderabbit = !coderabbitKickPosted(comments);
  const needQodo = !qodoKickPosted(comments);

  if (!needCoderabbit && !needQodo) {
    core?.info?.(`Review chain already kicked on PR #${prNumber}`);
    return { kicked: false, reason: 'already_kicked' };
  }

  if (needCoderabbit) {
    await github.rest.issues.createComment({
      owner,
      repo,
      issue_number: prNumber,
      body: '@coderabbitai review',
    });
  }
  if (needQodo) {
    await github.rest.issues.createComment({
      owner,
      repo,
      issue_number: prNumber,
      body: '/review',
    });
  }
  core?.info?.(`Kicked review chain for PR #${prNumber} (coderabbit=${needCoderabbit}, qodo=${needQodo})`);
  return { kicked: true, coderabbit: needCoderabbit, qodo: needQodo };
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
  return (
    prs.find(
      (p) => (p.head?.ref || '').startsWith(prefix) && isBotOpenedPr(p)
    ) || null
  );
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
  } else if (typeof github.paginate === 'function') {
    prs = await github.paginate(github.rest.pulls.list, {
      owner,
      repo,
      state: 'open',
      per_page: 100,
    });
  } else {
    const { data } = await github.rest.pulls.list({ owner, repo, state: 'open', per_page: 100 });
    prs = data;
  }

  const cutoff = Date.now() - minAgeMs;
  let recovered = 0;
  for (const pr of prs) {
    if (recovered >= maxRecover) break;
    if (!isBotOpenedPr(pr)) continue;
    if (!prNumber && new Date(pr.created_at).getTime() > cutoff) continue;
    const comments = await listAllComments(github, owner, repo, pr.number);
    if (chainKickPosted(comments)) continue;
    await kickReviewChain(github, owner, repo, pr.number, core, comments);
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
  coderabbitKickPosted,
  qodoKickPosted,
  isBotOpenedPr,
  kickReviewChain,
  findOpenPrForIssue,
  kickReviewChainForIssue,
  recoverStalledBotPrs,
};
