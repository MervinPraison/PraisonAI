/**
 * Basic Tools Example
 * Demonstrates tool creation and usage
 */

import { tool, ToolRegistry, getRegistry } from 'praisonai';

async function main() {
  // Create tools
  const calculator = tool({
    name: 'calculator',
    description: 'Perform basic math calculations',
    parameters: {
      type: 'object',
      properties: {
        expression: { type: 'string', description: 'Math expression to evaluate' }
      },
      required: ['expression']
    },
    execute: async ({ expression }) => {
      try {
        // Only allow safe numeric math characters
        if (!/^[0-9+\-*/.() ]+$/.test(expression)) {
          return 'Error: Only basic math expressions are allowed';
        }
        // Use Function constructor scoped to math only, no globals
        const result = new Function(`"use strict"; return (${expression})`)();
        if (typeof result !== 'number' || !isFinite(result)) {
          return 'Error: Invalid result';
        }
        return `Result: ${result}`;
      } catch (e) {
        return 'Error: Invalid expression';
      }
    }
  });

  const greeter = tool({
    name: 'greeter',
    description: 'Generate a greeting',
    parameters: {
      type: 'object',
      properties: {
        name: { type: 'string', description: 'Name to greet' }
      },
      required: ['name']
    },
    execute: async ({ name }) => `Hello, ${name}! Welcome to PraisonAI.`
  });

  // Create registry and register tools
  const registry = new ToolRegistry();
  registry.register(calculator);
  registry.register(greeter);

  console.log('Registered tools:', registry.list().map(t => t.name));

  // Execute tools
  const calcResult = await calculator.execute({ expression: '10 * 5 + 2' });
  console.log('\nCalculator:', calcResult);

  const greetResult = await greeter.execute({ name: 'Developer' });
  console.log('Greeter:', greetResult);

  // Get OpenAI format
  console.log('\nOpenAI tool format:', JSON.stringify(calculator.toOpenAITool(), null, 2));
}

main().catch(console.error);
