"""
Feature Configuration Classes for PraisonAI Agents.

Provides dataclasses for consolidated feature configuration:
- MemoryConfig: Memory and session management
- KnowledgeConfig: RAG and knowledge retrieval
- PlanningConfig: Planning mode settings
- ReflectionConfig: Self-reflection settings
- GuardrailConfig: Safety and validation
- WebConfig: Web search and fetch
- ToolSearchConfig: Progressive tool disclosure

All configs follow the agent-centric pattern:
- False: Feature disabled (zero overhead)
- True: Feature enabled with safe defaults
- Config: Custom configuration
- Instance: Pre-configured manager/engine

Usage:
    from praisonaiagents import Agent, MemoryConfig, KnowledgeConfig, ToolSearchConfig
    
    # Simple enable
    agent = Agent(instructions="...", memory=True, tool_search=True)
    
    # With config
    agent = Agent(
        instructions="...",
        memory=MemoryConfig(backend="redis", user_id="user123"),
        knowledge=KnowledgeConfig(sources=["docs/"], rerank=True),
        tool_search=ToolSearchConfig(enabled="auto", threshold_pct=15),
    )
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Tuple, Union, FrozenSet
from enum import Enum

# Import AutonomyConfig from canonical location (no circular dep)
from ..agent.autonomy import AutonomyConfig

# TYPE_CHECKING import to avoid circular dependency
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..compaction.strategy import CompactionStrategy
    from ..context.artifact_store import FileSystemArtifactStore


class MemoryBackend(str, Enum):
    """Memory storage backends."""
    FILE = "file"
    SQLITE = "sqlite"
    REDIS = "redis"
    VALKEY = "valkey"
    POSTGRES = "postgres"
    MEM0 = "mem0"
    MONGODB = "mongodb"


class LearnScope(str, Enum):
    """Scope for learning data visibility.
    
    PRIVATE: Learning data is private to this user/agent (default, safest)
    SHARED: Learning data is shared with all agents
    """
    PRIVATE = "private"   # Private to this user/agent
    SHARED = "shared"     # Shared with all agents


class LearnMode(str, Enum):
    """Learning mode for automatic learning extraction.
    
    DISABLED: No automatic learning (manual capture only)
    AGENTIC: Agent autonomously extracts and stores learnings after each conversation
    PROPOSE: (Future) Agent proposes learnings for user approval before storing.
             Note: PROPOSE mode is defined but not yet implemented. Using it will
             behave the same as DISABLED until the approval workflow is added.
    """
    DISABLED = "disabled"
    AGENTIC = "agentic"
    PROPOSE = "propose"


class LearnBackend(str, Enum):
    """Storage backend for learning data.
    
    FILE: JSON files (default, zero dependencies)
    SQLITE: SQLite database
    REDIS: Redis (requires redis package)
    MONGODB: MongoDB (requires pymongo)
    """
    FILE = "file"
    SQLITE = "sqlite"
    REDIS = "redis"
    MONGODB = "mongodb"


@dataclass
class LearnConfig:
    """
    Configuration for continuous learning within memory system.
    
    Learning captures patterns, preferences, and insights from agent interactions
    to improve future responses. All learning data is stored within the memory system.
    
    Usage:
        # Simple enable (top-level param)
        Agent(learn=True)
        
        # With specific capabilities
        Agent(learn=LearnConfig(
            persona=True,      # User preferences
            insights=True,     # Observations
            patterns=True,     # Reusable knowledge
            mode="agentic",    # Auto-extract learnings
        ))
        
        # With database backend
        Agent(learn=LearnConfig(
            backend="sqlite",
            db_url="sqlite:///learn.db",
        ))
    """
    # Learning capabilities
    persona: bool = True       # User preferences and profile
    insights: bool = True      # Observations and learnings
    thread: bool = True        # Session/conversation context
    patterns: bool = False     # Reusable knowledge patterns
    decisions: bool = False    # Decision logging
    feedback: bool = False     # Outcome signals
    improvements: bool = False # Self-improvement proposals
    
    # Nudge mechanism (self-improving agent loop)
    nudge_interval: int = 0    # 0=disabled; N=nudge every N turns  
    nudge_min_tool_iters: int = 3  # Only nudge if agent did real work
    propose_skills: bool = False   # Enable skill_manage tool (propose mode)
    
    # Learning mode
    mode: Union[str, LearnMode] = LearnMode.DISABLED  # How to extract learnings
    
    # Scope configuration
    scope: Union[str, LearnScope] = LearnScope.PRIVATE
    
    # Storage backend configuration
    backend: Union[str, LearnBackend] = LearnBackend.FILE  # Storage backend
    db_url: Optional[str] = None  # Database connection URL (for non-file backends)
    store_path: Optional[str] = None  # Custom storage path (for file backend)
    
    # LLM for learning extraction
    llm: Optional[str] = None  # LLM model for extracting learnings (defaults to agent's LLM)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "persona": self.persona,
            "insights": self.insights,
            "thread": self.thread,
            "patterns": self.patterns,
            "decisions": self.decisions,
            "feedback": self.feedback,
            "improvements": self.improvements,
            "nudge_interval": self.nudge_interval,
            "nudge_min_tool_iters": self.nudge_min_tool_iters,
            "propose_skills": self.propose_skills,
            "mode": self.mode.value if isinstance(self.mode, LearnMode) else self.mode,
            "scope": self.scope.value if isinstance(self.scope, LearnScope) else self.scope,
            "backend": self.backend.value if isinstance(self.backend, LearnBackend) else self.backend,
            "db_url": self.db_url,
            "store_path": self.store_path,
            "llm": self.llm,
        }


@dataclass
class MemoryConfig:
    """
    Configuration for agent memory and session management.
    
    Consolidates: memory, auto_memory, claude_memory, user_id, session_id, db, learn
    
    Usage:
        # Simple enable (uses FileMemory)
        Agent(memory=True)
        
        # With backend
        Agent(memory=MemoryConfig(backend="redis"))
        
        # Full config with learning
        Agent(memory=MemoryConfig(
            backend="sqlite",
            user_id="user123",
            session_id="session456",
            auto_memory=True,
            learn=True,  # Enable continuous learning
        ))
        
        # With detailed learn config
        Agent(memory=MemoryConfig(
            learn=LearnConfig(
                persona=True,
                insights=True,
                patterns=True,
            )
        ))
    """
    # Backend selection
    backend: Union[str, MemoryBackend] = MemoryBackend.FILE
    
    # Session identification
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    
    # Auto-memory extraction
    auto_memory: bool = False
    
    # Claude-specific memory (for Anthropic models)
    claude_memory: bool = False
    
    # Database adapter (for advanced use)
    db: Optional[Any] = None
    
    # Memory configuration dict (for provider-specific settings)
    config: Optional[Dict[str, Any]] = None
    
    # Continuous learning configuration
    learn: Optional[Union[bool, LearnConfig]] = None
    
    # History injection (auto-inject session history into context)
    history: bool = False
    history_limit: int = 10
    
    # Auto-save session name (consolidated from standalone auto_save param)
    # When set, automatically saves session to memory with this name
    auto_save: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        learn_dict = None
        if self.learn is True:
            learn_dict = LearnConfig().to_dict()
        elif isinstance(self.learn, LearnConfig):
            learn_dict = self.learn.to_dict()
        elif isinstance(self.learn, dict):
            # Pass through dict directly (user provided learn config as dict)
            learn_dict = self.learn
        
        return {
            "backend": self.backend.value if isinstance(self.backend, MemoryBackend) else self.backend,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "auto_memory": self.auto_memory,
            "claude_memory": self.claude_memory,
            "config": self.config,
            "learn": learn_dict,
            "history": self.history,
            "history_limit": self.history_limit,
            "auto_save": self.auto_save,
        }


class ChunkingStrategy(str, Enum):
    """Knowledge chunking strategies."""
    FIXED = "fixed"
    SEMANTIC = "semantic"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"


@dataclass
class KnowledgeConfig:
    """
    Configuration for RAG and knowledge retrieval.
    
    Consolidates: knowledge, retrieval_config, knowledge_config, rag_config, embedder_config
    
    Usage:
        # Simple enable with sources
        Agent(knowledge=["docs/", "data.pdf"])
        
        # With config
        Agent(knowledge=KnowledgeConfig(
            sources=["docs/"],
            embedder="openai",
            chunking_strategy="semantic",
            retrieval_k=5,
            rerank=True,
        ))
        
        # With chunker config
        Agent(knowledge={
            "sources": ["docs/"],
            "chunker": {
                "type": "semantic",
                "chunk_size": 512
            }
        })
    """
    # Knowledge sources (files, directories, URLs)
    sources: List[str] = field(default_factory=list)
    
    # Embedder configuration
    embedder: str = "openai"
    embedder_config: Optional[Dict[str, Any]] = None
    
    # Chunking (direct fields)
    chunking_strategy: Union[str, ChunkingStrategy] = ChunkingStrategy.SEMANTIC
    chunk_size: int = 1000
    chunk_overlap: int = 200
    
    # Chunker config dict (alternative to direct fields)
    # Supports: {"type": "semantic", "chunk_size": 512, ...}
    chunker: Optional[Dict[str, Any]] = None
    
    # Retrieval
    retrieval_k: int = 5
    retrieval_threshold: float = 0.0
    
    # Reranking
    rerank: bool = False
    rerank_model: Optional[str] = None
    
    # Auto-retrieval (inject context automatically)
    auto_retrieve: bool = True
    
    # Vector store config dict (for vector database settings)
    # Supports: {"provider": "qdrant", "url": "...", ...}
    vector_store: Optional[Dict[str, Any]] = None
    
    # Full config dict (for advanced use)
    config: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sources": self.sources,
            "embedder": self.embedder,
            "embedder_config": self.embedder_config,
            "chunking_strategy": self.chunking_strategy.value if isinstance(self.chunking_strategy, ChunkingStrategy) else self.chunking_strategy,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "chunker": self.chunker,
            "retrieval_k": self.retrieval_k,
            "retrieval_threshold": self.retrieval_threshold,
            "rerank": self.rerank,
            "rerank_model": self.rerank_model,
            "auto_retrieve": self.auto_retrieve,
            "vector_store": self.vector_store,
            "config": self.config,
        }


@dataclass
class PlanningConfig:
    """
    Configuration for planning mode.
    
    Consolidates: planning, plan_mode, planning_tools, planning_reasoning, planning_llm
    
    Usage:
        # Simple enable
        Agent(planning=True)
        
        # With config
        Agent(planning=PlanningConfig(
            llm="gpt-4o",
            tools=[search_tool],
            reasoning=True,
            auto_approve=False,
        ))
    """
    # Planning LLM (if different from main)
    llm: Optional[str] = None
    
    # Tools available during planning
    tools: Optional[List[Any]] = None
    
    # Enable reasoning during planning
    reasoning: bool = False
    
    # Auto-approve plans without user confirmation
    auto_approve: bool = False
    
    # Read-only mode (plan_mode) - only read operations allowed
    read_only: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "llm": self.llm,
            "tools": [str(t) for t in (self.tools or [])],
            "reasoning": self.reasoning,
            "auto_approve": self.auto_approve,
            "read_only": self.read_only,
        }


@dataclass
class ReflectionConfig:
    """
    Configuration for self-reflection.
    
    Consolidates: self_reflect, max_reflect, min_reflect, reflect_llm, reflect_prompt
    
    Usage:
        # Simple enable
        Agent(reflection=True)
        
        # With config
        Agent(reflection=ReflectionConfig(
            min_iterations=1,
            max_iterations=3,
            llm="gpt-4o",
            prompt="Evaluate your response for accuracy...",
        ))
    """
    # Iteration limits
    min_iterations: int = 1
    max_iterations: int = 3
    
    # Reflection LLM (if different from main)
    llm: Optional[str] = None
    
    # Custom reflection prompt
    prompt: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "min_iterations": self.min_iterations,
            "max_iterations": self.max_iterations,
            "llm": self.llm,
            "prompt": self.prompt,
        }


class GuardrailAction(str, Enum):
    """Action to take when guardrail fails."""
    RETRY = "retry"
    SKIP = "skip"
    RAISE = "raise"


@dataclass
class GuardrailConfig:
    """
    Configuration for guardrails and safety validation.
    
    Consolidates: guardrail, max_guardrail_retries, policy
    
    Usage:
        # With validator function
        Agent(guardrails=my_validator_fn)
        
        # With string preset
        Agent(guardrails="strict")  # Uses strict preset
        
        # With policy strings
        Agent(guardrails=["policy:strict", "pii:redact"])
        
        # With config
        Agent(guardrails=GuardrailConfig(
            validator=my_validator_fn,
            max_retries=3,
            on_fail="retry",
        ))
        
        # With LLM-based validation
        Agent(guardrails=GuardrailConfig(
            llm_validator="Ensure response is helpful and safe",
            max_retries=2,
        ))
    """
    # Validator function: (TaskOutput) -> Tuple[bool, Any]
    validator: Optional[Callable[..., Tuple[bool, Any]]] = None
    
    # LLM-based validation prompt
    llm_validator: Optional[str] = None
    
    # Retry settings
    max_retries: int = 3
    on_fail: Union[str, GuardrailAction] = GuardrailAction.RETRY
    
    # Policy engine (for advanced use)
    policy: Optional[Any] = None
    
    # Policy strings (e.g., ["policy:strict", "pii:redact"])
    policies: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "validator": str(self.validator) if self.validator else None,
            "llm_validator": self.llm_validator,
            "max_retries": self.max_retries,
            "on_fail": self.on_fail.value if isinstance(self.on_fail, GuardrailAction) else self.on_fail,
            "policies": self.policies,
        }


class WebSearchProvider(str, Enum):
    """Web search providers."""
    DUCKDUCKGO = "duckduckgo"
    GOOGLE = "google"
    BING = "bing"
    TAVILY = "tavily"
    SERPER = "serper"


@dataclass
class WebConfig:
    """
    Configuration for web search and fetch capabilities.
    
    Consolidates: web_search, web_fetch
    
    Usage:
        # Simple enable
        Agent(web=True)
        
        # With config
        Agent(web=WebConfig(
            search=True,
            fetch=True,
            search_provider="duckduckgo",
            max_results=5,
        ))
    """
    # Enable web search
    search: bool = True
    
    # Enable web fetch (retrieve full page content)
    fetch: bool = True
    
    # Search provider
    search_provider: Union[str, WebSearchProvider] = WebSearchProvider.DUCKDUCKGO
    
    # Search settings
    max_results: int = 5
    
    # Search config dict (for provider-specific settings)
    search_config: Optional[Dict[str, Any]] = None
    
    # Fetch config dict
    fetch_config: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "search": self.search,
            "fetch": self.fetch,
            "search_provider": self.search_provider.value if isinstance(self.search_provider, WebSearchProvider) else self.search_provider,
            "max_results": self.max_results,
            "search_config": self.search_config,
            "fetch_config": self.fetch_config,
        }


class OutputPreset(str, Enum):
    """Output style presets."""
    MINIMAL = "minimal"
    NORMAL = "normal"
    VERBOSE = "verbose"
    DEBUG = "debug"
    SILENT = "silent"


@dataclass
class OutputConfig:
    """
    Configuration for agent output behavior.
    
    Consolidates: verbose, markdown, stream, metrics, reasoning_steps, output_style
    
    DEFAULT: output="silent" (zero overhead, fastest performance)
    
    Usage:
        # Default is silent mode (no output overhead, programmatic use)
        Agent(instructions="...")  # Uses output="silent"
        
        # Actions mode (tool calls + final output trace)
        Agent(output="actions")
        
        # Verbose mode with Rich panels
        Agent(output="verbose")
        
        # JSON mode for piping
        Agent(output="json")
        
        # With config
        Agent(output=OutputConfig(
            verbose=True,
            markdown=True,
            stream=True,
            metrics=True,
            reasoning_steps=True,
        ))
    """
    # Verbosity - False by default for silent mode (fastest)
    verbose: bool = False
    
    # Formatting - False by default for silent mode
    markdown: bool = False
    
    # Streaming
    stream: bool = False
    
    # Metrics display
    metrics: bool = False
    
    # Show reasoning steps
    reasoning_steps: bool = False
    
    # Output style (custom styling)
    style: Optional[Any] = None
    
    # Actions trace mode - shows tool calls, agent lifecycle, final output
    # When True, registers callbacks and outputs to stderr
    # DEFAULT: False for zero overhead (silent mode)
    actions_trace: bool = False
    
    # JSON output mode - emit JSONL events for piping
    json_output: bool = False
    
    # Simple output mode - just print response without panels
    simple_output: bool = False
    
    # Show LLM parameters (for debug mode)
    show_parameters: bool = False
    
    # Status trace mode - clean inline status updates
    # Shows: [timestamp] Calling LLM..., Executing tool..., Response: ...
    status_trace: bool = False
    
    # Editor output mode - beginner-friendly numbered steps
    # Shows: Step 1: 📄 Creating file: path → ✓ Done
    editor_output: bool = False
    
    # Output file - save agent response to file automatically
    # When set, saves the response to the specified file path
    output_file: Optional[str] = None
    
    # Output template - format template for the response
    # Agent will be instructed to follow this template when generating response
    # Example: "# {{title}}\n\n{{content}}\n\n---\nGenerated by AI"
    template: Optional[str] = None
    
    # Tool output limit - maximum characters for tool output
    # Default: 16000 chars (≈ 4000 tokens) to prevent runaway tool outputs
    tool_output_limit: int = 16000

    def __post_init__(self) -> None:
        if not isinstance(self.tool_output_limit, int) or self.tool_output_limit <= 0:
            raise ValueError(
                "OutputConfig.tool_output_limit must be a positive integer."
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "verbose": self.verbose,
            "markdown": self.markdown,
            "stream": self.stream,
            "metrics": self.metrics,
            "reasoning_steps": self.reasoning_steps,
            "actions_trace": self.actions_trace,
            "json_output": self.json_output,
            "simple_output": self.simple_output,
            "show_parameters": self.show_parameters,
            "status_trace": self.status_trace,
            "editor_output": self.editor_output,
            "output_file": self.output_file,
            "template": self.template,
            "tool_output_limit": self.tool_output_limit,
        }


class ExecutionPreset(str, Enum):
    """Execution mode presets."""
    FAST = "fast"
    BALANCED = "balanced"
    THOROUGH = "thorough"
    UNLIMITED = "unlimited"


@dataclass
class ExecutionConfig:
    """
    Configuration for agent execution limits.
    
    Consolidates: max_iter, max_rpm, max_execution_time, max_retry_limit,
                  allow_code_execution, code_execution_mode, rate_limiter
    
    Usage:
        # Simple preset
        Agent(execution="thorough")
        
        # With config
        Agent(execution=ExecutionConfig(
            max_iter=50,
            max_rpm=100,
            max_execution_time=300,
            max_retry_limit=5,
        ))
        
        # With code execution and rate limiter
        Agent(execution=ExecutionConfig(
            code_execution=True,
            code_mode="safe",
            rate_limiter=my_limiter,
        ))
        
        # With token budget guard
        Agent(execution=ExecutionConfig(
            max_budget=0.50,              # Hard USD limit per agent run
            on_budget_exceeded="stop",    # "stop" | "warn" | callable
        ))
    """
    # Iteration limits
    max_iter: int = 20
    
    # Rate limiting
    max_rpm: Optional[int] = None
    
    # Time limits
    max_execution_time: Optional[int] = None
    
    # Retry settings
    max_retry_limit: int = 2
    retry_initial_delay: float = 1.0  # seconds
    retry_backoff_factor: float = 2.0
    retry_jitter: float = 0.1  # fraction of computed delay
    
    # Tool call limits (loop protection)
    max_tool_calls_per_turn: int = 10
    
    # Code execution (consolidated from allow_code_execution + code_execution_mode)
    code_execution: bool = False
    code_mode: str = "safe"  # "safe" or "unsafe"
    
    # Code execution sandbox mode - "sandbox" (default) uses subprocess isolation
    # "direct" runs in current process (legacy, less secure)
    code_sandbox_mode: str = "sandbox"  # "sandbox" or "direct"
    
    # Rate limiter instance (consolidated from standalone rate_limiter param)
    rate_limiter: Optional[Any] = None

    # Context compaction: automatically compact chat_history when approaching token limit.
    # DEFAULT CHANGED: Previously False, now True (with deprecation warning period).
    # Usage: Agent(execution=ExecutionConfig(context_compaction=False))  # to disable
    # Or: Agent(execution=ExecutionConfig(context_compaction=my_policy))  # custom policy
    context_compaction: Union[bool, "ContextCompactionPolicy"] = False  # Keep False during deprecation period

    # Token limit before compaction triggers. None = auto-detect from model metadata.
    max_context_tokens: Optional[int] = None
    
    # Compaction strategy to use when context_compaction is enabled.
    # Defaults to TRUNCATE for backward compatibility.
    compaction_strategy: Optional["CompactionStrategy"] = None

    # Token budget guard — hard dollar limit per agent run.
    # None = disabled (zero overhead). Float = max USD spend.
    max_budget: Optional[float] = None

    # Action when budget exceeded: "stop" (default) raises BudgetExceededError,
    # "warn" logs warning but continues, or callable(total_cost, max_budget).
    on_budget_exceeded: Any = "stop"
    
    # Parallel tool execution (Gap 2): Enable parallel execution of batched LLM tool calls
    # When True, multiple tool calls from LLM are executed concurrently instead of sequentially
    # Default False preserves existing behavior for backward compatibility
    parallel_tool_calls: bool = False

    def __post_init__(self) -> None:
        """Post-initialization processing with deprecation warnings and validation."""
        # Handle context_compaction serialization round-trip
        if isinstance(self.context_compaction, dict):
            from ..context.policy import ContextCompactionPolicy
            self.context_compaction = ContextCompactionPolicy.from_dict(
                self.context_compaction
            )
        
        # Emit deprecation warning once per process for default behavior change.
        # Walk the stack once — dataclass __init__ uses caller filename "<string>".
        if self.context_compaction is False:
            if getattr(ExecutionConfig, '_context_compaction_internal', False):
                return
            if getattr(ExecutionConfig, '_context_compaction_warned', False):
                return
            import warnings
            import inspect
            _INTERNAL = ('praisonaiagents', 'test_', '__pycache__')
            frame = inspect.currentframe()
            try:
                caller = frame.f_back if frame else None
                is_internal = False
                while caller is not None:
                    if any(p in caller.f_code.co_filename for p in _INTERNAL):
                        is_internal = True
                        break
                    caller = caller.f_back
                if is_internal:
                    ExecutionConfig._context_compaction_internal = True
                    return
                warnings.warn(
                    "ExecutionConfig.context_compaction will default to True in the next "
                    "release for proactive context overflow protection. To disable, explicitly "
                    "set context_compaction=False. To use the new default early, set "
                    "context_compaction=True.",
                    DeprecationWarning,
                    stacklevel=3,
                )
                ExecutionConfig._context_compaction_warned = True
            finally:
                del frame
        
        # Validate retry configuration parameters
        if self.retry_initial_delay <= 0:
            raise ValueError("ExecutionConfig.retry_initial_delay must be positive.")
        if self.retry_backoff_factor < 1.0:
            raise ValueError("ExecutionConfig.retry_backoff_factor must be >= 1.0.")
        if self.retry_jitter < 0:
            raise ValueError("ExecutionConfig.retry_jitter must be non-negative.")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_iter": self.max_iter,
            "max_rpm": self.max_rpm,
            "max_execution_time": self.max_execution_time,
            "max_retry_limit": self.max_retry_limit,
            "retry_initial_delay": self.retry_initial_delay,
            "retry_backoff_factor": self.retry_backoff_factor,
            "retry_jitter": self.retry_jitter,
            "code_execution": self.code_execution,
            "code_mode": self.code_mode,
            "code_sandbox_mode": self.code_sandbox_mode,
            "context_compaction": (
                self.context_compaction.to_dict() 
                if hasattr(self.context_compaction, 'to_dict') 
                else self.context_compaction
            ),
            "max_context_tokens": self.max_context_tokens,
            "compaction_strategy": self.compaction_strategy.value if self.compaction_strategy and hasattr(self.compaction_strategy, 'value') else (str(self.compaction_strategy) if self.compaction_strategy else None),
            "max_budget": self.max_budget,
            "parallel_tool_calls": self.parallel_tool_calls,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionConfig":
        """Create ExecutionConfig from dictionary."""
        # Handle context_compaction policy restoration
        context_compaction = data.get("context_compaction", False)
        if isinstance(context_compaction, dict):
            from ..context.policy import ContextCompactionPolicy
            context_compaction = ContextCompactionPolicy.from_dict(context_compaction)
        
        return cls(
            max_iter=data.get("max_iter", 20),
            max_rpm=data.get("max_rpm", None),
            max_execution_time=data.get("max_execution_time", None),
            max_retry_limit=data.get("max_retry_limit", 2),
            code_execution=data.get("code_execution", False),
            code_mode=data.get("code_mode", "safe"),
            code_sandbox_mode=data.get("code_sandbox_mode", "docker"),
            context_compaction=context_compaction,
            max_context_tokens=data.get("max_context_tokens", None),
            max_budget=data.get("max_budget", None),
            parallel_tool_calls=data.get("parallel_tool_calls", False),
        )


@dataclass
class LLMConfig:
    """
    Configuration for LLM model settings.
    
    Groups all LLM-related parameters including model selection, 
    API settings, and fallback configuration.
    
    Usage:
        # With primary model only
        Agent(llm_config=LLMConfig(model="gpt-4o"))
        
        # With fallback chain
        Agent(llm_config=LLMConfig(
            model="gpt-4o",
            fallback_models=["claude-3-5-sonnet", "gpt-4o-mini"],
            base_url="https://api.example.com",
            api_key="sk-...",
        ))
        
        # With LiteLLM-style provider prefix
        Agent(llm_config=LLMConfig(
            model="anthropic/claude-3-5-sonnet",
            fallback_models=["openai/gpt-4o", "openai/gpt-4o-mini"],
        ))
    """
    # Primary model to use (required)
    model: str
    
    # Ordered fallback models for resilience (optional)
    fallback_models: Optional[List[str]] = None
    
    # API endpoint override (optional)
    base_url: Optional[str] = None
    
    # API key (optional, defaults to env vars)
    api_key: Optional[str] = None
    
    # Additional auth headers (optional)
    auth: Optional[Dict[str, str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model": self.model,
            "fallback_models": list(self.fallback_models) if self.fallback_models else None,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "auth": dict(self.auth) if self.auth else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMConfig":
        """Create LLMConfig from dictionary."""
        return cls(
            model=data["model"],
            fallback_models=list(data["fallback_models"]) if data.get("fallback_models") else None,
            base_url=data.get("base_url"),
            api_key=data.get("api_key"),
            auth=dict(data["auth"]) if data.get("auth") else None,
        )


@dataclass  
class ToolConfig:
    """
    Configuration for tool execution behavior.
    
    Configuration for tool execution behavior including timeout, retry policy, parallel execution,
    and artifact storage for large outputs.
    
    Usage:
        # Simple enable with defaults
        Agent(tool_config=ToolConfig())
        
        # With custom settings
        Agent(tool_config=ToolConfig(
            timeout=60,
            retry_policy=RetryPolicy(max_attempts=5),
            parallel=True,
        ))
        
        # With artifact storage for large outputs
        Agent(tool_config=ToolConfig(
            output_limit=32000,
            enable_artifacts=True,
            artifact_retention_days=14,
        ))
    """
    # Tool execution timeout in seconds  
    timeout: Optional[int] = None
    
    # Retry policy for tool execution with exponential backoff
    retry_policy: Optional[Any] = None  # RetryPolicy instance
    
    # Enable parallel execution of batched LLM tool calls
    parallel: bool = False
    
    # Tool output handling and artifact storage
    output_limit: int = 16000  # Maximum bytes before spilling to artifact store
    output_max_lines: Optional[int] = None  # Maximum lines before spilling
    output_direction: str = "both"  # Truncation direction: "head", "tail", or "both"
    enable_artifacts: bool = False  # Whether to enable artifact storage (default False for backward compat)
    artifact_retention_days: int = 7  # Days to retain artifacts before garbage collection
    artifact_store: Optional[Any] = None  # Custom artifact store instance
    redact_secrets: bool = True  # Whether to redact secrets from artifacts
    
    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.output_limit <= 0:
            raise ValueError("tool_config.output_limit must be > 0")
        if self.output_max_lines is not None and self.output_max_lines <= 0:
            raise ValueError("tool_config.output_max_lines must be > 0 when provided")
        if self.output_direction not in {"head", "tail", "both"}:
            raise ValueError("tool_config.output_direction must be one of: 'head', 'tail', 'both'")
        if self.artifact_retention_days < 0:
            raise ValueError("tool_config.artifact_retention_days must be >= 0")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timeout": self.timeout,
            "retry_policy": (
                self.retry_policy.to_dict()
                if hasattr(self.retry_policy, 'to_dict')
                else self.retry_policy
            ),
            "parallel": self.parallel,
            "output_limit": self.output_limit,
            "output_max_lines": self.output_max_lines,
            "output_direction": self.output_direction,
            "enable_artifacts": self.enable_artifacts,
            "artifact_retention_days": self.artifact_retention_days,
            "artifact_store": self.artifact_store,
            "redact_secrets": self.redact_secrets,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolConfig":
        """Create ToolConfig from dictionary."""
        retry_policy = data.get("retry_policy")
        if isinstance(retry_policy, dict):
            try:
                from ..tools.retry import RetryPolicy
                retry_policy = RetryPolicy.from_dict(retry_policy)
            except ImportError:
                # Keep as dict if RetryPolicy not available
                pass
                
        return cls(
            timeout=data.get("timeout"),
            retry_policy=retry_policy,
            parallel=data.get("parallel", False),
            output_limit=data.get("output_limit", 16000),
            output_max_lines=data.get("output_max_lines"),
            output_direction=data.get("output_direction", "both"),
            enable_artifacts=data.get("enable_artifacts", False),
            artifact_retention_days=data.get("artifact_retention_days", 7),
            artifact_store=data.get("artifact_store"),
            redact_secrets=data.get("redact_secrets", True),
        )


@dataclass
class TemplateConfig:
    """
    Configuration for prompt templates.
    
    Consolidates: system_template, prompt_template, response_template, use_system_prompt
    
    Usage:
        Agent(templates=TemplateConfig(
            system="You are a helpful assistant...",
            prompt="User query: {input}",
            response="Response format...",
            use_system_prompt=True,
        ))
    """
    # Templates
    system: Optional[str] = None
    prompt: Optional[str] = None
    response: Optional[str] = None
    
    # System prompt behavior
    use_system_prompt: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "system": self.system,
            "prompt": self.prompt,
            "response": self.response,
            "use_system_prompt": self.use_system_prompt,
        }


@dataclass
class CachingConfig:
    """
    Configuration for caching behavior.
    
    Consolidates: cache, prompt_caching
    
    Usage:
        # Simple enable
        Agent(caching=True)
        
        # With config
        Agent(caching=CachingConfig(
            enabled=True,
            prompt_caching=True,
        ))
    """
    # Response caching
    enabled: bool = True
    
    # Prompt caching (provider-specific)
    prompt_caching: Optional[bool] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "prompt_caching": self.prompt_caching,
        }


@dataclass
class HooksConfig:
    """
    Configuration for agent hooks/callbacks.
    
    Consolidates: hooks, step_callback
    
    Usage:
        Agent(hooks=HooksConfig(
            on_step=my_step_callback,
            on_tool_call=my_tool_callback,
            middleware=[my_middleware],
        ))
    """
    # Step callback
    on_step: Optional[Callable] = None
    
    # Tool call callback
    on_tool_call: Optional[Callable] = None
    
    # Middleware list
    middleware: List[Any] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "on_step": str(self.on_step) if self.on_step else None,
            "on_tool_call": str(self.on_tool_call) if self.on_tool_call else None,
            "middleware": [str(m) for m in self.middleware],
        }


@dataclass
class SkillsConfig:
    """
    Configuration for agent skills.
    
    Consolidates: skills, skills_dirs
    
    Usage:
        # Simple list
        Agent(skills=["./my-skill", "code-review"])
        
        # With config
        Agent(skills=SkillsConfig(
            paths=["./my-skill"],
            dirs=["~/.praisonai/skills/"],
            auto_discover=True,
        ))
    """
    # Direct skill paths
    paths: List[str] = field(default_factory=list)
    
    # Directories to scan for skills
    dirs: List[str] = field(default_factory=list)
    
    # Auto-discover from default locations
    auto_discover: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "paths": self.paths,
            "dirs": self.dirs,
            "auto_discover": self.auto_discover,
        }


@dataclass
class MultiAgentHooksConfig:
    """
    Configuration for multi-agent orchestration hooks/callbacks.
    
    Consolidates: completion_checker, on_task_start, on_task_complete
    
    Usage:
        AgentManager(
            agents=[...],
            hooks=MultiAgentHooksConfig(
                on_task_start=my_start_callback,
                on_task_complete=my_complete_callback,
                completion_checker=my_checker,
            )
        )
    """
    # Task lifecycle callbacks
    on_task_start: Optional[Callable] = None
    on_task_complete: Optional[Callable] = None
    
    # Custom completion checker
    completion_checker: Optional[Callable] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "on_task_start": str(self.on_task_start) if self.on_task_start else None,
            "on_task_complete": str(self.on_task_complete) if self.on_task_complete else None,
            "completion_checker": str(self.completion_checker) if self.completion_checker else None,
        }


@dataclass
class MultiAgentOutputConfig:
    """
    Configuration for multi-agent output behavior.
    
    Consolidates: verbose, stream
    
    Usage:
        # Simple preset
        AgentManager(agents=[...], output="verbose")
        
        # With config
        AgentManager(
            agents=[...],
            output=MultiAgentOutputConfig(verbose=2, stream=True)
        )
    """
    # Verbosity level (0=silent, 1=minimal, 2+=verbose)
    verbose: int = 0
    
    # Streaming output - False by default for sync multi-agent compatibility
    stream: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "verbose": self.verbose,
            "stream": self.stream,
        }


@dataclass
class MultiAgentExecutionConfig:
    """
    Configuration for multi-agent execution limits.
    
    Consolidates: max_iter, max_retries
    
    Usage:
        AgentManager(
            agents=[...],
            execution=MultiAgentExecutionConfig(max_iter=20, max_retries=5)
        )
    """
    # Maximum iterations per task
    max_iter: int = 10
    
    # Maximum retries on failure
    max_retries: int = 5
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_iter": self.max_iter,
            "max_retries": self.max_retries,
        }


@dataclass
class MultiAgentPlanningConfig:
    """
    Configuration for multi-agent planning mode.
    
    Consolidates: planning, planning_llm, auto_approve_plan, planning_tools, planning_reasoning
    
    Usage:
        # Simple enable
        AgentManager(agents=[...], planning=True)
        
        # With config
        AgentManager(
            agents=[...],
            planning=MultiAgentPlanningConfig(
                llm="gpt-4o",
                auto_approve=True,
                reasoning=True,
            )
        )
    """
    # Planning LLM model
    llm: Optional[str] = None
    
    # Auto-approve generated plans
    auto_approve: bool = False
    
    # Planning tools
    tools: Optional[List[Any]] = None
    
    # Enable reasoning in planning
    reasoning: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "llm": self.llm,
            "auto_approve": self.auto_approve,
            "tools": self.tools,
            "reasoning": self.reasoning,
        }


@dataclass
class MultiAgentMemoryConfig:
    """
    Configuration for multi-agent shared memory.
    
    Consolidates: memory, memory_config, embedder, user_id
    
    Usage:
        # Simple enable
        AgentManager(agents=[...], memory=True)
        
        # With config
        AgentManager(
            agents=[...],
            memory=MultiAgentMemoryConfig(
                user_id="user123",
                embedder={"provider": "openai"},
                config={"provider": "rag"},
            )
        )
    """
    # User identification
    user_id: Optional[str] = None
    
    # Embedder configuration
    embedder: Optional[Any] = None
    
    # Memory provider config
    config: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "user_id": self.user_id,
            "embedder": self.embedder,
            "config": self.config,
        }


# Import ToolSearchConfig from tools module to avoid duplication
def __get_tool_search_config():
    try:
        from ..tools.tool_search import ToolSearchConfig as _ToolSearchConfig
        return _ToolSearchConfig
    except ImportError:
        # Fallback minimal config if tools module not available
        @dataclass
        class FallbackToolSearchConfig:
            enabled: Union[bool, str] = "auto"
            threshold_pct: float = 10.0
            search_default_limit: int = 5
            max_search_limit: int = 20
            core_tools: Optional[FrozenSet[str]] = None
        return FallbackToolSearchConfig

ToolSearchConfig = __get_tool_search_config()


class AutonomyLevel(str, Enum):
    """Autonomy levels for agent behavior."""
    SUGGEST = "suggest"
    AUTO_EDIT = "auto_edit"
    FULL_AUTO = "full_auto"

# Type aliases for Union types used in Agent.__init__
MemoryParam = Union[bool, MemoryConfig, Any]  # Any = MemoryManager instance
KnowledgeParam = Union[bool, List[str], KnowledgeConfig, Any]  # Any = KnowledgeBase instance
PlanningParam = Union[bool, PlanningConfig]
ReflectionParam = Union[bool, ReflectionConfig]
GuardrailParam = Union[bool, Callable[..., Tuple[bool, Any]], GuardrailConfig, Any]  # Any = GuardrailEngine
WebParam = Union[bool, WebConfig]
OutputParam = Union[str, OutputConfig]  # str = preset name
ExecutionParam = Union[str, ExecutionConfig]  # str = preset name
TemplateParam = TemplateConfig
CachingParam = Union[bool, CachingConfig]
HooksParam = Union[List[Any], HooksConfig]
SkillsParam = Union[List[str], SkillsConfig]
AutonomyParam = Union[bool, Dict[str, Any], "AutonomyConfig"]
ToolSearchParam = Union[bool, str, Dict[str, Any], ToolSearchConfig]
ToolParam = Union[bool, ToolConfig]  # bool = defaults, ToolConfig = custom


# =============================================================================
# PRECEDENCE LADDER RESOLVERS
# =============================================================================
# Precedence: Instance > Config > Array > Dict > String > Bool > Default
#
# These resolvers normalize various input types into the canonical Config form.
# This allows users to pass simplified inputs while maintaining type safety.


def resolve_memory(value: MemoryParam) -> Optional[MemoryConfig]:
    """
    Resolve memory= parameter following precedence ladder.
    
    Delegates to the canonical resolver in param_resolver.py with
    special handling for backward compatibility.
    
    Args:
        value: Memory parameter in any supported form
        
    Returns:
        MemoryConfig if enabled, None if disabled
    """
    from .param_resolver import resolve_memory as _resolve
    
    # Special case: handle string backends not in MEMORY_PRESETS
    if isinstance(value, str):
        try:
            # Try to resolve with canonical resolver first
            return _resolve(value, MemoryConfig)
        except ValueError:
            # Fall back to old behavior for custom/unknown backends
            try:
                backend = MemoryBackend(value.lower())
            except ValueError:
                backend = value  # Allow custom backend strings
            return MemoryConfig(backend=backend)
    
    # Special case: handle arbitrary instances with passthrough
    if not isinstance(value, (type(None), bool, dict, list, tuple, MemoryConfig)):
        # Try canonical resolver first
        result = _resolve(value, MemoryConfig)
        # If canonical resolver returns None for an instance, pass it through
        if result is None and hasattr(value, '__class__'):
            return value
        return result
    
    # Default: use canonical resolver
    return _resolve(value, MemoryConfig)


def resolve_knowledge(value: KnowledgeParam) -> Optional[KnowledgeConfig]:
    """
    Resolve knowledge= parameter following precedence ladder.
    
    Delegates to the canonical resolver in param_resolver.py.
    Kept for backward compatibility with tests.
    
    Args:
        value: Knowledge parameter in any supported form
        
    Returns:
        KnowledgeConfig if enabled, None if disabled
    """
    from .param_resolver import resolve_knowledge as _resolve
    return _resolve(value, KnowledgeConfig)


def resolve_planning(value: PlanningParam) -> Optional[PlanningConfig]:
    """
    Resolve planning= parameter following precedence ladder.
    
    Delegates to the canonical resolver in param_resolver.py.
    Kept for backward compatibility with tests.
    """
    from .param_resolver import resolve_planning as _resolve
    return _resolve(value, PlanningConfig)


def resolve_reflection(value: ReflectionParam) -> Optional[ReflectionConfig]:
    """
    Resolve reflection= parameter following precedence ladder.
    
    Delegates to the canonical resolver in param_resolver.py.
    Kept for backward compatibility with tests.
    """
    from .param_resolver import resolve_reflection as _resolve
    return _resolve(value, ReflectionConfig)


def resolve_guardrails(value: GuardrailParam) -> Optional[GuardrailConfig]:
    """
    Resolve guardrails= parameter following precedence ladder.
    
    Delegates to the canonical resolver in param_resolver.py with
    special handling for callable validators.
    """
    from .param_resolver import resolve_guardrails as _resolve
    
    # Special case: wrap callable in GuardrailConfig for backward compatibility
    if callable(value) and not isinstance(value, type):
        return GuardrailConfig(validator=value)
    
    # Default: use canonical resolver
    return _resolve(value, GuardrailConfig)


def resolve_web(value: WebParam) -> Optional[WebConfig]:
    """
    Resolve web= parameter following precedence ladder.
    
    Delegates to the canonical resolver in param_resolver.py.
    Kept for backward compatibility with tests.
    """
    from .param_resolver import resolve_web as _resolve
    return _resolve(value, WebConfig)



def resolve_caching(value: CachingParam) -> Optional[CachingConfig]:
    """
    Resolve caching= parameter following precedence ladder.
    
    Delegates to the canonical resolver in param_resolver.py.
    Kept for backward compatibility with tests.
    """
    from .param_resolver import resolve_caching as _resolve
    return _resolve(value, CachingConfig)


def resolve_autonomy(value: AutonomyParam) -> Optional[AutonomyConfig]:
    """
    Resolve autonomy= parameter following precedence ladder.
    
    Delegates to the canonical resolver in param_resolver.py.
    Kept for backward compatibility with tests.
    """
    from .param_resolver import resolve_autonomy as _resolve
    return _resolve(value, AutonomyConfig)


def resolve_tool_search(value: ToolSearchParam) -> Optional[ToolSearchConfig]:
    """
    Resolve tool_search= parameter following precedence ladder.
    
    NOTE: This resolver has zero references in the codebase but is kept
    for backward compatibility. Consider removing in a future version.
    """
    # Simple implementation since it's unused
    if value is None or value is False:
        return None
    if value is True:
        return ToolSearchConfig()
    if isinstance(value, str):
        return ToolSearchConfig(enabled=value)
    if isinstance(value, dict):
        return ToolSearchConfig(**value)
    if isinstance(value, ToolSearchConfig):
        return value
    return value


def resolve_tools(value: ToolParam) -> Optional[ToolConfig]:
    """Resolve tools= parameter following precedence ladder."""
    if value is None or value is False:
        return None
    if value is True:
        return ToolConfig()
    if isinstance(value, dict):
        return ToolConfig.from_dict(value)
    if isinstance(value, ToolConfig):
        return value
    return value


@dataclass
class RuntimeConfig:
    """
    Configuration for agent runtime capabilities and requirements.
    
    Used to declare what capabilities an agent requires and validate
    against runtime implementations at config/selection time.
    
    Usage:
        # Agent that requires native hooks and streaming
        Agent(
            instructions="...",
            runtime=RuntimeConfig(
                required_capabilities={"native_hooks", "streaming_deltas"}
            )
        )
        
        # Agent with runtime preference  
        Agent(
            runtime=RuntimeConfig(
                preferred_runtime="native",
                required_capabilities={"tool_loop", "mcp_tools"},
                fallback_allowed=True
            )
        )
    """
    # Required capabilities for this agent (capability names or enum values)
    required_capabilities: Optional[Union[List[str], FrozenSet[str], List[Any], FrozenSet[Any]]] = None
    
    # Preferred runtime implementation name
    preferred_runtime: Optional[str] = None
    
    # Whether to allow fallback to other runtimes if preferred is unavailable
    fallback_allowed: bool = True
    
    # Fail fast validation (validate at agent creation vs first execution) 
    validate_on_creation: bool = True
    
    # Additional runtime metadata/hints
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Normalize required_capabilities to a list."""
        if self.required_capabilities is not None:
            if isinstance(self.required_capabilities, str):
                self.required_capabilities = [self.required_capabilities]
            else:
                try:
                    self.required_capabilities = list(self.required_capabilities)
                except TypeError:
                    self.required_capabilities = [self.required_capabilities]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        req_caps = None
        if self.required_capabilities:
            req_caps = [
                cap.name.lower() if hasattr(cap, "name") else str(cap)
                for cap in self.required_capabilities
            ]
        return {
            "required_capabilities": req_caps,
            "preferred_runtime": self.preferred_runtime,
            "fallback_allowed": self.fallback_allowed,
            "validate_on_creation": self.validate_on_creation,
            "metadata": self.metadata,
        }


