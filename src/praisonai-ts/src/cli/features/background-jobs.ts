/**
 * Background Jobs - Persisted job queue with adapter support
 */

export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type JobPriority = 'low' | 'normal' | 'high' | 'critical';

export interface Job<T = any> {
  id: string;
  name: string;
  data: T;
  status: JobStatus;
  priority: JobPriority;
  attempts: number;
  maxAttempts: number;
  createdAt: Date;
  startedAt?: Date;
  completedAt?: Date;
  result?: any;
  error?: string;
  progress?: number;
  metadata?: Record<string, any>;
}

export interface JobQueueConfig {
  name?: string;
  concurrency?: number;
  maxAttempts?: number;
  retryDelay?: number;
  storage?: JobStorageAdapter;
}

export interface JobStorageAdapter {
  save(job: Job): Promise<void>;
  get(id: string): Promise<Job | null>;
  getAll(): Promise<Job[]>;
  getByStatus(status: JobStatus): Promise<Job[]>;
  update(id: string, updates: Partial<Job>): Promise<void>;
  delete(id: string): Promise<void>;
  clear(): Promise<void>;
}

export type JobHandler<T = any, R = any> = (job: Job<T>, context: JobContext) => Promise<R>;

export interface JobContext {
  updateProgress: (progress: number) => Promise<void>;
  log: (message: string) => void;
}

/**
 * In-memory job storage adapter
 */
export class MemoryJobStorage implements JobStorageAdapter {
  private jobs: Map<string, Job> = new Map();

  async save(job: Job): Promise<void> {
    this.jobs.set(job.id, { ...job });
  }

  async get(id: string): Promise<Job | null> {
    return this.jobs.get(id) || null;
  }

  async getAll(): Promise<Job[]> {
    return Array.from(this.jobs.values());
  }

  async getByStatus(status: JobStatus): Promise<Job[]> {
    return Array.from(this.jobs.values()).filter(j => j.status === status);
  }

  async update(id: string, updates: Partial<Job>): Promise<void> {
    const job = this.jobs.get(id);
    if (job) {
      this.jobs.set(id, { ...job, ...updates });
    }
  }

  async delete(id: string): Promise<void> {
    this.jobs.delete(id);
  }

  async clear(): Promise<void> {
    this.jobs.clear();
  }
}

/**
 * File-based job storage adapter
 */
export class FileJobStorage implements JobStorageAdapter {
  private filePath: string;
  private jobs: Map<string, Job> = new Map();
  private initialized: boolean = false;

  constructor(filePath: string) {
    this.filePath = filePath;
  }

  private async init(): Promise<void> {
    if (this.initialized) return;
    
    try {
      const fs = await import('fs/promises');
      const content = await fs.readFile(this.filePath, 'utf-8');
      const data = JSON.parse(content);
      for (const job of data) {
        job.createdAt = new Date(job.createdAt);
        if (job.startedAt) job.startedAt = new Date(job.startedAt);
        if (job.completedAt) job.completedAt = new Date(job.completedAt);
        this.jobs.set(job.id, job);
      }
    } catch {
      // File doesn't exist yet
    }
    this.initialized = true;
  }

  private async persist(): Promise<void> {
    const fs = await import('fs/promises');
    const data = Array.from(this.jobs.values());
    await fs.writeFile(this.filePath, JSON.stringify(data, null, 2));
  }

  async save(job: Job): Promise<void> {
    await this.init();
    this.jobs.set(job.id, { ...job });
    await this.persist();
  }

  async get(id: string): Promise<Job | null> {
    await this.init();
    return this.jobs.get(id) || null;
  }

  async getAll(): Promise<Job[]> {
    await this.init();
    return Array.from(this.jobs.values());
  }

  async getByStatus(status: JobStatus): Promise<Job[]> {
    await this.init();
    return Array.from(this.jobs.values()).filter(j => j.status === status);
  }

  async update(id: string, updates: Partial<Job>): Promise<void> {
    await this.init();
    const job = this.jobs.get(id);
    if (job) {
      this.jobs.set(id, { ...job, ...updates });
      await this.persist();
    }
  }

  async delete(id: string): Promise<void> {
    await this.init();
    this.jobs.delete(id);
    await this.persist();
  }

  async clear(): Promise<void> {
    this.jobs.clear();
    await this.persist();
  }
}

/**
 * Job Queue class
 */
export class JobQueue {
  private config: JobQueueConfig;
  private storage: JobStorageAdapter;
  private handlers: Map<string, JobHandler> = new Map();
  private running: boolean = false;
  private activeJobs: number = 0;
  private processInterval?: NodeJS.Timeout;

  constructor(config: JobQueueConfig = {}) {
    this.config = {
      name: 'default',
      concurrency: 1,
      maxAttempts: 3,
      retryDelay: 1000,
      ...config
    };
    this.storage = config.storage || new MemoryJobStorage();
  }

  /**
   * Register a job handler
   */
  register<T = any, R = any>(name: string, handler: JobHandler<T, R>): void {
    this.handlers.set(name, handler);
  }

