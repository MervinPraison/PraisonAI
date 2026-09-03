/**
 * Skill discovery and directory scanning.
 *
 * Python parity with praisonaiagents/skills/discovery.py and the lazy
 * `load_skill` defined in praisonaiagents/skills/__init__.py.
 */

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { findSkillMd } from './parser';
import { SkillLoader, type Skill, type SkillProperties } from './index';

/**
 * A declarative remote skill source. Mirrors the shapes accepted by Python's
 * `discover_skills(sources=...)` (discovery.py:80): a URL string, a
 * `{url, ref}` object, or an object implementing `fetch(cacheDir)` that
 * returns local directories holding fetched skills.
 */
export type RemoteSkillSource =
  | string
  | { url: string; ref?: string }
  | { fetch: (cacheDir: string) => Iterable<string> | Promise<Iterable<string>> };

function isDir(p: string): boolean {
  try {
    return fs.statSync(p).isDirectory();
  } catch {
    return false;
  }
}

function expandUser(p: string): string {
  if (p === '~') return os.homedir();
  if (p.startsWith('~/')) return path.join(os.homedir(), p.slice(2));
  return p;
}

/**
 * PraisonAI data directory.
 * Python: praisonaiagents/paths.py:126 `get_data_dir()` — PRAISONAI_HOME,
 * then ~/.praisonai, then the legacy ~/.praison fallback.
 */
function getDataDir(): string {
  const envHome = process.env.PRAISONAI_HOME;
  if (envHome) return expandUser(envHome);
  const home = os.homedir();
  const primary = path.join(home, '.praisonai');
  if (isDir(primary)) return primary;
  const legacy = path.join(home, '.praison');
  if (isDir(legacy)) return legacy;
  return primary;
}

/**
 * Get default skill directory locations.
 *
 * Python: praisonaiagents/skills/discovery.py:14 `get_default_skill_dirs()`.
 * Returns existing directories in precedence order (high to low):
 * 1. Project: ./.praisonai/skills/ or ./.claude/skills/ (plus ancestors)
 * 2. User: ~/.praisonai/skills/
 * 3. Remote skill cache (`<cache>/remote-skills/<source>/current`)
 * 4. System: /etc/praison/skills/ (admin-managed)
 *
 * @returns List of existing skill directories
 */
export function getDefaultSkillDirs(): string[] {
  const dirs: string[] = [];
  const cwd = process.cwd();
  const add = (p: string) => {
    if (isDir(p) && !dirs.includes(p)) dirs.push(p);
  };

  // Project-level directories
  add(path.join(cwd, '.praisonai', 'skills'));
  add(path.join(cwd, '.claude', 'skills'));

  // Walk ancestor directories so monorepo packages pick up workspace skills
  let parent = path.dirname(cwd);
  while (parent !== path.dirname(parent)) {
    add(path.join(parent, '.praisonai', 'skills'));
    add(path.join(parent, '.claude', 'skills'));
    parent = path.dirname(parent);
  }
  add(path.join(parent, '.praisonai', 'skills'));
  add(path.join(parent, '.claude', 'skills'));

  // User-level directory
  const dataDir = getDataDir();
  add(path.join(dataDir, 'skills'));

  // Remote skill cache populated by `skills sync`: each source keeps a
  // `current` alias pointing at its last-good versioned tree.
  const remoteCache = path.join(dataDir, 'cache', 'remote-skills');
  if (isDir(remoteCache)) {
    try {
      for (const source of fs.readdirSync(remoteCache)) {
        add(path.join(remoteCache, source, 'current'));
      }
    } catch {
      // ignore unreadable cache
    }
  }

  // System-level directory (Unix-like systems)
  add('/etc/praison/skills');

  return dirs;
}

/**
 * Resolve declarative remote sources to local directories.
 * Python: praisonaiagents/skills/remote.py:182 `fetch_remote_skill_dirs`.
 * Only `fetch()`-protocol objects are supported in TS; URL sources are
 * skipped with a warning (no git fetch in this runtime). Never throws.
 */
async function fetchRemoteSkillDirs(sources: RemoteSkillSource[]): Promise<string[]> {
  const root = path.join(getDataDir(), 'cache', 'remote-skills');
  const dirs: string[] = [];
  for (const entry of sources) {
    if (typeof entry !== 'object' || entry === null || !('fetch' in entry) || typeof entry.fetch !== 'function') {
      console.warn(`Skipping remote skill source (not supported in TS runtime): ${JSON.stringify(entry)}`);
      continue;
    }
    try {
      for (const d of await entry.fetch(root)) {
        const p = path.resolve(String(d));
        if (isDir(p) && findSkillMd(p) !== undefined && !dirs.includes(p)) {
          dirs.push(p);
        } else if (isDir(p) && fs.readdirSync(p).some((c) => findSkillMd(path.join(p, c)) !== undefined) && !dirs.includes(p)) {
          dirs.push(p);
        }
      }
    } catch (exc) {
      console.warn(`Remote skill source failed: ${(exc as Error).message}`);
    }
  }
  return dirs;
}

