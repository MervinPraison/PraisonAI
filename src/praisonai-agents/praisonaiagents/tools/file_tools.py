"""File handling tools for basic file operations.

Usage:
from praisonaiagents.tools import file_tools
content = file_tools.read_file("example.txt")
file_tools.write_file("output.txt", "Hello World")

or 
from praisonaiagents.tools import read_file, write_file, list_files
content = read_file("example.txt")
"""

import os
import json
import hashlib
from typing import List, Dict, Union, Optional
from pathlib import Path
import shutil
import logging
from ..approval import require_approval
from . import _file_locks

# Default cap on the number of lines returned by a single ``read_file`` call
# when no explicit ``limit`` is given.  Keeps an unbounded whole-file read from
# silently blowing the context budget; the model is told how to page for more.
DEFAULT_MAX_LINES = 2000

# Default cap on characters rendered per line so one pathologically long line
# cannot dominate the window.
DEFAULT_MAX_LINE_CHARS = 2000


def _render_with_line_numbers(lines, start_index, max_line_chars):
    """Render ``lines`` with a right-aligned 1-based line-number gutter.

    Args:
        lines: The window of lines to render.
        start_index: 0-based index of the first line within the full file.
        max_line_chars: Truncate any single line longer than this.

    Returns:
        str: Line-numbered content (e.g. ``   42\\tconst x = ...``).
    """
    if not lines:
        return ""
    last_number = start_index + len(lines)
    width = max(len(str(last_number)), 6)
    rendered = []
    for offset, line in enumerate(lines):
        if max_line_chars and len(line) > max_line_chars:
            line = line[:max_line_chars] + "... (line truncated)"
        rendered.append(f"{str(start_index + offset + 1).rjust(width)}\t{line}")
    return "\n".join(rendered)


