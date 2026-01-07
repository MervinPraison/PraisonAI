"""
AutoRagAgent - Agent with automatic RAG retrieval decision.

This module provides an agent wrapper that automatically decides when to
retrieve context from knowledge bases vs direct chat.

Usage:
    from praisonaiagents import Agent, AutoRagAgent
    
    agent = Agent(
        name="Research Assistant",
        knowledge=["docs/manual.pdf"],
    )
    
    auto_rag = AutoRagAgent(agent=agent)
    result = auto_rag.chat("What are the key findings?")  # Auto retrieves
    result = auto_rag.chat("Hello!")  # Skips retrieval
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Set, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.agent import Agent
    from praisonaiagents.rag import RAG, ContextPack

logger = logging.getLogger(__name__)


class RetrievalPolicy(Enum):
    """Policy for when to perform RAG retrieval."""
    AUTO = "auto"      # Decide based on query heuristics
    ALWAYS = "always"  # Always retrieve
    NEVER = "never"    # Never retrieve (direct chat only)


@dataclass
class AutoRagConfig:
    """Configuration for AutoRagAgent."""
    
    retrieval_policy: RetrievalPolicy = RetrievalPolicy.AUTO
    
    top_k: int = 5
    hybrid: bool = False
    rerank: bool = False
    
    include_citations: bool = True
    citations_mode: str = "append"  # append, hidden, none
    
    max_context_tokens: int = 4000
    
    auto_keywords: Set[str] = field(default_factory=lambda: {
        "what", "how", "why", "when", "where", "who", "which",
        "explain", "describe", "summarize", "find", "search",
        "tell me", "show me", "according to", "based on",
        "cite", "source", "reference", "document", "paper",
    })
    
    auto_min_length: int = 10
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "retrieval_policy": self.retrieval_policy.value,
            "top_k": self.top_k,
            "hybrid": self.hybrid,
            "rerank": self.rerank,
            "include_citations": self.include_citations,
            "citations_mode": self.citations_mode,
            "max_context_tokens": self.max_context_tokens,
            "auto_keywords": list(self.auto_keywords),
            "auto_min_length": self.auto_min_length,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutoRagConfig":
        """Create from dictionary."""
        policy = data.get("retrieval_policy", "auto")
        if isinstance(policy, str):
            policy = RetrievalPolicy(policy)
        
        keywords = data.get("auto_keywords", None)
        if keywords is not None and isinstance(keywords, list):
            keywords = set(keywords)
        
        kwargs = {
            "retrieval_policy": policy,
            "top_k": data.get("top_k", 5),
            "hybrid": data.get("hybrid", False),
            "rerank": data.get("rerank", False),
            "include_citations": data.get("include_citations", True),
            "max_context_tokens": data.get("max_context_tokens", 4000),
            "auto_min_length": data.get("auto_min_length", 10),
            "citations_mode": data.get("citations_mode", "append"),
        }
        if keywords:
            kwargs["auto_keywords"] = keywords
        
        return cls(**kwargs)


class AutoRagAgent:
    """
    Agent wrapper with automatic RAG retrieval decision.
    
    Decides when to perform retrieval based on policy and heuristics,
    then composes RAG context with Agent chat.
    
    This follows the same pattern as AutoAgents but for RAG:
    - AutoAgents: auto-generates agent configs from instructions
    - AutoRagAgent: auto-decides when to retrieve context
    
    Usage:
        from praisonaiagents import Agent, AutoRagAgent
        
        agent = Agent(
            name="Research Assistant",
            knowledge=["docs/manual.pdf"],
        )
        
        auto_rag = AutoRagAgent(agent=agent)
        
        # Auto mode - decides based on query
        result = auto_rag.chat("What are the key findings?")
        
        # Force retrieval
        result = auto_rag.chat("Hello", force_retrieval=True)
        
        # Skip retrieval
        result = auto_rag.chat("What is 2+2?", skip_retrieval=True)
    """
    
    def __init__(
        self,
        agent: "Agent",
        rag: Optional["RAG"] = None,
        config: Optional[AutoRagConfig] = None,
        *,
        retrieval_policy: Optional[str] = None,
        top_k: Optional[int] = None,
        hybrid: Optional[bool] = None,
        rerank: Optional[bool] = None,
        citations: bool = True,
    ):
        """
        Initialize AutoRagAgent.
        
        Args:
            agent: Agent instance (must have knowledge configured for RAG)
            rag: Optional RAG instance (uses agent.rag if not provided)
            config: AutoRagConfig instance
            retrieval_policy: Shorthand for config.retrieval_policy (auto/always/never)
            top_k: Shorthand for config.top_k
            hybrid: Shorthand for config.hybrid
            rerank: Shorthand for config.rerank
            citations: Shorthand for config.include_citations
        """
        self.agent = agent
        self._rag = rag
        
        # Build config from kwargs or use provided
        if config is not None:
            self.config = config
        else:
            config_kwargs = {}
            if retrieval_policy is not None:
                config_kwargs["retrieval_policy"] = RetrievalPolicy(retrieval_policy)
            if top_k is not None:
                config_kwargs["top_k"] = top_k
            if hybrid is not None:
                config_kwargs["hybrid"] = hybrid
            if rerank is not None:
                config_kwargs["rerank"] = rerank
            config_kwargs["include_citations"] = citations
            self.config = AutoRagConfig(**config_kwargs)
        
        # Lazy RAG initialization flag
        self._rag_initialized = False
    
    @property
    def rag(self) -> Optional["RAG"]:
        """Lazy load RAG from agent if not provided."""
        if self._rag is not None:
            return self._rag
        
        if not self._rag_initialized:
            # Try to get RAG from agent
            if hasattr(self.agent, 'rag') and self.agent.rag is not None:
                self._rag = self.agent.rag
            self._rag_initialized = True
        
        return self._rag
    
    @property
    def name(self) -> str:
        """Delegate name to wrapped agent."""
        return getattr(self.agent, 'name', 'AutoRagAgent')
    
    def _needs_retrieval(self, query: str) -> bool:
        """
        Determine if query needs retrieval based on heuristics.
        
        Simple, local heuristics (no ML classifier):
        1. Query length check
        2. Keyword presence check
        3. Question mark check
        
        Args:
            query: User query
            
        Returns:
            True if retrieval should be performed
        """
        # Check minimum length
        if len(query.strip()) < self.config.auto_min_length:
            return False
        
        # Check for keywords
        query_lower = query.lower()
        for keyword in self.config.auto_keywords:
            if keyword in query_lower:
                return True
        
        # Check for question marks (likely a question)
        if "?" in query:
            return True
        
        return False
    
    def _should_retrieve(
        self,
        query: str,
        force_retrieval: bool = False,
        skip_retrieval: bool = False,
    ) -> bool:
        """
        Determine if retrieval should be performed.
        
        Args:
            query: User query
            force_retrieval: Override to force retrieval
            skip_retrieval: Override to skip retrieval
            
        Returns:
            True if retrieval should be performed
        """
        # Explicit overrides take precedence
        if skip_retrieval:
            return False
        if force_retrieval:
            return True
        
        # Check if RAG is available
        if self.rag is None:
            logger.debug("RAG not available, skipping retrieval")
            return False
        
        # Apply policy
        if self.config.retrieval_policy == RetrievalPolicy.ALWAYS:
            return True
        elif self.config.retrieval_policy == RetrievalPolicy.NEVER:
            return False
        else:  # AUTO
            return self._needs_retrieval(query)
    
    def _format_response_with_citations(
        self,
        response: str,
        context_pack: Optional["ContextPack"],
    ) -> str:
        """Format response with citations based on config."""
        if context_pack is None or not context_pack.has_citations:
            return response
        
        if self.config.citations_mode == "none":
            return response
        elif self.config.citations_mode == "hidden":
            return response
        else:  # append
            if not self.config.include_citations:
                return response
            
            sources = "\n\nSources:\n"
            for citation in context_pack.citations:
                sources += f"  [{citation.id}] {citation.source}\n"
            return response + sources
    
    def chat(
        self,
        message: str,
        *,
        force_retrieval: bool = False,
        skip_retrieval: bool = False,
        top_k: Optional[int] = None,
        hybrid: Optional[bool] = None,
        rerank: Optional[bool] = None,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Chat with automatic RAG retrieval decision.
        
        Decides whether to retrieve context, then runs agent chat.
        
        Args:
            message: User message/query
            force_retrieval: Force retrieval regardless of policy
            skip_retrieval: Skip retrieval regardless of policy
            top_k: Override top_k for retrieval
            hybrid: Override hybrid retrieval setting
            rerank: Override rerank setting
            user_id: User ID for RAG retrieval (uses agent.user_id if not provided)
            **kwargs: Additional arguments passed to agent.chat()
            
        Returns:
            Agent response (with citations if configured)
        """
        start_time = time.time()
        context_pack = None
        
        # Determine if we should retrieve
        should_retrieve = self._should_retrieve(
            message,
            force_retrieval=force_retrieval,
            skip_retrieval=skip_retrieval,
        )
        
        if should_retrieve and self.rag is not None:
            logger.debug(f"AutoRagAgent: Performing retrieval for: {message[:50]}...")
            
            # Get user_id from parameter or agent
            effective_user_id = user_id or getattr(self.agent, 'user_id', None)
            
            # Retrieve context
            context_pack = self.rag.retrieve(
                query=message,
                top_k=top_k or self.config.top_k,
                hybrid=hybrid if hybrid is not None else self.config.hybrid,
                rerank=rerank if rerank is not None else self.config.rerank,
                user_id=effective_user_id,
            )
            
            # Use agent's chat_with_context if available
            if hasattr(self.agent, 'chat_with_context'):
                response = self.agent.chat_with_context(
                    message=message,
                    context=context_pack,
                    citations_mode=self.config.citations_mode,
                    **kwargs,
                )
            else:
                # Fallback: inject context into message
                augmented_message = self._augment_message(message, context_pack)
                response = self.agent.chat(augmented_message, **kwargs)
                response = self._format_response_with_citations(response, context_pack)
        else:
            # Direct agent chat without retrieval
            logger.debug(f"AutoRagAgent: Skipping retrieval for: {message[:50]}...")
            response = self.agent.chat(message, **kwargs)
        
        elapsed = time.time() - start_time
        logger.debug(f"AutoRagAgent: chat completed in {elapsed:.2f}s")
        
        return response
    
    def _augment_message(self, message: str, context_pack: "ContextPack") -> str:
        """Augment message with retrieved context."""
        return f"""Based on the following context, answer the question.

Context:
{context_pack.context}

Question: {message}

Answer:"""
    
    async def achat(
        self,
        message: str,
        *,
        force_retrieval: bool = False,
        skip_retrieval: bool = False,
        top_k: Optional[int] = None,
        hybrid: Optional[bool] = None,
        rerank: Optional[bool] = None,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Async version of chat.
        
        Currently wraps sync version. Can be extended for true async.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.chat(
                message=message,
                force_retrieval=force_retrieval,
                skip_retrieval=skip_retrieval,
                top_k=top_k,
                hybrid=hybrid,
                rerank=rerank,
                user_id=user_id,
                **kwargs,
            ),
        )
    
    # Alias for consistency with Orchestrator pattern
    run = chat
    arun = achat
