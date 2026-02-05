/**
 * Protocols Module for PraisonAI TypeScript SDK
 * 
 * Python parity with praisonaiagents protocols
 * 
 * Provides:
 * - A2A (Agent-to-Agent) protocol types
 * - AGUI (Agent GUI) protocol types
 * - AutoRagAgent configuration
 * - Tools class
 * - Global singletons (config, memory, obs, workflows)
 * - Guardrail policy resolver
 */

// ============================================================================
// A2A Protocol Types (Agent-to-Agent)
// ============================================================================

/**
 * A2A Task state.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export enum A2ATaskState {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELED = 'canceled',
}

/**
 * A2A Role.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export enum A2ARole {
  USER = 'user',
  AGENT = 'agent',
}

/**
 * A2A Text part.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export interface A2ATextPart {
  type: 'text';
  text: string;
}

/**
 * A2A File part.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export interface A2AFilePart {
  type: 'file';
  file: {
    name: string;
    mimeType: string;
    bytes?: string;
    uri?: string;
  };
}

/**
 * A2A Data part.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export interface A2ADataPart {
  type: 'data';
  data: Record<string, any>;
}

export type A2APart = A2ATextPart | A2AFilePart | A2ADataPart;

/**
 * A2A Message.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export interface A2AMessage {
  role: A2ARole;
  parts: A2APart[];
  metadata?: Record<string, any>;
}

/**
 * A2A Task status.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export interface A2ATaskStatus {
  state: A2ATaskState;
  message?: A2AMessage;
  timestamp?: string;
}

/**
 * A2A Task.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export interface A2ATask {
  id: string;
  sessionId?: string;
  status: A2ATaskStatus;
  artifacts?: A2AArtifact[];
  history?: A2AMessage[];
  metadata?: Record<string, any>;
}

/**
 * A2A Artifact.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export interface A2AArtifact {
  name: string;
  description?: string;
  parts: A2APart[];
  index?: number;
  append?: boolean;
  lastChunk?: boolean;
  metadata?: Record<string, any>;
}

/**
 * A2A Agent skill.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export interface A2AAgentSkill {
  id: string;
  name: string;
  description?: string;
  tags?: string[];
  examples?: string[];
  inputModes?: string[];
  outputModes?: string[];
}

/**
 * A2A Agent capabilities.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export interface A2AAgentCapabilities {
  streaming?: boolean;
  pushNotifications?: boolean;
  stateTransitionHistory?: boolean;
}

/**
 * A2A Agent card.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export interface A2AAgentCard {
  name: string;
  description?: string;
  url: string;
  provider?: {
    organization: string;
    url?: string;
  };
  version: string;
  documentationUrl?: string;
  capabilities?: A2AAgentCapabilities;
  authentication?: {
    schemes: string[];
    credentials?: string;
  };
  defaultInputModes?: string[];
  defaultOutputModes?: string[];
  skills?: A2AAgentSkill[];
}

/**
 * A2A Send message request.
 * Python parity: praisonaiagents/ui/a2a/types.py
 */
export interface A2ASendMessageRequest {
  id: string;
  jsonrpc: '2.0';
  method: 'message/send';
  params: {
    id: string;
    sessionId?: string;
    message: A2AMessage;
    acceptedOutputModes?: string[];
    pushNotificationConfig?: {
      url: string;
      token?: string;
    };
    metadata?: Record<string, any>;
  };
}

/**
 * A2A class placeholder.
 * Python parity: praisonaiagents/ui/a2a/a2a.py
 */
export class A2A {
  private agentCard: A2AAgentCard;

  constructor(config: {
    name: string;
    description?: string;
    url?: string;
    version?: string;
    skills?: A2AAgentSkill[];
  }) {
    this.agentCard = {
      name: config.name,
      description: config.description,
      url: config.url ?? 'http://localhost:8000',
      version: config.version ?? '1.0.0',
      skills: config.skills,
    };
  }

  getAgentCard(): A2AAgentCard {
    return this.agentCard;
  }
}

// ============================================================================
// AGUI Protocol Types (Agent GUI)
// ============================================================================

/**
 * AGUI class placeholder.
 * Python parity: praisonaiagents/ui/agui/agui.py
 */
export class AGUI {
  private config: {
    name: string;
    description?: string;
  };

