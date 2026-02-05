/**
 * DeepResearchAgent - Agent for comprehensive research tasks
 */

import { type LLMProvider, type Message } from '../llm/providers';
import { resolveBackend } from '../llm/backend-resolver';

export interface Citation {
  title: string;
  url: string;
  snippet?: string;
}

export interface ReasoningStep {
  step: number;
  thought: string;
  action?: string;
  result?: string;
}

export interface ResearchResponse {
  answer: string;
  citations: Citation[];
  reasoning: ReasoningStep[];
  confidence: number;
}

/**
 * Python parity: DeepResearchResponse with additional fields
 */
export interface DeepResearchResponse extends ResearchResponse {
  /** Query that was researched */
  query: string;
  /** Total iterations performed */
  iterations: number;
  /** Time taken in seconds */
  duration?: number;
  /** Model used */
  model?: string;
}

/**
 * Python parity: Code execution step in research
 */
export interface CodeExecutionStep {
  /** Code that was executed */
  code: string;
  /** Language of the code */
  language: string;
  /** Output from execution */
  output?: string;
  /** Error if execution failed */
  error?: string;
  /** Whether execution succeeded */
  success: boolean;
}

/**
 * Python parity: File search call during research
 */
export interface FileSearchCall {
  /** Query used for file search */
  query: string;
  /** Files that matched */
  files: string[];
  /** Snippets from matched files */
  snippets?: Array<{ file: string; content: string; line?: number }>;
}

/**
 * Python parity: MCP (Model Context Protocol) call during research
 */
export interface MCPCall {
  /** Server name */
  server: string;
  /** Tool name */
  tool: string;
  /** Arguments passed */
  arguments: Record<string, any>;
  /** Result from the call */
  result?: any;
  /** Error if call failed */
  error?: string;
}

/**
 * Python parity: Web search call during research
 */
export interface WebSearchCall {
  /** Search query */
  query: string;
  /** Search engine used */
  engine?: string;
  /** Results returned */
  results: Citation[];
  /** Number of results */
  count: number;
}

/**
 * Python parity: Provider configuration for research
 */
export interface Provider {
  /** Provider name (openai, anthropic, etc.) */
  name: string;
  /** Model to use */
  model: string;
  /** API key (optional, uses env var if not provided) */
  apiKey?: string;
  /** Base URL for API */
  baseUrl?: string;
  /** Additional options */
  options?: Record<string, any>;
}

export interface DeepResearchConfig {
  name?: string;
  llm?: string;
  maxIterations?: number;
  searchTool?: (query: string) => Promise<Citation[]>;
  verbose?: boolean;
}

/**
 * DeepResearchAgent - Comprehensive research with citations
 */
export class DeepResearchAgent {
  readonly name: string;
  private provider: LLMProvider | null = null;
  private providerPromise: Promise<LLMProvider> | null = null;
  private llmModel: string;
  private maxIterations: number;
  private searchTool?: (query: string) => Promise<Citation[]>;
  private verbose: boolean;

  constructor(config: DeepResearchConfig = {}) {
    this.name = config.name || `ResearchAgent_${Math.random().toString(36).substr(2, 9)}`;
    this.llmModel = config.llm || 'openai/gpt-4o-mini';
    this.maxIterations = config.maxIterations ?? 5;
    this.searchTool = config.searchTool;
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
   * Conduct deep research on a topic
   */
  async research(query: string): Promise<ResearchResponse> {
    const reasoning: ReasoningStep[] = [];
    const citations: Citation[] = [];
    let iteration = 0;

    // Step 1: Analyze the query
    reasoning.push({
      step: ++iteration,
      thought: `Analyzing research query: "${query}"`,
      action: 'query_analysis'
    });

    // Step 2: Generate search queries
    const searchQueries = await this.generateSearchQueries(query);
    reasoning.push({
      step: ++iteration,
      thought: `Generated ${searchQueries.length} search queries`,
      action: 'generate_queries',
      result: searchQueries.join(', ')
    });

    // Step 3: Execute searches if tool available
    if (this.searchTool) {
      for (const sq of searchQueries.slice(0, 3)) {
        try {
          const results = await this.searchTool(sq);
          citations.push(...results);
          reasoning.push({
            step: ++iteration,
            thought: `Searched for: "${sq}"`,
            action: 'web_search',
            result: `Found ${results.length} results`
          });
        } catch (error) {
          if (this.verbose) {
            console.log(`[Research] Search failed for: ${sq}`);
          }
        }
      }
    }

    // Step 4: Synthesize answer
    const answer = await this.synthesizeAnswer(query, citations);
    reasoning.push({
      step: ++iteration,
      thought: 'Synthesizing final answer from gathered information',
      action: 'synthesize',
      result: 'Answer generated'
    });

    // Calculate confidence based on citations
    const confidence = Math.min(0.5 + (citations.length * 0.1), 0.95);

    return {
      answer,
      citations,
      reasoning,
      confidence
    };
  }

  private async generateSearchQueries(query: string): Promise<string[]> {
    const provider = await this.getProvider();
    const result = await provider.generateText({
      messages: [
        {
          role: 'system',
          content: 'Generate 3 search queries to research this topic. Output only the queries, one per line.'
        },
        { role: 'user', content: query }
      ]
    });

    return result.text.split('\n').filter(q => q.trim().length > 0).slice(0, 3);
  }

  private async synthesizeAnswer(query: string, citations: Citation[]): Promise<string> {
    const context = citations.length > 0
      ? `\n\nRelevant sources:\n${citations.map(c => `- ${c.title}: ${c.snippet || ''}`).join('\n')}`
      : '';

    const provider = await this.getProvider();
    const result = await provider.generateText({
      messages: [
        {
          role: 'system',
          content: 'You are a research assistant. Provide a comprehensive, well-structured answer based on the available information. Cite sources when available.'
        },
        { role: 'user', content: `${query}${context}` }
      ]
    });

    return result.text;
  }

  /**
   * Set search tool
   */
  setSearchTool(tool: (query: string) => Promise<Citation[]>): void {
    this.searchTool = tool;
  }
}

/**
 * Create a DeepResearchAgent
 */
export function createDeepResearchAgent(config?: DeepResearchConfig): DeepResearchAgent {
  return new DeepResearchAgent(config);
}
