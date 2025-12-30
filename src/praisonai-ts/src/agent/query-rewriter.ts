/**
 * QueryRewriterAgent - Rewrite and optimize queries
 */

import { type LLMProvider } from '../llm/providers';
import { resolveBackend } from '../llm/backend-resolver';

export type RewriteStrategy = 'expand' | 'simplify' | 'decompose' | 'rephrase' | 'auto';

export interface RewriteResult {
  original: string;
  rewritten: string[];
  strategy: RewriteStrategy;
  confidence: number;
}

export interface QueryRewriterConfig {
  name?: string;
  llm?: string;
  defaultStrategy?: RewriteStrategy;
  verbose?: boolean;
}

/**
 * QueryRewriterAgent - Optimize and rewrite queries
 */
export class QueryRewriterAgent {
  readonly name: string;
  private provider: LLMProvider | null = null;
  private providerPromise: Promise<LLMProvider> | null = null;
  private llmModel: string;
  private defaultStrategy: RewriteStrategy;
  private verbose: boolean;

  constructor(config: QueryRewriterConfig = {}) {
    this.name = config.name || `QueryRewriter_${Math.random().toString(36).substr(2, 9)}`;
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
   * Rewrite a query
   */
  async rewrite(query: string, strategy?: RewriteStrategy): Promise<RewriteResult> {
    const useStrategy = strategy || this.defaultStrategy;
    const actualStrategy = useStrategy === 'auto' ? this.detectStrategy(query) : useStrategy;

    const prompt = this.buildPrompt(query, actualStrategy);
    
    const provider = await this.getProvider();
    const result = await provider.generateText({
      messages: [
        { role: 'system', content: this.getSystemPrompt(actualStrategy) },
        { role: 'user', content: prompt }
      ]
    });

    const rewritten = this.parseRewrittenQueries(result.text);

    if (this.verbose) {
      console.log(`[QueryRewriter] Strategy: ${actualStrategy}, Rewrites: ${rewritten.length}`);
    }

    return {
      original: query,
      rewritten,
      strategy: actualStrategy,
      confidence: rewritten.length > 0 ? 0.85 : 0.5
    };
  }

  private detectStrategy(query: string): RewriteStrategy {
    const words = query.split(/\s+/).length;
    
    if (words < 3) return 'expand';
    if (words > 20) return 'simplify';
    if (query.includes(' and ') || query.includes(' or ')) return 'decompose';
    return 'rephrase';
  }

  private getSystemPrompt(strategy: RewriteStrategy): string {
    const prompts: Record<RewriteStrategy, string> = {
      expand: 'Expand this query with more context and detail. Generate 3 expanded versions.',
      simplify: 'Simplify this query to its core intent. Generate 3 simpler versions.',
      decompose: 'Break this query into smaller, focused sub-queries. Generate 3-5 sub-queries.',
      rephrase: 'Rephrase this query in different ways while keeping the same meaning. Generate 3 versions.',
      auto: 'Optimize this query for better search results. Generate 3 improved versions.'
    };
    return prompts[strategy] + ' Output one query per line.';
  }

  private buildPrompt(query: string, strategy: RewriteStrategy): string {
    return `Query: ${query}\n\nRewrite using ${strategy} strategy:`;
  }

  private parseRewrittenQueries(response: string): string[] {
    return response
      .split('\n')
      .map(line => line.replace(/^\d+[\.\)]\s*/, '').trim())
      .filter(line => line.length > 0 && line.length < 500);
  }
}

/**
 * Create a QueryRewriterAgent
 */
export function createQueryRewriterAgent(config?: QueryRewriterConfig): QueryRewriterAgent {
  return new QueryRewriterAgent(config);
}
