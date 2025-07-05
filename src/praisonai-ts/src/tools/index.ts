// Export base tool interfaces
export interface Tool {
  name: string;
  description: string;
  execute(...args: any[]): Promise<any>;
}

export class BaseTool implements Tool {
  name: string;
  description: string;

  constructor(name: string, description: string) {
    this.name = name;
    this.description = description;
  }

  async execute(...args: any[]): Promise<any> {
    throw new Error('Method not implemented.');
  }
}

// Export all tool modules
export * from './arxivTools';
export * from './mcpSse';
export * from './mcp';
