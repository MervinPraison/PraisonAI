"""File editing tools for fuzzy find-and-replace operations.

This module provides tools for making targeted edits to files,
supporting fuzzy matching and patch operations similar to those
used in skill management.
"""

import os
import re
import logging
import hashlib
import difflib
from typing import List, Optional, Tuple
from ..approval import require_approval

logger = logging.getLogger(__name__)

# Sentinel returned by span finders when more than one candidate matches.
_AMBIGUOUS = "AMBIGUOUS"

# Minimum similarity ratio for an accepted block-anchor (fuzzy) match.
_BLOCK_ANCHOR_THRESHOLD = 0.7


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
    
    # ------------------------------------------------------------------
    # Fuzzy matching ladder
    #
    # Each strategy receives the full file ``content`` and the target
    # ``old`` string and returns a list of ``(start, end)`` character spans
    # that the target maps onto.  ``_find_span`` walks the ladder in order
    # and stops at the first strategy yielding exactly one confident span.
    # ------------------------------------------------------------------

    @staticmethod
    def _exact(content: str, old: str) -> List[Tuple[int, int]]:
        """Strategy 1: byte-for-byte substring matches."""
        spans = []
        start = content.find(old)
        while start != -1:
            spans.append((start, start + len(old)))
            start = content.find(old, start + 1)
        return spans

    @staticmethod
    def _line_offsets(content: str) -> List[Tuple[int, int]]:
        """Return (start, end) char offsets for each line (keeping newline)."""
        offsets = []
        pos = 0
        for line in content.splitlines(keepends=True):
            offsets.append((pos, pos + len(line)))
            pos += len(line)
        return offsets

    def _line_block_match(self, content: str, old: str, transform) -> List[Tuple[int, int]]:
        """Generic line-block matcher.

        Compares ``old`` against the file line-by-line after applying
        ``transform`` to each line.  Returns char spans covering the whole
        matched block (from the start of the first line to the end of the
        last line).
        """
        old_lines = old.splitlines()
        if not old_lines:
            return []

        content_lines = content.splitlines(keepends=True)
        offsets = self._line_offsets(content)
        norm_old = [transform(l) for l in old_lines]
        norm_content = [transform(l.rstrip('\n').rstrip('\r')) for l in content_lines]

        n = len(norm_old)
        spans = []
        for i in range(len(norm_content) - n + 1):
            if norm_content[i:i + n] == norm_old:
                start = offsets[i][0]
                end = offsets[i + n - 1][1]
                spans.append((start, end))
        return spans

    def _line_trimmed(self, content: str, old: str) -> List[Tuple[int, int]]:
        """Strategy 2: match ignoring leading/trailing whitespace per line."""
        return self._line_block_match(content, old, lambda l: l.strip())

    def _ws_normalised(self, content: str, old: str) -> List[Tuple[int, int]]:
        """Strategy 3: match collapsing all internal whitespace runs."""
        norm = lambda l: re.sub(r'\s+', ' ', l).strip()
        return self._line_block_match(content, old, norm)

    def _indent_flexible(self, content: str, old: str) -> List[Tuple[int, int]]:
        """Strategy 4: match ignoring indentation but preserving inner text.

        Normalises tabs/spaces indentation and the relative structure so a
        block indented differently than ``old_string`` still matches.
        """
        norm = lambda l: l.replace('\t', '    ').strip()
        return self._line_block_match(content, old, norm)

    def _block_anchor(self, content: str, old: str) -> List[Tuple[int, int]]:
        """Strategy 5: similarity-scored block anchoring.

        Uses the first and last lines of ``old`` as anchors, then scores the
        enclosed candidate block with difflib.  Only returns a span when the
        single best candidate exceeds the similarity threshold and has a
        proportionate length, guarding against silent corruption.
        """
        old_lines = old.splitlines()
        if len(old_lines) < 2:
            return []

        content_lines = content.splitlines(keepends=True)
        offsets = self._line_offsets(content)
        stripped = [l.rstrip('\n').rstrip('\r').strip() for l in content_lines]
        first_anchor = old_lines[0].strip()
        last_anchor = old_lines[-1].strip()
        if not first_anchor or not last_anchor:
            return []

        n = len(old_lines)
        candidates = []
        for i, line in enumerate(stripped):
            if line != first_anchor:
                continue
            for j in range(i + 1, len(stripped)):
                if stripped[j] != last_anchor:
                    continue
                block_len = j - i + 1
                # Disproportionate-length guard.
                if block_len > n * 2 or block_len < max(2, n // 2):
                    continue
                candidate = '\n'.join(stripped[i:j + 1])
                target = '\n'.join(l.strip() for l in old_lines)
                ratio = difflib.SequenceMatcher(None, candidate, target).ratio()
                if ratio >= _BLOCK_ANCHOR_THRESHOLD:
                    candidates.append((ratio, offsets[i][0], offsets[j][1]))
                break

        if not candidates:
            return []
        candidates.sort(reverse=True)
        # If the top two candidates tie, treat as ambiguous (caller handles).
        if len(candidates) > 1 and abs(candidates[0][0] - candidates[1][0]) < 1e-9:
            return [(candidates[0][1], candidates[0][2]),
                    (candidates[1][1], candidates[1][2])]
        return [(candidates[0][1], candidates[0][2])]

    def _find_spans(self, content: str, old: str):
        """Walk the fuzzy ladder and return matching spans for ``old``.

        Returns:
            - list of (start, end) spans from the first strategy that
              produces at least one match;
            - ``_AMBIGUOUS`` is never returned here; callers inspect the
              span count to decide ambiguity.
            - empty list when no strategy matches.
        """
        strategies = (
            self._exact,
            self._line_trimmed,
            self._ws_normalised,
            self._indent_flexible,
            self._block_anchor,
        )
        for strategy in strategies:
            spans = strategy(content, old)
            if spans:
                return spans
        return []

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
            
            # Locate the target using the fuzzy matching ladder.  Exact
            # substring matches are preferred and behave exactly as before;
            # fuzzy strategies only engage when an exact match is not found.
            spans = self._find_spans(content, old_string)
            
            if not spans:
                preview = old_string[:50] + ("..." if len(old_string) > 50 else "")
                return f"Error: String not found in file: '{preview}'"
            
            occurrences = len(spans)
            
            # Check for ambiguous match
            if occurrences > 1 and not replace_all:
                preview = old_string[:30] + ("..." if len(old_string) > 30 else "")
                return (f"Error: Ambiguous match - '{preview}' occurs {occurrences} times. "
                       f"Please provide more surrounding context to make the match unique, "
                       f"or use replace_all=True to replace all occurrences.")
            
            # Perform replacement using located spans (apply right-to-left so
            # earlier offsets remain valid as we splice in new_string).
            if replace_all:
                new_content = content
                for start, end in sorted(spans, reverse=True):
                    new_content = new_content[:start] + new_string + new_content[end:]
                replacements = occurrences
            else:
                start, end = spans[0]
                new_content = content[:start] + new_string + content[end:]
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

    # ------------------------------------------------------------------
    # Multi-file structured patch
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_patch(patch: str):
        """Parse a structured multi-file patch into operations.

        Supported section headers (one operation each):

            *** Add File: path/to/file
            <full file content lines>

            *** Update File: path/to/file
            @@
            <old block>
            ===
            <new block>

            *** Delete File: path/to/file

        ``Update File`` may contain multiple ``@@`` hunks.  Returns a list of
        dicts: ``{"op", "path", ...}``.  Raises ``ValueError`` on malformed
        input.
        """
        lines = patch.splitlines()
        ops = []
        i = 0
        n = len(lines)

        def _header(line):
            for op, prefix in (("add", "*** Add File:"),
                               ("update", "*** Update File:"),
                               ("delete", "*** Delete File:")):
                if line.strip().startswith(prefix):
                    return op, line.split(":", 1)[1].strip()
            return None, None

        while i < n:
            line = lines[i]
            if not line.strip() or line.strip() == "*** Begin Patch" or line.strip() == "*** End Patch":
                i += 1
                continue
            op, path = _header(line)
            if op is None:
                raise ValueError(f"Unexpected line in patch (expected a section header): {line!r}")
            i += 1
            if op == "delete":
                ops.append({"op": "delete", "path": path})
            elif op == "add":
                body = []
                while i < n and _header(lines[i])[0] is None:
                    body.append(lines[i])
                    i += 1
                ops.append({"op": "add", "path": path, "content": "\n".join(body)})
            elif op == "update":
                hunks = []
                while i < n and _header(lines[i])[0] is None:
                    if lines[i].strip().startswith("@@"):
                        i += 1
                        old_block, new_block = [], []
                        in_new = False
                        while i < n and not lines[i].strip().startswith("@@") and _header(lines[i])[0] is None:
                            if lines[i].strip() == "===":
                                in_new = True
                                i += 1
                                continue
                            (new_block if in_new else old_block).append(lines[i])
                            i += 1
                        hunks.append(("\n".join(old_block), "\n".join(new_block)))
                    else:
                        i += 1
                ops.append({"op": "update", "path": path, "hunks": hunks})
        return ops

    @require_approval(risk_level="high")
    def apply_patch(self, patch: str) -> str:
        """Apply a structured multi-file patch atomically.

        The patch may Add, Update, and Delete multiple files in a single
        call.  All operations are validated first; only if every operation
        is valid are the changes committed to disk.  On any error nothing is
        written.

        Args:
            patch: Structured patch text (see ``_parse_patch`` for format).

        Returns:
            Combined success message with diffs, or an error description.
        """
        try:
            try:
                ops = self._parse_patch(patch)
            except ValueError as e:
                return f"Error: Invalid patch: {e}"

            if not ops:
                return "Error: Patch contains no operations"

            # Phase 1: validate every operation and compute new content.
            planned = []  # list of (op, safe_path, new_content_or_None, diff)
            for op in ops:
                safe_path = self._validate_path(op["path"])

                if op["op"] == "add":
                    if os.path.exists(safe_path):
                        return f"Error: Cannot add '{op['path']}': file already exists"
                    planned.append(("add", safe_path, op["path"], op["content"],
                                    self._render_diff("", op["content"], op["path"])))

                elif op["op"] == "delete":
                    if not os.path.exists(safe_path):
                        return f"Error: Cannot delete '{op['path']}': file not found"
                    planned.append(("delete", safe_path, op["path"], None, ""))

                elif op["op"] == "update":
                    if not os.path.exists(safe_path):
                        return f"Error: Cannot update '{op['path']}': file not found"
                    with open(safe_path, 'r', encoding='utf-8') as f:
                        original = f.read()
                    updated = original
                    for old_block, new_block in op["hunks"]:
                        if not old_block:
                            return f"Error: Empty hunk in update for '{op['path']}'"
                        spans = self._find_spans(updated, old_block)
                        if not spans:
                            preview = old_block[:50] + ("..." if len(old_block) > 50 else "")
                            return (f"Error: Hunk not found in '{op['path']}': '{preview}'")
                        if len(spans) > 1:
                            preview = old_block[:30] + ("..." if len(old_block) > 30 else "")
                            return (f"Error: Ambiguous hunk in '{op['path']}': '{preview}' "
                                   f"matches {len(spans)} locations")
                        start, end = spans[0]
                        updated = updated[:start] + new_block + updated[end:]
                    planned.append(("update", safe_path, op["path"], updated,
                                    self._render_diff(original, updated, op["path"])))

            # Phase 2: commit all operations.
            messages = []
            for kind, safe_path, display, new_content, diff in planned:
                if kind == "delete":
                    os.remove(safe_path)
                    self._file_cache.pop(safe_path, None)
                    messages.append(f"Deleted {display}")
                else:
                    os.makedirs(os.path.dirname(safe_path) or ".", exist_ok=True)
                    with open(safe_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    self._file_cache[safe_path] = self._compute_content_hash(new_content)
                    verb = "Added" if kind == "add" else "Updated"
                    messages.append(f"{verb} {display}\n{diff}")

            return "Success: Applied patch to {} file(s)\n\n{}".format(
                len(planned), "\n\n".join(messages))

        except Exception as e:
            error_msg = f"Error applying patch: {str(e)}"
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


@require_approval(risk_level="high")
def apply_patch(patch: str) -> str:
    """Apply a structured multi-file patch atomically (Add/Update/Delete).

    Args:
        patch: Structured patch text with ``*** Add File:``,
            ``*** Update File:`` and ``*** Delete File:`` sections.

    Returns:
        Combined success message with diffs or an error description.
    """
    return _edit_tools.apply_patch(patch)


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