/**
 * Cost Tracker - Track token usage and costs across LLM requests
 */

export interface ModelPricing {
  inputCostPer1k: number;
  outputCostPer1k: number;
}

export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
}

export interface RequestStats {
  timestamp: number;
  model: string;
  usage: TokenUsage;
  cost: number;
  latencyMs?: number;
}

export interface SessionStats {
  totalInputTokens: number;
  totalOutputTokens: number;
  totalTokens: number;
  totalCost: number;
  requestCount: number;
  avgLatencyMs: number;
  startTime: number;
  requests: RequestStats[];
}

/**
 * Model pricing data (USD per 1K tokens)
 */
export const MODEL_PRICING: Record<string, ModelPricing> = {
  // OpenAI
  'gpt-4o': { inputCostPer1k: 0.005, outputCostPer1k: 0.015 },
  'gpt-4o-mini': { inputCostPer1k: 0.00015, outputCostPer1k: 0.0006 },
  'gpt-4-turbo': { inputCostPer1k: 0.01, outputCostPer1k: 0.03 },
  'gpt-4': { inputCostPer1k: 0.03, outputCostPer1k: 0.06 },
  'gpt-3.5-turbo': { inputCostPer1k: 0.0005, outputCostPer1k: 0.0015 },
  'o1': { inputCostPer1k: 0.015, outputCostPer1k: 0.06 },
  'o1-mini': { inputCostPer1k: 0.003, outputCostPer1k: 0.012 },
  'o1-preview': { inputCostPer1k: 0.015, outputCostPer1k: 0.06 },
  
  // Anthropic
  'claude-3-5-sonnet-20241022': { inputCostPer1k: 0.003, outputCostPer1k: 0.015 },
  'claude-3-5-haiku-20241022': { inputCostPer1k: 0.001, outputCostPer1k: 0.005 },
  'claude-3-opus-20240229': { inputCostPer1k: 0.015, outputCostPer1k: 0.075 },
  'claude-3-sonnet-20240229': { inputCostPer1k: 0.003, outputCostPer1k: 0.015 },
  'claude-3-haiku-20240307': { inputCostPer1k: 0.00025, outputCostPer1k: 0.00125 },
  
  // Google
  'gemini-2.0-flash': { inputCostPer1k: 0.0001, outputCostPer1k: 0.0004 },
  'gemini-1.5-pro': { inputCostPer1k: 0.00125, outputCostPer1k: 0.005 },
  'gemini-1.5-flash': { inputCostPer1k: 0.000075, outputCostPer1k: 0.0003 },
  
  // Default fallback
  'default': { inputCostPer1k: 0.001, outputCostPer1k: 0.002 }
};

/**
 * Cost Tracker class
 */
export class CostTracker {
  private stats: SessionStats;
  private customPricing: Map<string, ModelPricing> = new Map();

  constructor() {
    this.stats = this.createEmptyStats();
  }

  private createEmptyStats(): SessionStats {
    return {
      totalInputTokens: 0,
      totalOutputTokens: 0,
      totalTokens: 0,
      totalCost: 0,
      requestCount: 0,
      avgLatencyMs: 0,
      startTime: Date.now(),
      requests: []
    };
  }

  /**
   * Add a request's token usage
   */
  addUsage(
    model: string,
    inputTokens: number,
    outputTokens: number,
    latencyMs?: number
  ): RequestStats {
    const totalTokens = inputTokens + outputTokens;
    const cost = this.calculateCost(model, inputTokens, outputTokens);

    const request: RequestStats = {
      timestamp: Date.now(),
      model,
      usage: { inputTokens, outputTokens, totalTokens },
      cost,
      latencyMs
    };

    this.stats.requests.push(request);
    this.stats.totalInputTokens += inputTokens;
    this.stats.totalOutputTokens += outputTokens;
    this.stats.totalTokens += totalTokens;
    this.stats.totalCost += cost;
    this.stats.requestCount++;

    if (latencyMs !== undefined) {
      const totalLatency = this.stats.avgLatencyMs * (this.stats.requestCount - 1) + latencyMs;
      this.stats.avgLatencyMs = totalLatency / this.stats.requestCount;
    }

    return request;
  }

