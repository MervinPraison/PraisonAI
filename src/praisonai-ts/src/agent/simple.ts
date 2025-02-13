import { OpenAIService } from '../llm/openai';
import { Logger } from '../utils/logger';

export interface SimpleAgentConfig {
  instructions: string;
  name?: string;
  verbose?: boolean;
  pretty?: boolean;
  llm?: string;
  markdown?: boolean;
  stream?: boolean;
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

  constructor(config: SimpleAgentConfig) {
    this.instructions = config.instructions;
    this.name = config.name || `Agent_${Math.random().toString(36).substr(2, 9)}`;
    this.verbose = config.verbose ?? process.env.PRAISON_VERBOSE !== 'false';
    this.pretty = config.pretty ?? process.env.PRAISON_PRETTY === 'true';
    this.llm = config.llm || 'gpt-4o-mini';
    this.markdown = config.markdown ?? true;
    this.stream = config.stream ?? true;
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

  async start(prompt: string, previousResult?: string): Promise<string> {
    await Logger.debug(`Agent ${this.name} starting with prompt: ${prompt}`);

    try {
      // Replace placeholder with previous result if available
      if (previousResult) {
        prompt = prompt.replace('{{previous}}', previousResult);
      }

      let response: string;
      if (this.stream) {
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
        response = fullResponse;
      } else {
        response = await this.llmService.generateText(
          prompt,
          this.createSystemPrompt()
        );
      }

      return response;
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
