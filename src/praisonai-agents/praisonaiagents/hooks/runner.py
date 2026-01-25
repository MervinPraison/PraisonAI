"""
Hook Runner for PraisonAI Agents.

Executes hooks registered in the registry, supporting both
Python functions and shell commands.
"""

import os
import json
import time
import asyncio
import logging
import subprocess
from typing import List, Optional, Dict, Any

from .types import (
    HookEvent, HookDefinition, CommandHook, FunctionHook,
    HookInput, HookResult, HookExecutionResult
)
from .registry import HookRegistry

logger = logging.getLogger(__name__)

# Exit codes for command hooks
EXIT_CODE_SUCCESS = 0
EXIT_CODE_BLOCKING_ERROR = 2
EXIT_CODE_NON_BLOCKING_ERROR = 1


class HookRunner:
    """
    Executes hooks from a registry.
    
    Supports:
    - Python function hooks (sync and async)
    - Shell command hooks
    - Sequential and parallel execution
    - Timeout handling
    - Result aggregation
    
    Example:
        registry = HookRegistry()
        runner = HookRunner(registry)
        
        # Execute hooks for an event
        results = await runner.execute(
            event=HookEvent.BEFORE_TOOL,
            input_data=BeforeToolInput(
                tool_name="write_file",
                tool_input={"path": "/tmp/test.txt"}
            )
        )
        
        # Check if any hook blocked
        if runner.is_blocked(results):
            print("Tool execution blocked by hook")
    """
    
    def __init__(
        self,
        registry: Optional[HookRegistry] = None,
        default_timeout: float = 60.0,
        cwd: Optional[str] = None
    ):
        """
        Initialize the hook runner.
        
        Args:
            registry: Hook registry to use
            default_timeout: Default timeout for hooks
            cwd: Working directory for command hooks
        """
        self._registry = registry or HookRegistry()
        self._default_timeout = default_timeout
        self._cwd = cwd or os.getcwd()
    
    @property
    def registry(self) -> HookRegistry:
        """Get the hook registry."""
        return self._registry
    
    async def execute(
        self,
        event: HookEvent,
        input_data: HookInput,
        target: Optional[str] = None
    ) -> List[HookExecutionResult]:
        """
        Execute all hooks for an event.
        
        Args:
            event: The event to execute hooks for
            input_data: Input data for the hooks
            target: Optional target to filter hooks (e.g., tool name)
            
        Returns:
            List of execution results
        """
        hooks = self._registry.get_hooks(event, target)
        
        if not hooks:
            return []
        
        # Separate sequential and parallel hooks
        sequential_hooks = [h for h in hooks if h.sequential]
        parallel_hooks = [h for h in hooks if not h.sequential]
        
        results = []
        
        # Execute parallel hooks first
        if parallel_hooks:
            parallel_results = await self._execute_parallel(
                parallel_hooks, event, input_data
            )
            results.extend(parallel_results)
        
        # Execute sequential hooks
        if sequential_hooks:
            sequential_results = await self._execute_sequential(
                sequential_hooks, event, input_data
            )
            results.extend(sequential_results)
        
        return results
    
    def execute_sync(
        self,
        event: HookEvent,
        input_data: HookInput,
        target: Optional[str] = None
    ) -> List[HookExecutionResult]:
        """
        Synchronous version of execute.
        
        Args:
            event: The event to execute hooks for
            input_data: Input data for the hooks
            target: Optional target to filter hooks
            
        Returns:
            List of execution results
        """
        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, create a task
            future = asyncio.ensure_future(self.execute(event, input_data, target))
            return loop.run_until_complete(future)
        except RuntimeError:
            # No event loop running, create one
            return asyncio.run(self.execute(event, input_data, target))
    
    async def _execute_parallel(
        self,
        hooks: List[HookDefinition],
        event: HookEvent,
        input_data: HookInput
    ) -> List[HookExecutionResult]:
        """Execute hooks in parallel."""
        tasks = [
            self._execute_single(hook, event, input_data)
            for hook in hooks
        ]
        return await asyncio.gather(*tasks)
    
    async def _execute_sequential(
        self,
        hooks: List[HookDefinition],
        event: HookEvent,
        input_data: HookInput
    ) -> List[HookExecutionResult]:
        """Execute hooks sequentially, passing modified input to next hook."""
        results = []
        current_input = input_data
        
        for hook in hooks:
            result = await self._execute_single(hook, event, current_input)
            results.append(result)
            
            # If hook modified the input, use it for next hook
            if result.success and result.output and result.output.modified_input:
                # Update input with modifications
                for key, value in result.output.modified_input.items():
                    if hasattr(current_input, key):
                        setattr(current_input, key, value)
            
            # Stop if hook blocked
            if result.output and result.output.is_denied():
                break
        
        return results
    
    async def _execute_single(
        self,
        hook: HookDefinition,
        event: HookEvent,
        input_data: HookInput
    ) -> HookExecutionResult:
        """Execute a single hook."""
        start_time = time.time()
        
        try:
            if isinstance(hook, CommandHook):
                return await self._execute_command_hook(hook, event, input_data, start_time)
            elif isinstance(hook, FunctionHook):
                return await self._execute_function_hook(hook, event, input_data, start_time)
            else:
                raise ValueError(f"Unknown hook type: {type(hook)}")
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.warning(f"Hook '{hook.name}' failed: {e}")
            return HookExecutionResult(
                hook_id=hook.id,
                hook_name=hook.name or "unknown",
                event=event,
                success=False,
                error=str(e),
                duration_ms=duration
            )
    
    async def _execute_command_hook(
        self,
        hook: CommandHook,
        event: HookEvent,
        input_data: HookInput,
        start_time: float
    ) -> HookExecutionResult:
        """Execute a command hook."""
        timeout = hook.timeout or self._default_timeout
        
        # Prepare environment
        env = os.environ.copy()
        env.update(hook.env)
        env["PRAISON_PROJECT_DIR"] = self._cwd
        env["PRAISON_EVENT"] = event.value
        
        # Expand command variables
        command = self._expand_command(hook.command, input_data)
        
        try:
            # Create subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self._cwd
            )
            
            # Send input as JSON
            input_json = json.dumps(input_data.to_dict()).encode()
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input=input_json),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                duration = (time.time() - start_time) * 1000
                return HookExecutionResult(
                    hook_id=hook.id,
                    hook_name=hook.name or "unknown",
                    event=event,
                    success=False,
                    error=f"Hook timed out after {timeout}s",
                    duration_ms=duration
                )
            
            duration = (time.time() - start_time) * 1000
            exit_code = process.returncode
            stdout_str = stdout.decode() if stdout else ""
            stderr_str = stderr.decode() if stderr else ""
            
            # Parse output
            output = self._parse_command_output(stdout_str, stderr_str, exit_code)
            
            return HookExecutionResult(
                hook_id=hook.id,
                hook_name=hook.name or "unknown",
                event=event,
                success=exit_code == EXIT_CODE_SUCCESS,
                output=output,
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=exit_code,
                duration_ms=duration
            )
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return HookExecutionResult(
                hook_id=hook.id,
                hook_name=hook.name or "unknown",
                event=event,
                success=False,
                error=str(e),
                duration_ms=duration
            )
    
    async def _execute_function_hook(
        self,
        hook: FunctionHook,
        event: HookEvent,
        input_data: HookInput,
        start_time: float
    ) -> HookExecutionResult:
        """Execute a function hook."""
        if hook.func is None:
            duration = (time.time() - start_time) * 1000
            return HookExecutionResult(
                hook_id=hook.id,
                hook_name=hook.name or "unknown",
                event=event,
                success=False,
                error="Hook function is None",
                duration_ms=duration
            )
        
        timeout = hook.timeout or self._default_timeout
        
        try:
            if hook.is_async:
                # Execute async function with timeout
                result = await asyncio.wait_for(
                    hook.func(input_data),
                    timeout=timeout
                )
            else:
                # Execute sync function in thread pool with timeout
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, hook.func, input_data),
                    timeout=timeout
                )
            
            duration = (time.time() - start_time) * 1000
            
            # Normalize result - allow simple return values for easier hooks
            # None, True, missing return → allow
            # False → deny  
            # str → deny with that reason
            # dict with 'decision' → convert to HookResult
            if result is None or result is True:
                result = HookResult.allow()
            elif result is False:
                result = HookResult.deny("Denied by hook")
            elif isinstance(result, str):
                result = HookResult.deny(result)
            elif isinstance(result, dict) and 'decision' in result:
                result = HookResult(**result)
            elif not isinstance(result, HookResult):
                # Unknown type, treat as allow
                result = HookResult.allow()
            
            return HookExecutionResult(
                hook_id=hook.id,
                hook_name=hook.name or "unknown",
                event=event,
                success=True,
                output=result,
                duration_ms=duration
            )
            
        except asyncio.TimeoutError:
            duration = (time.time() - start_time) * 1000
            return HookExecutionResult(
                hook_id=hook.id,
                hook_name=hook.name or "unknown",
                event=event,
                success=False,
                error=f"Hook timed out after {timeout}s",
                duration_ms=duration
            )
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return HookExecutionResult(
                hook_id=hook.id,
                hook_name=hook.name or "unknown",
                event=event,
                success=False,
                error=str(e),
                duration_ms=duration
            )
    
    def _expand_command(self, command: str, input_data: HookInput) -> str:
        """Expand variables in command string."""
        return command.replace(
            "$PRAISON_PROJECT_DIR", self._cwd
        ).replace(
            "$PRAISON_CWD", input_data.cwd
        )
    
    def _parse_command_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int
    ) -> HookResult:
        """Parse command output into HookResult."""
        # Try to parse JSON from stdout
        if stdout.strip():
            try:
                data = json.loads(stdout.strip())
                
                # Handle double-encoded JSON
                if isinstance(data, str):
                    data = json.loads(data)
                
                return HookResult(
                    decision=data.get("decision", "allow"),
                    reason=data.get("reason"),
                    modified_input=data.get("modified_input"),
                    additional_context=data.get("additional_context"),
                    suppress_output=data.get("suppress_output", False)
                )
            except json.JSONDecodeError:
                pass
        
        # Convert exit code to decision
        if exit_code == EXIT_CODE_SUCCESS:
            return HookResult(
                decision="allow",
                additional_context=stdout.strip() if stdout.strip() else None
            )
        elif exit_code == EXIT_CODE_BLOCKING_ERROR:
            return HookResult(
                decision="deny",
                reason=stderr.strip() or stdout.strip() or "Blocked by hook"
            )
        else:
            return HookResult(
                decision="allow",
                additional_context=f"Warning: {stderr.strip() or stdout.strip()}"
            )
    
    @staticmethod
    def is_blocked(results: List[HookExecutionResult]) -> bool:
        """Check if any hook blocked execution."""
        for result in results:
            if result.output and result.output.is_denied():
                return True
        return False
    
    @staticmethod
    def get_blocking_reason(results: List[HookExecutionResult]) -> Optional[str]:
        """Get the reason for blocking from results."""
        for result in results:
            if result.output and result.output.is_denied():
                return result.output.reason
        return None
    
    @staticmethod
    def aggregate_context(results: List[HookExecutionResult]) -> Optional[str]:
        """Aggregate additional context from all results."""
        contexts = []
        for result in results:
            if result.output and result.output.additional_context:
                contexts.append(result.output.additional_context)
        return "\n".join(contexts) if contexts else None
