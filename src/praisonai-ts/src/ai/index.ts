/**
 * AI SDK Wrapper Module
 * 
 * This module provides a stable wrapper over the AI SDK (aisdk) primitives.
 * It isolates aisdk imports and provides typed wrappers to ensure future
 * aisdk upgrades don't break praisonai-ts users.
 * 
 * @module ai
 */

// Re-export core execution functions
export {
  generateText,
  streamText,
  type GenerateTextOptions,
  type GenerateTextResult,
  type StreamTextOptions,
  type StreamTextResult,
  type TextStreamPart,
} from './generate-text';

export {
  generateObject,
  streamObject,
  type GenerateObjectOptions,
  type GenerateObjectResult,
  type StreamObjectOptions,
  type StreamObjectResult,
} from './generate-object';

export {
  generateImage,
  type GenerateImageOptions,
  type GenerateImageResult,
} from './generate-image';

export {
  embed,
  embedMany,
  type EmbedOptions,
  type EmbedResult,
  type EmbedManyResult,
} from './embed';

// Re-export tool utilities
export {
  defineTool,
  createToolSet,
  functionToTool,
  type ToolDefinition,
  type ToolExecuteFunction,
  type ToolInput,
  type ToolOutput,
} from './tools';

// Re-export model utilities
export {
  createModel,
  getModel,
  parseModel,
  MODEL_ALIASES,
  listModelAliases,
  hasModelAlias,
  resolveModelAlias,
  type ModelConfig,
  type ModelId,
} from './models';

// Re-export middleware
export {
  createCachingMiddleware,
  createLoggingMiddleware,
  wrapModel,
  applyMiddleware,
  clearCache,
  getCacheStats,
  type Middleware,
  type MiddlewareConfig,
  type MiddlewareRequest,
  type MiddlewareResponse,
} from './middleware';

// Re-export multimodal utilities
export {
  createImagePart,
  createFilePart,
  createPdfPart,
  createTextPart,
  createMultimodalMessage,
  toMessageContent,
  base64ToUint8Array,
  uint8ArrayToBase64,
  isUrl,
  isDataUrl,
  type InputPart,
  type ImagePart,
  type FilePart,
  type PdfPart,
  type TextPart,
} from './multimodal';

// Re-export MCP client
export {
  createMCP,
  getMCPClient,
  closeMCPClient,
  closeAllMCPClients,
  mcpToolsToAITools,
  type MCPConfig,
  type MCPClient,
  type MCPTool,
  type MCPResource,
  type MCPPrompt,
} from './mcp';

// Re-export server adapters
export {
  createHttpHandler,
  createExpressHandler,
  createHonoHandler,
  createFastifyHandler,
  createNestHandler,
  type ServerHandler,
  type ServerHandlerConfig,
} from './server';

// Re-export React/Next.js utilities (lazy loaded)
export {
  createRouteHandler,
  createPagesHandler,
  type RouteHandlerConfig,
  type UseChatConfig,
} from './nextjs';

// Re-export agent loop utilities
export {
  createAgentLoop,
  AgentLoop,
  stopAfterSteps,
  stopWhenNoToolCalls,
  stopWhen,
  type AgentLoopConfig,
  type AgentStep,
  type AgentLoopResult,
  type StopCondition,
} from './agent-loop';

// Re-export UI message utilities
export {
  convertToModelMessages,
  convertToUIMessages,
  validateUIMessages,
  safeValidateUIMessages,
  createTextMessage,
  createSystemMessage,
  hasPendingApprovals,
  getToolsNeedingApproval,
  createApprovalResponse,
  toUIMessageStreamResponse,
  pipeUIMessageStreamToResponse,
  type UIMessage,
  type UIMessagePart,
  type TextUIPart,
  type ReasoningUIPart,
  type ToolUIPart,
  type FileUIPart,
  type DataUIPart,
  type ModelMessage,
  type UIMessageStreamOptions,
} from './ui-message';

// Re-export tool approval utilities
export {
  ApprovalManager,
  getApprovalManager,
  setApprovalManager,
  withApproval,
  createCLIApprovalPrompt,
  ToolApprovalDeniedError,
  ToolApprovalTimeoutError,
  DANGEROUS_PATTERNS,
  isDangerous,
  createDangerousPatternChecker,
  type ToolApprovalConfig,
  type ToolApprovalRequest,
  type ToolApprovalResponse,
  type ApprovalState,
  type ApprovalHandler,
} from './tool-approval';

// Re-export speech and transcription
export {
  generateSpeech,
  transcribe,
  SPEECH_MODELS,
  TRANSCRIPTION_MODELS,
  type GenerateSpeechOptions,
  type GenerateSpeechResult,
  type TranscribeOptions,
  type TranscribeResult,
  type TranscriptionSegment,
} from './speech';

// Re-export DevTools
export {
  enableDevTools,
  disableDevTools,
  isDevToolsEnabled,
  getDevToolsState,
  getDevToolsUrl,
  createDevToolsMiddleware,
  autoEnableDevTools,
  type DevToolsConfig,
  type DevToolsState,
} from './devtools';

// Re-export OAuth provider for MCP
export type { OAuthClientProvider } from './mcp';

// Re-export telemetry utilities
export {
  configureTelemetry,
  getTelemetrySettings,
  enableTelemetry as enableAITelemetry,
  disableTelemetry as disableAITelemetry,
  isTelemetryEnabled,
  initOpenTelemetry,
  getTracer,
  createAISpan,
  withSpan,
  createTelemetryMiddleware,
  recordEvent,
  getEvents,
  clearEvents,
  createTelemetrySettings,
  type TelemetrySettings,
  type Tracer,
  type Span,
  type SpanOptions,
  type SpanKind,
  type SpanStatus,
  type TelemetryEvent,
} from './telemetry';
