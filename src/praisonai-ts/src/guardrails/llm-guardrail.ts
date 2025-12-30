/**
 * LLMGuardrail - LLM-based content validation
 */

import { type LLMProvider } from '../llm/providers';
import { resolveBackend } from '../llm/backend-resolver';

export interface LLMGuardrailConfig {
  name: string;
  criteria: string;
  llm?: string;
  threshold?: number;
  verbose?: boolean;
}

export interface LLMGuardrailResult {
  status: 'passed' | 'failed' | 'warning';
  score: number;
  message?: string;
  reasoning?: string;
}

/**
 * LLMGuardrail - Use LLM to validate content against criteria
 */
export class LLMGuardrail {
  readonly name: string;
  readonly criteria: string;
  private provider: LLMProvider | null = null;
  private providerPromise: Promise<LLMProvider> | null = null;
  private llmModel: string;
  private threshold: number;
  private verbose: boolean;

  constructor(config: LLMGuardrailConfig) {
    this.name = config.name;
    this.criteria = config.criteria;
    this.llmModel = config.llm || 'openai/gpt-4o-mini';
    this.threshold = config.threshold ?? 0.7;
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
          attribution: { agentId: `LLMGuardrail:${this.name}` },
        });
        this.provider = result.provider;
        return result.provider;
      })();
    }

    return this.providerPromise;
  }

  /**
   * Check content against criteria
   */
  async check(content: string): Promise<LLMGuardrailResult> {
    const prompt = `Evaluate the following content against this criteria:

Criteria: ${this.criteria}

Content: ${content}

Respond with a JSON object containing:
- score: number from 0 to 1 (1 = fully meets criteria)
- passed: boolean
- reasoning: brief explanation

JSON response:`;

    try {
      const provider = await this.getProvider();
      const result = await provider.generateText({
        messages: [{ role: 'user', content: prompt }]
      });

      const parsed = this.parseResponse(result.text);
      
      if (this.verbose) {
        console.log(`[LLMGuardrail:${this.name}] Score: ${parsed.score}, Passed: ${parsed.status}`);
      }

      return parsed;
    } catch (error: any) {
      return {
        status: 'warning',
        score: 0.5,
        message: `Guardrail check failed: ${error.message}`
      };
    }
  }

  /**
   * Run guardrail (alias for check)
   */
  async run(content: string): Promise<LLMGuardrailResult> {
    return this.check(content);
  }

  private parseResponse(response: string): LLMGuardrailResult {
    try {
      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0]);
        const score = typeof parsed.score === 'number' ? parsed.score : 0.5;
        return {
          status: score >= this.threshold ? 'passed' : 'failed',
          score,
          reasoning: parsed.reasoning
        };
      }
    } catch (e) {
      // Parse failed
    }

    // Fallback parsing
    const hasPositive = /pass|good|valid|accept|meets/i.test(response);
    return {
      status: hasPositive ? 'passed' : 'failed',
      score: hasPositive ? 0.8 : 0.3,
      reasoning: response.substring(0, 200)
    };
  }
}

/**
 * Create an LLMGuardrail
 */
export function createLLMGuardrail(config: LLMGuardrailConfig): LLMGuardrail {
  return new LLMGuardrail(config);
}
