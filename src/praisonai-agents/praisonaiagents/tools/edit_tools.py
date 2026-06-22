"""File editing tools for fuzzy find-and-replace operations.

This module provides tools for making targeted edits to files,
supporting fuzzy matching and patch operations similar to those
used in skill management.
"""

import os
import logging
import hashlib
import difflib
from typing import Optional, Tuple
from ..approval import require_approval

logger = logging.getLogger(__name__)


class EditTools:
    """Tools for file editing and patching operations."""
    
    def __init__(self, workspace=None):
        """Initialize EditTools with optional workspace containment.
        
        Args:
            workspace: Optional Workspace instance for path containment
        """
        self._workspace = workspace
        self._file_cache = {}  # Cache for staleness checking
    
    def _validate_path(self, filepath: str) -> str:
        """Validate and resolve a file path within workspace constraints."""
        if self._workspace is not None:
            return str(self._workspace.resolve(filepath))
        
        # Fallback to basic validation
        filepath = os.path.expanduser(filepath)
        if '..' in filepath:
            raise ValueError(f"Path traversal detected: {filepath}")
        return os.path.abspath(filepath)
    
    def _detect_line_ending(self, content: str) -> str:
        """Detect the line ending style of the content.
        
        Returns:
            '\\r\\n' for CRLF, '\\n' for LF (default)
        """
        if '\r\n' in content:
            return '\r\n'
        return '\n'
    
    def _count_occurrences(self, content: str, search_string: str) -> int:
        """Count the number of occurrences of search_string in content."""
        return content.count(search_string)
    
    def _compute_content_hash(self, content: str) -> str:
        """Compute a SHA256 hash of the content for staleness checking."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _render_diff(self, old_content: str, new_content: str, filepath: str, max_lines: int = 10) -> str:
        """Generate a bounded unified diff between old and new content.
        
        Args:
            old_content: Original content
            new_content: Modified content
            filepath: Path to the file (for diff header)
            max_lines: Maximum number of diff lines to include
            
        Returns:
            Unified diff string, truncated if necessary
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"{filepath} (before)",
            tofile=f"{filepath} (after)",
            n=3  # Context lines
        )
        
        diff_lines = []
        for i, line in enumerate(diff):
            if i >= max_lines:
                diff_lines.append("... (diff truncated)\n")
                break
            # Truncate very long lines
            if len(line) > 200:
                line = line[:197] + "...\n"
            diff_lines.append(line)
        
        return ''.join(diff_lines) if diff_lines else "No changes detected"
    
    @require_approval(risk_level="high")
    def edit_file(self, filepath: str, old_string: str, new_string: str, 
                  replace_all: bool = False, expected_hash: Optional[str] = None) -> str:
        """Edit a file by replacing text using precise find-and-replace.
        
        Args:
            filepath: Path to the file to edit
            old_string: Text to find and replace
            new_string: Replacement text
            replace_all: Whether to replace all occurrences (default: first only)
            expected_hash: Optional SHA256 hash of expected content for staleness check
            
        Returns:
            Success message with diff or error description
        """
        try:
            safe_path = self._validate_path(filepath)
            
            if not os.path.exists(safe_path):
                return f"Error: File not found: {filepath}"
            
            # Detect BOM and read file content
            with open(safe_path, 'rb') as f:
                raw_bytes = f.read()
            
            # Check for UTF-8 BOM only (we don't support UTF-16)
            bom = b''
            if raw_bytes.startswith(b'\xef\xbb\xbf'):  # UTF-8 BOM
                bom = b'\xef\xbb\xbf'
                raw_bytes = raw_bytes[3:]
            elif raw_bytes.startswith(b'\xff\xfe') or raw_bytes.startswith(b'\xfe\xff'):
                # UTF-16 BOM detected - not supported
                return "Error: UTF-16 encoding is not supported. Please convert the file to UTF-8."
            
            # Decode content (UTF-8 only)
            content = raw_bytes.decode('utf-8')
            
            # Detect line endings
            line_ending = self._detect_line_ending(content)
            
            # Staleness check
            if expected_hash is not None:
                current_hash = self._compute_content_hash(content)
                if current_hash != expected_hash:
                    return (f"Error: File has been modified since last read. "
                           f"Please re-read the file before editing. "
                           f"Expected hash: {expected_hash[:8]}..., "
                           f"Current hash: {current_hash[:8]}...")
            
            # Cache the current content hash for future staleness checks
            self._file_cache[safe_path] = self._compute_content_hash(content)
            
            # Validation
            if old_string == "":
                return "Error: old_string must be non-empty"
            
            if old_string not in content:
                preview = old_string[:50] + ("..." if len(old_string) > 50 else "")
                return f"Error: String not found in file: '{preview}'"
            
            # Count occurrences
            occurrences = self._count_occurrences(content, old_string)
            
            # Check for ambiguous match
            if occurrences > 1 and not replace_all:
                preview = old_string[:30] + ("..." if len(old_string) > 30 else "")
                return (f"Error: Ambiguous match - '{preview}' occurs {occurrences} times. "
                       f"Please provide more surrounding context to make the match unique, "
                       f"or use replace_all=True to replace all occurrences.")
            
            # Perform replacement
            if replace_all:
                new_content = content.replace(old_string, new_string)
                replacements = occurrences
            else:
                new_content = content.replace(old_string, new_string, 1)
                replacements = 1
            
            # Generate diff
            diff = self._render_diff(content, new_content, filepath)
            
            # Normalize line endings for the new content
            if line_ending == '\r\n':
                new_content = new_content.replace('\r\n', '\n').replace('\n', '\r\n')
            
            # Write updated content back with BOM if present
            with open(safe_path, 'wb') as f:
                if bom:
                    f.write(bom)
                f.write(new_content.encode('utf-8'))
            
            # Update cache with new content hash
            self._file_cache[safe_path] = self._compute_content_hash(new_content)
            
            return f"Success: Made {replacements} replacement(s) in {filepath}\n\nDiff:\n{diff}"
            
        except Exception as e:
            error_msg = f"Error editing file {filepath}: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def read_file(self, filepath: str) -> Tuple[str, str]:
        """Read a file and cache its content hash for staleness checking.
        
        Args:
            filepath: Path to the file to read
            
        Returns:
            Tuple of (content, hash) where hash can be used for staleness checking
        """
        try:
            safe_path = self._validate_path(filepath)
            
            if not os.path.exists(safe_path):
                return f"Error: File not found: {filepath}", ""
            
            # Read in binary mode to match edit_file behavior
            with open(safe_path, 'rb') as f:
                raw_bytes = f.read()
            
            # Strip UTF-8 BOM if present (matching edit_file logic)
            if raw_bytes.startswith(b'\xef\xbb\xbf'):
                raw_bytes = raw_bytes[3:]
            
            # Decode content (UTF-8 only, matching edit_file)
            content = raw_bytes.decode('utf-8')
            
            content_hash = self._compute_content_hash(content)
            self._file_cache[safe_path] = content_hash
            
            return content, content_hash
            
        except Exception as e:
            error_msg = f"Error reading file {filepath}: {str(e)}"
            logger.error(error_msg)
            return error_msg, ""
    
    def search_files(self, directory: str, pattern: str, 
                    file_pattern: str = "*") -> str:
        """Search for text patterns within files.
        
        Args:
            directory: Directory to search in
            pattern: Text pattern to search for
            file_pattern: File name pattern (glob) to filter files
            
        Returns:
            JSON string with search results
        """
        import json
        import glob
        from pathlib import Path
        
        try:
            safe_dir = self._validate_path(directory)
            
            if not os.path.exists(safe_dir):
                return json.dumps({"error": f"Directory not found: {directory}"})
            
            results = []
            search_pattern = os.path.join(safe_dir, "**", file_pattern)
            
            for filepath in glob.glob(search_pattern, recursive=True):
                if os.path.isfile(filepath):
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                        
                        matches = []
                        for line_num, line in enumerate(lines, 1):
                            if pattern.lower() in line.lower():
                                matches.append({
                                    "line_number": line_num,
                                    "line": line.strip(),
                                    "match_start": line.lower().find(pattern.lower())
                                })
                        
                        if matches:
                            relative_path = os.path.relpath(filepath, safe_dir)
                            results.append({
                                "file": relative_path,
                                "matches": matches
                            })
                    
                    except (UnicodeDecodeError, PermissionError):
                        # Skip files that can't be read
                        continue
            
            return json.dumps({
                "pattern": pattern,
                "directory": directory,
                "results": results,
                "total_files": len(results),
                "total_matches": sum(len(r["matches"]) for r in results)
            }, indent=2)
            
        except Exception as e:
            error_msg = f"Error searching files: {str(e)}"
            logger.error(error_msg)
            return json.dumps({"error": error_msg})


