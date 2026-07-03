"""Agent-callable code-navigation tools backed by the built-in LSP client.

These expose the *navigation* half of the Language Server Protocol client that
already ships in :mod:`praisonaiagents.lsp` (the *diagnostics* half is already
wired into the edit path).  For a CLI-first coding agent working in a large
codebase this replaces text ``grep`` for "where is this defined / who calls
this?" with language-server-accurate symbol resolution.

Tools:
    - ``lsp_definition(file_path, line=None, character=None, symbol=None)``
    - ``lsp_references(file_path, line=None, character=None, symbol=None)``
    - ``lsp_hover(file_path, line, character)``
    - ``lsp_document_symbols(file_path)``
    - ``lsp_workspace_symbols(query)``

All tools:
    - Are path-safe (contained to the workspace, no traversal).
    - Lazily import and spawn the LSP client only when a language server is
      actually installed for the file's language, degrading gracefully with a
      clear message otherwise (a missing server never raises).
    - Return compact, model-friendly strings (``file:line:col`` plus a snippet)
      rather than raw LSP JSON.

Usage::

    from praisonaiagents import Agent
    from praisonaiagents.tools import lsp_definition, lsp_references

    agent = Agent(name="coder", tools=[lsp_definition, lsp_references])

or directly::

    from praisonaiagents.tools import lsp_references
    print(lsp_references("src/mod.py", symbol="my_func"))
"""

from __future__ import annotations

import os
import re
import logging
from typing import List, Optional, Tuple

from .path_safety import resolve_within_root

logger = logging.getLogger(__name__)

# File extension -> LSP language id.  Mirrors the languages with a default
# server in ``lsp/config.py`` (DEFAULT_SERVERS) and the map used by the edit
# path's diagnostics hook, so tool availability tracks the diagnostics feature.
_LSP_LANGUAGE_BY_EXT = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
}

# Bound the number of navigation results returned to keep output agent-friendly.
_MAX_RESULTS = 100

# Seconds before an LSP exchange is abandoned so a slow/hung server never
# stalls a tool call.
_LSP_TIMEOUT = 15

# LSP SymbolKind -> short human label (subset most useful for navigation).
_SYMBOL_KIND = {
    1: "file", 2: "module", 3: "namespace", 4: "package", 5: "class",
    6: "method", 7: "property", 8: "field", 9: "constructor", 10: "enum",
    11: "interface", 12: "function", 13: "variable", 14: "constant",
    15: "string", 16: "number", 17: "boolean", 18: "array", 19: "object",
    20: "key", 21: "null", 22: "enum-member", 23: "struct", 24: "event",
    25: "operator", 26: "type-parameter",
}


