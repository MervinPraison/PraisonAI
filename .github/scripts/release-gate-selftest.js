const assert = require('assert');
const rg = require('./release-gate.js');

assert.strictEqual(rg.bumpPatch('1.6.80'), '1.6.81');
assert.strictEqual(rg.bumpPatch('4.6.80'), '4.6.81');
assert.strictEqual(rg.bumpPatch('0.0.2'), '0.0.3');

const versions = rg.readVersionsFromTree();
assert.ok(versions.currentAgents);
assert.ok(versions.currentCode);
assert.ok(versions.currentWrapper);
assert.ok(versions.targetCode);
assert.ok(rg.PACKAGE_PATHS.includes('src/praisonai-code'));

(async () => {
  assert.strictEqual(await rg.pypiVersionExists('praisonaiagents', '0.0.0'), false);
  console.log('ok: bumpPatch');
  console.log('ok: readVersionsFromTree');
  console.log('ok: pypiVersionExists missing version');
})();
