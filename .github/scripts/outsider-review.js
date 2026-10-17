/**
 * Outsider provenance and the extra security layer for outsider-origin PRs.
 *
 * Claude keeps reviewing and implementing work from outsiders. A PR counts as
 * outsider-origin when anything it was built from came from someone without
 * write access: a fork head, a non-writer author, or a non-writer's issue or
 * comment that Claude read while writing or reviewing it. Such a PR may still
 * be auto-merged, but only after an independent read-only security review
 * passes on its HEAD, and never when it touches the build, dependency or CI
 * surface (those need a maintainer).
 *
 * The verdict is a commit status set by the merge gate's own GITHUB_TOKEN
 * (github-actions[bot]) from the security run's output. Every Claude run posts
 * comments as the App bot, so a comment saying "SECURITY_REVIEW: PASS" could be
 * forged by any manipulated Claude run; the status cannot, because no Claude
 * run is ever given that token.
 *
 * @see .github/prompts/outsider-security-review.md
 * @see .github/workflows/claude-merge-gate.yml (claude-assess)
 */

const WRITE_PERMISSIONS = new Set(['admin', 'maintain', 'write']);
// Automation never counts as an outsider: review bots and our own fleet.
const TRUSTED_AUTOMATION = new Set(['Copilot']);
const SECURITY_STATUS_CONTEXT = 'security/outsider-review';
const SECURITY_STATUS_CREATOR = 'github-actions[bot]';
const SECURITY_REVIEW_RE = /^\s*SECURITY_REVIEW:\s*(PASS|FAIL)\b/;
const MAINTAINER_SECURITY_LABEL = 'maintainer-security-reviewed';
const OUTSIDER_ORIGIN_LABEL = 'origin/outsider';

// Build, dependency, CI and install-time surface. Code here runs on developer
// machines, in CI with secrets, or at install time, so an outsider-origin
// change to it always needs a maintainer.
const OUTSIDER_SENSITIVE_PATTERNS = [
  /^\.github\//,
  /(^|\/)(pyproject\.toml|setup\.py|setup\.cfg|MANIFEST\.in|requirements[^/]*\.txt|Pipfile(\.lock)?)$/,
  /(^|\/)(uv|poetry)\.lock$/,
  /(^|\/)(package(-lock)?\.json|yarn\.lock|pnpm-lock\.yaml|\.npmrc)$/,
  /(^|\/)(Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|Makefile|\.pre-commit-config\.yaml)$/,
  /(^|\/)conftest\.py$/,
  /\.pth$/,
  /\.(sh|bash|ps1|bat|cmd)$/,
];

