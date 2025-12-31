/**
 * Computer Use Integration
 * 
 * Provides interfaces for computer use capabilities (browser/desktop control).
 * By default, tools are safe no-ops that require explicit implementation.
 */

export interface ComputerUseConfig {
  /** Enable browser control */
  browser?: boolean;
  /** Enable desktop control */
  desktop?: boolean;
  /** Require human approval for actions (default: true) */
  requireApproval?: boolean;
  /** Screenshot directory */
  screenshotDir?: string;
  /** Action timeout in ms (default: 30000) */
  timeout?: number;
  /** Custom tool implementations */
  tools?: Partial<ComputerUseTools>;
}

export interface ComputerUseTools {
  /** Take a screenshot */
  screenshot: () => Promise<ScreenshotResult>;
  /** Click at coordinates */
  click: (x: number, y: number, button?: 'left' | 'right' | 'middle') => Promise<void>;
  /** Double click at coordinates */
  doubleClick: (x: number, y: number) => Promise<void>;
  /** Type text */
  type: (text: string) => Promise<void>;
  /** Press a key or key combination */
  key: (key: string) => Promise<void>;
  /** Move mouse to coordinates */
  moveMouse: (x: number, y: number) => Promise<void>;
  /** Scroll */
  scroll: (direction: 'up' | 'down' | 'left' | 'right', amount?: number) => Promise<void>;
  /** Get screen size */
  getScreenSize: () => Promise<{ width: number; height: number }>;
  /** Wait for a duration */
  wait: (ms: number) => Promise<void>;
  /** Execute a shell command (with approval) */
  execute: (command: string) => Promise<string>;
}

export interface ScreenshotResult {
  /** Base64-encoded image */
  base64: string;
  /** Image width */
  width: number;
  /** Image height */
  height: number;
  /** File path if saved */
  path?: string;
}

export interface ComputerAction {
  type: 'screenshot' | 'click' | 'doubleClick' | 'type' | 'key' | 'moveMouse' | 'scroll' | 'wait' | 'execute';
  params?: any;
  requiresApproval?: boolean;
}

/**
 * Create a Computer Use agent with safe defaults.
 * 
 * @example Basic usage (safe mode - no-op tools)
 * ```typescript
 * import { createComputerUse } from 'praisonai/integrations/computer-use';
 * 
 * const computer = createComputerUse({
 *   requireApproval: true
 * });
 * 
 * // Get tools for use with an agent
 * const tools = computer.getTools();
 * ```
 * 
 * @example With Playwright browser control
 * ```typescript
 * import { chromium } from 'playwright';
 * import { createComputerUse } from 'praisonai/integrations/computer-use';
 * 
 * const browser = await chromium.launch();
 * const page = await browser.newPage();
 * 
 * const computer = createComputerUse({
 *   browser: true,
 *   tools: {
 *     screenshot: async () => {
 *       const buffer = await page.screenshot();
 *       return {
 *         base64: buffer.toString('base64'),
 *         width: 1920,
 *         height: 1080
 *       };
 *     },
 *     click: async (x, y) => {
 *       await page.mouse.click(x, y);
 *     },
 *     type: async (text) => {
 *       await page.keyboard.type(text);
 *     }
 *   }
 * });
 * ```
 */
export function createComputerUse(config: ComputerUseConfig = {}): ComputerUseClient {
  return new ComputerUseClient(config);
}

export class ComputerUseClient {
  private config: ComputerUseConfig;
  private tools: ComputerUseTools;
  private approvalCallback?: (action: ComputerAction) => Promise<boolean>;

  constructor(config: ComputerUseConfig = {}) {
    this.config = {
      requireApproval: true,
      timeout: 30000,
      ...config,
    };

    // Initialize with safe no-op tools
    this.tools = {
      screenshot: config.tools?.screenshot || this.noOpScreenshot,
      click: config.tools?.click || this.noOpAction,
      doubleClick: config.tools?.doubleClick || this.noOpAction,
      type: config.tools?.type || this.noOpAction,
      key: config.tools?.key || this.noOpAction,
      moveMouse: config.tools?.moveMouse || this.noOpAction,
      scroll: config.tools?.scroll || this.noOpAction,
      getScreenSize: config.tools?.getScreenSize || (async () => ({ width: 1920, height: 1080 })),
      wait: config.tools?.wait || (async (ms: number) => new Promise(r => setTimeout(r, ms))),
      execute: config.tools?.execute || this.noOpExecute,
    };
  }

