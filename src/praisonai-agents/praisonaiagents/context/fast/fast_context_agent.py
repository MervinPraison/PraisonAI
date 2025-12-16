"""
FastContextAgent - Specialized subagent for rapid code search.

This agent is designed for fast context retrieval using:
- Parallel tool execution (up to 8 concurrent calls)
- Limited turns (max 4) for fast response
- Lightweight model (gpt-4o-mini by default)
- Restricted tool set (grep, glob, read, list_dir)
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional

from praisonaiagents.context.fast.result import (
    FastContextResult,
    FileMatch,
    LineRange
)
from praisonaiagents.context.fast.search_tools import (
    grep_search,
    glob_search,
    read_file,
    list_directory,
    FAST_CONTEXT_TOOLS
)
from praisonaiagents.context.fast.parallel_executor import (
    ToolCallBatch,
    ParallelSearchCoordinator
)

logger = logging.getLogger(__name__)


class FastContextAgent:
    """Specialized agent for fast parallel code search.
    
    This agent performs rapid code search using parallel tool calls
    and a lightweight model optimized for retrieval tasks.
    
    Attributes:
        workspace_path: Root directory for searches
        max_turns: Maximum search turns (default: 4)
        max_parallel: Maximum parallel tool calls (default: 8)
        model: LLM model for intelligent search (default: gpt-4o-mini)
        timeout: Timeout per tool call in seconds
    """
    
    def __init__(
        self,
        workspace_path: str,
        max_turns: int = 4,
        max_parallel: int = 8,
        model: str = "gpt-4o-mini",
        timeout: float = 30.0,
        verbose: bool = False
    ):
        """Initialize FastContextAgent.
        
        Args:
            workspace_path: Root directory for searches
            max_turns: Maximum search turns
            max_parallel: Maximum parallel tool calls per turn
            model: LLM model name for intelligent search
            timeout: Timeout per tool call in seconds
            verbose: If True, print debug information
        """
        self.workspace_path = os.path.abspath(workspace_path)
        self.max_turns = max_turns
        self.max_parallel = max_parallel
        self.model = model
        self.timeout = timeout
        self.verbose = verbose
        
        # Initialize coordinator
        self.coordinator = ParallelSearchCoordinator(
            max_parallel=max_parallel,
            max_turns=max_turns,
            timeout=timeout
        )
        
        # LLM instance (lazy loaded)
        self._llm = None
    
    def _get_llm(self):
        """Get or create LLM instance (lazy loading)."""
        if self._llm is None:
            try:
                from praisonaiagents.llm import LLM
                self._llm = LLM(model=self.model)
            except Exception as e:
                logger.warning(f"Could not initialize LLM: {e}")
                self._llm = None
        return self._llm
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Get tool definitions for LLM function calling.
        
        Returns:
            List of tool definition dictionaries
        """
        return FAST_CONTEXT_TOOLS
    
    def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """Execute a single tool.
        
        Args:
            tool_name: Name of the tool
            **kwargs: Tool arguments
            
        Returns:
            Tool result
        """
        # Prepend workspace path if needed
        if tool_name in ("grep_search", "glob_search"):
            if "search_path" not in kwargs or kwargs["search_path"] == ".":
                kwargs["search_path"] = self.workspace_path
            elif not os.path.isabs(kwargs["search_path"]):
                kwargs["search_path"] = os.path.join(
                    self.workspace_path, kwargs["search_path"]
                )
        elif tool_name == "list_directory":
            if "dir_path" not in kwargs or kwargs["dir_path"] == ".":
                kwargs["dir_path"] = self.workspace_path
            elif not os.path.isabs(kwargs["dir_path"]):
                kwargs["dir_path"] = os.path.join(
                    self.workspace_path, kwargs["dir_path"]
                )
        elif tool_name == "read_file":
            if "filepath" in kwargs and not os.path.isabs(kwargs["filepath"]):
                kwargs["filepath"] = os.path.join(
                    self.workspace_path, kwargs["filepath"]
                )
        
        tools = {
            "grep_search": grep_search,
            "glob_search": glob_search,
            "read_file": read_file,
            "list_directory": list_directory
        }
        
        if tool_name not in tools:
            return {"error": f"Unknown tool: {tool_name}"}
        
        try:
            return tools[tool_name](**kwargs)
        except Exception as e:
            return {"error": str(e)}
    
    def search_simple(
        self,
        query: str,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        max_results: int = 50
    ) -> FastContextResult:
        """Perform a simple search without LLM.
        
        This is a fast, direct search that doesn't use the LLM
        for query understanding. Good for simple pattern searches.
        
        Args:
            query: Search pattern
            include_patterns: Glob patterns to include
            exclude_patterns: Glob patterns to exclude
            max_results: Maximum results per tool
            
        Returns:
            FastContextResult with matching files and lines
        """
        result = FastContextResult(query=query)
        result.start_timer()
        
        # Execute grep search
        grep_results = grep_search(
            search_path=self.workspace_path,
            pattern=query,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            max_results=max_results,
            context_lines=2
        )
        
        # Convert to FastContextResult format
        for match in grep_results:
            file_match = FileMatch(
                path=match["path"],
                relevance_score=1.0,
                match_count=1
            )
            file_match.add_line_range(LineRange(
                start=max(1, match["line_number"] - 2),
                end=match["line_number"] + 2,
                content=match.get("context"),
                relevance_score=1.0
            ))
            result.add_file(file_match)
        
        result.stop_timer()
        result.turns_used = 1
        result.total_tool_calls = 1
        
        return result
    
    def search(
        self,
        query: str,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> FastContextResult:
        """Perform intelligent search using LLM.
        
        Uses the LLM to understand the query and plan search strategy,
        then executes parallel tool calls to find relevant code.
        
        Args:
            query: Natural language search query
            include_patterns: Glob patterns to include
            exclude_patterns: Glob patterns to exclude
            
        Returns:
            FastContextResult with matching files and lines
        """
        result = FastContextResult(query=query)
        result.start_timer()
        
        llm = self._get_llm()
        
        # If no LLM available, fall back to simple search
        if llm is None:
            logger.info("LLM not available, falling back to simple search")
            return self.search_simple(query, include_patterns, exclude_patterns)
        
        self.coordinator.start()
        
        # System prompt for the search agent
        system_prompt = f"""You are a fast code search agent. Your task is to find relevant code in a codebase.

Workspace: {self.workspace_path}

You have access to these tools:
- grep_search: Search for patterns in files
- glob_search: Find files by pattern
- read_file: Read file contents
- list_directory: List directory contents

Strategy:
1. Start with broad searches (glob, list_directory) to understand structure
2. Use grep_search to find specific patterns
3. Use read_file to get detailed context for relevant files
4. Execute up to {self.max_parallel} tool calls in parallel per turn
5. Complete search in {self.max_turns} turns or less

Return files and line ranges that are relevant to the query.
Be efficient - use parallel tool calls to explore multiple paths at once."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Find code relevant to: {query}"}
        ]
        
        # Add file pattern constraints if provided
        if include_patterns:
            messages[1]["content"] += f"\nOnly search in files matching: {include_patterns}"
        if exclude_patterns:
            messages[1]["content"] += f"\nExclude files matching: {exclude_patterns}"
        
        try:
            # Multi-turn search loop
            for turn in range(self.max_turns):
                if self.verbose:
                    logger.info(f"Search turn {turn + 1}/{self.max_turns}")
                
                # Get LLM response with tool calls
                response = llm.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=[{"type": "function", "function": t} for t in self.get_tools()],
                    tool_choice="auto"
                )
                
                message = response.choices[0].message
                
                # Check if we have tool calls
                if not message.tool_calls:
                    # No more tool calls, search complete
                    break
                
                # Execute tool calls in parallel
                batch = ToolCallBatch(max_size=self.max_parallel)
                tool_call_map = {}  # Map tool call ID to batch index
                
                for tool_call in message.tool_calls[:self.max_parallel]:
                    try:
                        args = json.loads(tool_call.function.arguments)
                        batch.add(tool_call.function.name, **args)
                        tool_call_map[tool_call.id] = len(batch.tasks) - 1
                    except json.JSONDecodeError:
                        continue
                
                # Execute batch
                if batch.tasks:
                    tool_results = self.coordinator.execute_turn_sync(batch)
                    
                    # Process results
                    messages.append({"role": "assistant", "content": None, "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls[:self.max_parallel]
                    ]})
                    
                    # Add tool results to messages
                    for tool_call in message.tool_calls[:self.max_parallel]:
                        idx = tool_call_map.get(tool_call.id)
                        if idx is not None and idx < len(tool_results):
                            tool_result = tool_results[idx]
                            
                            # Process grep results into FastContextResult
                            if tool_call.function.name == "grep_search":
                                if isinstance(tool_result, list):
                                    for match in tool_result:
                                        file_match = FileMatch(
                                            path=match.get("path", ""),
                                            relevance_score=1.0,
                                            match_count=1
                                        )
                                        line_num = match.get("line_number", 1)
                                        file_match.add_line_range(LineRange(
                                            start=max(1, line_num - 2),
                                            end=line_num + 2,
                                            content=match.get("context"),
                                            relevance_score=1.0
                                        ))
                                        result.add_file(file_match)
                            
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(tool_result) if not isinstance(tool_result, str) else tool_result
                            })
        
        except Exception as e:
            logger.error(f"Error during LLM search: {e}")
            # Fall back to simple search
            return self.search_simple(query, include_patterns, exclude_patterns)
        
        finally:
            self.coordinator.stop()
        
        result.stop_timer()
        result.turns_used = self.coordinator.turns_used
        result.total_tool_calls = self.coordinator.total_tool_calls
        result.sort_by_relevance()
        
        return result
    
    async def search_async(
        self,
        query: str,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> FastContextResult:
        """Async version of search.
        
        Args:
            query: Natural language search query
            include_patterns: Glob patterns to include
            exclude_patterns: Glob patterns to exclude
            
        Returns:
            FastContextResult with matching files and lines
        """
        # For now, wrap sync version
        # TODO: Implement true async with async LLM calls
        return self.search(query, include_patterns, exclude_patterns)
    
    def close(self) -> None:
        """Close resources."""
        self.coordinator.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
