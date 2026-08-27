# Feature Parity Tracker

> **Version:** 1.5.87 | **Last Updated:** 2026-08-27
> **Source of Truth:** Python SDK (praisonaiagents)

> [!IMPORTANT]
> **What this measures:** whether a matching *exported symbol name* exists in
> the TypeScript SDK's public surface (parsed from `src/index.ts`). It does **not**
> verify that the capability is reachable, wired up, or behaves like its Python
> counterpart. A `✅ exported` cell means the name is exported — not that it works.
> Counts include barrel re-exports, so `TypeScript Features` reflects module
> structure, not distinct capabilities, and is not directly comparable to the
> Python count. For a capability with a testable contract, rely on its conformance
> suite rather than this table.

## Summary

| Metric | Count |
|--------|-------|
| Python Core Features | 411 |
| Python Wrapper Features | 21 |
| TypeScript Features | 1194 |
| **Gap Count** | **116** |
| P0 (Critical) | 2 |
| P1 (High) | 5 |
| P2 (Medium) | 6 |
| P3 (Low) | 103 |

## Gap Matrix

### P0_CoreParity (52 exported, 2 missing)

| Feature | Python | TypeScript | Effort | Status |
|---------|--------|------------|--------|--------|
| `HandoffToolPolicy` | ✅ | ❌ | high | ⏳ missing |
| `parallel\_handoffs` | ✅ | ❌ | low | ⏳ missing |
| `Agent` | ✅ | ✅ | high | ✅ exported |
| `AudioAgent` | ✅ | ✅ | high | ✅ exported |
| `AudioConfig` | ✅ | ✅ | low | ✅ exported |
| `BaseTool` | ✅ | ✅ | high | ✅ exported |
| `CodeAgent` | ✅ | ✅ | high | ✅ exported |
| `CodeConfig` | ✅ | ✅ | low | ✅ exported |
| `CodeExecutionStep` | ✅ | ✅ | high | ✅ exported |
| `ContextAgent` | ✅ | ✅ | high | ✅ exported |
| `ContextPolicy` | ✅ | ✅ | high | ✅ exported |
| `DeepResearchAgent` | ✅ | ✅ | high | ✅ exported |
| `DeepResearchResponse` | ✅ | ✅ | high | ✅ exported |
| `EmbeddingAgent` | ✅ | ✅ | high | ✅ exported |
| `EmbeddingConfig` | ✅ | ✅ | low | ✅ exported |
| `ExpandResult` | ✅ | ✅ | low | ✅ exported |
| `ExpandStrategy` | ✅ | ✅ | high | ✅ exported |
| `FileSearchCall` | ✅ | ✅ | high | ✅ exported |
| `FunctionTool` | ✅ | ✅ | high | ✅ exported |
| `Handoff` | ✅ | ✅ | high | ✅ exported |
| `HandoffConfig` | ✅ | ✅ | low | ✅ exported |
| `HandoffInputData` | ✅ | ✅ | high | ✅ exported |
| `HandoffResult` | ✅ | ✅ | low | ✅ exported |
| `ImageAgent` | ✅ | ✅ | high | ✅ exported |
| `MCPCall` | ✅ | ✅ | high | ✅ exported |
| `OCRAgent` | ✅ | ✅ | high | ✅ exported |
| `OCRConfig` | ✅ | ✅ | low | ✅ exported |
| `PromptExpanderAgent` | ✅ | ✅ | high | ✅ exported |
| `Provider` | ✅ | ✅ | high | ✅ exported |
| `QueryRewriterAgent` | ✅ | ✅ | high | ✅ exported |
| `RECOMMENDED\_PROMPT\_PREFIX` | ✅ | ✅ | low | ✅ exported |
| `RealtimeAgent` | ✅ | ✅ | high | ✅ exported |
| `RealtimeConfig` | ✅ | ✅ | low | ✅ exported |
| `ReasoningStep` | ✅ | ✅ | high | ✅ exported |
| `RewriteResult` | ✅ | ✅ | low | ✅ exported |
| `RewriteStrategy` | ✅ | ✅ | high | ✅ exported |
| `ToolRegistry` | ✅ | ✅ | high | ✅ exported |
| `ToolResult` | ✅ | ✅ | low | ✅ exported |
| `ToolValidationError` | ✅ | ✅ | low | ✅ exported |
| `Tools` | ✅ | ✅ | high | ✅ exported |
| `VideoAgent` | ✅ | ✅ | high | ✅ exported |
| `VideoConfig` | ✅ | ✅ | low | ✅ exported |
| `VisionAgent` | ✅ | ✅ | high | ✅ exported |
| `VisionConfig` | ✅ | ✅ | low | ✅ exported |
| `WebSearchCall` | ✅ | ✅ | high | ✅ exported |
| `create\_context\_agent` | ✅ | ✅ | low | ✅ exported |
| `get\_registry` | ✅ | ✅ | low | ✅ exported |
| `get\_tool` | ✅ | ✅ | low | ✅ exported |
| `handoff` | ✅ | ✅ | low | ✅ exported |
| `handoff\_filters` | ✅ | ✅ | low | ✅ exported |
| `prompt\_with\_handoff\_instructions` | ✅ | ✅ | low | ✅ exported |
| `register\_tool` | ✅ | ✅ | low | ✅ exported |
| `tool` | ✅ | ✅ | low | ✅ exported |
| `validate\_tool` | ✅ | ✅ | low | ✅ exported |

