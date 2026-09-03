/**
 * Skill validation logic.
 *
 * Python parity with praisonaiagents/skills/validator.py. Every rule and
 * error message mirrors the Python implementation so the two runtimes
 * accept and reject the same SKILL.md files.
 */

import * as fs from 'fs';
import * as path from 'path';
import { findSkillMd, parseFrontmatter, ParseError } from './parser';

/** Python: validator.py:10 */
export const MAX_SKILL_NAME_LENGTH = 64;
/** Python: validator.py:11 */
export const MAX_DESCRIPTION_LENGTH = 1024;
/** Python: validator.py:12 */
export const MAX_COMPATIBILITY_LENGTH = 500;

/**
 * Frontmatter fields accepted in strict mode.
 *
 * Python: validator.py:14 `ALLOWED_FIELDS`.
 */
export const ALLOWED_FIELDS: ReadonlySet<string> = new Set([
  // Agent Skills spec (agentskills.io)
  'name',
  'description',
  'license',
  'allowed-tools',
  'metadata',
  'compatibility',
  // Claude Code extensions (https://docs.claude.com/en/skills)
  'when_to_use',
  'disable-model-invocation',
  'user-invocable',
  'argument-hint',
  'model',
  'effort',
  'context',
  'agent',
  'hooks',
  'paths',
  'shell',
]);

/** Unicode-aware equivalent of Python's `str.isalnum()` for a single char. */
const ALNUM_OR_HYPHEN = /^[\p{L}\p{N}-]*$/u;

/**
 * Validate skill name format and directory match.
 *
 * Skill names support i18n characters (Unicode letters) plus hyphens.
 * Names must be lowercase and cannot start/end with hyphens.
 *
 * Python: validator.py:37 `_validate_name(name, skill_dir)`.
 */
function validateName(name: unknown, skillDir?: string): string[] {
  const errors: string[] = [];

  if (typeof name !== 'string' || !name.trim()) {
    errors.push("Field 'name' must be a non-empty string");
    return errors;
  }

  const normalized = name.trim().normalize('NFKC');

  if (normalized.length > MAX_SKILL_NAME_LENGTH) {
    errors.push(
      `Skill name '${normalized}' exceeds ${MAX_SKILL_NAME_LENGTH} character limit ` +
        `(${normalized.length} chars)`
    );
  }

  if (normalized !== normalized.toLowerCase()) {
    errors.push(`Skill name '${normalized}' must be lowercase`);
  }

  if (normalized.startsWith('-') || normalized.endsWith('-')) {
    errors.push('Skill name cannot start or end with a hyphen');
  }

  if (normalized.includes('--')) {
    errors.push('Skill name cannot contain consecutive hyphens');
  }

  if (!ALNUM_OR_HYPHEN.test(normalized)) {
    errors.push(
      `Skill name '${normalized}' contains invalid characters. ` +
        'Only letters, digits, and hyphens are allowed.'
    );
  }

  if (skillDir) {
    const rawDirName = path.basename(skillDir);
    const dirName = rawDirName.normalize('NFKC');
    if (dirName !== normalized) {
      errors.push(`Directory name '${rawDirName}' must match skill name '${normalized}'`);
    }
  }

  return errors;
}

/**
 * Validate description format.
 *
 * Python: validator.py:82 `_validate_description(description)`.
 */
function validateDescription(description: unknown): string[] {
  const errors: string[] = [];

  if (typeof description !== 'string' || !description.trim()) {
    errors.push("Field 'description' must be a non-empty string");
    return errors;
  }

  if (description.length > MAX_DESCRIPTION_LENGTH) {
    errors.push(
      `Description exceeds ${MAX_DESCRIPTION_LENGTH} character limit ` +
        `(${description.length} chars)`
    );
  }

  return errors;
}

/**
 * Validate compatibility format.
 *
 * Python: validator.py:99 `_validate_compatibility(compatibility)`.
 */
