/**
 * Planning System Unit Tests (TDD - Write tests first)
 */

import { describe, it, expect } from '@jest/globals';

describe('Planning System', () => {
  describe('Plan', () => {
    it('should create a plan', async () => {
      const { Plan } = await import('../../../src/planning');
      const plan = new Plan({ name: 'Test Plan' });
      expect(plan.name).toBe('Test Plan');
    });

    it('should add steps', async () => {
      const { Plan, PlanStep } = await import('../../../src/planning');
      const plan = new Plan({ name: 'Test' });
      plan.addStep(new PlanStep({ description: 'Step 1' }));
      plan.addStep(new PlanStep({ description: 'Step 2' }));
      expect(plan.steps.length).toBe(2);
    });
  });

  describe('TodoList', () => {
    it('should create a todo list', async () => {
      const { TodoList } = await import('../../../src/planning');
      const todos = new TodoList();
      expect(todos.items.length).toBe(0);
    });

    it('should add items', async () => {
      const { TodoList, TodoItem } = await import('../../../src/planning');
      const todos = new TodoList();
      todos.add(new TodoItem({ content: 'Task 1' }));
      todos.add(new TodoItem({ content: 'Task 2' }));
      expect(todos.items.length).toBe(2);
    });

    it('should mark items complete', async () => {
      const { TodoList, TodoItem } = await import('../../../src/planning');
      const todos = new TodoList();
      const item = new TodoItem({ content: 'Task 1' });
      todos.add(item);
      item.complete();
      expect(item.status).toBe('completed');
    });
  });
});
