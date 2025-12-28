/**
 * Planning Example - Using planning mode for complex tasks
 * 
 * Run: npx ts-node examples/features/planning.ts
 */

import { Agent, Plan, PlanStep, TodoList, TodoItem } from '../../src';

async function main() {
  // Create a plan for a complex task
  console.log("=== Creating a Plan ===");
  const plan = new Plan({
    name: "Build a Web App",
    description: "Plan to build a simple web application"
  });

  // Add steps to the plan
  plan.addStep(new PlanStep({ description: "Initialize project structure" }));
  plan.addStep(new PlanStep({ description: "Build API endpoints" }));
  plan.addStep(new PlanStep({ description: "Create UI components" }));
  plan.addStep(new PlanStep({ description: "Write and run tests" }));
  plan.addStep(new PlanStep({ description: "Deploy to production" }));

  console.log("Plan created with", plan.steps.length, "steps");

  // Create a todo list
  console.log("\n=== Creating a Todo List ===");
  const todos = new TodoList();
  
  todos.add(new TodoItem({ content: "Research frameworks", priority: "high" }));
  todos.add(new TodoItem({ content: "Design database schema", priority: "medium" }));
  todos.add(new TodoItem({ content: "Write documentation", priority: "low" }));

  console.log("Todo list has", todos.items.length, "items");

  // Create agent with planning context
  const agent = new Agent({
    instructions: `You are a project planning assistant.
    
Current plan: ${plan.name}
Steps: ${plan.steps.map((s: PlanStep) => s.description).join(', ')}

Help the user execute this plan.`,
    verbose: true
  });

  await agent.chat("What should I do first?");
}

main().catch(console.error);
