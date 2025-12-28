/**
 * Skills Example - Using agent skills
 * 
 * Run: npx ts-node examples/features/skills.ts
 */

import { Agent, SkillManager, type Skill } from '../../src';

async function main() {
  // Create a skill manager
  const skillManager = new SkillManager({
    paths: ['./.praison/skills'],
    includeProject: true,
    includeUser: true
  });

  // Discover available skills
  console.log("=== Discovering Skills ===");
  const skills = await skillManager.discover();
  
  if (skills.length === 0) {
    console.log("No skills found. Create a skill in .praison/skills/");
    console.log("\nExample SKILL.md:");
    console.log(`---
name: code-review
description: Reviews code for best practices
---

# Code Review Skill

When reviewing code:
1. Check for security issues
2. Verify error handling
3. Suggest improvements
`);
  } else {
    skills.forEach((skill: Skill) => {
      console.log(`  - ${skill.metadata.name}: ${skill.metadata.description}`);
    });
  }

  // Create agent (skills would be loaded automatically if configured)
  const agent = new Agent({
    instructions: "You are a helpful coding assistant.",
    verbose: true
  });

  await agent.chat("Help me write clean code");
}

main().catch(console.error);
