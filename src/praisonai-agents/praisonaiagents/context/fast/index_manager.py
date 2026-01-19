"""
Index manager for FastContext incremental indexing.

Provides file indexing for faster repeat searches:
- FileIndex: Lightweight file index with mtime tracking
- Incremental updates: Only rescan changed files
- Optional file watcher integration (watchfiles)

Design principles:
- Index stored as JSON for simplicity
- Lazy loading of optional dependencies
- No performance impact when disabled
"""

import os
import json
import hashlib
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Optional, Set, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Lazy availability check for watchfiles
_WATCHFILES_AVAILABLE: Optional[bool] = None


def _check_watchfiles() -> bool:
    """Lazy check for watchfiles availability."""
    global _WATCHFILES_AVAILABLE
    if _WATCHFILES_AVAILABLE is None:
        try:
            import watchfiles  # noqa: F401
            _WATCHFILES_AVAILABLE = True
        except ImportError:
            _WATCHFILES_AVAILABLE = False
    return _WATCHFILES_AVAILABLE


@dataclass
class FileEntry:
    """Entry for a single file in the index."""
    path: str
    mtime: float  # Modification time
    size: int
    content_hash: Optional[str] = None  # Optional for large files
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileEntry":
        return cls(**data)


@dataclass  
class FileIndex:
    """Lightweight file index for incremental search.
    
    Tracks file modification times to avoid rescanning
    unchanged files on repeat searches.
    
    Attributes:
        workspace_path: Root directory being indexed
        index_version: Version for format compatibility
    """
    
    INDEX_VERSION = 1
    INDEX_FILENAME = ".fast_context_index.json"
    
    workspace_path: str
    entries: Dict[str, FileEntry] = field(default_factory=dict)
    index_version: int = INDEX_VERSION
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def index_path(self) -> str:
        """Path to the index file."""
        return os.path.join(self.workspace_path, self.INDEX_FILENAME)
    
    def needs_rescan(self, filepath: str) -> bool:
        """Check if file needs rescan based on mtime.
        
        Args:
            filepath: Absolute path to file
            
        Returns:
            True if file needs rescan (new, modified, or not indexed)
        """
        rel_path = os.path.relpath(filepath, self.workspace_path)
        
        if rel_path not in self.entries:
            return True
        
        entry = self.entries[rel_path]
        
        try:
            stat = os.stat(filepath)
            return stat.st_mtime != entry.mtime or stat.st_size != entry.size
        except OSError:
            return True
    
    def update(self, filepath: str, content_hash: Optional[str] = None) -> None:
        """Update index entry for file.
        
        Args:
            filepath: Absolute path to file
            content_hash: Optional hash of file content
        """
        rel_path = os.path.relpath(filepath, self.workspace_path)
        
        try:
            stat = os.stat(filepath)
            self.entries[rel_path] = FileEntry(
                path=rel_path,
                mtime=stat.st_mtime,
                size=stat.st_size,
                content_hash=content_hash
            )
            self.updated_at = datetime.now().isoformat()
        except OSError as e:
            logger.debug(f"Failed to update index for {filepath}: {e}")
    
    def remove(self, filepath: str) -> None:
        """Remove file from index.
        
        Args:
            filepath: Absolute or relative path
        """
        rel_path = os.path.relpath(filepath, self.workspace_path) if os.path.isabs(filepath) else filepath
        self.entries.pop(rel_path, None)
        self.updated_at = datetime.now().isoformat()
    
    def get_changed_files(self, filepaths: List[str]) -> List[str]:
        """Get list of files that need rescan.
        
        Args:
            filepaths: List of absolute file paths
            
        Returns:
            List of files that need rescan
        """
        return [fp for fp in filepaths if self.needs_rescan(fp)]
    
    def save(self) -> bool:
        """Save index to disk.
        
        Returns:
            True if saved successfully
        """
        try:
            data = {
                "version": self.index_version,
                "workspace": self.workspace_path,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "entries": {k: v.to_dict() for k, v in self.entries.items()}
            }
            
            with open(self.index_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            return True
        except Exception as e:
            logger.warning(f"Failed to save index: {e}")
            return False
    
    @classmethod
    def load(cls, workspace_path: str) -> Optional["FileIndex"]:
        """Load index from disk.
        
        Args:
            workspace_path: Root directory
            
        Returns:
            FileIndex if loaded, None if not found or invalid
        """
        index_path = os.path.join(workspace_path, cls.INDEX_FILENAME)
        
        if not os.path.exists(index_path):
            return None
        
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Version check
            if data.get("version") != cls.INDEX_VERSION:
                logger.info("Index version mismatch, will rebuild")
                return None
            
            entries = {
                k: FileEntry.from_dict(v) 
                for k, v in data.get("entries", {}).items()
            }
            
            return cls(
                workspace_path=workspace_path,
                entries=entries,
                index_version=data.get("version", cls.INDEX_VERSION),
                created_at=data.get("created_at", datetime.now().isoformat()),
                updated_at=data.get("updated_at", datetime.now().isoformat())
            )
        except Exception as e:
            logger.warning(f"Failed to load index: {e}")
            return None
    
    @classmethod
    def load_or_create(cls, workspace_path: str) -> "FileIndex":
        """Load existing index or create new one.
        
        Args:
            workspace_path: Root directory
            
        Returns:
            FileIndex instance
        """
        index = cls.load(workspace_path)
        if index is None:
            index = cls(workspace_path=workspace_path)
        return index
    
    def clear(self) -> None:
        """Clear all index entries."""
        self.entries.clear()
        self.updated_at = datetime.now().isoformat()
    
    def __len__(self) -> int:
        return len(self.entries)


class IndexWatcher:
    """Optional file watcher for real-time index updates.
    
    Uses watchfiles if available, otherwise disabled.
    """
    
    def __init__(self, index: FileIndex):
        self.index = index
        self._watching = False
    
    def is_available(self) -> bool:
        """Check if file watching is available."""
        return _check_watchfiles()
    
    async def start(self) -> None:
        """Start watching for file changes."""
        if not self.is_available():
            logger.warning("watchfiles not available, file watching disabled")
            return
        
        if self._watching:
            return
        
        import watchfiles
        self._watching = True
        
        async for changes in watchfiles.awatch(self.index.workspace_path):
            for change_type, path in changes:
                if change_type == watchfiles.Change.deleted:
                    self.index.remove(path)
                else:
                    self.index.update(path)
    
    def stop(self) -> None:
        """Stop watching."""
        self._watching = False


def is_watchfiles_available() -> bool:
    """Check if watchfiles is available for file watching.
    
    Returns:
        True if watchfiles is installed
    """
    return _check_watchfiles()
