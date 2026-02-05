# Feature Parity Tracker

> **Version:** 1.5.5 | **Last Updated:** 2026-02-05
> **Source of Truth:** Python SDK (praisonaiagents)

## Summary

| Metric | Count |
|--------|-------|
| Python Core Features | 282 |
| Python Wrapper Features | 94 |
<<<<<<< Updated upstream
| TypeScript Features | 1118 |
| **Gap Count** | **97** |
| P0 (Critical) | 21 |
| P1 (High) | 8 |
| P2 (Medium) | 19 |
| P3 (Low) | 49 |
=======
| TypeScript Features | 1183 |
| **Gap Count** | **0** |
| P0 (Critical) | 0 |
| P1 (High) | 0 |
| P2 (Medium) | 0 |
| P3 (Low) | 0 |
>>>>>>> Stashed changes

## Gap Matrix

### P0_CoreParity (24 done, 21 todo)

| Feature | Python | TypeScript | Effort | Status |
|---------|--------|------------|--------|--------|
<<<<<<< Updated upstream
| `AudioConfig` | ✅ | ❌ | low | ⏳ TODO |
| `CodeAgent` | ✅ | ❌ | high | ⏳ TODO |
| `CodeConfig` | ✅ | ❌ | low | ⏳ TODO |
| `CodeExecutionStep` | ✅ | ❌ | high | ⏳ TODO |
| `DeepResearchResponse` | ✅ | ❌ | high | ⏳ TODO |
| `EmbeddingAgent` | ✅ | ❌ | high | ⏳ TODO |
| `FileSearchCall` | ✅ | ❌ | high | ⏳ TODO |
| `MCPCall` | ✅ | ❌ | high | ⏳ TODO |
| `OCRAgent` | ✅ | ❌ | high | ⏳ TODO |
| `OCRConfig` | ✅ | ❌ | low | ⏳ TODO |
| `Provider` | ✅ | ❌ | high | ⏳ TODO |
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
| `ContextPolicy` | ✅ | ✅ | high | ✅ DONE |
| `DeepResearchAgent` | ✅ | ✅ | high | ✅ DONE |
| `EmbeddingConfig` | ✅ | ✅ | low | ✅ DONE |
| `ExpandResult` | ✅ | ✅ | low | ✅ DONE |
| `ExpandStrategy` | ✅ | ✅ | high | ✅ DONE |
=======
| `Agent` | ✅ | ✅ | high | ✅ DONE |
| `AudioAgent` | ✅ | ✅ | high | ✅ DONE |
| `AudioConfig` | ✅ | ✅ | low | ✅ DONE |
| `CodeAgent` | ✅ | ✅ | high | ✅ DONE |
| `CodeConfig` | ✅ | ✅ | low | ✅ DONE |
| `CodeExecutionStep` | ✅ | ✅ | high | ✅ DONE |
| `ContextAgent` | ✅ | ✅ | high | ✅ DONE |
| `ContextPolicy` | ✅ | ✅ | high | ✅ DONE |
| `DeepResearchAgent` | ✅ | ✅ | high | ✅ DONE |
| `DeepResearchResponse` | ✅ | ✅ | high | ✅ DONE |
| `EmbeddingAgent` | ✅ | ✅ | high | ✅ DONE |
| `EmbeddingConfig` | ✅ | ✅ | low | ✅ DONE |
| `ExpandResult` | ✅ | ✅ | low | ✅ DONE |
| `ExpandStrategy` | ✅ | ✅ | high | ✅ DONE |
| `FileSearchCall` | ✅ | ✅ | high | ✅ DONE |
>>>>>>> Stashed changes
| `Handoff` | ✅ | ✅ | high | ✅ DONE |
| `HandoffConfig` | ✅ | ✅ | low | ✅ DONE |
| `HandoffCycleError` | ✅ | ✅ | low | ✅ DONE |
| `HandoffDepthError` | ✅ | ✅ | low | ✅ DONE |
| `HandoffError` | ✅ | ✅ | low | ✅ DONE |
| `HandoffInputData` | ✅ | ✅ | high | ✅ DONE |
| `HandoffResult` | ✅ | ✅ | low | ✅ DONE |
| `HandoffTimeoutError` | ✅ | ✅ | low | ✅ DONE |
| `ImageAgent` | ✅ | ✅ | high | ✅ DONE |
<<<<<<< Updated upstream
| `PromptExpanderAgent` | ✅ | ✅ | high | ✅ DONE |
| `QueryRewriterAgent` | ✅ | ✅ | high | ✅ DONE |
| `RECOMMENDED\_PROMPT\_PREFIX` | ✅ | ✅ | low | ✅ DONE |
| `ReasoningStep` | ✅ | ✅ | high | ✅ DONE |
| `RewriteResult` | ✅ | ✅ | low | ✅ DONE |
| `RewriteStrategy` | ✅ | ✅ | high | ✅ DONE |
=======
| `MCPCall` | ✅ | ✅ | high | ✅ DONE |
| `OCRAgent` | ✅ | ✅ | high | ✅ DONE |
| `OCRConfig` | ✅ | ✅ | low | ✅ DONE |
| `PromptExpanderAgent` | ✅ | ✅ | high | ✅ DONE |
| `Provider` | ✅ | ✅ | high | ✅ DONE |
| `QueryRewriterAgent` | ✅ | ✅ | high | ✅ DONE |
| `RECOMMENDED\_PROMPT\_PREFIX` | ✅ | ✅ | low | ✅ DONE |
| `RealtimeAgent` | ✅ | ✅ | high | ✅ DONE |
| `RealtimeConfig` | ✅ | ✅ | low | ✅ DONE |
| `ReasoningStep` | ✅ | ✅ | high | ✅ DONE |
| `RewriteResult` | ✅ | ✅ | low | ✅ DONE |
| `RewriteStrategy` | ✅ | ✅ | high | ✅ DONE |
| `VideoAgent` | ✅ | ✅ | high | ✅ DONE |
| `VideoConfig` | ✅ | ✅ | low | ✅ DONE |
| `VisionAgent` | ✅ | ✅ | high | ✅ DONE |
| `VisionConfig` | ✅ | ✅ | low | ✅ DONE |
| `WebSearchCall` | ✅ | ✅ | high | ✅ DONE |
| `create\_context\_agent` | ✅ | ✅ | low | ✅ DONE |
>>>>>>> Stashed changes
| `handoff` | ✅ | ✅ | low | ✅ DONE |
| `handoff\_filters` | ✅ | ✅ | low | ✅ DONE |
| `prompt\_with\_handoff\_instructions` | ✅ | ✅ | low | ✅ DONE |

