import { OpenAIService } from '../llm/openai';
import { Logger } from '../utils/logger';
import type { ChatCompletionTool } from 'openai/resources/chat/completions';
import type { DbAdapter, DbMessage, DbRun } from '../db/types';
import { randomUUID } from 'crypto';

/**
 * Agent Configuration
 * 
 * The Agent class is the primary entry point for PraisonAI.
 * It supports both simple instruction-based agents and advanced configurations.
 * 
 * @example Simple usage (3 lines)
 * ```typescript
 * import { Agent } from 'praisonai';
 * const agent = new Agent({ instructions: "You are helpful" });
 * await agent.chat("Hello!");
 * ```
 * 
 * @example With tools (5 lines)
 * ```typescript
 * const getWeather = (city: string) => `Weather in ${city}: 20°C`;
 * const agent = new Agent({
 *   instructions: "You provide weather info",
 *   tools: [getWeather]
 * });
 * await agent.chat("Weather in Paris?");
 * ```
 * 
 * @example With persistence (4 lines)
 * ```typescript
 * import { Agent, db } from 'praisonai';
 * const agent = new Agent({
 *   instructions: "You are helpful",
 *   db: db("sqlite:./data.db"),
 *   sessionId: "my-session"
 * });
 * await agent.chat("Hello!");
 * ```
 */
export interface SimpleAgentConfig {
  /** Agent instructions/system prompt (required) */
  instructions: string;
  /** Agent name (auto-generated if not provided) */
  name?: string;
  /** Enable verbose logging (default: true) */
  verbose?: boolean;
  /** Enable pretty output formatting */
  pretty?: boolean;
  /** 
   * LLM model to use. Accepts:
   * - Model name: "gpt-4o-mini", "claude-3-sonnet"
   * - Provider/model: "openai/gpt-4o", "anthropic/claude-3"
   * Default: "gpt-4o-mini"
   */
  llm?: string;
  /** Enable markdown formatting in responses */
  markdown?: boolean;
  /** Enable streaming responses (default: true) */
  stream?: boolean;
  /** 
   * Tools available to the agent.
   * Can be plain functions (auto-schema) or OpenAI tool definitions.
   */
  tools?: any[] | Function[];
  /** Map of tool function implementations */
  toolFunctions?: Record<string, Function>;
  /** Database adapter for persistence */
  db?: DbAdapter;
  /** Session ID for conversation persistence (auto-generated if not provided) */
  sessionId?: string;
  /** Run ID for tracing (auto-generated if not provided) */
  runId?: string;
  /** Max messages to restore from history (default: 100) */
  historyLimit?: number;
  /** Auto-restore conversation history from db (default: true) */
  autoRestore?: boolean;
  /** Auto-persist messages to db (default: true) */
  autoPersist?: boolean;
  /** Enable caching of responses */
  cache?: boolean;
  /** Cache TTL in seconds (default: 3600) */
  cacheTTL?: number;
  /** Enable telemetry tracking (default: false, opt-in) */
  telemetry?: boolean;
  
  // Advanced mode (role/goal/backstory) - for compatibility
  /** Agent role (advanced mode) */
  role?: string;
  /** Agent goal (advanced mode) */
  goal?: string;
  /** Agent backstory (advanced mode) */
  backstory?: string;
}

export class Agent {
  private instructions: string;
  public name: string;
  private verbose: boolean;
  private pretty: boolean;
  private llm: string;
  private markdown: boolean;
  private stream: boolean;
  private llmService: OpenAIService;
  private tools?: any[];
  private toolFunctions: Record<string, Function> = {};
  private dbAdapter?: DbAdapter;
  private sessionId: string;
  private runId: string;
  private messages: Array<{ role: string; content: string | null; tool_calls?: any[]; tool_call_id?: string }> = [];
  private dbInitialized: boolean = false;
  private historyLimit: number;
  private autoRestore: boolean;
  private autoPersist: boolean;
  private cache: boolean;
  private cacheTTL: number;
  private responseCache: Map<string, { response: string; timestamp: number }> = new Map();
  private telemetryEnabled: boolean;

