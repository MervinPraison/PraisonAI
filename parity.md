# Feature Parity Tracker

> **Version:** 1.5.5 | **Last Updated:** 2026-02-04
> **Source of Truth:** Python SDK (praisonaiagents)

## Summary

| Metric | Count |
|--------|-------|
| Python Core Features | 282 |
| Python Wrapper Features | 94 |
| TypeScript Features | 847 |
| **Gap Count** | **229** |
| P0 (Critical) | 29 |
| P1 (High) | 8 |
| P2 (Medium) | 29 |
| P3 (Low) | 163 |

## Gap Matrix

### P0_CoreParity (16 done, 29 todo)

| Feature | Python | TypeScript | Effort | Status |
|---------|--------|------------|--------|--------|
| `AudioConfig` | ✅ | ❌ | low | ⏳ TODO |
| `CodeAgent` | ✅ | ❌ | high | ⏳ TODO |
| `CodeConfig` | ✅ | ❌ | low | ⏳ TODO |
| `CodeExecutionStep` | ✅ | ❌ | high | ⏳ TODO |
| `ContextPolicy` | ✅ | ❌ | high | ⏳ TODO |
| `DeepResearchResponse` | ✅ | ❌ | high | ⏳ TODO |
| `EmbeddingAgent` | ✅ | ❌ | high | ⏳ TODO |
| `EmbeddingConfig` | ✅ | ❌ | low | ⏳ TODO |
| `FileSearchCall` | ✅ | ❌ | high | ⏳ TODO |
| `HandoffCycleError` | ✅ | ❌ | low | ⏳ TODO |
| `HandoffDepthError` | ✅ | ❌ | low | ⏳ TODO |
| `HandoffError` | ✅ | ❌ | low | ⏳ TODO |
| `HandoffInputData` | ✅ | ❌ | high | ⏳ TODO |
| `HandoffTimeoutError` | ✅ | ❌ | low | ⏳ TODO |
| `MCPCall` | ✅ | ❌ | high | ⏳ TODO |
| `OCRAgent` | ✅ | ❌ | high | ⏳ TODO |
| `OCRConfig` | ✅ | ❌ | low | ⏳ TODO |
| `Provider` | ✅ | ❌ | high | ⏳ TODO |
| `RECOMMENDED\_PROMPT\_PREFIX` | ✅ | ❌ | low | ⏳ TODO |
| `RealtimeAgent` | ✅ | ❌ | high | ⏳ TODO |
| `RealtimeConfig` | ✅ | ❌ | low | ⏳ TODO |
| `VideoAgent` | ✅ | ❌ | high | ⏳ TODO |
| `VideoConfig` | ✅ | ❌ | low | ⏳ TODO |
| `VisionAgent` | ✅ | ❌ | high | ⏳ TODO |
| `VisionConfig` | ✅ | ❌ | low | ⏳ TODO |
| `WebSearchCall` | ✅ | ❌ | high | ⏳ TODO |
| `create\_context\_agent` | ✅ | ❌ | low | ⏳ TODO |
| `handoff\_filters` | ✅ | ❌ | low | ⏳ TODO |
| `prompt\_with\_handoff\_instructions` | ✅ | ❌ | low | ⏳ TODO |
| `Agent` | ✅ | ✅ | high | ✅ DONE |
| `AudioAgent` | ✅ | ✅ | high | ✅ DONE |
| `ContextAgent` | ✅ | ✅ | high | ✅ DONE |
| `DeepResearchAgent` | ✅ | ✅ | high | ✅ DONE |
| `ExpandResult` | ✅ | ✅ | low | ✅ DONE |
| `ExpandStrategy` | ✅ | ✅ | high | ✅ DONE |
| `Handoff` | ✅ | ✅ | high | ✅ DONE |
| `HandoffConfig` | ✅ | ✅ | low | ✅ DONE |
| `HandoffResult` | ✅ | ✅ | low | ✅ DONE |
| `ImageAgent` | ✅ | ✅ | high | ✅ DONE |
| `PromptExpanderAgent` | ✅ | ✅ | high | ✅ DONE |
| `QueryRewriterAgent` | ✅ | ✅ | high | ✅ DONE |
| `ReasoningStep` | ✅ | ✅ | high | ✅ DONE |
| `RewriteResult` | ✅ | ✅ | low | ✅ DONE |
| `RewriteStrategy` | ✅ | ✅ | high | ✅ DONE |
| `handoff` | ✅ | ✅ | low | ✅ DONE |

### P1_Persistence (12 done, 8 todo)

