"""Claude Code CLI Backend.

Implementation of CliBackendProtocol for Claude Code CLI following OpenClaw patterns:
- Default configuration mirroring OpenClaw's claude-backend.ts
- Subprocess execution with JSONL parsing
- Environment sanitization and session management
"""

import os
import json
import asyncio
import subprocess
from typing import Optional, List, Dict, Any, AsyncIterator

try:
    from praisonaiagents import CliBackendProtocol, CliBackendConfig, CliSessionBinding, CliBackendResult, CliBackendDelta
except ImportError:
    # Fallback for testing or development
    from praisonaiagents.cli_backend.protocols import CliBackendProtocol, CliBackendConfig, CliSessionBinding, CliBackendResult, CliBackendDelta


# Default configuration matching OpenClaw's extensions/anthropic/cli-backend.ts
DEFAULT_CONFIG = CliBackendConfig(
    command="claude",
    args=[
        "-p", 
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--verbose",
        "--setting-sources", "user",
        "--permission-mode", "bypassPermissions"
    ],
    resume_args=["-p", "--output-format", "stream-json", "--resume", "{session_id}"],
    output="jsonl",
    input="stdin",
    live_session="claude-stdio",
    model_arg="--model",
    model_aliases={
        "opus": "claude-opus-4-5",
        "sonnet": "claude-sonnet-4-5",
        "haiku": "claude-haiku-3-5"
    },
    session_arg="--session-id",
    session_mode="always",
    session_id_fields=["session_id"],
    system_prompt_arg="--append-system-prompt",
    system_prompt_when="first",
    image_arg="--image",
    # Environment sanitization from OpenClaw cli-shared.ts
    clear_env=[
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL", 
        "ANTHROPIC_OAUTH_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_RESOURCE_ATTRIBUTES",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN"
    ],
    bundle_mcp=True,
    bundle_mcp_mode="claude-config-file",
    serialize=True,
    timeout_ms=300_000
)


class ClaudeCodeBackend:
    """Claude Code CLI backend implementation."""
    
    def __init__(self, config: Optional[CliBackendConfig] = None):
        """Initialize with custom or default configuration."""
        self.config = config or DEFAULT_CONFIG
    
    async def execute(
        self,
        prompt: str,
        *,
        session: Optional[CliSessionBinding] = None,
        images: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> CliBackendResult:
        """Execute a single prompt via Claude CLI."""
        cmd = self._build_command(
            prompt, 
            session=session,
            images=images,
            system_prompt=system_prompt,
            **kwargs
        )
        
        try:
            # Use execute mode (not streaming)
            result = await self._execute_subprocess(cmd)
            
            # Parse result if JSON output
            if self.config.output == "json":
                try:
                    data = json.loads(result)
                    content = data.get("content", result)
                except json.JSONDecodeError:
                    content = result
            else:
                content = result
            
            return CliBackendResult(
                content=content,
                session_id=session.session_id if session else None,
                metadata={"command": cmd}
            )
            
        except subprocess.CalledProcessError as e:
            error_msg = str(e)
            if hasattr(e, 'stderr') and e.stderr:
                try:
                    error_msg = e.stderr.decode() if isinstance(e.stderr, bytes) else str(e.stderr)
                except AttributeError:
                    error_msg = str(e.stderr)
            return CliBackendResult(
                content="",
                error=f"Claude CLI failed: {error_msg}",
                metadata={"command": cmd, "return_code": getattr(e, 'returncode', -1)}
            )
    
    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[CliBackendDelta]:
        """Stream response deltas from Claude CLI."""
        cmd = self._build_command(prompt, output_format="stream-json", **kwargs)
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._get_env()
            )
            
            async for line in self._read_lines(process.stdout):
                if line.strip():
                    try:
                        event = json.loads(line)
                        delta_type = event.get("type", "text")
                        content = event.get("content", event.get("data", ""))
                        
                        yield CliBackendDelta(
                            type=delta_type,
                            content=str(content),
                            metadata=event
                        )
                    except json.JSONDecodeError:
                        # Fallback for non-JSON lines
                        yield CliBackendDelta(
                            type="text",
                            content=line,
                            metadata={}
                        )
            
            # Wait for process completion
            await process.wait()
            
            if process.returncode != 0:
                stderr = await process.stderr.read()
                error_msg = stderr.decode() if stderr else f"Process exited {process.returncode}"
                yield CliBackendDelta(
                    type="error",
                    content=f"Claude CLI error: {error_msg}",
                    metadata={"return_code": process.returncode}
                )
                
        except Exception as e:
            yield CliBackendDelta(
                type="error",
                content=f"Stream error: {str(e)}",
                metadata={"command": cmd}
            )
    
    def _build_command(
        self,
        prompt: str,
        *,
        session: Optional[CliSessionBinding] = None,
        images: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        output_format: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> List[str]:
        """Build Claude CLI command with arguments."""
        # Start with base command and args
        cmd = [self.config.command] + list(self.config.args)
        
        # Override output format if specified
        if output_format:
            # Replace existing output format
            try:
                idx = cmd.index("--output-format")
                cmd[idx + 1] = output_format
            except ValueError:
                cmd.extend(["--output-format", output_format])
        
        # Add session if provided
        if session and session.session_id and self.config.session_mode != "none":
            if self.config.session_arg:
                cmd.extend([self.config.session_arg, session.session_id])
        
        # Add model if specified
        if model and self.config.model_arg:
            # Apply aliases
            resolved_model = self.config.model_aliases.get(model, model)
            cmd.extend([self.config.model_arg, resolved_model])
        
        # Add system prompt if specified and configured
        if system_prompt and self.config.system_prompt_arg:
            cmd.extend([self.config.system_prompt_arg, system_prompt])
        
        # Add images if provided
        if images and self.config.image_arg:
            for image_path in images:
                cmd.extend([self.config.image_arg, image_path])
        
        # Add prompt as argument or prepare for stdin
        if self.config.input == "arg":
            cmd.append(prompt)
        
        return cmd
    
    async def _execute_subprocess(self, cmd: List[str]) -> str:
        """Execute subprocess and return stdout."""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._get_env()
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else f"Exit code {process.returncode}"
            raise subprocess.CalledProcessError(process.returncode, cmd, stderr=error_msg)
        
        return stdout.decode()
    
    async def _read_lines(self, stream) -> AsyncIterator[str]:
        """Read lines from async stream."""
        while True:
            line = await stream.readline()
            if not line:
                break
            yield line.decode().rstrip('\n')
    
    def _get_env(self) -> Dict[str, str]:
        """Get environment with sanitization."""
        env = dict(os.environ)
        
        # Clear specified environment variables
        for var in self.config.clear_env:
            env.pop(var, None)
        
        # Add custom environment variables
        env.update(self.config.env)
        
        return env