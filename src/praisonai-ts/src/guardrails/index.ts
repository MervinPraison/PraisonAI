/**
 * Guardrails - Input/output validation and safety checks
 * 
 * Python parity with praisonaiagents/guardrails module
 */

export type GuardrailStatus = 'passed' | 'failed' | 'warning';

export interface GuardrailResult {
  status: GuardrailStatus;
  message?: string;
  details?: Record<string, any>;
  modifiedContent?: string;
}

// ============================================================================
// GuardrailValidationResult (Python parity)
// ============================================================================

/**
 * Result of a guardrail validation.
 * 
 * Python parity: praisonaiagents/guardrails/guardrail_result.py:13-43
 * 
 * This is the Pydantic-style result that matches the Python SDK.
 */
export interface GuardrailValidationResult {
  /** Whether the guardrail check passed */
  success: boolean;
  /** The result if modified, or null if unchanged */
  result: string | null;
  /** Error message if validation failed */
  error: string;
}

/**
 * Create a GuardrailValidationResult with defaults.
 */
export function createGuardrailValidationResult(
  config: Partial<GuardrailValidationResult> = {}
): GuardrailValidationResult {
  return {
    success: config.success ?? false,
    result: config.result ?? null,
    error: config.error ?? '',
  };
}

/**
 * Create a GuardrailValidationResult from a tuple.
 * 
 * Python parity: praisonaiagents/guardrails/guardrail_result.py:20-43
 */
export function guardrailResultFromTuple(
  tuple: [boolean, string | null]
): GuardrailValidationResult {
  const [success, data] = tuple;
  
  if (success) {
    return {
      success: true,
      result: data,
      error: '',
    };
  } else {
    return {
      success: false,
      result: null,
      error: data ?? 'Guardrail validation failed',
    };
  }
}

export type GuardrailFunction = (
  content: string,
  context?: GuardrailContext
) => Promise<GuardrailResult> | GuardrailResult;

export interface GuardrailContext {
  role: 'input' | 'output';
  agentName?: string;
  sessionId?: string;
  metadata?: Record<string, any>;
}

export interface GuardrailConfig {
  name: string;
  description?: string;
  check: GuardrailFunction;
  onFail?: 'block' | 'warn' | 'modify';
}

/**
 * Guardrail class
 */
export class Guardrail {
  readonly name: string;
  readonly description: string;
  readonly check: GuardrailFunction;
  readonly onFail: 'block' | 'warn' | 'modify';

  constructor(config: GuardrailConfig) {
    this.name = config.name;
    this.description = config.description || `Guardrail: ${config.name}`;
    this.check = config.check;
    this.onFail = config.onFail || 'block';
  }

  async run(content: string, context?: GuardrailContext): Promise<GuardrailResult> {
    try {
      return await this.check(content, context);
    } catch (error: any) {
      return {
        status: 'failed',
        message: `Guardrail error: ${error.message}`,
        details: { error: error.message },
      };
    }
  }
}

/**
 * Create a guardrail
 */
export function guardrail(config: GuardrailConfig): Guardrail {
  return new Guardrail(config);
}

/**
 * Guardrail Manager - Run multiple guardrails
 */
export class GuardrailManager {
  private guardrails: Guardrail[] = [];

  add(g: Guardrail): this {
    this.guardrails.push(g);
    return this;
  }

  async runAll(
    content: string,
    context?: GuardrailContext
  ): Promise<{ passed: boolean; results: Array<{ name: string; result: GuardrailResult }> }> {
    const results: Array<{ name: string; result: GuardrailResult }> = [];
    let passed = true;

    for (const g of this.guardrails) {
      const result = await g.run(content, context);
      results.push({ name: g.name, result });

      if (result.status === 'failed') {
        passed = false;
        if (g.onFail === 'block') {
          break;
        }
      }
    }

    return { passed, results };
  }

  get count(): number {
    return this.guardrails.length;
  }
}

/**
 * Built-in guardrails
 */
export const builtinGuardrails = {
  /**
   * Check for maximum length
   */
  maxLength: (maxChars: number): Guardrail => {
    return guardrail({
      name: 'max_length',
      description: `Ensure content is under ${maxChars} characters`,
      check: (content) => {
        if (content.length > maxChars) {
          return {
            status: 'failed',
            message: `Content exceeds maximum length of ${maxChars} characters`,
            details: { length: content.length, max: maxChars },
          };
        }
        return { status: 'passed' };
      },
    });
  },

  /**
   * Check for minimum length
   */
  minLength: (minChars: number): Guardrail => {
    return guardrail({
      name: 'min_length',
      description: `Ensure content is at least ${minChars} characters`,
      check: (content) => {
        if (content.length < minChars) {
          return {
            status: 'failed',
            message: `Content is below minimum length of ${minChars} characters`,
            details: { length: content.length, min: minChars },
          };
        }
        return { status: 'passed' };
      },
    });
  },

  /**
   * Check for blocked words
   */
  blockedWords: (words: string[]): Guardrail => {
    return guardrail({
      name: 'blocked_words',
      description: 'Check for blocked words',
      check: (content) => {
        const lowerContent = content.toLowerCase();
        const found = words.filter(w => lowerContent.includes(w.toLowerCase()));
        if (found.length > 0) {
          return {
            status: 'failed',
            message: `Content contains blocked words`,
            details: { blockedWords: found },
          };
        }
        return { status: 'passed' };
      },
    });
  },

  /**
   * Check for required words
   */
  requiredWords: (words: string[]): Guardrail => {
    return guardrail({
      name: 'required_words',
      description: 'Check for required words',
      check: (content) => {
        const lowerContent = content.toLowerCase();
        const missing = words.filter(w => !lowerContent.includes(w.toLowerCase()));
        if (missing.length > 0) {
          return {
            status: 'failed',
            message: `Content missing required words`,
            details: { missingWords: missing },
          };
        }
        return { status: 'passed' };
      },
    });
  },

  /**
   * Regex pattern check
   */
  pattern: (regex: RegExp, mustMatch: boolean = true): Guardrail => {
    return guardrail({
      name: 'pattern',
      description: `Check content against pattern: ${regex}`,
      check: (content) => {
        const matches = regex.test(content);
        if (mustMatch && !matches) {
          return {
            status: 'failed',
            message: `Content does not match required pattern`,
            details: { pattern: regex.toString() },
          };
        }
        if (!mustMatch && matches) {
          return {
            status: 'failed',
            message: `Content matches forbidden pattern`,
            details: { pattern: regex.toString() },
          };
        }
        return { status: 'passed' };
      },
    });
  },

  /**
   * JSON validity check
   */
  validJson: (): Guardrail => {
    return guardrail({
      name: 'valid_json',
      description: 'Ensure content is valid JSON',
      check: (content) => {
        try {
          JSON.parse(content);
          return { status: 'passed' };
        } catch (e: any) {
          return {
            status: 'failed',
            message: 'Content is not valid JSON',
            details: { error: e.message },
          };
        }
      },
    });
  },
};
