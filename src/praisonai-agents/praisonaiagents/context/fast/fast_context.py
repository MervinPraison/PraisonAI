"""
FastContext - High-level API for fast parallel code search.

This module provides the main FastContext class that can be used
standalone or integrated with the main Agent class via context= param.

Example usage:
    # Standalone usage
    from praisonaiagents.context.fast import FastContext
    
    fc = FastContext(workspace_path="/path/to/project")
    result = fc.search("find authentication handlers")
    print(result.to_context_string())
    
    # With Agent integration via context= param
    from praisonaiagents import Agent
    from praisonaiagents.context import ManagerConfig
    
    agent = Agent(
        name="CodeAssistant",
        context=True,  # Enable context management
    )
"""

import os
import hashlib
import json
import logging
from typing import Optional, List, Dict, Any

from praisonaiagents.context.fast.result import FastContextResult, FileMatch, LineRange
from praisonaiagents.context.fast.fast_context_agent import FastContextAgent

logger = logging.getLogger(__name__)


class FastContext:
    """High-level API for fast parallel code search.
    
    FastContext provides rapid code search capabilities using:
    - Parallel tool execution (up to 8 concurrent calls)
    - Limited turns (max 4) for fast response
    - Optional LLM-powered intelligent search
    - Result caching for repeated queries
    
    Attributes:
        workspace_path: Root directory for searches
        model: LLM model for intelligent search
        max_turns: Maximum search turns
        max_parallel: Maximum parallel tool calls
        cache_enabled: Whether to cache results
    """
    
    # Environment variable names for configuration
    ENV_MODEL = "FAST_CONTEXT_MODEL"
    ENV_MAX_TURNS = "FAST_CONTEXT_MAX_TURNS"
    ENV_MAX_PARALLEL = "FAST_CONTEXT_PARALLELISM"
    ENV_TIMEOUT = "FAST_CONTEXT_TIMEOUT"
    ENV_CACHE_ENABLED = "FAST_CONTEXT_CACHE"
    ENV_CACHE_TTL = "FAST_CONTEXT_CACHE_TTL"
    ENV_SEARCH_BACKEND = "FAST_CONTEXT_BACKEND"
    
    def __init__(
        self,
        workspace_path: Optional[str] = None,
        model: Optional[str] = None,
        max_turns: Optional[int] = None,
        max_parallel: Optional[int] = None,
        timeout: Optional[float] = None,
        cache_enabled: Optional[bool] = None,
        cache_ttl: Optional[int] = None,
        verbose: bool = False,
        # New optimization parameters
        search_backend: Optional[str] = None,
        enable_indexing: bool = False,
        index_path: Optional[str] = None,
        compression: Optional[str] = None
    ):
        """Initialize FastContext.
        
        Configuration can be set via parameters or environment variables.
        Parameters take precedence over environment variables.
        
        Environment variables:
            FAST_CONTEXT_MODEL: LLM model name (default: gpt-4o-mini)
            FAST_CONTEXT_MAX_TURNS: Maximum search turns (default: 4)
            FAST_CONTEXT_PARALLELISM: Max parallel calls (default: 8)
            FAST_CONTEXT_TIMEOUT: Timeout in seconds (default: 30.0)
            FAST_CONTEXT_CACHE: Enable caching (default: true)
            FAST_CONTEXT_CACHE_TTL: Cache TTL in seconds (default: 300)
            FAST_CONTEXT_BACKEND: Search backend (default: auto)
        
        Args:
            workspace_path: Root directory for searches (defaults to cwd)
            model: LLM model for intelligent search
            max_turns: Maximum search turns
            max_parallel: Maximum parallel tool calls per turn
            timeout: Timeout per tool call in seconds
            cache_enabled: Whether to cache search results
            cache_ttl: Cache time-to-live in seconds
            verbose: If True, print debug information
            search_backend: Search backend ("auto", "python", "ripgrep")
            enable_indexing: Enable incremental file indexing
            index_path: Custom path for index file
            compression: Compression strategy ("truncate", "smart", None)
        """
        self.workspace_path = os.path.abspath(workspace_path or os.getcwd())
        
        # Apply environment variable overrides with defaults
        self.model = model or os.environ.get(self.ENV_MODEL, "gpt-4o-mini")
        self.max_turns = max_turns if max_turns is not None else int(os.environ.get(self.ENV_MAX_TURNS, "4"))
        self.max_parallel = max_parallel if max_parallel is not None else int(os.environ.get(self.ENV_MAX_PARALLEL, "8"))
        self.timeout = timeout if timeout is not None else float(os.environ.get(self.ENV_TIMEOUT, "30.0"))
        
        # Cache settings
        cache_env = os.environ.get(self.ENV_CACHE_ENABLED, "true").lower()
        self.cache_enabled = cache_enabled if cache_enabled is not None else cache_env in ("true", "1", "yes")
        self.cache_ttl = cache_ttl if cache_ttl is not None else int(os.environ.get(self.ENV_CACHE_TTL, "300"))
        
        self.verbose = verbose
        
        # Optimization settings (all optional with graceful fallback)
        self.search_backend = search_backend or os.environ.get(self.ENV_SEARCH_BACKEND, "auto")
        self.enable_indexing = enable_indexing
        self.index_path = index_path
        self.compression = compression
        
        # Cache storage
        self._cache: Dict[str, Dict[str, Any]] = {}
        
        # Lazy-loaded components
        self._agent: Optional[FastContextAgent] = None
        self._backend = None  # SearchBackend instance
        self._index = None    # FileIndex instance
        self._compressor = None  # ContextCompressor instance
    
    def _get_agent(self) -> FastContextAgent:
        """Get or create FastContextAgent instance."""
        if self._agent is None:
            self._agent = FastContextAgent(
                workspace_path=self.workspace_path,
                max_turns=self.max_turns,
                max_parallel=self.max_parallel,
                model=self.model,
                timeout=self.timeout,
                verbose=self.verbose
            )
        return self._agent
    
    def _get_backend(self):
        """Get or create SearchBackend instance (lazy)."""
        if self._backend is None:
            from praisonaiagents.context.fast.search_backends import get_search_backend
            self._backend = get_search_backend(self.search_backend, workspace_path=self.workspace_path)
        return self._backend
    
    def _get_index(self):
        """Get or create FileIndex instance (lazy)."""
        if not self.enable_indexing:
            return None
        if self._index is None:
            from praisonaiagents.context.fast.index_manager import FileIndex
            self._index = FileIndex.load_or_create(self.workspace_path)
        return self._index
    
    def _get_compressor(self):
        """Get or create ContextCompressor instance (lazy)."""
        if not self.compression:
            return None
        if self._compressor is None:
            from praisonaiagents.context.fast.compressor import get_compressor
            self._compressor = get_compressor(self.compression)
        return self._compressor
    
    def _get_cache_key(self, query: str, **kwargs) -> str:
        """Generate cache key for a query."""
        key_data = {
            "query": query,
            "workspace": self.workspace_path,
            **kwargs
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_cached(self, cache_key: str) -> Optional[FastContextResult]:
        """Get cached result if valid."""
        if not self.cache_enabled:
            return None
        
        import time
        cached = self._cache.get(cache_key)
        if cached:
            if time.time() - cached["timestamp"] < self.cache_ttl:
                result = cached["result"]
                result.from_cache = True
                return result
            else:
                # Expired
                del self._cache[cache_key]
        return None
    
    def _set_cached(self, cache_key: str, result: FastContextResult) -> None:
        """Cache a result."""
        if not self.cache_enabled:
            return
        
        import time
        self._cache[cache_key] = {
            "result": result,
            "timestamp": time.time()
        }
    
    def search(
        self,
        query: str,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        use_llm: bool = False
    ) -> FastContextResult:
        """Search for code relevant to the query.
        
        Args:
            query: Search query (pattern or natural language)
            include_patterns: Glob patterns to include (e.g., ["*.py"])
            exclude_patterns: Glob patterns to exclude
            use_llm: If True, use LLM for intelligent search
            
        Returns:
            FastContextResult with matching files and lines
        """
        # Check cache
        cache_key = self._get_cache_key(
            query,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            use_llm=use_llm
        )
        cached = self._get_cached(cache_key)
        if cached:
            if self.verbose:
                logger.info(f"Cache hit for query: {query}")
            return cached
        
        # Perform search
        agent = self._get_agent()
        
        if use_llm:
            result = agent.search(query, include_patterns, exclude_patterns)
        else:
            result = agent.search_simple(query, include_patterns, exclude_patterns)
        
        # Cache result
        self._set_cached(cache_key, result)
        
        return result
    
    def search_files(
        self,
        pattern: str,
        max_results: int = 50
    ) -> FastContextResult:
        """Search for files matching a glob pattern.
        
        Args:
            pattern: Glob pattern (e.g., "**/*.py", "src/*.js")
            max_results: Maximum results to return
            
        Returns:
            FastContextResult with matching files
        """
        from praisonaiagents.context.fast.search_tools import glob_search
        
        result = FastContextResult(query=pattern)
        result.start_timer()
        
        matches = glob_search(
            self.workspace_path,
            pattern,
            max_results=max_results
        )
        
        for match in matches:
            result.add_file(FileMatch(
                path=match["path"],
                relevance_score=1.0
            ))
        
        result.stop_timer()
        result.turns_used = 1
        result.total_tool_calls = 1
        
        return result
    
    def read_context(
        self,
        filepath: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        context_lines: int = 5
    ) -> Optional[str]:
        """Read file content with context.
        
        Args:
            filepath: Path to file (relative to workspace)
            start_line: Starting line (1-indexed)
            end_line: Ending line (1-indexed)
            context_lines: Additional context lines
            
        Returns:
            File content string or None if error
        """
        from praisonaiagents.context.fast.search_tools import read_file
        
        full_path = filepath
        if not os.path.isabs(filepath):
            full_path = os.path.join(self.workspace_path, filepath)
        
        result = read_file(
            full_path,
            start_line=start_line,
            end_line=end_line,
            context_lines=context_lines
        )
        
        if result["success"]:
            return result["content"]
        return None
    
    def get_context_for_agent(
        self,
        query: str,
        max_files: int = 10,
        max_lines_per_file: int = 100,
        include_content: bool = True
    ) -> str:
        """Get formatted context string for an agent.
        
        This method searches for relevant code and formats it
        as a context string that can be injected into an agent's
        system prompt or message.
        
        Args:
            query: Search query
            max_files: Maximum files to include
            max_lines_per_file: Maximum lines per file
            include_content: Whether to include file content
            
        Returns:
            Formatted context string
        """
        result = self.search(query)
        
        if not result.files:
            return f"No relevant code found for: {query}"
        
        lines = [f"# Relevant Code Context for: {query}"]
        lines.append(f"Found {result.total_files} relevant file(s) in {result.search_time_ms}ms\n")
        
        for i, file_match in enumerate(result.files[:max_files]):
            lines.append(f"## {file_match.path}")
            
            if include_content and file_match.line_ranges:
                for lr in file_match.line_ranges:
                    # Limit lines
                    if lr.line_count > max_lines_per_file:
                        lr = LineRange(
                            start=lr.start,
                            end=lr.start + max_lines_per_file - 1,
                            content=lr.content,
                            relevance_score=lr.relevance_score
                        )
                    
                    lines.append(f"Lines {lr.start}-{lr.end}:")
                    
                    # Read content if not already present
                    if lr.content:
                        lines.append(f"```\n{lr.content}\n```")
                    else:
                        content = self.read_context(
                            file_match.path,
                            start_line=lr.start,
                            end_line=lr.end
                        )
                        if content:
                            lines.append(f"```\n{content}\n```")
            
            lines.append("")
        
        if len(result.files) > max_files:
            lines.append(f"... and {len(result.files) - max_files} more files")
        
        return "\n".join(lines)
    
    def clear_cache(self) -> None:
        """Clear the result cache."""
        self._cache.clear()
    
    def close(self) -> None:
        """Close resources."""
        if self._agent:
            self._agent.close()
            self._agent = None
        self._cache.clear()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Convenience function for quick searches
def fast_search(
    query: str,
    workspace_path: Optional[str] = None,
    **kwargs
) -> FastContextResult:
    """Convenience function for quick code search.
    
    Args:
        query: Search query
        workspace_path: Root directory (defaults to cwd)
        **kwargs: Additional arguments for FastContext
        
    Returns:
        FastContextResult with matching files
    """
    with FastContext(workspace_path=workspace_path, **kwargs) as fc:
        return fc.search(query)