/**
 * Discover all valid skills in the given directories.
 *
 * Python: praisonaiagents/skills/discovery.py:77
 * `discover_skills(skill_dirs=None, include_defaults=True, sources=None)`.
 * Metadata is read through `SkillLoader.loadMetadata` (Level 1 only).
 * Invalid skills are skipped with a warning; when two skills share a name the
 * earlier (higher-precedence) entry wins.
 *
 * @param skillDirs Directory paths to scan. Each directory should contain
 *   skill subdirectories (or itself be a single skill).
 * @param includeDefaults Whether to include the default skill directories
 * @param sources Optional declarative remote skill sources, scanned after
 *   local directories (lowest precedence; never breaks local discovery)
 * @returns SkillProperties for every valid skill found
 */
export async function discoverSkills(
  skillDirs?: string[],
  includeDefaults = true,
  sources?: RemoteSkillSource[]
): Promise<SkillProperties[]> {
  const allDirs: string[] = [];

  // Add explicit directories
  if (skillDirs) {
    for (const d of skillDirs) {
      const resolved = path.resolve(expandUser(d));
      if (isDir(resolved)) {
        allDirs.push(resolved);
      }
    }
  }

  // Add default directories
  if (includeDefaults) {
    allDirs.push(...getDefaultSkillDirs());
  }

  // Add remote sources last (lowest precedence; local always wins).
  if (sources && sources.length > 0) {
    try {
      allDirs.push(...(await fetchRemoteSkillDirs(sources)));
    } catch (exc) {
      console.warn(`Skipping remote skill sources: ${(exc as Error).message}`);
    }
  }

  // Remove duplicates while preserving order
  const uniqueDirs = Array.from(new Set(allDirs));

  const loader = new SkillLoader();
  const skills: SkillProperties[] = [];

  const addSkill = async (item: string): Promise<void> => {
    if (findSkillMd(item) === undefined) {
      return;
    }
    let props: SkillProperties;
    try {
      props = await loader.loadMetadata(item);
    } catch (exc) {
      console.warn(`Skipping invalid skill ${item}: ${(exc as Error).message}`);
      return;
    }
    if (skills.some((p) => p.name === props.name)) {
      // Shadowed by an earlier (higher-precedence) entry
      return;
    }
    skills.push(props);
  };

  for (const parentDir of uniqueDirs) {
    // A dir may itself be a single skill or a parent holding skill subdirs.
    if (findSkillMd(parentDir) !== undefined) {
      await addSkill(parentDir);
      continue;
    }
    let entries: string[];
    try {
      entries = fs.readdirSync(parentDir);
    } catch (exc) {
      console.warn(`Cannot read skills directory ${parentDir}: ${(exc as Error).message}`);
      continue;
    }
    for (const name of entries) {
      const item = path.join(parentDir, name);
      if (isDir(item)) {
        await addSkill(item);
      }
    }
  }

  return skills;
}

/**
 * Discover a single skill from a directory path.
 *
 * Python: praisonaiagents/skills/discovery.py:166 `discover_skill(skill_path)`.
 *
 * @param skillPath Path to a skill directory
 * @returns SkillProperties if valid, undefined otherwise
 */
export async function discoverSkill(skillPath: string): Promise<SkillProperties | undefined> {
  const resolved = path.resolve(expandUser(skillPath));
  if (!isDir(resolved) || findSkillMd(resolved) === undefined) {
    return undefined;
  }
  try {
    return await new SkillLoader().loadMetadata(resolved);
  } catch {
    return undefined;
  }
}

/** Valid skill names never contain a path separator, so anything that does is a path. */
function looksLikePath(value: string): boolean {
  return (
    path.isAbsolute(value) ||
    value.includes('/') ||
    value.includes(path.sep) ||
    value.startsWith('.') ||
    isDir(value)
  );
}

/**
 * Load a skill (metadata + activated instructions) by name, searching the
 * provided or default skill directories.
 *
 * Python: praisonaiagents/skills/__init__.py:166
 * `load_skill(skill_name, skill_dirs=None)` (lazily defined in `__getattr__`).
 *
 * TS extension: `skillName` may also be a path to a skill directory (or its
 * SKILL.md). A bare name that is not found resolves to `undefined` as in
 * Python; an explicit path that does not exist or has no SKILL.md throws.
 *
 * @param skillName Skill name (frontmatter `name`) or a skill directory path
 * @param skillDirs Directories to search before the defaults
 * @returns The loaded skill, or undefined when no skill has that name
 */
export async function loadSkill(skillName: string, skillDirs?: string[]): Promise<Skill | undefined> {
  const loader = new SkillLoader();

  if (looksLikePath(skillName)) {
    let dir = path.resolve(expandUser(skillName));
    if (fs.existsSync(dir) && !isDir(dir)) {
      dir = path.dirname(dir);
    }
    if (!isDir(dir)) {
      throw new Error(`Skill path does not exist: ${skillName}`);
    }
    return loader.loadFull(dir);
  }

  const propsList = await discoverSkills(skillDirs, true);
  for (const props of propsList) {
    if (props.name === skillName && props.path !== undefined) {
      return loader.loadFull(props.path);
    }
  }
  return undefined;
}
