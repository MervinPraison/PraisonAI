/**
 * Release gate preflight — path changes, CI SHA, dedupe, PyPI version checks.
 */

const https = require('https');

const PACKAGE_PATHS = ['src/praisonai', 'src/praisonai-agents'];
const ACTIVE_RELEASE_STATUSES = new Set([
  'queued', 'in_progress', 'waiting', 'pending', 'requested',
]);

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
  const wrapperPy = fs.readFileSync(
    path.join(root, 'src/praisonai/praisonai/version.py'), 'utf8'
  );
  const wrapperMatch = wrapperPy.match(/__version__ = "([^"]+)"/);
  if (!wrapperMatch) throw new Error('Could not read wrapper version');
  return {
    currentAgents: agentsMatch[1],
    currentWrapper: wrapperMatch[1],
    targetAgents: bumpPatch(agentsMatch[1]),
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

async function hasActiveReleaseRun(github, owner, repo) {
  const runs = await github.rest.actions.listWorkflowRuns({
    owner,
    repo,
    workflow_id: 'pypi-release.yml',
    per_page: 20,
  });
  return runs.data.workflow_runs.some(
    (r) => ACTIVE_RELEASE_STATUSES.has(r.status) && !r.conclusion
  );
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
    targetWrapper: '',
  };

  if (bump !== 'patch') {
    reasons.push('only patch auto-release supported');
    return out;
  }

  if (await hasActiveReleaseRun(github, owner, repo)) {
    reasons.push('PyPI Release already in progress or awaiting approval');
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
  out.targetWrapper = versions.targetWrapper;

  const agentsOnPypi = await pypiVersionExists('praisonaiagents', versions.targetAgents);
  const wrapperOnPypi = await pypiVersionExists('praisonai', versions.targetWrapper);
  if (agentsOnPypi && wrapperOnPypi) {
    reasons.push(`already published: praisonaiagents==${versions.targetAgents}, praisonai==${versions.targetWrapper}`);
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
      reasons.push(`CI not green on HEAD (last green: ${greenSha ? greenSha.slice(0, 7) : 'none'})`);
      return out;
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
  evaluateReleasePreflight,
  ACTIVE_RELEASE_STATUSES,
};