### P1_Persistence (20 exported, 5 missing)

| Feature | Python | TypeScript | Effort | Status |
|---------|--------|------------|--------|--------|
| `Include` | ✅ | ❌ | high | ⏳ missing |
| `MAX\_NESTING\_DEPTH` | ✅ | ❌ | low | ⏳ missing |
| `YAMLWorkflowParser` | ✅ | ❌ | high | ⏳ missing |
| `if\_` | ✅ | ❌ | low | ⏳ missing |
| `include` | ✅ | ❌ | low | ⏳ missing |
| `AgentFlow` | ✅ | ✅ | high | ✅ exported |
| `Chunking` | ✅ | ✅ | high | ✅ exported |
| `If` | ✅ | ✅ | high | ✅ exported |
| `Knowledge` | ✅ | ✅ | high | ✅ exported |
| `Loop` | ✅ | ✅ | high | ✅ exported |
| `Memory` | ✅ | ✅ | high | ✅ exported |
| `Parallel` | ✅ | ✅ | high | ✅ exported |
| `Pipeline` | ✅ | ✅ | high | ✅ exported |
| `Repeat` | ✅ | ✅ | high | ✅ exported |
| `Route` | ✅ | ✅ | high | ✅ exported |
| `Session` | ✅ | ✅ | high | ✅ exported |
| `StepResult` | ✅ | ✅ | low | ✅ exported |
| `Workflow` | ✅ | ✅ | high | ✅ exported |
| `WorkflowContext` | ✅ | ✅ | high | ✅ exported |
| `WorkflowHooksConfig` | ✅ | ✅ | low | ✅ exported |
| `loop` | ✅ | ✅ | low | ✅ exported |
| `parallel` | ✅ | ✅ | low | ✅ exported |
| `repeat` | ✅ | ✅ | low | ✅ exported |
| `route` | ✅ | ✅ | low | ✅ exported |
| `when` | ✅ | ✅ | low | ✅ exported |

### P2_CLI (41 exported, 6 missing)

| Feature | Python | TypeScript | Effort | Status |
|---------|--------|------------|--------|--------|
| `EnforcementLevel` | ✅ | ❌ | high | ⏳ missing |
| `SkillState` | ✅ | ❌ | high | ⏳ missing |
| `discover\_skills` | ✅ | ❌ | low | ⏳ missing |
| `load\_skill` | ✅ | ❌ | low | ⏳ missing |
| `validate` | ✅ | ❌ | low | ⏳ missing |
| `validate\_metadata` | ✅ | ❌ | low | ⏳ missing |
| `ApprovalCallback` | ✅ | ✅ | high | ✅ exported |
| `Citation` | ✅ | ✅ | high | ✅ exported |
| `CitationsMode` | ✅ | ✅ | high | ✅ exported |
| `ContextConfig` | ✅ | ✅ | low | ✅ exported |
| `ContextManager` | ✅ | ✅ | high | ✅ exported |
| `ContextPack` | ✅ | ✅ | high | ✅ exported |
| `FastContext` | ✅ | ✅ | high | ✅ exported |
| `FastContextResult` | ✅ | ✅ | low | ✅ exported |
| `FileMatch` | ✅ | ✅ | high | ✅ exported |
| `GuardrailResult` | ✅ | ✅ | low | ✅ exported |
| `LLMGuardrail` | ✅ | ✅ | high | ✅ exported |
| `LineRange` | ✅ | ✅ | high | ✅ exported |
| `MCP` | ✅ | ✅ | low | ✅ exported |
| `ManagerConfig` | ✅ | ✅ | low | ✅ exported |
| `MinimalTelemetry` | ✅ | ✅ | high | ✅ exported |
| `OptimizerStrategy` | ✅ | ✅ | high | ✅ exported |
| `Plan` | ✅ | ✅ | high | ✅ exported |
| `PlanStep` | ✅ | ✅ | high | ✅ exported |
| `PlanStorage` | ✅ | ✅ | high | ✅ exported |
| `PlanningAgent` | ✅ | ✅ | high | ✅ exported |
| `RAG` | ✅ | ✅ | low | ✅ exported |
| `RAGCitation` | ✅ | ✅ | high | ✅ exported |
| `RAGConfig` | ✅ | ✅ | low | ✅ exported |
| `RAGResult` | ✅ | ✅ | low | ✅ exported |
| `READ\_ONLY\_TOOLS` | ✅ | ✅ | low | ✅ exported |
| `RESTRICTED\_TOOLS` | ✅ | ✅ | low | ✅ exported |
| `RetrievalConfig` | ✅ | ✅ | low | ✅ exported |
| `RetrievalPolicy` | ✅ | ✅ | high | ✅ exported |
| `SkillLoader` | ✅ | ✅ | high | ✅ exported |
| `SkillManager` | ✅ | ✅ | high | ✅ exported |
| `SkillMetadata` | ✅ | ✅ | high | ✅ exported |
| `SkillProperties` | ✅ | ✅ | high | ✅ exported |
| `TelemetryCollector` | ✅ | ✅ | high | ✅ exported |
| `TodoItem` | ✅ | ✅ | high | ✅ exported |
| `TodoList` | ✅ | ✅ | high | ✅ exported |
| `cleanup\_telemetry\_resources` | ✅ | ✅ | low | ✅ exported |
| `disable\_performance\_mode` | ✅ | ✅ | low | ✅ exported |
| `disable\_telemetry` | ✅ | ✅ | low | ✅ exported |
| `enable\_performance\_mode` | ✅ | ✅ | low | ✅ exported |
| `enable\_telemetry` | ✅ | ✅ | low | ✅ exported |
| `get\_telemetry` | ✅ | ✅ | low | ✅ exported |

