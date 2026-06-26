#!/usr/bin/env node
const chain = require('./bot-pr-review-chain.js');

let failed = 0;
function assert(name, cond) {
  if (!cond) {
    console.error('FAIL:', name);
    failed++;
  } else {
    console.log('ok:', name);
  }
}

assert('chainKickPosted requires both markers', chain.chainKickPosted([
  { user: { login: 'MervinPraison' }, body: '@coderabbitai review' },
  { user: { login: 'MervinPraison' }, body: '/review' },
]));
assert('chainKickPosted false with only coderabbit', !chain.chainKickPosted([
  { user: { login: 'MervinPraison' }, body: '@coderabbitai review' },
]));
assert('coderabbitKickPosted detects coderabbit', chain.coderabbitKickPosted([
  { user: { login: 'MervinPraison' }, body: '@coderabbitai review' },
]));
assert('qodoKickPosted detects qodo', chain.qodoKickPosted([
  { user: { login: 'github-actions[bot]' }, body: '/review' },
]));
assert('ignores coderabbit bot comment', !chain.coderabbitKickPosted([
  { user: { login: 'coderabbitai[bot]' }, body: '@coderabbitai review' },
]));
assert('bot PR author match', chain.isBotOpenedPr({ user: { login: 'praisonai-triage-agent[bot]' } }));
assert('generic bot type match', chain.isBotOpenedPr({ user: { login: 'my-bot', type: 'Bot' } }));
assert('human author excluded', !chain.isBotOpenedPr({ user: { login: 'MervinPraison', type: 'User' } }));

process.exit(failed ? 1 : 0);
