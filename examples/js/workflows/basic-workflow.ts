/**
 * Basic Workflow Example
 * Demonstrates sequential workflow execution
 */

import { Workflow, parallel, route, loop } from 'praisonai';

async function main() {
  // Create a simple workflow
  const workflow = new Workflow<string, string>('DataProcessor')
    .step('validate', async (input) => {
      console.log('Step 1: Validating input...');
      return input.trim();
    })
    .step('transform', async (input) => {
      console.log('Step 2: Transforming...');
      return input.toUpperCase();
    })
    .step('format', async (input) => {
      console.log('Step 3: Formatting...');
      return `[PROCESSED] ${input}`;
    });

  const result = await workflow.run('  hello world  ');
  console.log('\nFinal output:', result.output);
  console.log('Steps executed:', result.steps.length);
}

main().catch(console.error);