  constructor(config: SimpleAgentConfig) {
    // Build instructions from either simple or advanced mode
    if (config.instructions) {
      this.instructions = config.instructions;
    } else if (config.role || config.goal || config.backstory) {
      // Advanced mode: construct instructions from role/goal/backstory
      const parts: string[] = [];
      if (config.role) parts.push(`You are a ${config.role}.`);
      if (config.goal) parts.push(`Your goal is: ${config.goal}`);
      if (config.backstory) parts.push(`Background: ${config.backstory}`);
      this.instructions = parts.join('\n');
    } else {
      this.instructions = 'You are a helpful AI assistant.';
    }
    
    this.name = config.name || `Agent_${Math.random().toString(36).substr(2, 9)}`;
    this.verbose = config.verbose ?? process.env.PRAISON_VERBOSE !== 'false';
    this.pretty = config.pretty ?? process.env.PRAISON_PRETTY === 'true';
    this.llm = config.llm || process.env.OPENAI_MODEL_NAME || process.env.PRAISONAI_MODEL || 'gpt-4o-mini';
    this.markdown = config.markdown ?? true;
    this.stream = config.stream ?? true;
    this.tools = config.tools;
    this.dbAdapter = config.db;
    this.sessionId = config.sessionId || this.generateSessionId();
    this.runId = config.runId || randomUUID();
    this.historyLimit = config.historyLimit ?? 100;
    this.autoRestore = config.autoRestore ?? true;
    this.autoPersist = config.autoPersist ?? true;
    this.cache = config.cache ?? false;
    this.cacheTTL = config.cacheTTL ?? 3600;
    this.telemetryEnabled = config.telemetry ?? false;
    this.llmService = new OpenAIService(this.llm);

    // Configure logging
    Logger.setVerbose(this.verbose);
    Logger.setPretty(this.pretty);
    
    // Process tools array - handle both tool definitions and functions
    if (config.tools && Array.isArray(config.tools)) {
      // Convert tools array to proper format if it contains functions
      const processedTools: any[] = [];
      
      for (let i = 0; i < config.tools.length; i++) {
        const tool = config.tools[i];
        
        if (typeof tool === 'function') {
          // If it's a function, extract its name and register it
          const funcName = tool.name || `function_${i}`;
          
          // Skip functions with empty names
          if (funcName && funcName.trim() !== '') {
            this.registerToolFunction(funcName, tool);
            
            // Auto-generate tool definition
            this.addAutoGeneratedToolDefinition(funcName, tool);
          } else {
            // Generate a random name for functions without names
            const randomName = `function_${Math.random().toString(36).substring(2, 9)}`;
            this.registerToolFunction(randomName, tool);
            
            // Auto-generate tool definition
            this.addAutoGeneratedToolDefinition(randomName, tool);
          }
        } else {
          // If it's already a tool definition, add it as is
          processedTools.push(tool);
        }
      }
      
      // Add any pre-defined tool definitions
      if (processedTools.length > 0) {
        this.tools = this.tools || [];
        this.tools.push(...processedTools);
      }
    }
    
    // Register directly provided tool functions if any
    if (config.toolFunctions) {
      for (const [name, func] of Object.entries(config.toolFunctions)) {
        this.registerToolFunction(name, func);
        
        // Auto-generate tool definition if not already provided
        if (!this.hasToolDefinition(name)) {
          this.addAutoGeneratedToolDefinition(name, func);
        }
      }
    }
  }

  /**
   * Generate a session ID based on current hour and agent name (like Python SDK)
   */
  private generateSessionId(): string {
    const now = new Date();
    const hourStr = now.toISOString().slice(0, 13).replace(/[-T:]/g, '');
    const hash = this.name ? this.name.slice(0, 6) : 'agent';
    return `${hourStr}-${hash}`;
  }

  /**
   * Initialize DB session - restore history on first chat (lazy)
   */
  private async initDbSession(): Promise<void> {
    if (this.dbInitialized || !this.dbAdapter || !this.autoRestore) return;
    
    try {
      // Restore previous messages from DB
      const history = await this.dbAdapter.getMessages(this.sessionId, this.historyLimit);
      if (history.length > 0) {
        this.messages = history.map(m => ({
          role: m.role,
          content: m.content
        }));
        Logger.debug(`Restored ${history.length} messages from session ${this.sessionId}`);
      }
    } catch (error) {
      Logger.warn('Failed to initialize DB session:', error);
    }
    
    this.dbInitialized = true;
  }