### P1_Persistence (12 done, 8 todo)

| Feature | Python | TypeScript | Effort | Status |
|---------|--------|------------|--------|--------|
<<<<<<< Updated upstream
| `Chunking` | ✅ | ❌ | high | ⏳ TODO |
| `If` | ✅ | ❌ | high | ⏳ TODO |
| `Knowledge` | ✅ | ❌ | high | ⏳ TODO |
| `Loop` | ✅ | ❌ | high | ⏳ TODO |
| `Parallel` | ✅ | ❌ | high | ⏳ TODO |
| `Route` | ✅ | ❌ | high | ⏳ TODO |
| `Session` | ✅ | ❌ | high | ⏳ TODO |
| `when` | ✅ | ❌ | low | ⏳ TODO |
| `AgentFlow` | ✅ | ✅ | high | ✅ DONE |
=======
| `AgentFlow` | ✅ | ✅ | high | ✅ DONE |
| `Chunking` | ✅ | ✅ | high | ✅ DONE |
| `If` | ✅ | ✅ | high | ✅ DONE |
| `Knowledge` | ✅ | ✅ | high | ✅ DONE |
| `Loop` | ✅ | ✅ | high | ✅ DONE |
>>>>>>> Stashed changes
| `Memory` | ✅ | ✅ | high | ✅ DONE |
| `Parallel` | ✅ | ✅ | high | ✅ DONE |
| `Pipeline` | ✅ | ✅ | high | ✅ DONE |
| `Repeat` | ✅ | ✅ | high | ✅ DONE |
| `Route` | ✅ | ✅ | high | ✅ DONE |
| `Session` | ✅ | ✅ | high | ✅ DONE |
| `StepResult` | ✅ | ✅ | low | ✅ DONE |
| `Workflow` | ✅ | ✅ | high | ✅ DONE |
| `WorkflowContext` | ✅ | ✅ | high | ✅ DONE |
| `db` | ✅ | ✅ | low | ✅ DONE |
| `loop` | ✅ | ✅ | low | ✅ DONE |
| `parallel` | ✅ | ✅ | low | ✅ DONE |
| `repeat` | ✅ | ✅ | low | ✅ DONE |
| `route` | ✅ | ✅ | low | ✅ DONE |
| `when` | ✅ | ✅ | low | ✅ DONE |

