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
}

export interface PraisonAIAgentsConfig {
  agents: Agent[];
  tasks: string[];
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
    this.tasks = config.tasks;
    this.verbose = config.verbose || false;
    this.pretty = config.pretty || false;
    this.process = config.process || 'sequential';

    // Configure logging
    Logger.setVerbose(config.verbose ?? process.env.PRAISON_VERBOSE !== 'false');
    Logger.setPretty(config.pretty ?? process.env.PRAISON_PRETTY === 'true');
  }

  async start(): Promise<string[]> {
    await Logger.debug('Starting PraisonAI Agents execution...');

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

      await Logger.info(`Agent ${agent.name} starting with prompt: ${task}`);

      const result = await agent.start(task, previousResult);
      results.push(result);
    }

    return results;
  }
}
