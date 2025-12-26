/**
 * Interactive TUI - Terminal User Interface for CLI
 * Minimal but functional interactive mode with readline
 */

import { SlashCommandHandler, isSlashCommand, SlashCommandContext } from './slash-commands';
import { CostTracker, createCostTracker } from './cost-tracker';

export interface TUIConfig {
  prompt?: string;
  welcomeMessage?: string;
  historyFile?: string;
  maxHistorySize?: number;
  onMessage?: (message: string) => Promise<string>;
  onExit?: () => void;
}

export interface TUIState {
  running: boolean;
  history: string[];
  context: SlashCommandContext;
}

/**
 * Interactive TUI class
 */
export class InteractiveTUI {
  private config: TUIConfig;
  private state: TUIState;
  private slashHandler: SlashCommandHandler;
  private costTracker: CostTracker;
  private readline: any;
  private rl: any;

  constructor(config: TUIConfig = {}) {
    this.config = {
      prompt: '> ',
      welcomeMessage: 'PraisonAI Interactive Mode. Type /help for commands, /exit to quit.',
      maxHistorySize: 1000,
      ...config
    };

    this.costTracker = createCostTracker();
    this.state = {
      running: false,
      history: [],
      context: {
        history: [],
        settings: {},
        costTracker: this.costTracker,
        onOutput: (msg) => this.output(msg)
      }
    };

    this.slashHandler = new SlashCommandHandler(this.state.context);
  }

  /**
   * Start the interactive session
   */
  async start(): Promise<void> {
    if (this.state.running) return;

    // Lazy load readline
    this.readline = await import('readline');
    this.rl = this.readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      terminal: true
    });

    this.state.running = true;

    // Load history if available
    await this.loadHistory();

    // Show welcome message
    if (this.config.welcomeMessage) {
      this.output(this.config.welcomeMessage);
    }

    // Start the input loop
    await this.inputLoop();
  }

  /**
   * Stop the interactive session
   */
  stop(): void {
    this.state.running = false;
    if (this.rl) {
      this.rl.close();
    }
    this.saveHistory();
    this.config.onExit?.();
  }

  /**
   * Main input loop
   */
  private async inputLoop(): Promise<void> {
    while (this.state.running) {
      const input = await this.prompt();
      
      if (input === null) {
        // EOF or Ctrl+C
        this.stop();
        break;
      }

      const trimmed = input.trim();
      if (!trimmed) continue;

      // Add to history
      this.addToHistory(trimmed);

      // Handle slash commands
      if (isSlashCommand(trimmed)) {
        const result = await this.slashHandler.handle(trimmed);
        if (result.shouldExit) {
          this.stop();
          break;
        }
        continue;
      }

      // Handle regular message
      if (this.config.onMessage) {
        try {
          const response = await this.config.onMessage(trimmed);
          this.output(response);
        } catch (error: any) {
          this.output(`Error: ${error.message}`);
        }
      } else {
        this.output('No message handler configured. Use /help for available commands.');
      }
    }
  }

  /**
   * Prompt for input
   */
  private prompt(): Promise<string | null> {
    return new Promise((resolve) => {
      if (!this.state.running || !this.rl) {
        resolve(null);
        return;
      }

      this.rl.question(this.config.prompt, (answer: string) => {
        resolve(answer);
      });

      // Handle Ctrl+C
      this.rl.once('close', () => {
        resolve(null);
      });
    });
  }

  /**
   * Output a message
   */
  private output(message: string): void {
    console.log(message);
  }

  /**
   * Add input to history
   */
  private addToHistory(input: string): void {
    this.state.history.push(input);
    if (this.state.history.length > (this.config.maxHistorySize || 1000)) {
      this.state.history.shift();
    }
  }

  /**
   * Load history from file
   */
  private async loadHistory(): Promise<void> {
    if (!this.config.historyFile) return;

    try {
      const fs = await import('fs/promises');
      const content = await fs.readFile(this.config.historyFile, 'utf-8');
      this.state.history = content.trim().split('\n').filter(Boolean);
    } catch {
      // Ignore if file doesn't exist
    }
  }

  /**
   * Save history to file
   */
  private async saveHistory(): Promise<void> {
    if (!this.config.historyFile) return;

    try {
      const fs = await import('fs/promises');
      await fs.writeFile(this.config.historyFile, this.state.history.join('\n'));
    } catch {
      // Ignore save errors
    }
  }

  /**
   * Get current state
   */
  getState(): TUIState {
    return { ...this.state };
  }

  /**
   * Get cost tracker
   */
  getCostTracker(): CostTracker {
    return this.costTracker;
  }

  /**
   * Update context
   */
  updateContext(updates: Partial<SlashCommandContext>): void {
    this.slashHandler.updateContext(updates);
  }
}

/**
 * Create an interactive TUI instance
 */
export function createInteractiveTUI(config?: TUIConfig): InteractiveTUI {
  return new InteractiveTUI(config);
}

/**
 * Simple status display helper
 */
export class StatusDisplay {
  private lines: string[] = [];

  add(label: string, value: string | number): this {
    this.lines.push(`${label}: ${value}`);
    return this;
  }

  addSeparator(): this {
    this.lines.push('─'.repeat(40));
    return this;
  }

  addHeader(text: string): this {
    this.lines.push(`\n=== ${text} ===`);
    return this;
  }

  toString(): string {
    return this.lines.join('\n');
  }

  print(): void {
    console.log(this.toString());
  }

  clear(): void {
    this.lines = [];
  }
}

/**
 * Create a status display
 */
export function createStatusDisplay(): StatusDisplay {
  return new StatusDisplay();
}

/**
 * History manager for persistent command history
 */
export class HistoryManager {
  private history: string[] = [];
  private maxSize: number;
  private filePath?: string;

  constructor(maxSize: number = 1000, filePath?: string) {
    this.maxSize = maxSize;
    this.filePath = filePath;
  }

  add(entry: string): void {
    // Don't add duplicates of the last entry
    if (this.history[this.history.length - 1] === entry) return;
    
    this.history.push(entry);
    if (this.history.length > this.maxSize) {
      this.history.shift();
    }
  }

  getAll(): string[] {
    return [...this.history];
  }

  search(query: string): string[] {
    const lower = query.toLowerCase();
    return this.history.filter(h => h.toLowerCase().includes(lower));
  }

  async load(): Promise<void> {
    if (!this.filePath) return;
    
    try {
      const fs = await import('fs/promises');
      const content = await fs.readFile(this.filePath, 'utf-8');
      this.history = content.trim().split('\n').filter(Boolean);
    } catch {
      // File doesn't exist yet
    }
  }

  async save(): Promise<void> {
    if (!this.filePath) return;
    
    try {
      const fs = await import('fs/promises');
      await fs.writeFile(this.filePath, this.history.join('\n'));
    } catch {
      // Ignore save errors
    }
  }

  clear(): void {
    this.history = [];
  }
}

/**
 * Create a history manager
 */
export function createHistoryManager(maxSize?: number, filePath?: string): HistoryManager {
  return new HistoryManager(maxSize, filePath);
}
