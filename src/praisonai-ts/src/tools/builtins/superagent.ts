/**
 * Superagent Security Tools
 * 
 * AI security guardrails: Guard, Redact, Verify.
 * Package: @superagent-ai/ai-sdk
 */

import type { ToolMetadata, PraisonTool, ToolExecutionContext } from '../registry/types';
import { MissingDependencyError, MissingEnvVarError } from '../registry/types';

export const SUPERAGENT_METADATA: ToolMetadata = {
  id: 'superagent',
  displayName: 'Superagent Security',
  description: 'AI security guardrails: prompt injection protection, PII/PHI redaction, claim verification',
  tags: ['security', 'guardrails', 'pii', 'prompt-injection', 'verification'],
  requiredEnv: ['SUPERAGENT_API_KEY'],
  optionalEnv: [],
  install: {
    npm: 'npm install @superagent-ai/ai-sdk',
    pnpm: 'pnpm add @superagent-ai/ai-sdk',
    yarn: 'yarn add @superagent-ai/ai-sdk',
    bun: 'bun add @superagent-ai/ai-sdk',
  },
  docsSlug: 'tools/superagent',
  capabilities: {
    security: true,
  },
  packageName: '@superagent-ai/ai-sdk',
};

// Guard types
export interface GuardConfig {
  strictMode?: boolean;
}

export interface GuardInput {
  text: string;
}

export interface GuardResult {
  safe: boolean;
  threats: string[];
  decision: {
    status: 'allow' | 'block';
    violationTypes?: string[];
  };
}

// Redact types
export interface RedactConfig {
  entities?: string[];
}

export interface RedactInput {
  text: string;
}

export interface RedactResult {
  redactedText: string;
  entities: Array<{
    type: string;
    original: string;
    replacement: string;
  }>;
}

// Verify types
export interface VerifyConfig {
  strictMode?: boolean;
}

export interface VerifyInput {
  claim: string;
  sources: string[];
}

export interface VerifyResult {
  verified: boolean;
  confidence: number;
  evidence: string[];
}

async function loadSuperagentPackage() {
  if (!process.env.SUPERAGENT_API_KEY) {
    throw new MissingEnvVarError(
      SUPERAGENT_METADATA.id,
      'SUPERAGENT_API_KEY',
      SUPERAGENT_METADATA.docsSlug
    );
  }

  try {
    // @ts-ignore - Optional dependency
    return await import('@superagent-ai/ai-sdk');
  } catch {
    throw new MissingDependencyError(
      SUPERAGENT_METADATA.id,
      SUPERAGENT_METADATA.packageName,
      SUPERAGENT_METADATA.install,
      SUPERAGENT_METADATA.requiredEnv,
      SUPERAGENT_METADATA.docsSlug
    );
  }
}

/**
 * Create a Superagent Guard tool
 */
export function superagentGuard(config?: GuardConfig): PraisonTool<GuardInput, GuardResult> {
  return {
    name: 'guard',
    description: 'Check text for security threats like prompt injection, jailbreaks, and data exfiltration attempts.',
    parameters: {
      type: 'object',
      properties: {
        text: {
          type: 'string',
          description: 'The text to analyze for security threats',
        },
      },
      required: ['text'],
    },
    execute: async (input: GuardInput, context?: ToolExecutionContext): Promise<GuardResult> => {
      const pkg = await loadSuperagentPackage();
      const guardFn = (pkg as Record<string, unknown>).guard;
      
      if (guardFn && typeof guardFn === 'function') {
        const tool = guardFn(config);
        if (tool && typeof tool.execute === 'function') {
          return await tool.execute(input);
        }
      }
      
      return { safe: true, threats: [], decision: { status: 'allow' } };
    },
  };
}

/**
 * Create a Superagent Redact tool
 */
export function superagentRedact(config?: RedactConfig): PraisonTool<RedactInput, RedactResult> {
  return {
    name: 'redact',
    description: 'Remove sensitive data (PII, PHI, secrets) from text. Redacts SSNs, emails, phone numbers, credit cards, etc.',
    parameters: {
      type: 'object',
      properties: {
        text: {
          type: 'string',
          description: 'The text to redact sensitive information from',
        },
      },
      required: ['text'],
    },
    execute: async (input: RedactInput, context?: ToolExecutionContext): Promise<RedactResult> => {
      const pkg = await loadSuperagentPackage();
      const redactFn = (pkg as Record<string, unknown>).redact;
      
      if (redactFn && typeof redactFn === 'function') {
        const tool = redactFn(config);
        if (tool && typeof tool.execute === 'function') {
          return await tool.execute(input);
        }
      }
      
      return { redactedText: input.text, entities: [] };
    },
  };
}

/**
 * Create a Superagent Verify tool
 */
export function superagentVerify(config?: VerifyConfig): PraisonTool<VerifyInput, VerifyResult> {
  return {
    name: 'verify',
    description: 'Verify claims against source materials. Check if statements are supported by provided evidence.',
    parameters: {
      type: 'object',
      properties: {
        claim: {
          type: 'string',
          description: 'The claim to verify',
        },
        sources: {
          type: 'array',
          description: 'Source materials to verify against',
          items: { type: 'string' },
        },
      },
      required: ['claim', 'sources'],
    },
    execute: async (input: VerifyInput, context?: ToolExecutionContext): Promise<VerifyResult> => {
      const pkg = await loadSuperagentPackage();
      const verifyFn = (pkg as Record<string, unknown>).verify;
      
      if (verifyFn && typeof verifyFn === 'function') {
        const tool = verifyFn(config);
        if (tool && typeof tool.execute === 'function') {
          return await tool.execute(input);
        }
      }
      
      return { verified: false, confidence: 0, evidence: [] };
    },
  };
}

/**
 * Factory functions for registry
 */
export function createSuperagentGuardTool(config?: GuardConfig): PraisonTool<unknown, unknown> {
  return superagentGuard(config) as PraisonTool<unknown, unknown>;
}

export function createSuperagentRedactTool(config?: RedactConfig): PraisonTool<unknown, unknown> {
  return superagentRedact(config) as PraisonTool<unknown, unknown>;
}

export function createSuperagentVerifyTool(config?: VerifyConfig): PraisonTool<unknown, unknown> {
  return superagentVerify(config) as PraisonTool<unknown, unknown>;
}
