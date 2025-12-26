/**
 * Planning System Example
 * Demonstrates plans, steps, and todo lists
 */

import { Plan, PlanStep, TodoList, TodoItem, PlanStorage, createPlan, createTodoList } from 'praisonai';

async function main() {
  // Create a project plan
  console.log('=== Project Plan ===');
  const plan = createPlan({ 
    name: 'Build AI Agent',
    description: 'Create a fully functional AI agent'
  });

  plan.addStep(new PlanStep({ description: 'Design agent architecture' }));
  plan.addStep(new PlanStep({ description: 'Implement core functionality' }));
  plan.addStep(new PlanStep({ description: 'Add tool support' }));
  plan.addStep(new PlanStep({ description: 'Write tests' }));
  plan.addStep(new PlanStep({ description: 'Deploy to production' }));

  console.log('Plan:', plan.name);
  console.log('Steps:', plan.steps.length);

  // Execute steps
  plan.start();
  plan.steps[0].start();
  plan.steps[0].complete();
  plan.steps[1].start();
  plan.steps[1].complete();

  const progress = plan.getProgress();
  console.log(`Progress: ${progress.completed}/${progress.total} (${progress.percentage}%)`);

  // Create todo list
  console.log('\n=== Todo List ===');
  const todos = createTodoList('Sprint Tasks');

  todos.add(new TodoItem({ content: 'Review PR #123', priority: 'high' }));
  todos.add(new TodoItem({ content: 'Fix bug in router', priority: 'high' }));
  todos.add(new TodoItem({ content: 'Update documentation', priority: 'medium' }));
  todos.add(new TodoItem({ content: 'Refactor tests', priority: 'low' }));

  console.log('Total items:', todos.items.length);
  console.log('High priority:', todos.getByPriority('high').length);

  // Complete some items
  todos.items[0].complete();
  todos.items[1].start();

  console.log('Pending:', todos.getPending().length);
  console.log('Completed:', todos.getCompleted().length);

  const todoProgress = todos.getProgress();
  console.log(`Progress: ${todoProgress.completed}/${todoProgress.total} (${todoProgress.percentage}%)`);

  // Use storage
  console.log('\n=== Plan Storage ===');
  const storage = new PlanStorage();
  storage.savePlan(plan);
  storage.saveTodoList(todos);

  console.log('Saved plans:', storage.listPlans().length);
  console.log('Saved todo lists:', storage.listTodoLists().length);

  // Retrieve
  const retrieved = storage.getPlan(plan.id);
  console.log('Retrieved plan:', retrieved?.name);
}

main().catch(console.error);
