"""File editing tools for fuzzy find-and-replace operations.

This module provides tools for making targeted edits to files,
supporting fuzzy matching and patch operations similar to those
used in skill management.
"""

import os
import logging
from typing import Optional
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
    
    def _validate_path(self, filepath: str) -> str:
        """Validate and resolve a file path within workspace constraints."""
        if self._workspace is not None:
            return str(self._workspace.resolve(filepath))
        
        # Fallback to basic validation
        filepath = os.path.expanduser(filepath)
        if '..' in filepath:
            raise ValueError(f"Path traversal detected: {filepath}")
        return os.path.abspath(filepath)
    
    @require_approval(risk_level="high")
    def edit_file(self, filepath: str, old_string: str, new_string: str, 
                  replace_all: bool = False) -> str:
        """Edit a file by replacing text using fuzzy find-and-replace.
        
        Args:
            filepath: Path to the file to edit
            old_string: Text to find and replace
            new_string: Replacement text
            replace_all: Whether to replace all occurrences (default: first only)
            
        Returns:
            Success message or error description
        """
        try:
            safe_path = self._validate_path(filepath)
            
            if not os.path.exists(safe_path):
                return f"Error: File not found: {filepath}"
            
            # Read file content
            with open(safe_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Perform replacement
            if old_string not in content:
                return f"Error: String not found in file: '{old_string[:50]}...'"
            
            if replace_all:
                new_content = content.replace(old_string, new_string)
                replacements = content.count(old_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
                replacements = 1
            
            # Write updated content back
            with open(safe_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return f"Success: Made {replacements} replacement(s) in {filepath}"
            
        except Exception as e:
            error_msg = f"Error editing file {filepath}: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
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
              replace_all: bool = False) -> str:
    """Edit a file by replacing text using fuzzy find-and-replace.
    
    Args:
        filepath: Path to the file to edit
        old_string: Text to find and replace
        new_string: Replacement text
        replace_all: Whether to replace all occurrences (default: first only)
        
    Returns:
        Success message or error description
    """
    return _edit_tools.edit_file(filepath, old_string, new_string, replace_all)


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