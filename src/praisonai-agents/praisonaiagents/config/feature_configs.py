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


@dataclass
class MemoryConfig:
    """
    Configuration for agent memory and session management.
    
    Consolidates: memory, auto_memory, claude_memory, user_id, session_id, db
    
    Usage:
        # Simple enable (uses FileMemory)
        Agent(memory=True)
        
        # With backend
        Agent(memory=MemoryConfig(backend="redis"))
        
        # Full config
        Agent(memory=MemoryConfig(
            backend="sqlite",
            user_id="user123",
            session_id="session456",
            auto_memory=True,
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "backend": self.backend.value if isinstance(self.backend, MemoryBackend) else self.backend,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "auto_memory": self.auto_memory,
            "claude_memory": self.claude_memory,
            "config": self.config,
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
    """
    # Knowledge sources (files, directories, URLs)
    sources: List[str] = field(default_factory=list)
    
    # Embedder configuration
    embedder: str = "openai"
    embedder_config: Optional[Dict[str, Any]] = None
    
    # Chunking
    chunking_strategy: Union[str, ChunkingStrategy] = ChunkingStrategy.SEMANTIC
    chunk_size: int = 1000
    chunk_overlap: int = 200
    
    # Retrieval
    retrieval_k: int = 5
    retrieval_threshold: float = 0.0
    
    # Reranking
    rerank: bool = False
    rerank_model: Optional[str] = None
    
    # Auto-retrieval (inject context automatically)
    auto_retrieve: bool = True
    
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
            "retrieval_k": self.retrieval_k,
            "retrieval_threshold": self.retrieval_threshold,
            "rerank": self.rerank,
            "rerank_model": self.rerank_model,
            "auto_retrieve": self.auto_retrieve,
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "validator": str(self.validator) if self.validator else None,
            "llm_validator": self.llm_validator,
            "max_retries": self.max_retries,
            "on_fail": self.on_fail.value if isinstance(self.on_fail, GuardrailAction) else self.on_fail,
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


# Type aliases for Union types used in Agent.__init__
MemoryParam = Union[bool, MemoryConfig, Any]  # Any = MemoryManager instance
KnowledgeParam = Union[bool, List[str], KnowledgeConfig, Any]  # Any = KnowledgeBase instance
PlanningParam = Union[bool, PlanningConfig]
ReflectionParam = Union[bool, ReflectionConfig]
GuardrailParam = Union[bool, Callable[..., Tuple[bool, Any]], GuardrailConfig, Any]  # Any = GuardrailEngine
WebParam = Union[bool, WebConfig]


__all__ = [
    # Enums
    "MemoryBackend",
    "ChunkingStrategy",
    "GuardrailAction",
    "WebSearchProvider",
    # Config classes
    "MemoryConfig",
    "KnowledgeConfig",
    "PlanningConfig",
    "ReflectionConfig",
    "GuardrailConfig",
    "WebConfig",
    # Type aliases
    "MemoryParam",
    "KnowledgeParam",
    "PlanningParam",
    "ReflectionParam",
    "GuardrailParam",
    "WebParam",
]
