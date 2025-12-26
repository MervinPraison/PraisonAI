/**
 * Checkpoints - Snapshot session/run state for recovery
 */

export interface CheckpointData {
  id: string;
  name: string;
  timestamp: Date;
  sessionId?: string;
  runId?: string;
  agentId?: string;
  state: Record<string, any>;
  messages?: any[];
  metadata?: Record<string, any>;
}

export interface CheckpointConfig {
  storage?: CheckpointStorage;
  autoSave?: boolean;
  autoSaveInterval?: number;
  maxCheckpoints?: number;
}

export interface CheckpointStorage {
  save(checkpoint: CheckpointData): Promise<void>;
  load(id: string): Promise<CheckpointData | null>;
  list(): Promise<CheckpointData[]>;
  delete(id: string): Promise<void>;
  clear(): Promise<void>;
}

/**
 * In-memory checkpoint storage
 */
export class MemoryCheckpointStorage implements CheckpointStorage {
  private checkpoints: Map<string, CheckpointData> = new Map();

  async save(checkpoint: CheckpointData): Promise<void> {
    this.checkpoints.set(checkpoint.id, { ...checkpoint });
  }

  async load(id: string): Promise<CheckpointData | null> {
    return this.checkpoints.get(id) || null;
  }

  async list(): Promise<CheckpointData[]> {
    return Array.from(this.checkpoints.values())
      .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
  }

  async delete(id: string): Promise<void> {
    this.checkpoints.delete(id);
  }

  async clear(): Promise<void> {
    this.checkpoints.clear();
  }
}

/**
 * File-based checkpoint storage
 */
export class FileCheckpointStorage implements CheckpointStorage {
  private dirPath: string;

  constructor(dirPath: string) {
    this.dirPath = dirPath;
  }

  private async ensureDir(): Promise<void> {
    const fs = await import('fs/promises');
    await fs.mkdir(this.dirPath, { recursive: true });
  }

  private getFilePath(id: string): string {
    return `${this.dirPath}/${id}.json`;
  }

  async save(checkpoint: CheckpointData): Promise<void> {
    await this.ensureDir();
    const fs = await import('fs/promises');
    await fs.writeFile(
      this.getFilePath(checkpoint.id),
      JSON.stringify(checkpoint, null, 2)
    );
  }

  async load(id: string): Promise<CheckpointData | null> {
    try {
      const fs = await import('fs/promises');
      const content = await fs.readFile(this.getFilePath(id), 'utf-8');
      const data = JSON.parse(content);
      data.timestamp = new Date(data.timestamp);
      return data;
    } catch {
      return null;
    }
  }

  async list(): Promise<CheckpointData[]> {
    try {
      await this.ensureDir();
      const fs = await import('fs/promises');
      const files = await fs.readdir(this.dirPath);
      const checkpoints: CheckpointData[] = [];

      for (const file of files) {
        if (file.endsWith('.json')) {
          const id = file.replace('.json', '');
          const checkpoint = await this.load(id);
          if (checkpoint) {
            checkpoints.push(checkpoint);
          }
        }
      }

      return checkpoints.sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime());
    } catch {
      return [];
    }
  }

  async delete(id: string): Promise<void> {
    try {
      const fs = await import('fs/promises');
      await fs.unlink(this.getFilePath(id));
    } catch {
      // Ignore if file doesn't exist
    }
  }

  async clear(): Promise<void> {
    const checkpoints = await this.list();
    for (const checkpoint of checkpoints) {
      await this.delete(checkpoint.id);
    }
  }
}

/**
 * Checkpoint Manager class
 */
export class CheckpointManager {
  private config: CheckpointConfig;
  private storage: CheckpointStorage;
  private autoSaveTimer?: NodeJS.Timeout;
  private currentState: Record<string, any> = {};

