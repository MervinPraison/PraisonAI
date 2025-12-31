/**
 * Custom Tool Registration API
 * 
 * Clean API to register custom tools (local + npm) with minimal friction.
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext, ToolParameterSchema } from '../registry/types';
import { getToolsRegistry } from '../registry/registry';

export interface CustomToolConfig<TInput = unknown, TOutput = unknown> {
  /** Unique tool identifier */
  id: string;
  /** Display name */
  name: string;
  /** Tool description (used by LLM) */
  description: string;
  /** Parameter schema */
  parameters?: ToolParameterSchema;
  /** Execute function */
  execute: (input: TInput, context?: ToolExecutionContext) => Promise<TOutput> | TOutput;
  /** Tags for categorization */
  tags?: string[];
  /** Documentation slug */
  docsSlug?: string;
}

/**
 * Register a custom tool with the global registry
 */
export function registerCustomTool<TInput = unknown, TOutput = unknown>(
  config: CustomToolConfig<TInput, TOutput>
): PraisonTool<TInput, TOutput> {
  const metadata: ToolMetadata = {
    id: config.id,
    displayName: config.name,
    description: config.description,
    tags: config.tags || ['custom'],
    requiredEnv: [],
    optionalEnv: [],
    install: {
      npm: '# Custom tool - no installation required',
      pnpm: '# Custom tool - no installation required',
      yarn: '# Custom tool - no installation required',
      bun: '# Custom tool - no installation required',
    },
    docsSlug: config.docsSlug || `tools/custom/${config.id}`,
    capabilities: {},
    packageName: 'custom',
  };

  const tool: PraisonTool<TInput, TOutput> = {
    name: config.name,
    description: config.description,
    parameters: config.parameters || { type: 'object', properties: {} },
    execute: async (input: TInput, context?: ToolExecutionContext): Promise<TOutput> => {
      return config.execute(input, context);
    },
  };

  // Register with the global registry
  const registry = getToolsRegistry();
  registry.register(metadata, () => tool as PraisonTool<unknown, unknown>);

  return tool;
}

/**
 * Create a custom tool without registering it
 */
export function createCustomTool<TInput = unknown, TOutput = unknown>(
  config: CustomToolConfig<TInput, TOutput>
): PraisonTool<TInput, TOutput> {
  return {
    name: config.name,
    description: config.description,
    parameters: config.parameters || { type: 'object', properties: {} },
    execute: async (input: TInput, context?: ToolExecutionContext): Promise<TOutput> => {
      return config.execute(input, context);
    },
  };
}

/**
 * Register a tool from an npm package
 */
export async function registerNpmTool(
  packageName: string,
  toolName?: string
): Promise<PraisonTool<unknown, unknown>> {
  try {
    const pkg = await import(packageName);
    
    // Try to find the tool export
    const toolExport = toolName 
      ? pkg[toolName] 
      : pkg.default || pkg.tool || pkg[Object.keys(pkg)[0]];

    if (!toolExport) {
      throw new Error(`Could not find tool export in package "${packageName}"`);
    }

    // If it's a function, call it to get the tool
    const tool = typeof toolExport === 'function' ? toolExport() : toolExport;

    // Validate it has the required properties
    if (!tool.name || !tool.execute) {
      throw new Error(`Invalid tool structure in package "${packageName}"`);
    }

    // Register with the registry
    const metadata: ToolMetadata = {
      id: `npm:${packageName}${toolName ? `:${toolName}` : ''}`,
      displayName: tool.name,
      description: tool.description || `Tool from ${packageName}`,
      tags: ['npm', 'external'],
      requiredEnv: [],
      optionalEnv: [],
      install: {
        npm: `npm install ${packageName}`,
        pnpm: `pnpm add ${packageName}`,
        yarn: `yarn add ${packageName}`,
        bun: `bun add ${packageName}`,
      },
      docsSlug: `tools/npm/${packageName.replace(/[@/]/g, '-')}`,
      capabilities: {},
      packageName,
    };

    const registry = getToolsRegistry();
    registry.register(metadata, () => tool);

    return tool;
  } catch (error) {
    throw new Error(
      `Failed to register tool from "${packageName}": ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

/**
 * Register a tool from a local file path
 */
export async function registerLocalTool(
  filePath: string,
  toolName?: string
): Promise<PraisonTool<unknown, unknown>> {
  try {
    // Resolve the path
    const resolvedPath = require.resolve(filePath, { paths: [process.cwd()] });
    const pkg = await import(resolvedPath);
    
    const toolExport = toolName 
      ? pkg[toolName] 
      : pkg.default || pkg.tool || pkg[Object.keys(pkg)[0]];

    if (!toolExport) {
      throw new Error(`Could not find tool export in file "${filePath}"`);
    }

    const tool = typeof toolExport === 'function' ? toolExport() : toolExport;

    if (!tool.name || !tool.execute) {
      throw new Error(`Invalid tool structure in file "${filePath}"`);
    }

    const metadata: ToolMetadata = {
      id: `local:${filePath}${toolName ? `:${toolName}` : ''}`,
      displayName: tool.name,
      description: tool.description || `Tool from ${filePath}`,
      tags: ['local', 'custom'],
      requiredEnv: [],
      optionalEnv: [],
      install: {
        npm: '# Local tool - no installation required',
        pnpm: '# Local tool - no installation required',
        yarn: '# Local tool - no installation required',
        bun: '# Local tool - no installation required',
      },
      docsSlug: `tools/local`,
      capabilities: {},
      packageName: 'local',
    };

    const registry = getToolsRegistry();
    registry.register(metadata, () => tool);

    return tool;
  } catch (error) {
    throw new Error(
      `Failed to register tool from "${filePath}": ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

/**
 * Decorator for creating tools from class methods
 */
export function Tool(config: Omit<CustomToolConfig, 'execute'>) {
  return function (
    target: unknown,
    propertyKey: string,
    descriptor: PropertyDescriptor
  ) {
    const originalMethod = descriptor.value;
    
    // Create and register the tool
    registerCustomTool({
      ...config,
      execute: originalMethod,
    });

    return descriptor;
  };
}
