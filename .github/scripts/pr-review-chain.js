/**
 * PR review pipeline: CodeRabbit / Greptile (+ optional Qodo/Gemini) → Claude (FINAL).
 * Copilot step optional — set REVIEW_CHAIN_SKIP_COPILOT=1 or skipCopilot: true to bypass.
 * @see .github/workflows/auto-pr-comment.yml
 */

function isSkipCopilot(options = {}) {
  if (options.skipCopilot === true) return true;
  if (options.skipCopilot === false) return false;
  return process.env.REVIEW_CHAIN_SKIP_COPILOT === '1';
}

const COPILOT_TRIGGER_LOGINS = new Set(['MervinPraison', 'github-actions[bot]']);
const CLAUDE_TRIGGER_LOGINS = new Set(['MervinPraison', 'github-actions[bot]']);

const REQUIRED_PRIOR = ['coderabbit', 'greptile'];
const OPTIONAL_PRIOR = ['qodo', 'gemini'];
const OPTIONAL_PRIOR_WAIT_MS = 20 * 60 * 1000;

function loginOf(item) {
  return (item?.user?.login || '').toLowerCase();
}

function bodyOf(item) {
  return item?.body || '';
}

function hasCoderabbitSummary(comments) {
  return comments.some(
    (c) =>
      loginOf(c).includes('coderabbit') &&
      bodyOf(c).toLowerCase().includes('summarize by coderabbit')
  );
}

function hasGreptileReview(comments) {
  return comments.some((c) => {
    if (!loginOf(c).includes('greptile')) return false;
    const body = bodyOf(c);
    return body.includes('Greptile Summary') || body.includes('<h3>Greptile Summary</h3>') || body.length > 150;
  });
}

function hasQodoReview(comments, reviews = []) {
  if (comments.some((c) => loginOf(c).includes('qodo'))) return true;
  return reviews.some((r) => loginOf(r).includes('qodo'));
}

function hasGeminiReview(comments, reviews = []) {
  if (reviews.some((r) => loginOf(r).includes('gemini'))) return true;
  return comments.some((c) => {
    if (loginOf(c).includes('gemini')) return true;
    const body = bodyOf(c);
    return (
      body.includes('Review completed by Gemini CLI') ||
      body.includes('The fix is ready for review. Please test')
    );
  });
}

const PRIOR_CHECKS = {
  coderabbit: (comments) => hasCoderabbitSummary(comments),
  greptile: (comments) => hasGreptileReview(comments),
  qodo: (comments, reviews) => hasQodoReview(comments, reviews),
  gemini: (comments, reviews) => hasGeminiReview(comments, reviews),
};

function priorReviewerStatus(comments, reviews = []) {
  const status = {};
  for (const [id, check] of Object.entries(PRIOR_CHECKS)) {
    status[id] = check(comments, reviews);
  }
  return status;
}

function priorReviewersReady(comments, reviews = [], options = {}) {
  const waitMs = options.optionalWaitMs ?? OPTIONAL_PRIOR_WAIT_MS;
  const prCreatedAt = options.prCreatedAt || null;
  const status = priorReviewerStatus(comments, reviews);

  const missingRequired = REQUIRED_PRIOR.filter((id) => !status[id]);
  if (missingRequired.length) {
    return { ready: false, reason: `waiting for ${missingRequired.join(', ')}`, status };
  }

  const missingOptional = OPTIONAL_PRIOR.filter((id) => !status[id]);
  if (missingOptional.length && prCreatedAt) {
    const age = Date.now() - new Date(prCreatedAt).getTime();
    if (age < waitMs) {
      return {
        ready: false,
        reason: `waiting for optional ${missingOptional.join(', ')} (${Math.round((waitMs - age) / 60000)}m left)`,
        status,
      };
    }
  }

  return { ready: true, reason: '', status };
}

