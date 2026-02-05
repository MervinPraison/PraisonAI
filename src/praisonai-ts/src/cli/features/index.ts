/**
 * CLI Features - Lazy-loaded feature modules
 */

// Slash Commands
export {
  SlashCommandHandler,
  createSlashCommandHandler,
  registerCommand,
  parseSlashCommand,
  executeSlashCommand,
  isSlashCommand,
  getRegistry,
  type SlashCommand,
  type SlashCommandContext,
  type SlashCommandResult,
  type CostTracker as SlashCostTracker
} from './slash-commands';

// Cost Tracker
export {
  CostTracker,
  createCostTracker,
  estimateTokens,
  formatCost,
  MODEL_PRICING,
  type ModelPricing,
  type TokenUsage,
  type RequestStats,
  type SessionStats
} from './cost-tracker';

// Interactive TUI
export {
  InteractiveTUI,
  createInteractiveTUI,
  StatusDisplay,
  createStatusDisplay,
  HistoryManager,
  createHistoryManager,
  type TUIConfig,
  type TUIState
} from './interactive-tui';

// Repo Map
export {
  RepoMap,
  createRepoMap,
  getRepoTree,
  DEFAULT_IGNORE_PATTERNS,
  type RepoMapConfig,
  type FileInfo,
  type SymbolInfo,
  type RepoMapResult
} from './repo-map';

// Git Integration
export {
  GitManager,
  createGitManager,
  DiffViewer,
  createDiffViewer,
  type GitConfig,
  type GitStatus,
  type GitCommit,
  type GitDiff,
  type GitDiffFile
} from './git-integration';

// Sandbox Executor
export {
  SandboxExecutor,
  createSandboxExecutor,
  sandboxExec,
  CommandValidator,
  DEFAULT_BLOCKED_COMMANDS,
  DEFAULT_BLOCKED_PATHS,
  type SandboxMode,
  type SandboxConfig,
  type ExecutionResult
} from './sandbox-executor';

// Autonomy Mode
export {
  AutonomyManager,
  createAutonomyManager,
  cliApprovalPrompt,
  MODE_POLICIES,
  type AutonomyMode,
  type ActionType,
  type ApprovalPolicy,
  type AutonomyConfig,
  type ActionRequest,
  type ActionDecision
} from './autonomy-mode';

// Scheduler
export {
  Scheduler,
  createScheduler,
  cronExpressions,
  type ScheduleConfig,
  type ScheduledTask,
  type SchedulerStats
} from './scheduler';

// Background Jobs
export {
  JobQueue,
  createJobQueue,
  MemoryJobStorage,
  FileJobStorage,
  createFileJobStorage,
  type Job,
  type JobStatus,
  type JobPriority,
  type JobQueueConfig,
  type JobStorageAdapter,
  type JobHandler,
  type JobContext
} from './background-jobs';

// Checkpoints
export {
  CheckpointManager,
  createCheckpointManager,
  MemoryCheckpointStorage,
  FileCheckpointStorage,
  createFileCheckpointStorage,
  type CheckpointData,
  type CheckpointConfig,
  type CheckpointStorage
} from './checkpoints';

// Flow Display
export {
  FlowDisplay,
  createFlowDisplay,
  renderWorkflow,
  type FlowNode,
  type FlowGraph,
  type FlowDisplayConfig
} from './flow-display';

// External Agents
export {
  BaseExternalAgent,
  ClaudeCodeAgent,
  GeminiCliAgent,
  CodexCliAgent,
  AiderAgent,
  GenericExternalAgent,
  getExternalAgentRegistry,
  createExternalAgent,
  externalAgentAsTool,
  type ExternalAgentConfig,
  type ExternalAgentResult
} from './external-agents';

// N8N Integration
export {
  N8NIntegration,
  createN8NIntegration,
  triggerN8NWebhook,
  type N8NConfig,
  type N8NWebhookPayload,
  type N8NWorkflow,
  type N8NWorkflowNode
} from './n8n-integration';

// Fast Context (Python parity with praisonaiagents/context/fast)
export {
  FastContext,
  createFastContext,
  getQuickContext,
  type FastContextConfig,
  type ContextSource,
  type FastContextResult,
  // Python parity additions
  type LineRange,
  createLineRange,
  getLineCount,
  rangesOverlap,
  mergeRanges,
  type FileMatch,
  createFileMatch,
  addLineRangeToFileMatch,
  getTotalLines,
} from './fast-context';
