"""
File access control utilities for PraisonAI Code module.

Provides utilities for:
- Loading and parsing .gitignore patterns
- Checking if paths should be ignored
- Controlling file access within workspaces
"""

import os
import fnmatch
from typing import List, Optional, Set


def load_gitignore_patterns(directory: str) -> List[str]:
    """
    Load .gitignore patterns from a directory.
    
    Args:
        directory: The directory to search for .gitignore
        
    Returns:
        List of gitignore patterns
    """
    patterns = []
    gitignore_path = os.path.join(directory, '.gitignore')
    
    if os.path.isfile(gitignore_path):
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        patterns.append(line)
        except (IOError, OSError):
            pass
    
    return patterns


def _pattern_to_regex_parts(pattern: str) -> tuple:
    """
    Convert a gitignore pattern to matching components.
    
    Args:
        pattern: A gitignore pattern
        
    Returns:
        Tuple of (is_negation, is_directory_only, cleaned_pattern)
    """
    is_negation = pattern.startswith('!')
    if is_negation:
        pattern = pattern[1:]
    
    is_directory_only = pattern.endswith('/')
    if is_directory_only:
        pattern = pattern[:-1]
    
    return is_negation, is_directory_only, pattern


def should_ignore_path(
    path: str,
    patterns: List[str],
    base_dir: str,
    is_directory: bool = False
) -> bool:
    """
    Check if a path should be ignored based on gitignore patterns.
    
    Args:
        path: The path to check (relative or absolute)
        patterns: List of gitignore patterns
        base_dir: The base directory for relative path calculation
        is_directory: Whether the path is a directory
        
    Returns:
        True if the path should be ignored
    """
    # Get relative path
    if os.path.isabs(path):
        try:
            rel_path = os.path.relpath(path, base_dir)
        except ValueError:
            rel_path = path
    else:
        rel_path = path
    
    # Normalize path separators
    rel_path = rel_path.replace(os.sep, '/')
    
    # Check each pattern
    ignored = False
    
    for pattern in patterns:
        is_negation, is_directory_only, clean_pattern = _pattern_to_regex_parts(pattern)
        
        # Skip directory-only patterns for files
        if is_directory_only and not is_directory:
            continue
        
        # Check if pattern matches
        matches = False
        
        # Handle patterns with /
        if '/' in clean_pattern:
            # Pattern with / matches from root
            if clean_pattern.startswith('/'):
                clean_pattern = clean_pattern[1:]
            matches = fnmatch.fnmatch(rel_path, clean_pattern)
        else:
            # Pattern without / matches any path component
            path_parts = rel_path.split('/')
            for part in path_parts:
                if fnmatch.fnmatch(part, clean_pattern):
                    matches = True
                    break
            # Also check full path for ** patterns
            if not matches and '**' in clean_pattern:
                matches = fnmatch.fnmatch(rel_path, clean_pattern)
        
        if matches:
            ignored = not is_negation
    
    return ignored


class FileAccessController:
    """
    Controls file access within a workspace.
    
    Respects .gitignore patterns and can be configured with
    additional ignore/allow patterns.
    
    Attributes:
        workspace_root: The root directory of the workspace
        ignore_patterns: Patterns for files to ignore
        protected_patterns: Patterns for files that are read-only
    """
    
    def __init__(
        self,
        workspace_root: str,
        load_gitignore: bool = True,
        additional_ignore_patterns: Optional[List[str]] = None,
        protected_patterns: Optional[List[str]] = None
    ):
        """
        Initialize the FileAccessController.
        
        Args:
            workspace_root: The root directory of the workspace
            load_gitignore: Whether to load .gitignore patterns
            additional_ignore_patterns: Extra patterns to ignore
            protected_patterns: Patterns for read-only files
        """
        self.workspace_root = os.path.abspath(workspace_root)
        self.ignore_patterns: List[str] = []
        self.protected_patterns: List[str] = protected_patterns or []
        self._ignored_cache: Set[str] = set()
        
        # Load .gitignore patterns
        if load_gitignore:
            self.ignore_patterns.extend(load_gitignore_patterns(self.workspace_root))
        
        # Add additional patterns
        if additional_ignore_patterns:
            self.ignore_patterns.extend(additional_ignore_patterns)
        
        # Always ignore common patterns
        default_ignores = [
            '.git',
            '.git/**',
            '__pycache__',
            '__pycache__/**',
            '*.pyc',
            '.DS_Store',
            'node_modules',
            'node_modules/**',
        ]
        for pattern in default_ignores:
            if pattern not in self.ignore_patterns:
                self.ignore_patterns.append(pattern)
    
    def is_path_allowed(self, path: str) -> bool:
        """
        Check if a path is allowed for access.
        
        Args:
            path: The path to check
            
        Returns:
            True if the path is allowed
        """
        # Resolve to absolute path
        if not os.path.isabs(path):
            abs_path = os.path.abspath(os.path.join(self.workspace_root, path))
        else:
            abs_path = os.path.abspath(path)
        
        # Check if within workspace
        if not self._is_within_workspace(abs_path):
            return False
        
        # Check if ignored
        is_dir = os.path.isdir(abs_path)
        if should_ignore_path(abs_path, self.ignore_patterns, self.workspace_root, is_dir):
            return False
        
        return True
    
    def is_write_protected(self, path: str) -> bool:
        """
        Check if a path is write-protected.
        
        Args:
            path: The path to check
            
        Returns:
            True if the path is write-protected
        """
        if not self.protected_patterns:
            return False
        
        # Get relative path
        if os.path.isabs(path):
            try:
                rel_path = os.path.relpath(path, self.workspace_root)
            except ValueError:
                rel_path = path
        else:
            rel_path = path
        
        rel_path = rel_path.replace(os.sep, '/')
        
        for pattern in self.protected_patterns:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        
        return False
    
    def validate_access(self, path: str, write: bool = False) -> bool:
        """
        Validate if access to a path is allowed.
        
        Args:
            path: The path to validate
            write: Whether write access is needed
            
        Returns:
            True if access is allowed
        """
        if not self.is_path_allowed(path):
            return False
        
        if write and self.is_write_protected(path):
            return False
        
        return True
    
    def _is_within_workspace(self, abs_path: str) -> bool:
        """
        Check if an absolute path is within the workspace.
        
        Args:
            abs_path: The absolute path to check
            
        Returns:
            True if within workspace
        """
        # Normalize paths
        workspace = os.path.normpath(self.workspace_root)
        target = os.path.normpath(abs_path)
        
        # Check if target starts with workspace path
        return target.startswith(workspace + os.sep) or target == workspace
    
    def get_relative_path(self, path: str) -> str:
        """
        Get the relative path from workspace root.
        
        Args:
            path: The path to convert
            
        Returns:
            Relative path string
        """
        if os.path.isabs(path):
            try:
                return os.path.relpath(path, self.workspace_root)
            except ValueError:
                return path
        return path
    
    def get_absolute_path(self, path: str) -> str:
        """
        Get the absolute path for a relative path.
        
        Args:
            path: The relative path
            
        Returns:
            Absolute path string
        """
        if os.path.isabs(path):
            return path
        return os.path.abspath(os.path.join(self.workspace_root, path))
