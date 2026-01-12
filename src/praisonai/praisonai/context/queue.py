"""
Output Queue for Dynamic Context Discovery.

Middleware that automatically queues large tool outputs to artifacts,
replacing them with lightweight references in the context.

Usage:
    from praisonai.context import OutputQueue, create_queue_middleware
    
    # Create output queue
    queue = OutputQueue(store=artifact_store)
    
    # Process tool output
    result = queue.process(tool_output, metadata)
    # Returns either original output (if small) or ArtifactRef (if large)
    
    # Or use as middleware
    middleware = create_queue_middleware(store=artifact_store)
    agent = Agent(hooks=[middleware])
"""

import json
import logging
from typing import Any, Callable, Optional, Union

from praisonaiagents.context.artifacts import (
    ArtifactRef,
    ArtifactMetadata,
    QueueConfig,
)
from praisonaiagents.hooks import ToolRequest, ToolResponse

from .artifact_store import FileSystemArtifactStore

logger = logging.getLogger(__name__)


class OutputQueue:
    """
    Middleware that queues large tool outputs to artifacts.
    
    When a tool produces output larger than the configured threshold,
    the queue stores it as an artifact and returns a reference instead.
    
    Features:
    - Configurable size threshold
    - Automatic MIME type detection
    - Secret redaction
    - Checksum verification
    
    Example:
        queue = OutputQueue(
            store=FileSystemArtifactStore(),
            config=QueueConfig(inline_max_bytes=32*1024)
        )
        
        # Small output - returned as-is
        small_result = queue.process("Hello", metadata)
        # Returns: "Hello"
        
        # Large output - queued to artifact
        large_result = queue.process(large_json_data, metadata)
        # Returns: ArtifactRef(path="...", summary="...", ...)
    """
    
    def __init__(
        self,
        store: Optional[FileSystemArtifactStore] = None,
        config: Optional[QueueConfig] = None,
        base_dir: str = "~/.praison/runs",
    ):
        """
        Initialize the output queue.
        
        Args:
            store: Artifact store to use (created if not provided)
            config: Queue configuration
            base_dir: Base directory for artifacts (if store not provided)
        """
        self.config = config or QueueConfig()
        self.store = store or FileSystemArtifactStore(
            base_dir=base_dir,
            config=self.config,
        )
    
    def _estimate_size(self, content: Any) -> int:
        """Estimate the serialized size of content."""
        if isinstance(content, bytes):
            return len(content)
        elif isinstance(content, str):
            return len(content.encode("utf-8"))
        else:
            # Serialize to JSON to estimate size
            try:
                return len(json.dumps(content, default=str).encode("utf-8"))
            except (TypeError, ValueError):
                return len(str(content).encode("utf-8"))
    
    def should_queue(self, content: Any) -> bool:
        """
        Determine if content should be queued to artifact.
        
        Args:
            content: The content to check
            
        Returns:
            True if content should be queued to artifact
        """
        if not self.config.enabled:
            return False
        
        size = self._estimate_size(content)
        return size > self.config.inline_max_bytes
    
    def process(
        self,
        content: Any,
        metadata: ArtifactMetadata,
    ) -> Union[Any, ArtifactRef]:
        """
        Process tool output, queuing to artifact if necessary.
        
        Args:
            content: The tool output content
            metadata: Metadata about the tool call
            
        Returns:
            Original content if small, ArtifactRef if queued
        """
        if not self.should_queue(content):
            return content
        
        # Queue to artifact
        ref = self.store.store(content, metadata)
        logger.info(
            f"Queued tool output to artifact: {ref.path} "
            f"({ref.size_bytes} bytes)"
        )
        return ref
    
    
    def process_tool_response(
        self,
        response: ToolResponse,
        run_id: str = "default",
    ) -> ToolResponse:
        """
        Process a ToolResponse, queuing result if necessary.
        
        Args:
            response: The tool response to process
            run_id: Run ID for artifact storage
            
        Returns:
            Modified ToolResponse with result potentially replaced by ArtifactRef
        """
        if response.error:
            return response
        
        metadata = ArtifactMetadata(
            agent_id=response.context.agent_id if response.context else "default",
            run_id=run_id,
            tool_name=response.tool_name,
            turn_id=0,
        )
        
        processed_result = self.process(response.result, metadata)
        
        # If queued, update the response
        if isinstance(processed_result, ArtifactRef):
            # Replace result with inline reference
            response.result = processed_result.to_inline()
            response.extra["artifact_ref"] = processed_result.to_dict()
        
        return response


def create_queue_middleware(
    store: Optional[FileSystemArtifactStore] = None,
    config: Optional[QueueConfig] = None,
    base_dir: str = "~/.praison/runs",
    run_id: str = "default",
) -> Callable:
    """
    Create a wrap_tool_call middleware for automatic output queuing.
    
    This middleware intercepts tool calls and automatically queues
    large outputs to artifacts.
    
    Args:
        store: Artifact store to use
        config: Queue configuration
        base_dir: Base directory for artifacts
        run_id: Run ID for artifact storage
        
    Returns:
        Middleware function compatible with Agent(hooks=[...])
        
    Example:
        middleware = create_queue_middleware(
            config=QueueConfig(inline_max_bytes=16*1024)
        )
        agent = Agent(name="MyAgent", hooks=[middleware])
    """
    queue = OutputQueue(store=store, config=config, base_dir=base_dir)
    
    def queue_middleware(
        request: ToolRequest,
        call_next: Callable[[ToolRequest], ToolResponse],
    ) -> ToolResponse:
        """Middleware that queues large tool outputs."""
        # Execute the tool
        response = call_next(request)
        
        # Process the response
        return queue.process_tool_response(response, run_id=run_id)
    
    # Mark as wrap_tool_call middleware
    queue_middleware._middleware_type = "wrap_tool_call"
    
    return queue_middleware