| Feature | Python | TypeScript | Effort | Status |
|---------|--------|------------|--------|--------|
| `Chunking` | ✅ | ❌ | high | ⏳ TODO |
| `If` | ✅ | ❌ | high | ⏳ TODO |
| `Knowledge` | ✅ | ❌ | high | ⏳ TODO |
| `Loop` | ✅ | ❌ | high | ⏳ TODO |
| `Parallel` | ✅ | ❌ | high | ⏳ TODO |
| `Route` | ✅ | ❌ | high | ⏳ TODO |
| `Session` | ✅ | ❌ | high | ⏳ TODO |
| `when` | ✅ | ❌ | low | ⏳ TODO |
| `AgentFlow` | ✅ | ✅ | high | ✅ DONE |
| `Memory` | ✅ | ✅ | high | ✅ DONE |
| `Pipeline` | ✅ | ✅ | high | ✅ DONE |
| `Repeat` | ✅ | ✅ | high | ✅ DONE |
| `StepResult` | ✅ | ✅ | low | ✅ DONE |
| `Workflow` | ✅ | ✅ | high | ✅ DONE |
| `WorkflowContext` | ✅ | ✅ | high | ✅ DONE |
| `db` | ✅ | ✅ | low | ✅ DONE |
| `loop` | ✅ | ✅ | low | ✅ DONE |
| `parallel` | ✅ | ✅ | low | ✅ DONE |
| `repeat` | ✅ | ✅ | low | ✅ DONE |
| `route` | ✅ | ✅ | low | ✅ DONE |

### P2_CLI (12 done, 29 todo)

| Feature | Python | TypeScript | Effort | Status |
|---------|--------|------------|--------|--------|
| `ApprovalCallback` | ✅ | ❌ | high | ⏳ TODO |
| `CitationsMode` | ✅ | ❌ | high | ⏳ TODO |
| `ContextConfig` | ✅ | ❌ | low | ⏳ TODO |
| `ContextManager` | ✅ | ❌ | high | ⏳ TODO |
| `ContextPack` | ✅ | ❌ | high | ⏳ TODO |
| `FastContext` | ✅ | ❌ | high | ⏳ TODO |
| `FileMatch` | ✅ | ❌ | high | ⏳ TODO |
| `GuardrailResult` | ✅ | ❌ | low | ⏳ TODO |
| `LineRange` | ✅ | ❌ | high | ⏳ TODO |
| `MCP` | ✅ | ❌ | low | ⏳ TODO |
| `ManagerConfig` | ✅ | ❌ | low | ⏳ TODO |
| `MinimalTelemetry` | ✅ | ❌ | high | ⏳ TODO |
| `OptimizerStrategy` | ✅ | ❌ | high | ⏳ TODO |
| `RAG` | ✅ | ❌ | low | ⏳ TODO |
| `RAGCitation` | ✅ | ❌ | high | ⏳ TODO |
| `RAGConfig` | ✅ | ❌ | low | ⏳ TODO |
| `RAGResult` | ✅ | ❌ | low | ⏳ TODO |
| `READ\_ONLY\_TOOLS` | ✅ | ❌ | low | ⏳ TODO |
| `RESTRICTED\_TOOLS` | ✅ | ❌ | low | ⏳ TODO |
| `RetrievalConfig` | ✅ | ❌ | low | ⏳ TODO |
| `RetrievalPolicy` | ✅ | ❌ | high | ⏳ TODO |
| `SkillLoader` | ✅ | ❌ | high | ⏳ TODO |
| `SkillProperties` | ✅ | ❌ | high | ⏳ TODO |
| `cleanup\_telemetry\_resources` | ✅ | ❌ | low | ⏳ TODO |
| `disable\_performance\_mode` | ✅ | ❌ | low | ⏳ TODO |
| `disable\_telemetry` | ✅ | ❌ | low | ⏳ TODO |
| `enable\_performance\_mode` | ✅ | ❌ | low | ⏳ TODO |
| `enable\_telemetry` | ✅ | ❌ | low | ⏳ TODO |
| `get\_telemetry` | ✅ | ❌ | low | ⏳ TODO |
| `Citation` | ✅ | ✅ | high | ✅ DONE |
| `FastContextResult` | ✅ | ✅ | low | ✅ DONE |
| `LLMGuardrail` | ✅ | ✅ | high | ✅ DONE |
| `Plan` | ✅ | ✅ | high | ✅ DONE |
| `PlanStep` | ✅ | ✅ | high | ✅ DONE |
| `PlanStorage` | ✅ | ✅ | high | ✅ DONE |
| `PlanningAgent` | ✅ | ✅ | high | ✅ DONE |
| `SkillManager` | ✅ | ✅ | high | ✅ DONE |
| `SkillMetadata` | ✅ | ✅ | high | ✅ DONE |
| `TelemetryCollector` | ✅ | ✅ | high | ✅ DONE |
| `TodoItem` | ✅ | ✅ | high | ✅ DONE |
| `TodoList` | ✅ | ✅ | high | ✅ DONE |

