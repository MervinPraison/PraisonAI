"""
Query Rewriter Agent Module

This module provides the QueryRewriterAgent class for transforming user queries
to improve retrieval quality in RAG applications.

Supported Rewriting Strategies:
- **BASIC**: Simple rephrasing for clarity and keyword optimization
- **HYDE**: Hypothetical Document Embeddings - generates a hypothetical answer
- **STEP_BACK**: Generates higher-level concept questions for complex queries
- **SUB_QUERIES**: Decomposes multi-part questions into focused sub-queries
- **MULTI_QUERY**: Generates multiple paraphrased versions for ensemble retrieval
- **CONTEXTUAL**: Uses conversation history to resolve references and context

Example:
    from praisonaiagents import QueryRewriterAgent, RewriteStrategy
    
    agent = QueryRewriterAgent()
    
    # Basic rewriting
    result = agent.rewrite("AI trends")
    print(result.rewritten_queries)
    
    # HyDE for better semantic matching
    result = agent.rewrite("What is quantum computing?", strategy=RewriteStrategy.HYDE)
    print(result.hypothetical_document)
    
    # Contextual with chat history
    chat_history = [
        {"role": "user", "content": "Tell me about Python"},
        {"role": "assistant", "content": "Python is a programming language..."}
    ]
    result = agent.rewrite("What about its performance?", chat_history=chat_history)
    
    # With search tools for context-aware rewriting
    from praisonaiagents.tools import internet_search
    agent = QueryRewriterAgent(tools=[internet_search])
    result = agent.rewrite("latest AI developments")  # Searches first, then rewrites
"""

import logging
import json
from typing import List, Optional, Any, Dict
from dataclasses import dataclass, field
from enum import Enum


class RewriteStrategy(Enum):
    """Enumeration of available query rewriting strategies."""
    BASIC = "basic"
    HYDE = "hyde"
    STEP_BACK = "step_back"
    SUB_QUERIES = "sub_queries"
    MULTI_QUERY = "multi_query"
    CONTEXTUAL = "contextual"
    AUTO = "auto"


@dataclass
class RewriteResult:
    """Result of a query rewriting operation."""
    original_query: str
    rewritten_queries: List[str]
    strategy_used: RewriteStrategy
    hypothetical_document: Optional[str] = None
    step_back_question: Optional[str] = None
    sub_queries: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self):
        return f"RewriteResult(strategy={self.strategy_used.value}, queries={len(self.rewritten_queries)})"
    
    @property
    def primary_query(self) -> str:
        """Returns the primary rewritten query."""
        return self.rewritten_queries[0] if self.rewritten_queries else self.original_query
    
    @property
    def all_queries(self) -> List[str]:
        """Returns all queries including original and rewritten."""
        queries = [self.original_query]
        queries.extend(self.rewritten_queries)
        if self.step_back_question:
            queries.append(self.step_back_question)
        if self.sub_queries:
            queries.extend(self.sub_queries)
        return list(set(queries))  # Remove duplicates


