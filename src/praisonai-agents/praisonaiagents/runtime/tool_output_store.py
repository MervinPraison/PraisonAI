"""
Tool Output Store for persisting full tool outputs.

Provides overflow-safe storage of large tool outputs with bounded inline previews
and persistent full results. Manages TTL-based cleanup and run-scoped isolation.
"""

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import uuid4

from ..paths import get_cache_dir, ensure_dir


class ToolOutputStore:
    """Manages persistent storage of full tool outputs with TTL cleanup."""
    
    DEFAULT_RETENTION_HOURS = 24
    
    def __init__(self, run_id: Optional[str] = None, retention_hours: Optional[int] = None):
        """
        Initialize the tool output store.
        
        Args:
            run_id: Unique identifier for the run (auto-generated if not provided)
            retention_hours: How long to retain outputs (default 24 hours)
        """
        self.run_id = run_id or str(uuid4())
        self.retention_hours = retention_hours or int(
            os.environ.get('PRAISONAI_TOOL_OUTPUT_RETENTION_HOURS', self.DEFAULT_RETENTION_HOURS)
        )
        
        # Store outputs under cache dir (disposable data)
        self.store_dir = ensure_dir(get_cache_dir() / "tool_outputs" / self.run_id)
        self._call_counter = 0
        
        # Clean up old runs on initialization
        self._cleanup_old_runs()
    
    def store(self, tool_name: str, output: str, call_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Store full tool output and return reference info.
        
        Args:
            tool_name: Name of the tool that produced the output
            output: Full output text to store
            call_id: Optional unique identifier for this call
            
        Returns:
            Dictionary with storage metadata:
                - path: Path to stored output file
                - size: Total size in bytes
                - tool: Tool name
                - call_id: Unique call identifier
        """
        if call_id is None:
            self._call_counter += 1
            call_id = f"{tool_name}_{self._call_counter}_{int(time.time())}"
        
        # Sanitize filename
        safe_call_id = "".join(c if c.isalnum() or c in "_-" else "_" for c in call_id)
        output_path = self.store_dir / f"{safe_call_id}.txt"
        
        try:
            output_path.write_text(output, encoding='utf-8')
            
            return {
                'path': str(output_path),
                'size': len(output),
                'tool': tool_name,
                'call_id': call_id,
                'timestamp': time.time()
            }
        except Exception as e:
            logging.warning(f"Failed to store tool output: {e}")
            return {}
    
    def retrieve(self, path_or_metadata: Any) -> Optional[str]:
        """
        Retrieve stored tool output.
        
        Args:
            path_or_metadata: Either a file path string or metadata dict with 'path'
            
        Returns:
            Full output text or None if not found
        """
        try:
            if isinstance(path_or_metadata, dict):
                path = path_or_metadata.get('path')
            else:
                path = path_or_metadata
            
            if path and Path(path).exists():
                return Path(path).read_text(encoding='utf-8')
        except Exception as e:
            logging.debug(f"Failed to retrieve tool output: {e}")
        
        return None
    
    def _cleanup_old_runs(self):
        """Remove run directories older than retention period."""
        try:
            tool_outputs_dir = get_cache_dir() / "tool_outputs"
            if not tool_outputs_dir.exists():
                return
            
            cutoff_time = time.time() - (self.retention_hours * 3600)
            
            for run_dir in tool_outputs_dir.iterdir():
                if run_dir.is_dir():
                    # Check directory modification time
                    if run_dir.stat().st_mtime < cutoff_time:
                        try:
                            shutil.rmtree(run_dir)
                            logging.debug(f"Cleaned up old tool output dir: {run_dir.name}")
                        except Exception as e:
                            logging.debug(f"Failed to clean up {run_dir}: {e}")
        except Exception as e:
            logging.debug(f"Error during tool output cleanup: {e}")
    
    def format_reference(self, metadata: Dict[str, Any], truncated_preview: str) -> str:
        """
        Format a reference to stored output within the truncated preview.
        
        Args:
            metadata: Storage metadata from store()
            truncated_preview: The head/tail truncated text
            
        Returns:
            Formatted text with reference to full output
        """
        if not metadata or 'path' not in metadata:
            return truncated_preview
        
        # Insert reference info into the truncation marker
        path = metadata['path']
        size = metadata.get('size', 0)
        
        # Find the truncation marker and enhance it
        marker_start = "...["
        marker_end = "]..."
        
        if marker_start in truncated_preview and marker_end in truncated_preview:
            # Replace the existing marker with enhanced version
            import re
            pattern = r'\.\.\.\[([^\]]+)\]\.\.\.'
            replacement = f"...[\\1 | Full output stored at: {path}]..."
            return re.sub(pattern, replacement, truncated_preview, count=1)
        else:
            # Append reference if no marker found
            return f"{truncated_preview}\n[Full output ({size:,} bytes) available at: {path}]"


# Global instance management
_store_instance: Optional[ToolOutputStore] = None


def get_tool_output_store(run_id: Optional[str] = None) -> ToolOutputStore:
    """
    Get or create the global tool output store instance.
    
    Args:
        run_id: Run identifier (uses existing if already initialized)
        
    Returns:
        ToolOutputStore instance
    """
    global _store_instance
    if _store_instance is None or (run_id and run_id != _store_instance.run_id):
        _store_instance = ToolOutputStore(run_id)
    return _store_instance


def reset_tool_output_store():
    """Reset the global store instance. Mainly for testing."""
    global _store_instance
    _store_instance = None