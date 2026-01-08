"""
Incremental Indexing Infrastructure for PraisonAI Agents.

Provides:
- CorpusStats: Statistics about indexed corpus
- IndexResult: Result of indexing operation
- IgnoreMatcher: .praisonignore pattern matching
- FileTracker: File hash/mtime tracking for incremental updates

No heavy imports - only stdlib.
"""

import fnmatch
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


# Strategy thresholds based on corpus size
STRATEGY_THRESHOLDS = {
    10: "direct",        # < 10 files: load all
    100: "basic",        # < 100 files: semantic search only
    1000: "hybrid",      # < 1000 files: keyword + semantic
    10000: "reranked",   # < 10000 files: hybrid + rerank
    100000: "compressed", # < 100000 files: reranked + compression
}
DEFAULT_STRATEGY = "hierarchical"  # > 100000 files


def estimate_tokens_simple(text: str) -> int:
    """Simple token estimation (~4 chars per token)."""
    if not text:
        return 0
    return len(text) // 4 + 1


@dataclass
class CorpusStats:
    """
    Statistics about an indexed corpus.
    
    Used for strategy selection and monitoring.
    
    Attributes:
        file_count: Number of files in corpus
        chunk_count: Number of chunks created
        total_tokens: Estimated total tokens
        indexed_at: Timestamp of last indexing
        path: Path to corpus root
        strategy_recommendation: Recommended retrieval strategy
    """
    file_count: int = 0
    chunk_count: int = 0
    total_tokens: int = 0
    indexed_at: Optional[str] = None
    path: Optional[str] = None
    
    @property
    def strategy_recommendation(self) -> str:
        """Recommend retrieval strategy based on corpus size."""
        for threshold, strategy in sorted(STRATEGY_THRESHOLDS.items()):
            if self.file_count < threshold:
                return strategy
        return DEFAULT_STRATEGY
    
    @classmethod
    def from_directory(
        cls,
        path: str,
        extensions: Optional[List[str]] = None,
    ) -> "CorpusStats":
        """
        Create CorpusStats from directory scan.
        
        Args:
            path: Directory path to scan
            extensions: Optional list of extensions to include
            
        Returns:
            CorpusStats with file count and token estimate
        """
        if extensions is None:
            extensions = [
                ".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
                ".html", ".css", ".csv", ".xml", ".rst", ".pdf", ".docx",
            ]
        
        file_count = 0
        total_tokens = 0
        
        for root, _, files in os.walk(path):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext in extensions:
                    file_count += 1
                    filepath = os.path.join(root, filename)
                    try:
                        size = os.path.getsize(filepath)
                        # Rough estimate: 4 chars per token
                        total_tokens += size // 4
                    except OSError:
                        pass
        
        return cls(
            file_count=file_count,
            total_tokens=total_tokens,
            path=path,
            indexed_at=datetime.now().isoformat(),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_count": self.file_count,
            "chunk_count": self.chunk_count,
            "total_tokens": self.total_tokens,
            "indexed_at": self.indexed_at,
            "path": self.path,
            "strategy_recommendation": self.strategy_recommendation,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CorpusStats":
        """Create from dictionary."""
        return cls(
            file_count=data.get("file_count", 0),
            chunk_count=data.get("chunk_count", 0),
            total_tokens=data.get("total_tokens", 0),
            indexed_at=data.get("indexed_at"),
            path=data.get("path"),
        )


@dataclass
class IndexResult:
    """
    Result of an indexing operation.
    
    Attributes:
        success: Whether indexing succeeded
        files_indexed: Number of files indexed
        files_skipped: Number of files skipped (unchanged)
        chunks_created: Number of chunks created
        errors: List of error messages
        duration_seconds: Time taken for indexing
        corpus_stats: Stats about the indexed corpus
    """
    success: bool = True
    files_indexed: int = 0
    files_skipped: int = 0
    chunks_created: int = 0
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    corpus_stats: Optional[CorpusStats] = None
    
    @property
    def total_files(self) -> int:
        """Total files processed (indexed + skipped)."""
        return self.files_indexed + self.files_skipped
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "files_indexed": self.files_indexed,
            "files_skipped": self.files_skipped,
            "chunks_created": self.chunks_created,
            "total_files": self.total_files,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
            "corpus_stats": self.corpus_stats.to_dict() if self.corpus_stats else None,
        }


