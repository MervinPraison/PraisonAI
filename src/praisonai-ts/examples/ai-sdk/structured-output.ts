/**
 * AI SDK Structured Output Example
 * 
 * Demonstrates generating structured JSON output using schemas.
 * 
 * Usage:
 *   npx ts-node examples/ai-sdk/structured-output.ts
 * 
 * Required environment variables:
 *   OPENAI_API_KEY - Your OpenAI API key
 */

import { createAISDKBackend } from '../../src/llm/providers/ai-sdk';

// Define the schema for structured output
const recipeSchema = {
  type: 'object',
  properties: {
    name: {
      type: 'string',
      description: 'Name of the recipe'
    },
    ingredients: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          amount: { type: 'string' },
          unit: { type: 'string' }
        },
        required: ['name', 'amount']
      },
      description: 'List of ingredients'
    },
    steps: {
      type: 'array',
      items: { type: 'string' },
      description: 'Cooking steps'
    },
    prepTime: {
      type: 'number',
      description: 'Preparation time in minutes'
    },
    cookTime: {
      type: 'number',
      description: 'Cooking time in minutes'
    },
    servings: {
      type: 'number',
      description: 'Number of servings'
    }
  },
  required: ['name', 'ingredients', 'steps']
};

interface Recipe {
  name: string;
  ingredients: Array<{
    name: string;
    amount: string;
    unit?: string;
  }>;
  steps: string[];
  prepTime?: number;
  cookTime?: number;
  servings?: number;
}

async function main() {
  console.log('AI SDK Structured Output Example\n');

  const backend = createAISDKBackend('openai/gpt-4o-mini', {
    timeout: 30000,
  });

  console.log(`Provider: ${backend.providerId}`);
  console.log(`Model: ${backend.modelId}\n`);

  console.log('Generating a recipe in structured JSON format...\n');

  const result = await backend.generateObject<Recipe>({
    messages: [
      { 
        role: 'system', 
        content: 'You are a helpful cooking assistant. Generate recipes in the requested format.' 
      },
      { 
        role: 'user', 
        content: 'Give me a simple recipe for chocolate chip cookies.' 
      }
    ],
    schema: recipeSchema,
    temperature: 0.7,
  });

  console.log('Generated Recipe:');
  console.log('================\n');
  
  const recipe = result.object;
  
  console.log(`📝 ${recipe.name}`);
  console.log();
  
  if (recipe.prepTime || recipe.cookTime) {
    console.log(`⏱️  Prep: ${recipe.prepTime || 'N/A'} min | Cook: ${recipe.cookTime || 'N/A'} min`);
  }
  if (recipe.servings) {
    console.log(`🍽️  Servings: ${recipe.servings}`);
  }
  console.log();
  
  console.log('Ingredients:');
  for (const ing of recipe.ingredients) {
    const unit = ing.unit ? ` ${ing.unit}` : '';
    console.log(`  • ${ing.amount}${unit} ${ing.name}`);
  }
  console.log();
  
  console.log('Steps:');
  recipe.steps.forEach((step, i) => {
    console.log(`  ${i + 1}. ${step}`);
  });
  
  console.log('\n---');
  console.log('Usage:', result.usage);
}

main().catch(console.error);
