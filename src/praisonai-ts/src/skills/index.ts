/**
 * Skills System - Agent Skills standard implementation
 */

import * as fs from 'fs';
import * as path from 'path';

export interface SkillMetadata {
  name: string;
  description: string;
  license?: string;
  compatibility?: string;
  allowedTools?: string[];
  metadata?: Record<string, string>;
}

export interface Skill {
  metadata: SkillMetadata;
  instructions: string;
  path?: string;
}

export interface SkillDiscoveryOptions {
  paths?: string[];
  includeSystem?: boolean;
  includeUser?: boolean;
  includeProject?: boolean;
}

/**
 * Parse SKILL.md file
 */
export function parseSkillFile(content: string): Skill {
  const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  
  if (!frontmatterMatch) {
    throw new Error('Invalid SKILL.md format: missing frontmatter');
  }

  const [, frontmatter, instructions] = frontmatterMatch;
  const metadata = parseYamlFrontmatter(frontmatter);

  if (!metadata.name || !metadata.description) {
    throw new Error('Invalid SKILL.md: name and description are required');
  }

  return {
    metadata: {
      name: metadata.name,
      description: metadata.description,
      license: metadata.license,
      compatibility: metadata.compatibility,
      allowedTools: metadata['allowed-tools']?.split(/\s+/),
      metadata: metadata.metadata
    },
    instructions: instructions.trim()
  };
}

/**
 * Simple YAML frontmatter parser
 */
function parseYamlFrontmatter(yaml: string): Record<string, any> {
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
 * Skill Manager - Load and manage skills
 */
export class SkillManager {
  private skills: Map<string, Skill> = new Map();
  private discoveryPaths: string[] = [];

  constructor(options: SkillDiscoveryOptions = {}) {
    this.setupDiscoveryPaths(options);
  }

  private setupDiscoveryPaths(options: SkillDiscoveryOptions): void {
    if (options.paths) {
      this.discoveryPaths.push(...options.paths);
    }

    if (options.includeProject !== false) {
      this.discoveryPaths.push('./.praison/skills');
      this.discoveryPaths.push('./.claude/skills');
    }

    if (options.includeUser !== false) {
      const home = process.env.HOME || process.env.USERPROFILE || '';
      if (home) {
        this.discoveryPaths.push(path.join(home, '.praison/skills'));
      }
    }

    if (options.includeSystem) {
      this.discoveryPaths.push('/etc/praison/skills');
    }
  }

  /**
   * Discover and load skills from configured paths
   */
  async discover(): Promise<Skill[]> {
    const discovered: Skill[] = [];

    for (const basePath of this.discoveryPaths) {
      if (!fs.existsSync(basePath)) continue;

      const entries = fs.readdirSync(basePath, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory()) {
          const skillPath = path.join(basePath, entry.name, 'SKILL.md');
          if (fs.existsSync(skillPath)) {
            try {
              const skill = await this.loadSkill(skillPath);
              skill.path = path.join(basePath, entry.name);
              discovered.push(skill);
              this.skills.set(skill.metadata.name, skill);
            } catch (e) {
              // Skip invalid skills
            }
          }
        }
      }
    }

    return discovered;
  }

  /**
   * Load a skill from a SKILL.md file
   */
  async loadSkill(skillPath: string): Promise<Skill> {
    const content = fs.readFileSync(skillPath, 'utf-8');
    return parseSkillFile(content);
  }

  /**
   * Register a skill manually
   */
  register(skill: Skill): void {
    this.skills.set(skill.metadata.name, skill);
  }

  /**
   * Get a skill by name
   */
  get(name: string): Skill | undefined {
    return this.skills.get(name);
  }

  /**
   * List all loaded skills
   */
  list(): Skill[] {
    return Array.from(this.skills.values());
  }

  /**
   * Generate XML prompt for skills
   */
  generatePrompt(skillNames?: string[]): string {
    const skillsToInclude = skillNames
      ? skillNames.map(n => this.skills.get(n)).filter(Boolean) as Skill[]
      : this.list();

    if (skillsToInclude.length === 0) return '';

    const parts = ['<skills>'];
    for (const skill of skillsToInclude) {
      parts.push(`  <skill name="${skill.metadata.name}">`);
      parts.push(`    <description>${skill.metadata.description}</description>`);
      parts.push(`    <instructions>${skill.instructions}</instructions>`);
      parts.push('  </skill>');
    }
    parts.push('</skills>');

    return parts.join('\n');
  }

  /**
   * Validate a skill
   */
  validate(skill: Skill): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    if (!skill.metadata.name) {
      errors.push('Missing required field: name');
    } else if (!/^[a-z0-9-]{1,64}$/.test(skill.metadata.name)) {
      errors.push('Invalid name: must be 1-64 lowercase chars, numbers, or hyphens');
    }

    if (!skill.metadata.description) {
      errors.push('Missing required field: description');
    } else if (skill.metadata.description.length > 1024) {
      errors.push('Description too long: max 1024 characters');
    }

    if (skill.instructions.length > 5000) {
      errors.push('Instructions too long: max 5000 characters');
    }

    return { valid: errors.length === 0, errors };
  }
}

/**
 * Create a skill manager
 */
export function createSkillManager(options?: SkillDiscoveryOptions): SkillManager {
  return new SkillManager(options);
}