### P2_CLI (22 done, 19 todo)

| Feature | Python | TypeScript | Effort | Status |
|---------|--------|------------|--------|--------|
<<<<<<< Updated upstream
| `ApprovalCallback` | ✅ | ❌ | high | ⏳ TODO |
| `ContextConfig` | ✅ | ❌ | low | ⏳ TODO |
| `ContextManager` | ✅ | ❌ | high | ⏳ TODO |
| `ContextPack` | ✅ | ❌ | high | ⏳ TODO |
| `FastContext` | ✅ | ❌ | high | ⏳ TODO |
| `GuardrailResult` | ✅ | ❌ | low | ⏳ TODO |
| `LineRange` | ✅ | ❌ | high | ⏳ TODO |
| `MCP` | ✅ | ❌ | low | ⏳ TODO |
| `ManagerConfig` | ✅ | ❌ | low | ⏳ TODO |
| `MinimalTelemetry` | ✅ | ❌ | high | ⏳ TODO |
| `OptimizerStrategy` | ✅ | ❌ | high | ⏳ TODO |
| `Plan` | ✅ | ❌ | high | ⏳ TODO |
| `SkillLoader` | ✅ | ❌ | high | ⏳ TODO |
| `cleanup\_telemetry\_resources` | ✅ | ❌ | low | ⏳ TODO |
| `disable\_performance\_mode` | ✅ | ❌ | low | ⏳ TODO |
| `disable\_telemetry` | ✅ | ❌ | low | ⏳ TODO |
| `enable\_performance\_mode` | ✅ | ❌ | low | ⏳ TODO |
| `enable\_telemetry` | ✅ | ❌ | low | ⏳ TODO |
| `get\_telemetry` | ✅ | ❌ | low | ⏳ TODO |
| `Citation` | ✅ | ✅ | high | ✅ DONE |
| `CitationsMode` | ✅ | ✅ | high | ✅ DONE |
| `FastContextResult` | ✅ | ✅ | low | ✅ DONE |
| `FileMatch` | ✅ | ✅ | high | ✅ DONE |
| `LLMGuardrail` | ✅ | ✅ | high | ✅ DONE |
=======
| `ApprovalCallback` | ✅ | ✅ | high | ✅ DONE |
| `Citation` | ✅ | ✅ | high | ✅ DONE |
| `CitationsMode` | ✅ | ✅ | high | ✅ DONE |
| `ContextConfig` | ✅ | ✅ | low | ✅ DONE |
| `ContextManager` | ✅ | ✅ | high | ✅ DONE |
| `ContextPack` | ✅ | ✅ | high | ✅ DONE |
| `FastContext` | ✅ | ✅ | high | ✅ DONE |
| `FastContextResult` | ✅ | ✅ | low | ✅ DONE |
| `FileMatch` | ✅ | ✅ | high | ✅ DONE |
| `GuardrailResult` | ✅ | ✅ | low | ✅ DONE |
| `LLMGuardrail` | ✅ | ✅ | high | ✅ DONE |
| `LineRange` | ✅ | ✅ | high | ✅ DONE |
| `MCP` | ✅ | ✅ | low | ✅ DONE |
| `ManagerConfig` | ✅ | ✅ | low | ✅ DONE |
| `MinimalTelemetry` | ✅ | ✅ | high | ✅ DONE |
| `OptimizerStrategy` | ✅ | ✅ | high | ✅ DONE |
| `Plan` | ✅ | ✅ | high | ✅ DONE |
>>>>>>> Stashed changes
| `PlanStep` | ✅ | ✅ | high | ✅ DONE |
| `PlanStorage` | ✅ | ✅ | high | ✅ DONE |
| `PlanningAgent` | ✅ | ✅ | high | ✅ DONE |
| `RAG` | ✅ | ✅ | low | ✅ DONE |
| `RAGCitation` | ✅ | ✅ | high | ✅ DONE |
| `RAGConfig` | ✅ | ✅ | low | ✅ DONE |
| `RAGResult` | ✅ | ✅ | low | ✅ DONE |
| `READ\_ONLY\_TOOLS` | ✅ | ✅ | low | ✅ DONE |
| `RESTRICTED\_TOOLS` | ✅ | ✅ | low | ✅ DONE |
| `RetrievalConfig` | ✅ | ✅ | low | ✅ DONE |
| `RetrievalPolicy` | ✅ | ✅ | high | ✅ DONE |
<<<<<<< Updated upstream
=======
| `SkillLoader` | ✅ | ✅ | high | ✅ DONE |
>>>>>>> Stashed changes
| `SkillManager` | ✅ | ✅ | high | ✅ DONE |
| `SkillMetadata` | ✅ | ✅ | high | ✅ DONE |
| `SkillProperties` | ✅ | ✅ | high | ✅ DONE |
| `TelemetryCollector` | ✅ | ✅ | high | ✅ DONE |
| `TodoItem` | ✅ | ✅ | high | ✅ DONE |
| `TodoList` | ✅ | ✅ | high | ✅ DONE |
<<<<<<< Updated upstream

