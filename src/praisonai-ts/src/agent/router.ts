/**
 * Router Agent - Route requests to specialized agents
 */

import type { EnhancedAgent } from './enhanced';

export interface RouteConfig {
  agent: EnhancedAgent;
  condition: (input: string, context?: RouteContext) => boolean | Promise<boolean>;
  priority?: number;
}

export interface RouteContext {
  history?: string[];
  metadata?: Record<string, any>;
}

export interface RouterConfig {
  name?: string;
  routes: RouteConfig[];
  defaultAgent?: EnhancedAgent;
  verbose?: boolean;
}

/**
 * Router Agent - Routes requests to the most appropriate agent
 */
export class RouterAgent {
  readonly name: string;
  private routes: RouteConfig[];
  private defaultAgent?: EnhancedAgent;
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
  async route(input: string, context?: RouteContext): Promise<{ agent: EnhancedAgent; response: string } | null> {
    for (const route of this.routes) {
      const matches = await route.condition(input, context);
      if (matches) {
        if (this.verbose) {
          console.log(`[Router] Routing to: ${route.agent.name}`);
        }
        const response = await route.agent.chat(input);
        return { agent: route.agent, response: response.text };
      }
    }

    if (this.defaultAgent) {
      if (this.verbose) {
        console.log(`[Router] Using default agent: ${this.defaultAgent.name}`);
      }
      const response = await this.defaultAgent.chat(input);
      return { agent: this.defaultAgent, response: response.text };
    }

    return null;
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
 * Create a router agent
 */
export function createRouter(config: RouterConfig): RouterAgent {
  return new RouterAgent(config);
}
