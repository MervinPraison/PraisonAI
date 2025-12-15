"""
Cascade Hooks System for PraisonAI Agents.

Provides event hooks similar to Windsurf's Cascade Hooks,
allowing custom actions before/after agent operations.

Features:
- Pre/post hooks for read, write, command, prompt operations
- JSON configuration (.praison/hooks.json)
- Script execution with timeout
- Exit code handling
- Lazy loading for performance

Configuration (.praison/hooks.json):
    {
        "hooks": {
            "pre_write_code": "./scripts/lint.sh",
            "post_write_code": "./scripts/format.sh",
            "pre_run_command": "./scripts/validate.sh",
            "post_user_prompt": "./scripts/log.sh"
        },
        "timeout": 30,
        "enabled": true
    }

Hook Events:
- pre_read_code: Before reading a file
- post_read_code: After reading a file
- pre_write_code: Before writing to a file
- post_write_code: After writing to a file
- pre_run_command: Before running a terminal command
- post_run_command: After running a terminal command
- pre_user_prompt: Before processing user prompt
- post_user_prompt: After processing user prompt
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Literal
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Hook event types
HookEvent = Literal[
    "pre_read_code",
    "post_read_code",
    "pre_write_code",
    "post_write_code",
    "pre_run_command",
    "post_run_command",
    "pre_user_prompt",
    "post_user_prompt",
    "pre_mcp_tool_use",
    "post_mcp_tool_use"
]


@dataclass
class HookResult:
    """Result of a hook execution."""
    success: bool
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    blocked: bool = False  # If True, the operation should be blocked
    modified_input: Optional[str] = None  # Modified input if applicable


@dataclass
class HookConfig:
    """Configuration for a single hook."""
    event: HookEvent
    command: str
    timeout: int = 30
    enabled: bool = True
    block_on_failure: bool = False
    pass_input: bool = True


class HooksManager:
    """
    Manages hook discovery, loading, and execution.
    
    Hooks are configured in .praison/hooks.json and can execute
    scripts before/after agent operations.
    
    Example:
        ```python
        hooks = HooksManager(workspace_path="/path/to/project")
        
        # Execute pre-write hook
        result = hooks.execute(
            "pre_write_code",
            context={"file_path": "main.py", "content": "..."}
        )
        
        if result.blocked:
            print("Write blocked by hook")
        ```
    """
    
    CONFIG_FILE = ".praison/hooks.json"
    
    def __init__(
        self,
        workspace_path: Optional[str] = None,
        verbose: int = 0
    ):
        """
        Initialize HooksManager.
        
        Args:
            workspace_path: Path to workspace/project root
            verbose: Verbosity level
        """
        self.workspace_path = Path(workspace_path) if workspace_path else Path.cwd()
        self.verbose = verbose
        
        self._hooks: Dict[HookEvent, List[HookConfig]] = {}
        self._global_timeout = 30
        self._enabled = True
        self._loaded = False
        
        # Python callable hooks (for programmatic use)
        self._callable_hooks: Dict[HookEvent, List[Callable]] = {}
    
    def _log(self, msg: str, level: int = logging.INFO):
        """Log message if verbose."""
        if self.verbose >= 1:
            logger.log(level, msg)
    
    def _ensure_loaded(self):
        """Lazy load hooks on first access."""
        if not self._loaded:
            self._load_config()
            self._loaded = True
    
    def _load_config(self):
        """Load hooks configuration from file."""
        config_path = self.workspace_path / self.CONFIG_FILE.replace("/", os.sep)
        
        if not config_path.exists():
            return
        
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            
            self._enabled = config.get("enabled", True)
            self._global_timeout = config.get("timeout", 30)
            
            hooks_config = config.get("hooks", {})
            
            for event, command in hooks_config.items():
                if event not in self._hooks:
                    self._hooks[event] = []
                
                if isinstance(command, str):
                    # Simple command string
                    self._hooks[event].append(HookConfig(
                        event=event,
                        command=command,
                        timeout=self._global_timeout
                    ))
                elif isinstance(command, dict):
                    # Detailed config
                    self._hooks[event].append(HookConfig(
                        event=event,
                        command=command.get("command", ""),
                        timeout=command.get("timeout", self._global_timeout),
                        enabled=command.get("enabled", True),
                        block_on_failure=command.get("block_on_failure", False),
                        pass_input=command.get("pass_input", True)
                    ))
                elif isinstance(command, list):
                    # Multiple commands for same event
                    for cmd in command:
                        if isinstance(cmd, str):
                            self._hooks[event].append(HookConfig(
                                event=event,
                                command=cmd,
                                timeout=self._global_timeout
                            ))
            
            self._log(f"Loaded {sum(len(h) for h in self._hooks.values())} hooks")
            
        except Exception as e:
            self._log(f"Error loading hooks config: {e}", logging.WARNING)
    
    def reload(self):
        """Reload hooks configuration."""
        self._hooks = {}
        self._loaded = False
        self._ensure_loaded()
    
    def register(
        self,
        event: HookEvent,
        handler: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]
    ):
        """
        Register a Python callable as a hook.
        
        Args:
            event: Hook event type
            handler: Callable that receives context dict and optionally returns modified context
        """
        if event not in self._callable_hooks:
            self._callable_hooks[event] = []
        self._callable_hooks[event].append(handler)
    
    def unregister(self, event: HookEvent, handler: Callable):
        """Unregister a callable hook."""
        if event in self._callable_hooks:
            self._callable_hooks[event] = [
                h for h in self._callable_hooks[event] if h != handler
            ]
    
    def execute(
        self,
        event: HookEvent,
        context: Optional[Dict[str, Any]] = None
    ) -> HookResult:
        """
        Execute hooks for an event.
        
        Args:
            event: Hook event type
            context: Context data to pass to hooks
            
        Returns:
            HookResult with execution status
        """
        self._ensure_loaded()
        
        if not self._enabled:
            return HookResult(success=True)
        
        context = context or {}
        combined_result = HookResult(success=True)
        
        # Execute callable hooks first
        if event in self._callable_hooks:
            for handler in self._callable_hooks[event]:
                try:
                    result = handler(context)
                    if isinstance(result, dict):
                        context.update(result)
                except Exception as e:
                    self._log(f"Callable hook error for {event}: {e}", logging.WARNING)
                    combined_result.success = False
        
        # Execute script hooks
        if event in self._hooks:
            for hook in self._hooks[event]:
                if not hook.enabled:
                    continue
                
                result = self._execute_script(hook, context)
                
                if not result.success:
                    combined_result.success = False
                    combined_result.stderr += result.stderr
                    
                    if hook.block_on_failure:
                        combined_result.blocked = True
                        break
                
                combined_result.stdout += result.stdout
                
                if result.modified_input:
                    combined_result.modified_input = result.modified_input
        
        return combined_result
    
    def _execute_script(
        self,
        hook: HookConfig,
        context: Dict[str, Any]
    ) -> HookResult:
        """Execute a script hook."""
        try:
            # Prepare environment
            env = os.environ.copy()
            
            # Pass context as environment variables
            if hook.pass_input:
                for key, value in context.items():
                    if isinstance(value, (str, int, float, bool)):
                        env[f"PRAISON_HOOK_{key.upper()}"] = str(value)
                
                # Also pass as JSON
                env["PRAISON_HOOK_CONTEXT"] = json.dumps(context)
            
            # Resolve command path
            command = hook.command
            if not os.path.isabs(command) and not command.startswith("./"):
                command = str(self.workspace_path / command)
            
            # Execute
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace_path),
                env=env,
                capture_output=True,
                text=True,
                timeout=hook.timeout
            )
            
            success = result.returncode == 0
            
            # Check for special exit codes
            blocked = result.returncode == 1 and hook.block_on_failure
            
            # Check stdout for modified input
            modified_input = None
            if result.stdout.startswith("MODIFIED:"):
                modified_input = result.stdout[9:].strip()
            
            self._log(f"Hook {hook.event} executed: exit={result.returncode}")
            
            return HookResult(
                success=success,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                blocked=blocked,
                modified_input=modified_input
            )
            
        except subprocess.TimeoutExpired:
            self._log(f"Hook {hook.event} timed out after {hook.timeout}s", logging.WARNING)
            return HookResult(
                success=False,
                exit_code=-1,
                stderr=f"Timeout after {hook.timeout}s"
            )
        except Exception as e:
            self._log(f"Hook {hook.event} error: {e}", logging.WARNING)
            return HookResult(
                success=False,
                exit_code=-1,
                stderr=str(e)
            )
    
    def has_hooks(self, event: HookEvent) -> bool:
        """Check if any hooks are registered for an event."""
        self._ensure_loaded()
        return (
            event in self._hooks and len(self._hooks[event]) > 0 or
            event in self._callable_hooks and len(self._callable_hooks[event]) > 0
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get hooks statistics."""
        self._ensure_loaded()
        
        script_hooks = sum(len(h) for h in self._hooks.values())
        callable_hooks = sum(len(h) for h in self._callable_hooks.values())
        
        return {
            "enabled": self._enabled,
            "script_hooks": script_hooks,
            "callable_hooks": callable_hooks,
            "total_hooks": script_hooks + callable_hooks,
            "events": list(set(list(self._hooks.keys()) + list(self._callable_hooks.keys())))
        }
    
    def create_config(
        self,
        hooks: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        enabled: bool = True
    ):
        """
        Create a hooks configuration file.
        
        Args:
            hooks: Dict mapping event names to commands
            timeout: Global timeout in seconds
            enabled: Whether hooks are enabled
        """
        config_dir = self.workspace_path / ".praison"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        config = {
            "enabled": enabled,
            "timeout": timeout,
            "hooks": hooks or {}
        }
        
        config_path = config_dir / "hooks.json"
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        
        self._log(f"Created hooks config at {config_path}")
        self.reload()


def create_hooks_manager(
    workspace_path: Optional[str] = None,
    **kwargs
) -> HooksManager:
    """
    Create a HooksManager instance.
    
    Args:
        workspace_path: Path to workspace
        **kwargs: Additional configuration
        
    Returns:
        HooksManager instance
    """
    return HooksManager(workspace_path=workspace_path, **kwargs)