  /**
   * Get cached response if available and not expired
   */
  private getCachedResponse(prompt: string): string | null {
    if (!this.cache) return null;
    
    const cacheKey = `${this.sessionId}:${prompt}`;
    const cached = this.responseCache.get(cacheKey);
    
    if (cached) {
      const age = (Date.now() - cached.timestamp) / 1000;
      if (age < this.cacheTTL) {
        Logger.debug('Cache hit for prompt');
        return cached.response;
      }
      // Expired, remove it
      this.responseCache.delete(cacheKey);
    }
    return null;
  }

  /**
   * Cache a response
   */
  private cacheResponse(prompt: string, response: string): void {
    if (!this.cache) return;
    
    const cacheKey = `${this.sessionId}:${prompt}`;
    this.responseCache.set(cacheKey, { response, timestamp: Date.now() });
  }

  private createSystemPrompt(): string {
    let prompt = this.instructions;
    if (this.markdown) {
      prompt += '\nPlease format your response in markdown.';
    }
    return prompt;
  }

  /**
   * Register a tool function that can be called by the model
   * @param name Function name
   * @param fn Function implementation
   */
  registerToolFunction(name: string, fn: Function): void {
    this.toolFunctions[name] = fn;
    Logger.debug(`Registered tool function: ${name}`);
  }
  
  /**
   * Check if a tool definition exists for the given function name
   * @param name Function name
   * @returns True if a tool definition exists
   */
  private hasToolDefinition(name: string): boolean {
    if (!this.tools) return false;
    
    return this.tools.some(tool => {
      if (tool.type === 'function' && tool.function) {
        return tool.function.name === name;
      }
      return false;
    });
  }
  
  /**
   * Auto-generate a tool definition based on the function
   * @param name Function name
   * @param func Function implementation
   */
  private addAutoGeneratedToolDefinition(name: string, func: Function): void {
    if (!this.tools) {
      this.tools = [];
    }
    
    // Ensure we have a valid function name
    const functionName = name || func.name || `function_${Math.random().toString(36).substring(2, 9)}`;
    
    // Extract parameter names from function
    const funcStr = func.toString();
    const paramMatch = funcStr.match(/\(([^)]*)\)/);
    const params = paramMatch ? paramMatch[1].split(',').map(p => p.trim()).filter(p => p) : [];
    
    // Create a basic tool definition
    const toolDef = {
      type: "function",
      function: {
        name: functionName,
        description: `Auto-generated function for ${functionName}`,
        parameters: {
          type: "object",
          properties: {},
          required: [] as string[]
        }
      }
    };
    
    // Add parameters to the definition
    if (params.length > 0) {
      const properties: Record<string, any> = {};
      const required: string[] = [];
      
      params.forEach(param => {
        // Remove type annotations if present
        const paramName = param.split(':')[0].trim();
        if (paramName) {
          properties[paramName] = {
            type: "string",
            description: `Parameter ${paramName} for function ${name}`
          };
          required.push(paramName);
        }
      });
      
      toolDef.function.parameters.properties = properties;
      toolDef.function.parameters.required = required;
    }
    
