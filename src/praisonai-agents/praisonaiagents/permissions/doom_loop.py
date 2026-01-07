"""
Doom Loop Detection for PraisonAI Agents.

Detects and prevents agents from getting stuck in repetitive loops.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default thresholds
DEFAULT_LOOP_THRESHOLD = 3
DEFAULT_WINDOW_SECONDS = 60
DEFAULT_MAX_TOOL_CALLS = 50


@dataclass
class ToolCallRecord:
    """Record of a tool call for loop detection."""
    
    tool_name: str
    arguments_hash: str
    timestamp: float = field(default_factory=time.time)
    session_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments_hash": self.arguments_hash,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
        }


@dataclass
class DoomLoopResult:
    """Result of a doom loop check."""
    
    is_loop: bool
    reason: str = ""
    loop_count: int = 0
    tool_name: Optional[str] = None
    recommendation: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_loop": self.is_loop,
            "reason": self.reason,
            "loop_count": self.loop_count,
            "tool_name": self.tool_name,
            "recommendation": self.recommendation,
        }


class DoomLoopDetector:
    """
    Detects and prevents doom loops in agent execution.
    
    A doom loop occurs when an agent repeatedly calls the same
    tool with the same arguments, indicating it's stuck.
    
    Example:
        detector = DoomLoopDetector()
        
        # Record tool calls
        detector.record("bash", {"command": "ls"})
        detector.record("bash", {"command": "ls"})
        detector.record("bash", {"command": "ls"})
        
        # Check for loop
        result = detector.check("bash", {"command": "ls"})
        if result.is_loop:
            print(f"Doom loop detected: {result.reason}")
    """
    
    def __init__(
        self,
        loop_threshold: int = DEFAULT_LOOP_THRESHOLD,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    ):
        """
        Initialize the doom loop detector.
        
        Args:
            loop_threshold: Number of identical calls to trigger loop detection
            window_seconds: Time window for counting calls
            max_tool_calls: Maximum total tool calls before warning
        """
        self.loop_threshold = loop_threshold
        self.window_seconds = window_seconds
        self.max_tool_calls = max_tool_calls
        
        self._records: List[ToolCallRecord] = []
        self._call_counts: Dict[str, int] = defaultdict(int)
        self._session_id: Optional[str] = None
    
    def set_session(self, session_id: str):
        """Set the current session ID."""
        self._session_id = session_id
    
    def _hash_arguments(self, arguments: Dict[str, Any]) -> str:
        """Create a hash of tool arguments."""
        import hashlib
        import json
        
        try:
            arg_str = json.dumps(arguments, sort_keys=True, default=str)
            return hashlib.md5(arg_str.encode()).hexdigest()[:16]
        except (TypeError, ValueError):
            return "unhashable"
    
    def _cleanup_old_records(self):
        """Remove records outside the time window."""
        cutoff = time.time() - self.window_seconds
        self._records = [r for r in self._records if r.timestamp > cutoff]
    
    def record(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> ToolCallRecord:
        """
        Record a tool call.
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            
        Returns:
            The recorded ToolCallRecord
        """
        self._cleanup_old_records()
        
        args_hash = self._hash_arguments(arguments or {})
        
        record = ToolCallRecord(
            tool_name=tool_name,
            arguments_hash=args_hash,
            session_id=self._session_id,
        )
        
        self._records.append(record)
        self._call_counts[tool_name] += 1
        
        return record
    
    def check(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> DoomLoopResult:
        """
        Check if calling this tool would indicate a doom loop.
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            
        Returns:
            DoomLoopResult indicating if a loop is detected
        """
        self._cleanup_old_records()
        
        args_hash = self._hash_arguments(arguments or {})
        
        # Count identical calls in window
        identical_count = sum(
            1 for r in self._records
            if r.tool_name == tool_name and r.arguments_hash == args_hash
        )
        
        # Check for loop
        if identical_count >= self.loop_threshold:
            return DoomLoopResult(
                is_loop=True,
                reason=f"Tool '{tool_name}' called {identical_count} times with same arguments",
                loop_count=identical_count,
                tool_name=tool_name,
                recommendation="Consider a different approach or ask for user guidance",
            )
        
        # Check for excessive tool calls
        total_calls = len(self._records)
        if total_calls >= self.max_tool_calls:
            return DoomLoopResult(
                is_loop=True,
                reason=f"Excessive tool calls ({total_calls}) in time window",
                loop_count=total_calls,
                recommendation="Reduce tool usage or break task into smaller steps",
            )
        
        # Check for tool-specific excessive calls
        tool_count = self._call_counts.get(tool_name, 0)
        if tool_count >= self.max_tool_calls // 2:
            return DoomLoopResult(
                is_loop=True,
                reason=f"Tool '{tool_name}' called excessively ({tool_count} times)",
                loop_count=tool_count,
                tool_name=tool_name,
                recommendation=f"Consider alternative to '{tool_name}'",
            )
        
        return DoomLoopResult(
            is_loop=False,
            loop_count=identical_count,
            tool_name=tool_name,
        )
    
    def record_and_check(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> DoomLoopResult:
        """
        Record a tool call and check for doom loop.
        
        Convenience method that combines record() and check().
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            
        Returns:
            DoomLoopResult indicating if a loop is detected
        """
        result = self.check(tool_name, arguments)
        if not result.is_loop:
            self.record(tool_name, arguments)
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about tool calls."""
        self._cleanup_old_records()
        
        return {
            "total_calls": len(self._records),
            "unique_tools": len(set(r.tool_name for r in self._records)),
            "call_counts": dict(self._call_counts),
            "window_seconds": self.window_seconds,
            "loop_threshold": self.loop_threshold,
        }
    
    def reset(self):
        """Reset all records."""
        self._records.clear()
        self._call_counts.clear()
    
    def reset_tool(self, tool_name: str):
        """Reset records for a specific tool."""
        self._records = [r for r in self._records if r.tool_name != tool_name]
        self._call_counts.pop(tool_name, None)
