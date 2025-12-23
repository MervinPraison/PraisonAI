"""
Gemini CLI Integration.

Provides integration with Google's Gemini CLI for AI-powered coding tasks.

Features:
- Headless mode execution with JSON output
- Model selection (gemini-2.5-pro, gemini-2.5-flash, etc.)
- Multi-directory context support
- Google Search grounding
- Usage statistics

Usage:
    from praisonai.integrations import GeminiCLIIntegration
    
    # Create integration
    gemini = GeminiCLIIntegration(workspace="/path/to/project")
    
    # Execute a coding task
    result = await gemini.execute("Analyze this codebase")
    
    # Get result with stats
    result, stats = await gemini.execute_with_stats("Explain the architecture")
    
    # Use as agent tool
    tool = gemini.as_tool()
"""

import json
import os
from typing import AsyncIterator, Dict, Any, Optional, List, Tuple

from .base import BaseCLIIntegration


class GeminiCLIIntegration(BaseCLIIntegration):
    """
    Integration with Google's Gemini CLI.
    
    Attributes:
        output_format: Output format ("json", "text", "stream-json")
        model: Gemini model to use
        include_directories: Additional directories to include in context
        sandbox: Whether to run in sandbox mode
    """
    
    def __init__(
        self,
        workspace: str = ".",
        timeout: int = 300,
        output_format: str = "json",
        model: str = "gemini-2.5-pro",
        include_directories: Optional[List[str]] = None,
        sandbox: bool = False,
    ):
        """
        Initialize Gemini CLI integration.
        
        Args:
            workspace: Working directory for CLI execution
            timeout: Timeout in seconds for CLI execution
            output_format: Output format ("json", "text", "stream-json")
            model: Gemini model to use (e.g., "gemini-2.5-pro", "gemini-2.5-flash")
            include_directories: Additional directories to include in context
            sandbox: Whether to run in sandbox mode
        """
        super().__init__(workspace=workspace, timeout=timeout)
        
        self.output_format = output_format
        self.model = model
        self.include_directories = include_directories
        self.sandbox = sandbox
        
        # Store last stats for retrieval
        self._last_stats: Optional[Dict[str, Any]] = None
    
    @property
    def cli_command(self) -> str:
        """Return the CLI command name."""
        return "gemini"
    
    def _build_command(self, prompt: str, **options) -> List[str]:
        """
        Build the Gemini CLI command.
        
        Args:
            prompt: The prompt to send
            **options: Additional options
            
        Returns:
            List of command arguments
        """
        cmd = ["gemini"]
        
        # Add model
        cmd.extend(["-m", self.model])
        
        # Add output format
        cmd.extend(["--output-format", self.output_format])
        
        # Add include directories if specified
        if self.include_directories:
            cmd.extend(["--include-directories", ",".join(self.include_directories)])
        
        # Add sandbox flag if enabled
        if self.sandbox:
            cmd.append("--sandbox")
        
        # Add YOLO mode for non-interactive execution
        cmd.append("--yolo")
        
        # Add prompt flag with prompt value
        cmd.extend(["-p", prompt])
        
        return cmd
    
    async def execute(self, prompt: str, **options) -> str:
        """
        Execute Gemini CLI and return the result.
        
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
                # Store stats for later retrieval
                self._last_stats = data.get("stats")
                # Extract the main response
                return data.get("response", str(data))
            except json.JSONDecodeError:
                return output
        
        return output
    
    async def execute_with_stats(self, prompt: str, **options) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Execute Gemini CLI and return both result and usage stats.
        
        Args:
            prompt: The prompt/query to send
            **options: Additional options
            
        Returns:
            Tuple[str, dict]: (result, stats) where stats contains usage information
        """
        # Ensure JSON format for stats
        original_format = self.output_format
        self.output_format = "json"
        
        try:
            cmd = self._build_command(prompt, **options)
            output = await self.execute_async(cmd)
            
            try:
                data = json.loads(output)
                response = data.get("response", str(data))
                stats = data.get("stats")
                return response, stats
            except json.JSONDecodeError:
                return output, None
        finally:
            self.output_format = original_format
    
    async def stream(self, prompt: str, **options) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream output from Gemini CLI.
        
        Args:
            prompt: The prompt/query to send
            **options: Additional options
            
        Yields:
            dict: Parsed JSON events from the CLI
        """
        # Use stream-json format for streaming
        original_format = self.output_format
        self.output_format = "stream-json"
        
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
    
    def get_last_stats(self) -> Optional[Dict[str, Any]]:
        """
        Get the stats from the last execution.
        
        Returns:
            dict: Usage statistics or None if not available
        """
        return self._last_stats
    
    def get_env(self) -> Dict[str, str]:
        """Get environment variables for CLI execution."""
        env = super().get_env()
        
        # Add Google API key if available
        if "GOOGLE_API_KEY" in os.environ:
            env["GOOGLE_API_KEY"] = os.environ["GOOGLE_API_KEY"]
        elif "GEMINI_API_KEY" in os.environ:
            # Map GEMINI_API_KEY to GOOGLE_API_KEY
            env["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
        
        return env
