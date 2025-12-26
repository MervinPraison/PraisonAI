/**
 * Agent Scheduler - Cron-like scheduling for agent tasks
 */

export interface ScheduleConfig {
  id?: string;
  name: string;
  cron?: string;
  interval?: number; // milliseconds
  task: () => Promise<any>;
  enabled?: boolean;
  maxRuns?: number;
  onComplete?: (result: any) => void;
  onError?: (error: Error) => void;
}

export interface ScheduledTask {
  id: string;
  name: string;
  cron?: string;
  interval?: number;
  enabled: boolean;
  lastRun?: Date;
  nextRun?: Date;
  runCount: number;
  maxRuns?: number;
  status: 'idle' | 'running' | 'completed' | 'error';
  lastError?: string;
}

export interface SchedulerStats {
  totalTasks: number;
  activeTasks: number;
  totalRuns: number;
  errors: number;
}

/**
 * Parse cron expression (simplified: minute hour day month weekday)
 */
function parseCron(cron: string): { minute: number[]; hour: number[]; day: number[]; month: number[]; weekday: number[] } {
  const parts = cron.split(/\s+/);
  if (parts.length !== 5) {
    throw new Error('Invalid cron expression. Expected: minute hour day month weekday');
  }

  const parseField = (field: string, min: number, max: number): number[] => {
    if (field === '*') {
      return Array.from({ length: max - min + 1 }, (_, i) => min + i);
    }
    if (field.includes('/')) {
      const [, step] = field.split('/');
      const stepNum = parseInt(step);
      return Array.from({ length: Math.ceil((max - min + 1) / stepNum) }, (_, i) => min + i * stepNum);
    }
    if (field.includes(',')) {
      return field.split(',').map(n => parseInt(n));
    }
    if (field.includes('-')) {
      const [start, end] = field.split('-').map(n => parseInt(n));
      return Array.from({ length: end - start + 1 }, (_, i) => start + i);
    }
    return [parseInt(field)];
  };

  return {
    minute: parseField(parts[0], 0, 59),
    hour: parseField(parts[1], 0, 23),
    day: parseField(parts[2], 1, 31),
    month: parseField(parts[3], 1, 12),
    weekday: parseField(parts[4], 0, 6)
  };
}

/**
 * Get next run time from cron expression
 */
function getNextCronRun(cron: string, from: Date = new Date()): Date {
  const parsed = parseCron(cron);
  const next = new Date(from);
  next.setSeconds(0);
  next.setMilliseconds(0);
  next.setMinutes(next.getMinutes() + 1);

  for (let i = 0; i < 366 * 24 * 60; i++) { // Max 1 year search
    const minute = next.getMinutes();
    const hour = next.getHours();
    const day = next.getDate();
    const month = next.getMonth() + 1;
    const weekday = next.getDay();

    if (
      parsed.minute.includes(minute) &&
      parsed.hour.includes(hour) &&
      parsed.day.includes(day) &&
      parsed.month.includes(month) &&
      parsed.weekday.includes(weekday)
    ) {
      return next;
    }

    next.setMinutes(next.getMinutes() + 1);
  }

  throw new Error('Could not find next run time');
}

/**
 * Scheduler class
 */
export class Scheduler {
  private tasks: Map<string, { config: ScheduleConfig; task: ScheduledTask; timer?: NodeJS.Timeout }> = new Map();
  private running: boolean = false;
  private stats: SchedulerStats = {
    totalTasks: 0,
    activeTasks: 0,
    totalRuns: 0,
    errors: 0
  };

