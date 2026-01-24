"""
Context Management Data Models for PraisonAI Agents.

Provides dataclasses and protocols for context budgeting, composition,
optimization, and monitoring.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Literal, Protocol, runtime_checkable
from enum import Enum


class ContextSegment(str, Enum):
    """Segments that contribute to context."""
    SYSTEM_PROMPT = "system_prompt"
    RULES = "rules"
    SKILLS = "skills"
    MEMORY = "memory"
    TOOLS_SCHEMA = "tools_schema"
    HISTORY = "history"
    TOOL_OUTPUTS = "tool_outputs"
    BUFFER = "buffer"


@dataclass
class ContextLedger:
    """
    Tracks token usage across context segments.
    
    Provides per-segment token counts and total usage.
    """
    system_prompt: int = 0
    rules: int = 0
    skills: int = 0
    memory: int = 0
    tools_schema: int = 0
    history: int = 0
    tool_outputs: int = 0
    buffer: int = 0
    
    # Metadata
    turn_count: int = 0
    message_count: int = 0
    tool_call_count: int = 0
    
    @property
    def total(self) -> int:
        """Total tokens across all segments."""
        return (
            self.system_prompt +
            self.rules +
            self.skills +
            self.memory +
            self.tools_schema +
            self.history +
            self.tool_outputs +
            self.buffer
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def get_segment(self, segment: ContextSegment) -> int:
        """Get token count for a segment."""
        return getattr(self, segment.value, 0)
    
    def set_segment(self, segment: ContextSegment, tokens: int) -> None:
        """Set token count for a segment."""
        setattr(self, segment.value, tokens)
    
    def add_segment(self, segment: ContextSegment, tokens: int) -> None:
        """Add tokens to a segment."""
        current = self.get_segment(segment)
        self.set_segment(segment, current + tokens)
    
    def copy(self) -> "ContextLedger":
        """Create a copy of this ledger."""
        return ContextLedger(
            system_prompt=self.system_prompt,
            rules=self.rules,
            skills=self.skills,
            memory=self.memory,
            tools_schema=self.tools_schema,
            history=self.history,
            tool_outputs=self.tool_outputs,
            buffer=self.buffer,
            turn_count=self.turn_count,
            message_count=self.message_count,
            tool_call_count=self.tool_call_count,
        )


@dataclass
class BudgetAllocation:
    """
    Token budget allocation across segments.
    
    Specifies maximum tokens allowed per segment.
    """
    model_limit: int = 128000
    output_reserve: int = 8000
    
    # Segment budgets (absolute tokens or -1 for dynamic)
    system_prompt: int = 2000
    rules: int = 500
    skills: int = 500
    memory: int = 1000
    tools_schema: int = 2000
    history: int = -1  # Dynamic: fills remaining
    tool_outputs: int = 20000
    buffer: int = 1000
    
    @property
    def usable(self) -> int:
        """Usable tokens after output reserve."""
        return self.model_limit - self.output_reserve
    
    @property
    def fixed_total(self) -> int:
        """Total of fixed segment budgets."""
        total = 0
        for seg in [self.system_prompt, self.rules, self.skills, 
                    self.memory, self.tools_schema, self.tool_outputs, self.buffer]:
            if seg > 0:
                total += seg
        return total
    
    @property
    def history_budget(self) -> int:
        """Computed history budget (remainder after fixed segments)."""
        if self.history > 0:
            return self.history
        return max(0, self.usable - self.fixed_total)
    
    def get_segment_budget(self, segment: ContextSegment) -> int:
        """Get budget for a segment."""
        if segment == ContextSegment.HISTORY:
            return self.history_budget
        return getattr(self, segment.value, 0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        result['usable'] = self.usable
        result['history_budget'] = self.history_budget
        return result


@dataclass
class ContextSnapshot:
    """
    A snapshot of the current context state.
    
    Used for monitoring and debugging.
    """
    timestamp: str = ""
    session_id: str = ""
    agent_name: str = ""
    model_name: str = ""
    
    # Budget info
    budget: Optional[BudgetAllocation] = None
    
    # Token accounting
    ledger: Optional[ContextLedger] = None
    
    # Utilization
    utilization: float = 0.0
    
    # Content segments (for dump)
    system_prompt_content: str = ""
    rules_content: str = ""
    skills_content: str = ""
    memory_content: str = ""
    tools_schema_content: str = ""
    history_content: List[Dict[str, Any]] = field(default_factory=list)
    
    # Warnings
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "model_name": self.model_name,
            "budget": self.budget.to_dict() if self.budget else None,
            "ledger": self.ledger.to_dict() if self.ledger else None,
            "utilization": self.utilization,
            "warnings": self.warnings,
            "history_turn_count": len(self.history_content),
        }


class OptimizerStrategy(str, Enum):
    """Context optimization strategies."""
    TRUNCATE = "truncate"
    SLIDING_WINDOW = "sliding_window"
    SUMMARIZE = "summarize"
    PRUNE_TOOLS = "prune_tools"
    NON_DESTRUCTIVE = "non_destructive"
    SMART = "smart"


@dataclass
class OptimizationResult:
    """Result of context optimization."""
    original_tokens: int = 0
    optimized_tokens: int = 0
    tokens_saved: int = 0
    strategy_used: OptimizerStrategy = OptimizerStrategy.SMART
    messages_removed: int = 0
    messages_tagged: int = 0
    tool_outputs_pruned: int = 0
    tool_outputs_summarized: int = 0  # Count of tool outputs summarized via LLM
    tokens_saved_by_summarization: int = 0  # Tokens saved specifically by LLM summarization
    tokens_saved_by_truncation: int = 0  # Tokens saved specifically by truncation
    summary_added: bool = False
    
    @property
    def reduction_percent(self) -> float:
        """Percentage of tokens reduced."""
        if self.original_tokens == 0:
            return 0.0
        return (self.tokens_saved / self.original_tokens) * 100


@dataclass
class MonitorConfig:
    """Configuration for context monitoring."""
    enabled: bool = False
    path: str = "./context.txt"
    format: Literal["human", "json"] = "human"
    frequency: Literal["turn", "tool_call", "manual", "overflow"] = "turn"
    redact_sensitive: bool = True
    multi_agent_files: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ContextConfig:
    """
    Complete context management configuration.
    
    Merges settings from CLI flags, env vars, and config files.
    
    Example:
        # Enable with defaults
        agent = Agent(instructions="...", context=True)
        
        # Custom configuration
        agent = Agent(
            instructions="...",
            context=ContextConfig(
                auto_compact=True,
                session_tracking=True,      # Track goal/plan/progress
                aggregate_memory=True,       # Concurrent multi-memory fetch
            )
        )
    """
    # Auto-compaction
    auto_compact: bool = True
    compact_threshold: float = 0.8  # Trigger at 80% of usable budget
    strategy: OptimizerStrategy = OptimizerStrategy.SMART
    
    # Budget overrides
    output_reserve: int = 8000
    history_ratio: float = 0.6  # 60% of usable for history
    tool_output_max: int = 10000  # Max tokens per tool output
    
    # Pruning
    prune_after_tokens: int = 40000
    protected_tools: List[str] = field(default_factory=list)
    
    # Per-tool output limits (tool_name -> max_chars)
    tool_limits: Dict[str, int] = field(default_factory=dict)
    
    # Monitoring
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    
    # Sliding window
    keep_recent_turns: int = 5
    
    # LLM-powered summarization
    llm_summarize: bool = False  # Enable LLM-powered summarization (uses agent's LLM)
    
    # Smart tool output summarization (summarize before truncating)
    smart_tool_summarize: bool = True  # Summarize large tool outputs using LLM before truncating
    
    # Session tracking (Agno pattern)
    session_tracking: bool = False     # Enable goal/plan/progress tracking
    track_summary: bool = True         # Auto-extract conversation summary
    track_goal: bool = True            # Track user's objective
    track_plan: bool = True            # Track steps to achieve goal
    track_progress: bool = True        # Track completed steps
    
    # Multi-memory aggregation (CrewAI pattern)
    aggregate_memory: bool = False     # Enable concurrent multi-source fetch
    aggregate_sources: List[str] = field(default_factory=lambda: [
        "memory",      # Short-term memory
        "knowledge",   # Long-term knowledge base
        "rag",         # RAG retrieval
    ])
    aggregate_max_tokens: int = 4000   # Max tokens for aggregated context
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        result['strategy'] = self.strategy.value
        return result
    
    @classmethod
    def for_recipe(cls) -> "ContextConfig":
        """
        Preset for recipe/workflow use cases with many tool calls.
        
        Optimized for:
        - Preventing context overflow in multi-step workflows
        - Preserving important tool outputs
        - Triggering compaction earlier (70% vs 80%)
        - Limiting tool outputs to prevent explosion
        
        Returns:
            ContextConfig with recipe-optimized settings
        """
        return cls(
            auto_compact=True,
            compact_threshold=0.7,  # Trigger at 70% (earlier than default 80%)
            strategy=OptimizerStrategy.SMART,
            tool_output_max=2000,  # Limit each tool output to ~2000 tokens
            keep_recent_turns=3,   # Keep last 3 turns intact
            prune_after_tokens=50000,  # Start pruning after 50K tokens
            output_reserve=8000,
            history_ratio=0.6,
        )


@runtime_checkable
class TokenEstimator(Protocol):
    """Protocol for token estimation."""
    
    def estimate(self, text: str) -> int:
        """Estimate tokens for text."""
        ...
    
    def estimate_messages(self, messages: List[Dict[str, Any]]) -> int:
        """Estimate tokens for a list of messages."""
        ...


@runtime_checkable
class ContextOptimizer(Protocol):
    """Protocol for context optimization strategies."""
    
    def optimize(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: int,
        ledger: ContextLedger,
    ) -> tuple[List[Dict[str, Any]], OptimizationResult]:
        """Optimize messages to fit within target tokens."""
        ...