### P3_Advanced (182 exported, 103 missing)

| Feature | Python | TypeScript | Effort | Status |
|---------|--------|------------|--------|--------|
| `A2UI` | ✅ | ❌ | low | ⏳ missing |
| `AGGRESSIVE\_POLICY` | ✅ | ❌ | low | ⏳ missing |
| `AgentMessageEvent` | ✅ | ❌ | high | ⏳ missing |
| `AgentRunOutcome` | ✅ | ❌ | high | ⏳ missing |
| `AgentRuntimeProtocol` | ✅ | ❌ | medium | ⏳ missing |
| `AsyncLearnProtocol` | ✅ | ❌ | medium | ⏳ missing |
| `AutoApproveBackend` | ✅ | ❌ | high | ⏳ missing |
| `BALANCED\_POLICY` | ✅ | ❌ | low | ⏳ missing |
| `BackendNotAvailableError` | ✅ | ❌ | low | ⏳ missing |
| `BaseFrameworkAdapter` | ✅ | ❌ | high | ⏳ missing |
| `BasePlatformAdapter` | ✅ | ❌ | high | ⏳ missing |
| `BotOSConfig` | ✅ | ❌ | low | ⏳ missing |
| `BotOSProtocol` | ✅ | ❌ | medium | ⏳ missing |
| `CONSERVATIVE\_POLICY` | ✅ | ❌ | low | ⏳ missing |
| `ChromaMemory` | ✅ | ❌ | high | ⏳ missing |
| `CliBackendConfig` | ✅ | ❌ | low | ⏳ missing |
| `CliBackendDelta` | ✅ | ❌ | high | ⏳ missing |
| `CliBackendProtocol` | ✅ | ❌ | medium | ⏳ missing |
| `CliBackendResult` | ✅ | ❌ | low | ⏳ missing |
| `CliSessionBinding` | ✅ | ❌ | high | ⏳ missing |
| `CompactionRoute` | ✅ | ❌ | high | ⏳ missing |
| `CompactionStrategy` | ✅ | ❌ | high | ⏳ missing |
| `ConsoleBackend` | ✅ | ❌ | high | ⏳ missing |
| `ContextBudgetResult` | ✅ | ❌ | low | ⏳ missing |
| `ContextCompactionPolicy` | ✅ | ❌ | high | ⏳ missing |
| `ContextCompactionPolicyProtocol` | ✅ | ❌ | medium | ⏳ missing |
| `CorpusStats` | ✅ | ❌ | high | ⏳ missing |
| `CustomToolUseEvent` | ✅ | ❌ | high | ⏳ missing |
| `DoomLoopDetector` | ✅ | ❌ | high | ⏳ missing |
| `ErrorContextProtocol` | ✅ | ❌ | medium | ⏳ missing |
| `EscalationPipeline` | ✅ | ❌ | high | ⏳ missing |
| `EscalationStage` | ✅ | ❌ | high | ⏳ missing |
| `FileTracker` | ✅ | ❌ | high | ⏳ missing |
| `FrameworkAdapterProtocol` | ✅ | ❌ | medium | ⏳ missing |
| `GatewayEventType` | ✅ | ❌ | high | ⏳ missing |
| `Goal` | ✅ | ❌ | high | ⏳ missing |
| `GoalConfig` | ✅ | ❌ | low | ⏳ missing |
| `GoalEngineer` | ✅ | ❌ | high | ⏳ missing |
| `GoalVerificationResult` | ✅ | ❌ | low | ⏳ missing |
| `HarnessProfile` | ✅ | ❌ | high | ⏳ missing |
| `Heartbeat` | ✅ | ❌ | high | ⏳ missing |
| `HeartbeatConfig` | ✅ | ❌ | low | ⏳ missing |
| `IndexResult` | ✅ | ❌ | low | ⏳ missing |
| `KnowledgeStoreProtocol` | ✅ | ❌ | medium | ⏳ missing |
| `LLMError` | ✅ | ❌ | low | ⏳ missing |
| `LearnBackend` | ✅ | ❌ | high | ⏳ missing |
| `LearnManager` | ✅ | ❌ | high | ⏳ missing |
| `LearnManagerProtocol` | ✅ | ❌ | medium | ⏳ missing |
| `LearnMode` | ✅ | ❌ | high | ⏳ missing |
| `LearnProtocol` | ✅ | ❌ | medium | ⏳ missing |
| `LearnScope` | ✅ | ❌ | high | ⏳ missing |
| `ManagedBackendProtocol` | ✅ | ❌ | medium | ⏳ missing |
| `ManagedEvent` | ✅ | ❌ | high | ⏳ missing |
| `NetworkError` | ✅ | ❌ | low | ⏳ missing |
| `ObservabilityEventType` | ✅ | ❌ | high | ⏳ missing |
| `ObservabilityHooks` | ✅ | ❌ | high | ⏳ missing |
| `PlatformCapabilities` | ✅ | ❌ | high | ⏳ missing |
| `PraisonAIConfigError` | ✅ | ❌ | low | ⏳ missing |
| `PraisonAIError` | ✅ | ❌ | low | ⏳ missing |
| `PreCompactionMemoryFlushConfig` | ✅ | ❌ | low | ⏳ missing |
| `RetryBackoffConfig` | ✅ | ❌ | low | ⏳ missing |
| `RulesConfig` | ✅ | ❌ | low | ⏳ missing |
| `RunOutcome` | ✅ | ❌ | high | ⏳ missing |
| `RunStatus` | ✅ | ❌ | high | ⏳ missing |
| `ScopeRequiredError` | ✅ | ❌ | low | ⏳ missing |
| `SendResult` | ✅ | ❌ | low | ⏳ missing |
| `SessionErrorEvent` | ✅ | ❌ | high | ⏳ missing |
| `SessionIdleEvent` | ✅ | ❌ | high | ⏳ missing |
| `StructuredFormatter` | ✅ | ❌ | high | ⏳ missing |
| `SuccessCriterion` | ✅ | ❌ | high | ⏳ missing |
| `TerminationReason` | ✅ | ❌ | high | ⏳ missing |
| `ToolExecutionError` | ✅ | ❌ | low | ⏳ missing |
| `ToolSearchConfig` | ✅ | ❌ | low | ⏳ missing |
| `ToolUseEvent` | ✅ | ❌ | high | ⏳ missing |
| `ToolsetRegistry` | ✅ | ❌ | high | ⏳ missing |
| `ToolsetSpec` | ✅ | ❌ | high | ⏳ missing |
| `ValidationError` | ✅ | ❌ | low | ⏳ missing |
| `\_\_version\_\_` | ✅ | ❌ | low | ⏳ missing |
| `add\_memory\_adapter` | ✅ | ❌ | low | ⏳ missing |
| `add\_memory\_factory` | ✅ | ❌ | low | ⏳ missing |
| `configure\_structured\_logging` | ✅ | ❌ | low | ⏳ missing |
| `get\_default\_policy` | ✅ | ❌ | low | ⏳ missing |
| `get\_logger` | ✅ | ❌ | low | ⏳ missing |
| `get\_memory\_adapter` | ✅ | ❌ | low | ⏳ missing |
| `get\_toolset` | ✅ | ❌ | low | ⏳ missing |
| `get\_toolset\_registry` | ✅ | ❌ | low | ⏳ missing |
| `has\_memory\_adapter` | ✅ | ❌ | low | ⏳ missing |
| `has\_toolset` | ✅ | ❌ | low | ⏳ missing |
| `list\_memory\_adapters` | ✅ | ❌ | low | ⏳ missing |
| `list\_runtimes` | ✅ | ❌ | low | ⏳ missing |
| `list\_toolsets` | ✅ | ❌ | low | ⏳ missing |
| `register\_memory\_adapter` | ✅ | ❌ | low | ⏳ missing |
| `register\_memory\_factory` | ✅ | ❌ | low | ⏳ missing |
| `register\_profile` | ✅ | ❌ | low | ⏳ missing |
| `register\_runtime` | ✅ | ❌ | low | ⏳ missing |
| `register\_toolset` | ✅ | ❌ | low | ⏳ missing |
| `resolve\_harness` | ✅ | ❌ | low | ⏳ missing |
| `resolve\_runtime` | ✅ | ❌ | low | ⏳ missing |
| `resolve\_toolset` | ✅ | ❌ | low | ⏳ missing |
| `resolve\_toolsets` | ✅ | ❌ | low | ⏳ missing |
| `termination\_to\_run\_status` | ✅ | ❌ | low | ⏳ missing |
| `unregister\_toolset` | ✅ | ❌ | low | ⏳ missing |
| `validate\_decision\_string` | ✅ | ❌ | low | ⏳ missing |
| `A2A` | ✅ | ✅ | low | ✅ exported |
| `AGUI` | ✅ | ✅ | low | ✅ exported |
| `AUTONOMY\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `AgentAppConfig` | ✅ | ✅ | low | ✅ exported |
| `AgentAppProtocol` | ✅ | ✅ | medium | ✅ exported |
| `AgentManager` | ✅ | ✅ | high | ✅ exported |
| `AgentOSConfig` | ✅ | ✅ | low | ✅ exported |
| `AgentOSProtocol` | ✅ | ✅ | medium | ✅ exported |
| `AgentPluginProtocol` | ✅ | ✅ | medium | ✅ exported |
| `AgentTeam` | ✅ | ✅ | high | ✅ exported |
| `Agents` | ✅ | ✅ | high | ✅ exported |
| `ArrayMode` | ✅ | ✅ | high | ✅ exported |
| `AuthProfile` | ✅ | ✅ | high | ✅ exported |
| `AutoAgents` | ✅ | ✅ | high | ✅ exported |
| `AutoMemory` | ✅ | ✅ | high | ✅ exported |
| `AutoRagAgent` | ✅ | ✅ | high | ✅ exported |
| `AutoRagConfig` | ✅ | ✅ | low | ✅ exported |
| `AutonomyConfig` | ✅ | ✅ | low | ✅ exported |
| `AutonomyLevel` | ✅ | ✅ | high | ✅ exported |
| `BotChannel` | ✅ | ✅ | high | ✅ exported |
| `BotConfig` | ✅ | ✅ | low | ✅ exported |
| `BotMessage` | ✅ | ✅ | high | ✅ exported |
| `BotProtocol` | ✅ | ✅ | medium | ✅ exported |
| `BotUser` | ✅ | ✅ | high | ✅ exported |
| `BudgetExceededError` | ✅ | ✅ | low | ✅ exported |
| `CACHING\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `CONTEXT\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `CachingConfig` | ✅ | ✅ | low | ✅ exported |
| `ChunkingStrategy` | ✅ | ✅ | high | ✅ exported |
| `ConditionProtocol` | ✅ | ✅ | medium | ✅ exported |
| `ConfigValidationError` | ✅ | ✅ | low | ✅ exported |
| `ContextEvent` | ✅ | ✅ | high | ✅ exported |
| `ContextEventType` | ✅ | ✅ | high | ✅ exported |
| `ContextListSink` | ✅ | ✅ | high | ✅ exported |
| `ContextNoOpSink` | ✅ | ✅ | high | ✅ exported |
| `ContextTraceEmitter` | ✅ | ✅ | high | ✅ exported |
| `ContextTraceSink` | ✅ | ✅ | high | ✅ exported |
| `ContextTraceSinkProtocol` | ✅ | ✅ | medium | ✅ exported |
| `DefaultsConfig` | ✅ | ✅ | low | ✅ exported |
| `DictCondition` | ✅ | ✅ | high | ✅ exported |
| `EXECUTION\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `EmbeddingResult` | ✅ | ✅ | low | ✅ exported |
| `EventType` | ✅ | ✅ | high | ✅ exported |
| `ExecutionConfig` | ✅ | ✅ | low | ✅ exported |
| `ExecutionPreset` | ✅ | ✅ | high | ✅ exported |
| `ExpressionCondition` | ✅ | ✅ | high | ✅ exported |
| `FailoverConfig` | ✅ | ✅ | low | ✅ exported |
| `FailoverManager` | ✅ | ✅ | high | ✅ exported |
| `FlowDisplay` | ✅ | ✅ | high | ✅ exported |
| `FunctionPlugin` | ✅ | ✅ | high | ✅ exported |
| `GUARDRAIL\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `GatewayClientProtocol` | ✅ | ✅ | medium | ✅ exported |
| `GatewayConfig` | ✅ | ✅ | low | ✅ exported |
| `GatewayEvent` | ✅ | ✅ | high | ✅ exported |
| `GatewayMessage` | ✅ | ✅ | high | ✅ exported |
| `GatewayProtocol` | ✅ | ✅ | medium | ✅ exported |
| `GatewaySessionProtocol` | ✅ | ✅ | medium | ✅ exported |
| `GuardrailAction` | ✅ | ✅ | high | ✅ exported |
| `GuardrailConfig` | ✅ | ✅ | low | ✅ exported |
| `HandoffCycleError` | ✅ | ✅ | low | ✅ exported |
| `HandoffDepthError` | ✅ | ✅ | low | ✅ exported |
| `HandoffError` | ✅ | ✅ | low | ✅ exported |
| `HandoffTimeoutError` | ✅ | ✅ | low | ✅ exported |
| `HookPluginProtocol` | ✅ | ✅ | medium | ✅ exported |
| `HooksConfig` | ✅ | ✅ | low | ✅ exported |
| `KNOWLEDGE\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `KnowledgeConfig` | ✅ | ✅ | low | ✅ exported |
| `LLMPluginProtocol` | ✅ | ✅ | medium | ✅ exported |
| `LearnConfig` | ✅ | ✅ | low | ✅ exported |
| `MEMORY\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `MEMORY\_URL\_SCHEMES` | ✅ | ✅ | low | ✅ exported |
| `MULTI\_AGENT\_EXECUTION\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `MULTI\_AGENT\_OUTPUT\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `MemoryBackend` | ✅ | ✅ | high | ✅ exported |
| `MemoryConfig` | ✅ | ✅ | low | ✅ exported |
| `MessageType` | ✅ | ✅ | high | ✅ exported |
| `MultiAgentExecutionConfig` | ✅ | ✅ | low | ✅ exported |
| `MultiAgentHooksConfig` | ✅ | ✅ | low | ✅ exported |
| `MultiAgentMemoryConfig` | ✅ | ✅ | low | ✅ exported |
| `MultiAgentOutputConfig` | ✅ | ✅ | low | ✅ exported |
| `MultiAgentPlanningConfig` | ✅ | ✅ | low | ✅ exported |
| `OUTPUT\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `OutputConfig` | ✅ | ✅ | low | ✅ exported |
| `OutputPreset` | ✅ | ✅ | high | ✅ exported |
| `PLANNING\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `PlanningConfig` | ✅ | ✅ | low | ✅ exported |
| `Plugin` | ✅ | ✅ | high | ✅ exported |
| `PluginHook` | ✅ | ✅ | high | ✅ exported |
| `PluginInfo` | ✅ | ✅ | high | ✅ exported |
| `PluginManager` | ✅ | ✅ | high | ✅ exported |
| `PluginMetadata` | ✅ | ✅ | high | ✅ exported |
| `PluginParseError` | ✅ | ✅ | low | ✅ exported |
| `PluginProtocol` | ✅ | ✅ | medium | ✅ exported |
| `PluginsConfig` | ✅ | ✅ | low | ✅ exported |
| `PraisonAIAgents` | ✅ | ✅ | high | ✅ exported |
| `PraisonConfig` | ✅ | ✅ | low | ✅ exported |
| `ProviderStatus` | ✅ | ✅ | high | ✅ exported |
| `REFLECTION\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `RagRetrievalPolicy` | ✅ | ✅ | high | ✅ exported |
| `ReflectionConfig` | ✅ | ✅ | low | ✅ exported |
| `ReflectionOutput` | ✅ | ✅ | high | ✅ exported |
| `ResourceLimits` | ✅ | ✅ | high | ✅ exported |
| `RoutingConditionProtocol` | ✅ | ✅ | medium | ✅ exported |
| `SandboxConfig` | ✅ | ✅ | low | ✅ exported |
| `SandboxProtocol` | ✅ | ✅ | medium | ✅ exported |
| `SandboxResult` | ✅ | ✅ | low | ✅ exported |
| `SandboxStatus` | ✅ | ✅ | high | ✅ exported |
| `SecurityPolicy` | ✅ | ✅ | high | ✅ exported |
| `SessionConfig` | ✅ | ✅ | low | ✅ exported |
| `SkillsConfig` | ✅ | ✅ | low | ✅ exported |
| `StopReason` | ✅ | ✅ | high | ✅ exported |
| `Task` | ✅ | ✅ | high | ✅ exported |
| `TaskOutput` | ✅ | ✅ | high | ✅ exported |
| `TemplateConfig` | ✅ | ✅ | low | ✅ exported |
| `ToolPluginProtocol` | ✅ | ✅ | medium | ✅ exported |
| `TraceSink` | ✅ | ✅ | high | ✅ exported |
| `TraceSinkProtocol` | ✅ | ✅ | medium | ✅ exported |
| `WEB\_PRESETS` | ✅ | ✅ | low | ✅ exported |
| `WebConfig` | ✅ | ✅ | low | ✅ exported |
| `WebSearchProvider` | ✅ | ✅ | high | ✅ exported |
| `aembed` | ✅ | ✅ | low | ✅ exported |
| `aembedding` | ✅ | ✅ | low | ✅ exported |
| `aembeddings` | ✅ | ✅ | low | ✅ exported |
| `apply\_config\_defaults` | ✅ | ✅ | low | ✅ exported |
| `async\_display\_callbacks` | ✅ | ✅ | low | ✅ exported |
| `clean\_triple\_backticks` | ✅ | ✅ | low | ✅ exported |
| `config` | ✅ | ✅ | low | ✅ exported |
| `detect\_url\_scheme` | ✅ | ✅ | low | ✅ exported |
| `discover\_and\_load\_plugins` | ✅ | ✅ | low | ✅ exported |
| `discover\_plugins` | ✅ | ✅ | low | ✅ exported |
| `display\_error` | ✅ | ✅ | low | ✅ exported |
| `display\_generating` | ✅ | ✅ | low | ✅ exported |
| `display\_instruction` | ✅ | ✅ | low | ✅ exported |
| `display\_interaction` | ✅ | ✅ | low | ✅ exported |
| `display\_self\_reflection` | ✅ | ✅ | low | ✅ exported |
| `display\_tool\_call` | ✅ | ✅ | low | ✅ exported |
| `embed` | ✅ | ✅ | low | ✅ exported |
| `embedding` | ✅ | ✅ | low | ✅ exported |
| `embeddings` | ✅ | ✅ | low | ✅ exported |
| `ensure\_plugin\_dir` | ✅ | ✅ | low | ✅ exported |
| `error\_logs` | ✅ | ✅ | low | ✅ exported |
| `evaluate\_condition` | ✅ | ✅ | low | ✅ exported |
| `get\_config` | ✅ | ✅ | low | ✅ exported |
| `get\_config\_path` | ✅ | ✅ | low | ✅ exported |
| `get\_default` | ✅ | ✅ | low | ✅ exported |
| `get\_default\_plugin\_dirs` | ✅ | ✅ | low | ✅ exported |
| `get\_defaults\_config` | ✅ | ✅ | low | ✅ exported |
| `get\_dimensions` | ✅ | ✅ | low | ✅ exported |
| `get\_plugin\_manager` | ✅ | ✅ | low | ✅ exported |
| `get\_plugin\_template` | ✅ | ✅ | low | ✅ exported |
| `get\_plugins\_config` | ✅ | ✅ | low | ✅ exported |
| `is\_path\_like` | ✅ | ✅ | low | ✅ exported |
| `is\_policy\_string` | ✅ | ✅ | low | ✅ exported |
| `load\_plugin` | ✅ | ✅ | low | ✅ exported |
| `memory` | ✅ | ✅ | low | ✅ exported |
| `parse\_plugin\_header` | ✅ | ✅ | low | ✅ exported |
| `parse\_plugin\_header\_from\_file` | ✅ | ✅ | low | ✅ exported |
| `parse\_policy\_string` | ✅ | ✅ | low | ✅ exported |
| `register\_display\_callback` | ✅ | ✅ | low | ✅ exported |
| `resolve` | ✅ | ✅ | low | ✅ exported |
| `resolve\_autonomy` | ✅ | ✅ | low | ✅ exported |
| `resolve\_caching` | ✅ | ✅ | low | ✅ exported |
| `resolve\_context` | ✅ | ✅ | low | ✅ exported |
| `resolve\_execution` | ✅ | ✅ | low | ✅ exported |
| `resolve\_guardrail\_policies` | ✅ | ✅ | low | ✅ exported |
| `resolve\_guardrails` | ✅ | ✅ | low | ✅ exported |
| `resolve\_hooks` | ✅ | ✅ | low | ✅ exported |
| `resolve\_knowledge` | ✅ | ✅ | low | ✅ exported |
| `resolve\_memory` | ✅ | ✅ | low | ✅ exported |
| `resolve\_output` | ✅ | ✅ | low | ✅ exported |
| `resolve\_planning` | ✅ | ✅ | low | ✅ exported |
| `resolve\_reflection` | ✅ | ✅ | low | ✅ exported |
| `resolve\_routing` | ✅ | ✅ | low | ✅ exported |
| `resolve\_skills` | ✅ | ✅ | low | ✅ exported |
| `resolve\_web` | ✅ | ✅ | low | ✅ exported |
| `suggest\_similar` | ✅ | ✅ | low | ✅ exported |
| `sync\_display\_callbacks` | ✅ | ✅ | low | ✅ exported |
| `tools` | ✅ | ✅ | low | ✅ exported |
| `trace\_context` | ✅ | ✅ | low | ✅ exported |
| `track\_workflow` | ✅ | ✅ | low | ✅ exported |
| `validate\_config` | ✅ | ✅ | low | ✅ exported |
| `workflows` | ✅ | ✅ | low | ✅ exported |

