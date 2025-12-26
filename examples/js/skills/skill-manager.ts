/**
 * Skills System Example
 * Demonstrates skill management and parsing
 */

import { SkillManager, parseSkillFile, createSkillManager } from 'praisonai';

async function main() {
  // Parse a skill file
  const skillContent = `---
name: code-review
description: Reviews code for best practices and potential issues
license: MIT
metadata:
  author: praisonai
  version: "1.0"
allowed-tools: Read Grep
---

# Code Review Skill

When reviewing code:
1. Check for syntax errors
2. Look for security vulnerabilities
3. Suggest performance improvements
4. Ensure proper error handling
`;

  console.log('=== Parse Skill File ===');
  const skill = parseSkillFile(skillContent);
  console.log('Name:', skill.metadata.name);
  console.log('Description:', skill.metadata.description);
  console.log('License:', skill.metadata.license);
  console.log('Instructions preview:', skill.instructions.substring(0, 100) + '...');

  // Create skill manager
  console.log('\n=== Skill Manager ===');
  const manager = createSkillManager({ paths: [] });

  // Register skills manually
  manager.register({
    metadata: {
      name: 'typescript-expert',
      description: 'Expert knowledge in TypeScript development'
    },
    instructions: 'You are a TypeScript expert. Help with type definitions, generics, and best practices.'
  });

  manager.register({
    metadata: {
      name: 'api-designer',
      description: 'Designs RESTful APIs following best practices'
    },
    instructions: 'You design clean, RESTful APIs with proper versioning and documentation.'
  });

  // List skills
  console.log('Registered skills:');
  manager.list().forEach(s => {
    console.log(`- ${s.metadata.name}: ${s.metadata.description}`);
  });

  // Get specific skill
  const tsSkill = manager.get('typescript-expert');
  console.log('\n=== TypeScript Expert Skill ===');
  console.log('Instructions:', tsSkill?.instructions);

  // Generate prompt
  console.log('\n=== Generated Prompt ===');
  const prompt = manager.generatePrompt(['typescript-expert']);
  console.log(prompt.substring(0, 200) + '...');
}

main().catch(console.error);