### P3_Advanced (127 done, 49 todo)
=======
| `cleanup\_telemetry\_resources` | ✅ | ✅ | low | ✅ DONE |
| `disable\_performance\_mode` | ✅ | ✅ | low | ✅ DONE |
| `disable\_telemetry` | ✅ | ✅ | low | ✅ DONE |
| `enable\_performance\_mode` | ✅ | ✅ | low | ✅ DONE |
| `enable\_telemetry` | ✅ | ✅ | low | ✅ DONE |
| `get\_telemetry` | ✅ | ✅ | low | ✅ DONE |

### P3_Advanced (176 done, 0 todo)
>>>>>>> Stashed changes

| Feature | Python | TypeScript | Effort | Status |
|---------|--------|------------|--------|--------|
| `AGUI` | ✅ | ❌ | low | ⏳ TODO |
| `AgentManager` | ✅ | ❌ | high | ⏳ TODO |
| `BotConfig` | ✅ | ❌ | low | ⏳ TODO |
| `ConditionProtocol` | ✅ | ❌ | medium | ⏳ TODO |
| `ConfigValidationError` | ✅ | ❌ | low | ⏳ TODO |
| `ContextEvent` | ✅ | ❌ | high | ⏳ TODO |
| `ContextEventType` | ✅ | ❌ | high | ⏳ TODO |
| `DictCondition` | ✅ | ❌ | high | ⏳ TODO |
| `EmbeddingResult` | ✅ | ❌ | low | ⏳ TODO |
| `FailoverManager` | ✅ | ❌ | high | ⏳ TODO |
| `FlowDisplay` | ✅ | ❌ | high | ⏳ TODO |
| `GatewayConfig` | ✅ | ❌ | low | ⏳ TODO |
| `MEMORY\_PRESETS` | ✅ | ❌ | low | ⏳ TODO |
| `MemoryBackend` | ✅ | ❌ | high | ⏳ TODO |
| `Plugin` | ✅ | ❌ | high | ⏳ TODO |
| `PluginHook` | ✅ | ❌ | high | ⏳ TODO |
| `PluginMetadata` | ✅ | ❌ | high | ⏳ TODO |
| `ProviderStatus` | ✅ | ❌ | high | ⏳ TODO |
| `SandboxStatus` | ✅ | ❌ | high | ⏳ TODO |
| `Task` | ✅ | ❌ | high | ⏳ TODO |
| `TraceSink` | ✅ | ❌ | high | ⏳ TODO |
| `async\_display\_callbacks` | ✅ | ❌ | low | ⏳ TODO |
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
| `ensure\_plugin\_dir` | ✅ | ❌ | low | ⏳ TODO |
| `error\_logs` | ✅ | ❌ | low | ⏳ TODO |
| `evaluate\_condition` | ✅ | ❌ | low | ⏳ TODO |
| `get\_default\_plugin\_dirs` | ✅ | ❌ | low | ⏳ TODO |
| `get\_dimensions` | ✅ | ❌ | low | ⏳ TODO |
| `get\_plugin\_manager` | ✅ | ❌ | low | ⏳ TODO |
| `get\_plugin\_template` | ✅ | ❌ | low | ⏳ TODO |
| `load\_plugin` | ✅ | ❌ | low | ⏳ TODO |
| `parse\_plugin\_header` | ✅ | ❌ | low | ⏳ TODO |
| `parse\_plugin\_header\_from\_file` | ✅ | ❌ | low | ⏳ TODO |
| `register\_display\_callback` | ✅ | ❌ | low | ⏳ TODO |
| `resolve` | ✅ | ❌ | low | ⏳ TODO |
| `resolve\_guardrail\_policies` | ✅ | ❌ | low | ⏳ TODO |
| `sync\_display\_callbacks` | ✅ | ❌ | low | ⏳ TODO |
| `trace\_context` | ✅ | ❌ | low | ⏳ TODO |
| `track\_workflow` | ✅ | ❌ | low | ⏳ TODO |
| `A2A` | ✅ | ✅ | low | ✅ DONE |
| `AUTONOMY\_PRESETS` | ✅ | ✅ | low | ✅ DONE |
| `AgentAppConfig` | ✅ | ✅ | low | ✅ DONE |
| `AgentAppProtocol` | ✅ | ✅ | medium | ✅ DONE |
<<<<<<< Updated upstream
=======
| `AgentManager` | ✅ | ✅ | high | ✅ DONE |
>>>>>>> Stashed changes
| `AgentOSConfig` | ✅ | ✅ | low | ✅ DONE |
| `AgentOSProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `AgentPluginProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `AgentTeam` | ✅ | ✅ | high | ✅ DONE |
| `Agents` | ✅ | ✅ | high | ✅ DONE |
| `ArrayMode` | ✅ | ✅ | high | ✅ DONE |
| `AuthProfile` | ✅ | ✅ | high | ✅ DONE |
| `AutoAgents` | ✅ | ✅ | high | ✅ DONE |
| `AutoRagAgent` | ✅ | ✅ | high | ✅ DONE |
| `AutoRagConfig` | ✅ | ✅ | low | ✅ DONE |
| `AutonomyConfig` | ✅ | ✅ | low | ✅ DONE |
| `AutonomyLevel` | ✅ | ✅ | high | ✅ DONE |
| `BotChannel` | ✅ | ✅ | high | ✅ DONE |
| `BotMessage` | ✅ | ✅ | high | ✅ DONE |
| `BotProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `BotUser` | ✅ | ✅ | high | ✅ DONE |
| `CACHING\_PRESETS` | ✅ | ✅ | low | ✅ DONE |
| `CONTEXT\_PRESETS` | ✅ | ✅ | low | ✅ DONE |
| `CachingConfig` | ✅ | ✅ | low | ✅ DONE |
| `ChunkingStrategy` | ✅ | ✅ | high | ✅ DONE |
| `ContextListSink` | ✅ | ✅ | high | ✅ DONE |
| `ContextNoOpSink` | ✅ | ✅ | high | ✅ DONE |
| `ContextTraceEmitter` | ✅ | ✅ | high | ✅ DONE |
| `ContextTraceSink` | ✅ | ✅ | high | ✅ DONE |
| `ContextTraceSinkProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `DefaultsConfig` | ✅ | ✅ | low | ✅ DONE |
| `EXECUTION\_PRESETS` | ✅ | ✅ | low | ✅ DONE |
| `EventType` | ✅ | ✅ | high | ✅ DONE |
| `ExecutionConfig` | ✅ | ✅ | low | ✅ DONE |
| `ExecutionPreset` | ✅ | ✅ | high | ✅ DONE |
| `ExpressionCondition` | ✅ | ✅ | high | ✅ DONE |
| `FailoverConfig` | ✅ | ✅ | low | ✅ DONE |
| `FunctionPlugin` | ✅ | ✅ | high | ✅ DONE |
| `GUARDRAIL\_PRESETS` | ✅ | ✅ | low | ✅ DONE |
| `GatewayClientProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `GatewayEvent` | ✅ | ✅ | high | ✅ DONE |
| `GatewayMessage` | ✅ | ✅ | high | ✅ DONE |
| `GatewayProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `GatewaySessionProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `GuardrailAction` | ✅ | ✅ | high | ✅ DONE |
| `GuardrailConfig` | ✅ | ✅ | low | ✅ DONE |
| `HookPluginProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `HooksConfig` | ✅ | ✅ | low | ✅ DONE |
| `KNOWLEDGE\_PRESETS` | ✅ | ✅ | low | ✅ DONE |
| `KnowledgeConfig` | ✅ | ✅ | low | ✅ DONE |
| `LLMPluginProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `MEMORY\_URL\_SCHEMES` | ✅ | ✅ | low | ✅ DONE |
| `MULTI\_AGENT\_EXECUTION\_PRESETS` | ✅ | ✅ | low | ✅ DONE |
| `MULTI\_AGENT\_OUTPUT\_PRESETS` | ✅ | ✅ | low | ✅ DONE |
<<<<<<< Updated upstream
=======
| `MemoryBackend` | ✅ | ✅ | high | ✅ DONE |
>>>>>>> Stashed changes
| `MemoryConfig` | ✅ | ✅ | low | ✅ DONE |
| `MessageType` | ✅ | ✅ | high | ✅ DONE |
| `MultiAgentExecutionConfig` | ✅ | ✅ | low | ✅ DONE |
| `MultiAgentHooksConfig` | ✅ | ✅ | low | ✅ DONE |
| `MultiAgentMemoryConfig` | ✅ | ✅ | low | ✅ DONE |
| `MultiAgentOutputConfig` | ✅ | ✅ | low | ✅ DONE |
| `MultiAgentPlanningConfig` | ✅ | ✅ | low | ✅ DONE |
| `OUTPUT\_PRESETS` | ✅ | ✅ | low | ✅ DONE |
| `OutputConfig` | ✅ | ✅ | low | ✅ DONE |
| `OutputPreset` | ✅ | ✅ | high | ✅ DONE |
| `PLANNING\_PRESETS` | ✅ | ✅ | low | ✅ DONE |
| `PlanningConfig` | ✅ | ✅ | low | ✅ DONE |
| `PluginInfo` | ✅ | ✅ | high | ✅ DONE |
| `PluginManager` | ✅ | ✅ | high | ✅ DONE |
| `PluginParseError` | ✅ | ✅ | low | ✅ DONE |
| `PluginProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `PluginsConfig` | ✅ | ✅ | low | ✅ DONE |
| `PraisonConfig` | ✅ | ✅ | low | ✅ DONE |
| `REFLECTION\_PRESETS` | ✅ | ✅ | low | ✅ DONE |
| `RagRetrievalPolicy` | ✅ | ✅ | high | ✅ DONE |
| `ReflectionConfig` | ✅ | ✅ | low | ✅ DONE |
| `ReflectionOutput` | ✅ | ✅ | high | ✅ DONE |
| `ResourceLimits` | ✅ | ✅ | high | ✅ DONE |
| `RoutingConditionProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `SandboxConfig` | ✅ | ✅ | low | ✅ DONE |
| `SandboxProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `SandboxResult` | ✅ | ✅ | low | ✅ DONE |
<<<<<<< Updated upstream
=======
| `SandboxStatus` | ✅ | ✅ | high | ✅ DONE |
>>>>>>> Stashed changes
| `SecurityPolicy` | ✅ | ✅ | high | ✅ DONE |
| `SessionConfig` | ✅ | ✅ | low | ✅ DONE |
| `SkillsConfig` | ✅ | ✅ | low | ✅ DONE |
| `TaskOutput` | ✅ | ✅ | high | ✅ DONE |
| `TemplateConfig` | ✅ | ✅ | low | ✅ DONE |
| `ToolPluginProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `Tools` | ✅ | ✅ | high | ✅ DONE |
| `TraceSinkProtocol` | ✅ | ✅ | medium | ✅ DONE |
| `WEB\_PRESETS` | ✅ | ✅ | low | ✅ DONE |
| `WebConfig` | ✅ | ✅ | low | ✅ DONE |
| `WebSearchProvider` | ✅ | ✅ | high | ✅ DONE |
| `aembed` | ✅ | ✅ | low | ✅ DONE |
| `aembedding` | ✅ | ✅ | low | ✅ DONE |
| `aembeddings` | ✅ | ✅ | low | ✅ DONE |
| `apply\_config\_defaults` | ✅ | ✅ | low | ✅ DONE |
| `clean\_triple\_backticks` | ✅ | ✅ | low | ✅ DONE |
| `embedding` | ✅ | ✅ | low | ✅ DONE |
| `embeddings` | ✅ | ✅ | low | ✅ DONE |
| `get\_config` | ✅ | ✅ | low | ✅ DONE |
| `get\_config\_path` | ✅ | ✅ | low | ✅ DONE |
| `get\_default` | ✅ | ✅ | low | ✅ DONE |
| `get\_defaults\_config` | ✅ | ✅ | low | ✅ DONE |
| `get\_plugins\_config` | ✅ | ✅ | low | ✅ DONE |
| `is\_path\_like` | ✅ | ✅ | low | ✅ DONE |
| `is\_policy\_string` | ✅ | ✅ | low | ✅ DONE |
| `memory` | ✅ | ✅ | low | ✅ DONE |
| `obs` | ✅ | ✅ | low | ✅ DONE |
| `parse\_policy\_string` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_autonomy` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_caching` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_context` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_execution` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_guardrails` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_hooks` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_knowledge` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_memory` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_output` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_planning` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_reflection` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_routing` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_skills` | ✅ | ✅ | low | ✅ DONE |
| `resolve\_web` | ✅ | ✅ | low | ✅ DONE |
| `suggest\_similar` | ✅ | ✅ | low | ✅ DONE |
<<<<<<< Updated upstream
| `tool` | ✅ | ✅ | low | ✅ DONE |
| `tools` | ✅ | ✅ | low | ✅ DONE |
=======
| `sync\_display\_callbacks` | ✅ | ✅ | low | ✅ DONE |
| `tool` | ✅ | ✅ | low | ✅ DONE |
| `tools` | ✅ | ✅ | low | ✅ DONE |
| `trace\_context` | ✅ | ✅ | low | ✅ DONE |
| `track\_workflow` | ✅ | ✅ | low | ✅ DONE |
>>>>>>> Stashed changes
| `validate\_config` | ✅ | ✅ | low | ✅ DONE |
| `workflows` | ✅ | ✅ | low | ✅ DONE |

