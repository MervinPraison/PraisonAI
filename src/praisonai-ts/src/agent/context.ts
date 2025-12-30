/**
 * Context Agent - Agent with enhanced context management
 */

import { type LLMProvider, type Message } from '../llm/providers';
import { resolveBackend } from '../llm/backend-resolver';
import { Session } from '../session';
import { KnowledgeBase, type SearchResult } from '../knowledge/rag';

export interface ContextAgentConfig {
  name?: string;
  instructions: string;
  llm?: string;
  knowledgeBase?: KnowledgeBase;
  contextWindow?: number;
  maxContextTokens?: number;
  verbose?: boolean;
}

export interface ContextMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
  timestamp: number;
  metadata?: Record<string, any>;
}

/**
 * Context Agent - Agent with RAG and context management
 */
export class ContextAgent {
  readonly name: string;
  readonly instructions: string;
  
  private provider: LLMProvider | null = null;
  private providerPromise: Promise<LLMProvider> | null = null;
  private llmModel: string;
  private knowledgeBase?: KnowledgeBase;
  private contextWindow: number;
  private maxContextTokens: number;
  private messages: ContextMessage[] = [];
  private verbose: boolean;

  constructor(config: ContextAgentConfig) {
    this.name = config.name || `ContextAgent_${Math.random().toString(36).substr(2, 9)}`;
    this.instructions = config.instructions;
    this.llmModel = config.llm || 'openai/gpt-4o-mini';
    this.knowledgeBase = config.knowledgeBase;
    this.contextWindow = config.contextWindow ?? 10;
    this.maxContextTokens = config.maxContextTokens ?? 4000;
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
          attribution: { agentId: this.name },
        });
        this.provider = result.provider;
        return result.provider;
      })();
    }

    return this.providerPromise;
  }

  /**
   * Chat with context awareness
   */
  async chat(prompt: string): Promise<{ text: string; context?: SearchResult[] }> {
    // Add user message
    this.messages.push({
      role: 'user',
      content: prompt,
      timestamp: Date.now()
    });

    // Build context from knowledge base
    let ragContext: SearchResult[] = [];
    let contextString = '';
    
    if (this.knowledgeBase) {
      ragContext = await this.knowledgeBase.search(prompt);
      if (ragContext.length > 0) {
        contextString = this.knowledgeBase.buildContext(ragContext);
        if (this.verbose) {
          console.log(`[ContextAgent] Found ${ragContext.length} relevant documents`);
        }
      }
    }

    // Build messages array with context
    const systemPrompt = contextString
      ? `${this.instructions}\n\nRelevant context:\n${contextString}`
      : this.instructions;

    const messages: Message[] = [
      { role: 'system', content: systemPrompt },
      ...this.getRecentMessages()
    ];

    // Generate response
    const provider = await this.getProvider();
    const result = await provider.generateText({ messages });

    // Add assistant message
    this.messages.push({
      role: 'assistant',
      content: result.text,
      timestamp: Date.now()
    });

    return {
      text: result.text,
      context: ragContext.length > 0 ? ragContext : undefined
    };
  }

  /**
   * Get recent messages within context window
   */
  private getRecentMessages(): Message[] {
    const recent = this.messages.slice(-this.contextWindow);
    return recent.map(m => ({
      role: m.role,
      content: m.content
    }));
  }

  /**
   * Add document to knowledge base
   */
  async addDocument(id: string, content: string, metadata?: Record<string, any>): Promise<void> {
    if (!this.knowledgeBase) {
      throw new Error('No knowledge base configured');
    }
    await this.knowledgeBase.add({ id, content, metadata });
  }

  /**
   * Search knowledge base
   */
  async searchKnowledge(query: string, limit?: number): Promise<SearchResult[]> {
    if (!this.knowledgeBase) {
      return [];
    }
    return this.knowledgeBase.search(query, limit);
  }

  /**
   * Clear conversation history
   */
  clearHistory(): void {
    this.messages = [];
  }

  /**
   * Get conversation history
   */
  getHistory(): ContextMessage[] {
    return [...this.messages];
  }

  /**
   * Set knowledge base
   */
  setKnowledgeBase(kb: KnowledgeBase): void {
    this.knowledgeBase = kb;
  }
}

/**
 * Create a context agent
 */
export function createContextAgent(config: ContextAgentConfig): ContextAgent {
  return new ContextAgent(config);
}
