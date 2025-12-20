"""
Cursor CLI Integration.

Provides integration with Cursor's CLI (cursor-agent) for AI-powered coding tasks.

Features:
- Headless mode execution with JSON output
- Force mode for file modifications
- Model selection
- Session resume support
- Streaming output with partial deltas

Usage:
    from praisonai.integrations import CursorCLIIntegration
    
    # Create integration
    cursor = CursorCLIIntegration(workspace="/path/to/project")
    
    # Execute a coding task
    result = await cursor.execute("Fix the authentication bug")
    
    # Execute with force mode (allows file modifications)
    cursor_force = CursorCLIIntegration(force=True)
    result = await cursor_force.execute("Refactor the module")
    
    # Use as agent tool
    tool = cursor.as_tool()
"""

import json
import os
from typing import AsyncIterator, Dict, Any, Optional, List

from .base import BaseCLIIntegration


class CursorCLIIntegration(BaseCLIIntegration):
    """
    Integration with Cursor CLI (cursor-agent).
    
    Attributes:
        output_format: Output format ("json", "text", "stream-json")
        force: Whether to allow file modifications
        model: Model to use (e.g., "gpt-5")
        stream_partial: Whether to stream partial output
        resume_session: Session ID to resume
    """
    
    def __init__(
        self,
        workspace: str = ".",
        timeout: int = 300,
        output_format: str = "json",
        force: bool = False,
        model: Optional[str] = None,
        stream_partial: bool = False,
        resume_session: Optional[str] = None,
    ):
        """
        Initialize Cursor CLI integration.
        
        Args:
            workspace: Working directory for CLI execution
            timeout: Timeout in seconds for CLI execution
            output_format: Output format ("json", "text", "stream-json")
            force: Whether to allow file modifications (--force)
            model: Model to use (e.g., "gpt-5")
            stream_partial: Whether to stream partial output (--stream-partial-output)
            resume_session: Session ID to resume (--resume)
        """
        super().__init__(workspace=workspace, timeout=timeout)
        
        self.output_format = output_format
        self.force = force
        self.model = model
        self.stream_partial = stream_partial
        self.resume_session = resume_session
    
    @property
    def cli_command(self) -> str:
        """Return the CLI command name."""
        return "cursor-agent"
    
    def _build_command(self, prompt: str, **options) -> List[str]:
        """
        Build the Cursor CLI command.
        
        Args:
            prompt: The prompt to send
            **options: Additional options
            
        Returns:
            List of command arguments
        """
        cmd = ["cursor-agent"]
        
        # Add print mode flag
        cmd.append("-p")
        
        # Add workspace
        cmd.extend(["--workspace", self.workspace])
        
        # Add force flag if enabled
        if self.force:
            cmd.append("--force")
        
        # Add model if specified
        if self.model:
            cmd.extend(["-m", self.model])
        
        # Add output format
        cmd.extend(["--output-format", self.output_format])
        
        # Add stream partial flag if enabled
        if self.stream_partial:
            cmd.append("--stream-partial-output")
        
        # Add resume session if specified
        if self.resume_session:
            cmd.extend(["--resume", self.resume_session])
        
        # Add prompt (must be last)
        cmd.append(prompt)
        
        return cmd
    
    async def execute(self, prompt: str, **options) -> str:
        """
        Execute Cursor CLI and return the result.
        
        Args:
            prompt: The prompt/query to send
            **options: Additional options
            
        Returns:
            str: The CLI output (parsed from JSON if output_format is "json")
        """
        cmd = self._build_command(prompt, **options)
        
        output = await self.execute_async(cmd)
        
        # Parse JSON output if applicable
        if self.output_format == "json":
            try:
                data = json.loads(output)
                # Extract the main result
                if isinstance(data, dict):
                    return data.get("result", data.get("content", str(data)))
                return str(data)
            except json.JSONDecodeError:
                return output
        
        return output
    
    async def stream(self, prompt: str, **options) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream output from Cursor CLI.
        
        Args:
            prompt: The prompt/query to send
            **options: Additional options
            
        Yields:
            dict: Parsed JSON events from the CLI
        """
        # Use stream-json format for streaming
        original_format = self.output_format
        original_partial = self.stream_partial
        
        self.output_format = "stream-json"
        self.stream_partial = True
        
        try:
            cmd = self._build_command(prompt, **options)
            
            async for line in self.stream_async(cmd):
                if line.strip():
                    try:
                        event = json.loads(line)
                        yield event
                    except json.JSONDecodeError:
                        yield {"type": "text", "content": line}
        finally:
            self.output_format = original_format
            self.stream_partial = original_partial
    
    def get_env(self) -> Dict[str, str]:
        """Get environment variables for CLI execution."""
        env = super().get_env()
        
        # Add Cursor API key if available
        if "CURSOR_API_KEY" in os.environ:
            env["CURSOR_API_KEY"] = os.environ["CURSOR_API_KEY"]
        
        return env
