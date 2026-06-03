"""
Loop Guard for Tool Execution Safety.

Provides idempotency-aware guardrails to prevent tool execution loops in 
standard agent.chat() path, extending the existing DoomLoopDetector infrastructure.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, Set
from enum import Enum
import time

from .doom_loop import DoomLoopDetector, DoomLoopConfig


# Tool classification constants
IDEMPOTENT_TOOLS: Set[str] = frozenset({
    # File and search operations (safe to repeat)
    "read_file", "list_files", "search_files", "glob", "grep",
    "get_file_contents", "file_exists", "directory_exists",
    
    # Web and search operations
    "web_search", "duckduckgo_search", "spider_search", "fetch_url",
    "google_search", "bing_search", "perplexity_search",
    
    # Memory and knowledge retrieval
    "get_memory", "search_memory", "list_memories", "knowledge_search",
    "vector_search", "semantic_search",
    
    # System information (read-only)
    "get_system_info", "list_processes", "get_environment", "pwd",
    "whoami", "date", "uptime", "ps", "top", "df", "free",
    
    # Git operations (read-only)
    "git_status", "git_log", "git_diff", "git_show", "git_branch",
    "git_remote", "git_config",
    
    # Database queries (read-only)
    "db_query", "sql_select", "mongo_find", "redis_get",
    
    # API calls (read-only) 
    "api_get", "rest_get", "http_get", "curl_get",
    
    # Tool and command inspection
    "tool_search", "tool_describe", "which", "man", "help",
    "command_exists", "get_command_info",
})

MUTATING_TOOLS: Set[str] = frozenset({
    # File operations (modify state)
    "write_file", "edit_file", "patch_file", "delete_file", "move_file",
    "copy_file", "create_file", "append_file", "chmod", "chown",
    "mkdir", "rmdir", "touch", "ln", "unlink",
    
    # Code execution
    "execute_code", "run_python", "exec", "eval", "shell", "bash",
    "subprocess", "system", "popen", "call",
    
    # Git operations (modify state) 
    "git_add", "git_commit", "git_push", "git_pull", "git_merge",
    "git_rebase", "git_reset", "git_checkout", "git_branch_create",
    "git_tag", "git_stash", "git_apply", "git_cherry_pick",
    
    # Database modifications
    "db_insert", "db_update", "db_delete", "sql_insert", "sql_update",
    "sql_delete", "mongo_insert", "mongo_update", "mongo_delete",
    "redis_set", "redis_del",
    
    # API calls (modify state)
    "api_post", "api_put", "api_delete", "api_patch", "rest_post",
    "rest_put", "rest_delete", "http_post", "http_put", "http_delete",
    
    # Memory operations (modify state)
    "store_memory", "delete_memory", "update_memory", "clear_memory",
    
    # System operations
    "install_package", "uninstall_package", "kill_process", "restart_service",
    "start_service", "stop_service", "mount", "umount",
    
    # Tool execution proxy
    "tool_call", "execute_tool",
})


class GuardAction(Enum):
    """Actions the loop guard can take."""
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    HALT = "halt"


@dataclass
class LoopGuardConfig:
    """Configuration for loop guard behavior."""
    # Enable/disable the guard
    enabled: bool = True
    
    # Per-turn thresholds for idempotent tools
    idempotent_warn_threshold: int = 5
    idempotent_block_threshold: int = 8
    idempotent_halt_threshold: int = 12
    
    # Per-turn thresholds for mutating tools
    mutating_warn_threshold: int = 3
    mutating_block_threshold: int = 5
    mutating_halt_threshold: int = 7
    
    # Time-based limits
    max_time_per_turn: float = 120.0  # Max seconds per chat turn
    
    # No-progress detection
    no_progress_warn: int = 4
    no_progress_halt: int = 8


@dataclass
class LoopGuardDecision:
    """Decision made by the loop guard."""
    action: GuardAction
    code: str
    message: str
    metadata: Dict[str, Any] = None
    
    def should_block(self) -> bool:
        """Check if this decision blocks execution."""
        return self.action in (GuardAction.BLOCK, GuardAction.HALT)


class LoopGuard:
    """
    Idempotency-aware tool execution loop guard.
    
    Extends DoomLoopDetector with tool classification and graduated responses.
    Provides lightweight, always-on protection for agent.chat() path.
    
    Example:
        guard = LoopGuard()
        guard.record("read_file", {"path": "test.py"}, True)
        decision = guard.check("read_file", {"path": "test.py"})
        if decision.should_block():
            return {"error": decision.message}
    """
    
    def __init__(self, config: Optional[LoopGuardConfig] = None):
        """Initialize loop guard with configuration."""
        self.config = config or LoopGuardConfig()
        
        # Initialize underlying doom loop detector with appropriate config
        doom_config = DoomLoopConfig(
            max_identical_actions=max(
                self.config.idempotent_halt_threshold,
                self.config.mutating_halt_threshold
            ),
            max_similar_actions=max(
                self.config.idempotent_halt_threshold, 
                self.config.mutating_halt_threshold
            ),
            max_consecutive_failures=3,
            max_no_progress_steps=self.config.no_progress_halt,
            max_total_time=self.config.max_time_per_turn,
        )
        self.detector = DoomLoopDetector(doom_config)
        
        # Turn-based tracking
        self._turn_start_time: Optional[float] = None
        self._tool_counts: Dict[str, int] = {}
        self._last_progress_count = 0
        
    def reset_turn(self) -> None:
        """Reset tracking for a new chat turn."""
        self._turn_start_time = time.time()
        self._tool_counts.clear()
        # Reset the underlying DoomLoopDetector to clear cross-turn state
        self.detector.start_session()
        self._last_progress_count = 0
        
    def record(self, tool_name: str, args: Dict[str, Any], success: bool) -> None:
        """Record a tool execution for loop detection."""
        if not self.config.enabled:
            return
            
        # Initialize turn tracking if needed
        if self._turn_start_time is None:
            self.reset_turn()
            
        # Record in underlying detector
        self.detector.record_action(
            action_type=tool_name,
            args=args,
            result=success,  # Simple success flag for now
            success=success,
        )
        
        # Track per-turn counts
        self._tool_counts[tool_name] = self._tool_counts.get(tool_name, 0) + 1
        
    def check(self, tool_name: str, args: Dict[str, Any], is_pre_execution: bool = True) -> LoopGuardDecision:
        """
        Check if tool execution should be allowed, warned, blocked, or halted.
        
        Args:
            tool_name: Name of the tool to execute
            args: Arguments for the tool
            is_pre_execution: True for pre-execution checks, False for post-execution
            
        Returns:
            LoopGuardDecision with action and message
        """
        if not self.config.enabled:
            return LoopGuardDecision(
                action=GuardAction.ALLOW,
                code="disabled",
                message="Loop guard disabled"
            )
            
        # Initialize turn tracking if needed
        if self._turn_start_time is None:
            self.reset_turn()
            
        # Check time-based limits
        elapsed = time.time() - self._turn_start_time
        if elapsed > self.config.max_time_per_turn:
            return LoopGuardDecision(
                action=GuardAction.HALT,
                code="time_exceeded",
                message=f"Turn time limit exceeded ({elapsed:.1f}s > {self.config.max_time_per_turn}s)",
                metadata={"elapsed_time": elapsed}
            )
            
        # Get current count for this tool
        current_count = self._tool_counts.get(tool_name, 0)
        
        # For pre-execution checks, account for the pending execution
        if is_pre_execution:
            current_count += 1
        
        # Check for no-progress patterns first
        no_progress_decision = self._check_no_progress()
        if no_progress_decision and no_progress_decision.action != GuardAction.ALLOW:
            return no_progress_decision
            
        # Classify tool and apply appropriate thresholds
        if self._is_idempotent_tool(tool_name):
            return self._check_idempotent_tool(tool_name, current_count, args)
        else:
            return self._check_mutating_tool(tool_name, current_count, args)
            
    def _is_idempotent_tool(self, tool_name: str) -> bool:
        """Check if a tool is classified as idempotent."""
        # Explicit classification takes precedence
        if tool_name in IDEMPOTENT_TOOLS:
            return True
        if tool_name in MUTATING_TOOLS:
            return False
            
        # Heuristic classification for unknown tools
        # Tools with read/get/list/search patterns are likely idempotent
        read_patterns = ['read', 'get', 'list', 'search', 'find', 'show', 'view', 'check']
        tool_lower = tool_name.lower()
        return any(pattern in tool_lower for pattern in read_patterns)
        
    def _check_idempotent_tool(
        self, 
        tool_name: str, 
        count: int, 
        args: Dict[str, Any]
    ) -> LoopGuardDecision:
        """Check thresholds for idempotent tools."""
        if count >= self.config.idempotent_halt_threshold:
            return LoopGuardDecision(
                action=GuardAction.HALT,
                code="idempotent_halt",
                message=f"Tool '{tool_name}' called {count} times this turn (halt threshold: {self.config.idempotent_halt_threshold}). This may indicate a stuck loop.",
                metadata={"tool_name": tool_name, "count": count, "args": args}
            )
        elif count >= self.config.idempotent_block_threshold:
            return LoopGuardDecision(
                action=GuardAction.BLOCK,
                code="idempotent_block", 
                message=f"Tool '{tool_name}' called {count} times this turn (block threshold: {self.config.idempotent_block_threshold}). Consider if this is making progress.",
                metadata={"tool_name": tool_name, "count": count}
            )
        elif count >= self.config.idempotent_warn_threshold:
            return LoopGuardDecision(
                action=GuardAction.WARN,
                code="idempotent_warn",
                message=f"Tool '{tool_name}' called {count} times this turn. Consider if repeated calls are needed.",
                metadata={"tool_name": tool_name, "count": count}
            )
        else:
            return LoopGuardDecision(
                action=GuardAction.ALLOW,
                code="idempotent_allow",
                message="Tool execution allowed"
            )
            
    def _check_mutating_tool(
        self, 
        tool_name: str, 
        count: int, 
        args: Dict[str, Any]
    ) -> LoopGuardDecision:
        """Check thresholds for mutating tools."""
        if count >= self.config.mutating_halt_threshold:
            return LoopGuardDecision(
                action=GuardAction.HALT,
                code="mutating_halt",
                message=f"Mutating tool '{tool_name}' called {count} times this turn (halt threshold: {self.config.mutating_halt_threshold}). This may cause unintended side effects.",
                metadata={"tool_name": tool_name, "count": count, "args": args}
            )
        elif count >= self.config.mutating_block_threshold:
            return LoopGuardDecision(
                action=GuardAction.BLOCK,
                code="mutating_block",
                message=f"Mutating tool '{tool_name}' called {count} times this turn (block threshold: {self.config.mutating_block_threshold}). Verify this is intentional.",
                metadata={"tool_name": tool_name, "count": count}
            )
        elif count >= self.config.mutating_warn_threshold:
            return LoopGuardDecision(
                action=GuardAction.WARN,
                code="mutating_warn", 
                message=f"Mutating tool '{tool_name}' called {count} times this turn. Be careful of side effects.",
                metadata={"tool_name": tool_name, "count": count}
            )
        else:
            return LoopGuardDecision(
                action=GuardAction.ALLOW,
                code="mutating_allow",
                message="Tool execution allowed"
            )
            
    def _check_no_progress(self) -> Optional[LoopGuardDecision]:
        """Check for no-progress patterns."""
        current_progress = len(self.detector._progress_markers)
        actions_since_progress = len(self.detector._actions) - self._last_progress_count
        
        if actions_since_progress >= self.config.no_progress_halt:
            return LoopGuardDecision(
                action=GuardAction.HALT,
                code="no_progress_halt",
                message=f"No progress detected in {actions_since_progress} tool calls. Agent may be stuck.",
                metadata={"actions_since_progress": actions_since_progress}
            )
        elif actions_since_progress >= self.config.no_progress_warn:
            return LoopGuardDecision(
                action=GuardAction.WARN,
                code="no_progress_warn",
                message=f"Limited progress in {actions_since_progress} tool calls. Consider changing approach.",
                metadata={"actions_since_progress": actions_since_progress}
            )
        return None
        
    def mark_progress(self, marker: str) -> None:
        """Mark that meaningful progress has been made."""
        self.detector.mark_progress(marker)
        self._last_progress_count = len(self.detector._progress_markers)
        
    def get_stats(self) -> Dict[str, Any]:
        """Get loop guard statistics."""
        base_stats = self.detector.get_stats()
        base_stats.update({
            "turn_elapsed": time.time() - self._turn_start_time if self._turn_start_time else 0,
            "tool_counts": dict(self._tool_counts),
            "config": {
                "enabled": self.config.enabled,
                "idempotent_thresholds": [
                    self.config.idempotent_warn_threshold,
                    self.config.idempotent_block_threshold, 
                    self.config.idempotent_halt_threshold
                ],
                "mutating_thresholds": [
                    self.config.mutating_warn_threshold,
                    self.config.mutating_block_threshold,
                    self.config.mutating_halt_threshold
                ]
            }
        })
        return base_stats