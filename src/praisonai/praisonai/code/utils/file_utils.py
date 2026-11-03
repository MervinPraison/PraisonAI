"""
File utility functions for PraisonAI Code module.

Provides utilities for file operations including:
- Line number handling (add/strip)
- File existence and type checking
- Directory creation
- Line ending normalization
"""

import errno
import os
import re
import uuid
from typing import Optional, Tuple


def add_line_numbers(content: str, start_line: int = 1) -> str:
    """
    Add line numbers to content in the format: "  N | content"
    
    Args:
        content: The text content to add line numbers to
        start_line: The starting line number (1-indexed)
        
    Returns:
        Content with line numbers prefixed to each line
        
    Example:
        >>> add_line_numbers("hello\\nworld", 1)
        '  1 | hello\\n  2 | world'
    """
    if not content:
        return ""
    
    lines = content.split('\n')
    max_line_num = start_line + len(lines) - 1
    width = len(str(max_line_num))
    
    numbered_lines = []
    for i, line in enumerate(lines):
        line_num = start_line + i
        numbered_lines.append(f"{line_num:>{width}} | {line}")
    
    return '\n'.join(numbered_lines)


def strip_line_numbers(content: str, aggressive: bool = False) -> str:
    """
    Strip line numbers from content.
    
    Handles formats like:
    - "  1 | content"
    - "1| content"
    - "  1\tcontent"
    
    Args:
        content: Content with line numbers
        aggressive: If True, also strip formats like "1:" or just leading numbers
        
    Returns:
        Content with line numbers removed
    """
    if not content:
        return ""
    
    lines = content.split('\n')
    stripped_lines = []
    
    # Pattern for standard format: optional spaces, digits, optional spaces, pipe/tab, content
    standard_pattern = re.compile(r'^\s*\d+\s*[|\t]\s?(.*)$')
    # Aggressive pattern: digits followed by colon or just leading digits with space
    aggressive_pattern = re.compile(r'^\s*\d+[:\s]\s?(.*)$')
    
    for line in lines:
        match = standard_pattern.match(line)
        if match:
            stripped_lines.append(match.group(1))
        elif aggressive:
            match = aggressive_pattern.match(line)
            if match:
                stripped_lines.append(match.group(1))
            else:
                stripped_lines.append(line)
        else:
            stripped_lines.append(line)
    
    return '\n'.join(stripped_lines)


def every_line_has_line_numbers(content: str) -> bool:
    """
    Check if every non-empty line in content has line numbers.
    
    Args:
        content: The content to check
        
    Returns:
        True if all non-empty lines have line numbers
    """
    if not content or not content.strip():
        return False
    
    lines = content.split('\n')
    pattern = re.compile(r'^\s*\d+\s*[|\t]')
    
    for line in lines:
        if line.strip():  # Only check non-empty lines
            if not pattern.match(line):
                return False
    
    return True


def normalize_line_endings(content: str, target: str = '\n') -> str:
    """
    Normalize line endings to a consistent format.
    
    Args:
        content: The content to normalize
        target: The target line ending ('\\n' or '\\r\\n')
        
    Returns:
        Content with normalized line endings
    """
    # First normalize all to \n, then convert to target
    normalized = content.replace('\r\n', '\n').replace('\r', '\n')
    if target == '\r\n':
        normalized = normalized.replace('\n', '\r\n')
    return normalized


def detect_line_ending(content: str) -> str:
    """
    Detect the predominant line ending in content.
    
    Args:
        content: The content to analyze
        
    Returns:
        '\\r\\n' if Windows-style, '\\n' otherwise
    """
    if '\r\n' in content:
        return '\r\n'
    return '\n'


def get_file_extension(file_path: str) -> str:
    """
    Get the file extension from a path.
    
    Args:
        file_path: Path to the file
        
    Returns:
        File extension without the dot, or empty string
    """
    ext = os.path.splitext(file_path)[1]
    return ext[1:] if ext else ""


def is_binary_file(file_path: str, sample_size: int = 8192) -> bool:
    """
    Check if a file is binary by reading a sample.
    
    Args:
        file_path: Path to the file
        sample_size: Number of bytes to sample
        
    Returns:
        True if the file appears to be binary
    """
    try:
        with open(file_path, 'rb') as f:
            sample = f.read(sample_size)
        
        # Check for null bytes (common in binary files)
        if b'\x00' in sample:
            return True
        
        # Check the ratio of non-text characters
        text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7f})
        non_text = sum(1 for byte in sample if byte not in text_chars)
        
        # If more than 30% non-text characters, consider it binary
        return len(sample) > 0 and (non_text / len(sample)) > 0.30
        
    except (IOError, OSError):
        return False


