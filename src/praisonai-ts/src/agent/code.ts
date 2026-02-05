/**
 * CodeAgent - Code generation, execution, review, and refactoring
 * 
 * Python parity with praisonaiagents/agent/code_agent.py
 */

import { Agent, SimpleAgentConfig } from './simple';

// ============================================================================
// Configuration Types
// ============================================================================

/**
 * Configuration for CodeAgent.
 * Python parity with CodeConfig dataclass.
 */
export interface CodeConfig {
  /** Enable sandboxed execution (default: true for safety) */
  sandbox?: boolean;
  /** Execution timeout in seconds */
  timeout?: number;
  /** List of allowed programming languages */
  allowedLanguages?: string[];
  /** Maximum output length in characters */
  maxOutputLength?: number;
  /** Working directory for code execution */
  workingDirectory?: string;
  /** Environment variables for execution */
  environment?: Record<string, string>;
}

/**
 * Result of code execution.
 */
export interface CodeExecutionResult {
  /** Whether execution was successful */
  success: boolean;
  /** Standard output from execution */
  output: string;
  /** Error message if execution failed */
  error?: string;
  /** Exit code from execution */
  exitCode: number;
  /** Execution time in seconds */
  executionTime: number;
}

/**
 * Configuration for creating a CodeAgent.
 */
export interface CodeAgentConfig {
  /** Agent name */
  name?: string;
  /** LLM model (default: gpt-4o-mini) */
  llm?: string;
  /** Code configuration (bool, object, or CodeConfig) */
  code?: boolean | CodeConfig;
  /** System instructions */
  instructions?: string;
  /** Enable verbose output */
  verbose?: boolean;
}

// ============================================================================
// Default Configuration
// ============================================================================

const DEFAULT_CODE_CONFIG: Required<CodeConfig> = {
  sandbox: true,
  timeout: 30,
  allowedLanguages: ['python'],
  maxOutputLength: 10000,
  workingDirectory: process.cwd(),
  environment: {},
};

// ============================================================================
// CodeAgent Class
// ============================================================================

/**
 * Agent for code generation, execution, review, and refactoring.
 * 
 * This agent provides capabilities for:
 * - Generating code from natural language descriptions
 * - Executing code in a sandboxed environment
 * - Reviewing code for issues and improvements
 * - Refactoring and fixing code
 * - Explaining code functionality
 * 
 * @example
 * ```typescript
 * import { CodeAgent } from 'praisonai';
 * 
 * const agent = new CodeAgent({ name: 'Coder' });
 * 
 * // Generate code
 * const code = await agent.generate('Write a function to calculate fibonacci');
 * 
 * // Execute code
 * const result = await agent.execute("console.log('Hello, World!')");
 * 
 * // Review code
 * const review = await agent.review(code);
 * ```
 */
export class CodeAgent {
  readonly name: string;
  private readonly llm: string;
  private readonly instructions?: string;
  private readonly verbose: boolean;
  private readonly codeConfig: Required<CodeConfig>;
  private readonly agent: Agent;

  constructor(config: CodeAgentConfig) {
    this.name = config.name || 'CodeAgent';
    this.llm = config.llm || process.env.OPENAI_MODEL_NAME || 'gpt-4o-mini';
    this.instructions = config.instructions;
    this.verbose = config.verbose ?? true;

    // Resolve code configuration
    if (config.code === undefined || config.code === true) {
      this.codeConfig = { ...DEFAULT_CODE_CONFIG };
    } else if (typeof config.code === 'object') {
      this.codeConfig = { ...DEFAULT_CODE_CONFIG, ...config.code };
    } else {
      this.codeConfig = { ...DEFAULT_CODE_CONFIG };
    }

    // Create underlying agent for LLM calls
    this.agent = new Agent({
      name: this.name,
      instructions: this.buildSystemPrompt(),
      llm: this.llm,
      verbose: this.verbose,
    });
  }

  private buildSystemPrompt(): string {
    let prompt = `You are an expert programmer and code assistant.
You can generate, review, refactor, fix, and explain code.
Follow best practices and coding standards.
Write clean, well-documented, production-ready code.`;

    if (this.instructions) {
      prompt += `\n\nAdditional instructions: ${this.instructions}`;
    }

    return prompt;
  }

  // =========================================================================
  // Code Generation Methods
  // =========================================================================

  /**
   * Generate code from natural language description.
   * 
   * @param prompt - Natural language description of desired code
   * @param language - Target programming language (default: python)
   * @returns Generated code as string
   */
  async generate(prompt: string, language: string = 'python'): Promise<string> {
    const systemPrompt = `You are an expert ${language} programmer.
Generate clean, well-documented, production-ready code.
Only output the code, no explanations unless asked.
Follow best practices and coding standards.`;

    const response = await this.agent.chat(
      `Generate ${language} code for: ${prompt}`,
    );
    
    return response;
  }

