#!/usr/bin/env node
const chain = require('./pr-review-chain.js');

let failed = 0;
function assert(name, cond) {
  if (!cond) {
    console.error('FAIL:', name);
    failed++;
  } else {
    console.log('ok:', name);
  }
}

const coderabbit = {
  user: { login: 'coderabbitai[bot]' },
  body: '<!-- summarize by coderabbit.ai --> summary',
  created_at: '2026-07-02T07:16:00Z',
};
const greptile = {
  user: { login: 'greptile-apps[bot]' },
  body: '<h3>Greptile Summary</h3><p>Looks good</p>',
  created_at: '2026-07-02T07:19:00Z',
};
const copilotKick = {
  user: { login: 'MervinPraison' },
  body: '@copilot Do a thorough review',
  created_at: '2026-07-02T07:20:00Z',
};
const copilotReply = {
  user: { login: 'copilot-swe-agent' },
  body: 'Copilot review here',
  created_at: '2026-07-02T07:22:00Z',
};

assert('prior not ready without greptile', !chain.priorReviewersReady([coderabbit]).ready);
assert('prior ready with coderabbit + greptile', chain.priorReviewersReady([coderabbit, greptile]).ready);
assert('copilot not ready before trigger', !chain.copilotReviewReady([coderabbit, greptile]).ready);
assert(
  'copilot ready after reply',
  chain.copilotReviewReady([coderabbit, greptile, copilotKick, copilotReply]).ready
);
assert(
  'claude not ready before copilot',
  !chain.claudeFinalReady([coderabbit, greptile]).ready
);
assert(
  'claude ready after full chain',
  chain.claudeFinalReady([coderabbit, greptile, copilotKick, copilotReply]).ready
);
assert(
  'claude timeout fallback when copilot triggered but silent',
  chain.claudeFinalReady([coderabbit, greptile, copilotKick], [], { allowCopilotTimeout: true }).ready
);
assert(
  'no timeout fallback without copilot trigger',
  !chain.claudeFinalReady([coderabbit, greptile], [], { allowCopilotTimeout: true }).ready
);
assert(
  'skipCopilot proceeds after prior reviewers',
  chain.claudeFinalReady([coderabbit, greptile], [], { skipCopilot: true }).ready
);
const prev = process.env.REVIEW_CHAIN_SKIP_COPILOT;
process.env.REVIEW_CHAIN_SKIP_COPILOT = '1';
assert(
  'REVIEW_CHAIN_SKIP_COPILOT env skips copilot',
  chain.claudeFinalReady([coderabbit, greptile], [], {}).ready
);
process.env.REVIEW_CHAIN_SKIP_COPILOT = prev;

const geminiReview = {
  user: { login: 'gemini-code-assist[bot]' },
  body: '## Code Review\n\nThis pull request decomposes the large main.py file',
  submitted_at: '2026-07-03T08:08:00Z',
};
assert(
  'gemini pull review counts as prior reviewer',
  chain.hasGeminiReview([], [geminiReview])
);
assert(
  'prior ready with gemini review only (no gemini comment)',
  chain.priorReviewersReady([coderabbit, greptile], [geminiReview], { optionalWaitMs: 0 }).ready
);

const oldPr = new Date(Date.now() - 31 * 60 * 1000).toISOString();
assert(
  'prior not ready without coderabbit before timeout',
  !chain.priorReviewersReady([greptile], [], { prCreatedAt: new Date().toISOString(), requiredWaitMs: 30 * 60 * 1000 }).ready
);
assert(
  'prior timeout when coderabbit silent after 30m',
  chain.priorReviewersReady([greptile], [], { prCreatedAt: oldPr, requiredWaitMs: 30 * 60 * 1000 }).ready
);
assert(
  'claude FINAL timeout when required reviewer silent and no prior FINAL',
  chain.claudeFinalReady([greptile], [], { prCreatedAt: oldPr, skipCopilot: true, requiredWaitMs: 30 * 60 * 1000 }).ready
);
const finalClaude = {
  user: { login: 'github-actions[bot]' },
  body: '@claude You are the FINAL architecture reviewer for this PR.',
  created_at: '2026-07-02T07:25:00Z',
};
assert(
  'claude FINAL not re-posted when already triggered',
  !chain.claudeFinalReady([greptile, finalClaude], [], { prCreatedAt: oldPr, skipCopilot: true, requiredWaitMs: 0 }).ready
);

process.exit(failed ? 1 : 0);