function copilotTriggerComment(comments) {
  return comments.find(
    (c) =>
      bodyOf(c).includes('@copilot') &&
      COPILOT_TRIGGER_LOGINS.has(c.user?.login) &&
      !bodyOf(c).toLowerCase().includes('@claude')
  );
}

function copilotTriggered(comments) {
  return Boolean(copilotTriggerComment(comments));
}

function copilotReviewReady(comments, reviews = []) {
  const trigger = copilotTriggerComment(comments);
  if (!trigger) {
    return { ready: false, reason: 'copilot not triggered yet' };
  }
  const triggerTime = new Date(trigger.created_at).getTime();
  const copilotComment = comments.some((c) => {
    if (c === trigger) return false;
    if (new Date(c.created_at).getTime() < triggerTime) return false;
    const login = loginOf(c);
    return (
      login.includes('copilot') ||
      c.user?.login === 'Copilot' ||
      c.user?.login === 'copilot-swe-agent'
    );
  });
  const copilotReview = reviews.some((r) => {
    if (new Date(r.submitted_at).getTime() < triggerTime) return false;
    return loginOf(r).includes('copilot');
  });
  if (copilotComment || copilotReview) {
    return { ready: true, reason: '' };
  }
  return { ready: false, reason: 'awaiting copilot review' };
}

function isFinalClaudeTriggerComment(c) {
  const body = bodyOf(c).toLowerCase();
  if (!CLAUDE_TRIGGER_LOGINS.has(c.user?.login)) return false;
  if (!body.includes('@claude')) return false;
  if (body.includes('merge conflict')) return false;
  return body.includes('final architecture reviewer') || body.includes('lead engineer');
}

function claudeFinalAlreadyTriggered(comments) {
  return comments.some(isFinalClaudeTriggerComment);
}

function claudeFinalReady(comments, reviews = [], options = {}) {
  if (claudeFinalAlreadyTriggered(comments)) {
    return { ready: false, reason: 'claude FINAL already triggered', already: true };
  }
  const prior = priorReviewersReady(comments, reviews, options);
  if (!prior.ready) {
    return { ready: false, reason: prior.reason };
  }
  if (isSkipCopilot(options)) {
    return { ready: true, reason: 'copilot skipped', copilotSkipped: true };
  }
  const copilot = copilotReviewReady(comments, reviews);
  if (copilot.ready) {
    return { ready: true, reason: '' };
  }
  if (options.allowCopilotTimeout && copilotTriggered(comments)) {
    return { ready: true, reason: 'copilot timeout fallback', copilotSkipped: true };
  }
  return { ready: false, reason: copilot.reason };
}

/** Post @copilot when prior reviewers are ready, then @claude FINAL when Copilot done (or timeout). */
async function advanceReviewChain(github, owner, repo, prNumber, finalBody, core, options = {}) {
  const { data: pr } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
  const chainOpts = {
    prCreatedAt: pr.created_at,
    optionalWaitMs: options.optionalWaitMs ?? 0,
  };
  const copilot = options.skipCopilot
    ? { triggered: false, reason: 'skipped' }
    : await maybeTriggerCopilot(github, owner, repo, prNumber, core, chainOpts);
  const claude = await maybeTriggerClaudeFinal(
    github, owner, repo, prNumber, finalBody, core,
    { ...options, ...chainOpts }
  );
  return { copilot, claude };
}

async function maybeTriggerClaudeFinal(github, owner, repo, prNumber, finalBody, core, options = {}) {
  const { data: pr } = await github.rest.pulls.get({ owner, repo, pull_number: prNumber });
  const { comments, reviews } = await listCommentsAndReviews(github, owner, repo, prNumber);
  const gate = claudeFinalReady(comments, reviews, {
    prCreatedAt: pr.created_at,
    optionalWaitMs: options.optionalWaitMs,
    allowCopilotTimeout: options.allowCopilotTimeout !== false,
  });
  if (!gate.ready) {
    core?.info?.(`PR #${prNumber}: skip Claude FINAL — ${gate.reason}`);
    return { posted: false, reason: gate.reason };
  }
  await github.rest.issues.createComment({
    owner,
    repo,
    issue_number: prNumber,
    body: finalBody,
  });
  const note = gate.copilotSkipped ? ' (Copilot timeout fallback)' : '';
  core?.info?.(`Posted Claude FINAL on PR #${prNumber}${note}`);
  return { posted: true, reason: '' };
}

