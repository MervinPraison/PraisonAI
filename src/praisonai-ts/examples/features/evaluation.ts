/**
 * Evaluation Example - Testing agent accuracy and performance
 * 
 * Run: npx ts-node examples/features/evaluation.ts
 */

import { Agent, accuracyEval, performanceEval } from '../../src';

async function main() {
  // Create an agent to evaluate
  const agent = new Agent({
    instructions: "You are a math tutor. Answer math questions accurately.",
    llm: "gpt-4o-mini",
    verbose: false
  });

  console.log("=== Accuracy Evaluation ===");
  
  // Test accuracy with expected outputs
  const testCases = [
    { input: "What is 2 + 2?", expected: "4" },
    { input: "What is 10 * 5?", expected: "50" },
    { input: "What is 100 / 4?", expected: "25" }
  ];

  for (const test of testCases) {
    const response = await agent.chat(test.input);
    const passed = response.includes(test.expected);
    console.log(`  ${passed ? '✅' : '❌'} "${test.input}" → Expected: ${test.expected}`);
  }

  console.log("\n=== Performance Evaluation ===");
  
  // Measure response time
  const iterations = 3;
  const times: number[] = [];
  
  for (let i = 0; i < iterations; i++) {
    const start = Date.now();
    await agent.chat("What is 5 + 5?");
    const duration = Date.now() - start;
    times.push(duration);
    console.log(`  Run ${i + 1}: ${duration}ms`);
  }

  const avgTime = times.reduce((a, b) => a + b, 0) / times.length;
  console.log(`\n  Average: ${avgTime.toFixed(0)}ms`);
  console.log(`  Min: ${Math.min(...times)}ms`);
  console.log(`  Max: ${Math.max(...times)}ms`);
}

main().catch(console.error);
