"""
OpenAI Codex CLI Integration.

Provides integration with OpenAI's Codex CLI for AI-powered coding tasks.

Features:
- Non-interactive execution with `codex exec`
- Full auto mode for file modifications
- Sandbox modes for security
- JSON streaming output
- Structured output with schemas

Usage:
    from praisonai.integrations import CodexCLIIntegration
    
    # Create integration
    codex = CodexCLIIntegration(workspace="/path/to/project")
    
    # Execute a coding task
    result = await codex.execute("Fix the authentication bug")
    
    # Execute with full auto (allows file modifications)
    codex_auto = CodexCLIIntegration(full_auto=True)
    result = await codex_auto.execute("Refactor the module")
    
    # Use as agent tool
    tool = codex.as_tool()
"""

import json
import os
from typing import AsyncIterator, Dict, Any, Optional, List

from .base import BaseCLIIntegration


class CodexCLIIntegration(BaseCLIIntegration):
    """
    Integration with OpenAI's Codex CLI.
    
    Attributes:
        full_auto: Whether to allow file modifications
        sandbox: Sandbox mode ("default", "danger-full-access")
        json_output: Whether to use JSON streaming output
        output_schema: Path to JSON schema for structured output
    """
    
    def __init__(
        self,
        workspace: str = ".",
        timeout: int = 300,
        full_auto: bool = False,
        sandbox: str = "default",
        json_output: bool = False,
        output_schema: Optional[str] = None,
        output_file: Optional[str] = None,
    ):
        """
        Initialize Codex CLI integration.
        
        Args:
            workspace: Working directory for CLI execution
            timeout: Timeout in seconds for CLI execution
            full_auto: Whether to allow file modifications (--full-auto)
            sandbox: Sandbox mode ("default", "danger-full-access")
            json_output: Whether to use JSON streaming output (--json)
            output_schema: Path to JSON schema for structured output
            output_file: Path to save the final output (-o)
        """
        super().__init__(workspace=workspace, timeout=timeout)
        
        self.full_auto = full_auto
        self.sandbox = sandbox
        self.json_output = json_output
        self.output_schema = output_schema
        self.output_file = output_file
    
    @property
    def cli_command(self) -> str:
        """Return the CLI command name."""
        return "codex"
    
    def _build_command(self, task: str, **options) -> List[str]:
        """
        Build the Codex CLI command.
        
        Args:
            task: The task to execute
            **options: Additional options
            
        Returns:
            List of command arguments
        """
        cmd = ["codex", "exec"]
        
        # Add working directory
        cmd.extend(["-C", self.workspace])
        
        # Add task
        cmd.append(task)
        
        # Add full auto flag if enabled
        if self.full_auto:
            cmd.append("--full-auto")
        
        # Add sandbox mode if not default
        if self.sandbox and self.sandbox != "default":
            cmd.extend(["--sandbox", self.sandbox])
        
        # Add JSON output flag if enabled
        if self.json_output:
            cmd.append("--json")
        
        # Add output schema if specified
        if self.output_schema:
            cmd.extend(["--output-schema", self.output_schema])
        
        # Add output file if specified
        if self.output_file:
            cmd.extend(["-o", self.output_file])
        
        return cmd
    
    async def execute(self, prompt: str, **options) -> str:
        """
        Execute Codex CLI and return the result.
        
        Args:
            prompt: The task/prompt to execute
            **options: Additional options
            
        Returns:
            str: The CLI output
        """
        cmd = self._build_command(prompt, **options)
        
        output = await self.execute_async(cmd)
        
        # Parse JSON Lines output if json_output is enabled
        if self.json_output:
            return self._parse_json_events(output)
        
        return output
    
    def _parse_json_events(self, output: str) -> str:
        """
        Parse JSON Lines output and extract the final result.
        
        Args:
            output: Raw JSON Lines output
            
        Returns:
            str: The extracted result
        """
        result_parts = []
        
        for line in output.strip().split('\n'):
            if not line.strip():
                continue
            
            try:
                event = json.loads(line)
                event_type = event.get("type", "")
                
                # Extract agent messages
                if event_type == "item.completed":
                    item = event.get("item", {})
                    if item.get("type") == "agent_message":
                        text = item.get("text", "")
                        if text:
                            result_parts.append(text)
                
            except json.JSONDecodeError:
                continue
        
        return '\n'.join(result_parts) if result_parts else output
    
    async def stream(self, prompt: str, **options) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream output from Codex CLI.
        
        Args:
            prompt: The task/prompt to execute
            **options: Additional options
            
        Yields:
            dict: Parsed JSON events from the CLI
        """
        # Ensure JSON output is enabled for streaming
        original_json = self.json_output
        self.json_output = True
        
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
            self.json_output = original_json
    
    async def execute_with_schema(
        self, 
        prompt: str, 
        schema_path: str,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute Codex with structured output schema.
        
        Args:
            prompt: The task/prompt to execute
            schema_path: Path to the JSON schema file
            output_path: Optional path to save the output
            
        Returns:
            dict: Parsed structured output
        """
        original_schema = self.output_schema
        original_output = self.output_file
        
        self.output_schema = schema_path
        if output_path:
            self.output_file = output_path
        
        try:
            cmd = self._build_command(prompt)
            output = await self.execute_async(cmd)
            
            # If output file was specified, read from it
            if output_path and os.path.exists(output_path):
                with open(output_path, 'r') as f:
                    return json.load(f)
            
            # Otherwise parse the output
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {"result": output}
        finally:
            self.output_schema = original_schema
            self.output_file = original_output
    
    def get_env(self) -> Dict[str, str]:
        """Get environment variables for CLI execution."""
        env = super().get_env()
        
        # Codex uses ChatGPT authentication or API key
        # The CLI handles authentication internally
        
        return env
