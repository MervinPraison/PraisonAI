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
  private name: string;
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
    return `You are an AI assistant tasked with helping users with their requests.
Please provide detailed, accurate, and helpful responses.
Format your response in markdown if appropriate.`;
  }

  async execute(previousResult?: string): Promise<string> {
    if (this.verbose) {
      console.log(`Agent ${this.name} executing instructions: ${this.instructions}`);
    }

    try {
      // Replace placeholder with previous result if available
      const finalInstructions = previousResult 
        ? this.instructions.replace('{previous_result}', previousResult)
        : this.instructions;

      if (this.verbose) {
        console.log('Generating response (streaming)...');
        await this.llmService.streamText(
          finalInstructions,
          this.createSystemPrompt(),
          0.7,
          (token) => process.stdout.write(token)
        );
        console.log('\n');
      }

      // Get the final response
      this.result = await this.llmService.generateText(
        finalInstructions,
        this.createSystemPrompt()
      );

      return this.result;
    } catch (error) {
      console.error(`Error executing instructions: ${error}`);
      throw error;
    }
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
        this.agents[index].execute()
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

  private async executeSequential(): Promise<string[]> {
    const results: string[] = [];
    let previousResult: string | undefined = undefined;

    for (let i = 0; i < this.tasks.length; i++) {
      const result = await this.agents[i].execute(previousResult);
      results.push(result);
      previousResult = result;
    }

    return results;
  }
}
