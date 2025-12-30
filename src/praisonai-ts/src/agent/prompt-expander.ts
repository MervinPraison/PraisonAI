/**
 * PromptExpanderAgent - Expand and enhance prompts
 */

import { type LLMProvider } from '../llm/providers';
import { resolveBackend } from '../llm/backend-resolver';

export type ExpandStrategy = 'detail' | 'context' | 'examples' | 'constraints' | 'auto';

export interface ExpandResult {
  original: string;
  expanded: string;
  strategy: ExpandStrategy;
  additions: string[];
}

export interface PromptExpanderConfig {
  name?: string;
  llm?: string;
  defaultStrategy?: ExpandStrategy;
  verbose?: boolean;
}

/**
 * PromptExpanderAgent - Expand prompts with more detail and context
 */
export class PromptExpanderAgent {
  readonly name: string;
  private provider: LLMProvider | null = null;
  private providerPromise: Promise<LLMProvider> | null = null;
  private llmModel: string;
  private defaultStrategy: ExpandStrategy;
  private verbose: boolean;

  constructor(config: PromptExpanderConfig = {}) {
    this.name = config.name || `PromptExpander_${Math.random().toString(36).substr(2, 9)}`;
    this.llmModel = config.llm || 'openai/gpt-4o-mini';
    this.defaultStrategy = config.defaultStrategy || 'auto';
    this.verbose = config.verbose ?? false;
  }

  private async getProvider(): Promise<LLMProvider> {
    if (this.provider) return this.provider;
    if (!this.providerPromise) {
      this.providerPromise = (async () => {
        const result = await resolveBackend(this.llmModel, { attribution: { agentId: this.name } });
        this.provider = result.provider;
        return result.provider;
      })();
    }
    return this.providerPromise;
  }

  /**
   * Expand a prompt
   */
  async expand(prompt: string, strategy?: ExpandStrategy): Promise<ExpandResult> {
    const useStrategy = strategy || this.defaultStrategy;
    const actualStrategy = useStrategy === 'auto' ? this.detectStrategy(prompt) : useStrategy;

    const systemPrompt = this.getSystemPrompt(actualStrategy);
    
    const provider = await this.getProvider();
    const result = await provider.generateText({
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: `Expand this prompt: ${prompt}` }
      ]
    });

    const expanded = result.text;
    const additions = this.extractAdditions(prompt, expanded);

    if (this.verbose) {
      console.log(`[PromptExpander] Strategy: ${actualStrategy}, Added ${additions.length} elements`);
    }

    return {
      original: prompt,
      expanded,
      strategy: actualStrategy,
      additions
    };
  }

  /**
   * Detect the best expansion strategy
   */
  detectStrategy(prompt: string): ExpandStrategy {
    const words = prompt.split(/\s+/).length;
    const lower = prompt.toLowerCase();
    
    if (words < 5) return 'detail';
    if (lower.includes('why') || lower.includes('explain') || lower.includes('context')) return 'context';
    if (lower.includes('example') || lower.includes('show') || lower.includes('demonstrate')) return 'examples';
    if (lower.includes('must') || lower.includes('should') || lower.includes('require')) return 'constraints';
    
    return 'detail';
  }

  private getSystemPrompt(strategy: ExpandStrategy): string {
    const prompts: Record<ExpandStrategy, string> = {
      detail: 'Expand this prompt by adding specific details, requirements, and clarifications. Make it more precise and actionable.',
      context: 'Expand this prompt by adding relevant background context, explaining the purpose, and providing necessary information.',
      examples: 'Expand this prompt by adding concrete examples, sample inputs/outputs, and demonstrations of expected behavior.',
      constraints: 'Expand this prompt by adding explicit constraints, requirements, limitations, and success criteria.',
      auto: 'Expand this prompt to make it clearer, more specific, and more actionable. Add relevant details and context.'
    };
    return prompts[strategy];
  }

  private extractAdditions(original: string, expanded: string): string[] {
    const originalWords = new Set(original.toLowerCase().split(/\s+/));
    const expandedWords = expanded.toLowerCase().split(/\s+/);
    
    const newWords = expandedWords.filter(w => !originalWords.has(w) && w.length > 3);
    const uniqueNew = [...new Set(newWords)];
    
    return uniqueNew.slice(0, 10);
  }
}

/**
 * Create a PromptExpanderAgent
 */
export function createPromptExpanderAgent(config?: PromptExpanderConfig): PromptExpanderAgent {
  return new PromptExpanderAgent(config);
}
