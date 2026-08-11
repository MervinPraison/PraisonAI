/**
 * Release gate preflight — path changes, CI SHA, dedupe, PyPI version checks.
 */

const https = require('https');

/** Every directory whose changes should make a release eligible — all nine
 * published packages (mirrors the skip_* inputs in pypi-release.yml). */
const PACKAGE_PATHS = [
  'src/praisonai',
  'src/praisonai-agents',
  'src/praisonai-code',
  'src/praisonai-bot',
  'src/praisonai-train',
  'src/praisonai-browser',
  'src/praisonai-mcp',
  'src/praisonai-sandbox',
  'src/praisonai-deploy',
];
/** Minimum days between successful patch auto-releases. */
const PATCH_RELEASE_INTERVAL_DAYS = 3;
const ACTIVE_RELEASE_STATUSES = new Set([
  'queued', 'in_progress', 'waiting', 'pending', 'requested',
]);
/** A run stuck in `waiting` (environment approval) longer than this no longer
 * blocks the gate. GitHub only auto-fails unapproved deployments after 30
 * days, so without a cutoff one forgotten manual dispatch stalls all
 * auto-releases for up to a month. The run is warned about, never cancelled —
 * if later approved, the pypi-release concurrency group serializes it and its
 * pypi_exists checks no-op anything already published. */
const STALE_WAITING_HOURS = 6;

function bumpPatch(version) {
  const parts = version.split('.');
  if (parts.length !== 3) throw new Error(`Invalid version: ${version}`);
  return `${parts[0]}.${parts[1]}.${Number(parts[2]) + 1}`;
}

function readVersionsFromTree(root = '.') {
  const fs = require('fs');
  const path = require('path');
  const agentsToml = fs.readFileSync(
    path.join(root, 'src/praisonai-agents/pyproject.toml'), 'utf8'
  );
  const agentsMatch = agentsToml.match(/^version\s*=\s*"([^"]+)"/m);
  if (!agentsMatch) throw new Error('Could not read agents version');

  const codeToml = fs.readFileSync(
    path.join(root, 'src/praisonai-code/pyproject.toml'), 'utf8'
  );
  const codeMatch = codeToml.match(/^version\s*=\s*"([^"]+)"/m);
  if (!codeMatch) throw new Error('Could not read praisonai-code version');

  const wrapperPy = fs.readFileSync(
    path.join(root, 'src/praisonai/praisonai/version.py'), 'utf8'
  );
  const wrapperMatch = wrapperPy.match(/__version__ = "([^"]+)"/);
  if (!wrapperMatch) throw new Error('Could not read wrapper version');
  return {
    currentAgents: agentsMatch[1],
    currentCode: codeMatch[1],
    currentWrapper: wrapperMatch[1],
    targetAgents: bumpPatch(agentsMatch[1]),
    targetCode: bumpPatch(codeMatch[1]),
    targetWrapper: bumpPatch(wrapperMatch[1]),
  };
}

