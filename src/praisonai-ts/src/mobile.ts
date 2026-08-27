/**
 * The webview-safe entry point.
 *
 * `praisonai` resolves to `src/index.ts`, which re-exports the CLI, the MCP
 * server, the tool registry and the knowledge store -- modules that read the
 * filesystem, spawn processes and open sockets. A phone loads none of them,
 * and a bundler cannot tell that: it follows every re-export, pulls the whole
 * graph in, and the build dies on a Node builtin that nothing was ever going
 * to call.
 *
 * So this is an allowlist, not a convenience. Everything named here is
 * verified loadable in a webview by `scripts/webview-gate.mjs`, which fails
 * the build if any of it gains an import-time Node dependency.
 *
 * The rule for adding to this file: if it cannot run in a browser, it does not
 * belong here -- even if it would be useful. A consumer reaching for something
 * absent gets a clear resolution error at build time, which is a far better
 * outcome than a blank screen on a device at import time.
 */

// The agent loop itself.
export { Agent } from './agent/simple';
export type {
  AgentEvent,
  AgentStreamOptions,
  SimpleAgentConfig,
  StopReason,
} from './agent/simple';

// Ids, and the env accessor. Both are safe by construction and both are what a
// caller needs in order to avoid reaching for the Node originals.
export { randomUUID } from './utils/uuid';
export { getEnv } from './llm/openaiClientOptions';