  /**
   * Set the approval callback for actions.
   */
  onApproval(callback: (action: ComputerAction) => Promise<boolean>): this {
    this.approvalCallback = callback;
    return this;
  }

  /**
   * No-op screenshot implementation.
   */
  private async noOpScreenshot(): Promise<ScreenshotResult> {
    console.warn('Computer Use: screenshot() called but no implementation provided');
    return {
      base64: '',
      width: 0,
      height: 0,
    };
  }

  /**
   * No-op action implementation.
   */
  private async noOpAction(...args: any[]): Promise<void> {
    console.warn('Computer Use: action called but no implementation provided', args);
  }

  /**
   * No-op execute implementation.
   */
  private async noOpExecute(command: string): Promise<string> {
    console.warn('Computer Use: execute() called but no implementation provided');
    return `[No-op] Would execute: ${command}`;
  }

  /**
   * Request approval for an action.
   */
  private async requestApproval(action: ComputerAction): Promise<boolean> {
    if (!this.config.requireApproval) {
      return true;
    }

    if (this.approvalCallback) {
      return await this.approvalCallback(action);
    }

    // Default: deny if no callback
    console.warn('Computer Use: Action requires approval but no callback set', action);
    return false;
  }

  /**
   * Take a screenshot.
   */
  async screenshot(): Promise<ScreenshotResult> {
    const action: ComputerAction = { type: 'screenshot' };
    if (!(await this.requestApproval(action))) {
      throw new Error('Screenshot action denied');
    }
    return await this.tools.screenshot();
  }

  /**
   * Click at coordinates.
   */
  async click(x: number, y: number, button: 'left' | 'right' | 'middle' = 'left'): Promise<void> {
    const action: ComputerAction = { type: 'click', params: { x, y, button }, requiresApproval: true };
    if (!(await this.requestApproval(action))) {
      throw new Error('Click action denied');
    }
    await this.tools.click(x, y, button);
  }

  /**
   * Type text.
   */
  async type(text: string): Promise<void> {
    const action: ComputerAction = { type: 'type', params: { text }, requiresApproval: true };
    if (!(await this.requestApproval(action))) {
      throw new Error('Type action denied');
    }
    await this.tools.type(text);
  }

  /**
   * Press a key.
   */
  async key(key: string): Promise<void> {
    const action: ComputerAction = { type: 'key', params: { key }, requiresApproval: true };
    if (!(await this.requestApproval(action))) {
      throw new Error('Key action denied');
    }
    await this.tools.key(key);
  }

  /**
   * Execute a command.
   */
  async execute(command: string): Promise<string> {
    const action: ComputerAction = { type: 'execute', params: { command }, requiresApproval: true };
    if (!(await this.requestApproval(action))) {
      throw new Error('Execute action denied');
    }
    return await this.tools.execute(command);
  }

