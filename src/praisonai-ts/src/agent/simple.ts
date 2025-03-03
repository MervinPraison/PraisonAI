import { OpenAIService } from '../llm/openai';
import { Logger } from '../utils/logger';
import type { ChatCompletionTool } from 'openai/resources/chat/completions';

export interface SimpleAgentConfig {
  instructions: string;
  name?: string;
  verbose?: boolean;
  pretty?: boolean;
  llm?: string;
  markdown?: boolean;
  stream?: boolean;
  tools?: any[];
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

  constructor(config: SimpleAgentConfig) {
    this.instructions = config.instructions;
    this.name = config.name || `Agent_${Math.random().toString(36).substr(2, 9)}`;
    this.verbose = config.verbose ?? process.env.PRAISON_VERBOSE !== 'false';
    this.pretty = config.pretty ?? process.env.PRAISON_PRETTY === 'true';
    this.llm = config.llm || 'gpt-4o-mini';
    this.markdown = config.markdown ?? true;
    this.stream = config.stream ?? true;
    this.tools = config.tools;
    this.llmService = new OpenAIService(this.llm);

    // Configure logging
    Logger.setVerbose(this.verbose);
    Logger.setPretty(this.pretty);
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
    return this.start(prompt, previousResult);
  }

  async execute(previousResult?: string): Promise<string> {
    // For backward compatibility and multi-agent support
    return this.start(this.instructions, previousResult);
  }

  getResult(): string | null {
    return null;
  }

  getInstructions(): string {
    return this.instructions;
  }
}

export interface PraisonAIAgentsConfig {
  agents: Agent[];
  tasks?: string[];
  verbose?: boolean;
  pretty?: boolean;
  process?: 'sequential' | 'parallel';
}

export class PraisonAIAgents {
  private agents: Agent[];
  private tasks: string[];
  private verbose: boolean;
  private pretty: boolean;
  private process: 'sequential' | 'parallel';

  constructor(config: PraisonAIAgentsConfig) {
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
