/**
 * MCP Security - Authentication, authorization, and rate limiting
 * 
 * Provides security policies for MCP servers.
 */

import { randomUUID } from 'crypto';

/**
 * Security policy type
 */
export type SecurityPolicyType = 'allow' | 'deny' | 'authenticate' | 'rate-limit';

/**
 * Authentication method
 */
export type AuthMethod = 'none' | 'api-key' | 'bearer' | 'basic' | 'oauth';

/**
 * Rate limit config
 */
export interface RateLimitConfig {
    /** Requests per window */
    requests: number;
    /** Window duration in ms */
    windowMs: number;
    /** Key function to identify client */
    keyFn?: (request: any) => string;
}

/**
 * Security policy
 */
export interface SecurityPolicy {
    id: string;
    name: string;
    type: SecurityPolicyType;
    /** Paths/methods this applies to */
    match?: { path?: string; method?: string };
    /** Auth config */
    auth?: { method: AuthMethod; validate?: (token: string) => Promise<boolean> };
    /** Rate limit config */
    rateLimit?: RateLimitConfig;
    /** Priority (higher = first) */
    priority?: number;
}

/**
 * Security context
 */
export interface SecurityContext {
    authenticated: boolean;
    userId?: string;
    roles?: string[];
    permissions?: string[];
    metadata?: Record<string, any>;
}

/**
 * Security result
 */
export interface SecurityResult {
    allowed: boolean;
    reason?: string;
    context?: SecurityContext;
}

/**
 * Rate limit state
 */
interface RateLimitState {
    count: number;
    windowStart: number;
}

/**
 * MCPSecurity - Security manager for MCP servers
 */
export class MCPSecurity {
    readonly id: string;
    private policies: SecurityPolicy[];
    private apiKeys: Set<string>;
    private rateLimits: Map<string, RateLimitState>;
    private logging: boolean;

    constructor(config?: { policies?: SecurityPolicy[]; apiKeys?: string[]; logging?: boolean }) {
        this.id = randomUUID();
        this.policies = config?.policies ?? [];
        this.apiKeys = new Set(config?.apiKeys ?? []);
        this.rateLimits = new Map();
        this.logging = config?.logging ?? false;

        // Sort by priority
        this.policies.sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
    }

    /**
     * Add API key
     */
    addApiKey(key: string): void {
        this.apiKeys.add(key);
    }

    /**
     * Remove API key
     */
    removeApiKey(key: string): boolean {
        return this.apiKeys.delete(key);
    }

    /**
     * Add security policy
     */
    addPolicy(policy: SecurityPolicy): void {
        this.policies.push(policy);
        this.policies.sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
    }

    /**
     * Remove policy
     */
    removePolicy(id: string): boolean {
        const index = this.policies.findIndex(p => p.id === id);
        if (index >= 0) {
            this.policies.splice(index, 1);
            return true;
        }
        return false;
    }

    /**
     * Check request against security policies
     */
    async check(request: {
        path?: string;
        method?: string;
        headers?: Record<string, string>;
        clientId?: string;
    }): Promise<SecurityResult> {
        // Find matching policies
        const matchingPolicies = this.policies.filter(p => this.matchPolicy(p, request));

        for (const policy of matchingPolicies) {
            const result = await this.evaluatePolicy(policy, request);
            if (!result.allowed) {
                if (this.logging) {
                    console.log(`[MCPSecurity] Denied by policy ${policy.name}: ${result.reason}`);
                }
                return result;
            }
        }

        return { allowed: true, context: { authenticated: false } };
    }

    /**
     * Validate API key
     */
    validateApiKey(key: string): boolean {
        return this.apiKeys.has(key);
    }

    /**
     * Extract token from headers
     */
    extractToken(headers: Record<string, string>): string | null {
        const auth = headers['authorization'] ?? headers['Authorization'];
        if (!auth) return null;

        if (auth.startsWith('Bearer ')) {
            return auth.slice(7);
        }
        if (auth.startsWith('Basic ')) {
            return auth.slice(6);
        }
        return auth;
    }

