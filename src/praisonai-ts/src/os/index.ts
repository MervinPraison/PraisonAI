/**
 * App Module for Production Deployment of AI Agents
 * 
 * This module provides AgentOS, a production platform for deploying
 * agents as web services with REST endpoints.
 * 
 * AgentOS, AgentOSConfig, AgentOSProtocol are the primary names (v1.0+).
 * AgentApp, AgentAppConfig, AgentAppProtocol are silent aliases for backward compatibility.
 * 
 * @example
 * ```typescript
 * import { AgentOS, Agent } from 'praisonai';
 * 
 * const assistant = new Agent({
 *   name: 'assistant',
 *   instructions: 'Be helpful'
 * });
 * 
 * const app = new AgentOS({
 *   name: 'My AI App',
 *   agents: [assistant],
 * });
 * 
 * await app.serve({ port: 8000 });
 * ```
 */

// Config
export {
    AgentOSConfig,
    AgentAppConfig,  // Silent alias
    DEFAULT_AGENTOS_CONFIG,
    mergeConfig,
} from './config';

// Protocols
export {
    AgentOSProtocol,
    AgentAppProtocol,  // Silent alias
} from './protocols';

// Implementation
export {
    AgentOS,
    AgentApp,  // Silent alias
    AgentOSOptions,
    AgentAppOptions,  // Silent alias
} from './agentos';