### P3_Advanced (13 done, 163 todo)

| Feature | Python | TypeScript | Effort | Status |
|---------|--------|------------|--------|--------|
| `A2A` | ✅ | ❌ | low | ⏳ TODO |
| `AGUI` | ✅ | ❌ | low | ⏳ TODO |
| `AUTONOMY\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `AgentManager` | ✅ | ❌ | high | ⏳ TODO |
| `AgentPluginProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `ArrayMode` | ✅ | ❌ | high | ⏳ TODO |
| `AuthProfile` | ✅ | ❌ | high | ⏳ TODO |
| `AutoRagAgent` | ✅ | ❌ | high | ⏳ TODO |
| `AutoRagConfig` | ✅ | ❌ | low | ⏳ TODO |
| `AutonomyLevel` | ✅ | ❌ | high | ⏳ TODO |
| `BotChannel` | ✅ | ❌ | high | ⏳ TODO |
| `BotConfig` | ✅ | ❌ | low | ⏳ TODO |
| `BotMessage` | ✅ | ❌ | high | ⏳ TODO |
| `BotProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `BotUser` | ✅ | ❌ | high | ⏳ TODO |
| `CACHING\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `CONTEXT\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `CachingConfig` | ✅ | ❌ | low | ⏳ TODO |
| `ChunkingStrategy` | ✅ | ❌ | high | ⏳ TODO |
| `ConditionProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `ConfigValidationError` | ✅ | ❌ | low | ⏳ TODO |
| `ContextEvent` | ✅ | ❌ | high | ⏳ TODO |
| `ContextEventType` | ✅ | ❌ | high | ⏳ TODO |
| `ContextListSink` | ✅ | ❌ | high | ⏳ TODO |
| `ContextNoOpSink` | ✅ | ❌ | high | ⏳ TODO |
| `ContextTraceEmitter` | ✅ | ❌ | high | ⏳ TODO |
| `ContextTraceSink` | ✅ | ❌ | high | ⏳ TODO |
| `ContextTraceSinkProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `DefaultsConfig` | ✅ | ❌ | low | ⏳ TODO |
| `DictCondition` | ✅ | ❌ | high | ⏳ TODO |
| `EXECUTION\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `EmbeddingResult` | ✅ | ❌ | low | ⏳ TODO |
| `EventType` | ✅ | ❌ | high | ⏳ TODO |
| `ExecutionConfig` | ✅ | ❌ | low | ⏳ TODO |
| `ExecutionPreset` | ✅ | ❌ | high | ⏳ TODO |
| `ExpressionCondition` | ✅ | ❌ | high | ⏳ TODO |
| `FailoverConfig` | ✅ | ❌ | low | ⏳ TODO |
| `FailoverManager` | ✅ | ❌ | high | ⏳ TODO |
| `FlowDisplay` | ✅ | ❌ | high | ⏳ TODO |
| `FunctionPlugin` | ✅ | ❌ | high | ⏳ TODO |
| `GUARDRAIL\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `GatewayClientProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `GatewayConfig` | ✅ | ❌ | low | ⏳ TODO |
| `GatewayEvent` | ✅ | ❌ | high | ⏳ TODO |
| `GatewayMessage` | ✅ | ❌ | high | ⏳ TODO |
| `GatewayProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `GatewaySessionProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `GuardrailAction` | ✅ | ❌ | high | ⏳ TODO |
| `GuardrailConfig` | ✅ | ❌ | low | ⏳ TODO |
| `HookPluginProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `HooksConfig` | ✅ | ❌ | low | ⏳ TODO |
| `KNOWLEDGE\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `KnowledgeConfig` | ✅ | ❌ | low | ⏳ TODO |
| `LLMPluginProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `MEMORY\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `MEMORY\_URL\_SCHEMES` | ✅ | ❌ | low | ⏳ TODO |
| `MULTI\_AGENT\_EXECUTION\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `MULTI\_AGENT\_OUTPUT\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `MemoryBackend` | ✅ | ❌ | high | ⏳ TODO |
| `MessageType` | ✅ | ❌ | high | ⏳ TODO |
| `MultiAgentExecutionConfig` | ✅ | ❌ | low | ⏳ TODO |
| `MultiAgentHooksConfig` | ✅ | ❌ | low | ⏳ TODO |
| `MultiAgentMemoryConfig` | ✅ | ❌ | low | ⏳ TODO |
| `MultiAgentOutputConfig` | ✅ | ❌ | low | ⏳ TODO |
| `MultiAgentPlanningConfig` | ✅ | ❌ | low | ⏳ TODO |
| `OUTPUT\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `OutputConfig` | ✅ | ❌ | low | ⏳ TODO |
| `OutputPreset` | ✅ | ❌ | high | ⏳ TODO |
| `PLANNING\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `PlanningConfig` | ✅ | ❌ | low | ⏳ TODO |
| `Plugin` | ✅ | ❌ | high | ⏳ TODO |
| `PluginHook` | ✅ | ❌ | high | ⏳ TODO |
| `PluginInfo` | ✅ | ❌ | high | ⏳ TODO |
| `PluginManager` | ✅ | ❌ | high | ⏳ TODO |
| `PluginMetadata` | ✅ | ❌ | high | ⏳ TODO |
| `PluginParseError` | ✅ | ❌ | low | ⏳ TODO |
| `PluginProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `PluginsConfig` | ✅ | ❌ | low | ⏳ TODO |
| `PraisonConfig` | ✅ | ❌ | low | ⏳ TODO |
| `ProviderStatus` | ✅ | ❌ | high | ⏳ TODO |
| `REFLECTION\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `RagRetrievalPolicy` | ✅ | ❌ | high | ⏳ TODO |
| `ReflectionConfig` | ✅ | ❌ | low | ⏳ TODO |
| `ReflectionOutput` | ✅ | ❌ | high | ⏳ TODO |
| `ResourceLimits` | ✅ | ❌ | high | ⏳ TODO |
| `RoutingConditionProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `SandboxProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `SandboxResult` | ✅ | ❌ | low | ⏳ TODO |
| `SandboxStatus` | ✅ | ❌ | high | ⏳ TODO |
| `SessionConfig` | ✅ | ❌ | low | ⏳ TODO |
| `SkillsConfig` | ✅ | ❌ | low | ⏳ TODO |
| `Task` | ✅ | ❌ | high | ⏳ TODO |
| `TaskOutput` | ✅ | ❌ | high | ⏳ TODO |
| `TemplateConfig` | ✅ | ❌ | low | ⏳ TODO |
| `ToolPluginProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `Tools` | ✅ | ❌ | high | ⏳ TODO |
| `TraceSink` | ✅ | ❌ | high | ⏳ TODO |
| `TraceSinkProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `WEB\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `WebConfig` | ✅ | ❌ | low | ⏳ TODO |
| `WebSearchProvider` | ✅ | ❌ | high | ⏳ TODO |
| `aembed` | ✅ | ❌ | low | ⏳ TODO |
| `aembedding` | ✅ | ❌ | low | ⏳ TODO |
| `aembeddings` | ✅ | ❌ | low | ⏳ TODO |
| `apply\_config\_defaults` | ✅ | ❌ | low | ⏳ TODO |
| `async\_display\_callbacks` | ✅ | ❌ | low | ⏳ TODO |
| `clean\_triple\_backticks` | ✅ | ❌ | low | ⏳ TODO |
| `config` | ✅ | ❌ | low | ⏳ TODO |
| `detect\_url\_scheme` | ✅ | ❌ | low | ⏳ TODO |
| `discover\_and\_load\_plugins` | ✅ | ❌ | low | ⏳ TODO |
| `discover\_plugins` | ✅ | ❌ | low | ⏳ TODO |
| `display\_error` | ✅ | ❌ | low | ⏳ TODO |
| `display\_generating` | ✅ | ❌ | low | ⏳ TODO |
| `display\_instruction` | ✅ | ❌ | low | ⏳ TODO |
| `display\_interaction` | ✅ | ❌ | low | ⏳ TODO |
| `display\_self\_reflection` | ✅ | ❌ | low | ⏳ TODO |
| `display\_tool\_call` | ✅ | ❌ | low | ⏳ TODO |
| `embed` | ✅ | ❌ | low | ⏳ TODO |
| `embedding` | ✅ | ❌ | low | ⏳ TODO |
| `embeddings` | ✅ | ❌ | low | ⏳ TODO |
| `ensure\_plugin\_dir` | ✅ | ❌ | low | ⏳ TODO |
| `error\_logs` | ✅ | ❌ | low | ⏳ TODO |
| `evaluate\_condition` | ✅ | ❌ | low | ⏳ TODO |
| `get\_config` | ✅ | ❌ | low | ⏳ TODO |
| `get\_config\_path` | ✅ | ❌ | low | ⏳ TODO |
| `get\_default` | ✅ | ❌ | low | ⏳ TODO |
| `get\_default\_plugin\_dirs` | ✅ | ❌ | low | ⏳ TODO |
| `get\_defaults\_config` | ✅ | ❌ | low | ⏳ TODO |
| `get\_dimensions` | ✅ | ❌ | low | ⏳ TODO |
| `get\_plugin\_manager` | ✅ | ❌ | low | ⏳ TODO |
| `get\_plugin\_template` | ✅ | ❌ | low | ⏳ TODO |
| `get\_plugins\_config` | ✅ | ❌ | low | ⏳ TODO |
| `is\_path\_like` | ✅ | ❌ | low | ⏳ TODO |
| `is\_policy\_string` | ✅ | ❌ | low | ⏳ TODO |
| `load\_plugin` | ✅ | ❌ | low | ⏳ TODO |
| `memory` | ✅ | ❌ | low | ⏳ TODO |
| `obs` | ✅ | ❌ | low | ⏳ TODO |
| `parse\_plugin\_header` | ✅ | ❌ | low | ⏳ TODO |
| `parse\_plugin\_header\_from\_file` | ✅ | ❌ | low | ⏳ TODO |
| `parse\_policy\_string` | ✅ | ❌ | low | ⏳ TODO |
| `register\_display\_callback` | ✅ | ❌ | low | ⏳ TODO |
| `resolve` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_autonomy` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_caching` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_context` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_execution` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_guardrail\_policies` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_guardrails` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_hooks` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_knowledge` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_memory` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_output` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_planning` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_reflection` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_routing` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_skills` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_web` | ✅ | ❌ | low | ⏳ TODO |
| `suggest\_similar` | ✅ | ❌ | low | ⏳ TODO |
| `sync\_display\_callbacks` | ✅ | ❌ | low | ⏳ TODO |
| `trace\_context` | ✅ | ❌ | low | ⏳ TODO |
| `track\_workflow` | ✅ | ❌ | low | ⏳ TODO |
| `validate\_config` | ✅ | ❌ | low | ⏳ TODO |
| `workflows` | ✅ | ❌ | low | ⏳ TODO |
| `AgentAppConfig` | ✅ | ✅ | low | ✅ DONE |
| `AgentAppProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `AgentOSConfig` | ✅ | ✅ | low | ✅ DONE |
| `AgentOSProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `AgentTeam` | ✅ | ✅ | high | ✅ DONE |
| `Agents` | ✅ | ✅ | high | ✅ DONE |
| `AutoAgents` | ✅ | ✅ | high | ✅ DONE |
| `AutonomyConfig` | ✅ | ✅ | low | ✅ DONE |
| `MemoryConfig` | ✅ | ✅ | low | ✅ DONE |
| `SandboxConfig` | ✅ | ✅ | low | ✅ DONE |
| `SecurityPolicy` | ✅ | ✅ | high | ✅ DONE |
| `tool` | ✅ | ✅ | low | ✅ DONE |
| `tools` | ✅ | ✅ | low | ✅ DONE |