// Shown to the security reviewer, which must address each one. Not blocking
// on their own: the SDK legitimately uses subprocess, HTTP and env vars.
const RISK_PATTERNS = [
  ['code execution', /\b(eval|exec|compile)\s*\(|os\.system\s*\(|subprocess\.|shell\s*=\s*True|child_process|new Function\s*\(/],
  ['unsafe deserialization', /pickle\.loads?|marshal\.loads|yaml\.load\s*\((?![^)]*SafeLoader)|dill\.loads?/],
  ['dynamic import', /__import__\s*\(|importlib\.import_module\s*\(|\brequire\s*\(\s*[^'"`]/],
  ['network call', /https?:\/\/(?!github\.com\/MervinPraison|docs\.praison\.ai|localhost|127\.0\.0\.1)[^\s'"`)]+|requests\.(get|post|put)|urllib\.request|httpx\.|aiohttp\.|socket\.|fetch\s*\(/],
  ['secret or env access', /os\.environ|getenv\s*\(|process\.env|\.ssh\/|\.aws\/|credentials|_TOKEN|API_KEY|SECRET/],
  ['encoded blob', /base64\.(b64)?decode|atob\s*\(|bytes\.fromhex|\\x[0-9a-f]{2}(\\x[0-9a-f]{2}){7,}|[A-Za-z0-9+/]{120,}={0,2}/],
  ['hidden characters', /[\u202a-\u202e\u2066-\u2069\u200b-\u200f\u2060\ufeff]/],
  ['instructions to AI', /ignore (all |any )?(previous|prior|above) instructions|you are (now )?(an?|the) (ai|assistant|reviewer)|SECURITY_REVIEW:|MERGE_GATE_VERDICT:|approve (this|the) (pr|pull request)/i],
  ['security control touched', /\b(verify\s*=\s*False|allow_dangerous|skip_(auth|approval|verify)|bypass|disable_(auth|ssl|sandbox|approval)|chmod\s+777)\b/i],
];

function isAutomation(login) {
  return !login || login.endsWith('[bot]') || TRUSTED_AUTOMATION.has(login);
}

/** Issue the PR was built from: claude/issue-N-* branch, else "Fixes #N" in the body. */
function sourceIssueNumber(pr) {
  const branch = /^claude\/issue-(\d+)-/.exec(pr?.head?.ref || '');
  if (branch) return Number(branch[1]);
  const body = /\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s+#(\d+)\b/i.exec(pr?.body || '');
  return body ? Number(body[1]) : null;
}

function makePermissionLookup(github, owner, repo) {
  const cache = new Map();
  return async (login) => {
    if (isAutomation(login)) return true;
    if (!cache.has(login)) {
      cache.set(
        login,
        github.rest.repos
          .getCollaboratorPermissionLevel({ owner, repo, username: login })
          .then(({ data }) => WRITE_PERMISSIONS.has(data.permission), () => false)
      );
    }
    return cache.get(login);
  };
}

/**
 * Why a PR is outsider-origin ([] when it is not). `comments` are the PR's
 * issue comments; review comments and reviews are fetched here.
 */
async function outsiderOriginReasons(github, owner, repo, pr, comments = []) {
  const reasons = [];
  const isWriter = makePermissionLookup(github, owner, repo);

  if (pr.head?.repo?.full_name !== `${owner}/${repo}`) reasons.push('fork PR');
  if (!(await isWriter(pr.user?.login))) reasons.push(`author @${pr.user?.login} has no write access`);

  const issueNumber = sourceIssueNumber(pr);
  if (issueNumber) {
    reasons.push(...(await issueReasons(github, owner, repo, issueNumber, isWriter, 'source issue')));
  }

  const [reviewComments, reviews] = await Promise.all([
    github.paginate(github.rest.pulls.listReviewComments, { owner, repo, pull_number: pr.number, per_page: 100 }),
    github.paginate(github.rest.pulls.listReviews, { owner, repo, pull_number: pr.number, per_page: 100 }),
  ]);
  const prAuthors = [...comments, ...reviewComments, ...reviews].map((c) => c.user?.login);
  const prOutsiders = await outsiderLogins(prAuthors, isWriter);
  if (prOutsiders.length) reasons.push(`PR has comments from ${prOutsiders.map((l) => '@' + l).join(', ')}`);

  return reasons;
}

/** Outsider authorship of an issue and its comments ([] for a PR number). */
async function issueReasons(github, owner, repo, issueNumber, isWriter, label = 'issue') {
  const reasons = [];
  try {
    const { data: issue } = await github.rest.issues.get({ owner, repo, issue_number: issueNumber });
    if (issue.pull_request) return reasons;
    if (!(await isWriter(issue.user?.login))) {
      reasons.push(`${label} #${issueNumber} opened by @${issue.user?.login} (no write access)`);
    }
    const comments = await github.paginate(github.rest.issues.listComments, {
      owner, repo, issue_number: issueNumber, per_page: 100,
    });
    const outsiders = await outsiderLogins(comments.map((c) => c.user?.login), isWriter);
    if (outsiders.length) reasons.push(`${label} #${issueNumber} has comments from ${outsiders.map((l) => '@' + l).join(', ')}`);
  } catch (err) {
    if (err.status !== 404) throw err;
  }
  return reasons;
}

/** Why an issue Claude is asked to work on is outsider-influenced ([] when not). */
async function outsiderIssueReasons(github, owner, repo, issueNumber) {
  return issueReasons(github, owner, repo, issueNumber, makePermissionLookup(github, owner, repo));
}

async function outsiderLogins(logins, isWriter) {
  const unique = [...new Set(logins.filter((l) => l && !isAutomation(l)))];
  const writer = await Promise.all(unique.map((l) => isWriter(l)));
  return unique.filter((_, i) => !writer[i]);
}

function outsiderSensitivePaths(files) {
  return files.map((f) => f.filename).filter((name) => OUTSIDER_SENSITIVE_PATTERNS.some((p) => p.test(name)));
}

/** Deterministic red flags in added lines, for the security reviewer. */
function riskFlags(files) {
  const flags = [];
  for (const f of files) {
    const added = (f.patch || '').split('\n').filter((l) => l.startsWith('+') && !l.startsWith('+++'));
    for (const [category, pattern] of RISK_PATTERNS) {
      const hit = added.find((l) => pattern.test(l));
      if (hit) flags.push({ file: f.filename, category, line: hit.slice(1).trim().slice(0, 160) });
    }
    if (!f.patch && f.status !== 'removed') flags.push({ file: f.filename, category: 'binary or very large file', line: '' });
  }
  return flags;
}

function formatRiskFlags(flags) {
  if (!flags.length) return 'none';
  return flags.map((f) => `- ${f.file}: ${f.category}${f.line ? ` — \`${f.line.replace(/`/g, "'")}\`` : ''}`).join('\n');
}

/**
 * Verdict from the security run's stream-json output: the first line of the
 * comment it posted through mcp__github__add_issue_comment. Any FAIL wins;
 * no verdict at all is null (treated as not passed).
 */
function securityVerdictFromOutput(jsonl) {
  const verdicts = [];
  for (const line of (jsonl || '').split('\n')) {
    let msg;
    try { msg = JSON.parse(line); } catch { continue; }
    for (const item of msg?.message?.content || []) {
      if (item?.type !== 'tool_use' || !/add_issue_comment$/.test(item.name || '')) continue;
      const m = SECURITY_REVIEW_RE.exec(String(item.input?.body || ''));
      if (m) verdicts.push(m[1]);
    }
  }
  if (verdicts.includes('FAIL')) return 'FAIL';
  return verdicts.includes('PASS') ? 'PASS' : null;
}

/** Latest outsider security status on a commit, trusted only from the gate's token. */
function findSecurityReviewStatus(statuses) {
  const ours = (statuses || [])
    .filter((st) => st.context === SECURITY_STATUS_CONTEXT && st.creator?.login === SECURITY_STATUS_CREATOR)
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  if (!ours.length) return null;
  return ours[0].state === 'success' ? 'PASS' : 'FAIL';
}

/**
 * Merge-gate reasons for an outsider-origin PR. The security-review
 * requirement applies only on the merge step: the review itself runs inside
 * the assess job, so it must not keep the PR from becoming a candidate.
 */
function outsiderGateReasons({ origin, files, securityStatus = null, labels = [], forMergeStep = false }) {
  if (!origin.length) return [];
  if (labels.includes(MAINTAINER_SECURITY_LABEL)) return [];
  const reasons = [];
  const sensitive = outsiderSensitivePaths(files);
  if (sensitive.length) {
    reasons.push(
      `outsider-origin PR touches build/CI/dependency surface (${sensitive.slice(0, 3).join(', ')}) — maintainer review required (label ${MAINTAINER_SECURITY_LABEL})`
    );
  }
  if (forMergeStep && securityStatus !== 'PASS') {
    reasons.push(`outsider-origin PR needs a passing ${SECURITY_STATUS_CONTEXT} status on HEAD (got ${securityStatus || 'none'})`);
  }
  return reasons;
}

module.exports = {
  MAINTAINER_SECURITY_LABEL,
  OUTSIDER_ORIGIN_LABEL,
  SECURITY_STATUS_CONTEXT,
  sourceIssueNumber,
  outsiderOriginReasons,
  outsiderIssueReasons,
  outsiderSensitivePaths,
  riskFlags,
  formatRiskFlags,
  securityVerdictFromOutput,
  findSecurityReviewStatus,
  outsiderGateReasons,
};