    /**
     * Check rate limit
     */
    checkRateLimit(clientId: string, config: RateLimitConfig): boolean {
        const key = `${clientId}:${config.requests}:${config.windowMs}`;
        const now = Date.now();

        let state = this.rateLimits.get(key);

        if (!state || now - state.windowStart >= config.windowMs) {
            state = { count: 0, windowStart: now };
        }

        state.count++;
        this.rateLimits.set(key, state);

        return state.count <= config.requests;
    }

    /**
     * Get rate limit remaining
     */
    getRateLimitRemaining(clientId: string, config: RateLimitConfig): number {
        const key = `${clientId}:${config.requests}:${config.windowMs}`;
        const state = this.rateLimits.get(key);
        if (!state) return config.requests;
        return Math.max(0, config.requests - state.count);
    }

    /**
     * Match policy against request
     */
    private matchPolicy(policy: SecurityPolicy, request: { path?: string; method?: string }): boolean {
        if (!policy.match) return true;

        if (policy.match.path && request.path) {
            if (!request.path.startsWith(policy.match.path)) return false;
        }

        if (policy.match.method && request.method) {
            if (request.method.toUpperCase() !== policy.match.method.toUpperCase()) return false;
        }

        return true;
    }

    /**
     * Evaluate policy
     */
    private async evaluatePolicy(
        policy: SecurityPolicy,
        request: { headers?: Record<string, string>; clientId?: string }
    ): Promise<SecurityResult> {
        switch (policy.type) {
            case 'deny':
                return { allowed: false, reason: 'Denied by policy' };

            case 'allow':
                return { allowed: true };

            case 'authenticate':
                if (!policy.auth) return { allowed: true };

                const token = request.headers ? this.extractToken(request.headers) : null;
                if (!token) {
                    return { allowed: false, reason: 'Authentication required' };
                }

                if (policy.auth.method === 'api-key' || policy.auth.method === 'bearer') {
                    const valid = policy.auth.validate
                        ? await policy.auth.validate(token)
                        : this.validateApiKey(token);

                    if (!valid) {
                        return { allowed: false, reason: 'Invalid credentials' };
                    }
                }

                return { allowed: true, context: { authenticated: true } };

            case 'rate-limit':
                if (!policy.rateLimit) return { allowed: true };

                const clientId = request.clientId ?? 'anonymous';
                if (!this.checkRateLimit(clientId, policy.rateLimit)) {
                    return { allowed: false, reason: 'Rate limit exceeded' };
                }

                return { allowed: true };

            default:
                return { allowed: true };
        }
    }

    /**
     * Clear rate limits
     */
    clearRateLimits(): void {
        this.rateLimits.clear();
    }

    /**
     * Get stats
     */
    getStats(): { policyCount: number; apiKeyCount: number; rateLimitEntries: number } {
        return {
            policyCount: this.policies.length,
            apiKeyCount: this.apiKeys.size,
            rateLimitEntries: this.rateLimits.size,
        };
    }
}

/**
 * Create security instance
 */
export function createMCPSecurity(config?: { policies?: SecurityPolicy[]; apiKeys?: string[] }): MCPSecurity {
    return new MCPSecurity(config);
}

/**
 * Create API key authentication policy
 */
export function createApiKeyPolicy(name: string, validate?: (key: string) => Promise<boolean>): SecurityPolicy {
    return {
        id: randomUUID(),
        name,
        type: 'authenticate',
        auth: { method: 'api-key', validate },
        priority: 100,
    };
}

/**
 * Create rate limit policy
 */
export function createRateLimitPolicy(name: string, requests: number, windowMs: number): SecurityPolicy {
    return {
        id: randomUUID(),
        name,
        type: 'rate-limit',
        rateLimit: { requests, windowMs },
        priority: 50,
    };
}

// Default export
export default MCPSecurity;