    this.tools.push(toolDef);
    Logger.debug(`Auto-generated tool definition for ${functionName}`);
  }

  /**
   * Process tool calls from the model
   * @param toolCalls Tool calls from the model
   * @returns Array of tool results
   */
  private async processToolCalls(toolCalls: Array<any>): Promise<Array<{role: string, tool_call_id: string, content: string}>> {
    const results = [];
    
    for (const toolCall of toolCalls) {
      const { id, function: { name, arguments: argsString } } = toolCall;
      await Logger.debug(`Processing tool call: ${name}`, { arguments: argsString });
      
      try {
        // Parse arguments
        const args = JSON.parse(argsString);
        
        // Check if function exists
        if (!this.toolFunctions[name]) {
          throw new Error(`Function ${name} not registered`);
        }
        
        // Call the function
        const result = await this.toolFunctions[name](...Object.values(args));
        
        // Add result to messages
        results.push({
          role: 'tool',
          tool_call_id: id,
          content: result.toString()
        });
        
        await Logger.debug(`Tool call result for ${name}:`, { result });
      } catch (error: any) {
        await Logger.error(`Error executing tool ${name}:`, error);
        results.push({
          role: 'tool',
          tool_call_id: id,
          content: `Error: ${error.message || 'Unknown error'}`
        });
      }
    }
    
    return results;
  }

  async start(prompt: string, previousResult?: string): Promise<string> {
    await Logger.debug(`Agent ${this.name} starting with prompt: ${prompt}`);

    try {
      // Replace placeholder with previous result if available
      if (previousResult) {
        prompt = prompt.replace('{{previous}}', previousResult);
      }

      // Initialize messages array
      const messages: Array<any> = [
        { role: 'system', content: this.createSystemPrompt() },
        { role: 'user', content: prompt }
      ];
      
      let finalResponse = '';
      
      if (this.stream && !this.tools) {
        // Use streaming without tools
        let fullResponse = '';
        await this.llmService.streamText(
          prompt,
          this.createSystemPrompt(),
          0.7,
          (token: string) => {
            process.stdout.write(token);
            fullResponse += token;
          }
        );
        finalResponse = fullResponse;
      } else if (this.tools) {
        // Use tools (non-streaming for now to simplify implementation)
        let continueConversation = true;
        let iterations = 0;
        const maxIterations = 5; // Prevent infinite loops
        
        while (continueConversation && iterations < maxIterations) {
          iterations++;
          
          // Get response from LLM
          const response = await this.llmService.generateChat(messages, 0.7, this.tools);
          
          // Add assistant response to messages
          messages.push({
            role: 'assistant',
            content: response.content || '',
            tool_calls: response.tool_calls
          });
          
          // Check if there are tool calls to process
          if (response.tool_calls && response.tool_calls.length > 0) {
            // Process tool calls
            const toolResults = await this.processToolCalls(response.tool_calls);
            
            // Add tool results to messages
            messages.push(...toolResults);
            
            // Continue conversation to get final response
            continueConversation = true;
          } else {
            // No tool calls, we have our final response
            finalResponse = response.content || '';
            continueConversation = false;
          }
        }
        
        if (iterations >= maxIterations) {
          await Logger.warn(`Reached maximum iterations (${maxIterations}) for tool calls`);
        }
      } else {
        // Use regular text generation without streaming
        const response = await this.llmService.generateText(
          prompt,
          this.createSystemPrompt()
        );
        finalResponse = response;
      }

      return finalResponse;
    } catch (error) {
      await Logger.error('Error in agent execution', error);
      throw error;
    }
  }

  async chat(prompt: string, previousResult?: string): Promise<string> {
    // Lazy init: restore history on first chat (like Python SDK)
    await this.initDbSession();
    
    // Check cache first
    const cached = this.getCachedResponse(prompt);
    if (cached) {
      return cached;
    }
    
    // Add user message to conversation history
    this.messages.push({ role: 'user', content: prompt });
    
    // Persist user message if db is configured and autoPersist is enabled
    if (this.dbAdapter && this.autoPersist) {
      await this.persistMessage('user', prompt);
    }
    
    const response = await this.start(prompt, previousResult);
    
    // Add assistant response to history
    this.messages.push({ role: 'assistant', content: response });
    
    // Persist assistant response if db is configured and autoPersist is enabled
    if (this.dbAdapter && this.autoPersist) {
      await this.persistMessage('assistant', response);
    }
    
    // Cache the response
    this.cacheResponse(prompt, response);
    
    return response;
  }

  async execute(previousResult?: string): Promise<string> {
    // For backward compatibility and multi-agent support
    return this.start(this.instructions, previousResult);
  }

  /**
   * Persist a message to the database
   */
  private async persistMessage(role: 'user' | 'assistant' | 'system' | 'tool', content: string): Promise<void> {
    if (!this.dbAdapter) return;
    
    try {
      const message: DbMessage = {
        id: randomUUID(),
        sessionId: this.sessionId,
        runId: this.runId,
        role,
        content,
        createdAt: Date.now()
      };
      await this.dbAdapter.saveMessage(message);
    } catch (error) {
      await Logger.warn('Failed to persist message:', error);
    }
  }

  /**
   * Get the session ID for this agent
   */
  getSessionId(): string {
    return this.sessionId;
  }

  /**
   * Get the run ID for this agent
   */
  getRunId(): string {
    return this.runId;
  }

  getResult(): string | null {
    return null;
  }

  getInstructions(): string {
    return this.instructions;
  }

  /**
   * Get conversation history
   */
  getHistory(): Array<{ role: string; content: string | null }> {
    return [...this.messages];
  }

  /**
   * Clear conversation history (in memory and optionally in DB)
   */
  async clearHistory(clearDb: boolean = true): Promise<void> {
    this.messages = [];
    if (clearDb && this.dbAdapter) {
      try {
        await this.dbAdapter.deleteMessages(this.sessionId);
        Logger.debug(`Cleared history for session ${this.sessionId}`);
      } catch (error) {
        Logger.warn('Failed to clear DB history:', error);
      }
    }
  }

  /**
   * Clear response cache
   */
  clearCache(): void {
    this.responseCache.clear();
  }
}

