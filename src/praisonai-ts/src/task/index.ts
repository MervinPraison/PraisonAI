/**
 * Task Module for PraisonAI TypeScript SDK
 * 
 * Python parity with praisonaiagents task types
 */

export interface TaskConfig {
  priority?: number;
  deadline?: Date;
  dependencies?: string[];
  metadata?: Record<string, any>;
}

/**
 * Task output result.
 * Python parity: praisonaiagents/task
 */
export interface TaskOutput {
  taskId: string;
  status: 'success' | 'failure' | 'partial';
  result?: any;
  error?: string;
  duration?: number;
  metadata?: Record<string, any>;
}

/**
 * Create a task output.
 */
export function createTaskOutput(
  taskId: string,
  status: 'success' | 'failure' | 'partial',
  result?: any,
  error?: string
): TaskOutput {
  return {
    taskId,
    status,
    result,
    error,
  };
}

export interface Task {
  id: string;
  name: string;
  description: string;
  status: 'pending' | 'in-progress' | 'completed' | 'failed';
  config: TaskConfig;
  execute(): Promise<void>;
  cancel(): Promise<void>;
}

export class BaseTask implements Task {
  id: string;
  name: string;
  description: string;
  status: 'pending' | 'in-progress' | 'completed' | 'failed';
  config: TaskConfig;

  constructor(
    id: string,
    name: string,
    description: string,
    config: TaskConfig = {}
  ) {
    this.id = id;
    this.name = name;
    this.description = description;
    this.status = 'pending';
    this.config = {
      priority: 1,
      ...config
    };
  }

  async execute(): Promise<void> {
    this.status = 'in-progress';
    try {
      // Implement task execution logic here
      this.status = 'completed';
    } catch (error) {
      this.status = 'failed';
      throw error;
    }
  }

  async cancel(): Promise<void> {
    if (this.status === 'in-progress') {
      this.status = 'failed';
    }
  }
}
