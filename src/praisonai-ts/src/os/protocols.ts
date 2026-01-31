/**
 * AgentOS Protocol Definitions
 * 
 * This module defines the protocol (interface) for AgentOS implementations.
 * The protocol is lightweight and lives in the core SDK.
 * 
 * AgentOSProtocol is the primary name (v1.0+).
 * AgentAppProtocol is a silent alias for backward compatibility.
 * 
 * @example
 * ```typescript
 * import { AgentOSProtocol, AgentOSConfig } from 'praisonai';
 * 
 * class CustomAgentOS implements AgentOSProtocol {
 *   serve(options?: AgentOSConfig): Promise<void> { ... }
 *   getApp(): any { ... }
 * }
 * ```
 */

import type { AgentOSConfig } from './config';

/**
 * Protocol for AgentOS implementations.
 * 
 * AgentOS is a production platform for deploying agents as web services.
 * It wraps agents, teams, and flows into a unified API server.
 * 
 * Implementations should:
 * - Provide HTTP endpoints for agent interaction
 * - Support health checks and monitoring endpoints
 * - Handle agent lifecycle management
 * - Provide CORS support for web clients
 */
export interface AgentOSProtocol {
    /**
     * Start the AgentOS server.
     * 
     * @param options - Server configuration options
     * @returns Promise that resolves when server is ready
     */
    serve(options?: {
        host?: string;
        port?: number;
        reload?: boolean;
    }): Promise<void>;

    /**
     * Get the underlying web application instance.
     * 
     * @returns The Express/HTTP application instance for custom mounting or configuration
     */
    getApp(): any;
}

/**
 * AgentAppProtocol - Silent alias for AgentOSProtocol (backward compatibility)
 * @deprecated Use AgentOSProtocol instead
 */
export type AgentAppProtocol = AgentOSProtocol;