const COPILOT_REVIEW_BODY =
  '@copilot Do a thorough review of this PR. Read ALL existing reviewer comments above from Qodo, CodeRabbit, Gemini, and Greptile first — incorporate their findings.\n\nReview areas:\n1. **Bloat check**: Are changes minimal and focused? Any unnecessary code or scope creep?\n2. **Security**: Any hardcoded secrets, unsafe eval/exec, missing input validation?\n3. **Performance**: Any module-level heavy imports? Hot-path regressions?\n4. **Tests**: Are tests included? Do they cover the changes adequately?\n5. **Backward compat**: Any public API changes without deprecation?\n6. **Code quality**: DRY violations, naming conventions, error handling?\n7. **Address reviewer feedback**: If Qodo, CodeRabbit, Gemini, or Greptile flagged valid issues, include them in your review\n8. Suggest specific improvements with code examples where possible';

async function listCommentsAndReviews(github, owner, repo, prNumber) {
  let comments;
  if (typeof github.paginate === 'function') {
    comments = await github.paginate(github.rest.issues.listComments, {
      owner,
      repo,
      issue_number: prNumber,
      per_page: 100,
    });
  } else {
    const { data } = await github.rest.issues.listComments({
      owner,
      repo,
      issue_number: prNumber,
      per_page: 100,
    });
    comments = data;
  }
  const { data: reviews } = await github.rest.pulls.listReviews({
    owner,
    repo,
    pull_number: prNumber,
    per_page: 100,
  });
  return { comments, reviews };
}

async function maybeTriggerCopilot(github, owner, repo, prNumber, core, options = {}) {
  const { comments, reviews } = await listCommentsAndReviews(github, owner, repo, prNumber);
  if (copilotTriggered(comments)) {
    core?.info?.(`Copilot already triggered on PR #${prNumber}`);
    return { triggered: false, reason: 'already_triggered' };
  }
  const prior = priorReviewersReady(comments, reviews, options);
  if (!prior.ready) {
    core?.info?.(`PR #${prNumber}: not ready for Copilot — ${prior.reason}`);
    return { triggered: false, reason: prior.reason };
  }
  await github.rest.issues.createComment({
    owner,
    repo,
    issue_number: prNumber,
    body: COPILOT_REVIEW_BODY,
  });
  core?.info?.(`Posted @copilot on PR #${prNumber} after prior reviewers`);
  return { triggered: true };
}

async function pollCopilotResponse(github, owner, repo, prNumber, options = {}) {
  const maxAttempts = options.maxAttempts ?? 20;
  const delayMs = options.delayMs ?? 30000;
  for (let i = 0; i < maxAttempts; i += 1) {
    const { comments, reviews } = await listCommentsAndReviews(github, owner, repo, prNumber);
    const copilot = copilotReviewReady(comments, reviews);
    if (copilot.ready) {
      return { ready: true, reason: '' };
    }
    if (i < maxAttempts - 1) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  return { ready: false, reason: 'copilot timeout' };
}

module.exports = {
  isSkipCopilot,
  REQUIRED_PRIOR,
  OPTIONAL_PRIOR,
  COPILOT_REVIEW_BODY,
  priorReviewerStatus,
  priorReviewersReady,
  copilotTriggered,
  copilotReviewReady,
  claudeFinalReady,
  claudeFinalAlreadyTriggered,
  isFinalClaudeTriggerComment,
  maybeTriggerCopilot,
  maybeTriggerClaudeFinal,
  advanceReviewChain,
  pollCopilotResponse,
  hasGeminiReview,
  listCommentsAndReviews,
};
