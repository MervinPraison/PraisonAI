import { OpenAIService } from '../llm/openai';

export interface SimpleAgentConfig {
  instructions: string;
  name?: string;
  verbose?: boolean;
  llm?: string;
  markdown?: boolean;
}

export class Agent {
  private instructions: string;
  public name: string;
  private verbose: boolean;
  private llm: string;
  private markdown: boolean;
  private llmService: OpenAIService;
  private result: string | null = null;

  constructor(config: SimpleAgentConfig) {
    this.instructions = config.instructions;
    this.name = config.name || `Agent_${Math.random().toString(36).substr(2, 9)}`;
    this.verbose = config.verbose || false;
    this.llm = config.llm || 'gpt-4o-mini';
    this.markdown = config.markdown || true;
    this.llmService = new OpenAIService(this.llm);
  }

  private createSystemPrompt(): string {
    return `${this.instructions}
Please provide detailed, accurate, and helpful responses.
Format your response in markdown if appropriate.`;
  }

  async start(prompt: string, previousResult?: string): Promise<string> {
    if (this.verbose) {
      console.log(`Agent ${this.name} starting with prompt: ${prompt}`);
    }

    try {
      // Replace placeholder with previous result if available
      const finalPrompt = previousResult 
        ? prompt.replace('{previous_result}', previousResult)
        : prompt;

      if (this.verbose) {
        console.log('Generating response (streaming)...');
        await this.llmService.streamText(
          finalPrompt,
          this.createSystemPrompt(),
          0.7,
          (token) => process.stdout.write(token)
        );
        console.log('\n');
      }

      // Get the final response
      this.result = await this.llmService.generateText(
        finalPrompt,
        this.createSystemPrompt()
      );

      return this.result;
    } catch (error) {
      console.error(`Error executing prompt: ${error}`);
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
    return this.result;
  }
}

export interface PraisonAIAgentsConfig {
  agents: Agent[];
  tasks: string[];
  verbose?: boolean;
  process?: 'sequential' | 'parallel';
}

export class PraisonAIAgents {
  private agents: Agent[];
  private tasks: string[];
  private verbose: boolean;
  private process: 'sequential' | 'parallel';

  constructor(config: PraisonAIAgentsConfig) {
    this.agents = config.agents;
    this.tasks = config.tasks;
    this.verbose = config.verbose || false;
    this.process = config.process || 'sequential';
  }

  async start(): Promise<string[]> {
    if (this.verbose) {
      console.log('Starting PraisonAI Agents execution...');
    }

    let results: string[];

    if (this.process === 'parallel') {
      results = await Promise.all(this.tasks.map((task, index) => 
        this.agents[index].start(task)
      ));
    } else {
      results = await this.executeSequential();
    }

    if (this.verbose) {
      console.log('PraisonAI Agents execution completed.');
      results.forEach((result, index) => {
        console.log(`\nResult from Agent ${index + 1}:`);
        console.log(result);
      });
    }

    return results;
  }

  async chat(): Promise<string[]> {
    return this.start();
  }

  private async executeSequential(): Promise<string[]> {
    const results: string[] = [];

    for (let i = 0; i < this.agents.length; i++) {
      const agent = this.agents[i];
      const task = this.tasks[i];
      const previousResult = i > 0 ? results[i - 1] : undefined;

      if (this.verbose) {
        console.log(`Agent ${agent.name} starting with prompt: ${task}`);
      }

      const result = await agent.start(task, previousResult);
      results.push(result);
    }

    return results;
  }
}
