"""
@ Mention Autocomplete for PraisonAI CLI.

Provides file/directory autocomplete when user types @.
Uses only stdlib imports for zero performance impact.

Features:
- Detect @ trigger in input
- Fuzzy search files/directories
- Cache results for performance
- Integrate with prompt_toolkit
"""

import os
import time
import fnmatch
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class AtMentionContext:
    """Context for an @ mention in user input."""
    is_active: bool
    query: str
    start_pos: int
    mention_type: str = "file"  # file, directory, web, etc.


@dataclass
class FileSuggestion:
    """A file or directory suggestion."""
    path: str
    file_type: str  # "file" or "directory"
    score: int = 100
    display: str = ""
    
    def __post_init__(self):
        if not self.display:
            self.display = self.path


# ============================================================================
# @ Mention Detection
# ============================================================================

def detect_at_mention(text: str, cursor_pos: int) -> Optional[AtMentionContext]:
    """
    Detect if cursor is within an @ mention context.
    
    Scans backward from cursor to find @ symbol.
    Returns None if not in @ context.
    
    Args:
        text: Full input text
        cursor_pos: Current cursor position
        
    Returns:
        AtMentionContext if in @ mention, None otherwise
    """
    if cursor_pos <= 0 or cursor_pos > len(text):
        return None
    
    # Scan backward from cursor to find @
    at_pos = -1
    for i in range(cursor_pos - 1, -1, -1):
        char = text[i]
        
        # Found @
        if char == '@':
            at_pos = i
            break
        
        # Space/newline breaks @ context
        if char in ' \t\n\r':
            return None
    
    if at_pos == -1:
        return None
    
    # Extract query between @ and cursor
    query = text[at_pos + 1:cursor_pos]
    
    return AtMentionContext(
        is_active=True,
        query=query,
        start_pos=at_pos
    )


# ============================================================================
# File Search Service
# ============================================================================

class FileSearchService:
    """
    Service for searching files in a directory.
    
    Features:
    - Walk directory tree
    - Fuzzy match file paths
    - Cache results with TTL
    - Respect .gitignore (basic)
    """
    
    def __init__(
        self,
        root_dir: str,
        cache_ttl: int = 30,
        max_depth: int = 5,
        ignore_patterns: Optional[List[str]] = None
    ):
        self._root = os.path.abspath(root_dir)
        self._cache_ttl = cache_ttl
        self._max_depth = max_depth
        self._ignore_patterns = ignore_patterns or [
            '.git', '__pycache__', 'node_modules', '.venv', 'venv',
            '*.pyc', '*.pyo', '.DS_Store', '*.egg-info'
        ]
        
        # Cache: query -> (results, timestamp)
        self._cache: Dict[str, Tuple[List[FileSuggestion], float]] = {}
        
        # File list cache
        self._file_list: Optional[List[str]] = None
        self._file_list_time: float = 0
    
    def _should_ignore(self, name: str) -> bool:
        """Check if file/dir should be ignored."""
        for pattern in self._ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False
    
    def _get_file_list(self) -> List[str]:
        """Get list of all files (cached)."""
        now = time.time()
        
        # Return cached if fresh
        if self._file_list is not None and (now - self._file_list_time) < self._cache_ttl:
            return self._file_list
        
        files = []
        
        try:
            for root, dirs, filenames in os.walk(self._root):
                # Calculate depth
                rel_root = os.path.relpath(root, self._root)
                depth = 0 if rel_root == '.' else rel_root.count(os.sep) + 1
                
                if depth > self._max_depth:
                    dirs.clear()  # Don't descend further
                    continue
                
                # Filter ignored directories
                dirs[:] = [d for d in dirs if not self._should_ignore(d)]
                
                # Add directories
                for d in dirs:
                    rel_path = os.path.relpath(os.path.join(root, d), self._root)
                    files.append(rel_path + os.sep)
                
                # Add files
                for f in filenames:
                    if not self._should_ignore(f):
                        rel_path = os.path.relpath(os.path.join(root, f), self._root)
                        files.append(rel_path)
        except OSError:
            pass
        
        self._file_list = files
        self._file_list_time = now
        return files
    
    def _fuzzy_match(self, text: str, query: str) -> int:
        """
        Simple fuzzy match scoring.
        
        Returns score 0-100, higher is better.
        """
        if not query:
            return 50  # Default score for empty query
        
        text_lower = text.lower()
        query_lower = query.lower()
        
        # Exact match
        if text_lower == query_lower:
            return 100
        
        # Starts with
        if text_lower.startswith(query_lower):
            return 90
        
        # Contains
        if query_lower in text_lower:
            return 80
        
        # Fuzzy: all query chars appear in order
        text_idx = 0
        query_idx = 0
        matches = 0
        
        while text_idx < len(text_lower) and query_idx < len(query_lower):
            if text_lower[text_idx] == query_lower[query_idx]:
                matches += 1
                query_idx += 1
            text_idx += 1
        
        if query_idx == len(query_lower):
            # All query chars found
            return 50 + int(30 * matches / len(text))
        
        return 0
    
    def search(self, query: str, max_results: int = 20) -> List[FileSuggestion]:
        """
        Search for files matching query.
        
        Args:
            query: Search query (fuzzy matched)
            max_results: Maximum results to return
            
        Returns:
            List of FileSuggestion sorted by score
        """
        # Check cache
        cache_key = f"{query}:{max_results}"
        now = time.time()
        
        if cache_key in self._cache:
            results, cached_time = self._cache[cache_key]
            if (now - cached_time) < self._cache_ttl:
                return results
        
        # Get all files
        all_files = self._get_file_list()
        
        # Score and filter
        scored: List[Tuple[int, str]] = []
        for path in all_files:
            score = self._fuzzy_match(path, query)
            if score > 0:
                scored.append((score, path))
        
        # Sort by score descending
        scored.sort(key=lambda x: (-x[0], x[1]))
        
        # Build results
        results = []
        for score, path in scored[:max_results]:
            file_type = "directory" if path.endswith(os.sep) else "file"
            results.append(FileSuggestion(
                path=path,
                file_type=file_type,
                score=score
            ))
        
        # Cache results
        self._cache[cache_key] = (results, now)
        
        return results
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        self._cache.clear()
        self._file_list = None