function validateCompatibility(compatibility: unknown): string[] {
  const errors: string[] = [];

  if (typeof compatibility !== 'string') {
    errors.push("Field 'compatibility' must be a string");
    return errors;
  }

  if (compatibility.length > MAX_COMPATIBILITY_LENGTH) {
    errors.push(
      `Compatibility exceeds ${MAX_COMPATIBILITY_LENGTH} character limit ` +
        `(${compatibility.length} chars)`
    );
  }

  return errors;
}

/**
 * Validate that only allowed fields are present.
 *
 * Python: validator.py:116 `_validate_metadata_fields(metadata, strict=False)`.
 *
 * @param strict If true, unknown fields produce errors. If false (default),
 *   unknown fields are ignored (spec evolution + vendor extensions).
 */
function validateMetadataFields(metadata: Record<string, unknown>, strict = false): string[] {
  const errors: string[] = [];

  if (!strict) {
    return errors;
  }

  const extraFields = Object.keys(metadata)
    .filter((k) => !ALLOWED_FIELDS.has(k))
    .sort();
  if (extraFields.length > 0) {
    const allowed = Array.from(ALLOWED_FIELDS).sort();
    errors.push(
      `Unexpected fields in frontmatter: ${extraFields.join(', ')}. ` +
        `Only [${allowed.map((f) => `'${f}'`).join(', ')}] are allowed.`
    );
  }

  return errors;
}

/**
 * Validate parsed skill metadata.
 *
 * This is the core validation function that works on already-parsed
 * metadata, avoiding duplicate file I/O when called from the parser.
 *
 * Python: praisonaiagents/skills/validator.py:139
 * `validate_metadata(metadata, skill_dir=None, strict=False)`.
 *
 * @param metadata Parsed YAML frontmatter mapping
 * @param skillDir Optional path to the skill directory (for the
 *   name/directory match check)
 * @param strict If true, unknown frontmatter fields produce errors
 * @returns List of validation error messages. Empty list means valid.
 */
export function validateMetadata(
  metadata: Record<string, unknown>,
  skillDir?: string,
  strict = false
): string[] {
  const errors: string[] = [];
  errors.push(...validateMetadataFields(metadata, strict));

  if (!('name' in metadata)) {
    errors.push('Missing required field in frontmatter: name');
  } else {
    errors.push(...validateName(metadata.name, skillDir));
  }

  if (!('description' in metadata)) {
    errors.push('Missing required field in frontmatter: description');
  } else {
    errors.push(...validateDescription(metadata.description));
  }

  if ('compatibility' in metadata) {
    errors.push(...validateCompatibility(metadata.compatibility));
  }

  return errors;
}

/**
 * Validate a skill directory.
 *
 * Python: praisonaiagents/skills/validator.py:171
 * `validate(skill_dir, strict=False)`. Exported as `validateSkill` (and
 * aliased as `validate`) because `validate` alone is ambiguous in TS.
 *
 * @param skillDir Path to the skill directory
 * @param strict If true, unknown frontmatter fields produce errors
 * @returns List of validation error messages. Empty list means valid.
 */
export function validateSkill(skillDir: string, strict = false): string[] {
  if (!fs.existsSync(skillDir)) {
    return [`Path does not exist: ${skillDir}`];
  }

  if (!fs.statSync(skillDir).isDirectory()) {
    return [`Not a directory: ${skillDir}`];
  }

  const skillMd = findSkillMd(skillDir);
  if (skillMd === undefined) {
    return ['Missing required file: SKILL.md'];
  }

  let metadata: Record<string, unknown>;
  try {
    const content = fs.readFileSync(skillMd, 'utf-8');
    metadata = parseFrontmatter(content).metadata;
  } catch (e) {
    if (e instanceof ParseError) {
      return [e.message];
    }
    return [`SKILL.md is not valid UTF-8: ${(e as Error).message}`];
  }

  return validateMetadata(metadata, skillDir, strict);
}

/** Alias matching the Python name `validate`. */
export { validateSkill as validate };
