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

# Minimum similarity ratio for an accepted block-anchor (fuzzy) match.
_BLOCK_ANCHOR_THRESHOLD = 0.7

# Maximum characters of diagnostics output appended to a tool result.
_DIAGNOSTICS_MAX_CHARS = 2000

# Seconds before a diagnostics subprocess is abandoned.
_DIAGNOSTICS_TIMEOUT = 10


class EditTools:
    """Tools for file editing and patching operations."""
    
    def __init__(self, workspace=None, post_edit_diagnostics: str = "auto"):
        """Initialize EditTools with optional workspace containment.
        
        Args:
            workspace: Optional Workspace instance for path containment
            post_edit_diagnostics: When to run a lightweight, language-appropriate
                check on a file after a successful edit/patch and append the
                results to the tool output. One of:
                - ``"auto"`` (default): run a checker if one is available, but
                  only append a ``Diagnostics`` section when problems are found
                  (so clean edits return the plain success string — backward
                  compatible).
                - ``"on"``: always append a ``Diagnostics`` section when a
                  checker is available, even if it reports no problems.
                - ``"off"``: never run diagnostics (zero overhead).
                Checkers are auto-detected by file type and silently skipped
                when unavailable; a missing linter never fails the edit.
        """
        self._workspace = workspace
        self._file_cache = {}  # Cache for staleness checking
        mode = (post_edit_diagnostics or "auto")
        if isinstance(mode, str):
            mode = mode.lower()
        if mode not in ("auto", "on", "off"):
            mode = "auto"
        self._post_edit_diagnostics = mode
    
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

    @staticmethod
    def _decode_with_bom(raw_bytes: bytes) -> Tuple[str, bytes]:
        """Decode UTF-8 bytes, returning (content, bom_prefix).

        Raises ValueError for unsupported UTF-16 BOMs so callers can surface a
        friendly error.  Mirrors the BOM handling in ``edit_file`` so both
        entry points behave identically.
        """
        bom = b''
        if raw_bytes.startswith(b'\xef\xbb\xbf'):  # UTF-8 BOM
            bom = b'\xef\xbb\xbf'
            raw_bytes = raw_bytes[3:]
        elif raw_bytes.startswith(b'\xff\xfe') or raw_bytes.startswith(b'\xfe\xff'):
            raise ValueError("UTF-16 encoding is not supported. Please convert the file to UTF-8.")
        return raw_bytes.decode('utf-8'), bom

    def _encode_preserving(self, content: str, line_ending: str, bom: bytes) -> bytes:
        """Encode ``content`` back to bytes, re-applying line ending and BOM."""
        if line_ending == '\r\n':
            content = content.replace('\r\n', '\n').replace('\n', '\r\n')
        return bom + content.encode('utf-8')
    
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
    # Post-edit diagnostics
    #
    # After a successful mutation we optionally run a lightweight, language
    # appropriate check on the single modified file and surface concise
    # diagnostics so an agent can self-correct within the same loop.  All
    # imports are deferred and any failure is swallowed: a missing or broken
    # checker must never turn a successful edit into a failure.
    # ------------------------------------------------------------------

    @staticmethod
    def _diagnostics_command(safe_path: str) -> Optional[Tuple[str, List[str]]]:
        """Resolve a (tool_name, argv) checker for ``safe_path`` by extension.

        Returns ``None`` when no checker is available for the file type or none
        of the candidate executables are installed.  Lazy-imports ``shutil``.
        """
        import shutil

        ext = os.path.splitext(safe_path)[1].lower()
        # Ordered candidates per extension: first installed executable wins.
        candidates: List[Tuple[str, List[str]]] = []
        if ext in (".py", ".pyi"):
            if shutil.which("ruff"):
                # Restrict to error-class rules (pyflakes/syntax) so that
                # stylistically-imperfect-but-valid edits do not flood output;
                # this keeps behaviour close to a syntax gate. ``--no-cache``
                # avoids polluting the workspace.
                candidates.append((
                    "ruff",
                    ["ruff", "check", "--quiet", "--no-cache",
                     "--select", "E9,F63,F7,F82", safe_path],
                ))
            # py_compile is always available via the running interpreter and
            # catches syntax errors with zero third-party dependencies.
            import sys
            candidates.append(("py_compile", [sys.executable, "-m", "py_compile", safe_path]))
        elif ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            if shutil.which("eslint"):
                # ``--no-config-lookup`` prevents ESLint from discovering and
                # executing repository-controlled config/plugins (arbitrary code
                # execution risk in untrusted workspaces).
                candidates.append((
                    "eslint",
                    ["eslint", "--no-config-lookup", safe_path],
                ))
            if shutil.which("tsc") and ext in (".ts", ".tsx"):
                # Per-file invocation without a project ``tsconfig.json``: relax
                # project-config coupling so a single valid file does not report
                # spurious "no inputs"/missing-lib errors.
                candidates.append((
                    "tsc",
                    ["tsc", "--noEmit", "--skipLibCheck", "--allowJs",
                     "--target", "ESNext", "--moduleResolution", "node",
                     safe_path],
                ))
        elif ext == ".json":
            # Validate JSON with the stdlib; emitted via a tiny inline check.
            import sys
            candidates.append((
                "json",
                [sys.executable, "-c",
                 "import json,sys;json.load(open(sys.argv[1]))", safe_path],
            ))

        for tool_name, argv in candidates:
            exe = argv[0]
            if os.path.isabs(exe) or shutil.which(exe):
                return tool_name, argv
        return None

    def _run_diagnostics(self, safe_path: str, display_path: str) -> str:
        """Run a checker on ``safe_path`` and return a bounded diagnostics block.

        Returns an empty string when diagnostics are disabled, no checker is
        available, or (in ``auto`` mode) the checker reports no problems.  Any
        exception is logged and swallowed so the edit result is never lost.
        """
        if self._post_edit_diagnostics == "off":
            return ""
        try:
            resolved = self._diagnostics_command(safe_path)
            if resolved is None:
                return ""
            tool_name, argv = resolved

            import subprocess
            try:
                proc = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=_DIAGNOSTICS_TIMEOUT,
                    cwd=os.path.dirname(safe_path) or None,
                )
            except (subprocess.TimeoutExpired, OSError) as e:
                logger.debug("Diagnostics skipped for %s: %s", display_path, e)
                return ""

            output = (proc.stdout or "") + (proc.stderr or "")
            output = output.strip()
            # Replace absolute paths with the display path for cleaner output.
            if output and safe_path != display_path:
                output = output.replace(safe_path, display_path)

            has_problems = proc.returncode != 0 or bool(output)
            if not has_problems:
                if self._post_edit_diagnostics == "on":
                    return f"\n\nDiagnostics ({tool_name}): no problems found"
                return ""

            if not output:
                output = f"check failed (exit code {proc.returncode})"
            if len(output) > _DIAGNOSTICS_MAX_CHARS:
                output = output[:_DIAGNOSTICS_MAX_CHARS] + "\n... (diagnostics truncated)"
            return f"\n\nDiagnostics ({tool_name}):\n{output}"
        except Exception as e:  # never let diagnostics break a successful edit
            logger.debug("Diagnostics error for %s: %s", display_path, e)
            return ""

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
        norm_old = [transform(line) for line in old_lines]
        norm_content = [transform(line.rstrip('\n').rstrip('\r')) for line in content_lines]

        n = len(norm_old)
        spans = []
        for i in range(len(norm_content) - n + 1):
            if norm_content[i:i + n] == norm_old:
                start = offsets[i][0]
                # Exclude the last matched line's terminator from the span so
                # the replacement (which carries no trailing newline) does not
                # consume it and merge with the following line.
                last = content_lines[i + n - 1]
                term = len(last) - len(last.rstrip('\r\n'))
                end = offsets[i + n - 1][1] - term
                spans.append((start, end))
        return spans

    def _line_trimmed(self, content: str, old: str) -> List[Tuple[int, int]]:
        """Strategy 2: match ignoring leading/trailing whitespace per line."""
        return self._line_block_match(content, old, lambda line: line.strip())

    def _ws_normalised(self, content: str, old: str) -> List[Tuple[int, int]]:
        """Strategy 3: match collapsing all internal whitespace runs."""
        def norm(line):
            return re.sub(r'\s+', ' ', line).strip()
        return self._line_block_match(content, old, norm)

    def _indent_flexible(self, content: str, old: str) -> List[Tuple[int, int]]:
        """Strategy 4: match ignoring indentation but preserving inner text.

        Normalises tabs/spaces indentation and the relative structure so a
        block indented differently than ``old_string`` still matches.
        """
        def norm(line):
            return line.replace('\t', '    ').strip()
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
        stripped = [line.rstrip('\n').rstrip('\r').strip() for line in content_lines]
        first_anchor = old_lines[0].strip()
        last_anchor = old_lines[-1].strip()
        if not first_anchor or not last_anchor:
            return []

        n = len(old_lines)
        target = '\n'.join(line.strip() for line in old_lines)
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
                ratio = difflib.SequenceMatcher(None, candidate, target).ratio()
                if ratio >= _BLOCK_ANCHOR_THRESHOLD:
                    # Exclude the closing line's terminator from the span so
                    # the replacement does not swallow the following newline.
                    last = content_lines[j]
                    term = len(last) - len(last.rstrip('\r\n'))
                    candidates.append((ratio, offsets[i][0], offsets[j][1] - term))
                # Continue scanning: a later matching last_anchor may yield a
                # higher-similarity block, and breaking here would skip it.

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
              produces at least one match; callers inspect the span count to
              decide ambiguity (more than one span = ambiguous).
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
            
            result = f"Success: Made {replacements} replacement(s) in {filepath}\n\nDiff:\n{diff}"
            return result + self._run_diagnostics(safe_path, filepath)
            
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

        _SENTINELS = ("*** Begin Patch", "*** End Patch")

        def _header(line):
            for op, prefix in (("add", "*** Add File:"),
                               ("update", "*** Update File:"),
                               ("delete", "*** Delete File:")):
                if line.strip().startswith(prefix):
                    return op, line.split(":", 1)[1].strip()
            return None, None

        def _is_boundary(line):
            """A line that terminates a body/hunk: a header or a sentinel."""
            return _header(line)[0] is not None or line.strip() in _SENTINELS

        while i < n:
            line = lines[i]
            if not line.strip() or line.strip() in _SENTINELS:
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
                while i < n and not _is_boundary(lines[i]):
                    body.append(lines[i])
                    i += 1
                ops.append({"op": "add", "path": path, "content": "\n".join(body)})
            elif op == "update":
                hunks = []
                while i < n and not _is_boundary(lines[i]):
                    if lines[i].strip().startswith("@@"):
                        i += 1
                        old_block, new_block = [], []
                        in_new = False
                        while i < n and not lines[i].strip().startswith("@@") and not _is_boundary(lines[i]):
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
        is valid are the changes committed to disk.  The commit phase stages
        writes/deletes and rolls them back if any step fails, so on any error
        the filesystem is left in its original state.  BOM and CRLF line
        endings are preserved on Update, matching ``edit_file``.

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
            # Each planned entry: (kind, safe_path, display, encoded_bytes,
            # diff, content_hash). encoded_bytes is None for deletes.
            planned = []
            for op in ops:
                safe_path = self._validate_path(op["path"])

                if op["op"] == "add":
                    if os.path.exists(safe_path):
                        return f"Error: Cannot add '{op['path']}': file already exists"
                    encoded = op["content"].encode('utf-8')
                    planned.append(("add", safe_path, op["path"], encoded,
                                    self._render_diff("", op["content"], op["path"]),
                                    self._compute_content_hash(op["content"])))

                elif op["op"] == "delete":
                    if not os.path.exists(safe_path):
                        return f"Error: Cannot delete '{op['path']}': file not found"
                    planned.append(("delete", safe_path, op["path"], None, "", None))

                elif op["op"] == "update":
                    if not os.path.exists(safe_path):
                        return f"Error: Cannot update '{op['path']}': file not found"
                    # Read in binary to preserve BOM/CRLF like edit_file does.
                    with open(safe_path, 'rb') as f:
                        raw_bytes = f.read()
                    try:
                        original, bom = self._decode_with_bom(raw_bytes)
                    except ValueError as e:
                        return f"Error: Cannot update '{op['path']}': {e}"
                    line_ending = self._detect_line_ending(original)
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
                    encoded = self._encode_preserving(updated, line_ending, bom)
                    planned.append(("update", safe_path, op["path"], encoded,
                                    self._render_diff(original, updated, op["path"]),
                                    self._compute_content_hash(updated)))

            # Phase 2: commit all operations atomically.  Writes are staged to
            # temp files in the same directory and swapped in with os.replace;
            # deletes are staged by renaming the original aside.  If any step
            # fails, all already-applied operations are rolled back so the
            # filesystem is left untouched.
            messages = []
            applied = []  # rollback log: (action, *paths)
            tmp_suffix = ".praison_patch_tmp"
            try:
                for kind, safe_path, display, encoded, diff, content_hash in planned:
                    if kind == "delete":
                        backup = safe_path + tmp_suffix
                        os.replace(safe_path, backup)
                        applied.append(("delete", safe_path, backup))
                        self._file_cache.pop(safe_path, None)
                        messages.append(f"Deleted {display}")
                    else:
                        os.makedirs(os.path.dirname(safe_path) or ".", exist_ok=True)
                        tmp_path = safe_path + tmp_suffix
                        existed = os.path.exists(safe_path)
                        backup = safe_path + ".praison_patch_bak" if existed else None
                        try:
                            with open(tmp_path, 'wb') as f:
                                f.write(encoded)
                            if existed:
                                os.replace(safe_path, backup)
                            os.replace(tmp_path, safe_path)
                        except Exception:
                            # Clean up any partially-staged temp file before
                            # propagating to the rollback handler.
                            if os.path.exists(tmp_path):
                                try:
                                    os.remove(tmp_path)
                                except OSError:
                                    pass
                            raise
                        applied.append(("write", safe_path, backup))
                        self._file_cache[safe_path] = content_hash
                        verb = "Added" if kind == "add" else "Updated"
                        diagnostics = self._run_diagnostics(safe_path, display)
                        messages.append(f"{verb} {display}\n{diff}{diagnostics}")
            except Exception:
                # Roll back in reverse order to restore the original state.
                for entry in reversed(applied):
                    action, target = entry[0], entry[1]
                    backup = entry[2]
                    try:
                        if action == "delete":
                            os.replace(backup, target)
                        elif action == "write":
                            if backup is not None:
                                os.replace(backup, target)
                            elif os.path.exists(target):
                                os.remove(target)
                    except OSError:
                        logger.error("Rollback failed for %s", target)
                raise

            # Success: discard delete backups and write backups.
            for entry in applied:
                action, backup = entry[0], entry[2]
                if backup is not None and os.path.exists(backup):
                    try:
                        os.remove(backup)
                    except OSError:
                        pass

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


def create_edit_tools(workspace=None, post_edit_diagnostics: str = "auto") -> EditTools:
    """Create EditTools instance with optional workspace containment.
    
    Args:
        workspace: Optional Workspace instance for path containment
        post_edit_diagnostics: Diagnostics mode ("auto"|"on"|"off"); see
            ``EditTools.__init__`` for details.
        
    Returns:
        EditTools instance configured with workspace
    """
    return EditTools(workspace=workspace, post_edit_diagnostics=post_edit_diagnostics)