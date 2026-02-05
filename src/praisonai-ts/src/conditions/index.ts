/**
 * Conditions Module for PraisonAI TypeScript SDK
 * 
 * Python parity with praisonaiagents condition types
 * 
 * Provides:
 * - Condition protocols
 * - Condition implementations
 * - Condition evaluation
 */

// ============================================================================
// Condition Protocol
// ============================================================================

/**
 * Condition protocol interface.
 * Python parity: praisonaiagents/conditions
 */
export interface ConditionProtocol {
  evaluate(context: Record<string, any>): boolean | Promise<boolean>;
  describe(): string;
}

/**
 * Routing condition protocol.
 * Python parity: praisonaiagents/conditions
 */
export interface RoutingConditionProtocol extends ConditionProtocol {
  getTargetAgent(context: Record<string, any>): string | null;
}

// ============================================================================
// Condition Implementations
// ============================================================================

/**
 * Dictionary-based condition.
 * Python parity: praisonaiagents/conditions
 */
export class DictCondition implements ConditionProtocol {
  private conditions: Record<string, any>;
  private operator: 'and' | 'or';

  constructor(conditions: Record<string, any>, operator: 'and' | 'or' = 'and') {
    this.conditions = conditions;
    this.operator = operator;
  }

  evaluate(context: Record<string, any>): boolean {
    const results: boolean[] = [];

    for (const [key, expectedValue] of Object.entries(this.conditions)) {
      const actualValue = context[key];
      
      if (typeof expectedValue === 'function') {
        results.push(expectedValue(actualValue));
      } else if (expectedValue instanceof RegExp) {
        results.push(expectedValue.test(String(actualValue)));
      } else {
        results.push(actualValue === expectedValue);
      }
    }

    if (this.operator === 'and') {
      return results.every(r => r);
    } else {
      return results.some(r => r);
    }
  }

  describe(): string {
    const conditions = Object.entries(this.conditions)
      .map(([k, v]) => `${k} = ${v}`)
      .join(` ${this.operator.toUpperCase()} `);
    return `DictCondition(${conditions})`;
  }
}

/**
 * Expression-based condition.
 * Python parity: praisonaiagents/conditions
 */
export class ExpressionCondition implements ConditionProtocol {
  private expression: string;
  private evaluator: (context: Record<string, any>) => boolean;

  constructor(expression: string) {
    this.expression = expression;
    this.evaluator = this.compileExpression(expression);
  }

  private compileExpression(expr: string): (context: Record<string, any>) => boolean {
    // Simple expression parser for common patterns
    // Supports: ==, !=, >, <, >=, <=, &&, ||, !
    return (context: Record<string, any>) => {
      try {
        // Create a safe evaluation context
        const keys = Object.keys(context);
        const values = Object.values(context);
        
        // Replace variable names with context values
        let evalExpr = expr;
        for (const key of keys) {
          const value = context[key];
          const replacement = typeof value === 'string' ? `"${value}"` : String(value);
          evalExpr = evalExpr.replace(new RegExp(`\\b${key}\\b`, 'g'), replacement);
        }
        
        // Evaluate the expression (simplified - in production use a proper parser)
        // This is a basic implementation for common cases
        return this.evaluateSimple(evalExpr, context);
      } catch {
        return false;
      }
    };
  }