def _resolve_file(file_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve *file_path* within the workspace.

    Returns ``(safe_path, None)`` on success or ``(None, message)`` when the
    path escapes the workspace or does not exist.
    """
    safe_path = resolve_within_root(file_path)
    if safe_path is None:
        return None, f"Error: path escapes the workspace: {file_path}"
    if not os.path.isfile(safe_path):
        return None, f"Error: file not found: {file_path}"
    return safe_path, None


def _language_for(safe_path: str) -> Optional[str]:
    """Return the LSP language id for *safe_path* by extension, else ``None``."""
    return _LSP_LANGUAGE_BY_EXT.get(os.path.splitext(safe_path)[1].lower())


def _server_available(language: str) -> Tuple[bool, Optional[str]]:
    """Check whether a language server is configured *and* installed.

    Returns ``(True, command)`` when available or ``(False, None)`` otherwise.
    Everything is lazily imported so importing this module is cheap.
    """
    import shutil

    try:
        from ..lsp.config import DEFAULT_SERVERS
    except Exception:
        return False, None
    server = DEFAULT_SERVERS.get(language)
    if not server or not shutil.which(server["command"]):
        return False, None
    return True, server["command"]


def _resolve_position(safe_path: str, line: Optional[int],
                      character: Optional[int],
                      symbol: Optional[str]) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """Resolve a 0-indexed ``(line, character)`` for a request.

    Accepts either an explicit ``(line, character)`` (already 0-indexed, as LSP
    expects) or a ``symbol`` name whose first occurrence in the file is located
    with a word-boundary search.  Returns ``(line, character, None)`` on success
    or ``(None, None, message)`` on failure.
    """
    if line is not None:
        return line, (character or 0), None

    if not symbol:
        return None, None, "Error: provide either (line, character) or symbol"

    try:
        with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
            pattern = re.compile(r"\b" + re.escape(symbol) + r"\b")
            for idx, text in enumerate(f):
                match = pattern.search(text)
                if match:
                    return idx, match.start(), None
    except OSError as e:
        return None, None, f"Error: could not read file: {e}"
    return None, None, f"Error: symbol not found in file: {symbol!r}"


def _uri_path(uri: str) -> str:
    """Strip a ``file://`` prefix from *uri*, returning the bare path."""
    return uri[7:] if uri.startswith("file://") else uri


def _within_workspace(path: str) -> Optional[str]:
    """Return the absolute *path* if it is inside the workspace root, else None.

    Language servers can return locations anywhere on disk; this guards any
    server-provided path before it is read or surfaced, so a misbehaving server
    can never leak files outside the workspace.
    """
    abs_path = os.path.abspath(path)
    root = os.path.abspath(os.getcwd())
    try:
        if os.path.commonpath([root, abs_path]) != root:
            return None
    except ValueError:
        return None
    return abs_path


def _uri_to_display(uri: str) -> str:
    """Convert a ``file://`` URI to a workspace-relative (or marked) path."""
    path = _uri_path(uri)
    abs_path = _within_workspace(path)
    if abs_path is None:
        return "<outside-workspace>"
    return os.path.relpath(abs_path, os.getcwd())


def _snippet(uri: str, line: int) -> str:
    """Return the trimmed source line at *line* (0-indexed) for *uri*, if any.

    Only reads paths inside the workspace; server-returned paths that escape the
    workspace yield no snippet rather than leaking file contents.
    """
    abs_path = _within_workspace(_uri_path(uri))
    if abs_path is None:
        return ""
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            for idx, text in enumerate(f):
                if idx == line:
                    return text.strip()
    except OSError:
        pass
    return ""


def _format_locations(locations: List, header: str) -> str:
    """Render a list of ``Location`` objects as ``file:line:col  snippet``."""
    if not locations:
        return f"{header}: none found"
    lines = [header + ":"]
    for loc in locations[:_MAX_RESULTS]:
        try:
            uri = loc.uri
            start = loc.range.start
            display = _uri_to_display(uri)
            snippet = _snippet(uri, start.line)
            entry = f"  {display}:{start.line + 1}:{start.character + 1}"
            if snippet:
                entry += f"  {snippet}"
            lines.append(entry)
        except Exception:
            continue
    if len(locations) > _MAX_RESULTS:
        lines.append(f"  ... ({len(locations) - _MAX_RESULTS} more; narrow your query)")
    return "\n".join(lines)


def _run_lsp(language: str, coro_factory, open_path: Optional[str] = None):
    """Spawn an LSP client for *language*, open the doc, run *coro_factory*.

    ``coro_factory`` is an ``async def(client) -> result``.  Handles start/stop
    and, when *open_path* is given, the ``didOpen``/``didClose`` document
    lifecycle around the query (per the LSP spec).
    Runs on its own event loop; when called from within an already-running loop
    (e.g. an async agent context) it transparently offloads to a worker thread
    so it never blocks or re-enters the caller's loop.
    Returns ``(result, None)`` on success or ``(None, message)`` on failure.
    """
    import asyncio

    try:
        from ..lsp.client import LSPClient
    except Exception as e:  # pragma: no cover - import guarded
        return None, f"Error: LSP client unavailable: {e}"

    async def _driver():
        client = LSPClient(language=language)
        client.config.timeout = min(client.config.timeout, _LSP_TIMEOUT)
        opened = False
        try:
            if not await client.start():
                return None, f"Error: could not start {language} language server"
            if open_path is not None:
                await client.open_document(open_path)
                opened = True
            return await coro_factory(client), None
        finally:
            if opened:
                try:
                    await client.close_document(open_path)
                except Exception:
                    pass
            await client.stop()

    def _run() -> Tuple[Optional[object], Optional[str]]:
        return asyncio.run(
            asyncio.wait_for(_driver(), timeout=_LSP_TIMEOUT + 5)
        )

    try:
        # If a loop is already running in this thread, we cannot call
        # asyncio.run() here; offload to a dedicated thread with its own loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _run()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run).result(timeout=_LSP_TIMEOUT + 10)
    except Exception as e:
        logger.debug("LSP navigation error (%s): %s", language, e)
        return None, f"Error: lsp navigation failed: {e}"


def _prepare(file_path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Shared setup: resolve path, detect language, verify server installed.

    Returns ``(safe_path, language, None)`` on success or
    ``(None, None, message)`` with a clear degradation message otherwise.
    """
    safe_path, err = _resolve_file(file_path)
    if err:
        return None, None, err
    language = _language_for(safe_path)
    if language is None:
        return None, None, (
            f"Error: no language server configured for {os.path.basename(file_path)}"
        )
    available, _cmd = _server_available(language)
    if not available:
        return None, None, (
            f"Error: {language} language server not installed; "
            f"install it to use lsp navigation (falling back to grep is advised)"
        )
    return safe_path, language, None


def lsp_definition(file_path: str, line: Optional[int] = None,
                   character: Optional[int] = None,
                   symbol: Optional[str] = None) -> str:
    """Go to the definition of a symbol (LSP ``textDocument/definition``).

    Args:
        file_path: File to query (workspace-relative or absolute).
        line: 0-indexed line of the symbol (LSP convention). Optional if
            ``symbol`` is given.
        character: 0-indexed character/column of the symbol. Optional.
        symbol: Symbol name to locate in the file when a position is not
            provided; the first word-boundary occurrence is used.

    Returns:
        ``file:line:col  snippet`` for each definition, or a clear message when
        no language server is installed / nothing is found.
    """
    safe_path, language, err = _prepare(file_path)
    if err:
        return err

    resolved_line, resolved_char, perr = _resolve_position(
        safe_path, line, character, symbol)
    if perr:
        return perr

    async def _query(client):
        return await client.get_definition(safe_path, resolved_line, resolved_char)

    result, rerr = _run_lsp(language, _query, open_path=safe_path)
    if rerr:
        return rerr
    return _format_locations(result or [], "Definition")


def lsp_references(file_path: str, line: Optional[int] = None,
                   character: Optional[int] = None,
                   symbol: Optional[str] = None,
                   include_declaration: bool = True) -> str:
    """Find all references to a symbol (LSP ``textDocument/references``).

    Args:
        file_path: File to query (workspace-relative or absolute).
        line: 0-indexed line of the symbol. Optional if ``symbol`` is given.
        character: 0-indexed character/column of the symbol. Optional.
        symbol: Symbol name to locate when a position is not provided.
        include_declaration: Include the declaration in the results.

    Returns:
        ``file:line:col  snippet`` for each reference, or a clear message when
        no language server is installed / nothing is found.
    """
    safe_path, language, err = _prepare(file_path)
    if err:
        return err

    resolved_line, resolved_char, perr = _resolve_position(
        safe_path, line, character, symbol)
    if perr:
        return perr

    async def _query(client):
        return await client.get_references(
            safe_path, resolved_line, resolved_char,
            include_declaration=include_declaration)

    result, rerr = _run_lsp(language, _query, open_path=safe_path)
    if rerr:
        return rerr
    return _format_locations(result or [], "References")


def lsp_hover(file_path: str, line: int, character: int) -> str:
    """Get type/signature/doc at a position (LSP ``textDocument/hover``).

    Args:
        file_path: File to query (workspace-relative or absolute).
        line: 0-indexed line (LSP convention).
        character: 0-indexed character/column.

    Returns:
        The hover text, or a clear message when no server is installed or the
        server has nothing to report at that position.
    """
    safe_path, language, err = _prepare(file_path)
    if err:
        return err

    async def _query(client):
        return await client.get_hover(safe_path, line, character)

    result, rerr = _run_lsp(language, _query, open_path=safe_path)
    if rerr:
        return rerr
    if not result:
        return "Hover: no information at this position"
    return f"Hover:\n{result.strip()}"


def _flatten_symbols(symbols: List, container: Optional[str] = None) -> List:
    """Flatten hierarchical ``DocumentSymbol`` trees into a single list.

    ``textDocument/documentSymbol`` servers may nest methods/functions under a
    class via ``children``; flattening ensures those inner symbols are surfaced,
    tagging each with its parent's name as ``containerName`` for context.
    """
    flat: List = []
    for sym in symbols:
        if not isinstance(sym, dict):
            continue
        current = sym
        if container and "containerName" not in current:
            current = {**current, "containerName": container}
        flat.append(current)
        children = sym.get("children")
        if isinstance(children, list) and children:
            flat.extend(_flatten_symbols(children, sym.get("name", container)))
    return flat


def _format_symbols(symbols: List, header: str, include_container: bool = False) -> str:
    """Render document/workspace symbol dicts compactly."""
    if not symbols:
        return f"{header}: none found"
    flattened = _flatten_symbols(symbols)
    lines = [header + ":"]
    for sym in flattened[:_MAX_RESULTS]:
        name = sym.get("name", "?")
        kind = _SYMBOL_KIND.get(sym.get("kind"), "symbol")
        # documentSymbol carries ``range``; workspace/symbol carries ``location``.
        loc = sym.get("location")
        rng = sym.get("range") or sym.get("selectionRange")
        uri = None
        start = None
        if isinstance(loc, dict):
            uri = loc.get("uri")
            start = (loc.get("range") or {}).get("start")
        elif isinstance(rng, dict):
            start = rng.get("start")
        entry = f"  {kind} {name}"
        if include_container:
            container = sym.get("containerName")
            if container:
                entry += f" (in {container})"
        if start is not None:
            ln = start.get("line", 0) + 1
            col = start.get("character", 0) + 1
            display = _uri_to_display(uri) if uri else ""
            prefix = f"{display}:" if display else ""
            entry += f"  {prefix}{ln}:{col}"
        lines.append(entry)
    if len(flattened) > _MAX_RESULTS:
        lines.append(f"  ... ({len(flattened) - _MAX_RESULTS} more; narrow your query)")
    return "\n".join(lines)


def lsp_document_symbols(file_path: str) -> str:
    """List the symbols defined in a file (LSP ``textDocument/documentSymbol``).

    Args:
        file_path: File to query (workspace-relative or absolute).

    Returns:
        A compact ``kind name  line:col`` listing, or a clear message when no
        language server is installed.
    """
    safe_path, language, err = _prepare(file_path)
    if err:
        return err

    async def _query(client):
        return await client.get_document_symbols(safe_path)

    result, rerr = _run_lsp(language, _query, open_path=safe_path)
    if rerr:
        return rerr
    return _format_symbols(result or [], "Document symbols")


def lsp_workspace_symbols(query: str, file_path: Optional[str] = None) -> str:
    """Search symbols across the workspace (LSP ``workspace/symbol``).

    Args:
        query: Symbol name (or substring) to search for.
        file_path: Optional file used only to pick which language server to
            query; defaults to a Python server when omitted.

    Returns:
        A compact ``kind name  file:line:col`` listing, or a clear message when
        no language server is installed.
    """
    if not query:
        return "Error: query must be non-empty"

    if file_path:
        safe_path, err = _resolve_file(file_path)
        if err:
            return err
        language = _language_for(safe_path)
        if language is None:
            return (f"Error: no language server configured for "
                    f"{os.path.basename(file_path)}")
    else:
        language = "python"

    available, _cmd = _server_available(language)
    if not available:
        return (f"Error: {language} language server not installed; "
                f"install it to use lsp navigation")

    async def _query(client):
        return await client.get_workspace_symbols(query)

    result, rerr = _run_lsp(language, _query)
    if rerr:
        return rerr
    return _format_symbols(result or [], "Workspace symbols", include_container=True)