## Python Core SDK Exports

**Path:** `/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents/praisonaiagents`

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

**Path:** `/home/runner/work/PraisonAI/PraisonAI/src/praisonai-ts/src`

<details>
<summary><strong>agent</strong> (64 exports)</summary>

```typescript
import { Agent, AgentTeam, AgentTeamConfig, Agents, AudioAgent, AudioAgentConfig, AudioProvider, AudioSpeakOptions, AudioSpeakResult, AudioTranscribeOptions... } from 'praisonai';
```

</details>

<details>
<summary><strong>ai</strong> (166 exports)</summary>

```typescript
import { AIAgentStep, AIEmbedManyResult, AIEmbedOptions, AIEmbedResult, AIFilePart, AIGenerateImageOptions, AIGenerateImageResult, AIGenerateObjectOptions, AIGenerateObjectResult, AIGenerateTextOptions... } from 'praisonai';
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
<summary><strong>cli</strong> (130 exports)</summary>

```typescript
<<<<<<< Updated upstream
import { // Autonomy Mode
  AutonomyManager, // Background Jobs
  JobQueue, // Checkpoints
  CheckpointManager, // Cost Tracker
  CostTracker, // External Agents
  BaseExternalAgent, // Fast Context (Python parity with praisonaiagents/context/fast)
  FastContext, // Flow Display
  FlowDisplay, // Git Integration
  GitManager, // Interactive TUI
  InteractiveTUI, // N8N Integration
  N8NIntegration... } from 'praisonai';
