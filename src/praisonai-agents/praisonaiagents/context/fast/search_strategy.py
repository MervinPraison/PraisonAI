"""
Search Strategy for Fast Context.

Orchestrates multi-turn search with:
- Turn 1-3: Exploration (grep, glob, directory listing)
- Turn 4: Final answer (file list + line ranges)
- Early termination if sufficient context found
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from enum import Enum

from praisonaiagents.context.fast.result import FastContextResult, FileMatch, LineRange
from praisonaiagents.context.fast.parallel_executor import ToolCallBatch

logger = logging.getLogger(__name__)


class SearchPhase(Enum):
    """Phases of the search strategy."""
    DISCOVERY = "discovery"      # Turn 1: Discover structure
    EXPLORATION = "exploration"  # Turn 2-3: Deep search
    REFINEMENT = "refinement"    # Turn 4: Final answer


@dataclass
class SearchState:
    """Tracks the state of a multi-turn search.
    
    Attributes:
        query: Original search query
        current_turn: Current turn number (1-indexed)
        max_turns: Maximum turns allowed
        phase: Current search phase
        discovered_files: Files found so far
        explored_paths: Paths already explored
        result: Accumulated search result
        should_terminate: Whether to terminate early
    """
    query: str
    current_turn: int = 0
    max_turns: int = 4
    phase: SearchPhase = SearchPhase.DISCOVERY
    discovered_files: Set[str] = field(default_factory=set)
    explored_paths: Set[str] = field(default_factory=set)
    result: FastContextResult = field(default_factory=FastContextResult)
    should_terminate: bool = False
    
    # Thresholds for early termination
    min_files_for_termination: int = 5
    max_files_before_refinement: int = 20
    
    def advance_turn(self) -> None:
        """Advance to the next turn and update phase."""
        self.current_turn += 1
        
        if self.current_turn == 1:
            self.phase = SearchPhase.DISCOVERY
        elif self.current_turn < self.max_turns:
            self.phase = SearchPhase.EXPLORATION
        else:
            self.phase = SearchPhase.REFINEMENT
    
    def check_early_termination(self) -> bool:
        """Check if search should terminate early.
        
        Returns:
            True if search should terminate
        """
        # Terminate if we have enough high-quality results
        if len(self.discovered_files) >= self.min_files_for_termination:
            high_relevance = sum(
                1 for f in self.result.files 
                if f.relevance_score >= 0.8
            )
            if high_relevance >= 3:
                self.should_terminate = True
                return True
        
        # Terminate if we've explored everything
        if self.current_turn >= 2 and not self._has_unexplored_paths():
            self.should_terminate = True
            return True
        
        return False
    
    def _has_unexplored_paths(self) -> bool:
        """Check if there are unexplored paths."""
        # Simple heuristic: if we found files but haven't explored many paths
        return len(self.discovered_files) > len(self.explored_paths) * 2


class SearchStrategy:
    """Orchestrates multi-turn search strategy.
    
    Implements the Fast Context search approach:
    - Turn 1: Discovery - understand codebase structure
    - Turn 2-3: Exploration - deep search for relevant code
    - Turn 4: Refinement - finalize results
    
    Supports early termination when sufficient context is found.
    """
    
    def __init__(
        self,
        workspace_path: str,
        max_turns: int = 4,
        max_parallel: int = 8
    ):
        """Initialize search strategy.
        
        Args:
            workspace_path: Root directory for searches
            max_turns: Maximum search turns
            max_parallel: Maximum parallel tool calls per turn
        """
        self.workspace_path = workspace_path
        self.max_turns = max_turns
        self.max_parallel = max_parallel
    
    def create_state(self, query: str) -> SearchState:
        """Create a new search state.
        
        Args:
            query: Search query
            
        Returns:
            New SearchState instance
        """
        state = SearchState(query=query, max_turns=self.max_turns)
        state.result.query = query
        return state
    
    def plan_discovery_turn(self, state: SearchState) -> ToolCallBatch:
        """Plan the discovery turn (Turn 1).
        
        Focus on understanding codebase structure:
        - List root directory
        - Find common file patterns
        - Initial grep for query terms
        
        Args:
            state: Current search state
            
        Returns:
            Batch of tool calls to execute
        """
        batch = ToolCallBatch(max_size=self.max_parallel)
        query = state.query
        
        # List root directory
        batch.add("list_directory", dir_path=self.workspace_path, recursive=False)
        
        # Find Python files (most common)
        batch.add("glob_search", search_path=self.workspace_path, pattern="**/*.py", max_results=20)
        
        # Initial grep for query terms
        query_words = query.lower().split()
        for word in query_words[:3]:  # First 3 words
            if len(word) >= 3:  # Skip short words
                batch.add("grep_search", search_path=self.workspace_path, pattern=word, max_results=10)
                if batch.is_full:
                    break
        
        return batch
    
    def plan_exploration_turn(self, state: SearchState) -> ToolCallBatch:
        """Plan an exploration turn (Turn 2-3).
        
        Deep search based on discovery results:
        - Search in discovered directories
        - Read promising files
        - Follow references
        
        Args:
            state: Current search state
            
        Returns:
            Batch of tool calls to execute
        """
        batch = ToolCallBatch(max_size=self.max_parallel)
        
        # Read top files found so far
        for file_match in state.result.files[:4]:
            if file_match.path not in state.explored_paths:
                batch.add("read_file", filepath=file_match.path, context_lines=5)
                state.explored_paths.add(file_match.path)
                if batch.is_full:
                    break
        
        # Search in unexplored directories
        unexplored_dirs = self._find_unexplored_dirs(state)
        for dir_path in unexplored_dirs[:2]:
            batch.add("list_directory", dir_path=dir_path, recursive=True, max_depth=2)
            if batch.is_full:
                break
        
        # Additional grep searches with refined patterns
        if not batch.is_full:
            refined_patterns = self._generate_refined_patterns(state)
            for pattern in refined_patterns[:2]:
                batch.add("grep_search", search_path=self.workspace_path, pattern=pattern, max_results=15)
                if batch.is_full:
                    break
        
        return batch
    
    def plan_refinement_turn(self, state: SearchState) -> ToolCallBatch:
        """Plan the refinement turn (Turn 4).
        
        Finalize results:
        - Read remaining important files
        - Get specific line ranges
        
        Args:
            state: Current search state
            
        Returns:
            Batch of tool calls to execute
        """
        batch = ToolCallBatch(max_size=self.max_parallel)
        
        # Read top files that haven't been fully explored
        for file_match in state.result.files[:self.max_parallel]:
            if file_match.path not in state.explored_paths:
                # Read specific line ranges if available
                if file_match.line_ranges:
                    for lr in file_match.line_ranges[:2]:
                        batch.add(
                            "read_file",
                            filepath=file_match.path,
                            start_line=max(1, lr.start - 5),
                            end_line=lr.end + 5
                        )
                        if batch.is_full:
                            break
                else:
                    batch.add("read_file", filepath=file_match.path)
                
                state.explored_paths.add(file_match.path)
                if batch.is_full:
                    break
        
        return batch
    
    def plan_next_turn(self, state: SearchState) -> Optional[ToolCallBatch]:
        """Plan the next turn based on current state.
        
        Args:
            state: Current search state
            
        Returns:
            Batch of tool calls, or None if search should end
        """
        state.advance_turn()
        
        # Check for early termination
        if state.should_terminate or state.current_turn > state.max_turns:
            return None
        
        if state.check_early_termination():
            return None
        
        # Plan based on phase
        if state.phase == SearchPhase.DISCOVERY:
            return self.plan_discovery_turn(state)
        elif state.phase == SearchPhase.EXPLORATION:
            return self.plan_exploration_turn(state)
        else:  # REFINEMENT
            return self.plan_refinement_turn(state)
    
    def process_results(
        self,
        state: SearchState,
        tool_results: List[Any]
    ) -> None:
        """Process results from a turn and update state.
        
        Args:
            state: Current search state
            tool_results: Results from tool execution
        """
        for result in tool_results:
            if isinstance(result, list):
                # Grep or glob results
                for item in result:
                    if isinstance(item, dict):
                        path = item.get("path", "")
                        if path:
                            state.discovered_files.add(path)
                            
                            # Create or update file match
                            file_match = FileMatch(
                                path=path,
                                relevance_score=0.8,
                                match_count=1
                            )
                            
                            # Add line range if available
                            line_num = item.get("line_number")
                            if line_num:
                                file_match.add_line_range(LineRange(
                                    start=max(1, line_num - 2),
                                    end=line_num + 2,
                                    content=item.get("context"),
                                    relevance_score=0.8
                                ))
                            
                            state.result.add_file(file_match)
            
            elif isinstance(result, dict):
                # Read file or list directory result
                if result.get("success"):
                    path = result.get("path", "")
                    if path:
                        state.explored_paths.add(path)
                    
                    # Handle directory listing
                    entries = result.get("entries", [])
                    for entry in entries:
                        if not entry.get("is_dir"):
                            state.discovered_files.add(entry.get("path", ""))
    
    def _find_unexplored_dirs(self, state: SearchState) -> List[str]:
        """Find directories that haven't been explored.
        
        Args:
            state: Current search state
            
        Returns:
            List of unexplored directory paths
        """
        import os
        
        # Extract unique directories from discovered files
        dirs = set()
        for file_path in state.discovered_files:
            dir_path = os.path.dirname(file_path)
            if dir_path and dir_path not in state.explored_paths:
                dirs.add(dir_path)
        
        return list(dirs)[:5]  # Limit to 5
    
    def _generate_refined_patterns(self, state: SearchState) -> List[str]:
        """Generate refined search patterns based on results.
        
        Args:
            state: Current search state
            
        Returns:
            List of refined search patterns
        """
        patterns = []
        query_words = state.query.lower().split()
        
        # Combine query words
        if len(query_words) >= 2:
            patterns.append(f"{query_words[0]}.*{query_words[1]}")
        
        # Add common code patterns
        for word in query_words[:2]:
            if len(word) >= 3:
                patterns.append(f"def {word}")
                patterns.append(f"class {word}")
        
        return patterns[:4]