/**
 * Configuration for multi-agent orchestration
 */
export interface PraisonAIAgentsConfig {
  agents: Agent[];
  tasks?: string[];
  verbose?: boolean;
  pretty?: boolean;
  process?: 'sequential' | 'parallel';
}

/**
 * Multi-agent orchestration class
 * 
 * @example Simple array syntax
 * ```typescript
 * import { Agent, Agents } from 'praisonai';
 * 
 * const researcher = new Agent({ instructions: "Research the topic" });
 * const writer = new Agent({ instructions: "Write based on research" });
 * 
 * const agents = new Agents([researcher, writer]);
 * await agents.start();
 * ```
 * 
 * @example Config object syntax
 * ```typescript
 * const agents = new Agents({
 *   agents: [researcher, writer],
 *   process: 'parallel'
 * });
 * ```
 */
export class PraisonAIAgents {
  private agents: Agent[];
  private tasks: string[];
  private verbose: boolean;
  private pretty: boolean;
  private process: 'sequential' | 'parallel';

  /**
   * Create a multi-agent orchestration
   * @param configOrAgents - Either an array of agents or a config object
   */
  constructor(configOrAgents: PraisonAIAgentsConfig | Agent[]) {
    // Support array syntax: new Agents([a1, a2])
    const config: PraisonAIAgentsConfig = Array.isArray(configOrAgents) 
      ? { agents: configOrAgents }
      : configOrAgents;
    
    this.agents = config.agents;
    this.verbose = config.verbose ?? process.env.PRAISON_VERBOSE !== 'false';
    this.pretty = config.pretty ?? process.env.PRAISON_PRETTY === 'true';
    this.process = config.process || 'sequential';

    // Auto-generate tasks if not provided
    this.tasks = config.tasks || this.generateTasks();

    // Configure logging
    Logger.setVerbose(this.verbose);
    Logger.setPretty(this.pretty);
  }

  private generateTasks(): string[] {
    return this.agents.map(agent => {
      const instructions = agent.getInstructions();
      // Extract task from instructions - get first sentence or whole instruction if no period
      const task = instructions.split('.')[0].trim();
      return task;
    });
  }

  private async executeSequential(): Promise<string[]> {
    const results: string[] = [];
    let previousResult: string | undefined;

    for (let i = 0; i < this.agents.length; i++) {
      const agent = this.agents[i];
      const task = this.tasks[i];

      await Logger.debug(`Running agent ${i + 1}: ${agent.name}`);
      await Logger.debug(`Task: ${task}`);
      
      // For first agent, use task directly
      // For subsequent agents, append previous result to their instructions
      const prompt = i === 0 ? task : `${task}\n\nHere is the input: ${previousResult}`;
      const result = await agent.start(prompt, previousResult);
      results.push(result);
      previousResult = result;
    }

    return results;
  }

  async start(): Promise<string[]> {
    await Logger.debug('Starting PraisonAI Agents execution...');
    await Logger.debug('Process mode:', this.process);
    await Logger.debug('Tasks:', this.tasks);

    let results: string[];

    if (this.process === 'parallel') {
      // Run all agents in parallel
      const promises = this.agents.map((agent, i) => {
        const task = this.tasks[i];
        return agent.start(task);
      });
      results = await Promise.all(promises);
    } else {
      // Run agents sequentially (default)
      results = await this.executeSequential();
    }

    if (this.verbose) {
      await Logger.info('PraisonAI Agents execution completed.');
      for (let i = 0; i < results.length; i++) {
        await Logger.section(`Result from Agent ${i + 1}`, results[i]);
      }
    }

    return results;
  }

  async chat(): Promise<string[]> {
    return this.start();
  }
}

/**
 * Agents - Alias for PraisonAIAgents
 * 
 * This is the recommended class name for multi-agent orchestration.
 * PraisonAIAgents is kept for backward compatibility.
 * 
 * @example
 * ```typescript
 * import { Agent, Agents } from 'praisonai';
 * 
 * const agents = new Agents([
 *   new Agent({ instructions: "Research the topic" }),
 *   new Agent({ instructions: "Write based on research" })
 * ]);
 * await agents.start();
 * ```
 */
export const Agents = PraisonAIAgents;