=======
import { ActionDecision, ActionRequest, ActionType, AiderAgent, ApprovalPolicy, AutonomyConfig, AutonomyManager, AutonomyMode, BaseExternalAgent, CLI_SPEC_VERSION... } from 'praisonai';
>>>>>>> Stashed changes
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
import { AccuracyEvalConfig, AccuracyJudge, AggregatedResults, CriteriaJudge, EvalCriteria, EvalResult, EvalResults, EvalSuite, Evaluator, EvaluatorConfig... } from 'praisonai';
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
import { BaseObservabilityProvider, BaseVectorStore, BaseVoiceProvider, ChromaVectorStore, ColumnSchema, ComputerAction, ComputerUseClient, ComputerUseConfig, ComputerUseTools, ConsoleObservabilityProvider... } from 'praisonai';
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
import { ADAPTERS, AISDK_PROVIDERS, AdapterInfo, AnthropicProvider, BaseProvider, COMMUNITY_PROVIDERS, CommunityProvider, CreateProviderOptions, GenerateObjectOptions, GenerateObjectResult... } from 'praisonai';
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
import { AttributionContext, ConsoleObservabilityAdapter, MemoryObservabilityAdapter, NoopObservabilityAdapter, OBSERVABILITY_TOOLS, ObservabilityAdapter, ObservabilityToolConfig, ObservabilityToolInfo, ObservabilityToolName, ProviderMetadata... } from 'praisonai';
```

</details>

<details>
<summary><strong>os</strong> (10 exports)</summary>

```typescript
import { AgentApp, AgentAppConfig, AgentAppOptions, AgentAppProtocol, AgentOS, AgentOSConfig, AgentOSOptions, AgentOSProtocol, DEFAULT_AGENTOS_CONFIG, mergeConfig } from 'praisonai';
```

</details>

<details>
<<<<<<< Updated upstream
<summary><strong>other</strong> (233 exports)</summary>

```typescript
import { // A2A Protocol
  A2ATaskState, // AGUI Protocol
  AGUI, // AgentManager alias type
  AgentManager, // Bot types
  BotConfig, // Classes
  DictCondition, // Classes
  FailoverManager, // Classes
  Plugin, // Classes
  TraceSink, // Enums
  ContextEventType, // Enums
  MemoryBackend... } from 'praisonai';
