/**
 * Router Agent - Route requests to specialized agents
 * 
 * @example Simple usage (5 lines)
 * ```typescript
 * import { Agent, Router } from 'praisonai';
 * 
 * const router = new Router({
 *   math: { agent: new Agent({ instructions: 'Math expert' }), keywords: ['calculate', 'math'] },
 *   code: { agent: new Agent({ instructions: 'Code expert' }), keywords: ['code', 'program'] }
 * });
 * await router.chat('Calculate 2+2');  // Routes to math agent
 * ```
 */

import type { EnhancedAgent } from './enhanced';
import { Agent } from './simple';

// Support both Agent and EnhancedAgent
type AnyAgent = Agent | EnhancedAgent;

export interface RouteConfig {
  agent: AnyAgent;
  condition: (input: string, context?: RouteContext) => boolean | Promise<boolean>;
  priority?: number;
}

/** Simplified route definition */
export interface SimpleRouteConfig {
  agent: AnyAgent;
  keywords?: string[];
  pattern?: RegExp;
  priority?: number;
}

export interface RouteContext {
  history?: string[];
  metadata?: Record<string, any>;
}

export interface RouterConfig {
  name?: string;
  routes: RouteConfig[];
  defaultAgent?: AnyAgent;
  verbose?: boolean;
}

/** Simplified router config - just a map of route name to config */
export type SimpleRouterConfig = Record<string, SimpleRouteConfig>;

/**
 * Router Agent - Routes requests to the most appropriate agent
 */
export class RouterAgent {
  readonly name: string;
  private routes: RouteConfig[];
  private defaultAgent?: AnyAgent;
  private verbose: boolean;

  constructor(config: RouterConfig) {
    this.name = config.name || 'Router';
    this.routes = config.routes.sort((a, b) => (b.priority || 0) - (a.priority || 0));
    this.defaultAgent = config.defaultAgent;
    this.verbose = config.verbose ?? false;
  }

  /**
   * Route a request to the appropriate agent
   */
  async route(input: string, context?: RouteContext): Promise<{ agent: AnyAgent; response: string } | null> {
    for (const route of this.routes) {
      const matches = await route.condition(input, context);
      if (matches) {
        if (this.verbose) {
          console.log(`[Router] Routing to: ${route.agent.name}`);
        }
        const response = await route.agent.chat(input);
        // Handle both Agent (returns string) and EnhancedAgent (returns ChatResult)
        const responseText = typeof response === 'string' ? response : response.text;
        return { agent: route.agent, response: responseText };
      }
    }

    if (this.defaultAgent) {
      if (this.verbose) {
        console.log(`[Router] Using default agent: ${this.defaultAgent.name}`);
      }
      const response = await this.defaultAgent.chat(input);
      const responseText = typeof response === 'string' ? response : response.text;
      return { agent: this.defaultAgent, response: responseText };
    }

    return null;
  }

  /**
   * Simplified chat method - routes and returns just the response
   */
  async chat(input: string, context?: RouteContext): Promise<string> {
    const result = await this.route(input, context);
    if (!result) {
      throw new Error('No matching route found and no default agent configured');
    }
    return result.response;
  }

  /**
   * Add a route
   */
  addRoute(config: RouteConfig): this {
    this.routes.push(config);
    this.routes.sort((a, b) => (b.priority || 0) - (a.priority || 0));
    return this;
  }

  /**
   * Get all routes
   */
  getRoutes(): RouteConfig[] {
    return [...this.routes];
  }
}

/**
 * Route condition helpers
 */
export const routeConditions = {
  /**
   * Match by keywords
   */
  keywords: (keywords: string | string[]) => {
    const keywordList = Array.isArray(keywords) ? keywords : [keywords];
    return (input: string): boolean => {
      const lower = input.toLowerCase();
      return keywordList.some(kw => lower.includes(kw.toLowerCase()));
    };
  },

  /**
   * Match by regex
   */
  pattern: (regex: RegExp) => {
    return (input: string): boolean => regex.test(input);
  },

  /**
   * Match by metadata
   */
  metadata: (key: string, value: any) => {
    return (_input: string, context?: RouteContext): boolean => {
      return context?.metadata?.[key] === value;
    };
  },

  /**
   * Always match (for default routes)
   */
  always: () => {
    return (): boolean => true;
  },

  /**
   * Combine conditions with AND
   */
  and: (...conditions: Array<(input: string, context?: RouteContext) => boolean>) => {
    return (input: string, context?: RouteContext): boolean => {
      return conditions.every(c => c(input, context));
    };
  },

  /**
   * Combine conditions with OR
   */
  or: (...conditions: Array<(input: string, context?: RouteContext) => boolean>) => {
    return (input: string, context?: RouteContext): boolean => {
      return conditions.some(c => c(input, context));
    };
  }
};

/**
 * Create a router agent (legacy API)
 */
export function createRouter(config: RouterConfig): RouterAgent {
  return new RouterAgent(config);
}

/**
 * Simplified Router class - uses keyword/pattern-based routing
 * 
 * @example Simple usage (5 lines)
 * ```typescript
 * import { Agent, Router } from 'praisonai';
 * 
 * const router = new Router({
 *   math: { agent: new Agent({ instructions: 'Math expert' }), keywords: ['calculate', 'math'] },
 *   code: { agent: new Agent({ instructions: 'Code expert' }), keywords: ['code', 'program'] }
 * });
 * await router.chat('Calculate 2+2');  // Routes to math agent
 * ```
 */
export class Router {
  private routerAgent: RouterAgent;
  private agentMap: Map<string, AnyAgent> = new Map();

  constructor(config: SimpleRouterConfig, options?: { default?: string; verbose?: boolean }) {
    const routes: RouteConfig[] = [];
    let defaultAgent: AnyAgent | undefined;

    for (const [name, routeConfig] of Object.entries(config)) {
      this.agentMap.set(name, routeConfig.agent);
      
      // Build condition from keywords or pattern
      let condition: (input: string) => boolean;
      if (routeConfig.keywords) {
        condition = routeConditions.keywords(routeConfig.keywords);
      } else if (routeConfig.pattern) {
        condition = routeConditions.pattern(routeConfig.pattern);
      } else {
        condition = routeConditions.always();
      }

      routes.push({
        agent: routeConfig.agent,
        condition,
        priority: routeConfig.priority
      });

      // Set default agent
      if (options?.default === name) {
        defaultAgent = routeConfig.agent;
      }
    }

    // If no default specified, use first agent
    if (!defaultAgent && routes.length > 0) {
      defaultAgent = routes[0].agent;
    }

    this.routerAgent = new RouterAgent({
      routes,
      defaultAgent,
      verbose: options?.verbose
    });
  }

  /**
   * Route and get response
   */
  async chat(input: string): Promise<string> {
    return this.routerAgent.chat(input);
  }

  /**
   * Route and get full result with agent info
   */
  async route(input: string): Promise<{ agent: AnyAgent; response: string } | null> {
    return this.routerAgent.route(input);
  }

  /**
   * Get agent by name
   */
  getAgent(name: string): AnyAgent | undefined {
    return this.agentMap.get(name);
  }
}
