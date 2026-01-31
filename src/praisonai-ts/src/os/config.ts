/**
 * AgentOS Configuration
 * 
 * This module defines the configuration interface for AgentOS.
 * It follows PraisonAI's principle of sensible defaults with explicit overrides.
 * 
 * @example
 * ```typescript
 * const config: AgentOSConfig = {
 *   name: 'My AI App',
 *   port: 9000,
 *   debug: true
 * };
 * ```
 */

/**
 * Configuration for AgentOS.
 * 
 * All properties are optional with sensible defaults.
 */
export interface AgentOSConfig {
    /** Name of the application (default: "PraisonAI App") */
    name?: string;

    /** Host address to bind to (default: "0.0.0.0") */
    host?: string;

    /** Port number to listen on (default: 8000) */
    port?: number;

    /** Enable auto-reload for development (default: false) */
    reload?: boolean;

    /** List of allowed CORS origins (default: ["*"]) */
    corsOrigins?: string[];

    /** API route prefix (default: "/api") */
    apiPrefix?: string;

    /** URL for API documentation (default: "/docs") */
    docsUrl?: string;

    /** URL for OpenAPI schema (default: "/openapi.json") */
    openapiUrl?: string;

    /** Enable debug mode (default: false) */
    debug?: boolean;

    /** Logging level (default: "info") */
    logLevel?: 'debug' | 'info' | 'warn' | 'error';

    /** Number of worker processes (default: 1) */
    workers?: number;

    /** Request timeout in seconds (default: 60) */
    timeout?: number;

    /** Additional metadata for the app */
    metadata?: Record<string, any>;
}

/**
 * Default configuration values for AgentOS.
 */
export const DEFAULT_AGENTOS_CONFIG: Required<Omit<AgentOSConfig, 'metadata'>> & { metadata: Record<string, any> } = {
    name: 'PraisonAI App',
    host: '0.0.0.0',
    port: 8000,
    reload: false,
    corsOrigins: ['*'],
    apiPrefix: '/api',
    docsUrl: '/docs',
    openapiUrl: '/openapi.json',
    debug: false,
    logLevel: 'info',
    workers: 1,
    timeout: 60,
    metadata: {},
};

/**
 * Merge user config with defaults.
 */
export function mergeConfig(userConfig?: AgentOSConfig): Required<Omit<AgentOSConfig, 'metadata'>> & { metadata: Record<string, any> } {
    return {
        ...DEFAULT_AGENTOS_CONFIG,
        ...userConfig,
        metadata: {
            ...DEFAULT_AGENTOS_CONFIG.metadata,
            ...userConfig?.metadata,
        },
    };
}

/**
 * AgentAppConfig - Silent alias for AgentOSConfig (backward compatibility)
 * @deprecated Use AgentOSConfig instead
 */
export type AgentAppConfig = AgentOSConfig;