=======
<summary><strong>other</strong> (203 exports)</summary>

```typescript
import { AUTONOMY_PRESETS, AgentPluginProtocol, ArrayMode, AsyncDisplayCallback, AuthProfile, AutoRagConfig, AutonomyLevel, BatchEmbeddingResult, BotChannel, BotConfig... } from 'praisonai';
>>>>>>> Stashed changes
```

</details>

<details>
<<<<<<< Updated upstream
<summary><strong>planning</strong> (25 exports)</summary>

```typescript
import { // Core classes
  Plan, // Python parity additions
  ApprovalCallback, ApprovalCallbackConfig, PlanConfig, PlanResult, PlanStatus, PlanStep, PlanStepConfig, PlanStorage, PlanningAgent... } from 'praisonai';
=======
<summary><strong>parity</strong> (65 exports)</summary>

```typescript
import { AudioConfig, Chunking, CodeAgent, CodeConfig, CodeExecutionStep, ContextConfig, ContextManager, ContextPack, DeepResearchResponse, EmbeddingAgent... } from 'praisonai';
>>>>>>> Stashed changes
```

</details>

<details>
<<<<<<< Updated upstream
<summary><strong>skills</strong> (10 exports)</summary>

```typescript
import { // Python parity additions
  SkillLoader, Skill, SkillDiscoveryOptions, SkillManager, SkillMetadata, SkillProperties, createSkillLoader, createSkillManager, createSkillProperties, parseSkillFile } from 'praisonai';
