/**
 * RulesManager - Agent rules management system
 * 
 * Enables agents to follow configurable rules and policies.
 * 
 * @example
 * ```typescript
 * import { RulesManager, Agent } from 'praisonai';
 * 
 * const rules = new RulesManager({
 *   rules: [
 *     { id: 'safety', pattern: /harmful/i, action: 'block' },
 *     { id: 'format', pattern: /json/i, action: 'transform' }
 *   ]
 * });
 * 
 * const agent = new Agent({ rules });
 * ```
 */

import { randomUUID } from 'crypto';

/**
 * Rule action types
 */
export type RuleAction = 'allow' | 'block' | 'warn' | 'transform' | 'log';

/**
 * Rule priority levels
 */
export type RulePriority = 'low' | 'medium' | 'high' | 'critical';

/**
 * Rule definition
 */
export interface Rule {
    /** Unique rule identifier */
    id: string;
    /** Human-readable name */
    name?: string;
    /** Rule description */
    description?: string;
    /** Pattern to match (string or regex) */
    pattern?: string | RegExp;
    /** Custom matcher function */
    matcher?: (content: string, context?: RuleContext) => boolean;
    /** Action to take when matched */
    action: RuleAction;
    /** Priority level */
    priority?: RulePriority;
    /** Transformation function (for action='transform') */
    transform?: (content: string) => string;
    /** Custom handler */
    handler?: (content: string, context?: RuleContext) => RuleResult;
    /** Whether rule is enabled */
    enabled?: boolean;
    /** Tags for categorization */
    tags?: string[];
}

/**
 * Context passed to rule evaluation
 */
export interface RuleContext {
    /** Source of content (user, agent, tool) */
    source?: 'user' | 'agent' | 'tool' | 'system';
    /** Agent ID if applicable */
    agentId?: string;
    /** Session ID if applicable */
    sessionId?: string;
    /** Additional metadata */
    metadata?: Record<string, any>;
}

/**
 * Result of rule evaluation
 */
export interface RuleResult {
    /** Whether rule matched */
    matched: boolean;
    /** Rule ID that matched */
    ruleId: string;
    /** Action taken */
    action: RuleAction;
    /** Original content */
    original: string;
    /** Transformed content (if applicable) */
    transformed?: string;
    /** Warning/error message */
    message?: string;
}

/**
 * Rules evaluation summary
 */
export interface RulesEvaluation {
    /** Whether content passed all rules */
    passed: boolean;
    /** All rule results */
    results: RuleResult[];
    /** Blocked by rules */
    blocked: RuleResult[];
    /** Warnings generated */
    warnings: RuleResult[];
    /** Transformations applied */
    transformations: RuleResult[];
    /** Final content after transformations */
    content: string;
}

/**
 * RulesManager configuration
 */
export interface RulesManagerConfig {
    /** Initial rules */
    rules?: Rule[];
    /** Default action for unmatched content */
    defaultAction?: RuleAction;
    /** Whether to continue after first match */
    continueOnMatch?: boolean;
    /** Enable logging */
    logging?: boolean;
}

/**
 * RulesManager - Manages agent rules and policies
 */
export class RulesManager {
    readonly id: string;
    private rules: Map<string, Rule>;
    private defaultAction: RuleAction;
    private continueOnMatch: boolean;
    private logging: boolean;

    constructor(config: RulesManagerConfig = {}) {
        this.id = randomUUID();
        this.rules = new Map();
        this.defaultAction = config.defaultAction ?? 'allow';
        this.continueOnMatch = config.continueOnMatch ?? true;
        this.logging = config.logging ?? false;

        // Add initial rules
        if (config.rules) {
            for (const rule of config.rules) {
                this.addRule(rule);
            }
        }
    }

    /**
     * Add a rule
     */
    addRule(rule: Rule): void {
        const ruleWithDefaults: Rule = {
            ...rule,
            enabled: rule.enabled ?? true,
            priority: rule.priority ?? 'medium',
        };
        this.rules.set(rule.id, ruleWithDefaults);
    }

    /**
     * Remove a rule
     */
    removeRule(id: string): boolean {
        return this.rules.delete(id);
    }

    /**
     * Get a rule by ID
     */
    getRule(id: string): Rule | undefined {
        return this.rules.get(id);
    }

    /**
     * Get all rules
     */
    getAllRules(): Rule[] {
        return Array.from(this.rules.values());
    }

