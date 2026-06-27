const assert = require('assert');
const rg = require('./release-gate.js');

assert.strictEqual(rg.bumpPatch('1.6.80'), '1.6.81');
assert.strictEqual(rg.bumpPatch('4.6.80'), '4.6.81');

(async () => {
  assert.strictEqual(await rg.pypiVersionExists('praisonaiagents', '0.0.0'), false);
  console.log('ok: bumpPatch');
  console.log('ok: pypiVersionExists missing version');
})();
