"""AGENTS.md-style context file injection, resident in ``praisonai-code``.

This is the dependency-free home of the subtree-instruction helper so the
terminal-native CLI (``pip install praisonai-code``) can load project
instructions and resolve ``--instructions`` sources without importing the
optional ``praisonai_bot`` support package or the umbrella ``praisonai``
wrapper (C7 standalone contract).

It relies only on the standard library plus ``praisonaiagents.hooks`` (already a
core dependency of ``praisonai-code``). The ``praisonai_bot`` copy remains a
backward-compatible mirror for host apps that import it directly.
"""

from __future__ import annotations

import glob as _glob
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

DEFAULT_CANDIDATES = ["AGENTS.md", "agents.md", ".agents/AGENTS.md", "CLAUDE.md"]

# Upper bound on the bytes read from a single remote instruction source. Keeps a
# stray large URL from ballooning the system context; oversized bodies are
# truncated with a marker rather than failing the run.
_REMOTE_MAX_BYTES = 256 * 1024

# Timeout (seconds) for a single remote instruction fetch. Best-effort: a slow
# or unreachable URL is skipped with a warning, never blocking the run.
_REMOTE_TIMEOUT = 5.0

# Opt-in to allow fetching instruction URLs that resolve to private, loopback,
# or link-local addresses. Off by default so an auto-loaded project config from
# an untrusted checkout cannot make the host contact internal services (SSRF).
_ALLOW_LOCAL_URL_ENV = "PRAISONAI_INSTRUCTIONS_ALLOW_LOCAL_URLS"

# Tool-argument keys that carry a file path across the various file tools
# (praisonaiagents ``read_file`` uses ``filepath``; praisonai-code tools use
# ``path``/``file_path``; ACP edit tools use ``file_path``). The first present,
# string-valued key wins.
_PATH_ARG_KEYS = ("filepath", "file_path", "path", "filename", "target_file")


def _get_git_root(start: Path) -> Optional[Path]:
    """Resolve the git/project root using the resident CLI resolver.

    Falls back to None when the helper or git is unavailable so discovery
    simply walks up to the filesystem root.
    """
    try:
        from praisonai_code.cli.utils import project

        return project.get_git_root(str(start))
    except (ImportError, OSError):
        return None


# When no git root is found, cap the walk-up to avoid scanning arbitrary
# system directories up to the filesystem root.
_MAX_WALK_UP_DEPTH = 10


def _discover_search_dirs(base: Path, walk_up: bool) -> List[Path]:
    """Build directories to search, ordered root -> cwd (nearest last).

    Walks up from ``base`` to the git root so nearer, more specific
    instruction files take precedence by appearing last. When no git root
    is found, the walk-up is capped at ``_MAX_WALK_UP_DEPTH`` levels to avoid
    scanning arbitrary system directories.
    """
    base = base.resolve()
    if not walk_up:
        return [base]

    git_root = _get_git_root(base)
    if git_root is not None:
        git_root = git_root.resolve()

    dirs: List[Path] = []
    current = base
    depth = 0
    while True:
        dirs.append(current)
        if git_root and current == git_root:
            break
        if current == current.parent:
            break
        if git_root is None and depth >= _MAX_WALK_UP_DEPTH:
            break
        current = current.parent
        depth += 1

    # Reverse so root is first and cwd (nearest) is last.
    dirs.reverse()
    return dirs


def load_context_files(
    paths: Optional[List[str]] = None,
    *,
    cwd: Optional[Path] = None,
    walk_up: bool = True,
) -> str:
    """Load context from AGENTS.md-style files and return combined text.

    Discovery mirrors the configuration resolver: it walks up from ``cwd``
    to the project boundary (git root) collecting instruction files at each
    level, layers a user-global file (``~/.praisonai/AGENTS.md``) as the
    lowest-precedence source, and concatenates root -> cwd so nearer files
    take precedence (appear last).

    Args:
        paths: Explicit relative file names to load from ``cwd`` only. When
            provided, discovery/walk-up is skipped (backward compatible).
        cwd: Directory to start discovery from (defaults to ``Path.cwd()``).
        walk_up: When True (default), walk up to the git/project root and
            layer files. Ignored when ``paths`` is given.

    Returns:
        Combined instruction text, blank-line separated.
    """
    base = cwd or Path.cwd()

    seen: set = set()
    chunks: List[str] = []

    def _add(path: Path) -> None:
        if not path.is_file():
            return
        # De-duplicate by filesystem identity so the same physical file is
        # read once even via different paths or on case-insensitive volumes.
        try:
            stat = path.stat()
            key = (stat.st_dev, stat.st_ino)
        except OSError:
            key = path.resolve()
        if key in seen:
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return
        seen.add(key)
        chunks.append(text)

    # Explicit paths override discovery and remain cwd-only for compatibility.
    if paths is not None:
        for name in paths:
            _add(base / name)
        return "\n\n".join(chunks)

    # Lowest-precedence layer: user-global instructions
    # (skipped when walk_up is False to honour cwd-only semantics).
    if walk_up:
        _add(Path.home() / ".praisonai" / "AGENTS.md")

    # Walk-up layers: root -> cwd so nearer files take precedence (last).
    for search_dir in _discover_search_dirs(base, walk_up):
        for name in DEFAULT_CANDIDATES:
            _add(search_dir / name)

    return "\n\n".join(chunks)


