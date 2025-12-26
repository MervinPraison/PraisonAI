/**
 * Tool Decorator and Registry - Type-safe tool creation and management
 */

export interface ToolParameters {
  type: 'object';
  properties: Record<string, {
    type: string;
    description?: string;
    enum?: string[];
    default?: any;
  }>;
  required?: string[];
}

export interface ToolConfig<TParams = any, TResult = any> {
  name: string;
  description?: string;
  parameters?: ToolParameters | any; // Support Zod schemas
  category?: string;
  execute: (params: TParams, context?: ToolContext) => Promise<TResult> | TResult;
}

export interface ToolContext {
  agentName?: string;
  sessionId?: string;
  runId?: string;
  signal?: AbortSignal;
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: ToolParameters;
  category?: string;
}

/**
 * Tool class - Represents an executable tool
 */
export class FunctionTool<TParams = any, TResult = any> {
  readonly name: string;
  readonly description: string;
  readonly parameters: ToolParameters;
  readonly category?: string;
  private readonly executeFn: (params: TParams, context?: ToolContext) => Promise<TResult> | TResult;

  constructor(config: ToolConfig<TParams, TResult>) {
    this.name = config.name;
    this.description = config.description || `Function ${config.name}`;
    this.parameters = this.normalizeParameters(config.parameters);
    this.category = config.category;
    this.executeFn = config.execute;
  }

  private normalizeParameters(params: any): ToolParameters {
    if (!params) {
      return { type: 'object', properties: {}, required: [] };
    }
    
    // Check if it's a Zod schema
    if (params && typeof params.parse === 'function' && typeof params._def === 'object') {
      return this.zodToJsonSchema(params);
    }
    
    // Already a JSON schema
    return params;
  }

  private zodToJsonSchema(zodSchema: any): ToolParameters {
    // Basic Zod to JSON Schema conversion
    // For full support, use zod-to-json-schema package
    const def = zodSchema._def;
    
    if (def.typeName === 'ZodObject') {
      const properties: Record<string, any> = {};
      const required: string[] = [];
      
      for (const [key, value] of Object.entries(def.shape())) {
        const fieldDef = (value as any)._def;
        properties[key] = this.zodFieldToJsonSchema(fieldDef);
        
        // Check if field is required (not optional)
        if (fieldDef.typeName !== 'ZodOptional' && fieldDef.typeName !== 'ZodDefault') {
          required.push(key);
        }
      }
      
      return { type: 'object', properties, required };
    }
    
    return { type: 'object', properties: {}, required: [] };
  }

  private zodFieldToJsonSchema(def: any): any {
    const typeName = def.typeName;
    
    switch (typeName) {
      case 'ZodString':
        return { type: 'string', description: def.description };
      case 'ZodNumber':
        return { type: 'number', description: def.description };
      case 'ZodBoolean':
        return { type: 'boolean', description: def.description };
      case 'ZodArray':
        return { type: 'array', items: this.zodFieldToJsonSchema(def.type._def) };
      case 'ZodEnum':
        return { type: 'string', enum: def.values };
      case 'ZodOptional':
        return this.zodFieldToJsonSchema(def.innerType._def);
      case 'ZodDefault':
        const inner = this.zodFieldToJsonSchema(def.innerType._def);
        inner.default = def.defaultValue();
        return inner;
      default:
        return { type: 'string' };
    }
  }

  async execute(params: TParams, context?: ToolContext): Promise<TResult> {
    // Validate parameters if we have a schema
    // For now, just execute - validation can be added later
    return this.executeFn(params, context);
  }

  /**
   * Get the tool definition for LLM
   */
  getDefinition(): ToolDefinition {
    return {
      name: this.name,
      description: this.description,
      parameters: this.parameters,
      category: this.category,
    };
  }

  /**
   * Get OpenAI-compatible tool format
   */
  toOpenAITool(): { type: 'function'; function: { name: string; description: string; parameters: any } } {
    return {
      type: 'function',
      function: {
        name: this.name,
        description: this.description,
        parameters: this.parameters,
      },
    };
  }
}

/**
 * Create a tool from a configuration object
 */
export function tool<TParams = any, TResult = any>(
  config: ToolConfig<TParams, TResult>
): FunctionTool<TParams, TResult> {
  return new FunctionTool(config);
}

/**
 * Tool Registry - Manages tool registration and lookup
 */
export class ToolRegistry {
  private tools: Map<string, FunctionTool> = new Map();

  register(tool: FunctionTool, options?: { overwrite?: boolean }): this {
    if (this.tools.has(tool.name) && !options?.overwrite) {
      throw new Error(`Tool '${tool.name}' is already registered. Use { overwrite: true } to replace.`);
    }
    this.tools.set(tool.name, tool);
    return this;
  }

  get(name: string): FunctionTool | undefined {
    return this.tools.get(name);
  }

  has(name: string): boolean {
    return this.tools.has(name);
  }

  list(): FunctionTool[] {
    return Array.from(this.tools.values());
  }

  getByCategory(category: string): FunctionTool[] {
    return this.list().filter(t => t.category === category);
  }

  getDefinitions(): ToolDefinition[] {
    return this.list().map(t => t.getDefinition());
  }

  toOpenAITools(): Array<{ type: 'function'; function: any }> {
    return this.list().map(t => t.toOpenAITool());
  }

  delete(name: string): boolean {
    return this.tools.delete(name);
  }

  clear(): void {
    this.tools.clear();
  }
}

// Global registry instance
let globalRegistry: ToolRegistry | null = null;

export function getRegistry(): ToolRegistry {
  if (!globalRegistry) {
    globalRegistry = new ToolRegistry();
  }
  return globalRegistry;
}

export function registerTool(tool: FunctionTool, options?: { overwrite?: boolean }): void {
  getRegistry().register(tool, options);
}

export function getTool(name: string): FunctionTool | undefined {
  return getRegistry().get(name);
}