class FileTools:
    """Tools for file operations including read, write, list, and information."""
    
    def __init__(self, workspace=None):
        """Initialize FileTools with optional workspace containment.
        
        Args:
            workspace: Optional Workspace instance for path containment
        """
        self._workspace = workspace
    
    def _require_workspace_access(self, *, write: bool) -> None:
        """Check workspace access permissions for read/write operations."""
        if self._workspace is None:
            return
        access = getattr(self._workspace, "access", "rw")
        if access == "none":
            raise PermissionError("Workspace access is disabled")
        if write and access != "rw":
            raise PermissionError(f"Workspace is not writable: access={access!r}")

    def _validate_path(self, filepath: str) -> str:
        """
        Validate and normalize a file path to prevent path traversal attacks.
        
        Args:
            filepath: Path to validate
            
        Returns:
            str: Normalized absolute path
            
        Raises:
            ValueError: If path contains suspicious patterns
        """
        # If workspace is configured, use workspace validation
        if self._workspace is not None:
            return str(self._workspace.resolve(filepath))
        
        # Fallback to basic validation (when workspace=None)
        # Expand ~ to user home directory FIRST (before any validation)
        if filepath.startswith('~'):
            filepath = os.path.expanduser(filepath)
        
        # Check for path traversal attempts BEFORE normalization
        # We check the original input for '..' to catch traversal attempts
        if '..' in filepath:
            raise ValueError(f"Path traversal detected: {filepath}")
        
        # Normalize the path and securely resolve symlinks
        normalized = os.path.normpath(filepath)
        absolute = os.path.realpath(normalized)
        
        # Prevent path traversal outside current workspace / allowed directories
        cwd = os.path.abspath(os.getcwd())
        if os.path.commonpath([absolute, cwd]) != cwd:
            raise ValueError(f"Path traversal detected: {filepath} escapes workspace {cwd}")
        
        return absolute

    @staticmethod
    def _content_hash(safe_path: str, encoding: str = 'utf-8') -> str:
        """Hash the on-disk content in the same form EditTools records.

        Reads bytes, strips a UTF-8 BOM, and hashes the decoded string with
        line endings preserved.  This matches ``EditTools`` (which reads in
        binary mode) so the shared staleness registry stays consistent when a
        file is read by one tool and written by the other.
        """
        with open(safe_path, 'rb') as f:
            raw_bytes = f.read()
        if raw_bytes.startswith(b'\xef\xbb\xbf'):
            raw_bytes = raw_bytes[3:]
        content = raw_bytes.decode(encoding)
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def read_file(self, filepath: str, encoding: str = 'utf-8',
                  offset: Optional[int] = None, limit: Optional[int] = None,
                  line_numbers: bool = True,
                  max_line_chars: int = DEFAULT_MAX_LINE_CHARS) -> str:
        """
        Read content from a file (coding-grade, windowed + line-numbered).

        By default the content is returned with a right-aligned line-number
        gutter so a coding agent can reference exact lines for subsequent
        edits, and a sensible line cap keeps a whole-file read from blowing the
        context budget.  Pass ``line_numbers=False`` (with no ``offset``/
        ``limit``) to get the exact plain-string content as before.

        Args:
            filepath: Path to the file
            encoding: File encoding (default: utf-8)
            offset: 1-based first line to read (default: start of file)
            limit: Maximum number of lines to read (default: up to
                ``DEFAULT_MAX_LINES`` lines from ``offset``)
            line_numbers: Prefix each line with its 1-based number (default:
                True).  Set False to return raw content.
            max_line_chars: Truncate any single line longer than this many
                characters (default: ``DEFAULT_MAX_LINE_CHARS``)

        Returns:
            str: Content of the requested window.  When truncated, a trailing
            hint tells the model how to page for the rest via ``offset``.
        """
        try:
            # Validate path to prevent traversal attacks
            safe_path = self._validate_path(filepath)
            # Serialise with concurrent writers on this path so the read does
            # not observe a partially-written file.
            with _file_locks.get_lock(safe_path):
                with open(safe_path, 'r', encoding=encoding) as f:
                    data = f.read()
                # Record the read hash so a later write engages the staleness
                # guard.  Hash the on-disk byte form (CRLF preserved, BOM
                # stripped) so the recorded hash matches what EditTools (binary
                # mode) records for the same file, keeping the staleness guard
                # consistent across tools.
                try:
                    _file_locks.record_read_hash(
                        safe_path, self._content_hash(safe_path, encoding))
                except Exception:
                    pass

            # Fast path: preserve the exact legacy shape when the caller asks
            # for raw content of the whole file (no window requested).
            if not line_numbers and offset is None and limit is None:
                return data

            lines = data.splitlines()
            total = len(lines)

            # Clamp the 1-based offset into range; treat <=0 / None as start.
            start = (offset - 1) if offset and offset > 0 else 0
            if start > total:
                start = total
            if limit is not None and limit >= 0:
                end = start + limit
            else:
                end = start + DEFAULT_MAX_LINES
            end = min(end, total)

            window = lines[start:end]
            if line_numbers:
                body = _render_with_line_numbers(window, start, max_line_chars)
            else:
                body = "\n".join(window)

            # Tell the model how to page when the window does not reach EOF.
            if end < total:
                if body:
                    body += "\n"
                body += (
                    f"... (showing lines {start + 1}-{end} of {total}; "
                    f"call again with offset={end + 1} for more)"
                )
            return body
        except Exception as e:
            error_msg = f"Error reading file {filepath}: {str(e)}"
            logging.error(error_msg)
            return error_msg

    @require_approval(risk_level="high")
    def write_file(self, filepath: str, content: str, encoding: str = 'utf-8',
                   force: bool = False) -> bool:
        """
        Write content to a file.
        
        The write runs under a per-file lock shared with the edit tools, so a
        concurrent edit/write to the same path serialises instead of racing.
        If the file already exists and was previously read via these tools, the
        write aborts when the on-disk content changed since that read, unless
        ``force=True`` is passed.
        
        Args:
            filepath: Path to the file
            content: Content to write
            encoding: File encoding (default: utf-8)
            force: Bypass the automatic staleness guard for a blind overwrite
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check workspace permissions for write operations
            self._require_workspace_access(write=True)
            # Validate path to prevent traversal attacks
            safe_path = self._validate_path(filepath)
            # Auto-coerce non-string content (LLMs sometimes pass dicts/lists)
            if not isinstance(content, str):
                if isinstance(content, (dict, list)):
                    content = json.dumps(content, indent=2, ensure_ascii=False)
                else:
                    content = str(content)
            # Serialise concurrent writes/edits on this canonical path.
            with _file_locks.get_lock(safe_path):
                # Automatic staleness guard for existing files.
                if not force and os.path.exists(safe_path):
                    recorded = _file_locks.get_read_hash(safe_path)
                    if recorded is not None:
                        # Fail closed: if the verification re-read raises (decode,
                        # permission, etc.) refuse the write rather than blindly
                        # clobbering the file.
                        try:
                            current = self._content_hash(safe_path, encoding)
                        except Exception as e:
                            logging.error(
                                "Refusing to write %s: could not verify staleness: %s",
                                filepath, e)
                            return False
                        if current != recorded:
                            logging.error(
                                "Refusing to write %s: file changed since it was "
                                "read - re-read before writing (or pass force=True)",
                                filepath)
                            return False
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(safe_path), exist_ok=True)
                with open(safe_path, 'w', encoding=encoding) as f:
                    f.write(content)
                # Record the new content hash (in the on-disk byte form) so
                # follow-up writes are not falsely flagged stale and the hash
                # matches what a later read by either tool computes.
                try:
                    _file_locks.record_read_hash(
                        safe_path, self._content_hash(safe_path, encoding))
                except Exception:
                    pass
            return True
        except Exception as e:
            error_msg = f"Error writing to file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

    def list_files(self, directory: str, pattern: Optional[str] = None) -> List[Dict[str, Union[str, int]]]:
        """
        List files in a directory with optional pattern matching.
        
        Args:
            directory: Directory path
            pattern: Optional glob pattern (e.g., "*.txt")
            
        Returns:
            List[Dict]: List of file information dictionaries
        """
        try:
            # Validate directory path
            safe_dir = self._validate_path(directory)
            path = Path(safe_dir)
            if pattern:
                pattern_path = Path(pattern)
                if pattern_path.is_absolute() or any(
                    part == ".." or part.startswith("..")
                    for part in pattern_path.parts
                ):
                    raise ValueError(f"Invalid file pattern: {pattern}")
                files = path.glob(pattern)
            else:
                files = path.iterdir()

            result = []
            for file in files:
                if file.is_file():
                    stat = file.stat()
                    result.append({
                        'name': file.name,
                        'path': str(file),
                        'size': stat.st_size,
                        'modified': stat.st_mtime,
                        'created': stat.st_ctime
                    })
            return result
        except Exception as e:
            error_msg = f"Error listing files in {directory}: {str(e)}"
            logging.error(error_msg)
            return [{'error': error_msg}]

    def get_file_info(self, filepath: str) -> Dict[str, Union[str, int]]:
        """
        Get detailed information about a file.
        
        Args:
            filepath: Path to the file
            
        Returns:
            Dict: File information including size, dates, etc.
        """
        try:
            # Validate file path
            safe_path = self._validate_path(filepath)
            path = Path(safe_path)
            if not path.exists():
                return {'error': f'File not found: {filepath}'}
            
            stat = path.stat()
            return {
                'name': path.name,
                'path': str(path),
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'created': stat.st_ctime,
                'is_file': path.is_file(),
                'is_dir': path.is_dir(),
                'extension': path.suffix,
                'parent': str(path.parent)
            }
        except Exception as e:
            error_msg = f"Error getting file info for {filepath}: {str(e)}"
            logging.error(error_msg)
            return {'error': error_msg}

    @require_approval(risk_level="high")
    def copy_file(self, src: str, dst: str) -> bool:
        """
        Copy a file from source to destination.
        
        Args:
            src: Source file path
            dst: Destination file path
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check workspace permissions for write operations
            self._require_workspace_access(write=True)
            # Validate paths to prevent traversal attacks
            safe_src = self._validate_path(src)
            safe_dst = self._validate_path(dst)
            # Create destination directory if it doesn't exist
            os.makedirs(os.path.dirname(safe_dst), exist_ok=True)
            shutil.copy2(safe_src, safe_dst)
            return True
        except Exception as e:
            error_msg = f"Error copying file from {src} to {dst}: {str(e)}"
            logging.error(error_msg)
            return False

    @require_approval(risk_level="high")
    def move_file(self, src: str, dst: str) -> bool:
        """
        Move a file from source to destination.
        
        Args:
            src: Source file path
            dst: Destination file path
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check workspace permissions for write operations
            self._require_workspace_access(write=True)
            # Validate paths to prevent traversal attacks
            safe_src = self._validate_path(src)
            safe_dst = self._validate_path(dst)
            # Create destination directory if it doesn't exist
            os.makedirs(os.path.dirname(safe_dst), exist_ok=True)
            shutil.move(safe_src, safe_dst)
            return True
        except Exception as e:
            error_msg = f"Error moving file from {src} to {dst}: {str(e)}"
            logging.error(error_msg)
            return False

    @require_approval(risk_level="high")
    def delete_file(self, filepath: str) -> bool:
        """
        Delete a file.
        
        Args:
            filepath: Path to the file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check workspace permissions for write operations
            self._require_workspace_access(write=True)
            # Validate path to prevent traversal attacks
            safe_path = self._validate_path(filepath)
            os.remove(safe_path)
            return True
        except Exception as e:
            error_msg = f"Error deleting file {filepath}: {str(e)}"
            logging.error(error_msg)
            return False

    @require_approval(risk_level="medium")
    def download_file(
        self,
        url: str,
        destination: str,
        timeout: int = 30,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Union[bool, str, int]]:
        """
        Download a file from a URL.
        
        Args:
            url: URL to download from
            destination: Local path to save the file
            timeout: Request timeout in seconds
            progress_callback: Optional callback for progress updates
                              Called with (bytes_downloaded, total_bytes)
            
        Returns:
            Dict with keys: success, path, size, error
        """
        try:
            import httpx
        except ImportError:
            return {
                "success": False,
                "path": "",
                "size": 0,
                "error": "httpx not installed. Install with: pip install httpx"
            }
        
        try:
            # Check workspace permissions for write operations
            self._require_workspace_access(write=True)
            # Validate destination path
            safe_path = self._validate_path(destination)
            
            # Validate URL to prevent SSRF
            from urllib.parse import urlparse
            import ipaddress
            import socket
            
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return {
                    "success": False, "path": "", "size": 0,
                    "error": f"Unsupported URL scheme: {parsed.scheme}. Only http/https allowed."
                }
            
            hostname = parsed.hostname or ""
            # Resolve hostname and check for private/reserved IPs
            try:
                resolved = socket.getaddrinfo(hostname, parsed.port or 443)
                for family, _, _, _, sockaddr in resolved:
                    addr = ipaddress.ip_address(sockaddr[0])
                    if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
                        return {
                            "success": False, "path": "", "size": 0,
                            "error": f"Access to private/internal addresses is blocked: {hostname}"
                        }
            except (socket.gaierror, ValueError):
                pass  # Let httpx handle DNS failures naturally
            
            # Block cloud metadata endpoints
            _blocked_hosts = {"169.254.169.254", "metadata.google.internal", "metadata.google.com"}
            if hostname in _blocked_hosts:
                return {
                    "success": False, "path": "", "size": 0,
                    "error": f"Access to metadata service is blocked: {hostname}"
                }
            
            # Create directory if needed
            os.makedirs(os.path.dirname(safe_path) or ".", exist_ok=True)
            
            # Download file
            with httpx.stream("GET", url, timeout=timeout, follow_redirects=False) as response:
                response.raise_for_status()
                
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0
                
                with open(safe_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback and total_size:
                            progress_callback(downloaded, total_size)
            
            return {
                "success": True,
                "path": safe_path,
                "size": downloaded,
                "error": ""
            }
            
        except Exception as e:
            error_msg = f"Error downloading {url}: {str(e)}"
            logging.error(error_msg)
            return {
                "success": False,
                "path": "",
                "size": 0,
                "error": error_msg
            }

# Create default instance for direct function access
_file_tools = FileTools()
read_file = _file_tools.read_file
write_file = _file_tools.write_file
list_files = _file_tools.list_files
get_file_info = _file_tools.get_file_info
copy_file = _file_tools.copy_file
move_file = _file_tools.move_file
delete_file = _file_tools.delete_file
download_file = _file_tools.download_file


def create_file_tools(workspace=None):
    """Create FileTools instance with optional workspace containment.
    
    Args:
        workspace: Optional Workspace instance for path containment
        
    Returns:
        FileTools instance configured with workspace
    """
    return FileTools(workspace=workspace)

if __name__ == "__main__":
    # Example usage
    print("\n==================================================")
    print("FileTools Demonstration")
    print("==================================================\n")

    # Create a test directory
    test_dir = os.path.join(os.getcwd(), "test_files")
    os.makedirs(test_dir, exist_ok=True)
    
    # Create test files
    test_file = os.path.join(test_dir, "test_file.txt")
    test_content = "Hello, this is a test file!"
    
    print("1. Writing to file")
    print("------------------------------")
    success = write_file(test_file, test_content)
    print(f"Write successful: {success}\n")
    
    print("2. Reading from file")
    print("------------------------------")
    content = read_file(test_file)
    print(f"Content: {content}\n")
    
    print("3. File Information")
    print("------------------------------")
    info = get_file_info(test_file)
    print(json.dumps(info, indent=2))
    print()
    
    print("4. Listing Files")
    print("------------------------------")
    files = list_files(test_dir, "*.txt")
    for file in files:
        print(f"Found: {file['name']} ({file['size']} bytes)")
    print()
    
    print("5. Copying File")
    print("------------------------------")
    copy_file_path = os.path.join(test_dir, "test_file_copy.txt")
    copy_success = copy_file(test_file, copy_file_path)
    print(f"Copy successful: {copy_success}\n")
    
    print("6. Moving File")
    print("------------------------------")
    move_file_path = os.path.join(test_dir, "test_file_moved.txt")
    move_success = move_file(copy_file_path, move_file_path)
    print(f"Move successful: {move_success}\n")
    
    print("7. Deleting Files")
    print("------------------------------")
    delete_success = delete_file(test_file)
    print(f"Delete original successful: {delete_success}")
    delete_success = delete_file(move_file_path)
    print(f"Delete moved file successful: {delete_success}\n")
    
    # Clean up test directory
    try:
        shutil.rmtree(test_dir)
        print("Test directory cleaned up successfully")
    except Exception as e:
        print(f"Error cleaning up test directory: {str(e)}")
    
    print("\n==================================================")
    print("Demonstration Complete")
    print("==================================================")
