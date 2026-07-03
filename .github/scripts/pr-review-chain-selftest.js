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

assert(
  'hasGeminiReview tolerates undefined reviews',
  chain.hasGeminiReview([]) === false
);

async function advanceReviewChainOrderTest() {
  const now = '2026-07-03T09:00:00Z';
  const posted = [];
  let state = [coderabbit, greptile];
  const github = {
    rest: {
      pulls: {
        get: async () => ({ data: { created_at: '2026-07-03T07:00:00Z' } }),
        listReviews: async () => ({ data: [geminiReview] }),
      },
      issues: {
        listComments: async () => ({ data: state }),
        createComment: async ({ body }) => {
          posted.push(body);
          if (body.includes('@copilot')) {
            state = state.concat({
              user: { login: 'MervinPraison' },
              body,
              created_at: now,
            });
          }
        },
      },
    },
  };
  const result = await chain.advanceReviewChain(
    github, 'o', 'r', 1, '@claude FINAL architecture reviewer', null,
    { allowCopilotTimeout: true, optionalWaitMs: 0 }
  );
  assert('advanceReviewChain triggers copilot', result.copilot.triggered === true);
  assert(
    'advanceReviewChain defers claude when copilot just triggered',
    result.claude.posted === false
  );
  assert(
    'advanceReviewChain posts only @copilot in same pass',
    posted.length === 1 && posted[0].includes('@copilot')
  );
}

advanceReviewChainOrderTest()
  .then(() => process.exit(failed ? 1 : 0))
  .catch((err) => {
    console.error('FAIL: advanceReviewChain order test threw', err);
    process.exit(1);
  });
