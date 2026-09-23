"""
Multiedit tool for applying multiple edits to a file in a single operation.

Inspired by OpenCode's multiedit tool, this allows efficient batch editing
without multiple file read/write cycles.
"""

import contextlib
import difflib
import os
import tempfile
from typing import Any, Dict, List, Optional

from praisonai.code.utils.file_utils import is_path_within_directory


def _atomic_write(path: str, content: str) -> None:
    """Write ``content`` to ``path`` atomically (temp file + fsync + os.replace).

    ``open(path, 'w')`` truncates the target immediately, so any interrupt
    (cancellation, SIGTERM, disk-full) between open and write leaves the file
    zero-byte or half-written and the original content lost. multiedit runs on
    LLM-driven tool calls that regularly hit timeouts/cancellations, so it needs
    the same crash-safe write the rest of the wrapper already uses for configs.
    """
    target_dir = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", dir=target_dir)
    try:
        # Preserve the existing file's mode so a replaced file stays readable
        # (mkstemp creates 0600 by default).
        try:
            existing_mode = os.stat(path).st_mode
        except OSError:
            existing_mode = None
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())  # durability before rename
        if existing_mode is not None:
            try:
                os.chmod(tmp_path, existing_mode)
            except OSError:
                pass  # best-effort
        os.replace(tmp_path, path)  # atomic on POSIX + Windows
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


@contextlib.contextmanager
def _file_lock(path: str):
    """Advisory exclusive lock over the read-modify-write window for ``path``.

    Prevents the lost-update race where two concurrent multiedit calls both read
    the same snapshot and the later write silently discards the earlier edit.
    Falls back to a no-op where ``fcntl`` is unavailable (e.g. Windows).
    """
    try:
        import fcntl
    except ImportError:
        yield
        return

    lock_path = path + ".lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _resolve_safe_path(filepath: str, workspace_root: Optional[str] = None) -> Optional[str]:
    """Resolve filepath within workspace; return None if outside boundary."""
    if ".." in filepath.replace("\\", "/"):
        return None
    root = os.path.realpath(workspace_root or os.getcwd())
    abs_path = os.path.realpath(os.path.join(root, filepath) if not os.path.isabs(filepath) else filepath)
    if not is_path_within_directory(abs_path, root):
        return None
    return abs_path


def multiedit(
    filepath: str,
    edits: List[Dict[str, Any]],
    dry_run: bool = False,
    workspace_root: Optional[str] = None,
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
        workspace_root: Directory boundary for filepath (defaults to cwd).
    
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
    
    # Validate path within workspace
    safe_path = _resolve_safe_path(filepath, workspace_root)
    if safe_path is None:
        result["error"] = f"Path outside workspace: {filepath}"
        return result
    filepath = safe_path

    # Refuse to overwrite protected files even when they sit inside the
    # workspace root (.env, wallet.json, audit.jsonl, praisonaiagents/**, …).
    from praisonai.security import is_protected, get_protection_reason

    if is_protected(filepath):
        result["error"] = (
            f"Refusing to edit protected path: {get_protection_reason(filepath)}"
        )
        return result

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
        # Hold an advisory lock across the whole read-modify-write so two
        # concurrent multiedit calls on the same file cannot lose each other's
        # edits (classic lost-update). No-op where fcntl is unavailable.
        lock_cm = contextlib.nullcontext() if dry_run else _file_lock(filepath)
        with lock_cm:
            _run_edits(filepath, edits, dry_run, result)
    except Exception as e:
        result["error"] = str(e)
    
    return result


def _run_edits(
    filepath: str,
    edits: List[Dict[str, Any]],
    dry_run: bool,
    result: Dict[str, Any],
) -> None:
    """Read, apply edits, and atomically write ``filepath`` (mutates ``result``)."""
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

    # Write file atomically if not dry run (crash-safe: no zero-byte truncation)
    if not dry_run and result["edits_applied"] > 0:
        _atomic_write(filepath, content)

    result["success"] = result["edits_failed"] == 0


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
