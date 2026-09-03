/**
 * YAML frontmatter parsing for SKILL.md files.
 *
 * Python parity with praisonaiagents/skills/parser.py.
 */

import * as fs from 'fs';
import * as path from 'path';

/**
 * Raised when SKILL.md parsing fails.
 *
 * Python: praisonaiagents/skills/models.py:9 `ParseError`.
 */
export class ParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ParseError';
  }
}

/**
 * Find the SKILL.md file in a skill directory.
 * Prefers SKILL.md (uppercase) but accepts skill.md (lowercase).
 *
 * Python: praisonaiagents/skills/parser.py:15 `find_skill_md(skill_dir)`.
 *
 * @param skillDir Path to the skill directory
 * @returns Path to the SKILL.md file, or undefined if not found
 */
export function findSkillMd(skillDir: string): string | undefined {
  for (const name of ['SKILL.md', 'skill.md']) {
    const candidate = path.join(skillDir, name);
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return undefined;
}

/**
 * Minimal YAML frontmatter parser (flat `key: value` pairs plus a one-level
 * nested `metadata:` mapping). Values are kept as strings; surrounding quotes
 * are stripped.
 */
export function parseYamlFrontmatter(yaml: string): Record<string, any> {
  const result: Record<string, any> = {};
  const lines = yaml.split('\n');
  let currentKey = '';
  let inMetadata = false;
  const metadataObj: Record<string, string> = {};

  for (const line of lines) {
    if (line.startsWith('metadata:')) {
      inMetadata = true;
      continue;
    }

    if (inMetadata && line.startsWith('  ')) {
      const match = line.match(/^\s+(\w+):\s*(.*)$/);
      if (match) {
        metadataObj[match[1]] = match[2].replace(/^["']|["']$/g, '');
      }
      continue;
    } else if (inMetadata && !line.startsWith('  ')) {
      inMetadata = false;
      result.metadata = metadataObj;
    }

    const match = line.match(/^(\S+):\s*(.*)$/);
    if (match) {
      currentKey = match[1];
      result[currentKey] = match[2].replace(/^["']|["']$/g, '');
    }
  }

  if (inMetadata) {
    result.metadata = metadataObj;
  }

  return result;
}

/**
 * Parse YAML frontmatter from SKILL.md content.
 *
 * Python: praisonaiagents/skills/parser.py:33 `parse_frontmatter(content)`.
 *
 * @param content Raw content of the SKILL.md file
 * @returns `{ metadata, body }` — the parsed frontmatter mapping and the
 *   trimmed markdown body
 * @throws {ParseError} If frontmatter is missing or not properly closed
 */
export function parseFrontmatter(content: string): { metadata: Record<string, any>; body: string } {
  if (!content.startsWith('---')) {
    throw new ParseError('SKILL.md must start with YAML frontmatter (---)');
  }

  // Python: content.split("---", 2) — at most two splits, three parts.
  const first = content.indexOf('---');
  const second = content.indexOf('---', first + 3);
  if (second === -1) {
    throw new ParseError('SKILL.md frontmatter not properly closed with ---');
  }

  const frontmatterStr = content.slice(first + 3, second);
  const body = content.slice(second + 3).trim();

  let metadata: Record<string, any>;
  try {
    metadata = parseYamlFrontmatter(frontmatterStr);
  } catch (e) {
    throw new ParseError(`Invalid YAML in frontmatter: ${(e as Error).message}`);
  }

  if (metadata === null || typeof metadata !== 'object' || Array.isArray(metadata)) {
    throw new ParseError('SKILL.md frontmatter must be a YAML mapping');
  }

  return { metadata, body };
}
