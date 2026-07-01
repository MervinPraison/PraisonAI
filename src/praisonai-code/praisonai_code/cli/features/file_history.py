"""
File History and Undo System for PraisonAI CLI.

Provides file versioning for undo support during editing sessions.
"""

import os
import json
import hashlib
import shutil
import logging
import time
from typing import Optional, List, Dict
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_DIR = ".praison/history"
MAX_VERSIONS_PER_FILE = 50


@dataclass
class FileVersion:
    """Represents a single version of a file."""
    version_id: str
    file_path: str
    timestamp: float
    content_hash: str
    size: int
    session_id: str
    
    def to_dict(self) -> dict:
        return {
            "version_id": self.version_id,
            "file_path": self.file_path,
            "timestamp": self.timestamp,
            "content_hash": self.content_hash,
            "size": self.size,
            "session_id": self.session_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "FileVersion":
        return cls(**data)


class FileHistoryManager:
    """
    Manages file history for undo support.
    
    Stores file versions before edits to enable undo operations.
    Session-scoped with configurable retention.
    
    Usage:
        manager = FileHistoryManager()
        
        # Before editing
        version_id = manager.record_before_edit("file.py", session_id="session-1")
        
        # After editing, if undo needed
        manager.undo("file.py", session_id="session-1")
    """
    
    def __init__(
        self,
        storage_dir: Optional[str] = None,
        max_versions: int = MAX_VERSIONS_PER_FILE,
    ):
        self.storage_dir = storage_dir or os.path.expanduser(f"~/{DEFAULT_HISTORY_DIR}")
        self.max_versions = max_versions
        self._index: Dict[str, List[FileVersion]] = {}
        self._ensure_storage()
        self._load_index()
    
    def _ensure_storage(self) -> None:
        """Ensure storage directory exists."""
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(os.path.join(self.storage_dir, "versions"), exist_ok=True)
    
    def _get_index_path(self) -> str:
        """Get path to the index file."""
        return os.path.join(self.storage_dir, "index.json")
    
    def _load_index(self) -> None:
        """Load the version index from disk."""
        index_path = self._get_index_path()
        if os.path.exists(index_path):
            try:
                with open(index_path, "r") as f:
                    data = json.load(f)
                    for file_path, versions in data.items():
                        self._index[file_path] = [
                            FileVersion.from_dict(v) for v in versions
                        ]
            except Exception as e:
                logger.warning(f"Failed to load history index: {e}")
                self._index = {}
    
    def _save_index(self) -> None:
        """Save the version index to disk."""
        index_path = self._get_index_path()
        data = {
            file_path: [v.to_dict() for v in versions]
            for file_path, versions in self._index.items()
        }
        with open(index_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def _generate_version_id(self) -> str:
        """Generate a unique version ID."""
        return f"v_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
    
    def _get_content_hash(self, content: bytes) -> str:
        """Get hash of file content."""
        return hashlib.sha256(content).hexdigest()[:16]
    
    def _get_version_path(self, version_id: str) -> str:
        """Get path to store a version's content."""
        return os.path.join(self.storage_dir, "versions", f"{version_id}.bak")
    
    def record_before_edit(
        self,
        file_path: str,
        session_id: str,
    ) -> Optional[str]:
        """
        Record file state before an edit.
        
        Args:
            file_path: Path to the file being edited
            session_id: Current session ID
            
        Returns:
            Version ID if successful, None if file doesn't exist
        """
        if not os.path.exists(file_path):
            return None
        
        try:
            # Read current content
            with open(file_path, "rb") as f:
                content = f.read()
            
            # Generate version info
            version_id = self._generate_version_id()
            content_hash = self._get_content_hash(content)
            
            # Check if content is same as last version (skip if unchanged)
            if file_path in self._index and self._index[file_path]:
                last_version = self._index[file_path][-1]
                if last_version.content_hash == content_hash:
                    return last_version.version_id
            
            # Save content
            version_path = self._get_version_path(version_id)
            with open(version_path, "wb") as f:
                f.write(content)
            
            # Create version record
            version = FileVersion(
                version_id=version_id,
                file_path=os.path.abspath(file_path),
                timestamp=time.time(),
                content_hash=content_hash,
                size=len(content),
                session_id=session_id,
            )
            
            # Add to index
            if file_path not in self._index:
                self._index[file_path] = []
            self._index[file_path].append(version)
            
            # Trim old versions
            self._trim_versions(file_path)
            
            # Save index
            self._save_index()
            
            logger.debug(f"Recorded version {version_id} for {file_path}")
            return version_id
            
        except Exception as e:
            logger.error(f"Failed to record file version: {e}")
            return None
    
    def _trim_versions(self, file_path: str) -> None:
        """Remove old versions beyond max limit."""
        if file_path not in self._index:
            return
            
        versions = self._index[file_path]
        while len(versions) > self.max_versions:
            old_version = versions.pop(0)
            version_path = self._get_version_path(old_version.version_id)
            try:
                os.remove(version_path)
            except OSError:
                pass
    
    def undo(
        self,
        file_path: str,
        session_id: Optional[str] = None,
        version_id: Optional[str] = None,
    ) -> bool:
        """
        Undo to a previous version.
        
        Args:
            file_path: Path to the file to restore
            session_id: Optional session ID to filter versions
            version_id: Optional specific version to restore
            
        Returns:
            True if successful, False otherwise
        """
        if file_path not in self._index or not self._index[file_path]:
            logger.warning(f"No history found for {file_path}")
            return False
        
        versions = self._index[file_path]
        
        # Find version to restore
        target_version = None
        
        if version_id:
            # Find specific version
            for v in versions:
                if v.version_id == version_id:
                    target_version = v
                    break
        elif session_id:
            # Find last version from session
            for v in reversed(versions):
                if v.session_id == session_id:
                    target_version = v
                    break
        else:
            # Use last version
            target_version = versions[-1]
        
        if not target_version:
            logger.warning(f"No matching version found for {file_path}")
            return False
        
        # Restore content
        version_path = self._get_version_path(target_version.version_id)
        if not os.path.exists(version_path):
            logger.error(f"Version file not found: {version_path}")
            return False
        
        try:
            shutil.copy2(version_path, file_path)
            logger.info(f"Restored {file_path} to version {target_version.version_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore file: {e}")
            return False
    
    def get_versions(
        self,
        file_path: str,
        session_id: Optional[str] = None,
    ) -> List[FileVersion]:
        """Get all versions for a file."""
        if file_path not in self._index:
            return []
        
        versions = self._index[file_path]
        
        if session_id:
            versions = [v for v in versions if v.session_id == session_id]
        
        return versions
    
    def clear_session(self, session_id: str) -> int:
        """Clear all versions for a session. Returns count of cleared versions."""
        cleared = 0
        
        for file_path in list(self._index.keys()):
            versions = self._index[file_path]
            remaining = []
            
            for v in versions:
                if v.session_id == session_id:
                    version_path = self._get_version_path(v.version_id)
                    try:
                        os.remove(version_path)
                    except OSError:
                        pass
                    cleared += 1
                else:
                    remaining.append(v)
            
            if remaining:
                self._index[file_path] = remaining
            else:
                del self._index[file_path]
        
        self._save_index()
        return cleared
    
    def clear_all(self) -> int:
        """Clear all history. Returns count of cleared versions."""
        cleared = 0
        
        for versions in self._index.values():
            for v in versions:
                version_path = self._get_version_path(v.version_id)
                try:
                    os.remove(version_path)
                    cleared += 1
                except OSError:
                    pass
        
        self._index.clear()
        self._save_index()
        return cleared