class QueryRewriterAgent:
    """
    Agent for rewriting queries to improve retrieval quality in RAG applications.
    
    This agent transforms user queries using various strategies to bridge the gap
    between how users ask questions and how information is stored in knowledge bases.
    
    Attributes:
        name: Name of the agent
        model: LLM model to use for rewriting (alias for llm=)
        max_queries: Maximum number of queries to generate for multi-query strategy
        abbreviations: Dictionary of common abbreviations to expand
        
    Example:
        agent = QueryRewriterAgent(model="gpt-4o-mini")
        result = agent.rewrite("ML best practices", strategy=RewriteStrategy.MULTI_QUERY)
        for query in result.rewritten_queries:
            print(query)
    """
    
    # Default prompts for each strategy
    PROMPTS = {
        "basic": """You are an expert at improving prompts and queries.

Given the following input, improve it while preserving its original intent and type.

Guidelines:
- If it's a TASK (e.g., "write X", "create Y", "generate Z"), keep it as a task - do NOT convert to a question
- If it's a QUESTION (e.g., "what is X?", "how does Y work?"), keep it as a question
- Expand abbreviations and acronyms
- Fix typos and grammatical errors
- Add relevant context if too short
- Keep the original intent and action intact

IMPORTANT: If the input is a command/task to DO something, the output must also be a command/task to DO that thing.

Input: {query}

Improved version:""",

        "hyde": """You are an expert at generating hypothetical documents.

Given the following query, write a detailed hypothetical document that would perfectly answer this query. This document will be used to find similar real documents in a knowledge base.

Guidelines:
- Write as if you are answering the query directly
- Include specific details, facts, and terminology
- Use the same style and vocabulary as the target documents
- Be comprehensive but focused on the query topic

Query: {query}

Hypothetical document:""",

        "step_back": """You are an expert at generating step-back questions.

Given the following query, generate a more general, higher-level question that captures the broader concept. This helps retrieve background information needed to answer the specific query.

Guidelines:
- Identify the underlying concept or principle
- Create a question about fundamentals or general knowledge
- The step-back question should provide context for the original query

Query: {query}

Step-back question:""",

        "sub_queries": """You are an expert at decomposing complex queries.

Given the following query, break it down into simpler, focused sub-queries. Each sub-query should address one specific aspect of the original question.

Guidelines:
- Identify distinct aspects or components of the query
- Create independent, self-contained sub-queries
- Each sub-query should be answerable on its own
- Return as a JSON array of strings

Query: {query}

Sub-queries (JSON array):""",

        "multi_query": """You are an expert at query expansion and paraphrasing.

Given the following query, generate {num_queries} different versions that capture the same intent but use different words, phrases, or perspectives.

Guidelines:
- Use synonyms and alternative phrasings
- Try different question formats (what, how, why, etc.)
- Include both formal and informal versions
- Add relevant context or specificity
- Return as a JSON array of strings

Query: {query}

Alternative queries (JSON array):""",

        "contextual": """You are an expert at understanding conversational context.

Given the conversation history and a follow-up query, rewrite the query as a standalone question that captures all relevant context.

Guidelines:
- Resolve pronouns and references (it, this, that, etc.)
- Include relevant context from the conversation
- Keep entity names and important details
- Make the query self-contained and clear

Conversation history:
{chat_history}

Follow-up query: {query}

Standalone question:""",

        "auto": """You are an expert at analyzing and improving prompts and queries.

Analyze the following input and improve it while preserving its original intent and type.

Input types to consider:
1. TASK/COMMAND (write, create, generate, build) → Keep as a task, make it clearer
2. QUESTION (what, how, why, when) → Keep as a question, make it more specific
3. Short/keyword inputs → Expand with context but preserve type
4. Complex multi-part inputs → Clarify structure
5. Well-formed inputs → Minor optimization only

IMPORTANT: Never convert a task into a question. "Write X" should remain "Write X", not "How to write X?"

Input: {query}
{context}

Improved version:"""
    }
    
    def __init__(
        self,
        name: str = "QueryRewriterAgent",
        model: str = "gpt-4o-mini",
        instructions: Optional[str] = None,
        verbose: bool = False,
        max_queries: int = 5,
        abbreviations: Optional[Dict[str, str]] = None,
        temperature: float = 0.3,
        max_tokens: int = 500,
        tools: Optional[List[Any]] = None
    ):
        """
        Initialize the QueryRewriterAgent.
        
        Args:
            name: Name of the agent
            model: LLM model to use (default: gpt-4o-mini)
            instructions: Custom instructions for the agent
            verbose: Whether to print detailed logs
            max_queries: Maximum queries for multi-query strategy
            abbreviations: Custom abbreviation expansions
            temperature: Temperature for LLM generation
            max_tokens: Maximum tokens for LLM response
            tools: Optional list of tools (agent decides when to use them)
        """
        self.name = name
        self.model = model
        self.instructions = instructions
        self.verbose = verbose
        self.max_queries = max_queries
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.tools = tools or []
        self._agent = None  # Lazy initialized
        
        # Default abbreviations (can be extended)
        self.abbreviations = abbreviations or {
            "AI": "Artificial Intelligence",
            "ML": "Machine Learning",
            "NLP": "Natural Language Processing",
            "LLM": "Large Language Model",
            "RAG": "Retrieval Augmented Generation",
            "API": "Application Programming Interface",
            "DB": "Database",
            "UI": "User Interface",
            "UX": "User Experience",
            "SDK": "Software Development Kit",
            "CLI": "Command Line Interface",
        }
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        if self.verbose:
            self.logger.setLevel(logging.DEBUG)
    
    @property
    def agent(self):
        """Lazy initialization of internal Agent."""
        if self._agent is None:
            from .agent import Agent
            self._agent = Agent(
                name=self.name,
                role="Query Rewriting Specialist",
                goal="Rewrite queries for better search and retrieval results. Use available tools when needed to gather context.",
                backstory="You are an expert at understanding user intent and transforming queries for optimal information retrieval.",
                tools=self.tools,
                llm=self.model,
                output={"verbose": self.verbose, "markdown": False}
            )
        return self._agent
    
    def _call_agent(self, prompt: str) -> str:
        """Call the internal Agent with the given prompt."""
        try:
            response = self.agent.chat(prompt)
            return response if response else ""
        except Exception as e:
            self.logger.error(f"Agent call failed: {e}")
            raise
    
    def _expand_abbreviations(self, query: str) -> str:
        """Expand known abbreviations in the query."""
        words = query.split()
        expanded = []
        for word in words:
            clean_word = word.strip(".,!?;:")
            if clean_word.upper() in self.abbreviations:
                expanded.append(f"{clean_word} ({self.abbreviations[clean_word.upper()]})")
            else:
                expanded.append(word)
        return " ".join(expanded)
    
    def _is_short_query(self, query: str, threshold: int = 5) -> bool:
        """Check if query is considered short (keyword-style)."""
        return len(query.split()) < threshold
    
    def _parse_json_array(self, text: str) -> List[str]:
        """Parse a JSON array from LLM response."""
        try:
            # Try direct JSON parsing
            result = json.loads(text)
            if isinstance(result, list):
                return [str(item) for item in result]
        except json.JSONDecodeError:
            pass
        
        # Try to extract JSON array from text
        import re
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list):
                    return [str(item) for item in result]
            except json.JSONDecodeError:
                pass
        
        # Fallback: split by newlines and clean up
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        lines = [line.lstrip('0123456789.-) ').strip('"\'') for line in lines]
        return [line for line in lines if line and len(line) > 3]
    
    def rewrite(
        self,
        query: str,
        strategy: RewriteStrategy = RewriteStrategy.AUTO,
        chat_history: Optional[List[Dict[str, str]]] = None,
        context: Optional[str] = None,
        num_queries: int = None
    ) -> RewriteResult:
        """
        Rewrite a query using the specified strategy.
        
        All operations go through an internal Agent which automatically handles
        tool calling when tools are provided. The agent decides when to use tools
        based on the query context.
        
        Args:
            query: The original user query
            strategy: Rewriting strategy to use
            chat_history: Previous conversation messages for contextual rewriting
            context: Additional context about the knowledge base
            num_queries: Number of queries for multi-query strategy
            
        Returns:
            RewriteResult containing rewritten queries
        """
        if self.verbose:
            self.logger.debug(f"Rewriting query: '{query}' with strategy: {strategy.value}")
            if self.tools:
                print(f"[cyan]Agent has {len(self.tools)} tools available (will use if needed)...[/cyan]")
        
        # Auto-detect strategy if needed
        if strategy == RewriteStrategy.AUTO:
            strategy = self._detect_strategy(query, chat_history)
            if self.verbose:
                self.logger.debug(f"Auto-detected strategy: {strategy.value}")
        
        # All calls go through the internal Agent which handles tool calling
        combined_context = context or ""
        
        # Dispatch to appropriate method
        if strategy == RewriteStrategy.BASIC:
            return self._rewrite_basic(query, combined_context)
        elif strategy == RewriteStrategy.HYDE:
            return self._rewrite_hyde(query, combined_context)
        elif strategy == RewriteStrategy.STEP_BACK:
            return self._rewrite_step_back(query, combined_context)
        elif strategy == RewriteStrategy.SUB_QUERIES:
            return self._rewrite_sub_queries(query, combined_context)
        elif strategy == RewriteStrategy.MULTI_QUERY:
            return self._rewrite_multi_query(query, num_queries or self.max_queries, combined_context)
        elif strategy == RewriteStrategy.CONTEXTUAL:
            return self._rewrite_contextual(query, chat_history or [], combined_context)
        else:
            # Default to basic
            return self._rewrite_basic(query, combined_context)
    
    def _detect_strategy(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> RewriteStrategy:
        """Auto-detect the best rewriting strategy for a query."""
        # If chat history exists and query seems like a follow-up
        if chat_history and self._is_follow_up(query):
            return RewriteStrategy.CONTEXTUAL
        
        # Short keyword queries
        if self._is_short_query(query):
            return RewriteStrategy.BASIC
        
        # Complex multi-part queries
        if self._is_complex_query(query):
            return RewriteStrategy.SUB_QUERIES
        
        # Questions that might benefit from step-back
        if self._needs_step_back(query):
            return RewriteStrategy.STEP_BACK
        
        # Default to basic
        return RewriteStrategy.BASIC
    
    def _is_follow_up(self, query: str) -> bool:
        """Check if query appears to be a follow-up question."""
        follow_up_indicators = [
            "it", "this", "that", "they", "them", "their",
            "what about", "how about", "and", "also", "more",
            "same", "similar", "related"
        ]
        query_lower = query.lower()
        return any(indicator in query_lower for indicator in follow_up_indicators)
    
    def _is_complex_query(self, query: str) -> bool:
        """Check if query contains multiple distinct questions."""
        # Check for multiple question marks or conjunctions
        if query.count('?') > 1:
            return True
        complex_indicators = [" and ", " or ", " also ", " as well as ", " plus "]
        return any(ind in query.lower() for ind in complex_indicators)
    
    def _needs_step_back(self, query: str) -> bool:
        """Check if query would benefit from a step-back question."""
        # Queries about specific details often benefit from broader context
        specific_indicators = [
            "specific", "exactly", "precisely", "particular",
            "difference between", "compare", "versus", "vs"
        ]
        return any(ind in query.lower() for ind in specific_indicators)
    
    def _rewrite_basic(self, query: str, context: str = "") -> RewriteResult:
        """Basic query rewriting for clarity and keyword optimization."""
        # First expand abbreviations
        expanded_query = self._expand_abbreviations(query)
        
        # Build prompt with optional context
        prompt = self.PROMPTS["basic"].format(query=expanded_query)
        if context:
            prompt += f"\n\nAdditional context to help with rewriting:\n{context}"
        
        rewritten = self._call_agent(prompt).strip()
        
        return RewriteResult(
            original_query=query,
            rewritten_queries=[rewritten],
            strategy_used=RewriteStrategy.BASIC,
            metadata={"expanded_abbreviations": expanded_query != query, "has_context": bool(context)}
        )
    
    def _rewrite_hyde(self, query: str, context: str = "") -> RewriteResult:
        """HyDE: Generate hypothetical document for better semantic matching."""
        prompt = self.PROMPTS["hyde"].format(query=query)
        if context:
            prompt += f"\n\nUse this context to make the hypothetical document more accurate:\n{context}"
        
        hypothetical_doc = self._call_agent(prompt).strip()
        
        # The hypothetical document itself becomes the search query
        return RewriteResult(
            original_query=query,
            rewritten_queries=[hypothetical_doc[:500]],  # Truncate for embedding
            strategy_used=RewriteStrategy.HYDE,
            hypothetical_document=hypothetical_doc,
            metadata={"full_document_length": len(hypothetical_doc), "has_context": bool(context)}
        )
    
    def _rewrite_step_back(self, query: str, context: str = "") -> RewriteResult:
        """Generate step-back question for broader context retrieval."""
        # Generate step-back question
        prompt = self.PROMPTS["step_back"].format(query=query)
        if context:
            prompt += f"\n\nContext:\n{context}"
        step_back = self._call_agent(prompt).strip()
        
        # Also do basic rewriting of original
        basic_result = self._rewrite_basic(query, context)
        
        return RewriteResult(
            original_query=query,
            rewritten_queries=basic_result.rewritten_queries,
            strategy_used=RewriteStrategy.STEP_BACK,
            step_back_question=step_back,
            metadata={"includes_step_back": True, "has_context": bool(context)}
        )
    
    def _rewrite_sub_queries(self, query: str, context: str = "") -> RewriteResult:
        """Decompose complex query into focused sub-queries."""
        prompt = self.PROMPTS["sub_queries"].format(query=query)
        if context:
            prompt += f"\n\nContext to help with decomposition:\n{context}"
        response = self._call_agent(prompt).strip()
        
        sub_queries = self._parse_json_array(response)
        
        # Ensure we have at least one sub-query
        if not sub_queries:
            sub_queries = [query]
        
        return RewriteResult(
            original_query=query,
            rewritten_queries=sub_queries,
            strategy_used=RewriteStrategy.SUB_QUERIES,
            sub_queries=sub_queries,
            metadata={"num_sub_queries": len(sub_queries), "has_context": bool(context)}
        )
    
    def _rewrite_multi_query(self, query: str, num_queries: int, context: str = "") -> RewriteResult:
        """Generate multiple paraphrased versions for ensemble retrieval."""
        prompt = self.PROMPTS["multi_query"].format(
            query=query,
            num_queries=num_queries
        )
        if context:
            prompt += f"\n\nContext to help with paraphrasing:\n{context}"
        response = self._call_agent(prompt).strip()
        
        queries = self._parse_json_array(response)
        
        # Ensure we have queries and limit to max
        if not queries:
            queries = [query]
        queries = queries[:num_queries]
        
        return RewriteResult(
            original_query=query,
            rewritten_queries=queries,
            strategy_used=RewriteStrategy.MULTI_QUERY,
            metadata={"num_generated": len(queries), "has_context": bool(context)}
        )
    
    def _rewrite_contextual(
        self,
        query: str,
        chat_history: List[Dict[str, str]],
        context: str = ""
    ) -> RewriteResult:
        """Rewrite query using conversation context."""
        # Format chat history
        history_str = ""
        for msg in chat_history[-10:]:  # Last 10 messages
            role = msg.get("role", "user")
            content = msg.get("content", "")
            history_str += f"{role.capitalize()}: {content}\n"
        
        prompt = self.PROMPTS["contextual"].format(
            chat_history=history_str,
            query=query
        )
        if context:
            prompt += f"\n\nAdditional context:\n{context}"
        rewritten = self._call_agent(prompt).strip()
        
        return RewriteResult(
            original_query=query,
            rewritten_queries=[rewritten],
            strategy_used=RewriteStrategy.CONTEXTUAL,
            metadata={
                "history_length": len(chat_history),
                "history_used": min(10, len(chat_history)),
                "has_context": bool(context)
            }
        )
    
    # Convenience methods for direct strategy access
    def rewrite_basic(self, query: str) -> RewriteResult:
        """Convenience method for basic rewriting."""
        return self.rewrite(query, strategy=RewriteStrategy.BASIC)
    
    def rewrite_hyde(self, query: str) -> RewriteResult:
        """Convenience method for HyDE rewriting."""
        return self.rewrite(query, strategy=RewriteStrategy.HYDE)
    
    def rewrite_step_back(self, query: str) -> RewriteResult:
        """Convenience method for step-back rewriting."""
        return self.rewrite(query, strategy=RewriteStrategy.STEP_BACK)
    
    def rewrite_sub_queries(self, query: str) -> RewriteResult:
        """Convenience method for sub-query decomposition."""
        return self.rewrite(query, strategy=RewriteStrategy.SUB_QUERIES)
    
    def rewrite_multi_query(self, query: str, num_queries: int = None) -> RewriteResult:
        """Convenience method for multi-query generation."""
        return self.rewrite(
            query,
            strategy=RewriteStrategy.MULTI_QUERY,
            num_queries=num_queries
        )
    
    def rewrite_contextual(
        self,
        query: str,
        chat_history: List[Dict[str, str]]
    ) -> RewriteResult:
        """Convenience method for contextual rewriting."""
        return self.rewrite(
            query,
            strategy=RewriteStrategy.CONTEXTUAL,
            chat_history=chat_history
        )
    
    def add_abbreviation(self, abbrev: str, expansion: str) -> None:
        """Add a custom abbreviation expansion."""
        self.abbreviations[abbrev.upper()] = expansion
    
    def add_abbreviations(self, abbreviations: Dict[str, str]) -> None:
        """Add multiple custom abbreviation expansions."""
        for abbrev, expansion in abbreviations.items():
            self.abbreviations[abbrev.upper()] = expansion
