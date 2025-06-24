export interface TaskConfig {
  priority?: number;
  deadline?: Date;
  dependencies?: string[];
  metadata?: Record<string, any>;
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
