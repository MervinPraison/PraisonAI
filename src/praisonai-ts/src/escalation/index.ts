/**
 * Escalation Module for PraisonAI Agents.
 *
 * Python parity: praisonaiagents/escalation/__init__.py. Progressive
 * escalation pipeline for auto-mode execution:
 * - Stage 0: Direct response (no tools, no planning)
 * - Stage 1: Heuristic tool usage (local signals, no extra LLM call)
 * - Stage 2: Lightweight plan (single LLM call, constrained)
 * - Stage 3: Full autonomous loop (tools + subagents + verification)
 *
 * @example
 * import { EscalationPipeline, EscalationStage } from 'praisonai/escalation';
 *
 * const pipeline = new EscalationPipeline({ agent });
 * const stage = pipeline.analyze(prompt, context);
 * const result = await pipeline.executeAtStage(prompt, stage);
 */

// Core pipeline
export { EscalationPipeline } from './pipeline';
export type {
  EscalationPipelineOptions,
  EscalationAgent,
  CheckpointServiceLike,
  StageExecutionResult,
  AutonomousRunner,
  StageChangeCallback,
} from './pipeline';

// Types
export {
  EscalationStage,
  EscalationSignal,
  EscalationConfig,
  EscalationResult,
  StageContext,
  stageName,
  toEscalationConfig,
} from './types';
export type {
  EscalationConfigOptions,
  EscalationResultOptions,
  StageContextOptions,
  StageStep,
  StageToolResult,
} from './types';

// Signals and triggers
export { EscalationTrigger } from './triggers';

// Doom loop detection
export {
  DoomLoopDetector,
  DoomLoopConfig,
  DoomLoopEvent,
  DoomLoopType,
  RecoveryAction,
  toDoomLoopConfig,
  stableHash,
} from './doom-loop';
export type { DoomLoopConfigOptions, DoomLoopEventOptions, ActionRecord, DoomLoopStats } from './doom-loop';

// Observability (Python `EventType` is exported as `ObservabilityEventType`
// to avoid clashing with src/trace's `EventType`).
export { ObservabilityHooks, ObservabilityEventType, ObservabilityEvent, ExecutionMetrics } from './observability';
export type {
  ObservabilityHooksOptions,
  ObservabilityEventOptions,
  ExecutionMetricsOptions,
  ObservabilityHandler,
} from './observability';
