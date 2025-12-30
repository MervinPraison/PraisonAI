/**
 * AI SDK Structured Output Example
 * 
 * Demonstrates generating typed JSON objects with Zod schemas.
 * 
 * Usage:
 *   npx ts-node structured-output.ts
 * 
 * Environment:
 *   OPENAI_API_KEY - Your OpenAI API key
 */

import { generateObject } from 'ai';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';

// Define schema for a person profile
const PersonSchema = z.object({
  name: z.string().describe('Full name'),
  age: z.number().describe('Age in years'),
  occupation: z.string().describe('Job title'),
  city: z.string().describe('City of residence'),
  interests: z.array(z.string()).describe('List of hobbies/interests'),
  bio: z.string().describe('Short biography'),
});

// Define schema for a recipe
const RecipeSchema = z.object({
  name: z.string().describe('Recipe name'),
  cuisine: z.string().describe('Type of cuisine'),
  prepTime: z.number().describe('Preparation time in minutes'),
  cookTime: z.number().describe('Cooking time in minutes'),
  servings: z.number().describe('Number of servings'),
  ingredients: z.array(z.object({
    item: z.string(),
    amount: z.string(),
  })).describe('List of ingredients'),
  instructions: z.array(z.string()).describe('Step-by-step instructions'),
});

async function main() {
  console.log('Generating structured output with Zod schemas...\n');

  // Generate a person profile
  console.log('1. Generating a fictional person profile...');
  const personResult = await generateObject({
    model: openai('gpt-4o-mini'),
    schema: PersonSchema,
    prompt: 'Generate a fictional software engineer profile.',
  });

  console.log('Person:', JSON.stringify(personResult.object, null, 2));

  // Generate a recipe
  console.log('\n2. Generating a recipe...');
  const recipeResult = await generateObject({
    model: openai('gpt-4o-mini'),
    schema: RecipeSchema,
    prompt: 'Generate a simple pasta recipe.',
  });

  console.log('Recipe:', JSON.stringify(recipeResult.object, null, 2));

  // Type-safe access
  console.log('\n3. Type-safe access:');
  console.log(`  Person name: ${personResult.object.name}`);
  console.log(`  Person age: ${personResult.object.age}`);
  console.log(`  Recipe name: ${recipeResult.object.name}`);
  console.log(`  Total time: ${recipeResult.object.prepTime + recipeResult.object.cookTime} minutes`);
}

main().catch(console.error);