  /**
   * Add a scheduled task
   */
  add(config: ScheduleConfig): string {
    const id = config.id || `task_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    const task: ScheduledTask = {
      id,
      name: config.name,
      cron: config.cron,
      interval: config.interval,
      enabled: config.enabled ?? true,
      runCount: 0,
      maxRuns: config.maxRuns,
      status: 'idle'
    };

    if (config.cron) {
      task.nextRun = getNextCronRun(config.cron);
    } else if (config.interval) {
      task.nextRun = new Date(Date.now() + config.interval);
    }

    this.tasks.set(id, { config, task });
    this.stats.totalTasks++;

    if (this.running && task.enabled) {
      this.scheduleTask(id);
    }

    return id;
  }

  /**
   * Remove a task
   */
  remove(id: string): boolean {
    const entry = this.tasks.get(id);
    if (!entry) return false;

    if (entry.timer) {
      clearTimeout(entry.timer);
    }

    this.tasks.delete(id);
    this.stats.totalTasks--;
    return true;
  }

  /**
   * Enable a task
   */
  enable(id: string): boolean {
    const entry = this.tasks.get(id);
    if (!entry) return false;

    entry.task.enabled = true;
    if (this.running) {
      this.scheduleTask(id);
    }
    return true;
  }

  /**
   * Disable a task
   */
  disable(id: string): boolean {
    const entry = this.tasks.get(id);
    if (!entry) return false;

    entry.task.enabled = false;
    if (entry.timer) {
      clearTimeout(entry.timer);
      entry.timer = undefined;
    }
    return true;
  }

  /**
   * Start the scheduler
   */
  start(): void {
    if (this.running) return;
    this.running = true;

    for (const [id, entry] of this.tasks) {
      if (entry.task.enabled) {
        this.scheduleTask(id);
      }
    }
  }

  /**
   * Stop the scheduler
   */
  stop(): void {
    this.running = false;

    for (const entry of this.tasks.values()) {
      if (entry.timer) {
        clearTimeout(entry.timer);
        entry.timer = undefined;
      }
    }
  }

  /**
   * Schedule a task's next run
   */
  private scheduleTask(id: string): void {
    const entry = this.tasks.get(id);
    if (!entry || !entry.task.enabled || !this.running) return;

    // Check if max runs reached
    if (entry.task.maxRuns && entry.task.runCount >= entry.task.maxRuns) {
      entry.task.status = 'completed';
      return;
    }

    let delay: number;

    if (entry.config.cron) {
      const nextRun = getNextCronRun(entry.config.cron);
      entry.task.nextRun = nextRun;
      delay = nextRun.getTime() - Date.now();
    } else if (entry.config.interval) {
      entry.task.nextRun = new Date(Date.now() + entry.config.interval);
      delay = entry.config.interval;
    } else {
      return;
    }

    entry.timer = setTimeout(() => this.runTask(id), delay);
    this.stats.activeTasks = Array.from(this.tasks.values()).filter(e => e.timer).length;
  }

  /**
   * Run a task
   */
  private async runTask(id: string): Promise<void> {
    const entry = this.tasks.get(id);
    if (!entry) return;

    entry.task.status = 'running';
    entry.task.lastRun = new Date();

    try {
      const result = await entry.config.task();
      entry.task.runCount++;
      entry.task.status = 'idle';
      entry.task.lastError = undefined;
      this.stats.totalRuns++;

      entry.config.onComplete?.(result);
    } catch (error: any) {
      entry.task.status = 'error';
      entry.task.lastError = error.message;
      this.stats.errors++;

      entry.config.onError?.(error);
    }

    // Schedule next run
    this.scheduleTask(id);
  }

  /**
   * Run a task immediately
   */
  async runNow(id: string): Promise<any> {
    const entry = this.tasks.get(id);
    if (!entry) throw new Error(`Task ${id} not found`);

    entry.task.status = 'running';
    entry.task.lastRun = new Date();

    try {
      const result = await entry.config.task();
      entry.task.runCount++;
      entry.task.status = 'idle';
      this.stats.totalRuns++;
      return result;
    } catch (error: any) {
      entry.task.status = 'error';
      entry.task.lastError = error.message;
      this.stats.errors++;
      throw error;
    }
  }

  /**
   * Get task info
   */
  getTask(id: string): ScheduledTask | undefined {
    return this.tasks.get(id)?.task;
  }

  /**
   * Get all tasks
   */
  getAllTasks(): ScheduledTask[] {
    return Array.from(this.tasks.values()).map(e => e.task);
  }

  /**
   * Get scheduler stats
   */
  getStats(): SchedulerStats {
    return { ...this.stats };
  }

  /**
   * Check if scheduler is running
   */
  isRunning(): boolean {
    return this.running;
  }
}

/**
 * Create a scheduler instance
 */
export function createScheduler(): Scheduler {
  return new Scheduler();
}

/**
 * Helper to create common cron expressions
 */
export const cronExpressions = {
  everyMinute: '* * * * *',
  every5Minutes: '*/5 * * * *',
  every15Minutes: '*/15 * * * *',
  everyHour: '0 * * * *',
  everyDay: '0 0 * * *',
  everyWeek: '0 0 * * 0',
  everyMonth: '0 0 1 * *',
  weekdays: '0 9 * * 1-5',
  weekends: '0 10 * * 0,6'
};
