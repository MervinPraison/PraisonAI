"""
RAG Pipeline for PraisonAI Agents.

Thin orchestrator that uses Knowledge for retrieval and LLM for generation.
Provides citations, streaming, and async support.
"""

import logging
import time
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from .models import Citation, ContextPack, RAGConfig, RAGResult
from .context import build_context, DefaultContextBuilder

logger = logging.getLogger(__name__)


class DefaultCitationFormatter:
    """
    Default implementation of CitationFormatterProtocol.
    
    Creates Citation objects from search results with stable IDs.
    """
    
    def format(
        self,
        results: List[Dict[str, Any]],
        start_id: int = 1,
    ) -> List[Citation]:
        """Format retrieval results as citations."""
        citations = []
        
        for i, result in enumerate(results):
            # Handle different result formats
            text = result.get("text") or result.get("memory", "")
            # CRITICAL: Handle metadata=None from mem0 - ensure always dict
            metadata = result.get("metadata") or {}
            score = result.get("score", 0.0)
            
            # Extract source info
            source = metadata.get("source", "")
            filename = metadata.get("filename", "")
            doc_id = result.get("id") or metadata.get("doc_id", "")
            chunk_id = metadata.get("chunk_id", "")
            
            citation = Citation(
                id=str(start_id + i),
                source=filename or source or f"Source {start_id + i}",
                text=text[:500] if text else "",  # Limit snippet length
                score=float(score) if score else 0.0,
                doc_id=str(doc_id) if doc_id else None,
                chunk_id=str(chunk_id) if chunk_id else None,
                metadata=metadata,
            )
            citations.append(citation)
        
        return citations


