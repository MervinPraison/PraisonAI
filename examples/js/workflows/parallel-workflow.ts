/**
 * Parallel Workflow Example
 * Demonstrates parallel execution of tasks
 */

import { parallel } from 'praisonai';

async function main() {
  console.log('Starting parallel tasks...\n');

  const results = await parallel([
    async () => {
      console.log('Task 1: Starting...');
      await new Promise(r => setTimeout(r, 1000));
      console.log('Task 1: Complete');
      return 'Result 1';
    },
    async () => {
      console.log('Task 2: Starting...');
      await new Promise(r => setTimeout(r, 500));
      console.log('Task 2: Complete');
      return 'Result 2';
    },
    async () => {
      console.log('Task 3: Starting...');
      await new Promise(r => setTimeout(r, 750));
      console.log('Task 3: Complete');
      return 'Result 3';
    }
  ]);

  console.log('\nAll tasks complete!');
  console.log('Results:', results);
}

main().catch(console.error);