=======
<summary><strong>planning</strong> (25 exports)</summary>

```typescript
import { ApprovalCallback, ApprovalCallbackConfig, Plan, PlanConfig, PlanResult, PlanStatus, PlanStep, PlanStepConfig, PlanStorage, PlanningAgent... } from 'praisonai';
```

</details>

<details>
<summary><strong>protocols</strong> (30 exports)</summary>

```typescript
import { A2A, A2AAgentCapabilities, A2AAgentCard, A2AAgentSkill, A2AArtifact, A2ADataPart, A2AFilePart, A2AMessage, A2APart, A2ARole... } from 'praisonai';
```

</details>

<details>
<summary><strong>skills</strong> (10 exports)</summary>

```typescript
import { Skill, SkillDiscoveryOptions, SkillLoader, SkillManager, SkillMetadata, SkillProperties, createSkillLoader, createSkillManager, createSkillProperties, parseSkillFile } from 'praisonai';
>>>>>>> Stashed changes
```

</details>

<details>
<summary><strong>task</strong> (5 exports)</summary>

```typescript
import { AgentTask, AgentTaskConfig, BaseTask, TaskOutput, createTaskOutput } from 'praisonai';
```

</details>

<details>
<summary><strong>telemetry</strong> (26 exports)</summary>

```typescript
<<<<<<< Updated upstream
import { // Python parity additions
  MinimalTelemetry, AgentStats, AgentTelemetry, MetricEntry, PerformanceMonitor, PerformanceMonitorConfig, PerformanceStats, TelemetryCollector, TelemetryConfig, TelemetryEvent... } from 'praisonai';
=======
import { AgentStats, AgentTelemetry, MetricEntry, MinimalTelemetry, PerformanceMonitor, PerformanceMonitorConfig, PerformanceStats, TelemetryCollector, TelemetryConfig, TelemetryEvent... } from 'praisonai';
>>>>>>> Stashed changes
```

</details>

<details>
<summary><strong>tools</strong> (82 exports)</summary>

```typescript
import { BaseTool, DelegatorConfig, FunctionTool, InstallHints, MissingDependencyError, MissingEnvVarError, PraisonTool, RedactionHooks, RegisteredTool, SubagentTool... } from 'praisonai';
```

</details>

<details>
<summary><strong>workflows</strong> (31 exports)</summary>

```typescript
import { AgentFlow, Loop, LoopConfig, LoopResult, ParsedWorkflow, Pipeline, Repeat, RepeatConfig, RepeatContext, RepeatResult... } from 'praisonai';
```

</details>

---

*Generated by `praisonai._dev.parity.generator`*
