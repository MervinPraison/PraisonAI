"""
Concrete implementation of ArtifactStoreProtocol for filesystem storage.

This module provides a filesystem-based artifact store that persists
tool outputs to disk when they exceed configured size limits.
"""

import os
import re
import json
import time
import uuid
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .artifacts import (
    ArtifactRef,
    ArtifactMetadata,
    ArtifactStoreProtocol,
    GrepMatch,
    compute_checksum,
    generate_summary,
)


class FileSystemArtifactStore:
    """
    Filesystem-based artifact storage implementation.
    
    Stores artifacts under ~/.praisonai/artifacts/{agent_id}/{run_id}/
    with content-addressed naming using SHA256 hashes.
    """
    
    def __init__(
        self,
        base_dir: Optional[str] = None,
        retention_days: int = 7,
        redact_secrets: bool = True,
    ):
        """
        Initialize the filesystem artifact store.
        
        Args:
            base_dir: Base directory for storage (default: ~/.praisonai/artifacts)
            retention_days: Days to retain artifacts before GC
            redact_secrets: Whether to redact secrets from stored content
        """
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            # Use standard PraisonAI data directory
            home = Path.home()
            self.base_dir = home / ".praisonai" / "artifacts"
        
        self.retention_days = retention_days
        self.redact_secrets = redact_secrets
        self._secret_patterns = [
            r'(?i)(api[_-]?key|apikey)["\']?\s*[:=]\s*["\']?[\w\-]+',
            r'(?i)(secret|password|passwd|pwd)["\']?\s*[:=]\s*["\']?[\w\-]+',
            r'(?i)(token|bearer)["\']?\s*[:=]\s*["\']?[\w\-]+',
            r'sk-[a-zA-Z0-9]{20,}',  # OpenAI keys
            r'ghp_[a-zA-Z0-9]{36}',  # GitHub tokens
        ]
        
        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def store(
        self,
        content: Any,
        metadata: ArtifactMetadata,
    ) -> ArtifactRef:
        """
        Store content as an artifact.
        
        Args:
            content: The content to store (will be serialized)
            metadata: Metadata about the artifact
            
        Returns:
            ArtifactRef pointing to the stored artifact
        """
        # Serialize content
        if isinstance(content, (str, bytes)):
            content_bytes = content.encode("utf-8") if isinstance(content, str) else content
            mime_type = "text/plain"
        else:
            # JSON serialize structured data
            content_str = json.dumps(content, indent=2, default=str)
            content_bytes = content_str.encode("utf-8")
            mime_type = "application/json"
        
        # Redact secrets if enabled
        if self.redact_secrets and isinstance(content, str):
            for pattern in self._secret_patterns:
                content = re.sub(pattern, "[REDACTED]", content)
            content_bytes = content.encode("utf-8")
        
        # Compute checksum
        checksum = compute_checksum(content_bytes)
        
        # Generate artifact ID
        artifact_id = f"{checksum[:12]}_{uuid.uuid4().hex[:8]}"
        
        # Create directory structure
        artifact_dir = self.base_dir / metadata.agent_id / metadata.run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        # Write content to file
        artifact_path = artifact_dir / f"{artifact_id}.artifact"
        artifact_path.write_bytes(content_bytes)
        
        # Write metadata
        meta_path = artifact_dir / f"{artifact_id}.meta.json"
        meta_data = metadata.to_dict()
        meta_data["checksum"] = checksum
        meta_data["size_bytes"] = len(content_bytes)
        meta_data["mime_type"] = mime_type
        meta_data["created_at"] = time.time()
        meta_path.write_text(json.dumps(meta_data, indent=2))
        
        # Generate summary
        summary = generate_summary(content, max_chars=200)
        
        # Create and return reference
        ref = ArtifactRef(
            path=str(artifact_path),
            summary=summary,
            size_bytes=len(content_bytes),
            mime_type=mime_type,
            checksum=checksum,
            created_at=meta_data["created_at"],
            artifact_id=artifact_id,
            agent_id=metadata.agent_id,
            run_id=metadata.run_id,
            tool_name=metadata.tool_name,
            turn_id=metadata.turn_id,
        )
        
        logging.debug(f"Stored artifact {artifact_id} ({len(content_bytes)} bytes) at {artifact_path}")
        
        return ref
    
    def load(self, ref: ArtifactRef) -> Any:
        """
        Load full content from an artifact.
        
        Args:
            ref: Reference to the artifact
            
        Returns:
            The deserialized content
        """
        path = Path(ref.path)
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {ref.path}")
        
        content_bytes = path.read_bytes()
        
        # Verify checksum if provided
        if ref.checksum:
            actual_checksum = compute_checksum(content_bytes)
            if actual_checksum != ref.checksum:
                raise ValueError(f"Checksum mismatch for artifact {ref.artifact_id}")
        
        # Deserialize based on mime type
        if ref.mime_type == "application/json":
            return json.loads(content_bytes.decode("utf-8"))
        else:
            return content_bytes.decode("utf-8")
    
    def tail(self, ref: ArtifactRef, lines: int = 50) -> str:
        """
        Get the last N lines of an artifact.
        
        Args:
            ref: Reference to the artifact
            lines: Number of lines to return
            
        Returns:
            String containing the last N lines
        """
        path = Path(ref.path)
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {ref.path}")
        
        content = path.read_text(encoding="utf-8", errors="replace")
        content_lines = content.splitlines()
        
        if len(content_lines) <= lines:
            return content
        
        return "\n".join(content_lines[-lines:])
    
    def head(self, ref: ArtifactRef, lines: int = 50) -> str:
        """
        Get the first N lines of an artifact.
        
        Args:
            ref: Reference to the artifact
            lines: Number of lines to return
            
        Returns:
            String containing the first N lines
        """
        path = Path(ref.path)
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {ref.path}")
        
        content = path.read_text(encoding="utf-8", errors="replace")
        content_lines = content.splitlines()
        
        if len(content_lines) <= lines:
            return content
        
        return "\n".join(content_lines[:lines])
    
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
        path = Path(ref.path)
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {ref.path}")
        
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        
        matches = []
        pattern_re = re.compile(pattern, re.IGNORECASE)
        
        for i, line in enumerate(lines):
            if pattern_re.search(line):
                # Get context lines
                start_idx = max(0, i - context_lines)
                end_idx = min(len(lines), i + context_lines + 1)
                
                match = GrepMatch(
                    line_number=i + 1,  # 1-indexed
                    line_content=line,
                    context_before=lines[start_idx:i],
                    context_after=lines[i + 1:end_idx],
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
        path = Path(ref.path)
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {ref.path}")
        
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        
        # Convert to 0-indexed
        start_idx = max(0, start_line - 1)
        end_idx = end_line if end_line is None else end_line
        
        return "\n".join(lines[start_idx:end_idx])
    
    def delete(self, ref: ArtifactRef) -> bool:
        """
        Delete an artifact.
        
        Args:
            ref: Reference to the artifact
            
        Returns:
            True if deleted successfully
        """
        path = Path(ref.path)
        meta_path = path.with_suffix(".meta.json")
        
        deleted = False
        if path.exists():
            path.unlink()
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
        
        # Determine search path based on filters
        if agent_id and run_id:
            search_path = self.base_dir / agent_id / run_id
            if search_path.exists():
                search_paths = [search_path]
            else:
                search_paths = []
        elif agent_id:
            agent_path = self.base_dir / agent_id
            if agent_path.exists():
                search_paths = [p for p in agent_path.iterdir() if p.is_dir()]
            else:
                search_paths = []
        else:
            # Search all
            search_paths = []
            for agent_dir in self.base_dir.iterdir():
                if agent_dir.is_dir():
                    for run_dir in agent_dir.iterdir():
                        if run_dir.is_dir():
                            search_paths.append(run_dir)
        
        # Search for artifacts
        for dir_path in search_paths:
            for meta_file in dir_path.glob("*.meta.json"):
                try:
                    meta_data = json.loads(meta_file.read_text())
                    
                    # Apply tool_name filter if specified
                    if tool_name and meta_data.get("tool_name") != tool_name:
                        continue
                    
                    # Reconstruct artifact path
                    artifact_file = meta_file.with_suffix("").with_suffix(".artifact")
                    if not artifact_file.exists():
                        continue
                    
                    # Create ArtifactRef
                    ref = ArtifactRef(
                        path=str(artifact_file),
                        summary="",  # Not stored in meta, would need to regenerate
                        size_bytes=meta_data.get("size_bytes", 0),
                        mime_type=meta_data.get("mime_type", "application/octet-stream"),
                        checksum=meta_data.get("checksum", ""),
                        created_at=meta_data.get("created_at", 0),
                        artifact_id=artifact_file.stem,
                        agent_id=meta_data.get("agent_id", ""),
                        run_id=meta_data.get("run_id", ""),
                        tool_name=meta_data.get("tool_name"),
                        turn_id=meta_data.get("turn_id", 0),
                    )
                    artifacts.append(ref)
                except Exception as e:
                    logging.debug(f"Error loading artifact metadata from {meta_file}: {e}")
        
        # Sort by creation time (newest first)
        artifacts.sort(key=lambda x: x.created_at, reverse=True)
        
        return artifacts
    
    def cleanup_old_artifacts(self, days: Optional[int] = None) -> int:
        """
        Clean up artifacts older than retention period.
        
        Args:
            days: Days to retain (overrides default retention_days)
            
        Returns:
            Number of artifacts deleted
        """
        days = days or self.retention_days
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        deleted_count = 0
        
        for artifact in self.list_artifacts():
            if artifact.created_at < cutoff_time:
                if self.delete(artifact):
                    deleted_count += 1
                    logging.debug(f"Deleted old artifact {artifact.artifact_id}")
        
        return deleted_count