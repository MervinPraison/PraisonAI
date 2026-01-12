"""
Filesystem-backed Artifact Store for Dynamic Context Discovery.

Implements ArtifactStoreProtocol with:
- Deterministic storage layout per run/agent
- Checksum verification
- Secret redaction
- Efficient tail/grep/chunk operations
"""

import re
import json
import time
import uuid
import logging
from pathlib import Path
from typing import Any, List, Optional

from praisonaiagents.context.artifacts import (
    ArtifactRef,
    ArtifactMetadata,
    GrepMatch,
    QueueConfig,
    compute_checksum,
    generate_summary,
)

logger = logging.getLogger(__name__)


class FileSystemArtifactStore:
    """
    Filesystem-backed artifact storage.
    
    Stores artifacts in a deterministic layout:
    ~/.praison/runs/{run_id}/artifacts/{agent_id}/{artifact_id}.{ext}
    
    Features:
    - Automatic MIME type detection
    - Secret redaction (configurable)
    - Checksum verification
    - Efficient tail/grep for large files
    
    Example:
        store = FileSystemArtifactStore(base_dir="~/.praison/runs")
        
        ref = store.store(
            content={"data": [1, 2, 3]},
            metadata=ArtifactMetadata(agent_id="agent1", run_id="run123")
        )
        
        # Later, retrieve
        content = store.load(ref)
        last_lines = store.tail(ref, lines=10)
        matches = store.grep(ref, pattern="error")
    """
    
    def __init__(
        self,
        base_dir: str = "~/.praison/runs",
        config: Optional[QueueConfig] = None,
    ):
        """
        Initialize the artifact store.
        
        Args:
            base_dir: Base directory for artifact storage
            config: Queue configuration (optional)
        """
        self.base_dir = Path(base_dir).expanduser().resolve()
        self.config = config or QueueConfig()
        self._ensure_base_dir()
    
    def _ensure_base_dir(self) -> None:
        """Create base directory if it doesn't exist."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_artifact_dir(self, run_id: str, agent_id: str) -> Path:
        """Get the directory for storing artifacts."""
        artifact_dir = self.base_dir / run_id / "artifacts" / agent_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return artifact_dir
    
    def _detect_mime_type(self, content: Any) -> str:
        """Detect MIME type from content."""
        if isinstance(content, dict) or isinstance(content, list):
            return "application/json"
        elif isinstance(content, bytes):
            return "application/octet-stream"
        else:
            return "text/plain"
    
    def _get_extension(self, mime_type: str) -> str:
        """Get file extension from MIME type."""
        mime_to_ext = {
            "application/json": ".json",
            "text/plain": ".txt",
            "text/html": ".html",
            "text/csv": ".csv",
            "application/xml": ".xml",
            "application/octet-stream": ".bin",
        }
        return mime_to_ext.get(mime_type, ".txt")
    
    def _serialize_content(self, content: Any, mime_type: str) -> bytes:
        """Serialize content to bytes."""
        if isinstance(content, bytes):
            return content
        elif mime_type == "application/json":
            return json.dumps(content, indent=2, default=str).encode("utf-8")
        else:
            return str(content).encode("utf-8")
    
    def _deserialize_content(self, data: bytes, mime_type: str) -> Any:
        """Deserialize bytes to content."""
        if mime_type == "application/json":
            return json.loads(data.decode("utf-8"))
        elif mime_type == "application/octet-stream":
            return data
        else:
            return data.decode("utf-8")
    
    def _redact_secrets(self, content: str) -> str:
        """Redact secrets from content."""
        if not self.config.redact_secrets:
            return content
        
        redacted = content
        for pattern in self.config.secret_patterns:
            try:
                redacted = re.sub(pattern, "[REDACTED]", redacted, flags=re.IGNORECASE)
            except re.error:
                logger.warning(f"Invalid regex pattern: {pattern}")
        
        return redacted
    
    def store(
        self,
        content: Any,
        metadata: ArtifactMetadata,
    ) -> ArtifactRef:
        """
        Store content as an artifact.
        
        Args:
            content: The content to store
            metadata: Metadata about the artifact
            
        Returns:
            ArtifactRef pointing to the stored artifact
        """
        # Generate artifact ID
        artifact_id = str(uuid.uuid4())[:8]
        
        # Detect MIME type
        mime_type = self._detect_mime_type(content)
        
        # Serialize content
        data = self._serialize_content(content, mime_type)
        
        # Redact secrets if text-based
        if mime_type != "application/octet-stream":
            data_str = data.decode("utf-8")
            data_str = self._redact_secrets(data_str)
            data = data_str.encode("utf-8")
        
        # Compute checksum
        checksum = compute_checksum(data, self.config.checksum_algorithm)
        
        # Generate summary
        summary = generate_summary(content, self.config.summary_max_chars)
        
        # Determine file path
        run_id = metadata.run_id or "default"
        agent_id = metadata.agent_id or "default"
        artifact_dir = self._get_artifact_dir(run_id, agent_id)
        
        ext = self._get_extension(mime_type)
        filename = f"{artifact_id}{ext}"
        if metadata.tool_name:
            filename = f"{metadata.tool_name}_{artifact_id}{ext}"
        
        file_path = artifact_dir / filename
        
        # Write content
        file_path.write_bytes(data)
        
        # Write metadata sidecar
        meta_path = file_path.with_suffix(file_path.suffix + ".meta")
        meta_data = {
            **metadata.to_dict(),
            "artifact_id": artifact_id,
            "mime_type": mime_type,
            "checksum": checksum,
            "size_bytes": len(data),
            "created_at": time.time(),
        }
        meta_path.write_text(json.dumps(meta_data, indent=2))
        
        return ArtifactRef(
            path=str(file_path),
            summary=summary,
            size_bytes=len(data),
            mime_type=mime_type,
            checksum=checksum,
            created_at=meta_data["created_at"],
            artifact_id=artifact_id,
            agent_id=agent_id,
            run_id=run_id,
            tool_name=metadata.tool_name,
            turn_id=metadata.turn_id,
        )
    
    def load(self, ref: ArtifactRef) -> Any:
        """
        Load full content from an artifact.
        
        Args:
            ref: Reference to the artifact
            
        Returns:
            The deserialized content
        """
        file_path = Path(ref.path)
        if not file_path.exists():
            raise FileNotFoundError(f"Artifact not found: {ref.path}")
        
        data = file_path.read_bytes()
        
        # Verify checksum if available
        if ref.checksum:
            actual_checksum = compute_checksum(data, self.config.checksum_algorithm)
            if actual_checksum != ref.checksum:
                logger.warning(f"Checksum mismatch for {ref.path}")
        
        return self._deserialize_content(data, ref.mime_type)
    
    def tail(self, ref: ArtifactRef, lines: int = 50) -> str:
        """
        Get the last N lines of an artifact.
        
        Args:
            ref: Reference to the artifact
            lines: Number of lines to return
            
        Returns:
            String containing the last N lines
        """
        file_path = Path(ref.path)
        if not file_path.exists():
            raise FileNotFoundError(f"Artifact not found: {ref.path}")
        
        # Efficient tail for large files
        with open(file_path, "rb") as f:
            # Seek to end
            f.seek(0, 2)
            file_size = f.tell()
            
            # Read in chunks from the end
            chunk_size = 8192
            found_lines = []
            position = file_size
            
            while position > 0 and len(found_lines) < lines + 1:
                read_size = min(chunk_size, position)
                position -= read_size
                f.seek(position)
                chunk = f.read(read_size).decode("utf-8", errors="replace")
                
                # Split into lines and prepend
                chunk_lines = chunk.split("\n")
                if found_lines:
                    # Merge with previous chunk
                    chunk_lines[-1] += found_lines[0]
                    found_lines = chunk_lines + found_lines[1:]
                else:
                    found_lines = chunk_lines
            
            # Return last N lines
            return "\n".join(found_lines[-lines:])
    
    def head(self, ref: ArtifactRef, lines: int = 50) -> str:
        """
        Get the first N lines of an artifact.
        
        Args:
            ref: Reference to the artifact
            lines: Number of lines to return
            
        Returns:
            String containing the first N lines
        """
        file_path = Path(ref.path)
        if not file_path.exists():
            raise FileNotFoundError(f"Artifact not found: {ref.path}")
        
        result_lines = []
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= lines:
                    break
                result_lines.append(line.rstrip("\n"))
        
        return "\n".join(result_lines)
    
    def grep(
        self,
        ref: ArtifactRef,
        pattern: str,
        context_lines: int = 2,
        max_matches: int = 50,
    ) -> List[GrepMatch]:
        """
        Search for pattern in artifact content.
        
        Args:
            ref: Reference to the artifact
            pattern: Regex pattern to search for
            context_lines: Number of context lines before/after match
            max_matches: Maximum number of matches to return
            
        Returns:
            List of GrepMatch objects
        """
        file_path = Path(ref.path)
        if not file_path.exists():
            raise FileNotFoundError(f"Artifact not found: {ref.path}")
        
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        
        matches = []
        
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        
        for i, line in enumerate(all_lines):
            if regex.search(line):
                # Get context
                start = max(0, i - context_lines)
                end = min(len(all_lines), i + context_lines + 1)
                
                match = GrepMatch(
                    line_number=i + 1,
                    line_content=line.rstrip("\n"),
                    context_before=[ln.rstrip("\n") for ln in all_lines[start:i]],
                    context_after=[ln.rstrip("\n") for ln in all_lines[i+1:end]],
                )
                matches.append(match)
                
                if len(matches) >= max_matches:
                    break
        
        return matches
    
    def chunk(
        self,
        ref: ArtifactRef,
        start_line: int = 1,
        end_line: Optional[int] = None,
    ) -> str:
        """
        Get a chunk of lines from an artifact.
        
        Args:
            ref: Reference to the artifact
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (inclusive), None for end of file
            
        Returns:
            String containing the requested lines
        """
        file_path = Path(ref.path)
        if not file_path.exists():
            raise FileNotFoundError(f"Artifact not found: {ref.path}")
        
        result_lines = []
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                if i < start_line:
                    continue
                if end_line is not None and i > end_line:
                    break
                result_lines.append(line.rstrip("\n"))
        
        return "\n".join(result_lines)
    
    def delete(self, ref: ArtifactRef) -> bool:
        """
        Delete an artifact.
        
        Args:
            ref: Reference to the artifact
            
        Returns:
            True if deleted successfully
        """
        file_path = Path(ref.path)
        meta_path = file_path.with_suffix(file_path.suffix + ".meta")
        
        deleted = False
        if file_path.exists():
            file_path.unlink()
            deleted = True
        if meta_path.exists():
            meta_path.unlink()
        
        return deleted
    
    def list_artifacts(
        self,
        run_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> List[ArtifactRef]:
        """
        List artifacts matching filters.
        
        Args:
            run_id: Filter by run ID
            agent_id: Filter by agent ID
            tool_name: Filter by tool name
            
        Returns:
            List of matching ArtifactRef objects
        """
        artifacts = []
        
        # Determine search path
        if run_id:
            search_paths = [self.base_dir / run_id / "artifacts"]
        else:
            search_paths = list(self.base_dir.glob("*/artifacts"))
        
        for artifacts_dir in search_paths:
            if not artifacts_dir.exists():
                continue
            
            # Search for agent directories
            if agent_id:
                agent_dirs = [artifacts_dir / agent_id]
            else:
                agent_dirs = list(artifacts_dir.iterdir())
            
            for agent_dir in agent_dirs:
                if not agent_dir.is_dir():
                    continue
                
                # Find all meta files
                for meta_file in agent_dir.glob("*.meta"):
                    try:
                        meta_data = json.loads(meta_file.read_text())
                        
                        # Apply tool_name filter
                        if tool_name and meta_data.get("tool_name") != tool_name:
                            continue
                        
                        # Get artifact file path
                        artifact_path = meta_file.with_suffix("")
                        if not artifact_path.exists():
                            continue
                        
                        ref = ArtifactRef(
                            path=str(artifact_path),
                            summary=meta_data.get("summary", ""),
                            size_bytes=meta_data.get("size_bytes", 0),
                            mime_type=meta_data.get("mime_type", "application/octet-stream"),
                            checksum=meta_data.get("checksum", ""),
                            created_at=meta_data.get("created_at", 0),
                            artifact_id=meta_data.get("artifact_id", ""),
                            agent_id=meta_data.get("agent_id", ""),
                            run_id=meta_data.get("run_id", ""),
                            tool_name=meta_data.get("tool_name"),
                            turn_id=meta_data.get("turn_id", 0),
                        )
                        artifacts.append(ref)
                    except (json.JSONDecodeError, IOError) as e:
                        logger.warning(f"Failed to read metadata: {meta_file}: {e}")
        
        # Sort by creation time (newest first)
        artifacts.sort(key=lambda x: x.created_at, reverse=True)
        return artifacts
    
    def get_run_dir(self, run_id: str) -> Path:
        """Get the directory for a specific run."""
        return self.base_dir / run_id
    
    def cleanup_run(self, run_id: str) -> int:
        """
        Delete all artifacts for a run.
        
        Args:
            run_id: Run ID to clean up
            
        Returns:
            Number of artifacts deleted
        """
        import shutil
        
        run_dir = self.base_dir / run_id
        if not run_dir.exists():
            return 0
        
        # Count artifacts before deletion
        artifacts = self.list_artifacts(run_id=run_id)
        count = len(artifacts)
        
        # Remove the entire run directory
        shutil.rmtree(run_dir)
        
        return count
