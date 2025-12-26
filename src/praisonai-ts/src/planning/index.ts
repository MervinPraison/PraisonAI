/**
 * Planning System - Plans, Steps, and TodoLists
 */

export type PlanStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
export type TodoStatus = 'pending' | 'in_progress' | 'completed';

export interface PlanConfig {
  name: string;
  description?: string;
  metadata?: Record<string, any>;
}

export interface PlanStepConfig {
  description: string;
  status?: PlanStatus;
  order?: number;
  dependencies?: string[];
  metadata?: Record<string, any>;
}

export interface TodoItemConfig {
  content: string;
  priority?: 'low' | 'medium' | 'high';
  status?: TodoStatus;
  dueDate?: Date;
  metadata?: Record<string, any>;
}

/**
 * PlanStep - A single step in a plan
 */
export class PlanStep {
  readonly id: string;
  description: string;
  status: PlanStatus;
  order: number;
  dependencies: string[];
  metadata: Record<string, any>;
  startedAt?: number;
  completedAt?: number;

  constructor(config: PlanStepConfig) {
    this.id = `step_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    this.description = config.description;
    this.status = config.status ?? 'pending';
    this.order = config.order ?? 0;
    this.dependencies = config.dependencies ?? [];
    this.metadata = config.metadata ?? {};
  }

  start(): this {
    this.status = 'in_progress';
    this.startedAt = Date.now();
    return this;
  }

  complete(): this {
    this.status = 'completed';
    this.completedAt = Date.now();
    return this;
  }

  fail(): this {
    this.status = 'failed';
    this.completedAt = Date.now();
    return this;
  }

  cancel(): this {
    this.status = 'cancelled';
    return this;
  }
}

/**
 * Plan - A collection of steps to accomplish a goal
 */
export class Plan {
  readonly id: string;
  name: string;
  description?: string;
  steps: PlanStep[] = [];
  status: PlanStatus = 'pending';
  metadata: Record<string, any>;
  createdAt: number;
  updatedAt: number;

  constructor(config: PlanConfig) {
    this.id = `plan_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    this.name = config.name;
    this.description = config.description;
    this.metadata = config.metadata ?? {};
    this.createdAt = Date.now();
    this.updatedAt = Date.now();
  }

  addStep(step: PlanStep): this {
    step.order = this.steps.length;
    this.steps.push(step);
    this.updatedAt = Date.now();
    return this;
  }

  removeStep(stepId: string): boolean {
    const index = this.steps.findIndex(s => s.id === stepId);
    if (index >= 0) {
      this.steps.splice(index, 1);
      this.updatedAt = Date.now();
      return true;
    }
    return false;
  }

  getStep(stepId: string): PlanStep | undefined {
    return this.steps.find(s => s.id === stepId);
  }

  getNextStep(): PlanStep | undefined {
    return this.steps.find(s => s.status === 'pending');
  }

  getProgress(): { completed: number; total: number; percentage: number } {
    const completed = this.steps.filter(s => s.status === 'completed').length;
    const total = this.steps.length;
    return {
      completed,
      total,
      percentage: total > 0 ? Math.round((completed / total) * 100) : 0
    };
  }

  start(): this {
    this.status = 'in_progress';
    this.updatedAt = Date.now();
    return this;
  }

  complete(): this {
    this.status = 'completed';
    this.updatedAt = Date.now();
    return this;
  }
}

/**
 * TodoItem - A single todo item
 */
export class TodoItem {
  readonly id: string;
  content: string;
  priority: 'low' | 'medium' | 'high';
  status: TodoStatus;
  dueDate?: Date;
  metadata: Record<string, any>;
  createdAt: number;
  completedAt?: number;

  constructor(config: TodoItemConfig) {
    this.id = `todo_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    this.content = config.content;
    this.priority = config.priority ?? 'medium';
    this.status = config.status ?? 'pending';
    this.dueDate = config.dueDate;
    this.metadata = config.metadata ?? {};
    this.createdAt = Date.now();
  }

  start(): this {
    this.status = 'in_progress';
    return this;
  }

  complete(): this {
    this.status = 'completed';
    this.completedAt = Date.now();
    return this;
  }

  reset(): this {
    this.status = 'pending';
    this.completedAt = undefined;
    return this;
  }
}

/**
 * TodoList - A collection of todo items
 */
export class TodoList {
  readonly id: string;
  name: string;
  items: TodoItem[] = [];
  createdAt: number;

  constructor(name: string = 'Todo List') {
    this.id = `todolist_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    this.name = name;
    this.createdAt = Date.now();
  }

  add(item: TodoItem): this {
    this.items.push(item);
    return this;
  }

  remove(itemId: string): boolean {
    const index = this.items.findIndex(i => i.id === itemId);
    if (index >= 0) {
      this.items.splice(index, 1);
      return true;
    }
    return false;
  }

  get(itemId: string): TodoItem | undefined {
    return this.items.find(i => i.id === itemId);
  }

  getPending(): TodoItem[] {
    return this.items.filter(i => i.status === 'pending');
  }

  getCompleted(): TodoItem[] {
    return this.items.filter(i => i.status === 'completed');
  }

  getByPriority(priority: 'low' | 'medium' | 'high'): TodoItem[] {
    return this.items.filter(i => i.priority === priority);
  }

  getProgress(): { completed: number; total: number; percentage: number } {
    const completed = this.items.filter(i => i.status === 'completed').length;
    const total = this.items.length;
    return {
      completed,
      total,
      percentage: total > 0 ? Math.round((completed / total) * 100) : 0
    };
  }

  clear(): this {
    this.items = [];
    return this;
  }
}

/**
 * PlanStorage - Persist plans (in-memory implementation)
 */
export class PlanStorage {
  private plans: Map<string, Plan> = new Map();
  private todoLists: Map<string, TodoList> = new Map();

  savePlan(plan: Plan): void {
    this.plans.set(plan.id, plan);
  }

  getPlan(planId: string): Plan | undefined {
    return this.plans.get(planId);
  }

  deletePlan(planId: string): boolean {
    return this.plans.delete(planId);
  }

  listPlans(): Plan[] {
    return Array.from(this.plans.values());
  }

  saveTodoList(list: TodoList): void {
    this.todoLists.set(list.id, list);
  }

  getTodoList(listId: string): TodoList | undefined {
    return this.todoLists.get(listId);
  }

  deleteTodoList(listId: string): boolean {
    return this.todoLists.delete(listId);
  }

  listTodoLists(): TodoList[] {
    return Array.from(this.todoLists.values());
  }
}

/**
 * Create a Plan
 */
export function createPlan(config: PlanConfig): Plan {
  return new Plan(config);
}

/**
 * Create a TodoList
 */
export function createTodoList(name?: string): TodoList {
  return new TodoList(name);
}

/**
 * Create a PlanStorage
 */
export function createPlanStorage(): PlanStorage {
  return new PlanStorage();
}