function pypiVersionExists(packageName, version) {
  return new Promise((resolve) => {
    const req = https.get(
      `https://pypi.org/pypi/${packageName}/${version}/json`,
      { timeout: 15000 },
      (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      }
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function hasActiveReleaseRun(github, owner, repo, now = new Date(), core = null) {
  const runs = await github.rest.actions.listWorkflowRuns({
    owner,
    repo,
    workflow_id: 'pypi-release.yml',
    per_page: 20,
  });
  const staleCutoff = now.getTime() - STALE_WAITING_HOURS * 60 * 60 * 1000;
  return runs.data.workflow_runs.some((r) => {
    if (!ACTIVE_RELEASE_STATUSES.has(r.status) || r.conclusion) return false;
    if (r.status === 'waiting' && new Date(r.created_at).getTime() < staleCutoff) {
      if (core) {
        core.warning(
          `Ignoring release run waiting >${STALE_WAITING_HOURS}h for environment approval: `
          + `${r.html_url} — approve or cancel it. It no longer blocks auto-releases.`
        );
      }
      return false;
    }
    return true;
  });
}

function utcDayStart(now = new Date()) {
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
}

function releaseIntervalStart(now = new Date(), intervalDays = PATCH_RELEASE_INTERVAL_DAYS) {
  return new Date(now.getTime() - intervalDays * 24 * 60 * 60 * 1000);
}

async function hasSuccessfulReleaseWithinDays(
  github,
  owner,
  repo,
  now = new Date(),
  intervalDays = PATCH_RELEASE_INTERVAL_DAYS,
) {
  const windowStart = releaseIntervalStart(now, intervalDays);
  // Dedupe on GitHub releases (v* tags) rather than run conclusions: a
  // dry_run=true dispatch concludes 'success' without publishing anything and
  // must not consume the release window. Only a real full release creates a
  // v* GitHub release (bump_and_release.py's `gh release create`).
  const releases = await github.rest.repos.listReleases({
    owner,
    repo,
    per_page: 10,
  });
  return releases.data.some(
    (r) => r.tag_name && r.tag_name.startsWith('v')
      && new Date(r.published_at || r.created_at) >= windowStart
  );
}

/** @deprecated Use hasSuccessfulReleaseWithinDays — kept for selftests. */
async function hasSuccessfulReleaseToday(github, owner, repo, now = new Date()) {
  return hasSuccessfulReleaseWithinDays(github, owner, repo, now, 1);
}

async function lastGreenCoreTestsSha(github, owner, repo) {
  const runs = await github.rest.actions.listWorkflowRuns({
    owner,
    repo,
    workflow_id: 'test-core.yml',
    branch: 'main',
    status: 'completed',
    per_page: 30,
  });
  const hit = runs.data.workflow_runs.find((r) => r.conclusion === 'success');
  return hit ? hit.head_sha : '';
}

async function evaluateReleasePreflight(github, owner, repo, options, core) {
  const {
    headSha,
    isCiTrigger = false,
    bump = 'patch',
  } = options;

  const reasons = [];
  const out = {
    ready: false,
    reasons,
    headSha: headSha || '',
    lastTag: '',
    targetAgents: '',
    targetCode: '',
    targetWrapper: '',
  };

  if (bump !== 'patch') {
    reasons.push('only patch auto-release supported');
    return out;
  }

  const referenceTime = options.now instanceof Date ? options.now : new Date();

  if (await hasActiveReleaseRun(github, owner, repo, referenceTime, core)) {
    reasons.push('PyPI Release already in progress or awaiting approval');
    return out;
  }

  if (await hasSuccessfulReleaseWithinDays(github, owner, repo, referenceTime)) {
    reasons.push(
      `already released within last ${PATCH_RELEASE_INTERVAL_DAYS} days; `
      + `max one patch release every ${PATCH_RELEASE_INTERVAL_DAYS} days`
    );
    return out;
  }

  let versions;
  try {
    versions = readVersionsFromTree();
  } catch (err) {
    reasons.push(err.message);
    return out;
  }
  out.targetAgents = versions.targetAgents;
  out.targetCode = versions.targetCode;
  out.targetWrapper = versions.targetWrapper;

  const agentsOnPypi = await pypiVersionExists('praisonaiagents', versions.targetAgents);
  const codeOnPypi = await pypiVersionExists('praisonai-code', versions.targetCode);
  const wrapperOnPypi = await pypiVersionExists('praisonai', versions.targetWrapper);
  if (agentsOnPypi && codeOnPypi && wrapperOnPypi) {
    reasons.push(
      `already published: praisonaiagents==${versions.targetAgents}, `
      + `praisonai-code==${versions.targetCode}, praisonai==${versions.targetWrapper}`
    );
    return out;
  }

  const { execSync } = require('child_process');
  let lastTag = '';
  try {
    lastTag = execSync('git describe --tags --match "v*" --abbrev=0', { encoding: 'utf8' }).trim();
  } catch {
    reasons.push('no v* tag found');
    return out;
  }
  out.lastTag = lastTag;

  let changed = '';
  try {
    changed = execSync(
      `git diff --name-only ${lastTag} HEAD -- ${PACKAGE_PATHS.join(' ')}`,
      { encoding: 'utf8' }
    ).trim();
  } catch {
    reasons.push('git diff failed');
    return out;
  }

  if (!changed) {
    reasons.push(`no changes in ${PACKAGE_PATHS.join(' or ')} since ${lastTag}`);
    return out;
  }

  if (isCiTrigger) {
    let mainSha = '';
    try {
      mainSha = execSync('git rev-parse origin/main', { encoding: 'utf8' }).trim();
    } catch {
      reasons.push('could not resolve origin/main');
      return out;
    }
    if (headSha !== mainSha) {
      reasons.push(`superseded: green SHA ${headSha.slice(0, 7)} != main ${mainSha.slice(0, 7)}`);
      return out;
    }
    out.headSha = headSha;
  } else {
    const evalSha = execSync('git rev-parse HEAD', { encoding: 'utf8' }).trim();
    out.headSha = evalSha;
    const greenSha = await lastGreenCoreTestsSha(github, owner, repo);
    if (greenSha !== evalSha) {
      // Core Tests has path filters and honors [skip ci] (the release
      // safety-net commit uses it), so the tip of main may legitimately have
      // no Core Tests run of its own — e.g. a docs-only commit, or the
      // "chore(release): … [skip ci]" commit right after a release. Accept a
      // green ancestor when nothing under the released package paths changed
      // after it; otherwise the cron path stalls until the next src/** push.
      let greenAncestorOk = false;
      if (greenSha && /^[0-9a-f]{40}$/.test(greenSha)) {
        try {
          execSync(`git merge-base --is-ancestor ${greenSha} ${evalSha}`);
          const delta = execSync(
            `git diff --name-only ${greenSha} ${evalSha} -- ${PACKAGE_PATHS.join(' ')}`,
            { encoding: 'utf8' }
          ).trim();
          greenAncestorOk = delta === '';
        } catch {
          greenAncestorOk = false;
        }
      }
      if (!greenAncestorOk) {
        reasons.push(`CI not green on HEAD (last green: ${greenSha ? greenSha.slice(0, 7) : 'none'})`);
        return out;
      }
      if (core) {
        core.info(
          `HEAD ${evalSha.slice(0, 7)} has no Core Tests run; accepting green ancestor `
          + `${greenSha.slice(0, 7)} (no package-path changes since).`
        );
      }
    }
  }

  out.ready = true;
  out.reasons = ['ready'];
  if (core) core.info(`Release preflight passed for ${out.headSha || headSha}`);
  return out;
}

module.exports = {
  bumpPatch,
  readVersionsFromTree,
  pypiVersionExists,
  PATCH_RELEASE_INTERVAL_DAYS,
  STALE_WAITING_HOURS,
  releaseIntervalStart,
  hasActiveReleaseRun,
  hasSuccessfulReleaseWithinDays,
  hasSuccessfulReleaseToday,
  utcDayStart,
  evaluateReleasePreflight,
  ACTIVE_RELEASE_STATUSES,
  PACKAGE_PATHS,
};
