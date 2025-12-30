/**
 * AutoAgents - Automatic agent generation from task descriptions
 */

import { type LLMProvider, type Message } from '../llm/providers';
import { resolveBackend } from '../llm/backend-resolver';

export interface AgentConfig {
  name: string;
  role: string;
  goal: string;
  backstory?: string;
  instructions?: string;
  tools?: string[];
}

export interface TaskConfig {
  description: string;
  expectedOutput?: string;
  agent?: string;
}

export interface TeamStructure {
  agents: AgentConfig[];
  tasks: TaskConfig[];
  pattern: 'sequential' | 'parallel' | 'hierarchical';
}

export interface AutoAgentsConfig {
  llm?: string;
  pattern?: 'sequential' | 'parallel' | 'routing' | 'orchestrator-workers' | 'evaluator-optimizer';
  singleAgent?: boolean;
  verbose?: boolean;
}

/**
 * AutoAgents - Generate agent configurations from task descriptions
 */
export class AutoAgents {
  private provider: LLMProvider | null = null;
  private providerPromise: Promise<LLMProvider> | null = null;
  private llmModel: string;
  private pattern: string;
  private singleAgent: boolean;
  private verbose: boolean;

  constructor(config: AutoAgentsConfig = {}) {
    this.llmModel = config.llm || 'openai/gpt-4o-mini';
    this.pattern = config.pattern || 'sequential';
    this.singleAgent = config.singleAgent ?? false;
    this.verbose = config.verbose ?? false;
  }

  /**
   * Get the LLM provider (lazy initialization with AI SDK backend)
   */
  private async getProvider(): Promise<LLMProvider> {
    if (this.provider) {
      return this.provider;
    }

    if (!this.providerPromise) {
      this.providerPromise = (async () => {
        const result = await resolveBackend(this.llmModel, {
          attribution: { agentId: 'AutoAgents' },
        });
        this.provider = result.provider;
        return result.provider;
      })();
    }

    return this.providerPromise;
  }

  /**
   * Generate agent configuration from task description
   */
  async generate(taskDescription: string): Promise<TeamStructure> {
    const prompt = this.buildPrompt(taskDescription);
    const provider = await this.getProvider();
    const result = await provider.generateText({
      messages: [
        { role: 'system', content: this.getSystemPrompt() },
        { role: 'user', content: prompt }
      ]
    });

    return this.parseResponse(result.text);
  }

  /**
   * Recommend a pattern for the task
   */
  recommendPattern(taskDescription: string): string {
    const lower = taskDescription.toLowerCase();
    
    if (lower.includes('parallel') || lower.includes('concurrent') || lower.includes('simultaneously')) {
      return 'parallel';
    }
    if (lower.includes('route') || lower.includes('classify') || lower.includes('categorize')) {
      return 'routing';
    }
    if (lower.includes('orchestrat') || lower.includes('coordinat') || lower.includes('manage')) {
      return 'orchestrator-workers';
    }
    if (lower.includes('evaluat') || lower.includes('optimi') || lower.includes('improv')) {
      return 'evaluator-optimizer';
    }
    
    return 'sequential';
  }

  /**
   * Analyze task complexity
   */
  analyzeComplexity(taskDescription: string): 'simple' | 'moderate' | 'complex' {
    const words = taskDescription.split(/\s+/).length;
    const hasMultipleSteps = /step|then|after|before|first|second|third|finally/i.test(taskDescription);
    const hasMultipleAgents = /team|multiple|several|different|various/i.test(taskDescription);
    
    if (words < 20 && !hasMultipleSteps && !hasMultipleAgents) {
      return 'simple';
    }
    if (words > 100 || (hasMultipleSteps && hasMultipleAgents)) {
      return 'complex';
    }
    return 'moderate';
  }

  private getSystemPrompt(): string {
    return `You are an AI agent architect. Your job is to analyze task descriptions and generate optimal agent configurations.

Output a JSON object with the following structure:
{
  "agents": [
    {
      "name": "AgentName",
      "role": "Role description",
      "goal": "Agent's goal",
      "backstory": "Optional backstory",
      "instructions": "Specific instructions",
      "tools": ["tool1", "tool2"]
    }
  ],
  "tasks": [
    {
      "description": "Task description",
      "expectedOutput": "What the task should produce",
      "agent": "AgentName"
    }
  ],
  "pattern": "sequential|parallel|hierarchical"
}

Guidelines:
- For simple tasks, use 1 agent
- For moderate tasks, use 2-3 agents
- For complex tasks, use 3-5 agents
- Match the pattern to the task requirements
- Be specific about roles and goals`;
  }

  private buildPrompt(taskDescription: string): string {
    const complexity = this.analyzeComplexity(taskDescription);
    const recommendedPattern = this.recommendPattern(taskDescription);
    
    return `Task Description: ${taskDescription}

Complexity: ${complexity}
Recommended Pattern: ${this.pattern || recommendedPattern}
Single Agent Mode: ${this.singleAgent}

Generate an optimal agent configuration for this task.`;
  }

  private parseResponse(response: string): TeamStructure {
    try {
      // Extract JSON from response
      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[0]);
      }
    } catch (error) {
      // Fallback to default structure
    }

    // Default fallback
    return {
      agents: [{
        name: 'GeneralAgent',
        role: 'General purpose agent',
        goal: 'Complete the assigned task',
        instructions: 'Follow the task description carefully'
      }],
      tasks: [{
        description: 'Complete the task',
        agent: 'GeneralAgent'
      }],
      pattern: 'sequential'
    };
  }
}

/**
 * Create an AutoAgents instance
 */
export function createAutoAgents(config?: AutoAgentsConfig): AutoAgents {
  return new AutoAgents(config);
}