## Python Core SDK Exports

**Path:** `/Users/praison/praisonai-package/src/praisonai-agents/praisonaiagents`

<details>
<summary><strong>agent</strong> (45 exports)</summary>

```python
from praisonaiagents import Agent, AudioAgent, AudioConfig, CodeAgent, CodeConfig, CodeExecutionStep, ContextAgent, ContextPolicy, DeepResearchAgent, DeepResearchResponse...
```

</details>

<details>
<summary><strong>agents</strong> (6 exports)</summary>

```python
from praisonaiagents import AgentManager, AgentTeam, AutoAgents, AutoRagAgent, AutoRagConfig, RagRetrievalPolicy
```

</details>

<details>
<summary><strong>app</strong> (4 exports)</summary>

```python
from praisonaiagents import AgentAppConfig, AgentAppProtocol, AgentOSConfig, AgentOSProtocol
```

</details>

<details>
<summary><strong>bots</strong> (6 exports)</summary>

```python
from praisonaiagents import BotChannel, BotConfig, BotMessage, BotProtocol, BotUser, MessageType
```

</details>

<details>
<summary><strong>conditions</strong> (5 exports)</summary>

```python
from praisonaiagents import ConditionProtocol, DictCondition, ExpressionCondition, RoutingConditionProtocol, evaluate_condition
```