  constructor(config: CheckpointConfig = {}) {
    this.config = {
      autoSave: false,
      autoSaveInterval: 60000, // 1 minute
      maxCheckpoints: 10,
      ...config
    };
    this.storage = config.storage || new MemoryCheckpointStorage();
  }

  /**
   * Create a checkpoint
   */
  async create(name: string, options: Partial<CheckpointData> = {}): Promise<CheckpointData> {
    const checkpoint: CheckpointData = {
      id: `cp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      name,
      timestamp: new Date(),
      state: { ...this.currentState },
      ...options
    };

    await this.storage.save(checkpoint);
    await this.enforceMaxCheckpoints();

    return checkpoint;
  }

  /**
   * Restore from a checkpoint
   */
  async restore(id: string): Promise<CheckpointData | null> {
    const checkpoint = await this.storage.load(id);
    if (checkpoint) {
      this.currentState = { ...checkpoint.state };
    }
    return checkpoint;
  }

  /**
   * Restore the latest checkpoint
   */
  async restoreLatest(): Promise<CheckpointData | null> {
    const checkpoints = await this.storage.list();
    if (checkpoints.length === 0) return null;
    return this.restore(checkpoints[0].id);
  }

  /**
   * Get a checkpoint by ID
   */
  async get(id: string): Promise<CheckpointData | null> {
    return this.storage.load(id);
  }

  /**
   * List all checkpoints
   */
  async list(): Promise<CheckpointData[]> {
    return this.storage.list();
  }

  /**
   * Delete a checkpoint
   */
  async delete(id: string): Promise<void> {
    await this.storage.delete(id);
  }

  /**
   * Clear all checkpoints
   */
  async clear(): Promise<void> {
    await this.storage.clear();
  }

  /**
   * Update current state
   */
  setState(state: Record<string, any>): void {
    this.currentState = { ...this.currentState, ...state };
  }

  /**
   * Get current state
   */
  getState(): Record<string, any> {
    return { ...this.currentState };
  }

  /**
   * Start auto-save
   */
  startAutoSave(): void {
    if (this.autoSaveTimer) return;
    if (!this.config.autoSave) return;

    this.autoSaveTimer = setInterval(async () => {
      await this.create('auto-save', { metadata: { auto: true } });
    }, this.config.autoSaveInterval);
  }

  /**
   * Stop auto-save
   */
  stopAutoSave(): void {
    if (this.autoSaveTimer) {
      clearInterval(this.autoSaveTimer);
      this.autoSaveTimer = undefined;
    }
  }

  /**
   * Enforce maximum checkpoints limit
   */
  private async enforceMaxCheckpoints(): Promise<void> {
    if (!this.config.maxCheckpoints) return;

    const checkpoints = await this.storage.list();
    if (checkpoints.length > this.config.maxCheckpoints) {
      // Delete oldest checkpoints (but keep auto-saves separate)
      const toDelete = checkpoints.slice(this.config.maxCheckpoints);
      for (const checkpoint of toDelete) {
        await this.storage.delete(checkpoint.id);
      }
    }
  }

  /**
   * Export checkpoint to JSON string
   */
  async export(id: string): Promise<string | null> {
    const checkpoint = await this.storage.load(id);
    if (!checkpoint) return null;
    return JSON.stringify(checkpoint, null, 2);
  }

  /**
   * Import checkpoint from JSON string
   */
  async import(json: string): Promise<CheckpointData> {
    const data = JSON.parse(json);
    data.timestamp = new Date(data.timestamp);
    data.id = `cp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`; // New ID
    await this.storage.save(data);
    return data;
  }
}

/**
 * Create a checkpoint manager
 */
export function createCheckpointManager(config?: CheckpointConfig): CheckpointManager {
  return new CheckpointManager(config);
}

/**
 * Create file-based checkpoint storage
 */
export function createFileCheckpointStorage(dirPath: string): FileCheckpointStorage {
  return new FileCheckpointStorage(dirPath);
}
