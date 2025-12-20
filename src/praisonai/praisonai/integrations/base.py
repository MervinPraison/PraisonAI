"""
Base class for external CLI tool integrations.

Provides a consistent interface for integrating with AI coding CLI tools
like Claude Code, Gemini CLI, Codex CLI, and Cursor CLI.

Features:
- Lazy availability checking with caching
- Async subprocess execution
- Tool wrapper for agent integration
- Timeout handling
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Dict, Any, Tuple, List
import asyncio
import shutil
import os


class BaseCLIIntegration(ABC):
    """
    Abstract base class for external CLI tool integrations.
    
    Provides:
    - Lazy availability checking with class-level caching
    - Async subprocess execution with timeout handling
    - Tool wrapper for PraisonAI agent integration
    
    Subclasses must implement:
    - cli_command property: The CLI command name
    - execute method: Execute the CLI and return result
    - stream method: Stream output from the CLI
    
    Example:
        class MyIntegration(BaseCLIIntegration):
            @property
            def cli_command(self) -> str:
                return "my-cli"
            
            async def execute(self, prompt: str, **options) -> str:
                return await self.execute_async(["my-cli", "-p", prompt])
            
            async def stream(self, prompt: str, **options):
                async for line in self.stream_async(["my-cli", "-p", prompt]):
                    yield line
    """
    
    # Class-level cache for availability checks (shared across instances)
    _availability_cache: Dict[str, bool] = {}
    
    def __init__(self, workspace: str = ".", timeout: int = 300):
        """
        Initialize the CLI integration.
        
        Args:
            workspace: Working directory for CLI execution (default: current dir)
            timeout: Default timeout in seconds for CLI execution (default: 300)
        """
        self.workspace = workspace
        self.timeout = timeout
    
    @property
    @abstractmethod
    def cli_command(self) -> str:
        """
        Return the CLI command name.
        
        This is used for availability checking and tool naming.
        
        Returns:
            str: The CLI command (e.g., "claude", "gemini", "codex", "cursor-agent")
        """
        pass
    
    @property
    def is_available(self) -> bool:
        """
        Check if the CLI tool is installed and available.
        
        Uses class-level caching to avoid repeated filesystem checks.
        
        Returns:
            bool: True if the CLI is available, False otherwise
        """
        if self.cli_command not in self._availability_cache:
            self._availability_cache[self.cli_command] = shutil.which(self.cli_command) is not None
        return self._availability_cache[self.cli_command]
    
    @abstractmethod
    async def execute(self, prompt: str, **options) -> str:
        """
        Execute the CLI tool and return the result.
        
        Args:
            prompt: The prompt/query to send to the CLI
            **options: Additional options for the CLI
            
        Returns:
            str: The CLI output
        """
        pass
    
    @abstractmethod
    async def stream(self, prompt: str, **options) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream output from the CLI tool.
        
        Args:
            prompt: The prompt/query to send to the CLI
            **options: Additional options for the CLI
            
        Yields:
            dict: Parsed output events from the CLI
        """
        pass
    
    async def execute_async(self, cmd: List[str], timeout: Optional[int] = None) -> str:
        """
        Execute a command asynchronously and return stdout.
        
        Args:
            cmd: Command and arguments as a list
            timeout: Timeout in seconds (uses self.timeout if not specified)
            
        Returns:
            str: The command's stdout
            
        Raises:
            TimeoutError: If the command times out
        """
        timeout = timeout or self.timeout
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.workspace,
            env=self.get_env()
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            return stdout.decode()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"Command timed out after {timeout}s: {' '.join(cmd)}")
    
    async def execute_async_with_stderr(
        self, 
        cmd: List[str], 
        timeout: Optional[int] = None
    ) -> Tuple[str, str]:
        """
        Execute a command asynchronously and return both stdout and stderr.
        
        Args:
            cmd: Command and arguments as a list
            timeout: Timeout in seconds (uses self.timeout if not specified)
            
        Returns:
            Tuple[str, str]: (stdout, stderr)
            
        Raises:
            TimeoutError: If the command times out
        """
        timeout = timeout or self.timeout
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.workspace,
            env=self.get_env()
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            return stdout.decode(), stderr.decode()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"Command timed out after {timeout}s: {' '.join(cmd)}")
    
    async def stream_async(
        self, 
        cmd: List[str], 
        timeout: Optional[int] = None
    ) -> AsyncIterator[str]:
        """
        Stream stdout lines from a command asynchronously.
        
        Args:
            cmd: Command and arguments as a list
            timeout: Timeout in seconds for the entire operation
            
        Yields:
            str: Each line of output
        """
        timeout = timeout or self.timeout
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.workspace,
            env=self.get_env()
        )
        
        try:
            async def read_lines():
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    yield line.decode().rstrip('\n')
            
            async for line in read_lines():
                yield line
                
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"Stream timed out after {timeout}s")
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
    
    def as_tool(self) -> callable:
        """
        Return a callable suitable for use as a PraisonAI agent tool.
        
        The returned function is synchronous and wraps the async execute method.
        Uses asyncio.run() for proper event loop handling (Python 3.7+).
        
        Returns:
            callable: A function that can be used as an agent tool
        """
        # Capture self for closure
        integration = self
        
        def tool_func(query: str) -> str:
            """Execute the CLI tool with the given query."""
            # Use asyncio.run() for clean event loop management
            # This creates a new event loop, runs the coroutine, and closes it
            try:
                # Check if we're already in an async context
                asyncio.get_running_loop()
                # If we're in an async context, use ThreadPoolExecutor to avoid nested loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, integration.execute(query))
                    return future.result()
            except RuntimeError:
                # No running loop, safe to use asyncio.run()
                return asyncio.run(integration.execute(query))
        
        # Set function metadata for agent tool registration
        tool_func.__name__ = f"{self.cli_command}_tool"
        tool_func.__doc__ = f"Execute {self.cli_command} for coding tasks."
        
        return tool_func
    
    def get_env(self) -> Dict[str, str]:
        """
        Get environment variables for CLI execution.
        
        Subclasses can override this to add tool-specific environment variables.
        
        Returns:
            dict: Environment variables to pass to the CLI
        """
        return dict(os.environ)


def get_available_integrations() -> Dict[str, bool]:
    """
    Get a dictionary of all integrations and their availability status.
    
    Returns:
        dict: Mapping of integration name to availability (True/False)
    """
    from .claude_code import ClaudeCodeIntegration
    from .gemini_cli import GeminiCLIIntegration
    from .codex_cli import CodexCLIIntegration
    from .cursor_cli import CursorCLIIntegration
    
    integrations = {
        'claude': ClaudeCodeIntegration(),
        'gemini': GeminiCLIIntegration(),
        'codex': CodexCLIIntegration(),
        'cursor': CursorCLIIntegration(),
    }
    
    return {name: integration.is_available for name, integration in integrations.items()}
