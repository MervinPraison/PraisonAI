/**
 * Subagent Tool - Use agents as tools for other agents
 * 
 * Enables the agent-as-tool pattern where one agent can invoke
 * another agent as part of its tool execution.
 * 
 * @example
 * ```typescript
 * import { Agent, SubagentTool, createSubagentTool } from 'praisonai';
 * 
 * const researcher = new Agent({
 *   name: 'Researcher',
 *   instructions: 'Research topics thoroughly'
 * });
 * 
 * const writer = new Agent({
 *   name: 'Writer',
 *   instructions: 'Write articles based on input',
 *   tools: [createSubagentTool(researcher, {
 *     name: 'research',
 *     description: 'Research a topic before writing'
 *   })]
 * });
 * ```
 */

import { randomUUID } from 'crypto';

/**
 * Configuration for subagent tool
 */
export interface SubagentToolConfig {
    /** Tool name (defaults to agent name) */
    name?: string;
    /** Tool description */
    description?: string;
    /** Prompt template for the subagent (use {{input}} for placeholder) */
    promptTemplate?: string;
    /** Transform input before sending to subagent */
    inputTransform?: (input: any) => string;
    /** Transform output from subagent */
    outputTransform?: (output: any) => any;
    /** Timeout for subagent execution in ms */
    timeout?: number;
    /** Additional context to pass to subagent */
    context?: Record<string, any>;
    /** Whether to include parent conversation history */
    includeHistory?: boolean;
}

/**
 * Schema for subagent tool parameters
 */
export interface SubagentToolSchema {
    type: 'object';
    properties: {
        input: {
            type: 'string';
            description: string;
        };
    };
    required: ['input'];
}

/**
 * SubagentTool - Wraps an agent to be used as a tool
 */
export class SubagentTool {
    readonly id: string;
    readonly name: string;
    readonly description: string;
    private agent: any;
    private config: Required<Omit<SubagentToolConfig, 'name' | 'description'>>;

    constructor(agent: any, config: SubagentToolConfig = {}) {
        this.id = randomUUID();
        this.agent = agent;
        this.name = config.name ?? agent.name ?? 'subagent';
        this.description = config.description ??
            `Invoke the ${agent.name ?? 'subagent'} for specialized tasks`;

        this.config = {
            promptTemplate: config.promptTemplate ?? '{{input}}',
            inputTransform: config.inputTransform ?? ((input) => String(input)),
            outputTransform: config.outputTransform ?? ((output) => output),
            timeout: config.timeout ?? 60000,
            context: config.context ?? {},
            includeHistory: config.includeHistory ?? false,
        };
    }

    /**
     * Get the tool schema for AI SDK
     */
    getSchema(): SubagentToolSchema {
        return {
            type: 'object',
            properties: {
                input: {
                    type: 'string',
                    description: `Input for ${this.name}`,
                },
            },
            required: ['input'],
        };
    }

    /**
     * Execute the subagent
     */
    async execute(params: { input: string }): Promise<any> {
        const { input } = params;

        // Transform input
        const transformedInput = this.config.inputTransform(input);

        // Build prompt from template
        const prompt = this.config.promptTemplate.replace(/\{\{input\}\}/g, transformedInput);

        // Execute with timeout
        const result = await this.executeWithTimeout(prompt);

        // Transform output
        return this.config.outputTransform(result);
    }

    /**
     * Execute agent with timeout
     */
    private async executeWithTimeout(prompt: string): Promise<any> {
        return Promise.race([
            this.invokeAgent(prompt),
            new Promise((_, reject) => {
                setTimeout(
                    () => reject(new Error(`Subagent ${this.name} timed out after ${this.config.timeout}ms`)),
                    this.config.timeout
                );
            }),
        ]);
    }

    /**
     * Invoke the wrapped agent
     */
    private async invokeAgent(prompt: string): Promise<any> {
        // Check if agent has chat method
        if (typeof this.agent.chat === 'function') {
            const result = await this.agent.chat(prompt);
            // Handle different response formats
            if (typeof result === 'string') return result;
            if (result?.text) return result.text;
            if (result?.content) return result.content;
            return result;
        }

        // Check if agent has run method
        if (typeof this.agent.run === 'function') {
            return this.agent.run(prompt);
        }

        // Check if agent is a function
        if (typeof this.agent === 'function') {
            return this.agent(prompt);
        }

        throw new Error(`Subagent ${this.name} does not have a chat, run, or callable interface`);
    }

    /**
     * Convert to AI SDK tool format
     */
    toAISDKTool(): any {
        return {
            type: 'function',
            function: {
                name: this.name,
                description: this.description,
                parameters: this.getSchema(),
            },
            execute: this.execute.bind(this),
        };
    }

    /**
     * Convert to callable function tool format
     */
    toFunctionTool(): (...args: any[]) => Promise<any> {
        const fn = async (input: string) => {
            return this.execute({ input });
        };

        // Attach metadata
        Object.defineProperty(fn, 'name', { value: this.name });
        Object.defineProperty(fn, 'description', { value: this.description });
        Object.defineProperty(fn, 'parameters', { value: this.getSchema() });

        return fn;
    }
}

/**
 * Create a subagent tool from an agent
 * 
 * @example
 * ```typescript
 * const researchTool = createSubagentTool(researchAgent, {
 *   name: 'deep_research',
 *   description: 'Perform deep research on a topic'
 * });
 * 
 * const writer = new Agent({
 *   tools: [researchTool]
 * });
 * ```
 */
export function createSubagentTool(agent: any, config?: SubagentToolConfig): SubagentTool {
    return new SubagentTool(agent, config);
}

/**
 * Create multiple subagent tools from a list of agents
 */
export function createSubagentTools(agents: any[], configs?: SubagentToolConfig[]): SubagentTool[] {
    return agents.map((agent, i) => new SubagentTool(agent, configs?.[i]));
}

/**
 * Agent delegation helper - create a delegator agent that routes to subagents
 */
export interface DelegatorConfig {
    /** Name of the delegator agent */
    name?: string;
    /** Instructions for the delegator */
    instructions?: string;
    /** Subagents to delegate to */
    subagents: any[];
    /** LLM to use for routing decisions */
    llm?: string;
}

export function createDelegator(config: DelegatorConfig): any {
    const tools = config.subagents.map(agent =>
        createSubagentTool(agent).toFunctionTool()
    );

    return {
        name: config.name ?? 'Delegator',
        instructions: config.instructions ??
            'You are a task delegator. Analyze the request and delegate to the most appropriate subagent.',
        tools,
        delegate: async (task: string) => {
            // This would be implemented by the Agent class using the tools
            throw new Error('Delegator must be used with an Agent class');
        },
    };
}

// Default export
export default SubagentTool;
