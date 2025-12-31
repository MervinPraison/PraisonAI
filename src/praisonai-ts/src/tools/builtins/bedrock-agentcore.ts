/**
 * Amazon Bedrock AgentCore Tools
 * 
 * Code Interpreter and Browser automation powered by AWS.
 * Package: bedrock-agentcore
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';
import { MissingDependencyError } from '../registry/types';

export const BEDROCK_AGENTCORE_METADATA: ToolMetadata = {
  id: 'bedrock-agentcore',
  displayName: 'Amazon Bedrock AgentCore',
  description: 'Code interpreter and browser automation powered by AWS Bedrock AgentCore',
  tags: ['sandbox', 'code', 'browser', 'aws'],
  requiredEnv: [], // Uses AWS credentials from environment/config
  optionalEnv: ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION'],
  install: {
    npm: 'npm install bedrock-agentcore',
    pnpm: 'pnpm add bedrock-agentcore',
    yarn: 'yarn add bedrock-agentcore',
    bun: 'bun add bedrock-agentcore',
  },
  docsSlug: 'tools/bedrock-agentcore',
  capabilities: {
    sandbox: true,
    code: true,
    browser: true,
  },
  packageName: 'bedrock-agentcore',
};

// Code Interpreter types
export interface CodeInterpreterConfig {
  language?: 'python' | 'javascript' | 'typescript';
  timeout?: number;
}

export interface CodeInterpreterInput {
  code: string;
}

export interface CodeInterpreterResult {
  output: string;
  success: boolean;
  error?: string;
}

// Browser types
export interface BrowserConfig {
  headless?: boolean;
  timeout?: number;
}

export interface BrowserNavigateInput {
  url: string;
}

export interface BrowserClickInput {
  selector: string;
}

export interface BrowserFillInput {
  selector: string;
  value: string;
}

export interface BrowserResult {
  success: boolean;
  data?: unknown;
  error?: string;
}

async function loadBedrockPackage() {
  try {
    // @ts-ignore - Optional dependency
    return await import('bedrock-agentcore');
  } catch {
    throw new MissingDependencyError(
      BEDROCK_AGENTCORE_METADATA.id,
      BEDROCK_AGENTCORE_METADATA.packageName,
      BEDROCK_AGENTCORE_METADATA.install,
      BEDROCK_AGENTCORE_METADATA.requiredEnv,
      BEDROCK_AGENTCORE_METADATA.docsSlug
    );
  }
}

/**
 * Create a Bedrock Code Interpreter tool
 */
export function bedrockCodeInterpreter(config?: CodeInterpreterConfig): PraisonTool<CodeInterpreterInput, CodeInterpreterResult> {
  return {
    name: 'bedrockCodeInterpreter',
    description: 'Execute code in a secure AWS-managed sandbox. Supports Python, JavaScript, and TypeScript.',
    parameters: {
      type: 'object',
      properties: {
        code: {
          type: 'string',
          description: 'The code to execute',
        },
      },
      required: ['code'],
    },
    execute: async (input: CodeInterpreterInput, context?: ToolExecutionContext): Promise<CodeInterpreterResult> => {
      const pkg = await loadBedrockPackage();
      
      // Try to get CodeInterpreterTools from the package
      const CodeInterpreterTools = (pkg as Record<string, unknown>).CodeInterpreterTools;
      if (CodeInterpreterTools && typeof CodeInterpreterTools === 'function') {
        const interpreter = new (CodeInterpreterTools as new () => {
          tools: Record<string, { execute: (input: unknown) => Promise<unknown> }>;
        })();
        
        // Find the execute code tool
        const executeTool = interpreter.tools?.executeCode;
        if (executeTool && typeof executeTool.execute === 'function') {
          const result = await executeTool.execute(input);
          return {
            output: String(result),
            success: true,
          };
        }
      }
      
      return { output: '', success: false, error: 'Code interpreter not available' };
    },
  };
}

/**
 * Create a Bedrock Browser Navigate tool
 */
