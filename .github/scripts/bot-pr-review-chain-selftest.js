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

assert('detects kick from MervinPraison', chain.chainKickPosted([
  { user: { login: 'MervinPraison' }, body: '@coderabbitai review' },
]));
assert('ignores coderabbit bot comment', !chain.chainKickPosted([
  { user: { login: 'coderabbitai[bot]' }, body: '@coderabbitai review' },
]));
assert('bot PR author match', chain.isBotOpenedPr({ user: { login: 'praisonai-triage-agent[bot]' } }));
assert('generic bot type match', chain.isBotOpenedPr({ user: { login: 'my-bot', type: 'Bot' } }));
assert('human author excluded', !chain.isBotOpenedPr({ user: { login: 'MervinPraison', type: 'User' } }));

process.exit(failed ? 1 : 0);
