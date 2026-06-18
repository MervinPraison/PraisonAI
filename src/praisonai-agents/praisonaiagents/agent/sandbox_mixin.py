"""
Sandbox execution mixin for Agent.

Provides safe code execution capabilities to agents via the sandbox framework.
"""

import logging
from typing import Optional, Dict, Any, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ..sandbox import SandboxConfig, SandboxManager, SandboxResult

logger = logging.getLogger(__name__)


class SandboxMixin:
    """Mixin that adds sandbox execution capabilities to Agent.
    
    Provides safe code execution in isolated environments with security pre-checks.
    """
    
    def __init__(self, *args, **kwargs):
        # Extract sandbox config from kwargs
        sandbox = kwargs.pop('sandbox', None)
        
        # Convert boolean True to default config
        if sandbox is True:
            from ..sandbox import SandboxConfig
            sandbox = SandboxConfig.subprocess()
        elif sandbox is False:
            sandbox = None
        
        self.sandbox_config: Optional['SandboxConfig'] = sandbox
        
        super().__init__(*args, **kwargs)
        
        self._sandbox_manager: Optional['SandboxManager'] = None
    
    @property
    def has_sandbox(self) -> bool:
        """Check if sandbox is configured for this agent."""
        return self.sandbox_config is not None
    
    def get_sandbox_manager(self) -> Optional['SandboxManager']:
        """Get or create sandbox manager."""
        if not self.has_sandbox:
            return None
        
        if self._sandbox_manager is None:
            from ..sandbox import SandboxManager
            self._sandbox_manager = SandboxManager(self.sandbox_config)
        
        return self._sandbox_manager
    
    async def execute_code(
        self,
        code: str,
        language: str = "python",
        check_security: bool = True,
        **kwargs
    ) -> 'SandboxResult':
        """Execute code safely in configured sandbox.
        
        Args:
            code: Code to execute
            language: Programming language (python, bash, etc.)
            check_security: Whether to run security pre-checks
            **kwargs: Additional arguments passed to sandbox.execute()
            
        Returns:
            SandboxResult with execution details
            
        Raises:
            RuntimeError: If no sandbox is configured
        """
        if not self.has_sandbox:
            raise RuntimeError(
                "No sandbox configured. Set sandbox=True or provide SandboxConfig to Agent()"
            )
        
        # Security pre-check if enabled
        if check_security:
            from ..sandbox import check_code_safety, format_warnings
            warnings = check_code_safety(code, language)
            if warnings:
                warning_text = format_warnings(warnings)
                if self.verbose:
                    logger.warning(f"Security warnings for code execution:\n{warning_text}")
                
                # Store warnings in result metadata
                kwargs.setdefault('metadata', {})['security_warnings'] = warnings
        
        manager = self.get_sandbox_manager()
        return await manager.run_code(code, language=language, **kwargs)
    
    def execute_code_sync(
        self,
        code: str,
        language: str = "python", 
        check_security: bool = True,
        **kwargs
    ) -> 'SandboxResult':
        """Synchronous wrapper for execute_code.
        
        Args:
            code: Code to execute
            language: Programming language
            check_security: Whether to run security pre-checks
            **kwargs: Additional arguments
            
        Returns:
            SandboxResult with execution details
        """
        from ..approval.utils import run_coroutine_safely
        return run_coroutine_safely(self.execute_code(code, language, check_security, **kwargs))
    
    async def run_shell_command(
        self,
        command: Union[str, list],
        check_security: bool = True,
        **kwargs
    ) -> 'SandboxResult':
        """Run a shell command in the sandbox.
        
        Args:
            command: Shell command to run
            check_security: Whether to run security pre-checks
            **kwargs: Additional arguments
            
        Returns:
            SandboxResult with execution details
        """
        if not self.has_sandbox:
            raise RuntimeError("No sandbox configured")
        
        # Convert command to string for security checking
        if isinstance(command, list):
            command_str = " ".join(command)
        else:
            command_str = command
        
        # Security pre-check
        if check_security:
            from ..sandbox import check_code_safety, format_warnings
            warnings = check_code_safety(command_str, "bash")
            if warnings:
                warning_text = format_warnings(warnings)
                if self.verbose:
                    logger.warning(f"Security warnings for command:\n{warning_text}")
        
        async with self.get_sandbox_manager() as sandbox:
            return await sandbox.run_command(command, **kwargs)
    
    def get_sandbox_status(self) -> Dict[str, Any]:
        """Get sandbox status information.
        
        Returns:
            Dictionary with sandbox status details
        """
        if not self.has_sandbox:
            return {"configured": False}
        
        status = {
            "configured": True,
            "config": self.sandbox_config.to_dict() if self.sandbox_config else None,
        }
        
        manager = self.get_sandbox_manager()
        if manager:
            # Get available sandbox types
            available_types = manager.get_available_types()
            status["available_types"] = available_types
            status["current_type"] = self.sandbox_config.sandbox_type
        
        return status
    
    async def sandbox_cleanup(self):
        """Clean up sandbox resources."""
        if self._sandbox_manager:
            # The context manager handles cleanup, but we can force it here
            try:
                await self._sandbox_manager.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error during sandbox cleanup: {e}")
            finally:
                self._sandbox_manager = None
    
    def _get_code_execution_tools(self):
        """Get sandbox-based code execution tools for this agent.
        
        Returns tools that use the configured sandbox for safe execution.
        
        Returns:
            List of tool functions
        """
        if not self.has_sandbox:
            return []
        
        from ..tools import tool
        
        @tool
        def execute_python_code(code: str) -> str:
            """Execute Python code safely in sandbox.
            
            Args:
                code: Python code to execute
                
            Returns:
                Execution output
            """
            result = self.execute_code_sync(code, language="python")
            if result.success:
                return result.stdout or result.output
            else:
                return f"Error: {result.error or result.stderr}"
        
        @tool  
        def execute_shell_command(command: str) -> str:
            """Execute shell command safely in sandbox.
            
            Args:
                command: Shell command to execute
                
            Returns:
                Command output
            """
            from ..approval.utils import run_coroutine_safely
            result = run_coroutine_safely(self.run_shell_command(command))
            if result.success:
                return result.stdout or result.output
            else:
                return f"Error: {result.error or result.stderr}"
        
        return [execute_python_code, execute_shell_command]