</details>

<details>
<summary><strong>config</strong> (72 exports)</summary>

```python
from praisonaiagents import AUTONOMY_PRESETS, ArrayMode, AutonomyConfig, AutonomyLevel, CACHING_PRESETS, CONTEXT_PRESETS, CachingConfig, ChunkingStrategy, ConfigValidationError, DefaultsConfig...
```

</details>

<details>
<summary><strong>context</strong> (8 exports)</summary>

```python
from praisonaiagents import ContextConfig, ContextManager, FastContext, FastContextResult, FileMatch, LineRange, ManagerConfig, OptimizerStrategy
```

</details>

<details>
<summary><strong>db</strong> (1 exports)</summary>

```python
from praisonaiagents import db
```

</details>

<details>
<summary><strong>embedding</strong> (8 exports)</summary>

```python
from praisonaiagents import EmbeddingResult, aembed, aembedding, aembeddings, embed, embedding, embeddings, get_dimensions
```

</details>

<details>
<summary><strong>flow_display</strong> (2 exports)</summary>

```python
from praisonaiagents import FlowDisplay, track_workflow
```

</details>

<details>
<summary><strong>gateway</strong> (8 exports)</summary>

```python
from praisonaiagents import EventType, GatewayClientProtocol, GatewayConfig, GatewayEvent, GatewayMessage, GatewayProtocol, GatewaySessionProtocol, SessionConfig
```