  /**
   * Add a job to the queue
   */
  async add<T = any>(name: string, data: T, options: Partial<Job<T>> = {}): Promise<Job<T>> {
    const job: Job<T> = {
      id: `job_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      name,
      data,
      status: 'pending',
      priority: options.priority || 'normal',
      attempts: 0,
      maxAttempts: options.maxAttempts || this.config.maxAttempts || 3,
      createdAt: new Date(),
      metadata: options.metadata
    };

    await this.storage.save(job);
    return job;
  }

  /**
   * Get a job by ID
   */
  async get(id: string): Promise<Job | null> {
    return this.storage.get(id);
  }

  /**
   * Get all jobs
   */
  async getAll(): Promise<Job[]> {
    return this.storage.getAll();
  }

  /**
   * Get jobs by status
   */
  async getByStatus(status: JobStatus): Promise<Job[]> {
    return this.storage.getByStatus(status);
  }

  /**
   * Cancel a job
   */
  async cancel(id: string): Promise<boolean> {
    const job = await this.storage.get(id);
    if (!job || job.status === 'running' || job.status === 'completed') {
      return false;
    }
    await this.storage.update(id, { status: 'cancelled' });
    return true;
  }

  /**
   * Retry a failed job
   */
  async retry(id: string): Promise<boolean> {
    const job = await this.storage.get(id);
    if (!job || job.status !== 'failed') {
      return false;
    }
    await this.storage.update(id, { 
      status: 'pending', 
      attempts: 0, 
      error: undefined 
    });
    return true;
  }

  /**
   * Start processing jobs
   */
  start(): void {
    if (this.running) return;
    this.running = true;
    this.processInterval = setInterval(() => this.process(), 100);
  }

  /**
   * Stop processing jobs
   */
  stop(): void {
    this.running = false;
    if (this.processInterval) {
      clearInterval(this.processInterval);
      this.processInterval = undefined;
    }
  }

  /**
   * Process pending jobs
   */
  private async process(): Promise<void> {
    if (!this.running) return;
    if (this.activeJobs >= (this.config.concurrency || 1)) return;

    const pendingJobs = await this.storage.getByStatus('pending');
    
    // Sort by priority and creation time
    const priorityOrder: Record<JobPriority, number> = {
      critical: 0,
      high: 1,
      normal: 2,
      low: 3
    };
    
    pendingJobs.sort((a, b) => {
      const priorityDiff = priorityOrder[a.priority] - priorityOrder[b.priority];
      if (priorityDiff !== 0) return priorityDiff;
      return a.createdAt.getTime() - b.createdAt.getTime();
    });

    for (const job of pendingJobs) {
      if (this.activeJobs >= (this.config.concurrency || 1)) break;
      this.runJob(job);
    }
  }

  /**
   * Run a single job
   */
  private async runJob(job: Job): Promise<void> {
    const handler = this.handlers.get(job.name);
    if (!handler) {
      await this.storage.update(job.id, {
        status: 'failed',
        error: `No handler registered for job type: ${job.name}`
      });
      return;
    }

    this.activeJobs++;
    await this.storage.update(job.id, {
      status: 'running',
      startedAt: new Date(),
      attempts: job.attempts + 1
    });

    const context: JobContext = {
      updateProgress: async (progress: number) => {
        await this.storage.update(job.id, { progress });
      },
      log: (message: string) => {
        console.log(`[Job ${job.id}] ${message}`);
      }
    };

    try {
      const result = await handler(job, context);
      await this.storage.update(job.id, {
        status: 'completed',
        completedAt: new Date(),
        result,
        progress: 100
      });
    } catch (error: any) {
      const attempts = job.attempts + 1;
      
      if (attempts < job.maxAttempts) {
        // Retry after delay
        setTimeout(async () => {
          await this.storage.update(job.id, {
            status: 'pending',
            error: error.message
          });
        }, this.config.retryDelay || 1000);
      } else {
        await this.storage.update(job.id, {
          status: 'failed',
          completedAt: new Date(),
          error: error.message
        });
      }
    } finally {
      this.activeJobs--;
    }
  }

  /**
   * Process a job immediately (bypass queue)
   */
  async processNow(id: string): Promise<any> {
    const job = await this.storage.get(id);
    if (!job) throw new Error(`Job ${id} not found`);

    const handler = this.handlers.get(job.name);
    if (!handler) throw new Error(`No handler for job type: ${job.name}`);

    await this.storage.update(job.id, {
      status: 'running',
      startedAt: new Date()
    });

    const context: JobContext = {
      updateProgress: async (progress: number) => {
        await this.storage.update(job.id, { progress });
      },
      log: console.log
    };

    try {
      const result = await handler(job, context);
      await this.storage.update(job.id, {
        status: 'completed',
        completedAt: new Date(),
        result
      });
      return result;
    } catch (error: any) {
      await this.storage.update(job.id, {
        status: 'failed',
        completedAt: new Date(),
        error: error.message
      });
      throw error;
    }
  }

  /**
   * Get queue stats
   */
  async getStats(): Promise<{
    pending: number;
    running: number;
    completed: number;
    failed: number;
    cancelled: number;
  }> {
    const all = await this.storage.getAll();
    return {
      pending: all.filter(j => j.status === 'pending').length,
      running: all.filter(j => j.status === 'running').length,
      completed: all.filter(j => j.status === 'completed').length,
      failed: all.filter(j => j.status === 'failed').length,
      cancelled: all.filter(j => j.status === 'cancelled').length
    };
  }

  /**
   * Clear completed/failed jobs
   */
  async cleanup(olderThan?: Date): Promise<number> {
    const all = await this.storage.getAll();
    let count = 0;

    for (const job of all) {
      if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
        if (!olderThan || (job.completedAt && job.completedAt < olderThan)) {
          await this.storage.delete(job.id);
          count++;
        }
      }
    }

    return count;
  }
}

/**
 * Create a job queue
 */
export function createJobQueue(config?: JobQueueConfig): JobQueue {
  return new JobQueue(config);
}

/**
 * Create a file-based job storage
 */
export function createFileJobStorage(filePath: string): FileJobStorage {
  return new FileJobStorage(filePath);
}