def _is_remote_source(entry: str) -> bool:
    """Whether an instruction entry is an ``http(s)://`` URL."""
    return entry.startswith(("http://", "https://"))


def _allow_local_urls() -> bool:
    """Whether fetching URLs that resolve to internal addresses is opted in."""
    return os.environ.get(_ALLOW_LOCAL_URL_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _is_blocked_ip(addr: str) -> bool:
    """Whether a resolved address string is in a non-global (blocked) range."""
    import ipaddress

    try:
        ip = ipaddress.ip_address(addr.split("%", 1)[0])
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_public_addrs(host: str) -> Optional[List[str]]:
    """Resolve ``host`` and return its addresses only if *all* are global.

    Returns the list of resolved address strings when every resolution is a
    public/global address, ``None`` when the host is unresolvable (let urlopen
    surface the failure downstream), or an empty list when any resolved address
    is in a blocked (private/loopback/link-local/reserved) range so the caller
    fails closed. Returning the concrete addresses lets the fetch *pin* the
    connection to a validated IP, closing the DNS-rebinding (TOCTOU) window
    where a re-resolution at connect time could return an internal address.
    """
    import socket

    if not host:
        return []
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return None
    addrs: List[str] = []
    for info in infos:
        addr = info[4][0]
        if _is_blocked_ip(addr):
            return []
        addrs.append(addr)
    return addrs


def _is_blocked_host(host: str) -> bool:
    """Whether ``host`` resolves to a private/loopback/link-local/reserved IP.

    SSRF guard: an instruction URL can arrive from an auto-loaded project config
    in an untrusted checkout, so a URL that resolves to an internal service must
    not be fetched. Any resolved address in a non-global range blocks the fetch
    (fail-closed on resolution errors). Bypassable via ``_ALLOW_LOCAL_URL_ENV``
    for trusted internal setups.
    """
    addrs = _resolve_public_addrs(host)
    if addrs is None:
        # Unresolvable — let urlopen surface the failure/warning downstream.
        return False
    return len(addrs) == 0


def _url_is_fetchable(url: str) -> bool:
    """Validate scheme and destination of a remote instruction URL (SSRF guard)."""
    from urllib.parse import urlparse

    if _allow_local_urls():
        return True
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if _is_blocked_host(parsed.hostname or ""):
        logger.warning(
            "Skipping remote instruction source %s: resolves to a "
            "private/loopback/link-local address (set %s=1 to allow)",
            url,
            _ALLOW_LOCAL_URL_ENV,
        )
        return False
    return True


class _PinnedSSRFError(Exception):
    """Raised at connect time when a host re-resolves to a blocked address."""


def _build_pinned_opener():
    """Build a urllib opener that pins each connection to a validated IP.

    Closes the DNS-rebinding (TOCTOU) window: the up-front
    :func:`_url_is_fetchable` check resolves the host once, but a plain
    ``urlopen`` re-resolves at connect time, so an attacker-controlled hostname
    can rebind to an internal address between the two resolutions. Here each
    ``HTTP(S)Connection`` re-resolves *and re-validates* the host at connect
    time and connects to that exact validated IP, so the address checked is the
    address contacted. The original hostname is preserved for the ``Host``
    header and TLS SNI so virtual-hosted and HTTPS endpoints still work.

    Redirects are additionally re-validated by a guarded redirect handler, and
    the ``_allow_local_urls`` opt-in bypasses pinning entirely for trusted
    internal setups.
    """
    import http.client
    import socket
    import urllib.request

    def _pinned_connect(conn):
        # Re-validate at the moment of connection so a rebind since the
        # up-front check is caught, then connect to the validated address.
        addrs = _resolve_public_addrs(conn.host)
        if not addrs:  # empty (blocked) or None (unresolvable) -> refuse
            raise _PinnedSSRFError(
                f"host {conn.host!r} did not resolve to a public address"
            )
        last_err: Optional[Exception] = None
        for addr in addrs:
            try:
                conn.sock = socket.create_connection(
                    (addr, conn.port), timeout=conn.timeout
                )
                if getattr(conn, "_tunnel_host", None):
                    conn._tunnel()
                return
            except OSError as exc:  # try the next validated address
                last_err = exc
        raise last_err or OSError(f"could not connect to {conn.host!r}")

    class _PinnedHTTPConnection(http.client.HTTPConnection):
        def connect(self):
            _pinned_connect(self)

    class _PinnedHTTPSConnection(http.client.HTTPSConnection):
        def connect(self):
            _pinned_connect(self)
            # Wrap the raw socket with TLS using the original hostname for SNI
            # and certificate verification (not the pinned IP).
            self.sock = self._context.wrap_socket(
                self.sock, server_hostname=self.host
            )

    class _PinnedHTTPHandler(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(_PinnedHTTPConnection, req)

    class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(_PinnedHTTPSConnection, req)

    class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not _url_is_fetchable(newurl):
                return None
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    return urllib.request.build_opener(
        _PinnedHTTPHandler(),
        _PinnedHTTPSHandler(),
        _GuardedRedirectHandler(),
    )


def _fetch_remote_source(url: str) -> Optional[str]:
    """Fetch a remote instruction source, best-effort and size-bounded.

    Uses the stdlib ``urllib`` (lazily imported) so no heavy dependency is
    added. Destinations are validated against an SSRF guard (see
    :func:`_url_is_fetchable`) that rejects private/loopback/link-local hosts,
    the connection is *pinned* to the validated IP (see
    :func:`_build_pinned_opener`) so a DNS rebind cannot redirect it to an
    internal service, and redirects are re-validated so a public URL cannot
    bounce to an internal one. A slow, unreachable, or oversized response is
    handled gracefully: failures return ``None`` (with a warning) so the run
    continues, and bodies larger than ``_REMOTE_MAX_BYTES`` are truncated with a
    marker.
    """
    if not _url_is_fetchable(url):
        return None
    try:
        if _allow_local_urls():
            # Trusted internal setup: skip IP pinning so a legitimately private
            # instruction host is reachable.
            import urllib.request

            opener = urllib.request.build_opener()
        else:
            opener = _build_pinned_opener()
        with opener.open(url, timeout=_REMOTE_TIMEOUT) as resp:  # nosec B310
            raw = resp.read(_REMOTE_MAX_BYTES + 1)
    except Exception as exc:  # noqa: BLE001 - best-effort; never block the run
        logger.warning("Skipping remote instruction source %s: %s", url, exc)
        return None

    truncated = len(raw) > _REMOTE_MAX_BYTES
    if truncated:
        raw = raw[:_REMOTE_MAX_BYTES]
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - decode is defensive
        return None
    if truncated:
        text += "\n... [remote instruction source truncated]"
    return text


def resolve_instruction_sources(
    entries: Optional[List[str]] = None,
    *,
    cwd: Optional[Path] = None,
) -> str:
    """Resolve config-declared instruction sources into combined text.

    Each entry may be:

    * a plain file path (``docs/rules.md``),
    * a glob (``docs/standards/*.md``),
    * a ``~``-prefixed path (``~/company/ai-rules.md``), or
    * a remote ``http(s)://`` URL.

    Entries are resolved in order and their contents concatenated (blank-line
    separated), so callers can layer org-wide sources before project-specific
    ones. Local globs expand to their matches sorted for determinism; a
    ``~``/env-var path is expanded; remote URLs are fetched lazily, best-effort
    and size-bounded (see :func:`_fetch_remote_source`). Missing local paths and
    failed fetches are skipped with a warning rather than aborting the run.

    Args:
        entries: Ordered list of source specifiers. ``None``/empty returns "".
        cwd: Base directory for resolving relative paths (defaults to CWD).

    Returns:
        Combined instruction text, blank-line separated (possibly empty).
    """
    if not entries:
        return ""

    base = Path(cwd) if cwd else Path.cwd()

    seen: Set = set()
    chunks: List[str] = []

    def _add_file(path: Path) -> None:
        if not path.is_file():
            return
        try:
            stat = path.stat()
            key = (stat.st_dev, stat.st_ino)
        except OSError:
            key = path.resolve()
        if key in seen:
            return
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Skipping instruction source %s: %s", path, exc)
            return
        seen.add(key)
        chunks.append(text)

    for entry in entries:
        if not isinstance(entry, str) or not entry.strip():
            continue
        entry = entry.strip()

        if _is_remote_source(entry):
            if entry in seen:
                continue
            text = _fetch_remote_source(entry)
            if text is not None:
                seen.add(entry)
                chunks.append(text)
            continue

        expanded = os.path.expanduser(os.path.expandvars(entry))
        candidate = Path(expanded)
        if not candidate.is_absolute():
            candidate = base / candidate

        # Expand globs (including brace-free ``*``/``?``/``[]`` patterns). When
        # the entry contains no glob metacharacter this yields the single path.
        pattern = str(candidate)
        if any(ch in pattern for ch in "*?["):
            for match in sorted(_glob.glob(pattern, recursive=True)):
                _add_file(Path(match))
        else:
            if candidate.is_file():
                _add_file(candidate)
            else:
                logger.warning("Instruction source not found: %s", entry)

    return "\n\n".join(chunks)


def _identity_key(path: Path):
    """Filesystem identity for dedup (device+inode), falling back to resolved path."""
    try:
        stat = path.stat()
        return (stat.st_dev, stat.st_ino)
    except OSError:
        return path.resolve()


class PathContextAttacher:
    """Attach the nearest governing instruction files as files are touched.

    Up-front ``load_context_files`` discovery walks ``cwd -> project root`` once
    at session start. In a monorepo, an agent that later reads/edits a file in a
    *sibling or deeper* subtree (e.g. ``packages/foo/AGENTS.md``) never sees that
    subtree's conventions. This attacher augments the up-front load: on the first
    touch of a directory it walks up to the project root collecting
    ``DEFAULT_CANDIDATES``, deduplicates against files already loaded (both the
    up-front rules and earlier touches), bounds the result by a character budget,
    and caches per directory so repeated touches never re-walk disk.

    Session-scoped: create one instance per session/agent run so cache and dedup
    state stay isolated (multi-agent safe).
    """

    def __init__(
        self,
        already_loaded: Optional[str] = None,
        *,
        max_chars: int = 8000,
    ) -> None:
        """Initialise the attacher.

        Args:
            already_loaded: Text already injected up front (used only to seed
                dedup so its files are not re-attached). Its identity is tracked
                by content so duplicate physical files are skipped.
            max_chars: Character budget for the total text this attacher emits
                across the session. ``0`` disables the budget.
        """
        self._seen: Set = set()
        self._seen_texts: Set[str] = set()
        self._dir_cache: Dict[Path, str] = {}
        self._max_chars = max_chars
        self._emitted_chars = 0
        # Seed dedup with the identities of already-loaded files so the same
        # physical instruction file discovered up front is not re-attached.
        if already_loaded:
            self._seed_from_text(already_loaded)

    def _seed_from_text(self, text: str) -> None:
        # We cannot recover file identities from text alone, so we record the
        # text content to skip re-emitting identical bodies. Physical-identity
        # dedup below still handles the same file reached via different paths.
        #
        # ``load_context_files`` joins multiple instruction files with "\n\n",
        # so seed the whole blob *and* each chunk. This lets an individual file
        # discovered later match even when it was originally injected inside a
        # larger concatenated up-front load.
        self._seen_texts.add(text)
        for chunk in text.split("\n\n"):
            if chunk:
                self._seen_texts.add(chunk)

    def attach_for_path(self, file_path) -> str:
        """Return nearest instruction text for ``file_path``'s directory.

        Walks up from the file's directory to the project root collecting
        instruction files (root first, nearest last), deduplicated against
        everything already emitted/loaded and bounded by the char budget. The
        first touch of a directory does the disk walk; later touches of the same
        directory return the cached (already-deduped) result cheaply.

        Returns an empty string when nothing new is found or the budget is
        exhausted.
        """
        p = Path(file_path)
        directory = (p if p.is_dir() else p.parent).resolve()

        if directory in self._dir_cache:
            return self._dir_cache[directory]

        # Collect newly-discovered files without mutating dedup state yet: if
        # the char budget discards this result we must not permanently lock the
        # files out of future touches (they were never actually emitted).
        chunks: List[str] = []
        new_keys: List = []
        local_seen_texts: Set[str] = set()
        for search_dir in _discover_search_dirs(directory, walk_up=True):
            for name in DEFAULT_CANDIDATES:
                candidate = search_dir / name
                if not candidate.is_file():
                    continue
                key = _identity_key(candidate)
                if key in self._seen:
                    continue
                try:
                    text = candidate.read_text(encoding="utf-8")
                except OSError:
                    continue
                if text in self._seen_texts or text in local_seen_texts:
                    self._seen.add(key)
                    continue
                local_seen_texts.add(text)
                new_keys.append(key)
                chunks.append(text)

        result = "\n\n".join(chunks)

        # Enforce the character budget across the whole session, keeping the
        # truncation marker inside the remaining budget so max_chars holds.
        if self._max_chars and result:
            remaining = self._max_chars - self._emitted_chars
            if remaining <= 0:
                result = ""
            elif len(result) > remaining:
                suffix = "\n... [subtree context truncated]"
                if remaining > len(suffix):
                    result = result[: remaining - len(suffix)] + suffix
                else:
                    result = result[:remaining]

        # Only commit dedup state when something was actually emitted, so a
        # budget-suppressed discovery can still surface if budget frees up.
        if result:
            for key in new_keys:
                self._seen.add(key)
            self._seen_texts |= local_seen_texts

        self._emitted_chars += len(result)
        self._dir_cache[directory] = result
        return result


def load_context_files_for_path(
    file_path,
    *,
    already_loaded: Optional[str] = None,
    max_chars: int = 8000,
) -> str:
    """Stateless one-shot discovery of nearest instruction files for a path.

    Convenience wrapper around :class:`PathContextAttacher` for callers that do
    not maintain session state. Prefer the class when touching many files so
    dedup and per-directory caching persist across touches.
    """
    return PathContextAttacher(
        already_loaded, max_chars=max_chars
    ).attach_for_path(file_path)


# Tool names that operate on a file and should trigger subtree-rule discovery.
# Covers the real interactive tool surface (praisonaiagents ``read_file``/
# ``write_file`` and the ACP ``acp_create_file``/``acp_edit_file``/
# ``acp_delete_file`` tools) plus common generic aliases so custom file tools
# are matched too.
_FILE_TOOL_MATCHER = (
    r"^(read_file|write_file|edit_file|list_files"
    r"|acp_create_file|acp_edit_file|acp_delete_file"
    r"|read|edit|write|apply_patch|str_replace|multi_edit|search_replace)$"
)


def _extract_tool_path(tool_input: Any) -> Optional[str]:
    """Pull the target file path out of a tool's input arguments.

    Returns the first present, non-empty string value among ``_PATH_ARG_KEYS``
    so it works across the differing file-tool argument conventions.
    """
    if not isinstance(tool_input, dict):
        return None
    for key in _PATH_ARG_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def build_subtree_context_hook(
    already_loaded: Optional[str] = None,
    *,
    max_chars: int = 8000,
) -> Callable[[Any], Any]:
    """Build an ``AFTER_TOOL`` hook that lazily attaches subtree instructions.

    Wires the :class:`PathContextAttacher` into the neutral core hook
    substrate: on each file-touching tool call (``read_file``/``edit_file``/
    ``write_file`` and friends) it resolves the nearest instruction file for the
    touched directory and, if not already loaded/emitted this session, returns it
    as ``additional_context`` so the agent sees locally-relevant rules the first
    time it works in that subtree.

    The returned callable is session-scoped (its attacher owns the dedup and
    per-directory cache), so create one hook per session/agent run. Register it
    on an agent's hook registry for ``HookEvent.AFTER_TOOL`` (optionally with
    ``matcher=file_tool_matcher()`` to skip non-file tools cheaply).

    Args:
        already_loaded: Up-front instruction text (used only to seed dedup so
            files already injected at session start are not re-attached).
        max_chars: Character budget for the total text emitted across the
            session. ``0`` disables the budget.

    Returns:
        A function ``hook(hook_input) -> HookResult | None`` suitable for
        ``HookRegistry.register_function``. Returns ``None`` (no-op) when the
        tool is not a file tool or nothing new is discovered.
    """
    attacher = PathContextAttacher(already_loaded, max_chars=max_chars)

    def _hook(hook_input: Any):
        tool_input = getattr(hook_input, "tool_input", None)
        path = _extract_tool_path(tool_input)
        if not path:
            return None
        try:
            context = attacher.attach_for_path(path)
        except OSError:
            return None
        if not context:
            return None
        try:
            from praisonaiagents.hooks import HookResult
        except ImportError:
            return None
        return HookResult(decision="allow", additional_context=context)

    _hook.__name__ = "subtree_instruction_injection"
    return _hook


def file_tool_matcher() -> str:
    """Regex matching file-touching tool names for the subtree-context hook."""
    return _FILE_TOOL_MATCHER
