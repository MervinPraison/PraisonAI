/**
 * Guardrails Example - Input/output validation for agents
 * 
 * Run: npx ts-node examples/features/guardrails.ts
 */

import { Agent, LLMGuardrail } from '../../src';

async function main() {
  // Create an LLM-based guardrail
  const contentGuardrail = new LLMGuardrail({
    name: "ContentSafety",
    criteria: "Content must be professional, non-offensive, and factually accurate",
    llm: "gpt-4o-mini",
    threshold: 0.7,
    verbose: true
  });

  // Create agent
  const agent = new Agent({
    instructions: "You are a helpful assistant that provides accurate information.",
    verbose: true
  });

  // Example: Check content before responding
  const userInput = "Tell me about artificial intelligence";
  
  // Validate input using check()
  const inputCheck = await contentGuardrail.check(userInput);
  console.log("Input validation:", inputCheck);

  if (inputCheck.status === 'passed') {
    const response = await agent.chat(userInput);
    
    // Validate output
    const outputCheck = await contentGuardrail.check(response);
    console.log("Output validation:", outputCheck);
    
    if (outputCheck.status === 'passed') {
      console.log("\n✅ Response passed guardrails");
    } else {
      console.log("\n❌ Response failed guardrails:", outputCheck.reasoning);
    }
  } else {
    console.log("❌ Input failed guardrails:", inputCheck.reasoning);
  }
}

main().catch(console.error);
