/**
 * AutoAgents Example
 * Demonstrates automatic agent generation from task descriptions
 */

import { AutoAgents, createAutoAgents } from 'praisonai';

async function main() {
  const auto = createAutoAgents({
    pattern: 'sequential',
    verbose: true
  });

  // Analyze task complexity
  console.log('=== Complexity Analysis ===');
  const tasks = [
    'Write a hello world function',
    'Build a web scraper that extracts product data',
    'Create a multi-step data pipeline with validation, transformation, and multiple output formats'
  ];

  tasks.forEach(task => {
    const complexity = auto.analyzeComplexity(task);
    console.log(`"${task.substring(0, 40)}..." -> ${complexity}`);
  });

  // Recommend patterns
  console.log('\n=== Pattern Recommendations ===');
  const patternTasks = [
    'Process items in parallel',
    'Route requests to different handlers',
    'Orchestrate multiple workers',
    'Evaluate and optimize results'
  ];

  patternTasks.forEach(task => {
    const pattern = auto.recommendPattern(task);
    console.log(`"${task}" -> ${pattern}`);
  });

  // Generate agent configuration
  console.log('\n=== Generate Agent Config ===');
  console.log('Generating agents for: "Build a web scraper"');
  
  const team = await auto.generate('Build a web scraper that extracts product prices from e-commerce sites');
  
  console.log('\nGenerated Team:');
  console.log('Pattern:', team.pattern);
  console.log('Agents:', team.agents.length);
  team.agents.forEach(agent => {
    console.log(`  - ${agent.name}: ${agent.role}`);
  });
  console.log('Tasks:', team.tasks.length);
  team.tasks.forEach(task => {
    console.log(`  - ${task.description.substring(0, 50)}...`);
  });
}

main().catch(console.error);