</details>

<details>
<summary><strong>guardrails</strong> (2 exports)</summary>

```python
from praisonaiagents import GuardrailResult, LLMGuardrail
```

</details>

<details>
<summary><strong>knowledge</strong> (2 exports)</summary>

```python
from praisonaiagents import Chunking, Knowledge
```

</details>

<details>
<summary><strong>llm</strong> (4 exports)</summary>

```python
from praisonaiagents import AuthProfile, FailoverConfig, FailoverManager, ProviderStatus
```

</details>

<details>
<summary><strong>main</strong> (13 exports)</summary>

```python
from praisonaiagents import ReflectionOutput, TaskOutput, async_display_callbacks, clean_triple_backticks, display_error, display_generating, display_instruction, display_interaction, display_self_reflection, display_tool_call...
```

</details>

<details>
<summary><strong>mcp</strong> (1 exports)</summary>

```python
from praisonaiagents import MCP
```

</details>

<details>
<summary><strong>memory</strong> (1 exports)</summary>

```python
from praisonaiagents import Memory
```

</details>

<details>
<summary><strong>obs</strong> (1 exports)</summary>

```python
from praisonaiagents import obs
```

</details>

<details>
<summary><strong>other</strong> (7 exports)</summary>

```python
from praisonaiagents import Agents, Tools, config, memory, tool, tools, workflows
```

</details>

<details>
<summary><strong>planning</strong> (9 exports)</summary>

```python
from praisonaiagents import ApprovalCallback, Plan, PlanStep, PlanStorage, PlanningAgent, READ_ONLY_TOOLS, RESTRICTED_TOOLS, TodoItem, TodoList
```

</details>

<details>
<summary><strong>plugins</strong> (21 exports)</summary>

```python
from praisonaiagents import AgentPluginProtocol, FunctionPlugin, HookPluginProtocol, LLMPluginProtocol, Plugin, PluginHook, PluginInfo, PluginManager, PluginMetadata, PluginParseError...
```

</details>

<details>
<summary><strong>rag</strong> (9 exports)</summary>

```python
from praisonaiagents import Citation, CitationsMode, ContextPack, RAG, RAGCitation, RAGConfig, RAGResult, RetrievalConfig, RetrievalPolicy
```

</details>

<details>
<summary><strong>sandbox</strong> (6 exports)</summary>

```python
from praisonaiagents import ResourceLimits, SandboxConfig, SandboxProtocol, SandboxResult, SandboxStatus, SecurityPolicy
```

</details>

<details>
<summary><strong>session</strong> (1 exports)</summary>

```python
from praisonaiagents import Session
```

</details>

<details>
<summary><strong>skills</strong> (4 exports)</summary>

```python
from praisonaiagents import SkillLoader, SkillManager, SkillMetadata, SkillProperties
```

</details>

<details>
<summary><strong>task</strong> (1 exports)</summary>

```python
from praisonaiagents import Task
```

