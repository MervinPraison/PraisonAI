"""
File Indexer for Fast Context.

Provides file indexing capabilities for faster code search:
- Indexes file paths and metadata
- Supports .gitignore and .praisonignore patterns
- Incremental updates on file changes
- Memory-efficient storage
"""

import os
import fnmatch
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Set, Optional, Any
from pathlib import Path
import time

logger = logging.getLogger(__name__)


@dataclass
class FileInfo:
    """Information about an indexed file.
    
    Attributes:
        path: Relative path from workspace root
        absolute_path: Absolute file path
        size: File size in bytes
        modified: Last modification timestamp
        extension: File extension (lowercase)
        hash: Content hash for change detection
    """
    path: str
    absolute_path: str
    size: int
    modified: float
    extension: str
    hash: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "path": self.path,
            "absolute_path": self.absolute_path,
            "size": self.size,
            "modified": self.modified,
            "extension": self.extension,
            "hash": self.hash
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileInfo":
        """Create from dictionary."""
        return cls(**data)


class FileIndexer:
    """Indexes files in a workspace for fast search.
    
    The indexer maintains an in-memory index of files that can be
    used to quickly find files by pattern without filesystem traversal.
    
    Attributes:
        workspace_path: Root directory to index
        files: Dictionary mapping relative paths to FileInfo
        extensions: Set of indexed file extensions
    """
    
    # Default extensions to index
    DEFAULT_EXTENSIONS = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
        ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
        ".kt", ".scala", ".r", ".m", ".mm", ".sql", ".sh", ".bash",
        ".yaml", ".yml", ".json", ".xml", ".html", ".css", ".scss",
        ".md", ".txt", ".rst", ".toml", ".ini", ".cfg", ".conf"
    }
    
    # Default patterns to ignore
    DEFAULT_IGNORE_PATTERNS = {
        "__pycache__", "*.pyc", "*.pyo", ".git", ".svn", ".hg",
        "node_modules", "venv", ".venv", "env", ".env",
        "dist", "build", ".cache", ".pytest_cache",
        "*.egg-info", "*.egg", "*.whl", "*.so", "*.dll", "*.dylib"
    }
    
    def __init__(
        self,
        workspace_path: str,
        extensions: Optional[Set[str]] = None,
        ignore_patterns: Optional[Set[str]] = None,
        respect_gitignore: bool = True,
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
        compute_hashes: bool = False
    ):
        """Initialize file indexer.
        
        Args:
            workspace_path: Root directory to index
            extensions: File extensions to index (None = all text files)
            ignore_patterns: Patterns to ignore
            respect_gitignore: Whether to respect .gitignore
            max_file_size: Maximum file size to index
            compute_hashes: Whether to compute content hashes
        """
        self.workspace_path = os.path.abspath(workspace_path)
        self.extensions = extensions or self.DEFAULT_EXTENSIONS
        self.ignore_patterns = ignore_patterns or self.DEFAULT_IGNORE_PATTERNS.copy()
        self.respect_gitignore = respect_gitignore
        self.max_file_size = max_file_size
        self.compute_hashes = compute_hashes
        
        # Index storage
        self.files: Dict[str, FileInfo] = {}
        self.by_extension: Dict[str, List[str]] = {}
        
        # Gitignore patterns
        self._gitignore_patterns: Set[str] = set()
        
        # Index metadata
        self.last_indexed: Optional[float] = None
        self.total_files: int = 0
        self.total_size: int = 0
    
    def _load_gitignore(self) -> None:
        """Load patterns from .gitignore and .praisonignore."""
        self._gitignore_patterns.clear()
        
        for filename in [".gitignore", ".praisonignore"]:
            filepath = os.path.join(self.workspace_path, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                self._gitignore_patterns.add(line)
                except Exception:
                    pass
    
    def _should_ignore(self, path: str, is_dir: bool = False) -> bool:
        """Check if a path should be ignored.
        
        Args:
            path: Relative path from workspace
            is_dir: Whether the path is a directory
            
        Returns:
            True if path should be ignored
        """
        name = os.path.basename(path)
        parts = Path(path).parts
        
        # Check default ignore patterns
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
            if any(fnmatch.fnmatch(part, pattern) for part in parts):
                return True
        
        # Check gitignore patterns
        if self.respect_gitignore:
            for pattern in self._gitignore_patterns:
                # Handle directory patterns
                if pattern.endswith('/'):
                    dir_pattern = pattern.rstrip('/')
                    if is_dir and fnmatch.fnmatch(name, dir_pattern):
                        return True
                    if any(fnmatch.fnmatch(part, dir_pattern) for part in parts):
                        return True
                # Handle ** patterns
                elif '**' in pattern:
                    fnmatch_pattern = pattern.replace('**/', '*').replace('**', '*')
                    if fnmatch.fnmatch(path, fnmatch_pattern):
                        return True
                # Handle simple patterns
                else:
                    if fnmatch.fnmatch(name, pattern):
                        return True
                    if fnmatch.fnmatch(path, pattern):
                        return True
        
        return False
    
    def _compute_hash(self, filepath: str) -> Optional[str]:
        """Compute MD5 hash of file content.
        
        Args:
            filepath: Path to file
            
        Returns:
            MD5 hash string or None on error
        """
        if not self.compute_hashes:
            return None
        
        try:
            hasher = hashlib.md5()
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return None
    
    def index(self) -> int:
        """Index all files in the workspace.
        
        Returns:
            Number of files indexed
        """
        start_time = time.perf_counter()
        
        # Load gitignore patterns
        if self.respect_gitignore:
            self._load_gitignore()
        
        # Clear existing index
        self.files.clear()
        self.by_extension.clear()
        self.total_files = 0
        self.total_size = 0
        
        # Walk directory tree
        for root, dirs, files in os.walk(self.workspace_path):
            # Get relative path
            rel_root = os.path.relpath(root, self.workspace_path)
            if rel_root == '.':
                rel_root = ''
            
            # Filter directories in-place
            dirs[:] = [d for d in dirs if not self._should_ignore(
                os.path.join(rel_root, d) if rel_root else d, is_dir=True
            )]
            
            for filename in files:
                rel_path = os.path.join(rel_root, filename) if rel_root else filename
                abs_path = os.path.join(root, filename)
                
                # Check if should ignore
                if self._should_ignore(rel_path):
                    continue
                
                # Check extension
                ext = os.path.splitext(filename)[1].lower()
                if self.extensions and ext not in self.extensions:
                    continue
                
                try:
                    stat = os.stat(abs_path)
                    
                    # Check file size
                    if stat.st_size > self.max_file_size:
                        continue
                    
                    # Create file info
                    file_info = FileInfo(
                        path=rel_path,
                        absolute_path=abs_path,
                        size=stat.st_size,
                        modified=stat.st_mtime,
                        extension=ext,
                        hash=self._compute_hash(abs_path)
                    )
                    
                    # Add to index
                    self.files[rel_path] = file_info
                    
                    # Add to extension index
                    if ext not in self.by_extension:
                        self.by_extension[ext] = []
                    self.by_extension[ext].append(rel_path)
                    
                    self.total_files += 1
                    self.total_size += stat.st_size
                    
                except Exception as e:
                    logger.debug(f"Error indexing {abs_path}: {e}")
                    continue
        
        self.last_indexed = time.perf_counter()
        elapsed = self.last_indexed - start_time
        
        logger.info(f"Indexed {self.total_files} files ({self.total_size / 1024 / 1024:.2f} MB) in {elapsed:.2f}s")
        
        return self.total_files
    
    def find_by_pattern(self, pattern: str) -> List[FileInfo]:
        """Find files matching a glob pattern.
        
        Args:
            pattern: Glob pattern (e.g., "**/*.py", "src/*.js")
            
        Returns:
            List of matching FileInfo objects
        """
        results = []
        
        for rel_path, file_info in self.files.items():
            if fnmatch.fnmatch(rel_path, pattern):
                results.append(file_info)
            elif fnmatch.fnmatch(os.path.basename(rel_path), pattern):
                results.append(file_info)
        
        return results
    
    def find_by_extension(self, extension: str) -> List[FileInfo]:
        """Find files by extension.
        
        Args:
            extension: File extension (with or without dot)
            
        Returns:
            List of matching FileInfo objects
        """
        if not extension.startswith('.'):
            extension = '.' + extension
        extension = extension.lower()
        
        paths = self.by_extension.get(extension, [])
        return [self.files[p] for p in paths if p in self.files]
    
    def find_by_name(self, name: str, exact: bool = False) -> List[FileInfo]:
        """Find files by name.
        
        Args:
            name: Filename to search for
            exact: If True, match exact name; otherwise, partial match
            
        Returns:
            List of matching FileInfo objects
        """
        results = []
        name_lower = name.lower()
        
        for rel_path, file_info in self.files.items():
            filename = os.path.basename(rel_path).lower()
            if exact:
                if filename == name_lower:
                    results.append(file_info)
            else:
                if name_lower in filename:
                    results.append(file_info)
        
        return results
    
    def get_file(self, path: str) -> Optional[FileInfo]:
        """Get file info by path.
        
        Args:
            path: Relative path from workspace
            
        Returns:
            FileInfo or None if not found
        """
        return self.files.get(path)
    
    def is_stale(self, max_age: float = 60.0) -> bool:
        """Check if index is stale.
        
        Args:
            max_age: Maximum age in seconds
            
        Returns:
            True if index is stale or not indexed
        """
        if self.last_indexed is None:
            return True
        return (time.perf_counter() - self.last_indexed) > max_age
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics.
        
        Returns:
            Dictionary with index stats
        """
        return {
            "workspace_path": self.workspace_path,
            "total_files": self.total_files,
            "total_size_bytes": self.total_size,
            "total_size_mb": round(self.total_size / 1024 / 1024, 2),
            "extensions": dict(sorted(
                ((ext, len(paths)) for ext, paths in self.by_extension.items()),
                key=lambda x: x[1],
                reverse=True
            )),
            "last_indexed": self.last_indexed
        }
    
    def save_index(self, filepath: str) -> None:
        """Save index to file.
        
        Args:
            filepath: Path to save index
        """
        data = {
            "workspace_path": self.workspace_path,
            "last_indexed": self.last_indexed,
            "files": {path: info.to_dict() for path, info in self.files.items()}
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def load_index(self, filepath: str) -> bool:
        """Load index from file.
        
        Args:
            filepath: Path to load index from
            
        Returns:
            True if loaded successfully
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Verify workspace path matches
            if data.get("workspace_path") != self.workspace_path:
                return False
            
            self.last_indexed = data.get("last_indexed")
            self.files.clear()
            self.by_extension.clear()
            self.total_files = 0
            self.total_size = 0
            
            for path, info_dict in data.get("files", {}).items():
                file_info = FileInfo.from_dict(info_dict)
                self.files[path] = file_info
                
                ext = file_info.extension
                if ext not in self.by_extension:
                    self.by_extension[ext] = []
                self.by_extension[ext].append(path)
                
                self.total_files += 1
                self.total_size += file_info.size
            
            return True
        except Exception as e:
            logger.debug(f"Error loading index: {e}")
            return False
