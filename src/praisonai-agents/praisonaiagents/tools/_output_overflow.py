"""Shared helper for preserving large tool/command output.

When a built-in tool produces more output than its budget allows, the middle
of the output is frequently where the actual error lives (a failing assertion
or a stack trace buried in verbose build/test output). Discarding it makes the
agent blind to exactly what it needs.

Instead of dropping the middle, :func:`spill` writes the *full* output to a
retrievable, session-scoped artifact and :func:`bounded_with_pointer` returns a
bounded head/tail preview plus a pointer telling the model to read/grep the
artifact for the omitted region. Nothing is lost and the context window stays
bounded.

There is **zero overhead** when output is within budget: callers only invoke
these helpers on the overflow branch.
"""

import os
import atexit
import logging
import tempfile
from pathlib import Path
from typing import Optional

__all__ = ["get_spill_dir", "spill", "bounded_with_pointer"]

_SPILL_SUBDIR = "praisonai_tool_output"

# Artifacts created by *this* process, pruned on interpreter exit so a
# long-running agent that repeatedly overflows does not exhaust temp space.
# Callers that set ``PRAISONAI_TOOL_OUTPUT_DIR`` for cross-session retrieval
# remain responsible for their own retention policy.
_PROCESS_SPILL_FILES: "set[Path]" = set()
_ATEXIT_REGISTERED = False


def _cleanup_process_spills() -> None:
    for artifact in list(_PROCESS_SPILL_FILES):
        try:
            artifact.unlink()
        except OSError:
            pass
        _PROCESS_SPILL_FILES.discard(artifact)


def get_spill_dir(spill_dir: Optional[str] = None) -> Path:
    """Return the directory used to persist overflow artifacts.

    Resolution order:
    1. Explicit ``spill_dir`` argument.
    2. ``PRAISONAI_TOOL_OUTPUT_DIR`` environment variable (session/workspace
       scoped by the caller).
    3. A stable subdirectory under the system temp dir.

    The directory is created if it does not already exist. If the resolved
    directory cannot be created, a fresh unique temp directory is used so the
    fallback never retries the same failing path.
    """
    base = spill_dir or os.environ.get("PRAISONAI_TOOL_OUTPUT_DIR")
    if base:
        path = Path(base)
    else:
        path = Path(tempfile.gettempdir()) / _SPILL_SUBDIR
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # Target a genuinely different location instead of retrying the same
        # path (which would fail identically, e.g. a file already occupies it).
        logging.warning(
            "Spill dir %s unavailable (%s); using a fresh temp directory.",
            path, exc,
        )
        path = Path(tempfile.mkdtemp(prefix=f"{_SPILL_SUBDIR}_"))
    return path


def spill(output: str, kind: str = "output", spill_dir: Optional[str] = None) -> Optional[Path]:
    """Persist the full ``output`` to a retrievable artifact.

    Args:
        output: The complete output to preserve.
        kind: Short label for the artifact (e.g. ``"stdout"``, ``"stderr"``,
            ``"read_file"``) used in the filename.
        spill_dir: Optional directory override (see :func:`get_spill_dir`).

    Returns:
        The path to the written artifact, or ``None`` if persistence failed
        (the caller should then fall back to in-line truncation).
    """
    try:
        directory = get_spill_dir(spill_dir)
        # Deterministic-ish unique name; NamedTemporaryFile avoids collisions
        # across concurrent tool calls without extra locking.
        safe_kind = "".join(c if c.isalnum() or c in "-_" else "_" for c in kind) or "output"
        fd, name = tempfile.mkstemp(
            prefix=f"{safe_kind}_", suffix=".txt", dir=str(directory)
        )
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as f:
            f.write(output)
        artifact = Path(name)
        global _ATEXIT_REGISTERED
        if not _ATEXIT_REGISTERED:
            atexit.register(_cleanup_process_spills)
            _ATEXIT_REGISTERED = True
        _PROCESS_SPILL_FILES.add(artifact)
        return artifact
    except OSError as exc:
        logging.warning("Failed to spill tool output to artifact: %s", exc)
        return None


def bounded_with_pointer(
    output: str,
    max_output_size: int,
    path: Optional[Path],
    *,
    tail_size: Optional[int] = None,
) -> str:
    """Return a bounded head/tail preview plus a retrievable-artifact pointer.

    Args:
        output: The full (over-budget) output.
        max_output_size: Byte/char budget for the preview.
        path: Artifact path returned by :func:`spill`. If ``None`` (spill
            failed), the pointer is omitted and the classic head/tail preview
            is returned so no exception ever propagates.
        tail_size: Optional explicit tail length; defaults to
            ``min(max_output_size // 5, 500)``.

    Returns:
        A preview string small enough to keep the context window bounded.
    """
    total_chars = len(output)
    total_lines = output.count("\n") + 1

    if path is not None:
        pointer = (
            f"\n...[{total_chars:,} chars / {total_lines:,} lines truncated in preview]...\n"
            f"Full output saved to: {path}\n"
            f"Use read_file/grep on that path to inspect the omitted region "
            f"(do NOT re-run the command through head/tail).\n"
        )
    else:
        pointer = f"\n...[{total_chars:,} chars, showing first/last portions]...\n"

    # Reserve room for the pointer so head + pointer + tail stays within
    # ``max_output_size``. If the pointer alone would blow the budget (very
    # small ``max_output_size``), fall back to showing only the pointer.
    budget = max(0, max_output_size - len(pointer))

    if tail_size is None:
        tail_size = min(budget // 5, 500)
    tail_size = max(0, min(tail_size, budget))

    head = output[: budget - tail_size]
    tail = output[-tail_size:] if tail_size else ""

    return head + pointer + tail