  /**
   * Alias for generate() method.
   */
  async generateCode(prompt: string, language: string = 'python'): Promise<string> {
    return this.generate(prompt, language);
  }

  // =========================================================================
  // Code Execution Methods
  // =========================================================================

  /**
   * Execute code in a sandboxed environment.
   * 
   * @param code - Code to execute
   * @param language - Programming language (default: python)
   * @returns Execution result
   */
  async execute(code: string, language: string = 'python'): Promise<CodeExecutionResult> {
    // Check if language is allowed
    if (!this.codeConfig.allowedLanguages.includes(language)) {
      return {
        success: false,
        output: '',
        error: `Language '${language}' is not allowed. Allowed: ${this.codeConfig.allowedLanguages.join(', ')}`,
        exitCode: 1,
        executionTime: 0,
      };
    }

    const startTime = Date.now();

    try {
      // For safety, we use the sandbox executor if available
      // This is a simplified implementation - full sandbox would use child_process
      if (language === 'javascript' || language === 'typescript') {
        // Use eval for simple JS (NOT SAFE FOR PRODUCTION - use sandbox)
        if (!this.codeConfig.sandbox) {
          const result = eval(code);
          return {
            success: true,
            output: String(result ?? ''),
            exitCode: 0,
            executionTime: (Date.now() - startTime) / 1000,
          };
        }
      }

      // For other languages or sandboxed execution, return placeholder
      return {
        success: false,
        output: '',
        error: `Sandboxed execution for '${language}' requires additional setup. Use sandbox executor.`,
        exitCode: 1,
        executionTime: (Date.now() - startTime) / 1000,
      };
    } catch (error) {
      return {
        success: false,
        output: '',
        error: error instanceof Error ? error.message : String(error),
        exitCode: 1,
        executionTime: (Date.now() - startTime) / 1000,
      };
    }
  }

  /**
   * Alias for execute() method.
   */
  async executeCode(code: string, language: string = 'python'): Promise<CodeExecutionResult> {
    return this.execute(code, language);
  }

  // =========================================================================
  // Code Review Methods
  // =========================================================================

  /**
   * Review code for issues and improvements.
   * 
   * @param code - Code to review
   * @param language - Programming language
   * @returns Review feedback
   */
  async review(code: string, language?: string): Promise<string> {
    const langHint = language ? ` (${language})` : '';
    const response = await this.agent.chat(
      `Review the following code${langHint} for issues, bugs, and improvements:\n\n\`\`\`\n${code}\n\`\`\``,
    );
    return response;
  }

  /**
   * Alias for review() method.
   */
  async reviewCode(code: string, language?: string): Promise<string> {
    return this.review(code, language);
  }

  // =========================================================================
  // Code Refactoring Methods
  // =========================================================================

  /**
   * Refactor code for better quality.
   * 
   * @param code - Code to refactor
   * @param instructions - Specific refactoring instructions
   * @returns Refactored code
   */
  async refactor(code: string, instructions?: string): Promise<string> {
    const prompt = instructions
      ? `Refactor the following code according to these instructions: ${instructions}\n\n\`\`\`\n${code}\n\`\`\``
      : `Refactor the following code for better readability, performance, and maintainability:\n\n\`\`\`\n${code}\n\`\`\``;
    
    const response = await this.agent.chat(prompt);
    return response;
  }

  /**
   * Fix bugs in code.
   * 
   * @param code - Code with bugs
   * @param errorMessage - Optional error message to help identify the bug
   * @returns Fixed code
   */
  async fix(code: string, errorMessage?: string): Promise<string> {
    const prompt = errorMessage
      ? `Fix the bug in the following code. Error: ${errorMessage}\n\n\`\`\`\n${code}\n\`\`\``
      : `Fix any bugs in the following code:\n\n\`\`\`\n${code}\n\`\`\``;
    
    const response = await this.agent.chat(prompt);
    return response;
  }

  /**
   * Explain code functionality.
   * 
   * @param code - Code to explain
   * @returns Explanation of the code
   */
  async explain(code: string): Promise<string> {
    const response = await this.agent.chat(
      `Explain what the following code does in detail:\n\n\`\`\`\n${code}\n\`\`\``,
    );
    return response;
  }
}

// ============================================================================
// Factory Function
// ============================================================================

/**
 * Create a CodeAgent instance.
 * 
 * @param config - CodeAgent configuration
 * @returns CodeAgent instance
 */
export function createCodeAgent(config: CodeAgentConfig): CodeAgent {
  return new CodeAgent(config);
}
