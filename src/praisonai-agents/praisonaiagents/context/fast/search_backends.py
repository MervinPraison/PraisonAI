"""
Search backends for FastContext.

Provides protocol-driven search backends:
- PythonSearchBackend: Pure Python implementation (always available)
- RipgrepBackend: Optional ripgrep subprocess (faster for large codebases)

Design principles:
- Lazy imports for optional dependencies
- Graceful degradation if deps not installed
- No performance impact on default behavior
"""

import logging
from typing import Protocol, List, Dict, Any, Optional, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class SearchBackend(Protocol):
    """Protocol for search backends.
    
    All backends must implement these methods to be usable
    with FastContext.
    """
    
    def grep(
        self,
        path: str,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        max_results: int = 100,
        context_lines: int = 0
    ) -> List[Dict[str, Any]]:
        """Search for pattern in files.
        
        Args:
            path: Directory or file to search
            pattern: Search pattern
            is_regex: If True, treat pattern as regex
            case_sensitive: If True, case sensitive search
            include_patterns: Glob patterns to include
            exclude_patterns: Glob patterns to exclude
            max_results: Maximum results to return
            context_lines: Lines of context around matches
            
        Returns:
            List of match dictionaries
        """
        ...
    
    def glob(
        self,
        path: str,
        pattern: str,
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """Search for files matching glob pattern.
        
        Args:
            path: Directory to search
            pattern: Glob pattern
            max_results: Maximum results
            
        Returns:
            List of file info dictionaries
        """
        ...
    
    def is_available(self) -> bool:
        """Check if this backend is available.
        
        Returns:
            True if backend can be used
        """
        ...


class PythonSearchBackend:
    """Pure Python search backend using existing search_tools.
    
    This is always available and serves as the default fallback.
    """
    
    def is_available(self) -> bool:
        """Python backend is always available."""
        return True
    
    def grep(
        self,
        path: str,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        max_results: int = 100,
        context_lines: int = 0
    ) -> List[Dict[str, Any]]:
        """Search using pure Python regex."""
        # Import existing implementation
        from praisonaiagents.context.fast.search_tools import grep_search
        
        return grep_search(
            search_path=path,
            pattern=pattern,
            is_regex=is_regex,
            case_sensitive=case_sensitive,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            max_results=max_results,
            context_lines=context_lines
        )
    
    def glob(
        self,
        path: str,
        pattern: str,
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """Search for files using pathlib glob."""
        from praisonaiagents.context.fast.search_tools import glob_search
        
        return glob_search(
            search_path=path,
            pattern=pattern,
            max_results=max_results
        )


class RipgrepBackend:
    """Optional ripgrep backend using subprocess.
    
    Faster for large codebases but requires 'rg' binary in PATH.
    Falls back to PythonSearchBackend if not available.
    """
    
    def __init__(self):
        self._available: Optional[bool] = None
        self._rg_path: Optional[str] = None
        self._fallback: Optional[PythonSearchBackend] = None
    
    def _get_ripgrep_path(self) -> Optional[str]:
        """Find ripgrep binary in PATH."""
        if self._rg_path is not None:
            return self._rg_path if self._rg_path != "" else None
        
        import shutil
        self._rg_path = shutil.which("rg") or ""
        return self._rg_path if self._rg_path else None
    
    def is_available(self) -> bool:
        """Check if ripgrep is installed."""
        if self._available is None:
            self._available = self._get_ripgrep_path() is not None
        return self._available
    
    def _get_fallback(self) -> PythonSearchBackend:
        """Get Python fallback backend."""
        if self._fallback is None:
            self._fallback = PythonSearchBackend()
        return self._fallback
    
    def grep(
        self,
        path: str,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        max_results: int = 100,
        context_lines: int = 0
    ) -> List[Dict[str, Any]]:
        """Search using ripgrep subprocess."""
        if not self.is_available():
            logger.debug("Ripgrep not available, using Python fallback")
            return self._get_fallback().grep(
                path, pattern, is_regex, case_sensitive,
                include_patterns, exclude_patterns, max_results, context_lines
            )
        
        import subprocess
        import json
        import os
        
        rg_path = self._get_ripgrep_path()
        if not rg_path:
            return self._get_fallback().grep(
                path, pattern, is_regex, case_sensitive,
                include_patterns, exclude_patterns, max_results, context_lines
            )
        
        # Build ripgrep command
        cmd = [rg_path, "--json"]
        
        if not is_regex:
            cmd.append("--fixed-strings")
        
        if not case_sensitive:
            cmd.append("--ignore-case")
        
        if context_lines > 0:
            cmd.extend(["--context", str(context_lines)])
        
        cmd.extend(["--max-count", str(max_results)])
        
        # Add include patterns
        if include_patterns:
            for p in include_patterns:
                cmd.extend(["--glob", p])
        
        # Add exclude patterns
        if exclude_patterns:
            for p in exclude_patterns:
                cmd.extend(["--glob", f"!{p}"])
        
        cmd.append(pattern)
        cmd.append(path)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            results = []
            for line in result.stdout.splitlines():
                try:
                    data = json.loads(line)
                    if data.get("type") == "match":
                        match_data = data.get("data", {})
                        results.append({
                            "path": match_data.get("path", {}).get("text", ""),
                            "absolute_path": os.path.join(path, match_data.get("path", {}).get("text", "")),
                            "line_number": match_data.get("line_number", 0),
                            "content": match_data.get("lines", {}).get("text", "").rstrip(),
                        })
                except json.JSONDecodeError:
                    continue
            
            return results[:max_results]
            
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.warning(f"Ripgrep failed: {e}, falling back to Python")
            return self._get_fallback().grep(
                path, pattern, is_regex, case_sensitive,
                include_patterns, exclude_patterns, max_results, context_lines
            )
    
    def glob(
        self,
        path: str,
        pattern: str,
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """Glob is not well-supported by ripgrep, use Python."""
        return self._get_fallback().glob(path, pattern, max_results)


def _count_files_fast(path: str, limit: int = 1000) -> int:
    """Quickly count files in a directory (stops at limit).
    
    Args:
        path: Directory to count files in
        limit: Stop counting after this many files
        
    Returns:
        Number of files found (capped at limit)
    """
    import os
    
    count = 0
    try:
        for root, dirs, files in os.walk(path):
            # Skip common non-code directories
            dirs[:] = [d for d in dirs if d not in {
                '.git', 'node_modules', 'venv', '.venv', '__pycache__',
                'site-packages', '.tox', 'dist', 'build', '.eggs'
            }]
            count += len(files)
            if count >= limit:
                return limit
    except Exception:
        pass
    return count


# Threshold for switching from Python to Ripgrep
# Based on profiling: Python is faster for <500 files due to subprocess overhead
RIPGREP_FILE_THRESHOLD = 500


class SmartBackend:
    """Smart backend that auto-selects Python or Ripgrep based on codebase size.
    
    Uses Python for small codebases (<500 files) where subprocess overhead
    is significant, and Ripgrep for larger codebases where its speed advantage
    (30-40x faster) outweighs the ~10ms startup overhead.
    """
    
    def __init__(self, workspace_path: Optional[str] = None):
        self._workspace_path = workspace_path
        self._python = PythonSearchBackend()
        self._ripgrep: Optional[RipgrepBackend] = None
        self._file_count: Optional[int] = None
        self._use_ripgrep: Optional[bool] = None
    
    def _get_ripgrep(self) -> RipgrepBackend:
        """Lazy-load ripgrep backend."""
        if self._ripgrep is None:
            self._ripgrep = RipgrepBackend()
        return self._ripgrep
    
    def _should_use_ripgrep(self, path: str) -> bool:
        """Determine if ripgrep should be used based on codebase size."""
        # Check if ripgrep is available
        rg = self._get_ripgrep()
        if not rg.is_available():
            return False
        
        # Count files if not already counted for this path
        if self._file_count is None or self._workspace_path != path:
            self._workspace_path = path
            self._file_count = _count_files_fast(path, limit=RIPGREP_FILE_THRESHOLD + 1)
            self._use_ripgrep = self._file_count >= RIPGREP_FILE_THRESHOLD
            
            if self._use_ripgrep:
                logger.debug(f"Auto-selected ripgrep backend ({self._file_count}+ files)")
            else:
                logger.debug(f"Auto-selected Python backend ({self._file_count} files)")
        
        return self._use_ripgrep or False
    
    def is_available(self) -> bool:
        """Smart backend is always available."""
        return True
    
    def grep(
        self,
        path: str,
        pattern: str,
        is_regex: bool = False,
        case_sensitive: bool = False,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        max_results: int = 100,
        context_lines: int = 0
    ) -> List[Dict[str, Any]]:
        """Search using auto-selected backend."""
        if self._should_use_ripgrep(path):
            return self._get_ripgrep().grep(
                path, pattern, is_regex, case_sensitive,
                include_patterns, exclude_patterns, max_results, context_lines
            )
        return self._python.grep(
            path, pattern, is_regex, case_sensitive,
            include_patterns, exclude_patterns, max_results, context_lines
        )
    
    def glob(
        self,
        path: str,
        pattern: str,
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """Glob always uses Python (ripgrep doesn't support glob well)."""
        return self._python.glob(path, pattern, max_results)


def get_search_backend(
    backend_type: str = "auto",
    workspace_path: Optional[str] = None
) -> SearchBackend:
    """Get a search backend by type.
    
    Args:
        backend_type: One of "auto", "python", "ripgrep"
        workspace_path: Path to workspace (used for auto detection)
        
    Returns:
        SearchBackend instance
        
    Raises:
        ValueError: If backend_type is invalid
        
    Performance notes:
        - "python": Best for small codebases (<500 files), no subprocess overhead
        - "ripgrep": Best for large codebases (500+ files), 30-40x faster
        - "auto": Automatically selects based on codebase size
    """
    if backend_type == "python":
        return PythonSearchBackend()
    
    elif backend_type == "ripgrep":
        backend = RipgrepBackend()
        if not backend.is_available():
            logger.warning("Ripgrep not available, using Python fallback")
            return PythonSearchBackend()
        return backend
    
    elif backend_type == "auto":
        # Use SmartBackend that auto-selects based on codebase size
        return SmartBackend(workspace_path)
    
    else:
        raise ValueError(f"Invalid backend type: {backend_type}. Must be 'auto', 'python', or 'ripgrep'")
