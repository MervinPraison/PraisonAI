export interface Memory {
  id: string;
  content: any;
  timestamp: Date;
  metadata: Record<string, any>;
}

export interface MemoryStore {
  add(memory: Memory): void;
  get(id: string): Memory | undefined;
  search(query: string): Memory[];
  update(id: string, memory: Partial<Memory>): boolean;
  delete(id: string): boolean;
  clear(): void;
}

export class BaseMemoryStore implements MemoryStore {
  private memories: Map<string, Memory>;

  constructor() {
    this.memories = new Map();
  }

  add(memory: Memory): void {
    this.memories.set(memory.id, memory);
  }

  get(id: string): Memory | undefined {
    return this.memories.get(id);
  }

  search(query: string): Memory[] {
    return Array.from(this.memories.values()).filter(m =>
      JSON.stringify(m).toLowerCase().includes(query.toLowerCase())
    );
  }

  update(id: string, update: Partial<Memory>): boolean {
    const existing = this.memories.get(id);
    if (!existing) return false;

    this.memories.set(id, { ...existing, ...update });
    return true;
  }

  delete(id: string): boolean {
    return this.memories.delete(id);
  }

  clear(): void {
    this.memories.clear();
  }
}