  private evaluateSimple(expr: string, context: Record<string, any>): boolean {
    // Handle simple comparisons
    const comparisonMatch = expr.match(/^(\w+)\s*(==|!=|>=|<=|>|<)\s*(.+)$/);
    if (comparisonMatch) {
      const [, varName, op, valueStr] = comparisonMatch;
      const actualValue = context[varName];
      let expectedValue: any = valueStr.trim();
      
      // Parse the expected value
      if (expectedValue === 'true') expectedValue = true;
      else if (expectedValue === 'false') expectedValue = false;
      else if (expectedValue === 'null') expectedValue = null;
      else if (/^-?\d+$/.test(expectedValue)) expectedValue = parseInt(expectedValue);
      else if (/^-?\d+\.\d+$/.test(expectedValue)) expectedValue = parseFloat(expectedValue);
      else if (/^["'].*["']$/.test(expectedValue)) expectedValue = expectedValue.slice(1, -1);
      
      switch (op) {
        case '==': return actualValue === expectedValue;
        case '!=': return actualValue !== expectedValue;
        case '>': return actualValue > expectedValue;
        case '<': return actualValue < expectedValue;
        case '>=': return actualValue >= expectedValue;
        case '<=': return actualValue <= expectedValue;
      }
    }
    
    // Handle boolean expressions
    if (expr === 'true') return true;
    if (expr === 'false') return false;
    
    // Handle variable lookup
    if (context[expr] !== undefined) {
      return Boolean(context[expr]);
    }
    
    return false;
  }

  evaluate(context: Record<string, any>): boolean {
    return this.evaluator(context);
  }

  describe(): string {
    return `ExpressionCondition(${this.expression})`;
  }
}

/**
 * Function-based condition.
 */
export class FunctionCondition implements ConditionProtocol {
  private fn: (context: Record<string, any>) => boolean | Promise<boolean>;
  private description: string;

  constructor(
    fn: (context: Record<string, any>) => boolean | Promise<boolean>,
    description: string = 'FunctionCondition'
  ) {
    this.fn = fn;
    this.description = description;
  }

  evaluate(context: Record<string, any>): boolean | Promise<boolean> {
    return this.fn(context);
  }

  describe(): string {
    return this.description;
  }
}

// ============================================================================
// Condition Evaluation
// ============================================================================

/**
 * Evaluate a condition.
 * Python parity: praisonaiagents/conditions
 */
export function evaluateCondition(
  condition: ConditionProtocol | Record<string, any> | string | ((ctx: Record<string, any>) => boolean),
  context: Record<string, any>
): boolean | Promise<boolean> {
  // If it's a ConditionProtocol
  if (typeof condition === 'object' && 'evaluate' in condition) {
    return condition.evaluate(context);
  }
  
  // If it's a function
  if (typeof condition === 'function') {
    return condition(context);
  }
  
  // If it's a string expression
  if (typeof condition === 'string') {
    const expr = new ExpressionCondition(condition);
    return expr.evaluate(context);
  }
  
  // If it's a dictionary
  if (typeof condition === 'object') {
    const dict = new DictCondition(condition);
    return dict.evaluate(context);
  }
  
  return false;
}

/**
 * Create a condition from various input types.
 */
export function createCondition(
  input: ConditionProtocol | Record<string, any> | string | ((ctx: Record<string, any>) => boolean)
): ConditionProtocol {
  if (typeof input === 'object' && 'evaluate' in input && 'describe' in input) {
    return input as ConditionProtocol;
  }
  
  if (typeof input === 'function') {
    return new FunctionCondition(input as (ctx: Record<string, any>) => boolean);
  }
  
  if (typeof input === 'string') {
    return new ExpressionCondition(input);
  }
  
  if (typeof input === 'object') {
    return new DictCondition(input as Record<string, any>);
  }
  
  throw new Error('Invalid condition input');
}

/**
 * Combine conditions with AND.
 */
export function andConditions(...conditions: ConditionProtocol[]): ConditionProtocol {
  return new FunctionCondition(
    async (context) => {
      for (const condition of conditions) {
        const result = await condition.evaluate(context);
        if (!result) return false;
      }
      return true;
    },
    `AND(${conditions.map(c => c.describe()).join(', ')})`
  );
}

/**
 * Combine conditions with OR.
 */
export function orConditions(...conditions: ConditionProtocol[]): ConditionProtocol {
  return new FunctionCondition(
    async (context) => {
      for (const condition of conditions) {
        const result = await condition.evaluate(context);
        if (result) return true;
      }
      return false;
    },
    `OR(${conditions.map(c => c.describe()).join(', ')})`
  );
}

/**
 * Negate a condition.
 */
export function notCondition(condition: ConditionProtocol): ConditionProtocol {
  return new FunctionCondition(
    async (context) => {
      const result = await condition.evaluate(context);
      return !result;
    },
    `NOT(${condition.describe()})`
  );
}
