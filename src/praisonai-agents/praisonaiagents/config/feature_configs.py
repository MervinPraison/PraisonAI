"""
Feature Configuration Classes for PraisonAI Agents.

Provides dataclasses for consolidated feature configuration:
- MemoryConfig: Memory and session management
- KnowledgeConfig: RAG and knowledge retrieval
- PlanningConfig: Planning mode settings
- ReflectionConfig: Self-reflection settings
- GuardrailConfig: Safety and validation
- WebConfig: Web search and fetch

All configs follow the agent-centric pattern:
- False: Feature disabled (zero overhead)
- True: Feature enabled with safe defaults
- Config: Custom configuration
- Instance: Pre-configured manager/engine

Usage:
    from praisonaiagents import Agent, MemoryConfig, KnowledgeConfig
    
    # Simple enable
    agent = Agent(instructions="...", memory=True)
    
    # With config
    agent = Agent(
        instructions="...",
        memory=MemoryConfig(backend="redis", user_id="user123"),
        knowledge=KnowledgeConfig(sources=["docs/"], rerank=True),
    )
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Tuple, Union
from enum import Enum


class MemoryBackend(str, Enum):
    """Memory storage backends."""
    FILE = "file"
    SQLITE = "sqlite"
    REDIS = "redis"
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


@dataclass
class LearnConfig:
    """
    Configuration for continuous learning within memory system.
    
    Learning captures patterns, preferences, and insights from agent interactions
    to improve future responses. All learning data is stored within the memory system.
    
    Usage:
        # Simple enable
        Agent(memory=MemoryConfig(learn=True))
        
        # With specific capabilities
        Agent(memory=MemoryConfig(
            learn=LearnConfig(
                persona=True,      # User preferences
                insights=True,     # Observations
                patterns=True,     # Reusable knowledge
            )
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
    
    # Scope configuration
    scope: Union[str, LearnScope] = LearnScope.PRIVATE
    
    # Storage configuration
    store_path: Optional[str] = None  # Custom storage path
    
    # Maintenance settings
    auto_consolidate: bool = True     # Auto-consolidate learnings
    retention_days: Optional[int] = None  # Days to retain (None = forever)
    
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
            "scope": self.scope.value if isinstance(self.scope, LearnScope) else self.scope,
            "store_path": self.store_path,
            "auto_consolidate": self.auto_consolidate,
            "retention_days": self.retention_days,
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        learn_dict = None
        if self.learn is True:
            learn_dict = LearnConfig().to_dict()
        elif isinstance(self.learn, LearnConfig):
            learn_dict = self.learn.to_dict()
        
        return {
            "backend": self.backend.value if isinstance(self.backend, MemoryBackend) else self.backend,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "auto_memory": self.auto_memory,
            "claude_memory": self.claude_memory,
            "config": self.config,
            "learn": learn_dict,
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
    
    # Output file - save agent response to file automatically
    # When set, saves the response to the specified file path
    output_file: Optional[str] = None
    
    # Output template - format template for the response
    # Agent will be instructed to follow this template when generating response
    # Example: "# {{title}}\n\n{{content}}\n\n---\nGenerated by AI"
    template: Optional[str] = None
    
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
            "output_file": self.output_file,
            "template": self.template,
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
    
    Consolidates: max_iter, max_rpm, max_execution_time, max_retry_limit
    
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
    """
    # Iteration limits
    max_iter: int = 20
    
    # Rate limiting
    max_rpm: Optional[int] = None
    
    # Time limits
    max_execution_time: Optional[int] = None
    
    # Retry settings
    max_retry_limit: int = 2
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_iter": self.max_iter,
            "max_rpm": self.max_rpm,
            "max_execution_time": self.max_execution_time,
            "max_retry_limit": self.max_retry_limit,
        }


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
            dirs=["~/.praison/skills/"],
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
    
    # Streaming output
    stream: bool = True
    
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


class AutonomyLevel(str, Enum):
    """Autonomy levels for agent behavior."""
    SUGGEST = "suggest"
    AUTO_EDIT = "auto_edit"
    FULL_AUTO = "full_auto"


@dataclass
class AutonomyConfig:
    """
    Configuration for agent autonomy behavior.
    
    Controls escalation, doom-loop detection, and approval policies.
    
    Usage:
        # Simple enable
        Agent(autonomy=True)
        
        # With config
        Agent(autonomy=AutonomyConfig(
            level="auto_edit",
            escalation_enabled=True,
            doom_loop_detection=True,
            max_consecutive_failures=3,
        ))
    """
    # Autonomy level
    level: Union[str, AutonomyLevel] = AutonomyLevel.SUGGEST
    
    # Escalation pipeline
    escalation_enabled: bool = True
    escalation_threshold: int = 3
    
    # Doom loop detection
    doom_loop_detection: bool = True
    max_consecutive_failures: int = 3
    
    # Approval policies
    require_approval_for_writes: bool = True
    require_approval_for_shell: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "level": self.level.value if isinstance(self.level, AutonomyLevel) else self.level,
            "escalation_enabled": self.escalation_enabled,
            "escalation_threshold": self.escalation_threshold,
            "doom_loop_detection": self.doom_loop_detection,
            "max_consecutive_failures": self.max_consecutive_failures,
            "require_approval_for_writes": self.require_approval_for_writes,
            "require_approval_for_shell": self.require_approval_for_shell,
        }


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
AutonomyParam = Union[bool, Dict[str, Any], AutonomyConfig]


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
    
    Precedence: Instance > Config > Dict > String > Bool > Default
    
    Args:
        value: Memory parameter in any supported form
        
    Returns:
        MemoryConfig if enabled, None if disabled
        
    Examples:
        >>> resolve_memory(None)  # Default: disabled
        None
        >>> resolve_memory(False)  # Explicit disable
        None
        >>> resolve_memory(True)  # Enable with defaults
        MemoryConfig(backend='file')
        >>> resolve_memory("redis")  # String shorthand
        MemoryConfig(backend='redis')
        >>> resolve_memory({"backend": "sqlite", "user_id": "alice"})  # Dict
        MemoryConfig(backend='sqlite', user_id='alice')
        >>> resolve_memory(MemoryConfig(backend="postgres"))  # Config passthrough
        MemoryConfig(backend='postgres')
    """
    # Default: disabled
    if value is None:
        return None
    
    # Bool: False = disabled, True = defaults
    if value is False:
        return None
    if value is True:
        return MemoryConfig()
    
    # String: backend shorthand
    if isinstance(value, str):
        try:
            backend = MemoryBackend(value.lower())
        except ValueError:
            backend = value  # Allow custom backend strings
        return MemoryConfig(backend=backend)
    
    # Dict: expand to config
    if isinstance(value, dict):
        # Handle backend enum conversion
        backend = value.get("backend", MemoryBackend.FILE)
        if isinstance(backend, str):
            try:
                backend = MemoryBackend(backend.lower())
            except ValueError:
                pass  # Keep as string for custom backends
        return MemoryConfig(
            backend=backend,
            user_id=value.get("user_id"),
            session_id=value.get("session_id"),
            auto_memory=value.get("auto_memory", False),
            claude_memory=value.get("claude_memory", False),
            db=value.get("db"),
            config=value.get("config"),
        )
    
    # Config: passthrough
    if isinstance(value, MemoryConfig):
        return value
    
    # Instance (MemoryManager): return as-is (caller handles)
    # This is the highest precedence - user provided a pre-configured instance
    return value


def resolve_knowledge(value: KnowledgeParam) -> Optional[KnowledgeConfig]:
    """
    Resolve knowledge= parameter following precedence ladder.
    
    Precedence: Instance > Config > Array > Dict > String > Bool > Default
    
    Args:
        value: Knowledge parameter in any supported form
        
    Returns:
        KnowledgeConfig if enabled, None if disabled
    """
    # Default: disabled
    if value is None:
        return None
    
    # Bool: False = disabled, True = defaults
    if value is False:
        return None
    if value is True:
        return KnowledgeConfig()
    
    # String: single source
    if isinstance(value, str):
        return KnowledgeConfig(sources=[value])
    
    # Array: list of sources
    if isinstance(value, list):
        return KnowledgeConfig(sources=value)
    
    # Dict: expand to config
    if isinstance(value, dict):
        return KnowledgeConfig(
            sources=value.get("sources", []),
            embedder=value.get("embedder", "openai"),
            embedder_config=value.get("embedder_config"),
            chunking_strategy=value.get("chunking_strategy", ChunkingStrategy.SEMANTIC),
            chunk_size=value.get("chunk_size", 1000),
            chunk_overlap=value.get("chunk_overlap", 200),
            retrieval_k=value.get("retrieval_k", 5),
            retrieval_threshold=value.get("retrieval_threshold", 0.0),
            rerank=value.get("rerank", False),
            rerank_model=value.get("rerank_model"),
            auto_retrieve=value.get("auto_retrieve", True),
        )
    
    # Config: passthrough
    if isinstance(value, KnowledgeConfig):
        return value
    
    # Instance: return as-is
    return value


def resolve_planning(value: PlanningParam) -> Optional[PlanningConfig]:
    """Resolve planning= parameter following precedence ladder."""
    if value is None or value is False:
        return None
    if value is True:
        return PlanningConfig()
    if isinstance(value, dict):
        return PlanningConfig(**value)
    if isinstance(value, PlanningConfig):
        return value
    return value


def resolve_reflection(value: ReflectionParam) -> Optional[ReflectionConfig]:
    """Resolve reflection= parameter following precedence ladder."""
    if value is None or value is False:
        return None
    if value is True:
        return ReflectionConfig()
    if isinstance(value, dict):
        return ReflectionConfig(**value)
    if isinstance(value, ReflectionConfig):
        return value
    return value


def resolve_guardrails(value: GuardrailParam) -> Optional[GuardrailConfig]:
    """Resolve guardrails= parameter following precedence ladder."""
    if value is None or value is False:
        return None
    if value is True:
        return GuardrailConfig()
    if callable(value):
        return GuardrailConfig(validator=value)
    if isinstance(value, dict):
        return GuardrailConfig(**value)
    if isinstance(value, GuardrailConfig):
        return value
    return value


def resolve_web(value: WebParam) -> Optional[WebConfig]:
    """Resolve web= parameter following precedence ladder."""
    if value is None or value is False:
        return None
    if value is True:
        return WebConfig()
    if isinstance(value, dict):
        return WebConfig(**value)
    if isinstance(value, WebConfig):
        return value
    return value


def resolve_output(value: OutputParam) -> Optional[OutputConfig]:
    """Resolve output= parameter following precedence ladder."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            preset = OutputPreset(value.lower())
            return OutputConfig.from_preset(preset)
        except ValueError:
            return None
    if isinstance(value, dict):
        return OutputConfig(**value)
    if isinstance(value, OutputConfig):
        return value
    return value


def resolve_execution(value: ExecutionParam) -> Optional[ExecutionConfig]:
    """Resolve execution= parameter following precedence ladder."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            preset = ExecutionPreset(value.lower())
            return ExecutionConfig.from_preset(preset)
        except ValueError:
            return None
    if isinstance(value, dict):
        return ExecutionConfig(**value)
    if isinstance(value, ExecutionConfig):
        return value
    return value


def resolve_caching(value: CachingParam) -> Optional[CachingConfig]:
    """Resolve caching= parameter following precedence ladder."""
    if value is None or value is False:
        return None
    if value is True:
        return CachingConfig()
    if isinstance(value, dict):
        return CachingConfig(**value)
    if isinstance(value, CachingConfig):
        return value
    return value


def resolve_autonomy(value: AutonomyParam) -> Optional[AutonomyConfig]:
    """Resolve autonomy= parameter following precedence ladder."""
    if value is None or value is False:
        return None
    if value is True:
        return AutonomyConfig()
    if isinstance(value, dict):
        return AutonomyConfig(**value)
    if isinstance(value, AutonomyConfig):
        return value
    return value


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
    "TemplateConfig",
    "CachingConfig",
    "HooksConfig",
    "SkillsConfig",
    "AutonomyConfig",
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
    # Precedence ladder resolvers
    "resolve_memory",
    "resolve_knowledge",
    "resolve_planning",
    "resolve_reflection",
    "resolve_guardrails",
    "resolve_web",
    "resolve_output",
    "resolve_execution",
    "resolve_caching",
    "resolve_autonomy",
]
