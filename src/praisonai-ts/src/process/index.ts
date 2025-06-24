export interface ProcessConfig {
  maxRetries?: number;
  timeout?: number;
  metadata?: Record<string, any>;
}

export interface Process {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  config: ProcessConfig;
  start(): Promise<void>;
  stop(): Promise<void>;
  getStatus(): string;
  getResult(): any;
}

export class BaseProcess implements Process {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  config: ProcessConfig;
  private result: any;

  constructor(id: string, config: ProcessConfig = {}) {
    this.id = id;
    this.status = 'pending';
    this.config = {
      maxRetries: 3,
      timeout: 30000,
      ...config
    };
  }

  async start(): Promise<void> {
    this.status = 'running';
    try {
      // Implement process logic here
      this.status = 'completed';
    } catch (error) {
      this.status = 'failed';
      throw error;
    }
  }

  async stop(): Promise<void> {
    if (this.status === 'running') {
      this.status = 'failed';
    }
  }

  getStatus(): string {
    return this.status;
  }

  getResult(): any {
    return this.result;
  }
}