## Python Core SDK Exports

**Path:** `/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents/praisonaiagents`

<details>
<summary><strong>agent</strong> (43 exports)</summary>

```python
from praisonaiagents import Agent, AudioAgent, AudioConfig, CodeAgent, CodeConfig, CodeExecutionStep, ContextAgent, ContextPolicy, DeepResearchAgent, DeepResearchResponse...
```

</details>

<details>
<summary><strong>agents</strong> (7 exports)</summary>

```python
from praisonaiagents import AgentManager, AgentTeam, AutoAgents, AutoRagAgent, AutoRagConfig, PraisonAIAgents, RagRetrievalPolicy
```

</details>

<details>
<summary><strong>app</strong> (6 exports)</summary>

```python
from praisonaiagents import AgentAppConfig, AgentAppProtocol, AgentOSConfig, AgentOSProtocol, AutoApproveBackend, ConsoleBackend
```

</details>

<details>
<summary><strong>bots</strong> (9 exports)</summary>

```python
from praisonaiagents import BotChannel, BotConfig, BotMessage, BotOSConfig, BotOSProtocol, BotProtocol, BotUser, MessageType, PlatformCapabilities
```

</details>

<details>
<summary><strong>conditions</strong> (5 exports)</summary>

```python
from praisonaiagents import ConditionProtocol, DictCondition, ExpressionCondition, RoutingConditionProtocol, evaluate_condition
```