</details>

<details>
<summary><strong>telemetry</strong> (8 exports)</summary>

```python
from praisonaiagents import MinimalTelemetry, TelemetryCollector, cleanup_telemetry_resources, disable_performance_mode, disable_telemetry, enable_performance_mode, enable_telemetry, get_telemetry
```

</details>

<details>
<summary><strong>trace</strong> (10 exports)</summary>

```python
from praisonaiagents import ContextEvent, ContextEventType, ContextListSink, ContextNoOpSink, ContextTraceEmitter, ContextTraceSink, ContextTraceSinkProtocol, TraceSink, TraceSinkProtocol, trace_context
```

</details>

<details>
<summary><strong>ui</strong> (2 exports)</summary>

```python
from praisonaiagents import A2A, AGUI
```

</details>

<details>
<summary><strong>workflows</strong> (15 exports)</summary>

```python
from praisonaiagents import AgentFlow, If, Loop, Parallel, Pipeline, Repeat, Route, StepResult, Workflow, WorkflowContext...
```

</details>

## TypeScript SDK Exports

**Path:** `/Users/praison/praisonai-package/src/praisonai-ts/src`

<details>
<summary><strong>agent</strong> (55 exports)</summary>

```typescript
import { Agent, AgentTeam, AgentTeamConfig, Agents, AudioAgent, AudioAgentConfig, AudioProvider, AudioSpeakOptions, AudioSpeakResult, AudioTranscribeOptions... } from 'praisonai';
```

</details>

<details>
<summary><strong>ai</strong> (166 exports)</summary>

```typescript
import { // Agent loop
  createAgentLoop, // DevTools
  enableDevTools, // MCP
  createMCP, // Middleware (renamed to avoid conflicts)
  createCachingMiddleware, // Models
  createModel, // Multimodal
  createImagePart, // Next.js
  createRouteHandler, // OAuth for MCP
  OAuthClientProvider, // Server adapters
  createHttpHandler, // Speech & Transcription
  generateSpeech... } from 'praisonai';
```

</details>

<details>
<summary><strong>auto</strong> (6 exports)</summary>

```typescript
import { AgentConfig, AutoAgents, AutoAgentsConfig, AutoTaskConfig, TeamStructure, createAutoAgents } from 'praisonai';
```

</details>

<details>
<summary><strong>cache</strong> (7 exports)</summary>

```typescript
import { BaseCache, CacheConfig, CacheEntry, FileCache, MemoryCache, createFileCache, createMemoryCache } from 'praisonai';
```

</details>

<details>
<summary><strong>cli</strong> (121 exports)</summary>

```typescript
import { // Autonomy Mode
  AutonomyManager, // Background Jobs
  JobQueue, // Checkpoints
  CheckpointManager, // Cost Tracker
  CostTracker, // External Agents
  BaseExternalAgent, // Fast Context
  FastContext, // Flow Display
  FlowDisplay, // Git Integration
  GitManager, // Interactive TUI
  InteractiveTUI, // N8N Integration
  N8NIntegration... } from 'praisonai';
```

</details>

<details>
<summary><strong>db</strong> (26 exports)</summary>

```typescript
import { DbAdapter, DbConfig, DbMessage, DbRun, DbTrace, MemoryPostgresAdapter, MemoryRedisAdapter, NeonPostgresAdapter, PostgresAdapter, PostgresConfig... } from 'praisonai';
```

</details>

<details>
<summary><strong>eval</strong> (40 exports)</summary>

```typescript
import { // LLM-as-Judge
  Judge, AccuracyEvalConfig, AccuracyJudge, AggregatedResults, CriteriaJudge, EvalCriteria, EvalResult, EvalResults, EvalSuite, Evaluator... } from 'praisonai';
```

</details>

<details>
<summary><strong>events</strong> (8 exports)</summary>

```typescript
import { AgentEventBus, AgentEvents, Event, EventEmitterPubSub, EventHandler, PubSub, createEventBus, createPubSub } from 'praisonai';
```

</details>

<details>
<summary><strong>guardrails</strong> (4 exports)</summary>

```typescript
import { LLMGuardrail, LLMGuardrailConfig, LLMGuardrailResult, createLLMGuardrail } from 'praisonai';
```

</details>

<details>
<summary><strong>hooks</strong> (33 exports)</summary>

```typescript
import { ApprovalCallbackFn, ApprovalDecision, ApprovalRequest, DisplayCallbackData, DisplayCallbackFn, DisplayType, DisplayTypes, HookConfig, HookEvent, HookHandler... } from 'praisonai';
```