  /**
   * Get tools for use with an agent.
   */
  getTools(): Record<string, any> {
    return {
      computer_screenshot: {
        description: 'Take a screenshot of the current screen',
        parameters: { type: 'object', properties: {} },
        execute: async () => {
          const result = await this.screenshot();
          return JSON.stringify({ width: result.width, height: result.height, hasImage: !!result.base64 });
        },
      },
      computer_click: {
        description: 'Click at specific coordinates on the screen',
        parameters: {
          type: 'object',
          properties: {
            x: { type: 'number', description: 'X coordinate' },
            y: { type: 'number', description: 'Y coordinate' },
            button: { type: 'string', enum: ['left', 'right', 'middle'], description: 'Mouse button' },
          },
          required: ['x', 'y'],
        },
        execute: async ({ x, y, button }: { x: number; y: number; button?: 'left' | 'right' | 'middle' }) => {
          await this.click(x, y, button);
          return 'Clicked successfully';
        },
      },
      computer_type: {
        description: 'Type text using the keyboard',
        parameters: {
          type: 'object',
          properties: {
            text: { type: 'string', description: 'Text to type' },
          },
          required: ['text'],
        },
        execute: async ({ text }: { text: string }) => {
          await this.type(text);
          return 'Typed successfully';
        },
      },
      computer_key: {
        description: 'Press a key or key combination (e.g., "Enter", "Control+C")',
        parameters: {
          type: 'object',
          properties: {
            key: { type: 'string', description: 'Key or key combination to press' },
          },
          required: ['key'],
        },
        execute: async ({ key }: { key: string }) => {
          await this.key(key);
          return 'Key pressed successfully';
        },
      },
      computer_scroll: {
        description: 'Scroll the screen',
        parameters: {
          type: 'object',
          properties: {
            direction: { type: 'string', enum: ['up', 'down', 'left', 'right'] },
            amount: { type: 'number', description: 'Scroll amount in pixels' },
          },
          required: ['direction'],
        },
        execute: async ({ direction, amount }: { direction: 'up' | 'down' | 'left' | 'right'; amount?: number }) => {
          const action: ComputerAction = { type: 'scroll', params: { direction, amount }, requiresApproval: true };
          if (!(await this.requestApproval(action))) {
            throw new Error('Scroll action denied');
          }
          await this.tools.scroll(direction, amount);
          return 'Scrolled successfully';
        },
      },
      computer_execute: {
        description: 'Execute a shell command (requires approval)',
        parameters: {
          type: 'object',
          properties: {
            command: { type: 'string', description: 'Shell command to execute' },
          },
          required: ['command'],
        },
        execute: async ({ command }: { command: string }) => {
          const result = await this.execute(command);
          return result;
        },
      },
    };
  }
}

/**
 * Create a simple approval prompt for CLI usage.
 */
export function createCLIApprovalPrompt(): (action: ComputerAction) => Promise<boolean> {
  return async (action: ComputerAction): Promise<boolean> => {
    const readline = await import('readline');
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
    });

    return new Promise((resolve) => {
      const actionDesc = `${action.type}${action.params ? `: ${JSON.stringify(action.params)}` : ''}`;
      rl.question(`\n⚠️  Approve action: ${actionDesc}? (y/n) `, (answer) => {
        rl.close();
        resolve(answer.toLowerCase() === 'y' || answer.toLowerCase() === 'yes');
      });
    });
  };
}

/**
 * Create a Computer Use agent with human-in-the-loop approval.
 * 
 * @example
 * ```typescript
 * import { Agent } from 'praisonai';
 * import { createComputerUseAgent } from 'praisonai/integrations/computer-use';
 * 
 * const agent = await createComputerUseAgent({
 *   instructions: 'You can control the computer to help the user',
 *   approvalMode: 'cli' // or 'auto' for no approval
 * });
 * 
 * await agent.chat('Open a browser and search for AI news');
 * ```
 */
export async function createComputerUseAgent(options: {
  instructions?: string;
  model?: string;
  approvalMode?: 'cli' | 'auto' | 'custom';
  onApproval?: (action: ComputerAction) => Promise<boolean>;
  tools?: Partial<ComputerUseTools>;
}): Promise<any> {
  const { Agent } = await import('../agent/simple');
  
  const computer = createComputerUse({
    requireApproval: options.approvalMode !== 'auto',
    tools: options.tools,
  });

  if (options.approvalMode === 'cli') {
    computer.onApproval(createCLIApprovalPrompt());
  } else if (options.approvalMode === 'custom' && options.onApproval) {
    computer.onApproval(options.onApproval);
  }

  const computerTools = computer.getTools();

  return new Agent({
    instructions: options.instructions || 'You are a computer use assistant. You can take screenshots, click, type, and execute commands to help the user.',
    llm: options.model || 'gpt-4o',
    tools: Object.values(computerTools),
  });
}