# ============================================================================
# Completers for prompt_toolkit
# ============================================================================

# Lazy import to avoid performance impact
_Completer = None
_Completion = None

def _get_prompt_toolkit():
    """Lazy import prompt_toolkit."""
    global _Completer, _Completion
    if _Completer is None:
        from prompt_toolkit.completion import Completer, Completion
        _Completer = Completer
        _Completion = Completion
    return _Completer, _Completion


class AtMentionCompleter:
    """
    Completer for @ mentions.
    
    Shows file suggestions when user types @.
    Implements prompt_toolkit Completer interface.
    """
    
    def __init__(self, root_dir: str):
        self._file_service = FileSearchService(root_dir)
    
    def get_completions(self, document, complete_event):
        """Get completions for @ mentions."""
        _, Completion = _get_prompt_toolkit()
        
        text = document.text_before_cursor
        cursor_pos = len(text)
        
        # Detect @ context
        context = detect_at_mention(text, cursor_pos)
        if context is None or not context.is_active:
            return
        
        # Search files
        results = self._file_service.search(context.query, max_results=15)
        
        # Yield completions
        for suggestion in results:
            # Icon based on type
            icon = "📁 " if suggestion.file_type == "directory" else "📄 "
            display = f"{icon}{suggestion.path}"
            
            # Calculate replacement position
            # Replace from @ to cursor
            start_position = -(cursor_pos - context.start_pos)
            
            yield Completion(
                text=f"@{suggestion.path}",
                start_position=start_position,
                display=display
            )


def create_combined_completer(commands: List[str], root_dir: str):
    """
    Factory function to create a CombinedCompleter.
    
    Returns a proper Completer subclass that handles both / and @.
    """
    Completer, Completion = _get_prompt_toolkit()
    file_service = FileSearchService(root_dir)
    
    class CombinedCompleter(Completer):
        """
        Combined completer for both / commands and @ mentions.
        
        Properly inherits from prompt_toolkit Completer.
        """
        
        def get_completions(self, document, complete_event):
            """Get completions for / or @."""
            text = document.text_before_cursor.lstrip()
            
            # Check for slash command
            if text.startswith('/'):
                cmd_text = text[1:].lower()
                for cmd in commands:
                    if cmd.lower().startswith(cmd_text):
                        yield Completion(
                            f'/{cmd}',
                            start_position=-len(text),
                            display=f'/{cmd}'
                        )
                return
            
            # Check for @ mention
            full_text = document.text_before_cursor
            cursor_pos = len(full_text)
            
            context = detect_at_mention(full_text, cursor_pos)
            if context is None or not context.is_active:
                return
            
            # Search files
            results = file_service.search(context.query, max_results=15)
            
            # Yield completions
            for suggestion in results:
                icon = "📁 " if suggestion.file_type == "directory" else "📄 "
                display = f"{icon}{suggestion.path}"
                start_position = -(cursor_pos - context.start_pos)
                
                yield Completion(
                    text=f"@{suggestion.path}",
                    start_position=start_position,
                    display=display
                )
    
    return CombinedCompleter()


# Backward compatible alias
class CombinedCompleter:
    """
    Wrapper class for backward compatibility.
    
    Use create_combined_completer() for proper Completer subclass.
    """
    
    def __new__(cls, commands: List[str], root_dir: str):
        return create_combined_completer(commands, root_dir)


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    'AtMentionContext',
    'FileSuggestion',
    'detect_at_mention',
    'FileSearchService',
    'AtMentionCompleter',
    'CombinedCompleter',
]
