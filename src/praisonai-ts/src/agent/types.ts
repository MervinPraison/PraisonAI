import { OpenAIService } from '../llm/openai';
import { Logger } from '../utils/logger';

export interface TaskConfig {
    name: string;
    description: string;
    expected_output: string;
    agent?: any;  // Using any to avoid circular dependency
    dependencies?: Task[];
}

export class Task {
    name: string;
    description: string;
    expected_output: string;
    agent: any;  // Using any to avoid circular dependency
    dependencies: Task[];
    result: any;

    constructor(config: TaskConfig) {
        this.name = config.name;
        this.description = config.description;
        this.expected_output = config.expected_output;
        this.agent = config.agent || null;
        this.dependencies = config.dependencies || [];
        this.result = null;
        Logger.debug(`Task created: ${this.name}`, { config });
    }
}

export interface TaskAgentConfig {
    name: string;
    role: string;
    goal: string;
    backstory: string;
    verbose?: boolean;
    llm?: string;
    markdown?: boolean;
}

export class Agent {
    private name: string;
    private role: string;
    private goal: string;
    private backstory: string;
    private verbose: boolean;
    private llm: OpenAIService;
    private markdown: boolean;
    private result: string;

    constructor(config: TaskAgentConfig) {
        this.name = config.name;
        this.role = config.role;
        this.goal = config.goal;
        this.backstory = config.backstory;
        this.verbose = config.verbose || false;
        this.llm = new OpenAIService(config.llm || 'gpt-4o-mini');
        this.markdown = config.markdown || true;
        this.result = '';
        Logger.debug(`Agent created: ${this.name}`, { config });
    }

    async execute(task: Task, dependencyResults?: any[]): Promise<any> {
        Logger.debug(`Agent ${this.name} executing task: ${task.name}`, {
            task,
            dependencyResults
        });

        const systemPrompt = `You are ${this.name}, a ${this.role}.
Your goal is to ${this.goal}.
Background: ${this.backstory}

You must complete the following task:
Name: ${task.name}
Description: ${task.description}
Expected Output: ${task.expected_output}

Respond ONLY with the expected output. Do not include any additional text, explanations, or pleasantries.`;

        let prompt = '';
        if (dependencyResults && dependencyResults.length > 0) {
            prompt = `Here are the results from previous tasks that you should use as input:
${dependencyResults.map((result, index) => `Task ${index + 1} Result:\n${result}`).join('\n\n')}

Based on these results, please complete your task.`;
            Logger.debug('Using dependency results for prompt', { dependencyResults });
        } else {
            prompt = 'Please complete your task.';
        }

        Logger.debug('Preparing LLM request', {
            systemPrompt,
            prompt
        });

        if (this.verbose) {
            Logger.info(`\nExecuting task for ${this.name}...`);
            Logger.info(`Task: ${task.name}`);
            Logger.info('Generating response (streaming)...\n');
        }

        // Reset result
        this.result = '';
            
        // Stream the response and collect it
        await this.llm.streamText(
            prompt,
            systemPrompt,
            0.7,
            (token) => {
                if (this.verbose) {
                    process.stdout.write(token);
                }
                this.result += token;
            }
        );

        if (this.verbose) {
            console.log('\n'); // Add newline after streaming
        }

        Logger.debug(`Agent ${this.name} completed task: ${task.name}`, {
            result: this.result
        });

        return this.result;
    }
}

export interface TaskPraisonAIAgentsConfig {
    agents: Agent[];
    tasks: Task[];
    verbose?: boolean;
    process?: 'sequential' | 'parallel' | 'hierarchical';
    manager_llm?: string;
}

export class PraisonAIAgents {
    private agents: Agent[];
    private tasks: Task[];
    private verbose: boolean;
    private process: 'sequential' | 'parallel' | 'hierarchical';
    private manager_llm: string;

    constructor(config: TaskPraisonAIAgentsConfig) {
        this.agents = config.agents;
        this.tasks = config.tasks;
        this.verbose = config.verbose || false;
        this.process = config.process || 'sequential';
        this.manager_llm = config.manager_llm || 'gpt-4o-mini';
        Logger.debug('PraisonAIAgents initialized', { config });
    }

    async start(): Promise<any[]> {
        Logger.debug('Starting PraisonAI Agents execution...');
        Logger.debug('Starting with process mode:', this.process);

        let results: any[];

        switch (this.process) {
            case 'parallel':
                Logger.debug('Executing tasks in parallel');
                results = await Promise.all(this.tasks.map(task => {
                    if (!task.agent) throw new Error(`No agent assigned to task: ${task.name}`);
                    return task.agent.execute(task);
                }));
                break;
            case 'hierarchical':
                Logger.debug('Executing tasks hierarchically');
                results = await this.executeHierarchical();
                break;
            default:
                Logger.debug('Executing tasks sequentially');
                results = await this.executeSequential();
        }

        if (this.verbose) {
            Logger.info('\nPraisonAI Agents execution completed.');
            results.forEach((result, index) => {
                Logger.info(`\nFinal Result from Task ${index + 1}:`);
                console.log(result);
            });
        }

        Logger.debug('Execution completed', { results });
        return results;
    }

    private async executeSequential(): Promise<any[]> {
        Logger.debug('Starting sequential execution');
        const results: any[] = [];
        for (const task of this.tasks) {
            if (!task.agent) throw new Error(`No agent assigned to task: ${task.name}`);
            Logger.debug(`Executing task: ${task.name}`);
            const result = await task.agent.execute(task);
            results.push(result);
            task.result = result;
            Logger.debug(`Completed task: ${task.name}`, { result });
        }
        return results;
    }

    private async executeHierarchical(): Promise<any[]> {
        const startTime = process.env.LOGLEVEL === 'debug' ? Date.now() : 0;
        Logger.debug('Starting hierarchical execution');
        const results: any[] = [];
        for (const task of this.tasks) {
            const taskStartTime = process.env.LOGLEVEL === 'debug' ? Date.now() : 0;
            if (!task.agent) throw new Error(`No agent assigned to task: ${task.name}`);
            Logger.debug(`Executing task: ${task.name}`, {
                dependencies: task.dependencies.map(d => d.name)
            });
            const depResults = task.dependencies.map(dep => dep.result);
            Logger.debug(`Dependency results for task ${task.name}`, { depResults });
            const result = await task.agent.execute(task, depResults);
            results.push(result);
            task.result = result;
            if (process.env.LOGLEVEL === 'debug') {
                Logger.debug(`Task execution time for ${task.name}: ${Date.now() - taskStartTime}ms`);
            }
            Logger.debug(`Completed task: ${task.name}`, { result });
        }
        if (process.env.LOGLEVEL === 'debug') {
            Logger.debug(`Total hierarchical execution time: ${Date.now() - startTime}ms`);
        }
        return results;
    }
}

// Export these for type checking
export type { TaskAgentConfig as AgentConfig };