  constructor(config: {
    name: string;
    description?: string;
  }) {
    this.config = config;
  }

  getName(): string {
    return this.config.name;
  }
}

// ============================================================================
// AutoRagAgent Types
// ============================================================================

/**
 * Retrieval policy for AutoRagAgent.
 * Python parity: praisonaiagents/agents/auto_rag_agent.py
 */
export enum RetrievalPolicy {
  AUTO = 'auto',
  ALWAYS = 'always',
  NEVER = 'never',
}

/**
 * AutoRagAgent configuration.
 * Python parity: praisonaiagents/agents/auto_rag_agent.py
 */
export interface AutoRagAgentConfig {
  retrievalPolicy?: RetrievalPolicy;
  topK?: number;
  hybrid?: boolean;
  rerank?: boolean;
  includeCitations?: boolean;
  citationsMode?: 'append' | 'hidden' | 'none';
  maxContextTokens?: number;
  autoKeywords?: Set<string>;
  autoMinLength?: number;
}

/**
 * Default auto keywords for RAG retrieval.
 */
export const DEFAULT_AUTO_KEYWORDS = new Set([
  'what', 'how', 'why', 'when', 'where', 'who', 'which',
  'explain', 'describe', 'summarize', 'find', 'search',
  'tell me', 'show me', 'according to', 'based on',
  'cite', 'source', 'reference', 'document', 'paper',
]);

/**
 * AutoRagAgent class.
 * Python parity: praisonaiagents/agents/auto_rag_agent.py
 */
export class AutoRagAgent {
  private config: AutoRagAgentConfig;

  constructor(config: AutoRagAgentConfig = {}) {
    this.config = {
      retrievalPolicy: RetrievalPolicy.AUTO,
      topK: 5,
      hybrid: false,
      rerank: false,
      includeCitations: true,
      citationsMode: 'append',
      maxContextTokens: 4000,
      autoKeywords: DEFAULT_AUTO_KEYWORDS,
      autoMinLength: 10,
      ...config,
    };
  }

  /**
   * Check if query should trigger retrieval.
   */
  shouldRetrieve(query: string): boolean {
    if (this.config.retrievalPolicy === RetrievalPolicy.ALWAYS) {
      return true;
    }
    if (this.config.retrievalPolicy === RetrievalPolicy.NEVER) {
      return false;
    }

    // AUTO mode - check heuristics
    if (query.length < (this.config.autoMinLength ?? 10)) {
      return false;
    }

    const lowerQuery = query.toLowerCase();
    for (const keyword of this.config.autoKeywords ?? DEFAULT_AUTO_KEYWORDS) {
      if (lowerQuery.includes(keyword)) {
        return true;
      }
    }

    return false;
  }

  getConfig(): AutoRagAgentConfig {
    return { ...this.config };
  }
}

// ============================================================================
// Tools Class
// ============================================================================

/**
 * Tool definition.
 */
export interface ToolDefinition {
  name: string;
  description: string;
  parameters?: Record<string, any>;
  execute: (...args: any[]) => any | Promise<any>;
}

/**
 * Tools registry class.
 * Python parity: praisonaiagents/tools
 */
export class Tools {
  private _tools: Map<string, ToolDefinition> = new Map();

  /**
   * Register a tool.
   */
  register(tool: ToolDefinition): void {
    this._tools.set(tool.name, tool);
  }

  /**
   * Get a tool by name.
   */
  get(name: string): ToolDefinition | undefined {
    return this._tools.get(name);
  }

  /**
   * Check if tool exists.
   */
  has(name: string): boolean {
    return this._tools.has(name);
  }

  /**
   * List all tools.
   */
  list(): ToolDefinition[] {
    return Array.from(this._tools.values());
  }

  /**
   * Remove a tool.
   */
  remove(name: string): boolean {
    return this._tools.delete(name);
  }

  /**
   * Clear all tools.
   */
  clear(): void {
    this._tools.clear();
  }

  /**
   * Get tool count.
   */
  get count(): number {
    return this._tools.size;
  }
}

// ============================================================================
// Global Singletons
// ============================================================================

/**
 * Global config singleton.
 * Python parity: praisonaiagents.config
 */
let _globalConfig: Record<string, any> = {};