# Create default instance for direct function access
_edit_tools = EditTools()

@require_approval(risk_level="high")
def edit_file(filepath: str, old_string: str, new_string: str, 
              replace_all: bool = False, expected_hash: Optional[str] = None) -> str:
    """Edit a file by replacing text using precise find-and-replace.
    
    Args:
        filepath: Path to the file to edit
        old_string: Text to find and replace
        new_string: Replacement text
        replace_all: Whether to replace all occurrences (default: first only)
        expected_hash: Optional SHA256 hash of expected content for staleness check
        
    Returns:
        Success message with diff or error description
    """
    return _edit_tools.edit_file(filepath, old_string, new_string, replace_all, expected_hash)


def read_file(filepath: str) -> Tuple[str, str]:
    """Read a file and cache its content hash for staleness checking.
    
    Args:
        filepath: Path to the file to read
        
    Returns:
        Tuple of (content, hash) where hash can be used for staleness checking
    """
    return _edit_tools.read_file(filepath)


def search_files(directory: str, pattern: str, 
                file_pattern: str = "*") -> str:
    """Search for text patterns within files.
    
    Args:
        directory: Directory to search in
        pattern: Text pattern to search for
        file_pattern: File name pattern (glob) to filter files
        
    Returns:
        JSON string with search results
    """
    return _edit_tools.search_files(directory, pattern, file_pattern)


def create_edit_tools(workspace=None) -> EditTools:
    """Create EditTools instance with optional workspace containment.
    
    Args:
        workspace: Optional Workspace instance for path containment
        
    Returns:
        EditTools instance configured with workspace
    """
    return EditTools(workspace=workspace)