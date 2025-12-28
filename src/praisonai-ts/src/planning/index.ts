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

/**
 * PlanningAgent - Agent with built-in planning capabilities
 * 
 * @example Simple usage (4 lines)
 * ```typescript
 * import { PlanningAgent } from 'praisonai';
 * 
 * const agent = new PlanningAgent({ instructions: 'You break down tasks into steps' });
 * const result = await agent.planAndExecute('Build a web scraper');
 * console.log(result.plan);  // The plan that was created
 * console.log(result.results);  // Results from each step
 * ```
 */
export interface PlanningAgentConfig {
  instructions?: string;
  name?: string;
  llm?: string;
  verbose?: boolean;
  maxSteps?: number;
}

export interface PlanResult {
  plan: Plan;
  results: string[];
  success: boolean;
}

// Import Agent dynamically to avoid circular dependency
let AgentClass: any = null;

async function getAgentClass() {
  if (!AgentClass) {
    const { Agent } = await import('../agent/simple');
    AgentClass = Agent;
  }
  return AgentClass;
}

export class PlanningAgent {
  private config: PlanningAgentConfig;
  private agent: any = null;
  private currentPlan: Plan | null = null;

  constructor(config: PlanningAgentConfig = {}) {
    this.config = {
      instructions: config.instructions || 'You are a planning agent that breaks down complex tasks into steps.',
      name: config.name || 'PlanningAgent',
      llm: config.llm,
      verbose: config.verbose ?? true,
      maxSteps: config.maxSteps ?? 10
    };
  }

  private async getAgent() {
    if (!this.agent) {
      const Agent = await getAgentClass();
      this.agent = new Agent({
        name: this.config.name,
        instructions: this.config.instructions,
        llm: this.config.llm,
        verbose: this.config.verbose
      });
    }
    return this.agent;
  }

  /**
   * Create a plan for a task
   */
  async createPlan(task: string): Promise<Plan> {
    const agent = await this.getAgent();
    
    const planPrompt = `Create a step-by-step plan for: ${task}

Return ONLY a numbered list of steps, one per line. Example:
1. First step
2. Second step
3. Third step`;

    const response = await agent.chat(planPrompt);
    
    // Parse the response into steps
    const plan = new Plan({ name: task });
    const lines = response.split('\n').filter((l: string) => l.trim());
    
    for (const line of lines) {
      // Extract step description (remove numbering)
      const match = line.match(/^\d+[\.\)]\s*(.+)/);
      if (match) {
        plan.addStep(new PlanStep({ description: match[1].trim() }));
      }
    }

    this.currentPlan = plan;
    return plan;
  }

  /**
   * Execute a single step
   */
  async executeStep(step: PlanStep): Promise<string> {
    const agent = await this.getAgent();
    step.start();
    
    try {
      const response = await agent.chat(`Execute this step: ${step.description}`);
      step.complete();
      return response;
    } catch (error) {
      step.fail();
      throw error;
    }
  }

  /**
   * Plan and execute a task in one call
   */
  async planAndExecute(task: string): Promise<PlanResult> {
    const plan = await this.createPlan(task);
    const results: string[] = [];
    let success = true;

    plan.start();

    for (const step of plan.steps.slice(0, this.config.maxSteps)) {
      try {
        if (this.config.verbose) {
          console.log(`[${plan.getProgress().percentage}%] Executing: ${step.description}`);
        }
        const result = await this.executeStep(step);
        results.push(result);
      } catch (error) {
        success = false;
        results.push(`Error: ${error}`);
        break;
      }
    }

    if (success) {
      plan.complete();
    }

    return { plan, results, success };
  }

  /**
   * Get the current plan
   */
  getPlan(): Plan | null {
    return this.currentPlan;
  }

  /**
   * Simple chat (without planning)
   */
  async chat(message: string): Promise<string> {
    const agent = await this.getAgent();
    return agent.chat(message);
  }
}

/**
 * Create a planning agent
 */
export function createPlanningAgent(config?: PlanningAgentConfig): PlanningAgent {
  return new PlanningAgent(config);
}

/**
 * TaskAgent - Agent with built-in todo list management
 * 
 * @example Simple usage (4 lines)
 * ```typescript
 * import { TaskAgent } from 'praisonai';
 * 
 * const agent = new TaskAgent();
 * await agent.addTask('Fix critical bug', 'high');
 * await agent.addTask('Write docs', 'medium');
 * console.log(agent.getPendingTasks());
 * ```
 */
export class TaskAgent {
  private todos: TodoList;
  private agent: any = null;
  private config: { name?: string; llm?: string; verbose?: boolean };

  constructor(config?: { name?: string; llm?: string; verbose?: boolean }) {
    this.todos = new TodoList('Agent Tasks');
    this.config = config || {};
  }

  private async getAgent() {
    if (!this.agent) {
      const Agent = await getAgentClass();
      this.agent = new Agent({
        name: this.config.name || 'TaskAgent',
        instructions: 'You are a task management assistant.',
        llm: this.config.llm,
        verbose: this.config.verbose ?? false
      });
    }
    return this.agent;
  }

  /**
   * Add a task
   */
  addTask(content: string, priority: 'low' | 'medium' | 'high' = 'medium'): TodoItem {
    const item = new TodoItem({ content, priority });
    this.todos.add(item);
    return item;
  }

  /**
   * Complete a task by content (partial match)
   */
  completeTask(contentMatch: string): boolean {
    const item = this.todos.items.find(t => 
      t.content.toLowerCase().includes(contentMatch.toLowerCase()) && t.status !== 'completed'
    );
    if (item) {
      item.complete();
      return true;
    }
    return false;
  }

  /**
   * Get pending tasks
   */
  getPendingTasks(): TodoItem[] {
    return this.todos.getPending();
  }

  /**
   * Get all tasks
   */
  getAllTasks(): TodoItem[] {
    return [...this.todos.items];
  }

  /**
   * Get progress
   */
  getProgress(): { completed: number; total: number; percentage: number } {
    return this.todos.getProgress();
  }

  /**
   * Clear all tasks
   */
  clearTasks(): void {
    this.todos.clear();
  }

  /**
   * Chat with AI about tasks
   */
  async chat(message: string): Promise<string> {
    const agent = await this.getAgent();
    const context = `Current tasks:\n${this.todos.items.map(t => 
      `- [${t.status}] ${t.content} (${t.priority})`
    ).join('\n') || 'No tasks'}`;
    
    return agent.chat(`${context}\n\nUser: ${message}`);
  }
}

/**
 * Create a task agent
 */
export function createTaskAgent(config?: { name?: string; llm?: string; verbose?: boolean }): TaskAgent {
  return new TaskAgent(config);
}