# Type aliases for runtime parameters
RuntimeParam = Union[bool, str, Dict[str, Any], RuntimeConfig, None]


def resolve_runtime(value: RuntimeParam) -> Optional[RuntimeConfig]:
    """Resolve runtime= parameter following precedence ladder."""
    if value is None or value is False:
        return None
    if value is True:
        return RuntimeConfig()
    if isinstance(value, str):
        return RuntimeConfig(preferred_runtime=value)
    if isinstance(value, (list, set, tuple, frozenset)):
        return RuntimeConfig(required_capabilities=list(value))
    if isinstance(value, dict):
        return RuntimeConfig(**value)
    if isinstance(value, RuntimeConfig):
        return value
    raise TypeError(
        f"Invalid runtime parameter type: {type(value).__name__}. "
        "Expected None/False, True, str, list, set, dict, or RuntimeConfig."
    )


__all__ = [
    # Enums
    "MemoryBackend",
    "LearnScope",
    "ChunkingStrategy",
    "GuardrailAction",
    "WebSearchProvider",
    "OutputPreset",
    "ExecutionPreset",
    "AutonomyLevel",
    # Config classes (Agent)
    "LearnConfig",
    "MemoryConfig",
    "KnowledgeConfig",
    "PlanningConfig",
    "ReflectionConfig",
    "GuardrailConfig",
    "WebConfig",
    "OutputConfig",
    "ExecutionConfig",
    "ToolConfig",
    "TemplateConfig",
    "CachingConfig",
    "HooksConfig",
    "SkillsConfig",
    "AutonomyConfig",
    "ToolSearchConfig",
    "RuntimeConfig",
    # Config classes (Multi-Agent)
    "MultiAgentHooksConfig",
    "MultiAgentOutputConfig",
    "MultiAgentExecutionConfig",
    "MultiAgentPlanningConfig",
    "MultiAgentMemoryConfig",
    # Type aliases
    "MemoryParam",
    "KnowledgeParam",
    "PlanningParam",
    "ReflectionParam",
    "GuardrailParam",
    "WebParam",
    "OutputParam",
    "ExecutionParam",
    "TemplateParam",
    "CachingParam",
    "HooksParam",
    "SkillsParam",
    "AutonomyParam",
    "ToolSearchParam", 
    "ToolParam",
    "RuntimeParam",
    # Precedence ladder resolvers
    "resolve_memory",
    "resolve_knowledge",
    "resolve_planning",
    "resolve_reflection",
    "resolve_guardrails",
    "resolve_web",
    "resolve_caching",
    "resolve_autonomy",
    "resolve_tool_search",
    "resolve_tools",
    "resolve_runtime",
]
