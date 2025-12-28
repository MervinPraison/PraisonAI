/**
 * Workflow Pattern - Step-based pipeline with agent integration
 * 
 * Run: npx ts-node examples/patterns/workflow.ts
 */

import { Agent, Workflow } from '../../src';

// Create agents for the workflow
const researcher = new Agent({
  instructions: "You are a research specialist. Research the given topic thoroughly.",
  name: "Researcher"
});

const analyzer = new Agent({
  instructions: "You are a data analyst. Analyze the research and extract key insights.",
  name: "Analyzer"
});

const writer = new Agent({
  instructions: "You are a professional writer. Write a clear report based on the analysis.",
  name: "Writer"
});

// Create a workflow with agent steps
const workflow = new Workflow("Research Pipeline")
  .agent(researcher, "Research the topic")
  .agent(analyzer, "Analyze the research findings")
  .agent(writer, "Write a summary report");

// Run the workflow
workflow.run("Artificial Intelligence trends in 2025").then(result => {
  console.log("\n=== Workflow Results ===");
  console.log(`Steps completed: ${result.results.length}`);
  console.log(`Final output:\n${result.output}`);
  
  // Access individual step results
  result.results.forEach((step, i) => {
    console.log(`\nStep ${i + 1} (${step.stepName}): ${step.status} in ${step.duration}ms`);
  });
});