    /**
     * Enable/disable a rule
     */
    setRuleEnabled(id: string, enabled: boolean): boolean {
        const rule = this.rules.get(id);
        if (rule) {
            this.rules.set(id, { ...rule, enabled });
            return true;
        }
        return false;
    }

    /**
     * Evaluate content against a single rule
     */
    private evaluateRule(rule: Rule, content: string, context?: RuleContext): RuleResult {
        let matched = false;

        // Check custom matcher first
        if (rule.matcher) {
            matched = rule.matcher(content, context);
        }
        // Check pattern
        else if (rule.pattern) {
            const pattern = typeof rule.pattern === 'string'
                ? new RegExp(rule.pattern, 'i')
                : rule.pattern;
            matched = pattern.test(content);
        }

        if (!matched) {
            return { matched: false, ruleId: rule.id, action: 'allow', original: content };
        }

        // Handle custom handler
        if (rule.handler) {
            return rule.handler(content, context);
        }

        // Handle transformation
        let transformed: string | undefined;
        if (rule.action === 'transform' && rule.transform) {
            transformed = rule.transform(content);
        }

        return {
            matched: true,
            ruleId: rule.id,
            action: rule.action,
            original: content,
            transformed,
            message: rule.action === 'block' ? `Blocked by rule: ${rule.name || rule.id}` : undefined,
        };
    }

    /**
     * Evaluate content against all rules
     */
    evaluate(content: string, context?: RuleContext): RulesEvaluation {
        const results: RuleResult[] = [];
        const blocked: RuleResult[] = [];
        const warnings: RuleResult[] = [];
        const transformations: RuleResult[] = [];
        let currentContent = content;

        // Sort rules by priority
        const priorityOrder: Record<RulePriority, number> = {
            critical: 0, high: 1, medium: 2, low: 3
        };

        const sortedRules = this.getAllRules()
            .filter(r => r.enabled)
            .sort((a, b) => priorityOrder[a.priority!] - priorityOrder[b.priority!]);

        for (const rule of sortedRules) {
            const result = this.evaluateRule(rule, currentContent, context);
            results.push(result);

            if (result.matched) {
                if (this.logging) {
                    console.log(`[RulesManager] Rule ${rule.id} matched: ${result.action}`);
                }

                switch (result.action) {
                    case 'block':
                        blocked.push(result);
                        break;
                    case 'warn':
                        warnings.push(result);
                        break;
                    case 'transform':
                        if (result.transformed) {
                            transformations.push(result);
                            currentContent = result.transformed;
                        }
                        break;
                }

                if (!this.continueOnMatch && result.action === 'block') {
                    break;
                }
            }
        }

        const passed = blocked.length === 0;

        return {
            passed,
            results,
            blocked,
            warnings,
            transformations,
            content: passed ? currentContent : content,
        };
    }

    /**
     * Quick check if content passes rules
     */
    check(content: string, context?: RuleContext): boolean {
        return this.evaluate(content, context).passed;
    }

    /**
     * Apply rules and get transformed content
     */
    apply(content: string, context?: RuleContext): string {
        const evaluation = this.evaluate(content, context);
        if (!evaluation.passed) {
            throw new Error(evaluation.blocked[0]?.message || 'Content blocked by rules');
        }
        return evaluation.content;
    }

    /**
     * Get rules by tag
     */
    getRulesByTag(tag: string): Rule[] {
        return this.getAllRules().filter(r => r.tags?.includes(tag));
    }

    /**
     * Clear all rules
     */
    clear(): void {
        this.rules.clear();
    }

    /**
     * Export rules to JSON
     */
    toJSON(): Rule[] {
        return this.getAllRules().map(r => ({
            ...r,
            pattern: r.pattern instanceof RegExp ? r.pattern.source : r.pattern,
            matcher: undefined,
            transform: undefined,
            handler: undefined,
        }));
    }
}

/**
 * Create a rules manager
 */
export function createRulesManager(config?: RulesManagerConfig): RulesManager {
    return new RulesManager(config);
}

/**
 * Create common safety rules
 */
export function createSafetyRules(): Rule[] {
    return [
        {
            id: 'no-harmful-content',
            name: 'Block Harmful Content',
            pattern: /\b(dangerous|harmful|illegal|attack)\b/i,
            action: 'block',
            priority: 'critical',
            tags: ['safety']
        },
        {
            id: 'pii-warning',
            name: 'PII Warning',
            pattern: /\b(\d{3}-\d{2}-\d{4}|ssn|social security)\b/i,
            action: 'warn',
            priority: 'high',
            tags: ['privacy', 'pii']
        }
    ];
}

// Default export
export default RulesManager;
