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

const noonUtc = new Date('2026-07-08T12:00:00Z');
const dayStart = rg.utcDayStart(noonUtc);
assert.strictEqual(dayStart.toISOString(), '2026-07-08T00:00:00.000Z');

(async () => {
  assert.strictEqual(await rg.pypiVersionExists('praisonaiagents', '0.0.0'), false);

  const mockGithub = {
    rest: {
      actions: {
        listWorkflowRuns: async () => ({
          data: {
            workflow_runs: [
              {
                conclusion: 'success',
                created_at: '2026-07-08T09:00:00Z',
                status: 'completed',
              },
            ],
          },
        }),
      },
    },
  };
  assert.strictEqual(
    await rg.hasSuccessfulReleaseToday(mockGithub, 'o', 'r', noonUtc),
    true
  );

  const result = await rg.evaluateReleasePreflight(
    mockGithub, 'o', 'r',
    { headSha: 'abc', isCiTrigger: false, bump: 'patch', now: noonUtc },
    null
  );
  assert.ok(result.reasons.some((r) => r.includes('already released today')));

  console.log('ok: bumpPatch');
  console.log('ok: readVersionsFromTree');
  console.log('ok: pypiVersionExists missing version');
  console.log('ok: utcDayStart');
  console.log('ok: hasSuccessfulReleaseToday');
  console.log('ok: daily dedupe blocks second release');
})();