</details>

<details>
<summary><strong>config</strong> (78 exports)</summary>

```python
from praisonaiagents import AUTONOMY_PRESETS, ArrayMode, AutonomyLevel, CACHING_PRESETS, CONTEXT_PRESETS, CachingConfig, ChunkingStrategy, ConfigValidationError, DefaultsConfig, EXECUTION_PRESETS...
```

</details>

<details>
<summary><strong>context</strong> (8 exports)</summary>

```python
from praisonaiagents import ContextConfig, ContextManager, FastContext, FastContextResult, FileMatch, LineRange, ManagerConfig, OptimizerStrategy
```

</details>

<details>
<summary><strong>embedding</strong> (6 exports)</summary>

```python
from praisonaiagents import EmbeddingResult, aembed, aembedding, aembeddings, embed, get_dimensions
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
from praisonaiagents import GatewayClientProtocol, GatewayConfig, GatewayEvent, GatewayEventType, GatewayMessage, GatewayProtocol, GatewaySessionProtocol, SessionConfig
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
<summary><strong>other</strong> (106 exports)</summary>

```python
from praisonaiagents import AGGRESSIVE_POLICY, AgentMessageEvent, AgentRunOutcome, AgentRuntimeProtocol, Agents, AsyncLearnProtocol, AutoMemory, AutonomyConfig, BALANCED_POLICY, BackendNotAvailableError...
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
<summary><strong>skills</strong> (10 exports)</summary>

