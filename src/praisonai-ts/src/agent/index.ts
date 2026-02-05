/**
 * Agent Module - Core agent classes for PraisonAI
 * 
 * The primary exports are:
 * - Agent: Single agent with instructions, tools, and optional persistence
 * - Agents: Multi-agent orchestration (alias for PraisonAIAgents)
 * - Router: Simplified keyword/pattern-based routing
 * - Workflow: Step-based workflow execution (from workflows module)
 */

// Core exports - the main API surface
export { Agent, AgentTeam, PraisonAIAgents, Agents } from './simple';
export type { SimpleAgentConfig, AgentTeamConfig, PraisonAIAgentsConfig } from './simple';

// AudioAgent - Speech synthesis and transcription
export { AudioAgent, createAudioAgent } from './audio';
export type { AudioAgentConfig, SpeakOptions, TranscribeOptions, SpeakResult, TranscribeResult, AudioProvider } from './audio';

// CodeAgent - Code generation, execution, review, refactoring (Python parity)
export { CodeAgent, createCodeAgent } from './code';
export type { CodeConfig, CodeAgentConfig, CodeExecutionResult } from './code';

// OCRAgent - Optical Character Recognition (Python parity)
export { OCRAgent, createOCRAgent } from './ocr';
export type { OCRConfig, OCRAgentConfig, OCRResult, OCRPage } from './ocr';

// VisionAgent - Image analysis (Python parity)
export { VisionAgent, createVisionAgent } from './vision';
export type { VisionConfig, VisionAgentConfig, VisionResult } from './vision';

// VideoAgent - Video analysis (Python parity)
export { VideoAgent, createVideoAgent } from './video';
export type { VideoConfig, VideoAgentConfig, VideoResult } from './video';

// EmbeddingAgent - Text embeddings (Python parity)
export { EmbeddingAgent, createEmbeddingAgent } from './embedding';
export type { EmbeddingConfig, EmbeddingAgentConfig, EmbeddingResult, BatchEmbeddingResult } from './embedding';

// RealtimeAgent - Real-time voice (Python parity)
export { RealtimeAgent, createRealtimeAgent } from './realtime';
export type { RealtimeConfig, RealtimeAgentConfig, RealtimeEvent, RealtimeEventType } from './realtime';

// DeepResearchAgent - Research with citations (Python parity enhanced)
export { DeepResearchAgent, createDeepResearchAgent } from './research';
export type {
  DeepResearchConfig,
  DeepResearchResponse,
  ResearchResponse,
  Citation,
  ReasoningStep,
  CodeExecutionStep,
  FileSearchCall,
  MCPCall,
  WebSearchCall,
  Provider,
} from './research';

// Router exports
export { Router, RouterAgent, createRouter, routeConditions } from './router';
export type { RouterConfig, RouteConfig, RouteContext, SimpleRouterConfig, SimpleRouteConfig } from './router';

// Task support (for advanced use cases)
export { Task } from './types';
export type { TaskConfig, AgentConfig as TaskAgentConfig } from './types';

// Legacy compatibility - setTaskMode is deprecated but kept for backward compat
let useTaskMode = false;

/**
 * @deprecated Task mode is no longer needed. Use Agent with role/goal/backstory instead.
 */
export function setTaskMode(enabled: boolean) {
  if (enabled) {
    console.warn(
      'setTaskMode() is deprecated. Use Agent({ role, goal, backstory }) instead of task mode.'
    );
  }
  useTaskMode = enabled;
}
