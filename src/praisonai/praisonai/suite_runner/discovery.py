"""
Unified File Discovery for suite execution.

Provides common file discovery logic with filtering and grouping.
Used by both examples and docs runners.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import List, Optional, Set


class FileDiscovery:
    """
    Discovers files in a directory with filtering.
    
    Unified discovery for both examples and docs suites.
    """
    
    # Directories to always ignore
    IGNORE_DIRS: Set[str] = {
        '__pycache__', '.git', '.svn', '.hg',
        'venv', '.venv', 'env', '.env',
        'node_modules', '.tox', '.pytest_cache',
        '.mypy_cache', '.ruff_cache', 'dist', 'build',
        'egg-info', '.eggs', '.netlify',
    }
    
    def __init__(
        self,
        root: Path,
        extensions: Optional[List[str]] = None,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        ignore_underscore: bool = True,
    ):
        """
        Initialize discovery.
        
        Args:
            root: Root directory to search.
            extensions: File extensions to include (e.g., ['.py', '.md']).
            include_patterns: Glob patterns to include.
            exclude_patterns: Glob patterns to exclude.
            ignore_underscore: Skip files starting with underscore.
        """
        self.root = Path(root).resolve()
        self.extensions = extensions or ['.py']
        self.include_patterns = include_patterns or []
        self.exclude_patterns = exclude_patterns or []
        self.ignore_underscore = ignore_underscore
    
    def discover(self) -> List[Path]:
        """
        Discover all matching files, sorted deterministically.
        
        Returns:
            List of file paths.
        """
        files = []
        
        for ext in self.extensions:
            pattern = f"*{ext}" if not ext.startswith('*') else ext
            
            for path in self.root.rglob(pattern):
                if not path.is_file():
                    continue
                
                # Skip files starting with underscore
                if self.ignore_underscore and path.name.startswith('_'):
                    continue
                
                # Skip ignored directories
                rel_parts = path.relative_to(self.root).parts
                if any(
                    part in self.IGNORE_DIRS or 
                    part.endswith('.egg-info') or
                    part.startswith('.')
                    for part in rel_parts
                ):
                    continue
                
                # Apply include patterns (if any)
                rel_path = path.relative_to(self.root).as_posix()
                if self.include_patterns:
                    if not any(
                        fnmatch.fnmatch(rel_path, p) or 
                        fnmatch.fnmatch(path.name, p)
                        for p in self.include_patterns
                    ):
                        continue
                
                # Apply exclude patterns
                if self.exclude_patterns:
                    if any(fnmatch.fnmatch(rel_path, p) for p in self.exclude_patterns):
                        continue
                
                files.append(path)
        
        # Sort for deterministic order
        return sorted(files, key=lambda p: p.relative_to(self.root).as_posix())
    
    def discover_by_group(
        self,
        groups: Optional[List[str]] = None,
    ) -> dict:
        """
        Discover files grouped by top-level directory.
        
        Args:
            groups: Specific groups to include (None = all).
            
        Returns:
            Dict mapping group name to list of files.
        """
        all_files = self.discover()
        grouped = {}
        
        for path in all_files:
            rel_path = path.relative_to(self.root)
            
            # Get group (first directory component or 'root')
            if len(rel_path.parts) > 1:
                group = rel_path.parts[0]
            else:
                group = "root"
            
            # Filter by requested groups
            if groups and group not in groups:
                continue
            
            if group not in grouped:
                grouped[group] = []
            grouped[group].append(path)
        
        return grouped
    
    def get_groups(self) -> List[str]:
        """
        Get list of available groups (top-level directories).
        
        Returns:
            Sorted list of group names.
        """
        groups = set()
        
        for path in self.discover():
            rel_path = path.relative_to(self.root)
            if len(rel_path.parts) > 1:
                groups.add(rel_path.parts[0])
            else:
                groups.add("root")
        
        return sorted(groups)
    
    def discover_by_folder(
        self,
        folders: Optional[List[str]] = None,
    ) -> List[Path]:
        """
        Discover files in specific nested folders.
        
        Args:
            folders: Paths like 'examples/agent-recipes' to filter by.
            
        Returns:
            List of files that match any of the folder prefixes.
        """
        all_files = self.discover()
        if not folders:
            return all_files
        
        # Normalize folder paths
        normalized_folders = [f.rstrip('/').rstrip('\\') for f in folders]
        
        result = []
        for path in all_files:
            rel_path = path.relative_to(self.root).as_posix()
            for folder in normalized_folders:
                # Match if rel_path starts with folder/ or equals folder
                if rel_path.startswith(folder + '/') or rel_path == folder:
                    result.append(path)
                    break
        return result
    
    def get_folders(self, max_depth: int = 3) -> List[str]:
        """
        Get list of all available folders (including nested).
        
        Args:
            max_depth: Maximum folder depth to include.
            
        Returns:
            Sorted list of folder paths like 'examples/agent-recipes'.
        """
        folders = set()
        
        for path in self.discover():
            rel_path = path.relative_to(self.root)
            parts = rel_path.parts[:-1]  # Exclude filename
            
            # Add all folder levels up to max_depth
            for depth in range(1, min(len(parts) + 1, max_depth + 1)):
                folder_path = '/'.join(parts[:depth])
                if folder_path:
                    folders.add(folder_path)
        
        return sorted(folders)
    
    @staticmethod
    def get_group_for_path(path: Path, root: Path) -> str:
        """
        Get group name for a file path.
        
        Args:
            path: File path.
            root: Root directory.
            
        Returns:
            Group name (first directory or 'root').
        """
        try:
            rel_path = path.relative_to(root)
            if len(rel_path.parts) > 1:
                return rel_path.parts[0]
            return "root"
        except ValueError:
            return "unknown"


def get_pythonpath_for_dev(start_path: Path) -> List[str]:
    """
    Get PYTHONPATH additions for local package imports in dev mode.
    
    Searches up from start_path to find src/ directories.
    
    Args:
        start_path: Starting path to search from.
        
    Returns:
        List of paths to add to PYTHONPATH.
    """
    paths = []
    current = Path(start_path).resolve()
    
    for _ in range(10):  # Look up to 10 levels
        # Check for src directory
        src_dir = current / "src"
        if src_dir.exists():
            # Add all immediate subdirs of src
            for subdir in src_dir.iterdir():
                if subdir.is_dir() and not subdir.name.startswith('.'):
                    paths.append(str(subdir))
            break
        
        # Also check for common package directories
        for pkg in ["praisonai-agents", "praisonai"]:
            pkg_dir = current / "src" / pkg
            if pkg_dir.exists():
                paths.append(str(pkg_dir))
        
        parent = current.parent
        if parent == current:
            break
        current = parent
    
    return paths