class RAG:
    """
    Retrieval Augmented Generation Pipeline.
    
    Thin orchestrator that:
    1. Retrieves relevant context from Knowledge
    2. Optionally reranks results
    3. Builds context with token-aware truncation
    4. Generates answer using LLM
    5. Returns answer with citations
    
    Usage:
        from praisonaiagents.rag import RAG
        from praisonaiagents.knowledge import Knowledge
        
        knowledge = Knowledge(config={...})
        knowledge.add("document.pdf")
        
        rag = RAG(knowledge=knowledge)
        result = rag.query("What is the main finding?")
        print(result.answer)
        for citation in result.citations:
            print(f"  [{citation.id}] {citation.source}")
    """
    
    def __init__(
        self,
        knowledge: Any,
        llm: Optional[Any] = None,
        config: Optional[RAGConfig] = None,
        reranker: Optional[Any] = None,
        context_builder: Optional[Any] = None,
        citation_formatter: Optional[Any] = None,
    ):
        """
        Initialize RAG pipeline.
        
        Args:
            knowledge: Knowledge instance for retrieval
            llm: Optional LLM instance (uses default if not provided)
            config: RAG configuration
            reranker: Optional reranker for result refinement
            context_builder: Optional custom context builder
            citation_formatter: Optional custom citation formatter
        """
        self.knowledge = knowledge
        self._llm = llm
        self.config = config or RAGConfig()
        self.reranker = reranker
        self.context_builder = context_builder or DefaultContextBuilder()
        self.citation_formatter = citation_formatter or DefaultCitationFormatter()
        
        # Lazy LLM initialization
        self._llm_initialized = False
    
    @property
    def llm(self):
        """Lazy load LLM if not provided."""
        if self._llm is not None:
            return self._llm
        
        if not self._llm_initialized:
            try:
                from praisonaiagents.llm import LLM
                # Use default model from config or fallback to gpt-4o-mini
                model = self.config.model if self.config.model else "gpt-4o-mini"
                self._llm = LLM(model=model)
                self._llm_initialized = True
            except ImportError:
                logger.warning("LLM not available, using simple completion")
                self._llm = None
                self._llm_initialized = True
        
        return self._llm
    
    def _retrieve(
        self,
        query: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant chunks from Knowledge.
        
        Args:
            query: Search query
            user_id: Optional user ID for scoping
            agent_id: Optional agent ID for scoping
            run_id: Optional run ID for scoping
            
        Returns:
            List of search results
        """
        # Use Knowledge's search method
        results = self.knowledge.search(
            query=query,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            **kwargs,
        )
        
        # Handle different result formats
        if isinstance(results, dict):
            results = results.get("results", [])
        
        # Filter by minimum score
        if self.config.min_score > 0:
            results = [
                r for r in results
                if r.get("score", 0) >= self.config.min_score
            ]
        
        # Limit to top_k
        results = results[:self.config.top_k]
        
        return results
    
    def _rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Rerank results if reranker is configured.
        
        Args:
            query: Original query
            results: Results to rerank
            
        Returns:
            Reranked results
        """
        if not self.config.rerank or not self.reranker:
            return results
        
        try:
            reranked = self.reranker.rerank(
                query=query,
                results=results,
                top_k=self.config.rerank_top_k,
            )
            return reranked
        except Exception as e:
            logger.warning(f"Reranking failed: {e}, using original order")
            return results
    
    def _build_context(
        self,
        results: List[Dict[str, Any]],
    ) -> tuple:
        """
        Build context from results.
        
        Returns:
            Tuple of (context_string, used_results)
        """
        return build_context(
            results=results,
            max_tokens=self.config.max_context_tokens,
            deduplicate=True,
        )
    
    def _format_citations(
        self,
        results: List[Dict[str, Any]],
    ) -> List[Citation]:
        """Format results as citations."""
        if not self.config.include_citations:
            return []
        
        return self.citation_formatter.format(results)
    
    def _generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Generate answer using LLM.
        
        Args:
            prompt: Full prompt with context
            system_prompt: Optional system prompt
            
        Returns:
            Generated answer
        """
        if self.llm is None:
            return "LLM not available. Please configure an LLM."
        
        try:
            # Try different LLM interfaces
            if hasattr(self.llm, 'get_response'):
                # PraisonAI LLM interface - prompt can be string or messages list
                if system_prompt:
                    response = self.llm.get_response(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        verbose=False,
                        stream=False,
                        **kwargs
                    )
                else:
                    response = self.llm.get_response(
                        prompt=prompt,
                        verbose=False,
                        stream=False,
                        **kwargs
                    )
                return response if isinstance(response, str) else str(response)
            elif hasattr(self.llm, 'chat'):
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                response = self.llm.chat(messages=messages, **kwargs)
                return response if isinstance(response, str) else str(response)
            elif hasattr(self.llm, 'generate'):
                return self.llm.generate(prompt, **kwargs)
            elif callable(self.llm):
                return self.llm(prompt, **kwargs)
            else:
                return str(self.llm)
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return f"Error generating response: {e}"
    
    def _build_prompt(
        self,
        question: str,
        context: str,
    ) -> str:
        """Build prompt from template."""
        return self.config.template.format(
            question=question,
            context=context,
        )
    
    def retrieve(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        hybrid: Optional[bool] = None,
        rerank: Optional[bool] = None,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **kwargs,
    ) -> ContextPack:
        """
        Retrieve context without LLM generation (Orchestrator pattern).
        
        Returns a ContextPack that can be passed to Agent.chat_with_context().
        This enables conditional retrieval - only retrieve when needed.
        
        Args:
            query: Search query
            top_k: Override config top_k
            hybrid: Override config hybrid retrieval
            rerank: Override config rerank
            filters: Optional metadata filters
            user_id: Optional user ID for scoping
            agent_id: Optional agent ID for scoping
            run_id: Optional run ID for scoping
            
        Returns:
            ContextPack with context string and citations (no LLM call)
        """
        start_time = time.time()
        
        # Apply overrides
        original_top_k = self.config.top_k
        original_rerank = self.config.rerank
        
        if top_k is not None:
            self.config.top_k = top_k
        if rerank is not None:
            self.config.rerank = rerank
        
        try:
            # 1. Retrieve
            results = self._retrieve(
                query=query,
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                filters=filters,
                **kwargs,
            )
            
            # 2. Rerank (optional)
            results = self._rerank(query, results)
            
            # 3. Build context
            context, used_results = self._build_context(results)
            
            # 4. Format citations
            citations = self._format_citations(used_results)
            
            elapsed = time.time() - start_time
            
            return ContextPack(
                context=context,
                citations=citations,
                query=query,
                metadata={
                    "elapsed_seconds": elapsed,
                    "num_results": len(results),
                    "num_citations": len(citations),
                    "retrieval_strategy": self.config.retrieval_strategy.value,
                    "reranked": self.config.rerank,
                    "top_k": self.config.top_k,
                },
            )
        finally:
            # Restore original config
            self.config.top_k = original_top_k
            self.config.rerank = original_rerank
    
    async def aretrieve(
        self,
        query: str,
        *,
        top_k: Optional[int] = None,
        hybrid: Optional[bool] = None,
        rerank: Optional[bool] = None,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **kwargs,
    ) -> ContextPack:
        """
        Async version of retrieve.
        
        Currently wraps sync version. Can be extended for true async.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.retrieve(
                query=query,
                top_k=top_k,
                hybrid=hybrid,
                rerank=rerank,
                filters=filters,
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                **kwargs,
            ),
        )
    
    def query(
        self,
        question: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **kwargs,
    ) -> RAGResult:
        """
        Execute RAG query.
        
        Args:
            question: User's question
            user_id: Optional user ID for scoping
            agent_id: Optional agent ID for scoping
            run_id: Optional run ID for scoping
            
        Returns:
            RAGResult with answer and citations
        """
        start_time = time.time()
        
        # 1. Retrieve
        results = self._retrieve(
            query=question,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            **kwargs,
        )
        
        # 2. Rerank (optional)
        results = self._rerank(question, results)
        
        # 3. Build context
        context, used_results = self._build_context(results)
        
        # 4. Generate answer
        prompt = self._build_prompt(question, context)
        answer = self._generate(
            prompt=prompt,
            system_prompt=self.config.system_prompt,
        )
        
        # 5. Format citations
        citations = self._format_citations(used_results)
        
        # Build result
        elapsed = time.time() - start_time
        
        return RAGResult(
            answer=answer,
            citations=citations,
            context_used=context,
            query=question,
            metadata={
                "elapsed_seconds": elapsed,
                "num_results": len(results),
                "num_citations": len(citations),
                "retrieval_strategy": self.config.retrieval_strategy.value,
                "reranked": self.config.rerank,
            },
        )
    
    async def aquery(
        self,
        question: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **kwargs,
    ) -> RAGResult:
        """
        Async version of query.
        
        Currently wraps sync version. Can be extended for true async.
        """
        # For now, wrap sync version
        # TODO: Implement true async when Knowledge supports it
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.query(
                question=question,
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                **kwargs,
            ),
        )
    
    def stream(
        self,
        question: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **kwargs,
    ) -> Iterator[str]:
        """
        Stream RAG response.
        
        Yields tokens as they are generated.
        Final yield includes citation metadata.
        
        Args:
            question: User's question
            user_id: Optional user ID
            agent_id: Optional agent ID
            run_id: Optional run ID
            
        Yields:
            Response tokens
        """
        # 1. Retrieve
        results = self._retrieve(
            query=question,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            **kwargs,
        )
        
        # 2. Rerank
        results = self._rerank(question, results)
        
        # 3. Build context
        context, used_results = self._build_context(results)
        
        # 4. Build prompt
        prompt = self._build_prompt(question, context)
        
        # 5. Stream generation
        if self.llm is None:
            yield "LLM not available."
            return
        
        try:
            # Try streaming interface
            if hasattr(self.llm, 'stream'):
                messages = []
                if self.config.system_prompt:
                    messages.append({"role": "system", "content": self.config.system_prompt})
                messages.append({"role": "user", "content": prompt})
                
                for chunk in self.llm.stream(messages=messages, **kwargs):
                    yield chunk
            else:
                # Fallback to non-streaming
                answer = self._generate(prompt, self.config.system_prompt)
                # Simulate streaming by yielding words
                for word in answer.split():
                    yield word + " "
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            yield f"Error: {e}"
    
    async def astream(
        self,
        question: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Async streaming RAG response.
        
        Yields tokens as they are generated.
        """
        # 1. Retrieve
        results = self._retrieve(
            query=question,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            **kwargs,
        )
        
        # 2. Rerank
        results = self._rerank(question, results)
        
        # 3. Build context
        context, used_results = self._build_context(results)
        
        # 4. Build prompt
        prompt = self._build_prompt(question, context)
        
        # 5. Stream generation
        if self.llm is None:
            yield "LLM not available."
            return
        
        try:
            # Try async streaming interface
            if hasattr(self.llm, 'astream'):
                messages = []
                if self.config.system_prompt:
                    messages.append({"role": "system", "content": self.config.system_prompt})
                messages.append({"role": "user", "content": prompt})
                
                async for chunk in self.llm.astream(messages=messages, **kwargs):
                    yield chunk
            else:
                # Fallback to sync streaming wrapped
                for chunk in self.stream(question, user_id, agent_id, run_id, **kwargs):
                    yield chunk
        except Exception as e:
            logger.error(f"Async streaming failed: {e}")
            yield f"Error: {e}"
    
    def get_citations(
        self,
        question: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **kwargs,
    ) -> List[Citation]:
        """
        Get citations without generating answer.
        
        Useful for retrieval-only workflows.
        """
        results = self._retrieve(
            query=question,
            user_id=user_id,
            agent_id=agent_id,
            run_id=run_id,
            **kwargs,
        )
        results = self._rerank(question, results)
        return self._format_citations(results)