def create_directories_for_file(file_path: str) -> bool:
    """
    Create parent directories for a file path if they don't exist.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if directories were created or already exist
    """
    try:
        parent_dir = os.path.dirname(file_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        return True
    except OSError:
        return False


def file_exists(file_path: str) -> bool:
    """
    Check if a file exists.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if the file exists and is a file (not directory)
    """
    return os.path.isfile(file_path)


def get_relative_path(file_path: str, base_path: str) -> str:
    """
    Get the relative path from base_path to file_path.
    
    Args:
        file_path: The target file path
        base_path: The base directory path
        
    Returns:
        Relative path string
    """
    try:
        return os.path.relpath(file_path, base_path)
    except ValueError:
        # On Windows, relpath fails for paths on different drives
        return file_path


def is_path_within_directory(file_path: str, directory: str) -> bool:
    """
    Check if a file path is within a directory (prevents path traversal).
    
    Args:
        file_path: The file path to check
        directory: The directory that should contain the file
        
    Returns:
        True if file_path is within directory
    """
    # Resolve to real paths so symlinks cannot escape the workspace
    abs_file = os.path.realpath(file_path)
    abs_dir = os.path.realpath(directory)
    
    # Ensure directory ends with separator for proper prefix matching
    if not abs_dir.endswith(os.sep):
        abs_dir += os.sep
    
    return abs_file.startswith(abs_dir) or abs_file == abs_dir.rstrip(os.sep)


def read_file_lines(file_path: str, start_line: int = 1, end_line: Optional[int] = None) -> Tuple[str, int]:
    """
    Read specific lines from a file.
    
    Args:
        file_path: Path to the file
        start_line: First line to read (1-indexed)
        end_line: Last line to read (inclusive), None for all remaining
        
    Returns:
        Tuple of (content, total_lines)
    """
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    
    total_lines = len(lines)
    
    # Convert to 0-indexed
    start_idx = max(0, start_line - 1)
    end_idx = end_line if end_line else total_lines
    
    selected_lines = lines[start_idx:end_idx]
    content = ''.join(selected_lines)
    
    # Remove trailing newline if present
    if content.endswith('\n'):
        content = content[:-1]
    
    return content, total_lines


def count_file_lines(file_path: str) -> int:
    """
    Count the number of lines in a file efficiently.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Number of lines in the file
    """
    count = 0
    with open(file_path, 'rb') as f:
        for _ in f:
            count += 1
    return count


def atomic_write(path: str, content: str, *, encoding: Optional[str] = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically (temp file + fsync + os.replace).

    ``open(path, 'w')`` truncates the target immediately, so any interrupt
    (cancellation, SIGTERM, disk-full) between open and write leaves the file
    zero-byte or half-written and the original content lost. The code editing
    tools run on LLM-driven tool calls that regularly hit timeouts/cancellations,
    so they need the same crash-safe write the wrapper already uses for configs.
    """
    # Resolve symlinks so we replace the link target (like open(path, 'w')
    # writes through the link) instead of turning the symlink into a plain file.
    path = os.path.realpath(path)
    target_dir = os.path.dirname(path) or "."
    # Atomic replace swaps in a fresh inode, so carry over the metadata that
    # matters for a replaced file: permission bits and ownership (uid/gid).
    # Hard-link identity and xattrs/ACLs cannot be preserved through an inode
    # swap and are out of scope for this tool.
    try:
        existing_stat = os.stat(path)
    except OSError:
        existing_stat = None
    # An inode swap would bypass a read-only target's permissions, so keep the
    # old open(path, 'w') behaviour and refuse to replace a file we can't write.
    if existing_stat is not None and not os.access(path, os.W_OK):
        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), path)
    # Create the temp file with the target's permission bits (setuid/setgid
    # dropped) so private files (e.g. 0600 .env) are never readable by others
    # while the new content is written. New files use 0o666 so the kernel
    # applies the umask, like open(path, 'w'). Never call os.umask(): it is
    # process-wide and would race with other threads.
    mode = (existing_stat.st_mode & 0o777) if existing_stat is not None else 0o666
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    while True:
        tmp_path = os.path.join(target_dir, f".tmp_{uuid.uuid4().hex}")
        try:
            fd = os.open(tmp_path, flags, mode)
            break
        except FileExistsError:
            continue
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())  # durability before rename
        if existing_stat is not None:
            # Restore bits the umask may have removed; never widens beyond the
            # target. If this fails the temp file is at most as open as the target.
            try:
                os.chmod(tmp_path, mode)
            except OSError:
                pass  # best-effort
            if hasattr(os, "chown"):
                try:
                    os.chown(tmp_path, existing_stat.st_uid, existing_stat.st_gid)
                except (OSError, AttributeError):
                    pass  # best-effort (needs privilege; no-op on Windows)
        os.replace(tmp_path, path)  # atomic on POSIX + Windows
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
