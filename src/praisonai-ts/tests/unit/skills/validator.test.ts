import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import {
  validateMetadata,
  validateSkill,
  validate,
  parseFrontmatter,
  ParseError,
  MAX_SKILL_NAME_LENGTH,
  MAX_DESCRIPTION_LENGTH,
  MAX_COMPATIBILITY_LENGTH,
} from '../../../src/skills';

const VALID = { name: 'my-skill', description: 'Does something useful' };

describe('validateMetadata (validator.py:139 parity)', () => {
  it('accepts a valid frontmatter', () => {
    expect(validateMetadata(VALID)).toEqual([]);
  });

  it('accepts a valid frontmatter when the directory name matches', () => {
    expect(validateMetadata(VALID, '/tmp/skills/my-skill')).toEqual([]);
  });

  it('rejects a missing name', () => {
    expect(validateMetadata({ description: 'x' })).toEqual([
      'Missing required field in frontmatter: name',
    ]);
  });

  it('rejects a missing description', () => {
    expect(validateMetadata({ name: 'ok' })).toEqual([
      'Missing required field in frontmatter: description',
    ]);
  });

  it('rejects an empty / whitespace / non-string name', () => {
    for (const bad of ['', '   ', 42, null]) {
      expect(validateMetadata({ ...VALID, name: bad })).toEqual([
        "Field 'name' must be a non-empty string",
      ]);
    }
  });

  it('rejects uppercase names', () => {
    expect(validateMetadata({ ...VALID, name: 'MySkill' })).toEqual([
      "Skill name 'MySkill' must be lowercase",
    ]);
  });

  it('rejects invalid characters in the name', () => {
    const errors = validateMetadata({ ...VALID, name: 'my_skill!' });
    expect(errors).toEqual([
      "Skill name 'my_skill!' contains invalid characters. Only letters, digits, and hyphens are allowed.",
    ]);
  });

  it('rejects leading/trailing and consecutive hyphens', () => {
    expect(validateMetadata({ ...VALID, name: '-lead' })).toContain(
      'Skill name cannot start or end with a hyphen'
    );
    expect(validateMetadata({ ...VALID, name: 'trail-' })).toContain(
      'Skill name cannot start or end with a hyphen'
    );
    expect(validateMetadata({ ...VALID, name: 'a--b' })).toEqual([
      'Skill name cannot contain consecutive hyphens',
    ]);
  });

  it('rejects names longer than 64 characters', () => {
    const name = 'a'.repeat(MAX_SKILL_NAME_LENGTH + 1);
    expect(validateMetadata({ ...VALID, name })).toEqual([
      `Skill name '${name}' exceeds 64 character limit (65 chars)`,
    ]);
    expect(validateMetadata({ ...VALID, name: 'a'.repeat(64) })).toEqual([]);
  });

  it('accepts unicode letters in names (i18n, NFKC-normalised) like Python isalnum()', () => {
    expect(validateMetadata({ ...VALID, name: 'café-skill' })).toEqual([]);
    expect(validateMetadata({ ...VALID, name: 'スキル-1' })).toEqual([]);
    // Combining marks (Tamil vowel signs / virama) are not isalnum() in Python either
    expect(validateMetadata({ ...VALID, name: 'தமிழ்-skill' })).toEqual([
      "Skill name 'தமிழ்-skill' contains invalid characters. Only letters, digits, and hyphens are allowed.",
    ]);
  });

  it('rejects a directory name that does not match the skill name', () => {
    expect(validateMetadata(VALID, '/tmp/skills/other')).toEqual([
      "Directory name 'other' must match skill name 'my-skill'",
    ]);
  });

  it('rejects an empty / whitespace / non-string description (too short)', () => {
    for (const bad of ['', '  \n ', 7]) {
      expect(validateMetadata({ ...VALID, description: bad })).toEqual([
        "Field 'description' must be a non-empty string",
      ]);
    }
  });

  it('rejects a description longer than 1024 characters (too long)', () => {
    const description = 'd'.repeat(MAX_DESCRIPTION_LENGTH + 1);
    expect(validateMetadata({ ...VALID, description })).toEqual([
      'Description exceeds 1024 character limit (1025 chars)',
    ]);
    expect(validateMetadata({ ...VALID, description: 'd'.repeat(1024) })).toEqual([]);
  });

  it('validates compatibility only when present', () => {
    expect(validateMetadata({ ...VALID, compatibility: 'node >= 18' })).toEqual([]);
    expect(validateMetadata({ ...VALID, compatibility: 12 })).toEqual([
      "Field 'compatibility' must be a string",
    ]);
    expect(
      validateMetadata({ ...VALID, compatibility: 'c'.repeat(MAX_COMPATIBILITY_LENGTH + 1) })
    ).toEqual(['Compatibility exceeds 500 character limit (501 chars)']);
  });

  it('ignores unknown fields unless strict', () => {
    const meta = { ...VALID, vendor_x: '1', zeta: 2 };
    expect(validateMetadata(meta)).toEqual([]);
    const errors = validateMetadata(meta, undefined, true);
    expect(errors).toHaveLength(1);
    expect(errors[0]).toMatch(/^Unexpected fields in frontmatter: vendor_x, zeta\. Only \[/);
  });

  it('accumulates multiple errors in Python order', () => {
    const errors = validateMetadata({ name: 'Bad Name', description: '' });
    expect(errors).toEqual([
      "Skill name 'Bad Name' must be lowercase",
      "Skill name 'Bad Name' contains invalid characters. Only letters, digits, and hyphens are allowed.",
      "Field 'description' must be a non-empty string",
    ]);
  });
});

describe('validateSkill / validate (validator.py:171 parity)', () => {
  let tmp: string;
  beforeEach(() => {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'skills-validate-'));
  });
  afterEach(() => {
    fs.rmSync(tmp, { recursive: true, force: true });
  });

  const writeSkill = (dirName: string, content: string, file = 'SKILL.md') => {
    const dir = path.join(tmp, dirName);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, file), content);
    return dir;
  };

  it('is exported under both names', () => {
    expect(validate).toBe(validateSkill);
  });

  it('returns [] for a valid skill directory', () => {
    const dir = writeSkill('good-skill', '---\nname: good-skill\ndescription: Fine\n---\n# Body\n');
    expect(validateSkill(dir)).toEqual([]);
  });

  it('accepts lowercase skill.md', () => {
    const dir = writeSkill('lower', '---\nname: lower\ndescription: Fine\n---\nBody', 'skill.md');
    expect(validateSkill(dir)).toEqual([]);
  });

  it('reports a missing path, a non-directory, and a missing SKILL.md', () => {
    const missing = path.join(tmp, 'nope');
    expect(validateSkill(missing)).toEqual([`Path does not exist: ${missing}`]);

    const file = path.join(tmp, 'file.txt');
    fs.writeFileSync(file, 'x');
    expect(validateSkill(file)).toEqual([`Not a directory: ${file}`]);

    const empty = path.join(tmp, 'empty');
    fs.mkdirSync(empty);
    expect(validateSkill(empty)).toEqual(['Missing required file: SKILL.md']);
  });

  it('reports frontmatter parse errors', () => {
    const noFm = writeSkill('no-fm', '# Just markdown\n');
    expect(validateSkill(noFm)).toEqual(['SKILL.md must start with YAML frontmatter (---)']);

    const unclosed = writeSkill('unclosed', '---\nname: unclosed\n');
    expect(validateSkill(unclosed)).toEqual(['SKILL.md frontmatter not properly closed with ---']);
  });

  it('reports rule violations including directory mismatch', () => {
    const dir = writeSkill('wrong-dir', '---\nname: other-name\ndescription: Fine\n---\nBody');
    expect(validateSkill(dir)).toEqual([
      "Directory name 'wrong-dir' must match skill name 'other-name'",
    ]);
  });

  it('honours strict', () => {
    const dir = writeSkill('strict-skill', '---\nname: strict-skill\ndescription: Fine\nextra: 1\n---\nBody');
    expect(validateSkill(dir)).toEqual([]);
    expect(validateSkill(dir, true)[0]).toMatch(/^Unexpected fields in frontmatter: extra\./);
  });
});

describe('parseFrontmatter (parser.py:33 parity)', () => {
  it('splits metadata and body', () => {
    const { metadata, body } = parseFrontmatter('---\nname: a\ndescription: "b"\n---\n\n# Hi\n');
    expect(metadata).toEqual({ name: 'a', description: 'b' });
    expect(body).toBe('# Hi');
  });

  it('throws ParseError on missing or unclosed frontmatter', () => {
    expect(() => parseFrontmatter('name: a')).toThrow(ParseError);
    expect(() => parseFrontmatter('---\nname: a')).toThrow(ParseError);
  });
});
