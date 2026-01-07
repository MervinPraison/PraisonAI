"""
Multiedit tool for applying multiple edits to a file in a single operation.

Inspired by OpenCode's multiedit tool, this allows efficient batch editing
without multiple file read/write cycles.
"""

import difflib
import os
from typing import Any, Dict, List, Optional


def multiedit(
    filepath: str,
    edits: List[Dict[str, Any]],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Apply multiple edits to a file in a single operation.
    
    Args:
        filepath: Path to the file to edit.
        edits: List of edit operations. Each edit is a dict with:
            - old: The text to find and replace (required)
            - new: The replacement text (required)
            - line: Optional line number hint for faster matching
        dry_run: If True, don't actually modify the file.
    
    Returns:
        Dict with:
            - success: Whether all edits were applied
            - edits_applied: Number of successful edits
            - edits_failed: Number of failed edits
            - diff: Unified diff of changes
            - dry_run: Whether this was a dry run
            - error: Error message if any
    
    Example:
        >>> multiedit("file.py", [
        ...     {"old": "print('hello')", "new": "print('Hello!')"},
        ...     {"old": "x = 1", "new": "x = 10", "line": 5},
        ... ])
        {'success': True, 'edits_applied': 2, 'edits_failed': 0, ...}
    """
    result = {
        "success": False,
        "edits_applied": 0,
        "edits_failed": 0,
        "diff": "",
        "dry_run": dry_run,
        "error": None,
    }
    
    # Validate inputs
    if not os.path.exists(filepath):
        result["error"] = f"File not found: {filepath}"
        return result
    
    if not edits:
        result["error"] = "No edits provided"
        return result
    
    # Validate edit format
    for i, edit in enumerate(edits):
        if "old" not in edit:
            result["error"] = f"Edit {i} missing 'old' key"
            return result
        if "new" not in edit:
            result["error"] = f"Edit {i} missing 'new' key"
            return result
    
    try:
        # Read file
        with open(filepath, 'r') as f:
            original_content = f.read()
        
        content = original_content
        lines = content.split('\n')
        
        # Apply edits
        for edit in edits:
            old_text = edit["old"]
            new_text = edit["new"]
            line_hint = edit.get("line")
            
            # Try to find and replace
            if line_hint is not None:
                # Use line hint for faster matching
                success = _apply_edit_with_hint(lines, old_text, new_text, line_hint)
                if success:
                    content = '\n'.join(lines)
                    result["edits_applied"] += 1
                else:
                    # Fall back to global search
                    if old_text in content:
                        content = content.replace(old_text, new_text, 1)
                        lines = content.split('\n')
                        result["edits_applied"] += 1
                    else:
                        result["edits_failed"] += 1
            else:
                # Global search and replace
                if old_text in content:
                    content = content.replace(old_text, new_text, 1)
                    lines = content.split('\n')
                    result["edits_applied"] += 1
                else:
                    # Try fuzzy matching
                    fuzzy_result = _fuzzy_find_and_replace(content, old_text, new_text)
                    if fuzzy_result is not None:
                        content = fuzzy_result
                        lines = content.split('\n')
                        result["edits_applied"] += 1
                    else:
                        result["edits_failed"] += 1
        
        # Generate diff
        original_lines = original_content.splitlines(keepends=True)
        new_lines = content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{os.path.basename(filepath)}",
            tofile=f"b/{os.path.basename(filepath)}",
        )
        result["diff"] = ''.join(diff)
        
        # Write file if not dry run
        if not dry_run and result["edits_applied"] > 0:
            with open(filepath, 'w') as f:
                f.write(content)
        
        result["success"] = result["edits_failed"] == 0
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def _apply_edit_with_hint(
    lines: List[str],
    old_text: str,
    new_text: str,
    line_hint: int,
) -> bool:
    """Apply edit using line number hint."""
    # Convert to 0-indexed
    line_idx = line_hint - 1
    
    if line_idx < 0 or line_idx >= len(lines):
        return False
    
    # Check if old_text is in the hinted line
    if old_text in lines[line_idx]:
        lines[line_idx] = lines[line_idx].replace(old_text, new_text, 1)
        return True
    
    # Check nearby lines (within 3 lines)
    for offset in range(1, 4):
        for idx in [line_idx - offset, line_idx + offset]:
            if 0 <= idx < len(lines) and old_text in lines[idx]:
                lines[idx] = lines[idx].replace(old_text, new_text, 1)
                return True
    
    return False


def _fuzzy_find_and_replace(
    content: str,
    old_text: str,
    new_text: str,
    threshold: float = 0.8,
) -> Optional[str]:
    """
    Try to find old_text with fuzzy matching and replace it.
    
    This handles cases where whitespace or minor differences exist.
    """
    # Normalize whitespace for comparison
    old_normalized = ' '.join(old_text.split())
    
    lines = content.split('\n')
    
    for i, line in enumerate(lines):
        line_normalized = ' '.join(line.split())
        
        # Check if normalized old_text is in normalized line
        if old_normalized in line_normalized:
            # Find the actual position and preserve indentation
            stripped = line.lstrip()
            indent = line[:len(line) - len(stripped)]
            
            # Try to match preserving structure
            if old_text.strip() in stripped:
                new_line = stripped.replace(old_text.strip(), new_text.strip(), 1)
                lines[i] = indent + new_line
                return '\n'.join(lines)
    
    # Try sequence matching for multi-line edits
    if '\n' in old_text:
        old_lines = old_text.split('\n')
        content_lines = content.split('\n')
        
        for i in range(len(content_lines) - len(old_lines) + 1):
            window = content_lines[i:i + len(old_lines)]
            
            # Compare normalized
            window_norm = [' '.join(l.split()) for l in window]
            old_norm = [' '.join(l.split()) for l in old_lines]
            
            if window_norm == old_norm:
                # Found match, replace preserving indentation of first line
                first_line = content_lines[i]
                indent = first_line[:len(first_line) - len(first_line.lstrip())]
                
                new_lines = new_text.split('\n')
                # Apply indent to new lines
                indented_new = [indent + l.lstrip() if l.strip() else l for l in new_lines]
                
                result_lines = content_lines[:i] + indented_new + content_lines[i + len(old_lines):]
                return '\n'.join(result_lines)
    
    return None