export function bedrockBrowserNavigate(config?: BrowserConfig): PraisonTool<BrowserNavigateInput, BrowserResult> {
  return {
    name: 'bedrockBrowserNavigate',
    description: 'Navigate to a URL using cloud-based browser automation.',
    parameters: {
      type: 'object',
      properties: {
        url: {
          type: 'string',
          description: 'The URL to navigate to',
        },
      },
      required: ['url'],
    },
    execute: async (input: BrowserNavigateInput, context?: ToolExecutionContext): Promise<BrowserResult> => {
      const pkg = await loadBedrockPackage();
      
      const BrowserTools = (pkg as Record<string, unknown>).BrowserTools;
      if (BrowserTools && typeof BrowserTools === 'function') {
        const browser = new (BrowserTools as new () => {
          tools: Record<string, { execute: (input: unknown) => Promise<unknown> }>;
        })();
        
        const navigateTool = browser.tools?.navigate;
        if (navigateTool && typeof navigateTool.execute === 'function') {
          await navigateTool.execute(input);
          return { success: true };
        }
      }
      
      return { success: false, error: 'Browser tools not available' };
    },
  };
}

/**
 * Create a Bedrock Browser Click tool
 */
export function bedrockBrowserClick(config?: BrowserConfig): PraisonTool<BrowserClickInput, BrowserResult> {
  return {
    name: 'bedrockBrowserClick',
    description: 'Click an element on the page using a CSS selector.',
    parameters: {
      type: 'object',
      properties: {
        selector: {
          type: 'string',
          description: 'CSS selector for the element to click',
        },
      },
      required: ['selector'],
    },
    execute: async (input: BrowserClickInput, context?: ToolExecutionContext): Promise<BrowserResult> => {
      const pkg = await loadBedrockPackage();
      
      const BrowserTools = (pkg as Record<string, unknown>).BrowserTools;
      if (BrowserTools && typeof BrowserTools === 'function') {
        const browser = new (BrowserTools as new () => {
          tools: Record<string, { execute: (input: unknown) => Promise<unknown> }>;
        })();
        
        const clickTool = browser.tools?.click;
        if (clickTool && typeof clickTool.execute === 'function') {
          await clickTool.execute(input);
          return { success: true };
        }
      }
      
      return { success: false, error: 'Browser tools not available' };
    },
  };
}

/**
 * Create a Bedrock Browser Fill tool
 */
export function bedrockBrowserFill(config?: BrowserConfig): PraisonTool<BrowserFillInput, BrowserResult> {
  return {
    name: 'bedrockBrowserFill',
    description: 'Fill a form field with text using a CSS selector.',
    parameters: {
      type: 'object',
      properties: {
        selector: {
          type: 'string',
          description: 'CSS selector for the input element',
        },
        value: {
          type: 'string',
          description: 'The value to fill in',
        },
      },
      required: ['selector', 'value'],
    },
    execute: async (input: BrowserFillInput, context?: ToolExecutionContext): Promise<BrowserResult> => {
      const pkg = await loadBedrockPackage();
      
      const BrowserTools = (pkg as Record<string, unknown>).BrowserTools;
      if (BrowserTools && typeof BrowserTools === 'function') {
        const browser = new (BrowserTools as new () => {
          tools: Record<string, { execute: (input: unknown) => Promise<unknown> }>;
        })();
        
        const fillTool = browser.tools?.fill;
        if (fillTool && typeof fillTool.execute === 'function') {
          await fillTool.execute(input);
          return { success: true };
        }
      }
      
      return { success: false, error: 'Browser tools not available' };
    },
  };
}

/**
 * Factory functions for registry
 */
export function createBedrockCodeInterpreterTool(config?: CodeInterpreterConfig): PraisonTool<unknown, unknown> {
  return bedrockCodeInterpreter(config) as PraisonTool<unknown, unknown>;
}

export function createBedrockBrowserNavigateTool(config?: BrowserConfig): PraisonTool<unknown, unknown> {
  return bedrockBrowserNavigate(config) as PraisonTool<unknown, unknown>;
}

export function createBedrockBrowserClickTool(config?: BrowserConfig): PraisonTool<unknown, unknown> {
  return bedrockBrowserClick(config) as PraisonTool<unknown, unknown>;
}

export function createBedrockBrowserFillTool(config?: BrowserConfig): PraisonTool<unknown, unknown> {
  return bedrockBrowserFill(config) as PraisonTool<unknown, unknown>;
}
