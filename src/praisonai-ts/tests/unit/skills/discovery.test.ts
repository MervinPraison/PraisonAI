import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { discoverSkills, discoverSkill, loadSkill, getDefaultSkillDirs } from '../../../src/skills';

describe('discoverSkills / loadSkill (discovery.py:77, __init__.py:166 parity)', () => {
  let tmp: string;
  let warnSpy: jest.SpyInstance;

  const writeSkill = (base: string, dirName: string, name = dirName, extra = '') => {
    const dir = path.join(base, dirName);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(
      path.join(dir, 'SKILL.md'),
      `---\nname: ${name}\ndescription: Skill ${name}\n${extra}---\n# ${name}\n\nInstructions for ${name}.\n`
    );
    return dir;
  };

  beforeEach(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'skills-discover-'));
    warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
  });
  afterEach(() => {
    warnSpy.mockRestore();
    fs.rmSync(tmp, { recursive: true, force: true });
  });

  it('finds a skill in a temp dir and ignores a non-skill dir', async () => {
    writeSkill(tmp, 'alpha');
    fs.mkdirSync(path.join(tmp, 'not-a-skill'));
    fs.writeFileSync(path.join(tmp, 'not-a-skill', 'README.md'), 'nothing here');
    fs.writeFileSync(path.join(tmp, 'loose-file.txt'), 'ignored');

    const found = await discoverSkills([tmp], false);

    expect(found.map((s) => s.name)).toEqual(['alpha']);
    expect(found[0].description).toBe('Skill alpha');
    expect(found[0].path).toBe(path.join(tmp, 'alpha'));
    expect(warnSpy).not.toHaveBeenCalled();
  });

  it('skips invalid skills with a warning and keeps the valid ones', async () => {
    writeSkill(tmp, 'good');
    const bad = path.join(tmp, 'bad');
    fs.mkdirSync(bad);
    fs.writeFileSync(path.join(bad, 'SKILL.md'), '---\ndescription: no name\n---\nBody');

    const found = await discoverSkills([tmp], false);
    expect(found.map((s) => s.name)).toEqual(['good']);
    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy.mock.calls[0][0]).toMatch(/Skipping invalid skill/);
  });

  it('earlier directories win on name collisions and dirs are de-duplicated', async () => {
    const first = path.join(tmp, 'first');
    const second = path.join(tmp, 'second');
    writeSkill(first, 'dup');
    const dir2 = writeSkill(second, 'dup');
    fs.writeFileSync(path.join(dir2, 'SKILL.md'), '---\nname: dup\ndescription: from second\n---\nB');

    const found = await discoverSkills([first, second, first], false);
    expect(found).toHaveLength(1);
    expect(found[0].description).toBe('Skill dup');
  });

  it('treats a directory that is itself a skill as a single skill', async () => {
    const dir = writeSkill(tmp, 'solo');
    const found = await discoverSkills([dir], false);
    expect(found.map((s) => s.name)).toEqual(['solo']);
  });

  it('ignores non-existent explicit dirs and, with includeDefaults=false, returns []', async () => {
    expect(await discoverSkills([path.join(tmp, 'missing')], false)).toEqual([]);
    expect(await discoverSkills(undefined, false)).toEqual([]);
  });

  it('accepts fetch()-protocol remote sources after local dirs and never throws', async () => {
    writeSkill(tmp, 'local');
    const remote = path.join(tmp, 'remote-root');
    writeSkill(remote, 'remote-skill');
    const source = { fetch: jest.fn(async () => [remote]) };
    const failing = { fetch: () => { throw new Error('boom'); } };

    const found = await discoverSkills([path.join(tmp, 'local')], false, [source, failing, 'https://example.com/x.git']);
    expect(found.map((s) => s.name)).toEqual(['local', 'remote-skill']);
    expect(source.fetch).toHaveBeenCalledTimes(1);
  });

  it('getDefaultSkillDirs returns only existing directories', () => {
    for (const d of getDefaultSkillDirs()) {
      expect(fs.statSync(d).isDirectory()).toBe(true);
    }
  });

  it('discoverSkill returns props for a valid dir and undefined otherwise', async () => {
    const dir = writeSkill(tmp, 'single');
    expect((await discoverSkill(dir))?.name).toBe('single');
    expect(await discoverSkill(path.join(tmp, 'nope'))).toBeUndefined();
    fs.mkdirSync(path.join(tmp, 'empty'));
    expect(await discoverSkill(path.join(tmp, 'empty'))).toBeUndefined();
  });

  describe('loadSkill', () => {
    it('loads by path (directory or SKILL.md) with instructions', async () => {
      const dir = writeSkill(tmp, 'by-path');
      const skill = await loadSkill(dir);
      expect(skill?.metadata.name).toBe('by-path');
      expect(skill?.instructions).toContain('Instructions for by-path.');
      expect(skill?.path).toBe(dir);

      const viaFile = await loadSkill(path.join(dir, 'SKILL.md'));
      expect(viaFile?.metadata.name).toBe('by-path');
    });

    it('loads by name from the given skillDirs', async () => {
      writeSkill(tmp, 'named');
      const skill = await loadSkill('named', [tmp]);
      expect(skill?.metadata.name).toBe('named');
      expect(skill?.instructions).toContain('Instructions for named.');
    });

    it('errors on a missing path', async () => {
      await expect(loadSkill(path.join(tmp, 'does-not-exist'))).rejects.toThrow(/does not exist/);
      const noMd = path.join(tmp, 'no-md');
      fs.mkdirSync(noMd);
      await expect(loadSkill(noMd)).rejects.toThrow(/SKILL\.md not found/);
    });

    it('returns undefined for an unknown name (Python returns None)', async () => {
      writeSkill(tmp, 'other');
      expect(await loadSkill('unknown-skill', [tmp])).toBeUndefined();
    });
  });
});
