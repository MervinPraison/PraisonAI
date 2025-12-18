"""
Write File Tool for PraisonAI Code.

Provides functionality to create or overwrite files with content.
"""

import os
from typing import Optional, Dict, Any

from ..utils.file_utils import (
    file_exists,
    create_directories_for_file,
    is_path_within_directory,
    detect_line_ending,
    normalize_line_endings,
)
from ..utils.text_utils import (
    unescape_html_entities,
    strip_markdown_code_fences,
)


def write_file(
    path: str,
    content: str,
    workspace: Optional[str] = None,
    create_directories: bool = True,
    backup: bool = False,
    strip_code_fences: bool = True,
    encoding: str = 'utf-8',
) -> Dict[str, Any]:
    """
    Write content to a file, creating it if it doesn't exist.
    
    This tool writes content to a file, optionally creating parent
    directories and handling common AI output artifacts like code fences.
    
    Args:
        path: Path to the file (absolute or relative to workspace)
        content: Content to write to the file
        workspace: Workspace root directory (for relative paths)
        create_directories: Whether to create parent directories
        backup: Whether to create a backup of existing files
        strip_code_fences: Whether to strip markdown code fences
        encoding: File encoding (default: utf-8)
        
    Returns:
        Dictionary with:
        - success: bool
        - path: str (the path written to)
        - created: bool (True if file was created, False if overwritten)
        - backup_path: str (if backup was created)
        - error: str (if success is False)
        
    Example:
        >>> result = write_file("src/new_file.py", "print('hello')")
        >>> if result['success']:
        ...     print(f"Wrote to {result['path']}")
    """
    # Resolve path
    if workspace and not os.path.isabs(path):
        abs_path = os.path.abspath(os.path.join(workspace, path))
    else:
        abs_path = os.path.abspath(path)
    
    # Security check - ensure path is within workspace if specified
    if workspace:
        if not is_path_within_directory(abs_path, workspace):
            return {
                'success': False,
                'error': f"Path '{path}' is outside the workspace",
                'path': path,
            }
    
    # Process content
    processed_content = content
    
    # Strip markdown code fences if requested
    if strip_code_fences:
        processed_content = strip_markdown_code_fences(processed_content)
    
    # Unescape HTML entities (common in AI output)
    processed_content = unescape_html_entities(processed_content)
    
    # Check if file exists
    file_existed = file_exists(abs_path)
    backup_path = None
    
    try:
        # Create backup if requested and file exists
        if backup and file_existed:
            import time
            timestamp = int(time.time())
            backup_path = f"{abs_path}.backup.{timestamp}"
            with open(abs_path, 'r', encoding=encoding, errors='replace') as src:
                with open(backup_path, 'w', encoding=encoding) as dst:
                    dst.write(src.read())
        
        # Create parent directories if needed
        if create_directories:
            if not create_directories_for_file(abs_path):
                return {
                    'success': False,
                    'error': f"Failed to create directories for {path}",
                    'path': path,
                }
        
        # Preserve line endings if file exists
        if file_existed:
            try:
                with open(abs_path, 'r', encoding=encoding, errors='replace') as f:
                    original_content = f.read()
                original_line_ending = detect_line_ending(original_content)
                processed_content = normalize_line_endings(processed_content, original_line_ending)
            except Exception:
                pass  # If we can't read, just use the content as-is
        
        # Write the file
        with open(abs_path, 'w', encoding=encoding) as f:
            f.write(processed_content)
        
        return {
            'success': True,
            'path': path,
            'absolute_path': abs_path,
            'created': not file_existed,
            'backup_path': backup_path,
            'bytes_written': len(processed_content.encode(encoding)),
        }
        
    except PermissionError:
        return {
            'success': False,
            'error': f"Permission denied: {path}",
            'path': path,
        }
    except OSError as e:
        return {
            'success': False,
            'error': f"OS error writing {path}: {str(e)}",
            'path': path,
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error writing {path}: {str(e)}",
            'path': path,
        }


def append_to_file(
    path: str,
    content: str,
    workspace: Optional[str] = None,
    create_if_missing: bool = True,
    encoding: str = 'utf-8',
) -> Dict[str, Any]:
    """
    Append content to an existing file.
    
    Args:
        path: Path to the file
        content: Content to append
        workspace: Workspace root directory
        create_if_missing: Create file if it doesn't exist
        encoding: File encoding
        
    Returns:
        Dictionary with success status and details
    """
    # Resolve path
    if workspace and not os.path.isabs(path):
        abs_path = os.path.abspath(os.path.join(workspace, path))
    else:
        abs_path = os.path.abspath(path)
    
    # Security check
    if workspace:
        if not is_path_within_directory(abs_path, workspace):
            return {
                'success': False,
                'error': f"Path '{path}' is outside the workspace",
                'path': path,
            }
    
    file_existed = file_exists(abs_path)
    
    if not file_existed and not create_if_missing:
        return {
            'success': False,
            'error': f"File not found: {path}",
            'path': path,
        }
    
    try:
        # Create directories if needed
        if not file_existed:
            create_directories_for_file(abs_path)
        
        # Append to file
        with open(abs_path, 'a', encoding=encoding) as f:
            f.write(content)
        
        return {
            'success': True,
            'path': path,
            'absolute_path': abs_path,
            'created': not file_existed,
            'bytes_appended': len(content.encode(encoding)),
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f"Error appending to {path}: {str(e)}",
            'path': path,
        }