class IgnoreMatcher:
    """
    Matcher for .praisonignore patterns.
    
    Supports gitignore-style patterns:
    - * matches any sequence of characters
    - ** matches any path segments
    - ! negates a pattern
    - # starts a comment
    """
    
    def __init__(self, patterns: Optional[List[str]] = None):
        """
        Initialize with patterns.
        
        Args:
            patterns: List of gitignore-style patterns
        """
        self._include_patterns: List[str] = []
        self._exclude_patterns: List[str] = []
        
        if patterns:
            for pattern in patterns:
                pattern = pattern.strip()
                if not pattern or pattern.startswith("#"):
                    continue
                if pattern.startswith("!"):
                    self._include_patterns.append(pattern[1:])
                else:
                    self._exclude_patterns.append(pattern)
    
    def should_ignore(self, path: str) -> bool:
        """
        Check if path should be ignored.
        
        Args:
            path: Path to check (relative or absolute)
            
        Returns:
            True if path should be ignored
        """
        # Normalize path
        path = path.replace("\\", "/")
        basename = os.path.basename(path)
        
        # Check exclude patterns
        ignored = False
        for pattern in self._exclude_patterns:
            if self._matches(path, pattern) or self._matches(basename, pattern):
                ignored = True
                break
        
        # Check include patterns (negation)
        if ignored:
            for pattern in self._include_patterns:
                if self._matches(path, pattern) or self._matches(basename, pattern):
                    return False
        
        return ignored
    
    def _matches(self, path: str, pattern: str) -> bool:
        """Check if path matches pattern."""
        # Handle ** for recursive matching
        if "**" in pattern:
            # Convert gitignore pattern to regex
            # First escape special regex chars except * and /
            regex_pattern = re.escape(pattern)
            # Restore * and convert to regex
            regex_pattern = regex_pattern.replace(r"\*\*", ".*")
            regex_pattern = regex_pattern.replace(r"\*", "[^/]*")
            # Match anywhere in path
            try:
                return bool(re.search(regex_pattern, path))
            except re.error:
                return False
        
        # Handle trailing slash for directories
        if pattern.endswith("/"):
            pattern = pattern[:-1]
            return path == pattern or path.startswith(pattern + "/") or ("/" + pattern + "/") in ("/" + path + "/")
        
        # Standard fnmatch - check full path and basename
        if fnmatch.fnmatch(path, pattern):
            return True
        if fnmatch.fnmatch(os.path.basename(path), pattern):
            return True
        # Also check if pattern matches any path segment
        for segment in path.split("/"):
            if fnmatch.fnmatch(segment, pattern):
                return True
        return False
    
    @classmethod
    def from_file(cls, filepath: str) -> "IgnoreMatcher":
        """
        Load patterns from file.
        
        Args:
            filepath: Path to .praisonignore file
            
        Returns:
            IgnoreMatcher with loaded patterns
        """
        patterns = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                patterns = f.read().splitlines()
        except (OSError, IOError):
            pass
        return cls(patterns=patterns)
    
    @classmethod
    def from_directory(cls, directory: str) -> "IgnoreMatcher":
        """
        Auto-detect and load .praisonignore from directory.
        
        Also checks for .gitignore as fallback.
        
        Args:
            directory: Directory to search
            
        Returns:
            IgnoreMatcher with loaded patterns
        """
        patterns = []
        
        # Check for .praisonignore
        praison_ignore = os.path.join(directory, ".praisonignore")
        if os.path.exists(praison_ignore):
            try:
                with open(praison_ignore, "r", encoding="utf-8") as f:
                    patterns.extend(f.read().splitlines())
            except (OSError, IOError):
                pass
        
        # Also check .gitignore
        git_ignore = os.path.join(directory, ".gitignore")
        if os.path.exists(git_ignore):
            try:
                with open(git_ignore, "r", encoding="utf-8") as f:
                    patterns.extend(f.read().splitlines())
            except (OSError, IOError):
                pass
        
        return cls(patterns=patterns)


class FileTracker:
    """
    Track file hashes and modification times for incremental indexing.
    
    Persists state to a JSON file for cross-session tracking.
    """
    
    def __init__(self, state_file: Optional[str] = None):
        """
        Initialize tracker.
        
        Args:
            state_file: Path to state file for persistence
        """
        self._state_file = state_file
        self._tracked: Dict[str, Dict[str, Any]] = {}
    
    def get_file_info(self, filepath: str) -> Dict[str, Any]:
        """
        Get file information (hash, mtime, size).
        
        Args:
            filepath: Path to file
            
        Returns:
            Dict with path, hash, mtime, size
        """
        stat = os.stat(filepath)
        
        # Calculate hash for small files, use mtime+size for large files
        if stat.st_size < 1024 * 1024:  # 1MB
            with open(filepath, "rb") as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
        else:
            # For large files, use mtime + size as proxy
            file_hash = f"{stat.st_mtime}:{stat.st_size}"
        
        return {
            "path": filepath,
            "hash": file_hash,
            "mtime": stat.st_mtime,
            "size": stat.st_size,
        }
    
    def mark_indexed(self, filepath: str, info: Dict[str, Any]) -> None:
        """
        Mark file as indexed.
        
        Args:
            filepath: Path to file
            info: File info from get_file_info()
        """
        self._tracked[filepath] = info
    
    def has_changed(self, filepath: str) -> bool:
        """
        Check if file has changed since last indexing.
        
        Args:
            filepath: Path to file
            
        Returns:
            True if file is new or changed
        """
        if filepath not in self._tracked:
            return True
        
        try:
            current = self.get_file_info(filepath)
            tracked = self._tracked[filepath]
            
            # Compare hash
            if current["hash"] != tracked["hash"]:
                return True
            
            # Compare mtime as backup
            if current["mtime"] != tracked["mtime"]:
                return True
            
            return False
        except OSError:
            return True
    
    def save(self) -> None:
        """Save state to file."""
        if not self._state_file:
            return
        
        try:
            os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(self._tracked, f, indent=2)
        except (OSError, IOError):
            pass
    
    def load(self) -> None:
        """Load state from file."""
        if not self._state_file or not os.path.exists(self._state_file):
            return
        
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                self._tracked = json.load(f)
        except (OSError, IOError, json.JSONDecodeError):
            self._tracked = {}
    
    def clear(self) -> None:
        """Clear all tracked files."""
        self._tracked = {}
        if self._state_file and os.path.exists(self._state_file):
            try:
                os.remove(self._state_file)
            except OSError:
                pass