  /**
   * Calculate cost for token usage
   */
  calculateCost(model: string, inputTokens: number, outputTokens: number): number {
    const pricing = this.getPricing(model);
    const inputCost = (inputTokens / 1000) * pricing.inputCostPer1k;
    const outputCost = (outputTokens / 1000) * pricing.outputCostPer1k;
    return inputCost + outputCost;
  }

  /**
   * Get pricing for a model
   */
  getPricing(model: string): ModelPricing {
    // Check custom pricing first
    if (this.customPricing.has(model)) {
      return this.customPricing.get(model)!;
    }

    // Check built-in pricing
    if (MODEL_PRICING[model]) {
      return MODEL_PRICING[model];
    }

    // Try to match partial model names
    for (const [key, pricing] of Object.entries(MODEL_PRICING)) {
      if (model.includes(key) || key.includes(model)) {
        return pricing;
      }
    }

    return MODEL_PRICING['default'];
  }

  /**
   * Set custom pricing for a model
   */
  setCustomPricing(model: string, pricing: ModelPricing): void {
    this.customPricing.set(model, pricing);
  }

  /**
   * Get current session stats
   */
  getStats(): SessionStats {
    return { ...this.stats };
  }

  /**
   * Get summary string
   */
  getSummary(): string {
    const duration = (Date.now() - this.stats.startTime) / 1000;
    const lines = [
      '=== Cost Summary ===',
      `Requests: ${this.stats.requestCount}`,
      `Duration: ${duration.toFixed(1)}s`,
      '',
      'Tokens:',
      `  Input:  ${this.stats.totalInputTokens.toLocaleString()}`,
      `  Output: ${this.stats.totalOutputTokens.toLocaleString()}`,
      `  Total:  ${this.stats.totalTokens.toLocaleString()}`,
      '',
      `Total Cost: $${this.stats.totalCost.toFixed(6)}`,
    ];

    if (this.stats.avgLatencyMs > 0) {
      lines.push(`Avg Latency: ${this.stats.avgLatencyMs.toFixed(0)}ms`);
    }

    return lines.join('\n');
  }

  /**
   * Get detailed breakdown by model
   */
  getBreakdownByModel(): Record<string, { tokens: number; cost: number; requests: number }> {
    const breakdown: Record<string, { tokens: number; cost: number; requests: number }> = {};

    for (const request of this.stats.requests) {
      if (!breakdown[request.model]) {
        breakdown[request.model] = { tokens: 0, cost: 0, requests: 0 };
      }
      breakdown[request.model].tokens += request.usage.totalTokens;
      breakdown[request.model].cost += request.cost;
      breakdown[request.model].requests++;
    }

    return breakdown;
  }

  /**
   * Reset stats
   */
  reset(): void {
    this.stats = this.createEmptyStats();
  }

  /**
   * Export stats to JSON
   */
  toJSON(): SessionStats {
    return this.getStats();
  }

  /**
   * Import stats from JSON
   */
  fromJSON(data: SessionStats): void {
    this.stats = { ...data };
  }

  // Legacy interface compatibility
  get totalTokens(): number {
    return this.stats.totalTokens;
  }

  get totalCost(): number {
    return this.stats.totalCost;
  }

  get requests(): number {
    return this.stats.requestCount;
  }
}

/**
 * Create a cost tracker instance
 */
export function createCostTracker(): CostTracker {
  return new CostTracker();
}

/**
 * Estimate tokens from text (rough approximation)
 */
export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

/**
 * Format cost as currency string
 */
export function formatCost(cost: number): string {
  if (cost < 0.01) {
    return `$${cost.toFixed(6)}`;
  }
  if (cost < 1) {
    return `$${cost.toFixed(4)}`;
  }
  return `$${cost.toFixed(2)}`;
}
