"""
Query Engine Patterns for PraisonAI Agents.

This module defines query modes and protocols.
NO heavy imports - only stdlib and typing.

Implementations are provided by the wrapper layer.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class QueryMode(str, Enum):
    """Available query modes."""
    DEFAULT = "default"
    SUB_QUESTION = "sub_question"
    SQL = "sql"
    ROUTER = "router"
    SUMMARIZE = "summarize"


@dataclass
class QueryResult:
    """
    Result from a query operation.
    
    Attributes:
        answer: The synthesized answer
        sources: List of source documents/chunks used
        sub_questions: Optional list of sub-questions (for sub_question mode)
        metadata: Additional metadata
    """
    answer: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    sub_questions: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "answer": self.answer,
            "sources": self.sources,
            "sub_questions": self.sub_questions,
            "metadata": self.metadata
        }


@runtime_checkable
class QueryEngineProtocol(Protocol):
    """
    Protocol for query engines.
    
    Implementations must provide a query method that takes a question
    and returns an answer with sources.
    """
    
    name: str
    mode: QueryMode
    
    def query(
        self,
        question: str,
        context: Optional[List[str]] = None,
        **kwargs
    ) -> QueryResult:
        """
        Query the knowledge base.
        
        Args:
            question: The user's question
            context: Optional pre-retrieved context
            **kwargs: Additional engine-specific options
            
        Returns:
            QueryResult with answer and sources
        """
        ...
    
    async def aquery(
        self,
        question: str,
        context: Optional[List[str]] = None,
        **kwargs
    ) -> QueryResult:
        """Async version of query."""
        ...


class QueryEngineRegistry:
    """Registry for query engines."""
    
    _instance: Optional["QueryEngineRegistry"] = None
    
    def __new__(cls) -> "QueryEngineRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._engines: Dict[str, Callable[..., QueryEngineProtocol]] = {}
        return cls._instance
    
    def register(self, name: str, factory: Callable[..., QueryEngineProtocol]) -> None:
        """Register a query engine factory."""
        self._engines[name] = factory
    
    def get(self, name: str, **kwargs) -> Optional[QueryEngineProtocol]:
        """Get a query engine by name."""
        if name in self._engines:
            try:
                return self._engines[name](**kwargs)
            except Exception as e:
                logger.warning(f"Failed to initialize query engine '{name}': {e}")
                return None
        return None
    
    def list_engines(self) -> List[str]:
        """List all registered engine names."""
        return list(self._engines.keys())
    
    def clear(self) -> None:
        """Clear all registered engines."""
        self._engines.clear()


def get_query_engine_registry() -> QueryEngineRegistry:
    """Get the global query engine registry instance."""
    return QueryEngineRegistry()


def decompose_question(question: str) -> List[str]:
    """
    Simple deterministic question decomposition.
    
    Splits complex questions into sub-questions without LLM.
    Used as fallback when LLM is not available.
    
    Args:
        question: The complex question
        
    Returns:
        List of sub-questions
    """
    sub_questions = []
    
    # Split on common conjunctions
    conjunctions = [" and ", " also ", " additionally ", " furthermore ", " moreover "]
    parts = [question]
    
    for conj in conjunctions:
        new_parts = []
        for part in parts:
            new_parts.extend(part.split(conj))
        parts = new_parts
    
    # Clean up parts
    for part in parts:
        part = part.strip()
        if part:
            # Ensure it ends with a question mark
            if not part.endswith("?"):
                part = part + "?"
            # Capitalize first letter
            part = part[0].upper() + part[1:] if len(part) > 1 else part.upper()
            sub_questions.append(part)
    
    # If no decomposition happened, return original
    if len(sub_questions) <= 1:
        return [question]
    
    return sub_questions


def synthesize_answer(
    question: str,
    contexts: List[str],
    max_context_length: int = 4000
) -> str:
    """
    Simple answer synthesis without LLM.
    
    Concatenates relevant context with the question.
    Used as fallback when LLM is not available.
    
    Args:
        question: The original question
        contexts: List of context strings
        max_context_length: Maximum total context length
        
    Returns:
        Synthesized answer string
    """
    if not contexts:
        return "No relevant information found."
    
    # Truncate contexts to fit
    total_length = 0
    selected_contexts = []
    
    for ctx in contexts:
        if total_length + len(ctx) > max_context_length:
            remaining = max_context_length - total_length
            if remaining > 100:
                selected_contexts.append(ctx[:remaining] + "...")
            break
        selected_contexts.append(ctx)
        total_length += len(ctx)
    
    # Format as a simple answer
    context_text = "\n\n".join(selected_contexts)
    
    return f"Based on the available information:\n\n{context_text}"


class SimpleQueryEngine:
    """
    Simple query engine for testing and fallback.
    
    Uses basic context concatenation without LLM synthesis.
    """
    
    name: str = "simple"
    mode: QueryMode = QueryMode.DEFAULT
    
    def __init__(self, **kwargs):
        pass
    
    def query(
        self,
        question: str,
        context: Optional[List[str]] = None,
        **kwargs
    ) -> QueryResult:
        """Simple query that returns context as answer."""
        contexts = context or []
        answer = synthesize_answer(question, contexts)
        
        return QueryResult(
            answer=answer,
            sources=[{"text": ctx} for ctx in contexts],
            metadata={"mode": self.mode.value}
        )
    
    async def aquery(
        self,
        question: str,
        context: Optional[List[str]] = None,
        **kwargs
    ) -> QueryResult:
        """Async version (just calls sync)."""
        return self.query(question, context, **kwargs)


class SubQuestionEngine:
    """
    Sub-question decomposition query engine.
    
    Decomposes complex questions into simpler sub-questions.
    Uses deterministic fallback when LLM is not available.
    """
    
    name: str = "sub_question"
    mode: QueryMode = QueryMode.SUB_QUESTION
    
    def __init__(self, llm: Optional[Any] = None, **kwargs):
        self.llm = llm
    
    def query(
        self,
        question: str,
        context: Optional[List[str]] = None,
        retriever: Optional[Any] = None,
        **kwargs
    ) -> QueryResult:
        """Query with sub-question decomposition."""
        # Decompose question
        if self.llm:
            sub_questions = self._decompose_with_llm(question)
        else:
            sub_questions = decompose_question(question)
        
        # Gather context for each sub-question
        all_contexts = list(context or [])
        sub_answers = []
        
        for sub_q in sub_questions:
            if retriever:
                # Retrieve for each sub-question
                try:
                    results = retriever.retrieve(sub_q, top_k=3)
                    for r in results:
                        if hasattr(r, 'text'):
                            all_contexts.append(r.text)
                        elif isinstance(r, dict):
                            all_contexts.append(r.get('text', str(r)))
                except Exception as e:
                    logger.warning(f"Retrieval failed for sub-question: {e}")
            
            # Simple sub-answer (would use LLM in full implementation)
            sub_answers.append(f"Sub-question: {sub_q}")
        
        # Synthesize final answer
        answer = synthesize_answer(question, all_contexts)
        
        return QueryResult(
            answer=answer,
            sources=[{"text": ctx} for ctx in all_contexts[:10]],
            sub_questions=sub_questions,
            metadata={"mode": self.mode.value, "sub_question_count": len(sub_questions)}
        )
    
    async def aquery(
        self,
        question: str,
        context: Optional[List[str]] = None,
        **kwargs
    ) -> QueryResult:
        """Async version (just calls sync)."""
        return self.query(question, context, **kwargs)
    
    def _decompose_with_llm(self, question: str) -> List[str]:
        """Decompose question using LLM."""
        try:
            prompt = f"""Break down this complex question into simpler sub-questions that can be answered independently.
            
Question: {question}

Return only the sub-questions, one per line, without numbering or bullets."""
            
            response = self.llm.chat(prompt)
            if response:
                lines = response.strip().split("\n")
                return [line.strip() for line in lines if line.strip()]
        except Exception as e:
            logger.warning(f"LLM decomposition failed: {e}")
        
        return decompose_question(question)


# Register default engines
def _register_default_engines():
    """Register default query engines."""
    registry = get_query_engine_registry()
    registry.register("default", SimpleQueryEngine)
    registry.register("simple", SimpleQueryEngine)
    registry.register("sub_question", SubQuestionEngine)


_register_default_engines()