def create_artifact_tools(
    store: Optional[FileSystemArtifactStore] = None,
    base_dir: str = "~/.praison/runs",
):
    """
    Create tools for agents to interact with artifacts.
    
    Returns a list of tool functions that can be passed to Agent(tools=[...]).
    
    Tools created:
    - artifact_tail: Get last N lines of an artifact
    - artifact_head: Get first N lines of an artifact
    - artifact_grep: Search for pattern in artifact
    - artifact_chunk: Get specific line range from artifact
    - artifact_list: List available artifacts
    
    Example:
        tools = create_artifact_tools()
        agent = Agent(name="MyAgent", tools=tools)
    """
    artifact_store = store or FileSystemArtifactStore(base_dir=base_dir)
    
    def artifact_tail(artifact_path: str, lines: int = 50) -> str:
        """
        Get the last N lines of an artifact file.
        
        Args:
            artifact_path: Path to the artifact file
            lines: Number of lines to return (default: 50)
            
        Returns:
            String containing the last N lines
        """
        ref = ArtifactRef(path=artifact_path, summary="", size_bytes=0)
        try:
            return artifact_store.tail(ref, lines=lines)
        except FileNotFoundError:
            return f"Error: Artifact not found: {artifact_path}"
    
    def artifact_head(artifact_path: str, lines: int = 50) -> str:
        """
        Get the first N lines of an artifact file.
        
        Args:
            artifact_path: Path to the artifact file
            lines: Number of lines to return (default: 50)
            
        Returns:
            String containing the first N lines
        """
        ref = ArtifactRef(path=artifact_path, summary="", size_bytes=0)
        try:
            return artifact_store.head(ref, lines=lines)
        except FileNotFoundError:
            return f"Error: Artifact not found: {artifact_path}"
    
    def artifact_grep(
        artifact_path: str,
        pattern: str,
        context_lines: int = 2,
        max_matches: int = 20,
    ) -> str:
        """
        Search for a pattern in an artifact file.
        
        Args:
            artifact_path: Path to the artifact file
            pattern: Regex pattern to search for
            context_lines: Number of context lines before/after match
            max_matches: Maximum number of matches to return
            
        Returns:
            Formatted string with matches and context
        """
        ref = ArtifactRef(path=artifact_path, summary="", size_bytes=0)
        try:
            matches = artifact_store.grep(
                ref,
                pattern=pattern,
                context_lines=context_lines,
                max_matches=max_matches,
            )
            
            if not matches:
                return f"No matches found for pattern: {pattern}"
            
            result_lines = [f"Found {len(matches)} matches:"]
            for match in matches:
                result_lines.append(f"\n--- Line {match.line_number} ---")
                for ctx_line in match.context_before:
                    result_lines.append(f"  {ctx_line}")
                result_lines.append(f"> {match.line_content}")
                for ctx_line in match.context_after:
                    result_lines.append(f"  {ctx_line}")
            
            return "\n".join(result_lines)
        except FileNotFoundError:
            return f"Error: Artifact not found: {artifact_path}"
        except ValueError as e:
            return f"Error: {e}"
    
    def artifact_chunk(
        artifact_path: str,
        start_line: int = 1,
        end_line: Optional[int] = None,
    ) -> str:
        """
        Get a specific range of lines from an artifact file.
        
        Args:
            artifact_path: Path to the artifact file
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (inclusive), None for end of file
            
        Returns:
            String containing the requested lines
        """
        ref = ArtifactRef(path=artifact_path, summary="", size_bytes=0)
        try:
            return artifact_store.chunk(ref, start_line=start_line, end_line=end_line)
        except FileNotFoundError:
            return f"Error: Artifact not found: {artifact_path}"
    
    def artifact_list(
        run_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> str:
        """
        List available artifacts.
        
        Args:
            run_id: Filter by run ID
            agent_id: Filter by agent ID
            tool_name: Filter by tool name
            
        Returns:
            Formatted list of artifacts
        """
        artifacts = artifact_store.list_artifacts(
            run_id=run_id,
            agent_id=agent_id,
            tool_name=tool_name,
        )
        
        if not artifacts:
            return "No artifacts found."
        
        result_lines = [f"Found {len(artifacts)} artifacts:"]
        for ref in artifacts:
            size_str = ArtifactRef._format_size(ref.size_bytes)
            tool_info = f" (from {ref.tool_name})" if ref.tool_name else ""
            result_lines.append(
                f"- {ref.path}{tool_info}\n"
                f"  Size: {size_str}, Summary: {ref.summary[:50]}..."
            )
        
        return "\n".join(result_lines)
    
    return [artifact_tail, artifact_head, artifact_grep, artifact_chunk, artifact_list]