```python
from praisonaiagents import EnforcementLevel, SkillLoader, SkillManager, SkillMetadata, SkillProperties, SkillState, discover_skills, load_skill, validate, validate_metadata
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
<summary><strong>tools</strong> (11 exports)</summary>

```python
from praisonaiagents import BaseTool, FunctionTool, ToolRegistry, ToolResult, ToolValidationError, Tools, get_registry, get_tool, register_tool, tool...
```

</details>

<details>
<summary><strong>trace</strong> (10 exports)</summary>

```python
from praisonaiagents import ContextEvent, ContextEventType, ContextListSink, ContextNoOpSink, ContextTraceEmitter, ContextTraceSink, ContextTraceSinkProtocol, TraceSink, TraceSinkProtocol, trace_context
```

</details>

<details>
<summary><strong>ui</strong> (3 exports)</summary>

```python
from praisonaiagents import A2A, A2UI, AGUI
```

</details>

<details>
<summary><strong>workflows</strong> (21 exports)</summary>

```python
from praisonaiagents import AgentFlow, If, Include, Loop, MAX_NESTING_DEPTH, Parallel, Pipeline, Repeat, Route, StepResult...
```

</details>

## TypeScript SDK Exports

**Path:** `/home/runner/work/PraisonAI/PraisonAI/src/praisonai-ts/src`

<details>
<summary><strong>agent</strong> (68 exports)</summary>

```typescript
import { Agent, AgentEvent, AgentMessage, AgentStreamOptions, AgentTeam, AgentTeamConfig, Agents, AudioAgent, AudioAgentConfig, AudioProvider... } from 'praisonai';
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
import { ActionDecision, ActionRequest, ActionType, AiderAgent, ApprovalPolicy, AutonomyConfig, AutonomyManager, AutonomyMode, BaseExternalAgent, CLI_SPEC_VERSION... } from 'praisonai';
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
<summary><strong>other</strong> (203 exports)</summary>

```typescript
import { AUTONOMY_PRESETS, AgentPluginProtocol, ArrayMode, AsyncDisplayCallback, AuthProfile, AutoRagConfig, AutonomyLevel, BatchEmbeddingResult, BotChannel, BotConfig... } from 'praisonai';
```

</details>

<details>
<summary><strong>parity</strong> (65 exports)</summary>

```typescript
import { AudioConfig, Chunking, CodeAgent, CodeConfig, CodeExecutionStep, ContextConfig, ContextManager, ContextPack, DeepResearchResponse, EmbeddingAgent... } from 'praisonai';
```

</details>

<details>
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
import { AgentStats, AgentTelemetry, MetricEntry, MinimalTelemetry, PerformanceMonitor, PerformanceMonitorConfig, PerformanceStats, TelemetryCollector, TelemetryConfig, TelemetryEvent... } from 'praisonai';
```

</details>

<details>
<summary><strong>tools</strong> (89 exports)</summary>

```typescript
import { BaseTool, BudgetExceededError, DelegatorConfig, FunctionTool, InstallHints, MissingDependencyError, MissingEnvVarError, PraisonTool, RedactionHooks, RegisteredTool... } from 'praisonai';
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
