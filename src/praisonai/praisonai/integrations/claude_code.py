"""
Claude Code CLI Integration.

Provides integration with Claude Code CLI for AI-powered coding tasks.

Features:
- Headless mode execution with JSON output
- Session continuation support
- System prompt customization
- Tool restrictions
- Optional SDK integration (when claude-agent-sdk is installed)

Usage:
    from praisonai.integrations import ClaudeCodeIntegration
    
    # Create integration
    claude = ClaudeCodeIntegration(workspace="/path/to/project")
    
    # Execute a coding task
    result = await claude.execute("Refactor the auth module")
    
    # Stream output
    async for event in claude.stream("Add error handling"):
        print(event)
    
    # Use as agent tool
    tool = claude.as_tool()
"""

import json
import os
from typing import AsyncIterator, Dict, Any, Optional, List

from .base import BaseCLIIntegration


# Check if Claude Code SDK is available
CLAUDE_SDK_AVAILABLE = False
try:
    from claude_agent_sdk import query as claude_query, ClaudeAgentOptions
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    pass


class ClaudeCodeIntegration(BaseCLIIntegration):
    """
    Integration with Claude Code CLI.
    
    Supports both subprocess-based execution and SDK-based execution
    (when claude-agent-sdk is installed).
    
    Attributes:
        output_format: Output format ("json", "text", "stream-json")
        skip_permissions: Whether to skip permission prompts
        system_prompt: Custom system prompt to append
        allowed_tools: List of allowed tools (e.g., ["Read", "Write", "Bash"])
        disallowed_tools: List of disallowed tools
        use_sdk: Whether to use the SDK instead of subprocess
    """
    
    def __init__(
        self,
        workspace: str = ".",
        timeout: int = 300,
        output_format: str = "json",
        skip_permissions: bool = True,
        system_prompt: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        disallowed_tools: Optional[List[str]] = None,
        use_sdk: bool = False,
        model: Optional[str] = None,
    ):
        """
        Initialize Claude Code integration.
        
        Args:
            workspace: Working directory for CLI execution
            timeout: Timeout in seconds for CLI execution
            output_format: Output format ("json", "text", "stream-json")
            skip_permissions: Whether to skip permission prompts (--dangerously-skip-permissions)
            system_prompt: Custom system prompt to append
            allowed_tools: List of allowed tools
            disallowed_tools: List of disallowed tools
            use_sdk: Whether to use the SDK instead of subprocess
            model: Model to use (e.g., "sonnet", "opus")
        """
        super().__init__(workspace=workspace, timeout=timeout)
        
        self.output_format = output_format
        self.skip_permissions = skip_permissions
        self.system_prompt = system_prompt
        self.allowed_tools = allowed_tools
        self.disallowed_tools = disallowed_tools
        self.use_sdk = use_sdk and CLAUDE_SDK_AVAILABLE
        self.model = model
        
        # Session management
        self._session_active = False
    
    @property
    def cli_command(self) -> str:
        """Return the CLI command name."""
        return "claude"
    
    @property
    def sdk_available(self) -> bool:
        """Check if the Claude Code SDK is available."""
        return CLAUDE_SDK_AVAILABLE
    
    def _build_command(
        self, 
        prompt: str, 
        continue_session: bool = False,
        **options
    ) -> List[str]:
        """
        Build the Claude CLI command.
        
        Args:
            prompt: The prompt to send
            continue_session: Whether to continue a previous session
            **options: Additional options
            
        Returns:
            List of command arguments
        """
        cmd = ["claude"]
        
        # Add print mode flag for non-interactive output
        cmd.append("-p")
        
        # Add output format
        cmd.extend(["--output-format", self.output_format])
        
        # Add continue flag if needed
        if continue_session or self._session_active:
            cmd.append("--continue")
        
        # Add model if specified
        if self.model:
            cmd.extend(["--model", self.model])
        
        # Add system prompt if specified
        if self.system_prompt:
            cmd.extend(["--append-system-prompt", self.system_prompt])
        
        # Add allowed tools if specified
        if self.allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])
        
        # Add disallowed tools if specified
        if self.disallowed_tools:
            cmd.extend(["--disallowedTools", ",".join(self.disallowed_tools)])
        
        # Add verbose if needed
        if options.get('verbose'):
            cmd.append("--verbose")
        
        # Add prompt last
        cmd.append(prompt)
        
        return cmd
    
    async def execute(self, prompt: str, **options) -> str:
        """
        Execute Claude Code CLI and return the result.
        
        Args:
            prompt: The prompt/query to send
            **options: Additional options (continue_session, etc.)
            
        Returns:
            str: The CLI output (parsed from JSON if output_format is "json")
        """
        if self.use_sdk:
            return await self._execute_sdk(prompt, **options)
        
        return await self._execute_subprocess(prompt, **options)
    
    async def _execute_subprocess(self, prompt: str, **options) -> str:
        """Execute using subprocess."""
        cmd = self._build_command(prompt, **options)
        
        output = await self.execute_async(cmd)
        
        # Mark session as active for continuation
        self._session_active = True
        
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
    
    async def _execute_sdk(self, prompt: str, **options) -> str:
        """Execute using the Claude Code SDK."""
        if not CLAUDE_SDK_AVAILABLE:
            raise RuntimeError("Claude Code SDK not available. Install with: pip install claude-agent-sdk")
        
        sdk_options = ClaudeAgentOptions(
            cwd=self.workspace,
            system_prompt=self.system_prompt,
        )
        
        if self.allowed_tools:
            sdk_options.allowed_tools = self.allowed_tools
        
        if self.skip_permissions:
            sdk_options.permission_mode = 'acceptEdits'
        
        result_parts = []
        async for message in claude_query(prompt=prompt, options=sdk_options):
            if hasattr(message, 'content'):
                for block in message.content:
                    if hasattr(block, 'text'):
                        result_parts.append(block.text)
        
        return '\n'.join(result_parts)
    
    async def stream(self, prompt: str, **options) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream output from Claude Code CLI.
        
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
    
    def reset_session(self):
        """Reset the session state."""
        self._session_active = False
    
    def get_env(self) -> Dict[str, str]:
        """Get environment variables for CLI execution."""
        env = super().get_env()
        
        # Add Anthropic API key if available
        if "ANTHROPIC_API_KEY" in os.environ:
            env["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
        elif "CLAUDE_API_KEY" in os.environ:
            env["ANTHROPIC_API_KEY"] = os.environ["CLAUDE_API_KEY"]
        
        return env
