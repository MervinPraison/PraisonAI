/**
 * Skills command - Manage agent skills
 */

import { SkillManager, createSkillManager, Skill } from '../../skills';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface SkillsOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: SkillsOptions): Promise<void> {
  const action = args[0] || 'list';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    const searchPath = actionArgs[0] || '.';
    const manager = createSkillManager({ paths: [searchPath] });

    switch (action) {
      case 'list':
        await listSkills(manager, outputFormat);
        break;
      case 'discover':
        await discoverSkills(manager, actionArgs, outputFormat);
        break;
      case 'validate':
        await validateSkill(manager, actionArgs, outputFormat);
        break;
      case 'info':
        await skillInfo(manager, actionArgs, outputFormat);
        break;
      case 'help':
      default:
        await showHelp(outputFormat);
        break;
    }
  } catch (error) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, error instanceof Error ? error.message : String(error)));
    } else {
      await pretty.error(error instanceof Error ? error.message : String(error));
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }
}

async function listSkills(manager: SkillManager, outputFormat: string): Promise<void> {
  const skills = manager.list();
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      skills: skills.map((s: Skill) => ({
        name: s.metadata.name,
        description: s.metadata.description,
        path: s.path
      })),
      count: skills.length
    }));
  } else {
    await pretty.heading('Available Skills');
    if (skills.length === 0) {
      await pretty.info('No skills loaded');
      await pretty.dim('Run "praisonai-ts skills discover <path>" to discover skills');
    } else {
      for (const skill of skills) {
        await pretty.plain(`  • ${skill.metadata.name}`);
        if (skill.metadata.description) {
          await pretty.dim(`    ${skill.metadata.description}`);
        }
      }
    }
    await pretty.newline();
    await pretty.info(`Total: ${skills.length} skills`);
  }
}

async function discoverSkills(manager: SkillManager, args: string[], outputFormat: string): Promise<void> {
  const searchPath = args[0] || '.';
  
  const discovered = await manager.discover();
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      discovered: discovered.map((s: Skill) => ({
        name: s.metadata.name,
        description: s.metadata.description,
        path: s.path
      })),
      count: discovered.length,
      searchPath
    }));
  } else {
    await pretty.heading(`Discovered Skills in: ${searchPath}`);
    if (discovered.length === 0) {
      await pretty.info('No skills found');
    } else {
      for (const skill of discovered) {
        await pretty.plain(`  • ${skill.metadata.name}`);
        if (skill.metadata.description) {
          await pretty.dim(`    ${skill.metadata.description}`);
        }
        if (skill.path) {
          await pretty.dim(`    Path: ${skill.path}`);
        }
      }
    }
    await pretty.newline();
    await pretty.info(`Found: ${discovered.length} skills`);
  }
}

async function validateSkill(manager: SkillManager, args: string[], outputFormat: string): Promise<void> {
  const skillPath = args[0];
  if (!skillPath) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a skill path'));
    } else {
      await pretty.error('Please provide a skill path');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  try {
    // Load the skill first, then validate
    const skill = await manager.loadSkill(skillPath);
    const result = manager.validate(skill);
    
    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        valid: result.valid,
        path: skillPath,
        errors: result.errors || []
      }));
    } else {
      if (result.valid) {
        await pretty.success(`Skill is valid: ${skillPath}`);
      } else {
        await pretty.error(`Skill validation failed: ${skillPath}`);
        if (result.errors) {
          for (const err of result.errors) {
            await pretty.plain(`  ❌ ${err}`);
          }
        }
      }
    }
  } catch (error) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, error instanceof Error ? error.message : String(error)));
    } else {
      await pretty.error(`Validation error: ${error instanceof Error ? error.message : String(error)}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }
}

async function skillInfo(manager: SkillManager, args: string[], outputFormat: string): Promise<void> {
  const skillName = args[0];
  if (!skillName) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a skill name'));
    } else {
      await pretty.error('Please provide a skill name');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const skill = manager.get(skillName);
  if (!skill) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, `Skill not found: ${skillName}`));
    } else {
      await pretty.error(`Skill not found: ${skillName}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      name: skill.metadata.name,
      description: skill.metadata.description,
      path: skill.path,
      metadata: skill.metadata
    }));
  } else {
    await pretty.heading(`Skill: ${skill.metadata.name}`);
    await pretty.keyValue({
      'Name': skill.metadata.name,
      'Description': skill.metadata.description || 'No description',
      'Path': skill.path || 'N/A'
    });
    if (skill.metadata.metadata && Object.keys(skill.metadata.metadata).length > 0) {
      await pretty.newline();
      await pretty.plain('Metadata:');
      await pretty.plain(JSON.stringify(skill.metadata.metadata, null, 2));
    }
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'skills',
    subcommands: [
      { name: 'list', description: 'List loaded skills' },
      { name: 'discover <path>', description: 'Discover skills in directory' },
      { name: 'validate <path>', description: 'Validate a skill' },
      { name: 'info <name>', description: 'Show skill information' },
      { name: 'help', description: 'Show this help' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Skills Command');
    await pretty.plain('Manage agent skills\n');
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(20)} ${cmd.description}`);
    }
  }
}
