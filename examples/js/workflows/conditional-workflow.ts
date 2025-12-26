/**
 * Conditional Workflow Example
 * Demonstrates routing based on conditions
 */

import { route } from 'praisonai';

async function main() {
  const processRequest = async (type: string) => {
    console.log(`Processing request type: ${type}`);

    const result = await route([
      {
        condition: () => type === 'urgent',
        execute: async () => {
          console.log('  -> Urgent handler activated');
          return 'Processed urgently';
        }
      },
      {
        condition: () => type === 'normal',
        execute: async () => {
          console.log('  -> Normal handler activated');
          return 'Processed normally';
        }
      },
      {
        condition: () => true, // Default
        execute: async () => {
          console.log('  -> Default handler activated');
          return 'Processed with default handler';
        }
      }
    ]);

    return result;
  };

  // Test different request types
  const types = ['urgent', 'normal', 'unknown'];
  
  for (const type of types) {
    const result = await processRequest(type);
    console.log(`Result: ${result}\n`);
  }
}

main().catch(console.error);
