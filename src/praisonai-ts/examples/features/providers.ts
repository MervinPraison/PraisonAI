/**
 * LLM Providers Example - Using different LLM providers
 * 
 * Run: npx ts-node examples/features/providers.ts
 */

import { Agent } from '../../src';

async function main() {
  // OpenAI (default)
  console.log("=== OpenAI Agent ===");
  const openaiAgent = new Agent({
    instructions: "You are a helpful assistant.",
    llm: "gpt-4o-mini"  // or just omit for default
  });
  await openaiAgent.chat("Hello from OpenAI!");

  // Anthropic Claude
  console.log("\n=== Anthropic Agent ===");
  const anthropicAgent = new Agent({
    instructions: "You are a helpful assistant.",
    llm: "anthropic/claude-3-haiku-20240307"
  });
  // Uncomment if you have ANTHROPIC_API_KEY set
  // await anthropicAgent.chat("Hello from Anthropic!");

  // Google Gemini
  console.log("\n=== Google Agent ===");
  const googleAgent = new Agent({
    instructions: "You are a helpful assistant.",
    llm: "google/gemini-1.5-flash"
  });
  // Uncomment if you have GOOGLE_API_KEY set
  // await googleAgent.chat("Hello from Google!");

  // Model string formats
  console.log("\n=== Model String Formats ===");
  console.log("Supported formats:");
  console.log("  - 'gpt-4o-mini' (defaults to OpenAI)");
  console.log("  - 'openai/gpt-4o'");
  console.log("  - 'anthropic/claude-3-sonnet-20240229'");
  console.log("  - 'google/gemini-1.5-pro'");
}

main().catch(console.error);