</details>

<details>
<summary><strong>integrations</strong> (58 exports)</summary>

```typescript
import { // Computer Use
  createComputerUse, // Natural Language Postgres
  createNLPostgres, // Slack
  createSlackBot, BaseObservabilityProvider, BaseVectorStore, BaseVoiceProvider, ChromaVectorStore, ColumnSchema, ComputerAction, ComputerUseClient... } from 'praisonai';
```

</details>

<details>
<summary><strong>knowledge</strong> (16 exports)</summary>

```typescript
import { BaseReranker, CohereReranker, CrossEncoderReranker, GraphEdge, GraphNode, GraphQueryResult, GraphRAG, GraphRAGConfig, GraphStore, LLMReranker... } from 'praisonai';
```

</details>

<details>
<summary><strong>llm</strong> (44 exports)</summary>

```typescript
import { // Provider classes
  OpenAIProvider, // Provider factory and utilities
  createProvider, // Provider registry (extensibility API)
  ProviderRegistry, // Types
  LLMProvider, ADAPTERS, AISDK_PROVIDERS, AdapterInfo, AnthropicProvider, BaseProvider, COMMUNITY_PROVIDERS... } from 'praisonai';
```

</details>

<details>
<summary><strong>mcp</strong> (18 exports)</summary>

```typescript
import { MCPClient, MCPClientConfig, MCPSecurity, MCPServer, MCPServerConfig, MCPServerTool, MCPSession, MCPSessionManager, MCPTransportType, SecurityPolicy... } from 'praisonai';
```

</details>

<details>
<summary><strong>memory</strong> (47 exports)</summary>

```typescript
import { AfterDeleteHook, AfterRetrieveHook, AfterSearchHook, AfterStoreHook, AutoMemory, AutoMemoryConfig, AutoMemoryContext, AutoMemoryKnowledgeBase, AutoMemoryPolicy, AutoMemoryVectorStore... } from 'praisonai';
```

</details>

<details>
<summary><strong>observability</strong> (29 exports)</summary>

```typescript
import { // Adapters
  NoopObservabilityAdapter, // Constants
  OBSERVABILITY_TOOLS, // Global adapter management
  setObservabilityAdapter, // Types
  SpanKind, AttributionContext, ConsoleObservabilityAdapter, MemoryObservabilityAdapter, ObservabilityAdapter, ObservabilityToolConfig, ObservabilityToolInfo... } from 'praisonai';
```

</details>

<details>
<summary><strong>os</strong> (10 exports)</summary>

```typescript
import { AgentApp, AgentAppConfig, AgentAppOptions, AgentAppProtocol, AgentOS, AgentOSConfig, AgentOSOptions, AgentOSProtocol, DEFAULT_AGENTOS_CONFIG, mergeConfig } from 'praisonai';
```

</details>

<details>
<summary><strong>planning</strong> (19 exports)</summary>

```typescript
import { Plan, PlanConfig, PlanResult, PlanStatus, PlanStep, PlanStepConfig, PlanStorage, PlanningAgent, PlanningAgentConfig, TaskAgent... } from 'praisonai';
```

</details>

<details>
<summary><strong>skills</strong> (6 exports)</summary>

```typescript
import { Skill, SkillDiscoveryOptions, SkillManager, SkillMetadata, createSkillManager, parseSkillFile } from 'praisonai';
```

</details>

<details>
<summary><strong>telemetry</strong> (21 exports)</summary>

```typescript
import { AgentStats, AgentTelemetry, MetricEntry, PerformanceMonitor, PerformanceMonitorConfig, PerformanceStats, TelemetryCollector, TelemetryConfig, TelemetryEvent, TelemetryIntegration... } from 'praisonai';
```

</details>

<details>
<summary><strong>tools</strong> (82 exports)</summary>

```typescript
import { // Subagent Tool (agent-as-tool pattern)
  SubagentTool, BaseTool, DelegatorConfig, FunctionTool, InstallHints, MissingDependencyError, MissingEnvVarError, PraisonTool, RedactionHooks, RegisteredTool... } from 'praisonai';
```

</details>

<details>
<summary><strong>workflows</strong> (31 exports)</summary>

```typescript
import { // New: Python-parity Loop and Repeat classes
  Loop, // Task class
  Task, AgentFlow, LoopConfig, LoopResult, ParsedWorkflow, Pipeline, Repeat, RepeatConfig, RepeatContext... } from 'praisonai';
```

</details>

---

*Generated by `praisonai._dev.parity.generator`*
