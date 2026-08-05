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
// Every released package must make the gate's path-change check eligible.
for (const p of [
  'src/praisonai', 'src/praisonai-agents', 'src/praisonai-code',
  'src/praisonai-bot', 'src/praisonai-train', 'src/praisonai-browser',
  'src/praisonai-mcp', 'src/praisonai-sandbox', 'src/praisonai-deploy',
]) {
  assert.ok(rg.PACKAGE_PATHS.includes(p), `PACKAGE_PATHS missing ${p}`);
}

const noonUtc = new Date('2026-07-08T12:00:00Z');
const dayStart = rg.utcDayStart(noonUtc);
assert.strictEqual(dayStart.toISOString(), '2026-07-08T00:00:00.000Z');

function mockGithub({ runs = [], releases = [] } = {}) {
  return {
    rest: {
      actions: {
        listWorkflowRuns: async () => ({ data: { workflow_runs: runs } }),
      },
      repos: {
        listReleases: async () => ({ data: releases }),
      },
    },
  };
}

(async () => {
  assert.strictEqual(await rg.pypiVersionExists('praisonaiagents', '0.0.0'), false);

  assert.strictEqual(rg.PATCH_RELEASE_INTERVAL_DAYS, 3);

  // Dedupe is release-based: a v* release inside the window blocks…
  const recentRelease = mockGithub({
    releases: [{ tag_name: 'v4.6.159', published_at: '2026-07-08T09:00:00Z' }],
  });
  assert.strictEqual(
    await rg.hasSuccessfulReleaseWithinDays(recentRelease, 'o', 'r', noonUtc),
    true
  );

  const result = await rg.evaluateReleasePreflight(
    recentRelease, 'o', 'r',
    { headSha: 'abc', isCiTrigger: false, bump: 'patch', now: noonUtc },
    null
  );
  assert.ok(result.reasons.some((r) => r.includes('every 3 days')));

  // …an old release does not…
  const oldRelease = mockGithub({
    releases: [{ tag_name: 'v4.6.150', published_at: '2026-07-04T09:00:00Z' }],
  });
  assert.strictEqual(
    await rg.hasSuccessfulReleaseWithinDays(oldRelease, 'o', 'r', noonUtc),
    false
  );

  // …and a dry-run "success" (workflow run, no release) does not consume the
  // window: only real releases count.
  const dryRunOnly = mockGithub({
    runs: [{ conclusion: 'success', created_at: '2026-07-08T09:00:00Z', status: 'completed' }],
    releases: [],
  });
  assert.strictEqual(
    await rg.hasSuccessfulReleaseWithinDays(dryRunOnly, 'o', 'r', noonUtc),
    false
  );

  // Active-run blocking: fresh waiting run blocks…
  const freshWaiting = mockGithub({
    runs: [{ status: 'waiting', conclusion: null, created_at: '2026-07-08T11:00:00Z', html_url: 'x' }],
  });
  assert.strictEqual(
    await rg.hasActiveReleaseRun(freshWaiting, 'o', 'r', noonUtc, null),
    true
  );

  // …a waiting run stuck longer than STALE_WAITING_HOURS no longer blocks…
  const staleWaiting = mockGithub({
    runs: [{ status: 'waiting', conclusion: null, created_at: '2026-07-08T01:00:00Z', html_url: 'x' }],
  });
  const warnings = [];
  const fakeCore = { warning: (m) => warnings.push(m), info: () => {} };
  assert.strictEqual(rg.STALE_WAITING_HOURS, 6);
  assert.strictEqual(
    await rg.hasActiveReleaseRun(staleWaiting, 'o', 'r', noonUtc, fakeCore),
    false
  );
  assert.ok(warnings.length === 1 && warnings[0].includes('approve or cancel'));

  // …but an in_progress run always blocks regardless of age.
  const oldInProgress = mockGithub({
    runs: [{ status: 'in_progress', conclusion: null, created_at: '2026-07-07T01:00:00Z', html_url: 'x' }],
  });
  assert.strictEqual(
    await rg.hasActiveReleaseRun(oldInProgress, 'o', 'r', noonUtc, null),
    true
  );

  console.log('ok: bumpPatch');
  console.log('ok: readVersionsFromTree');
  console.log('ok: PACKAGE_PATHS covers all 9 released packages');
  console.log('ok: pypiVersionExists missing version');
  console.log('ok: utcDayStart');
  console.log('ok: release-based dedupe (recent blocks, old does not)');
  console.log('ok: dry-run success does not consume the release window');
  console.log('ok: 3-day dedupe blocks second release');
  console.log('ok: fresh waiting run blocks; stale waiting run ignored with warning');
  console.log('ok: in_progress always blocks');
})();