export const config = {
  get<T = any>(key: string, defaultValue?: T): T | undefined {
    return _globalConfig[key] ?? defaultValue;
  },
  set(key: string, value: any): void {
    _globalConfig[key] = value;
  },
  getAll(): Record<string, any> {
    return { ..._globalConfig };
  },
  clear(): void {
    _globalConfig = {};
  },
};

/**
 * Global memory singleton.
 * Python parity: praisonaiagents.memory
 */
let _globalMemory: Map<string, any> = new Map();

export const memory = {
  get<T = any>(key: string): T | undefined {
    return _globalMemory.get(key);
  },
  set(key: string, value: any): void {
    _globalMemory.set(key, value);
  },
  has(key: string): boolean {
    return _globalMemory.has(key);
  },
  delete(key: string): boolean {
    return _globalMemory.delete(key);
  },
  clear(): void {
    _globalMemory.clear();
  },
  keys(): string[] {
    return Array.from(_globalMemory.keys());
  },
  size(): number {
    return _globalMemory.size;
  },
};

/**
 * Global observability singleton.
 * Python parity: praisonaiagents.obs
 */
let _obsEnabled = false;
let _obsProvider: any = null;

export const obs = {
  enable(provider?: any): void {
    _obsEnabled = true;
    _obsProvider = provider;
  },
  disable(): void {
    _obsEnabled = false;
    _obsProvider = null;
  },
  isEnabled(): boolean {
    return _obsEnabled;
  },
  getProvider(): any {
    return _obsProvider;
  },
  trace(name: string, data?: Record<string, any>): void {
    if (_obsEnabled && _obsProvider?.trace) {
      _obsProvider.trace(name, data);
    }
  },
  span(name: string): { end: () => void } {
    if (_obsEnabled && _obsProvider?.span) {
      return _obsProvider.span(name);
    }
    return { end: () => {} };
  },
};

/**
 * Global workflows singleton.
 * Python parity: praisonaiagents.workflows
 */
let _workflows: Map<string, any> = new Map();

export const workflows = {
  register(name: string, workflow: any): void {
    _workflows.set(name, workflow);
  },
  get(name: string): any | undefined {
    return _workflows.get(name);
  },
  has(name: string): boolean {
    return _workflows.has(name);
  },
  list(): string[] {
    return Array.from(_workflows.keys());
  },
  remove(name: string): boolean {
    return _workflows.delete(name);
  },
  clear(): void {
    _workflows.clear();
  },
};

// ============================================================================
// Guardrail Policy Resolver
// ============================================================================

/**
 * Guardrail policy.
 */
export interface GuardrailPolicy {
  name: string;
  action: 'block' | 'warn' | 'log' | 'allow';
  conditions?: Record<string, any>;
  message?: string;
}

/**
 * Resolve guardrail policies.
 * Python parity: praisonaiagents/config/resolvers.py
 */
export function resolveGuardrailPolicies(
  policies: (string | GuardrailPolicy)[]
): GuardrailPolicy[] {
  const resolved: GuardrailPolicy[] = [];

  for (const policy of policies) {
    if (typeof policy === 'string') {
      // Resolve string preset
      const preset = GUARDRAIL_POLICY_PRESETS[policy];
      if (preset) {
        resolved.push(preset);
      } else {
        resolved.push({
          name: policy,
          action: 'warn',
        });
      }
    } else {
      resolved.push(policy);
    }
  }

  return resolved;
}

/**
 * Guardrail policy presets.
 */
export const GUARDRAIL_POLICY_PRESETS: Record<string, GuardrailPolicy> = {
  'block-pii': {
    name: 'block-pii',
    action: 'block',
    message: 'PII detected in content',
  },
  'warn-pii': {
    name: 'warn-pii',
    action: 'warn',
    message: 'PII detected in content',
  },
  'block-profanity': {
    name: 'block-profanity',
    action: 'block',
    message: 'Profanity detected',
  },
  'log-all': {
    name: 'log-all',
    action: 'log',
  },
  'allow-all': {
    name: 'allow-all',
    action: 'allow',
  },
};

// ============================================================================
// AgentManager Alias
// ============================================================================

/**
 * AgentManager is an alias for AgentTeam.
 * Python parity: praisonaiagents/agents/agents.py
 * 
 * Note: This is exported from the main index.ts as an alias.
 * The actual AgentTeam class is in the agents module.
 */
export type AgentManager = any; // Alias - actual type is AgentTeam
