"""The PraisonAI desktop engine.

Stdlib only, so it starts in milliseconds and adds nothing to the venv beyond
praisonaiagents itself. The shell spawns this, reads the announced port from
stdout, and the webview then talks to it directly over loopback HTTP -- tokens
never cross the Tauri IPC bridge, which is the one design point all four
reference apps converge on.
"""

import atexit
import collections
import hashlib
import json
import logging
import os
import pathlib
import secrets
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# The shell matches this exact prefix. Printed once, after the socket is bound,
# so a port announced here is always a port that is actually listening.
# Dev mode: prefer the checkout over any installed copy in site-packages.
# Without this the engine silently imports a *different* praisonaiagents than
# the one being edited -- the same source/installed-copy divergence that makes
# a fix appear to have no effect. Explicit and visible here rather than via
# PYTHONPATH, which would follow every child process invisibly.
# Searched upward rather than counted: this file is copied into the bundle at
# src-tauri/target/<profile>/engine/, where a fixed parents[2] resolves to
# target/praisonai-agents -- which does not exist. So the branch quietly never
# taken was the one whose whole purpose is to stop a fix having no effect.
def _checkout_source():
    """The praisonai-agents checkout above this file, if there is one."""
    override = os.environ.get("PRAISONAI_AGENTS_SOURCE", "").strip()
    if override:
        candidate = pathlib.Path(override)
        return candidate if (candidate / "praisonaiagents" / "__init__.py").is_file() else None
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        for candidate in (parent / "praisonai-agents",
                          parent / "src" / "praisonai-agents"):
            if (candidate / "praisonaiagents" / "__init__.py").is_file():
                return candidate
    return None


_SOURCE = _checkout_source()
if _SOURCE is not None:
    sys.path.insert(0, str(_SOURCE))


MIN_API_KEY_CHARS = 20

# What this process exported, so clearing a setting removes our value and never
# a value the user's shell provided.
_EXPORTED: dict = {}


def _export(name: str, value: str) -> None:
    _EXPORTED[name] = value
    os.environ[name] = value


def _unset_if_ours(name: str) -> None:
    ours = _EXPORTED.pop(name, None)
    if ours is not None and os.environ.get(name) == ours:
        del os.environ[name]
PORT_MARKER = "PRAISONAI_PORT="
PROTOCOL_VERSION = 2

# Transcripts live outside the app bundle, in the user's own space, so an app
# update can never take them with it. Append-only JSON per conversation: the
# format a user can read, diff and back up without our help.
APP_NAME = "PraisonAI"


def default_data_dir(platform=None, home=None, env=None):
    """Where the app keeps transcripts, settings and the lockfile.

    Taken per platform rather than hardcoded to the macOS location. On Windows
    a "Library/Application Support" folder is not merely unconventional -- it
    is excluded from roaming profiles and from most backup tooling, so a user's
    entire history would silently fail to follow them to a new machine.

    The Rust shell derives the same path in engine_paths.rs; the two must agree
    or the shell will look for an engine where the engine is not.
    """
    platform = sys.platform if platform is None else platform
    env = os.environ if env is None else env
    home = pathlib.Path.home() if home is None else home
    override = env.get("PRAISONAI_DESKTOP_HOME")
    if override:
        return pathlib.Path(override)
    if platform == "darwin":
        return home / "Library/Application Support" / APP_NAME
    if platform.startswith("win"):
        roaming = env.get("APPDATA")
        return (pathlib.Path(roaming) if roaming else home / "AppData/Roaming") / APP_NAME
    # Linux and the BSDs: the XDG base directory spec.
    xdg = env.get("XDG_DATA_HOME")
    return (pathlib.Path(xdg) if xdg else home / ".local/share") / APP_NAME


DATA_DIR = pathlib.Path(default_data_dir())
CHATS_DIR = DATA_DIR / "chats"

# The shell's src-tauri/src/lockfile.rs has always specified this file's format
# precisely and nothing ever wrote one, so the whole adoption path -- and any
# tool trying to find a running engine -- had nothing to read. `pgrep -f` is not
# a substitute: the shell running the pgrep matches the pattern itself.
LOCK_PATH = DATA_DIR / "engine.lock"

# Built on first use: importing the training module costs nothing until someone
# opens the tab, and the engine must stay fast to start for chat.
_TRAINER = None
LOCK_FORMAT_VERSION = 2


def _fnv1a64(text: str) -> int:
    """FNV-1a. Small, exact, and identical to the Rust side by construction."""
    h = 0xCBF29CE484222325
    for b in text.encode():
        h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def _start_time(pid: "int | None" = None) -> int:
    """A fingerprint of when this pid started, so a recycled pid is not us.

    This hashes `ps -o lstart=` verbatim rather than parsing it. The date `ps`
    prints is locale-dependent -- on this machine it is "Tue 25 Aug 15:26:04
    2026", day before month, which neither `time.strptime` nor
    `date -j -f "%a %b %e %T %Y"` accepts. Both sides silently fell back to
    something else and never agreed, so a live engine always looked like a
    recycled pid and a second one was started beside it.
    """
    pid = pid or os.getpid()
    if sys.platform.startswith("win"):
        return _windows_start_time(pid)
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                             capture_output=True, text=True, timeout=3).stdout
    except Exception:  # noqa: BLE001
        return 0
    return _fnv1a64(out.strip()) if out.strip() else 0


def _windows_start_time(pid: int) -> int:
    """The process creation time, hashed the same way as the ps output.

    Windows has no `ps`, so the POSIX path returns 0 for every process -- and
    0 is the "I could not tell" value, which means every recycled pid compares
    equal and an unrelated process gets adopted as the engine. GetProcessTimes
    gives a real 100-nanosecond creation stamp.
    """
    try:
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        # HANDLE is pointer-sized; the default c_int return truncates it above
        # 2**31. Unreachable in practice, but wrong for free.
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return 0                       # no such process, or not ours to ask
        try:
            created = wintypes.FILETIME()
            spare = wintypes.FILETIME()
            ok = kernel32.GetProcessTimes(
                handle, ctypes.byref(created), ctypes.byref(spare),
                ctypes.byref(spare), ctypes.byref(spare))
            if not ok:
                return 0
            stamp = (created.dwHighDateTime << 32) | created.dwLowDateTime
            return _fnv1a64(f"{pid}:{stamp}")
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return 0


def register_exit_signals(handler, module=None):
    """Register `handler` for every termination signal this platform has.

    The names are looked up one at a time rather than gathered into a tuple.
    Building `(SIGTERM, SIGINT, SIGHUP)` dereferences SIGHUP before any `try`
    runs, and Windows has no SIGHUP -- so the AttributeError escaped, and it
    escaped *after* the port had been announced and the lockfile written. The
    shell would adopt an engine that was already dead, and every request would
    look like a network fault rather than a crash.
    """
    module = signal if module is None else module
    for name in ("SIGTERM", "SIGINT", "SIGHUP", "SIGBREAK"):
        sig = getattr(module, name, None)
        if sig is None:
            continue                      # this platform does not have it
        try:
            module.signal(sig, handler)
        except (ValueError, OSError):
            pass                          # not the main thread, or not allowed


def write_lock_text(path: pathlib.Path, body: str) -> pathlib.Path:
    """Write the lockfile atomically, always as UTF-8.

    The encoding is explicit because the Rust side reads this file as strict
    UTF-8 and maps invalid bytes to "absent" -- and absent means spawn. A user
    whose home directory is not ASCII would otherwise get a second engine
    beside the live one on every launch, which is the exact orphan leak the
    lockfile exists to prevent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".lock.tmp")
    # write_bytes, not write_text: text mode translates "\n" to "\r\n" on
    # Windows, so the file was not the bytes this function says it writes. The
    # Rust parser trims each line and would have coped, but a lockfile that
    # differs by platform is a difference waiting to matter, and the encode is
    # the only conversion that should be happening here.
    tmp.write_bytes(body.encode("utf-8"))
    _replace_with_retry(tmp, path)
    return path


def _replace_with_retry(tmp: pathlib.Path, target: pathlib.Path, attempts: int = 4) -> None:
    """os.replace, tolerating a Windows reader holding the destination open.

    The call is atomic on all three platforms, but Windows raises
    PermissionError if any process has the target open -- a real risk for a
    lockfile the shell polls, and for a settings file an antivirus scanner is
    reading. Retrying briefly is the standard mitigation; the last attempt is
    allowed to raise so a genuine failure is not swallowed.
    """
    for attempt in range(attempts):
        try:
            tmp.replace(target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05)


def read_text_file(path) -> str:
    """Read a text file as UTF-8, replacing anything undecodable.

    Without an explicit encoding this decodes in the locale encoding -- cp1252
    on a default Windows box -- and because errors are replaced rather than
    raised, the caller is handed plausible-looking mojibake and never finds
    out. A model asked to reason over it will do so confidently.
    """
    return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")


def allow_address_reuse(platform=None) -> bool:
    """Whether the listening socket should set SO_REUSEADDR.

    On POSIX it means "reuse an address still in TIME_WAIT" and is what we
    want. On Windows the same flag means "another process may bind this exact
    address while I am still listening" -- and this server is unauthenticated
    loopback HTTP carrying API keys and transcripts, so a local process that
    guessed the port could take over connections. Windows sockets are
    exclusive by default, which is the behaviour we want there.
    """
    platform = sys.platform if platform is None else platform
    return not platform.startswith("win")


def write_lock(port: int) -> pathlib.Path:
    """Write the lockfile in exactly the format lockfile.rs parses.

    Written to a temporary file and renamed, because the parser treats a
    zero-length file as a crash mid-write -- so we must never produce one.
    """
    interpreter = sys.executable or "unknown"
    venv_root = sys.prefix
    config_hash = hashlib.sha256(
        json.dumps(load_settings(), sort_keys=True).encode()).hexdigest()[:16]
    body = (f"format_version={LOCK_FORMAT_VERSION}\n"
            f"pid={os.getpid()}\n"
            f"start_time={_start_time()}\n"
            f"port={port}\n"
            f"interpreter={interpreter}\n"
            f"venv_root={venv_root}\n"
            f"config_hash={config_hash}\n")
    return write_lock_text(LOCK_PATH, body)


def clear_lock() -> None:
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


def _chat_path(cid: str) -> pathlib.Path:
    # Ids are generated by us, but a traversal attempt must not escape the dir.
    safe = "".join(c for c in cid if c.isalnum() or c in "-_")[:64]
    if not safe:
        raise ValueError("invalid conversation id")
    return CHATS_DIR / f"{safe}.json"


def load_chat(cid: str) -> dict:
    try:
        chat = json.loads(_chat_path(cid).read_text())
        if not isinstance(chat, dict):
            # Valid JSON, wrong shape -- the app's own export is a list. Every
            # caller does chat.get(...), so a non-dict escapes as AttributeError
            # and drops the connection. /projects and /search both call this on
            # the same files list_chats() walks, so hardening only list_chats()
            # left those two routes crashing on exactly the file this fixes.
            raise ValueError("not a chat object")
        return chat
    except (OSError, ValueError):
        # Absent and corrupt are answered the same way here on purpose: the
        # caller is opening a conversation, and either way there is nothing to
        # show. The distinction is preserved in list_chats(), which reports a
        # corrupt file rather than hiding it.
        return {"id": cid, "title": "New chat", "messages": []}


def save_chat(chat: dict) -> None:
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    path = _chat_path(chat["id"])
    # Write-then-rename, so a crash mid-write cannot truncate an existing
    # transcript -- the failure mode that turns "my history is gone" into a
    # support ticket.
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(chat, indent=1))
    _replace_with_retry(tmp, path)


def list_chats() -> list:
    if not CHATS_DIR.is_dir():
        return []
    out = []
    for f in CHATS_DIR.glob("*.json"):
        try:
            c = json.loads(f.read_text())
            if not isinstance(c, dict):
                # Valid JSON, wrong shape -- the app's own export is a list.
                raise ValueError("not a chat object")
            out.append({
                "id": c.get("id", f.stem),
                "title": c.get("title") or "New chat",
                "updated": c.get("updated", 0),
                "count": len(c.get("messages", [])),
                "project": c.get("project", ""),
            })
        except (OSError, ValueError):
            # Surfaced, not swallowed: a corrupt transcript the user can see is
            # recoverable; one silently omitted looks like data loss.
            out.append({"id": f.stem, "title": "(unreadable)", "updated": 0,
                        "count": 0, "corrupt": True})
    return sorted(out, key=lambda c: c["updated"], reverse=True)

_agent_lock = threading.Lock()
_agents = {}

# Run id -> cancellation flag. A cancelled run must stop *emitting*; we cannot
# interrupt the provider call itself from here, so cancellation is enforced at
# the yield boundary and the client is told the run ended early rather than
# being left to infer it from silence.
# --- tool approval -----------------------------------------------------------
# Every request carries call_id. Binding an approval to a row by position --
# "the one pending tool must be the one that asked" -- holds only while exactly
# one approval is ever outstanding, and silently authorises the wrong command
# the moment that stops being true.
_approval_lock = threading.Condition()
_approvals = {}          # approval_id -> {"call_id","name","args","decision"}
_always_allow = set()    # tool names the user granted for this process

APPROVAL_TIMEOUT_S = 300


def _await_decision(aid: str) -> str:
    """Block until the user decides. Returns 'allow' or 'deny'.

    Times out into 'deny': silence is not consent, and a run that hangs forever
    on an unanswered prompt is worse than one that stops.
    """
    deadline = time.time() + float(load_settings().get("approval_timeout",
                                                       APPROVAL_TIMEOUT_S))
    with _approval_lock:
        while _approvals[aid]["decision"] is None:
            if not _approval_lock.wait(timeout=max(0.1, deadline - time.time())):
                if time.time() >= deadline:
                    _approvals[aid]["decision"] = "deny"
                    break
        return _approvals.pop(aid)["decision"]


def resolve_approval(approval_id: str, choice: str) -> bool:
    """Record a decision. Returns False for an unknown id rather than pretending."""
    with _approval_lock:
        entry = _approvals.get(approval_id)
        if entry is None or entry["decision"] is not None:
            return False
        if choice == "always":
            _always_allow.add(entry["name"])
            choice = "allow"
        entry["decision"] = "allow" if choice == "allow" else "deny"
        _approval_lock.notify_all()
        return True


_cancel_lock = threading.Lock()
_cancelled = set()
_active_runs = set()


def cancel_run(run_id: str) -> bool:
    """Mark a run cancelled. Returns whether the run was actually live.

    Reporting success for an unknown id would be a lie the UI cannot detect:
    the button would confirm a cancellation that never happened.
    """
    with _cancel_lock:
        if run_id not in _active_runs:
            return False
        _cancelled.add(run_id)
    return True


def _is_cancelled(run_id: str) -> bool:
    with _cancel_lock:
        return run_id in _cancelled


def _forget(run_id: str) -> None:
    with _cancel_lock:
        _cancelled.discard(run_id)


# Tool events are not carried on the token stream, so we subscribe to the
# library's public display-callback hook instead of patching it. The callback
# fires on the worker thread running the turn, so events are parked in a
# thread-local queue and drained by the SSE loop that owns the socket -- writing
# to the response from a callback thread would interleave frames.
# Bounded ring: enough to explain the last few turns, small enough that it can
# never become the memory leak it exists to help diagnose.
_LOG = collections.deque(maxlen=400)


def log(line: str) -> None:
    _LOG.append(f"{time.strftime('%H:%M:%S')}  {line}")


_tool_events = threading.local()


def _set_emitter(fn):
    """The tool runs on the thread that owns the socket, so a gate can write its
    own frame. Queueing it instead would deadlock: the drain loop that would
    send it is downstream of the blocking call.

    Must be cleared when the turn ends. ThreadingHTTPServer reuses threads, so a
    leftover emitter belongs to a previous request's closed socket -- the next
    turn on that thread then writes into it and dies silently.
    """
    _tool_events.emit = fn


def _emit_now(event, payload):
    fn = getattr(_tool_events, "emit", None)
    if fn is not None:
        fn(event, payload)


def _tool_queue():
    q = getattr(_tool_events, "q", None)
    if q is None:
        q = _tool_events.q = []
    return q


def _on_tool_call(message=None, console=None, tool_name=None, tool_input=None,
                  tool_output=None, elapsed_time=None, success=True, **_):
    """Called by praisonaiagents when a tool completes."""
    _tool_queue().append({
        "call_id": f"c_{len(_tool_queue())}_{tool_name or 'tool'}",
        "name": tool_name or "tool",
        "args": tool_input or {},
        "output": "" if tool_output is None else str(tool_output),
        "ok": bool(success),
        "seconds": round(elapsed_time, 2) if isinstance(elapsed_time, (int, float)) else None,
    })


_callbacks_registered = False


def _ensure_callbacks():
    global _callbacks_registered
    if _callbacks_registered:
        return
    try:
        from praisonaiagents.main import register_display_callback

        register_display_callback("tool_call", _on_tool_call)
        _callbacks_registered = True
    except Exception:  # noqa: BLE001 - tool cards are a nicety, chat is not
        pass


def _builtin_tools():
    """Tools the desktop agent ships with.

    Deliberately few and safe: read-only, no shell, no writes. Anything with
    side effects waits until the approval gate exists -- shipping a tool the
    user cannot refuse is the wrong order to build in.
    """

    def _gate(name, args):
        """Ask the user before a filesystem read. Returns True when allowed."""
        mode = load_settings().get("approval_mode", "ask")
        if mode == "never" or name in _always_allow:
            return True
        if getattr(_tool_events, "emit", None) is None:
            # No stream to ask on. Blocking here would hang the turn for the
            # full timeout with nobody able to answer, so refuse instead --
            # a declined tool is recoverable, a frozen turn is not.
            log(f"gate {name}: no stream to ask on, declining")
            return False
        log(f"gate {name}: awaiting approval")
        cid = f"c_{secrets.token_urlsafe(6)}"
        aid = f"ap_{secrets.token_urlsafe(12)}"
        with _approval_lock:
            _approvals[aid] = {"call_id": cid, "name": name, "args": args, "decision": None}
        _emit_now("approval_request",
                  {"approval_id": aid, "call_id": cid, "name": name, "args": args})
        return _await_decision(aid) == "allow"

    def read_file(path: str) -> str:
        """Read a UTF-8 text file and return its contents.

        Args:
            path: Absolute or ~-relative path to the file.
        """
        import pathlib as _p

        if not _gate("read_file", {"path": path}):
            return "The user declined this tool call."
        f = _p.Path(path).expanduser()
        if not f.is_file():
            return f"No such file: {f}"
        if f.stat().st_size > 200_000:
            return f"File too large ({f.stat().st_size} bytes); read a smaller file."
        return read_text_file(f)

    def list_directory(path: str = ".") -> str:
        """List the entries in a directory.

        Args:
            path: Directory to list.
        """
        import pathlib as _p

        if not _gate("list_directory", {"path": path}):
            return "The user declined this tool call."
        d = _p.Path(path).expanduser()
        if not d.is_dir():
            return f"Not a directory: {d}"
        entries = sorted(d.iterdir(), key=lambda e: (not e.is_dir(), e.name))[:200]
        return "\n".join(("d " if e.is_dir() else "f ") + e.name for e in entries) or "(empty)"

    def web_search(query: str) -> str:
        """Search the web and return the top results.

        Args:
            query: What to search for.
        """
        import json as _j
        import urllib.parse as _u
        import urllib.request as _r

        key = os.environ.get("TAVILY_API_KEY")
        if not key:
            # Say what is missing rather than returning an empty result set that
            # the model would report as "I found nothing".
            return ("Web search is not configured. Set TAVILY_API_KEY in the "
                    "environment to enable it.")
        try:
            req = _r.Request(
                "https://api.tavily.com/search",
                data=_j.dumps({"api_key": key, "query": query,
                               "max_results": 5}).encode(),
                headers={"content-type": "application/json"},
            )
            with _r.urlopen(req, timeout=20) as resp:
                data = _j.loads(resp.read())
        except Exception as exc:  # noqa: BLE001 - the model must see the cause
            return f"Web search failed: {type(exc).__name__}: {exc}"
        rows = [f"- {r.get('title','')}\n  {r.get('url','')}\n  {r.get('content','')[:200]}"
                for r in (data.get("results") or [])]
        return "\n".join(rows) or "No results."

    def fetch_url(url: str) -> str:
        """Fetch a web page and return its text.

        Args:
            url: An http(s) URL.
        """
        import re as _re
        import urllib.error as _e
        import urllib.request as _r

        if not url.startswith(("http://", "https://")):
            return "Only http and https URLs are supported."
        if not _gate("fetch_url", {"url": url}):
            return "The user declined this tool call."

        class _NoRedirect(_r.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise _e.HTTPError(req.full_url, code,
                                   f"redirect to {newurl} was not approved",
                                   headers, fp)

        try:
            with _r.build_opener(_NoRedirect).open(url, timeout=20) as resp:
                body = resp.read(400_000).decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            return f"Fetch failed: {type(exc).__name__}: {exc}"
        text = _re.sub(r"<script.*?</script>|<style.*?</style>", " ", body,
                       flags=_re.S | _re.I)
        text = _re.sub(r"<[^>]+>", " ", text)
        return _re.sub(r"\s+", " ", text).strip()[:20_000]

    def current_time() -> str:
        """Return the current local date and time."""
        import datetime as _dt

        return _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    return [read_file, list_directory, web_search, fetch_url, current_time]


APP_VERSION = "0.1.0"
SETTINGS_PATH = DATA_DIR / "settings.json"
MCP_PATH = DATA_DIR / "mcp.json"


def load_mcp() -> list:
    try:
        return json.loads(MCP_PATH.read_text()).get("servers", [])
    except (OSError, ValueError):
        return []


def save_mcp(servers: list) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MCP_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"servers": servers}, indent=1))
    _replace_with_retry(tmp, MCP_PATH)
# Mirrors frontend/dist/settings-registry.js. The registry is the source of
# truth for the UI; this is the storage contract, and load_settings() drops
# unknown keys and defaults missing ones so a hand-edited or older file can
# never leave the engine half-configured.
DEFAULT_SETTINGS = {
    "model": os.environ.get("PRAISONAI_MODEL", "gpt-4o-mini"),
    "temperature": 0.7,
    "max_tokens": 0,
    "top_p": 1,
    "base_url": "",
    "api_key": "",
    "system_prompt": "",
    "auto_title": True,
    "show_reasoning": True,
    "collapse_reasoning": False,
    "show_stats": True,
    "condense_paste": 4000,
    "theme": "system",
    "font_size": 15,
    "code_font_size": 12,
    "reduce_motion": "system",
    "approval_mode": "ask",
    "approval_timeout": 300,
    "confirm_delete": True,
    "launch_at_login": False,
    "check_updates": True,
}


# --- keychain ---------------------------------------------------------------
# Secrets go to the macOS keychain, never into settings.json. One reference app
# keyrings its API keys and then writes its proxy password to the settings file
# in plaintext -- the split is easy to get half-right, so it is centralised here.
# Overridable so a test never writes into the developer's real keychain.
# PRAISONAI_DESKTOP_HOME isolates the data directory but not the system
# keyring, which is shared per user -- a test run against the default service
# silently overwrites whatever key the person is actually using, and there is
# no way to put it back. Asking for isolation must isolate everything.
KEYCHAIN_SERVICE = os.environ.get("PRAISONAI_KEYCHAIN_SERVICE", "ai.praison.desktop")
SECRET_KEYS = {"api_key"}


def _quiet_subprocess_kwargs():
    """Keep a console window from flashing on Windows.

    A Tauri app is a GUI process with no console attached, so every bare Popen
    of a helper pops a black box on screen. load_settings() reads a secret on
    every turn, which would make this a flash per message.
    """
    if not sys.platform.startswith("win"):
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


class KeychainSecretStore:
    """The macOS keychain, via the `security` binary."""

    path = None

    def set(self, name: str, value: str) -> bool:
        try:
            if value:
                subprocess.run(["security", "add-generic-password", "-U",
                                "-s", KEYCHAIN_SERVICE, "-a", name, "-w", value],
                               check=True, capture_output=True, timeout=10,
                               **_quiet_subprocess_kwargs())
            else:
                # The write path above checks its exit status; this one did
                # not, and returned True regardless. A locked keychain leaves
                # the item intact, so "your key was removed" was reported
                # while the credential stayed live and came back on the next
                # launch. 44 is "no such item", which is a delete that has
                # already happened.
                removed = subprocess.run(
                    ["security", "delete-generic-password",
                     "-s", KEYCHAIN_SERVICE, "-a", name],
                    capture_output=True, timeout=10,
                    **_quiet_subprocess_kwargs())
                return removed.returncode in (0, 44)
            return True
        except Exception:  # noqa: BLE001 - a keychain failure must not lose the turn
            return False

    def get(self, name: str) -> str:
        try:
            r = subprocess.run(["security", "find-generic-password",
                                "-s", KEYCHAIN_SERVICE, "-a", name, "-w"],
                               capture_output=True, timeout=10, text=True,
                               **_quiet_subprocess_kwargs())
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:  # noqa: BLE001
            return ""


class SecretToolSecretStore:
    """The freedesktop secret service, via libsecret's `secret-tool`."""

    path = None

    def set(self, name: str, value: str) -> bool:
        try:
            if value:
                subprocess.run(["secret-tool", "store", "--label",
                                f"{KEYCHAIN_SERVICE} {name}",
                                "service", KEYCHAIN_SERVICE, "account", name],
                               input=value.encode(), check=True,
                               capture_output=True, timeout=10)
            else:
                # As above: unchecked, so an unavailable D-Bus session (a
                # headless or SSH login) reported a delete that never
                # happened. `secret-tool clear` exits 0 when it matches
                # nothing, so a non-zero status here is a real failure.
                cleared = subprocess.run(
                    ["secret-tool", "clear",
                     "service", KEYCHAIN_SERVICE, "account", name],
                    capture_output=True, timeout=10)
                return cleared.returncode == 0
            return True
        except Exception:  # noqa: BLE001
            return False

    def get(self, name: str) -> str:
        try:
            r = subprocess.run(["secret-tool", "lookup",
                                "service", KEYCHAIN_SERVICE, "account", name],
                               capture_output=True, timeout=10, text=True)
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:  # noqa: BLE001
            return ""


class DpapiSecretStore:
    """Windows DPAPI: encrypted to the logged-in user, no extra dependency."""

    def __init__(self, data_dir):
        self.path = pathlib.Path(data_dir) / "secrets.dat"

    def _crypt(self, blob, protect):
        import ctypes
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        buffer = ctypes.create_string_buffer(blob, len(blob))
        source = Blob(len(blob), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        result = Blob()
        crypt32 = ctypes.windll.crypt32
        call = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
        # Both functions take the same seven arguments: the blob in, a
        # description, optional entropy, a reserved pointer, a prompt struct,
        # flags, and the blob out.
        if not call(ctypes.byref(source), None, None, None, None, 0,
                    ctypes.byref(result)):
            raise OSError("DPAPI call failed")
        try:
            return ctypes.string_at(result.pbData, result.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(result.pbData)

    def _read(self):
        """The stored secrets, or {} if there are none.

        A missing file means "nothing stored yet". A file that will not decrypt
        means something else entirely -- a Windows password reset or a roamed
        profile can invalidate the DPAPI key -- and treating that as empty made
        the next `set` write a fresh blob over it, destroying every other
        secret in the file. So only absence is silent.
        """
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return {}
        return json.loads(self._crypt(raw, False).decode("utf-8"))

    def set(self, name: str, value: str) -> bool:
        try:
            store = self._read()          # raises if the blob will not decrypt
            if value:
                store[name] = value
            else:
                store.pop(name, None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            blob = self._crypt(json.dumps(store).encode("utf-8"), True)
            tmp = self.path.with_suffix(".dat.tmp")
            tmp.write_bytes(blob)
            _replace_with_retry(tmp, self.path)
            return True
        except Exception:  # noqa: BLE001
            return False

    def get(self, name: str) -> str:
        try:
            return str(self._read().get(name, ""))
        except Exception:  # noqa: BLE001 - unreadable is not the caller's problem
            return ""


class FileSecretStore:
    """A 0600 file beside the settings, for when nothing better is available.

    Not encryption -- it is file permissions, which is what an unlocked
    keyring amounts to in practice anyway. The point is that a secret is never
    written into settings.json, which users paste into issues.
    """

    def __init__(self, data_dir):
        self.path = pathlib.Path(data_dir) / "secrets.json"

    def _read(self) -> dict:
        """The stored secrets, or {} if there are none.

        Only absence is silent. Swallowing every error here meant one transient
        read failure -- or a partly written file -- read as "empty", and the
        next `set` wrote a fresh file over the top, destroying every other
        secret in it. The DPAPI store's docstring names this exact hazard; this
        one was left with it.
        """
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}

    def set(self, name: str, value: str) -> bool:
        try:
            store = self._read()
            if value:
                store[name] = value
            else:
                store.pop(name, None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            # O_EXCL, not just O_CREAT: the mode argument applies only when
            # the file is *created*, so a leftover temp file from an
            # interrupted write keeps its old permissions and the secret goes
            # into it world-readable until the chmod after the rename. On
            # Linux ~/.local/share is 0755, so that window is real. O_EXCL
            # also closes the symlink-follow hole.
            try:
                os.unlink(str(tmp))
            except FileNotFoundError:
                pass
            handle = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(store, out)
            _replace_with_retry(tmp, self.path)
            try:
                os.chmod(str(self.path), 0o600)
            except OSError:
                pass                      # Windows has no POSIX mode bits
            return True
        except Exception:  # noqa: BLE001
            return False

    def get(self, name: str) -> str:
        try:
            return str(self._read().get(name, ""))
        except Exception:  # noqa: BLE001 - unreadable is not the caller's problem
            return ""


class FallbackSecretStore:
    """Try the platform store; fall back rather than lose the secret.

    Without this, a machine with no keyring daemon -- a headless Linux box, a
    fresh container, a locked login keyring -- makes the app permanently
    unauthenticated with no user-visible cause: the write reports failure and
    the read reports the key as unset, forever.
    """

    def __init__(self, primary, secondary):
        self.primary, self.secondary = primary, secondary

    @property
    def path(self):
        return self.secondary.path

    def set(self, name: str, value: str) -> bool:
        """Write to the best store that will take it -- but delete from both.

        A delete that stopped at the first success left the other copy behind,
        and `get` served it: clearing an API key reported success while the key
        kept working and its plaintext stayed on disk. The same applies to a
        *new* value, which must not leave the superseded one readable in the
        fallback, so the secondary is cleared after a successful primary write.
        """
        if not value:
            # `and`, not `or`: a delete has only succeeded if the secret is
            # gone from everywhere it could be read from. With `or`, an
            # unwritable file store meant the plaintext copy survived, `get`
            # served it, and the user was told the key had been removed.
            cleared_primary = self.primary.set(name, "")
            cleared_secondary = self.secondary.set(name, "")
            return cleared_primary and cleared_secondary
        if self.primary.set(name, value):
            self.secondary.set(name, "")   # never leave a stale plaintext copy
            return True
        # The primary could not take the new value. If it still holds the old
        # one, `get` would keep serving that -- the user saves a new key, is
        # told it worked, and the app goes on using the previous one. Clearing
        # the primary first is what makes the fallback reachable; if even that
        # fails there is nowhere safe to put this.
        if self.primary.get(name) and not self.primary.set(name, ""):
            return False
        return self.secondary.set(name, value)

    def get(self, name: str) -> str:
        return self.primary.get(name) or self.secondary.get(name)


def secret_store_for(platform=None, data_dir=None):
    """The best available secret store for this platform, with a fallback."""
    platform = sys.platform if platform is None else platform
    data_dir = DATA_DIR if data_dir is None else data_dir
    fallback = FileSecretStore(data_dir)
    if platform == "darwin":
        return FallbackSecretStore(KeychainSecretStore(), fallback)
    if platform.startswith("win"):
        return FallbackSecretStore(DpapiSecretStore(data_dir), fallback)
    return FallbackSecretStore(SecretToolSecretStore(), fallback)


_SECRETS = None


def _secrets():
    global _SECRETS
    if _SECRETS is None:
        _SECRETS = secret_store_for()
    return _SECRETS


def keychain_set(name: str, value: str) -> bool:
    return _secrets().set(name, value)


def keychain_get(name: str) -> str:
    return _secrets().get(name)


def load_settings() -> dict:
    try:
        stored = json.loads(SETTINGS_PATH.read_text())
    except (OSError, ValueError):
        stored = {}
    # Unknown keys are dropped and missing keys defaulted, so a hand-edited or
    # older settings file can never leave the engine half-configured.
    out = {k: stored.get(k, v) for k, v in DEFAULT_SETTINGS.items()}
    for k in SECRET_KEYS:
        out[k] = keychain_get(k)
    return out


def save_settings(patch: dict) -> dict:
    merged = load_settings()
    for k in DEFAULT_SETTINGS:
        if k in patch:
            merged[k] = patch[k]
    for k in SECRET_KEYS:
        if k in patch:
            if not keychain_set(k, str(patch[k] or "")):
                raise RuntimeError(f"could not store {k} in the keychain")
            merged[k] = patch[k]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    # Secrets never reach the file.
    on_disk = {k: v for k, v in merged.items() if k not in SECRET_KEYS}
    tmp.write_text(json.dumps(on_disk, indent=1))
    _replace_with_retry(tmp, SETTINGS_PATH)
    # Settings change the agent's identity, so cached agents must go or the
    # next turn would silently run on the previous model.
    with _agent_lock:
        _agents.clear()
    return merged


def _llm_overrides(cfg: dict) -> dict:
    """Sampling overrides, passed at call time.

    Agent's constructor accepts none of temperature/max_tokens/top_p -- reaching
    them through llm={...} would switch to the custom-LLM path and pull in a
    134 MB dependency for identical intent. They are forwarded to start()
    instead, and only when the user actually changed them: sending
    temperature=0.7 unasked would override a provider default someone may have
    chosen deliberately elsewhere.
    """
    out = {}
    if cfg.get("temperature") != DEFAULT_SETTINGS["temperature"]:
        out["temperature"] = float(cfg["temperature"])
    if cfg.get("max_tokens"):
        out["max_tokens"] = int(cfg["max_tokens"])
    if cfg.get("top_p") != DEFAULT_SETTINGS["top_p"]:
        out["top_p"] = float(cfg["top_p"])
    _apply_env(cfg)
    return out


def _apply_env(cfg: dict) -> None:
    """Credentials and endpoint go to the environment, which the OpenAI client
    reads directly -- the constructor parameter routes through the heavier path."""
    if cfg.get("base_url"):
        # Set as an env var rather than base_url=, which routes through a
        # heavier code path for identical intent.
        _export("OPENAI_API_BASE", cfg["base_url"])
    else:
        # Clearing the setting clears only what *we* exported. Popping
        # unconditionally deleted the key inherited from the user's shell --
        # and this setting is documented as "blank uses the environment", so
        # that turned every request into an auth error.
        _unset_if_ours("OPENAI_API_BASE")
    key = cfg.get("api_key") or ""
    # A too-short value is a typo or a test fixture, not a credential. Exporting
    # it would replace a working environment key with a guaranteed 401. The UI
    # refuses it at entry (see api_key's validate) so this is a backstop, not
    # the only guard -- silently ignoring it is what made a bad key look set.
    if len(key) >= MIN_API_KEY_CHARS:
        _export("OPENAI_API_KEY", key)
    elif not key:
        _unset_if_ours("OPENAI_API_KEY")


def _installed_version() -> str:
    try:
        from importlib.metadata import version
        return version("praisonaiagents")
    except Exception:
        return "unknown"


def _vtuple(v: str):
    out = []
    for part in v.split(".")[:4]:
        digits = "".join(c for c in part if c.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def check_for_update(timeout: float = 4.0) -> dict:
    """Ask PyPI what the newest praisonaiagents is.

    Reports `checked: False` on any failure rather than "up to date" -- a check
    that did not happen must not read as a check that passed.
    """
    current = _installed_version()
    if not load_settings().get("check_updates", True):
        return {"current": current, "checked": False,
                "update_available": False, "message": "Update checks are off."}
    try:
        import urllib.request
        with urllib.request.urlopen(
            "https://pypi.org/pypi/praisonaiagents/json", timeout=timeout
        ) as r:
            latest = json.loads(r.read().decode())["info"]["version"]
    except Exception as exc:
        return {"current": current, "checked": False, "update_available": False,
                "message": f"Could not reach PyPI: {exc.__class__.__name__}"}
    newer = current != "unknown" and _vtuple(latest) > _vtuple(current)
    return {"current": current, "latest": latest, "checked": True,
            "update_available": newer,
            "message": (f"praisonaiagents {latest} is available."
                        if newer else "You are on the latest version.")}


LAUNCH_AGENT = pathlib.Path(
    "~/Library/LaunchAgents/ai.praison.desktop.plist").expanduser()


def set_launch_at_login(on: bool) -> dict:
    """Write or remove the LaunchAgent that opens the app at login.

    Uses the running .app bundle, so this is a no-op in dev where there is no
    bundle to open -- reported as such rather than silently succeeding.
    """
    app = os.environ.get("PRAISONAI_APP_BUNDLE") or ""
    if not on:
        try:
            LAUNCH_AGENT.unlink()
        except FileNotFoundError:
            pass
        return {"ok": True, "enabled": False}
    if not app.endswith(".app") or not os.path.isdir(app):
        return {"ok": False, "enabled": False,
                "message": "Only available in the installed app."}
    LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENT.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '  <key>Label</key><string>ai.praison.desktop</string>\n'
        '  <key>ProgramArguments</key>'
        f'<array><string>/usr/bin/open</string><string>{app}</string></array>\n'
        '  <key>RunAtLoad</key><true/>\n'
        '</dict></plist>\n')
    return {"ok": True, "enabled": True, "path": str(LAUNCH_AGENT)}


def _get_agent(session_id: str = "default", tools: bool = True):
    """One agent per session, built lazily: importing the engine costs more than
    binding a socket, and the window should be interactive before that is paid."""
    with _agent_lock:
        key = session_id if tools else session_id + "\x00notools"
        if key not in _agents:
            from praisonaiagents import Agent

            cfg = load_settings()
            _agents[key] = Agent(
                name="PraisonAI",
                role="Assistant",
                goal="Answer the user clearly and concisely.",
                instructions=cfg["system_prompt"] or None,
                llm=cfg["model"],
                tools=_builtin_tools() if tools else None,
            )
        return _agents[key]


def _seed_history(agent, chat_id: str) -> int:
    """Give the agent the conversation the user can already see.

    The history existed in two places and only one of them was durable: the
    transcript on disk, which the sidebar renders, and the agent's
    chat_history, which is what the model is actually shown. Nothing ever
    copied the first into the second.

    The agent cache is a plain dict in this process (`_agents`), so it is empty
    after any restart; `save_settings` clears it outright, because a model
    change must not run on the previous agent; and the tools toggle keys a
    *different* agent for the same session. After any of those, reopening a
    chat showed the user their whole conversation while the model was handed a
    blank slate -- and it said so: "I don't have access to your previous
    questions. Each session is treated independently."

    Only when the agent has nothing. An agent mid-session already holds the
    turns, including tool messages this transcript never stored, and replaying
    over the top would duplicate them.

    Returns how many messages were replayed, for the log.
    """
    try:
        if agent.chat_history:
            return 0
    except Exception:  # noqa: BLE001 - an agent without the attribute is not ours to seed
        return 0
    try:
        stored = load_chat(chat_id).get("messages") or []
    except Exception:  # noqa: BLE001 - a missing or broken transcript is not fatal
        return 0

    replayed = 0
    for message in stored:
        role, content = message.get("role"), message.get("content")
        # Only the two roles a transcript holds, and never a blank turn: an
        # empty assistant message is what a failed turn leaves behind, and
        # feeding it back teaches the model that silence is an acceptable
        # answer.
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            agent._append_to_chat_history({"role": role, "content": content})
            replayed += 1
    if replayed:
        log(f"replayed {replayed} messages into the agent for chat {chat_id}")
    return replayed


# --- stream protocol v2 -------------------------------------------------------
# v1 carried only start/delta/end/error, which is enough to print text and
# nothing else. Tool calls, reasoning and usage have to be first-class events or
# the UI has to infer them from prose -- and inference is how a tool call that
# silently failed still looks like a normal answer.
#
# Every event carries `msg_id` so the client can address a specific message
# rather than assuming the last one is the live one.
#
# This list is the whole vocabulary: eleven events, no more. A client written
# against a subset silently ignores the rest, so approval_request in particular
# -- the human-in-the-loop tool gate -- must appear here or the run blocks
# invisibly until its timeout. It is not a comment that can drift silently --
# the StreamProtocolVocabulary test in test_portability.py parses these names
# *and* every emit(...) / _emit_now(...) call site and asserts the two sets
# match in both directions, so a new event with no line here (or a line here
# with no emitter) fails CI.
#
#   start            {msg_id, run_id}
#   reasoning        {msg_id, text}          incremental, collapsible
#   delta            {msg_id, text}          assistant text
#   tool_drafting    {msg_id, name}          "preparing tool..." before the call
#   tool_call        {msg_id, call_id, name, args}
#   tool_result      {msg_id, call_id, name, ok, output, seconds}
#   approval_request {msg_id, approval_id, call_id, name, args}  human-in-the-loop gate
#   usage            {msg_id, chars, seconds, ttft}
#   cancelled        {msg_id, run_id}
#   error            {msg_id, message, kind}
#   end              {msg_id, user_index, assistant_index, versions, active}

def _classify_stream_item(item):
    """Map one yielded item onto a protocol event.

    Returns (event, payload). Unrecognised shapes become text rather than being
    dropped: a client that renders an unexpected object badly is recoverable,
    one that silently discards it is not.
    """
    if isinstance(item, str):
        return "delta", {"text": item}
    if isinstance(item, dict):
        kind = item.get("type") or item.get("event")
        if kind in ("tool_call", "tool_use"):
            return "tool_call", {
                "call_id": str(item.get("id") or item.get("call_id") or ""),
                "name": item.get("name") or item.get("tool") or "tool",
                "args": item.get("args") or item.get("arguments") or {},
            }
        if kind in ("tool_result", "tool_output"):
            return "tool_result", {
                "call_id": str(item.get("id") or item.get("call_id") or ""),
                "name": item.get("name") or item.get("tool") or "tool",
                "ok": bool(item.get("ok", True)),
                "output": str(item.get("output") or item.get("result") or ""),
            }
        if kind in ("reasoning", "thinking", "reasoning_delta"):
            return "reasoning", {"text": str(item.get("text") or item.get("content") or "")}
        if "content" in item or "text" in item:
            return "delta", {"text": str(item.get("content") or item.get("text") or "")}
    return "delta", {"text": str(item)}


def version_info(chat_id: str, user_index: "int | None") -> tuple:
    """(count, active) for the answer to `user_index`. (1, 0) when unversioned."""
    if user_index is None:
        return (1, 0)
    try:
        msgs = load_chat(chat_id)["messages"]
        msg = msgs[user_index + 1]
        versions = msg.get("versions")
        if not versions:
            return (1, 0)
        return (len(versions), min(max(int(msg.get("active", 0)), 0), len(versions) - 1))
    except Exception:  # noqa: BLE001
        return (1, 0)


def _active(msg: dict) -> str:
    """The text of an assistant message's currently selected version.

    A message written before versioning has no `versions` key and is its own
    only version, so this reads correctly for every chat already on disk.
    """
    versions = msg.get("versions")
    if not versions:
        return msg.get("content", "")
    i = min(max(int(msg.get("active", 0)), 0), len(versions) - 1)
    return versions[i]


def _persist(chat_id: str, prompt: str, reply: list,
             regenerate_of: "int | None" = None) -> "int | None":
    """Append one exchange and return the index the user message landed at.

    The index has to come from here because the client cannot compute it: a
    cancelled or errored turn is never persisted, yet it stays on screen. The UI
    used to derive `idx*2` from DOM position, so one unpersisted turn shifted
    every subsequent Fork and Delete onto the wrong message -- and the resulting
    404 was ignored, so the turn vanished from the screen and stayed on disk.

    Returns None if the write failed, which is the caller's signal that Fork and
    Delete must not be offered for this turn at all.
    """
    try:
        chat = load_chat(chat_id)
        chat["id"] = chat_id
        text = "".join(reply)

        # Regenerating keeps the previous answer as a prior version rather than
        # discarding it. Without this the only way to compare two answers is to
        # copy one out before asking for the other.
        if regenerate_of is not None:
            msgs = chat["messages"]
            a = regenerate_of + 1
            if 0 <= regenerate_of < len(msgs) and a < len(msgs) \
                    and msgs[a].get("role") == "assistant":
                target = msgs[a]
                versions = target.get("versions") or [target.get("content", "")]
                versions.append(text)
                target["versions"] = versions
                target["active"] = len(versions) - 1
                target["content"] = text        # readers that predate versions
                chat["updated"] = int(time.time())
                save_chat(chat)
                return regenerate_of
            # The turn it named is gone: fall through and append a new exchange
            # rather than silently writing nothing.

        user_index = len(chat["messages"])
        chat["messages"].append({"role": "user", "content": prompt})
        chat["messages"].append({"role": "assistant", "content": text})
        if load_settings().get("auto_title", True) and chat.get("title") in (
            None, "", "New chat"
        ):
            chat["title"] = (prompt[:48] + "…") if len(prompt) > 48 else prompt
        chat["updated"] = int(time.time())
        save_chat(chat)
        return user_index
    except Exception:  # noqa: BLE001 - persistence must never break a reply
        return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A003 - quiet by default
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _drain(self) -> bytes:
        """Read the request body exactly once, and return it.

        HTTP/1.1 keep-alive reuses the connection, so a body left unread is
        parsed as the start of the next request -- the following GET came back
        as 501 Unsupported method ('{}GET'). Every handler must therefore
        drain, including the ones that ignore the body.

        It returns the bytes because the first version did not: handlers that
        *did* want the body called `_drain()` and then `rfile.read(length)`,
        and the second read blocked forever on an empty socket. /approve and
        /project hung for the full approval timeout. A read that can only
        happen in one place cannot be done twice.
        """
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        return self.rfile.read(n) if n > 0 else b""

    def _body(self) -> dict:
        """The request body as a dict; `{}` for absent or malformed JSON."""
        raw = self._drain()
        try:
            value = json.loads(raw or b"{}")
        except (ValueError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # --- training -------------------------------------------------------
    def _training(self):
        """The one Trainer, built on first use so importing costs nothing."""
        global _TRAINER
        if _TRAINER is None:
            from training import Trainer
            _TRAINER = Trainer(DATA_DIR, sys.executable)
        return _TRAINER

    def _train_progress(self, run, cursor):
        """Replay from `cursor`, then follow. Not a subscription: a client that
        reconnects after a closed lid gets what it missed, which is the whole
        reason events are kept rather than streamed and dropped."""
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        idle = 0
        while True:
            events, gap = run.since(cursor)
            if gap:
                # Say so rather than handing over events with a hole in them,
                # then resume at the oldest event still held.
                #
                # Resuming at -1 instead made the *next* since() compute a gap
                # again -- every ring that has ever evicted satisfies
                # `0 < oldest` -- so the stream resynced forever, and the
                # `continue` skipped both the sleep and the terminal check.
                # A run past 4000 events (about twenty minutes of tqdm) showed
                # the viewer nothing at all while pinning a core, and kept
                # doing so after the run had finished. Falling through here
                # delivers the events instead of discarding them.
                self.wfile.write(b"event: resync\ndata: {}\n\n")
                self.wfile.flush()
                # Resume at the oldest event still held. A gap always comes
                # with events -- since() returns early on an empty buffer, and
                # a gap means every held event is newer than the cursor -- so
                # this is really `events[0][0] - 1`; the fallback is there so a
                # future change to since() cannot turn this into an
                # IndexError. The fix was removing the `continue` that used to
                # follow: without it the loop falls through and delivers them.
                cursor = events[0][0] - 1 if events else cursor
            for c, kind, payload in events:
                cursor = c
                body = json.dumps({"cursor": c, **payload})
                self.wfile.write(
                    f"id: {c}\nevent: {kind}\ndata: {body}\n\n".encode())
            if events:
                self.wfile.flush()
                idle = 0
            else:
                idle += 1
                if idle % 20 == 0:
                    # A heartbeat, so a proxy does not reap an idle stream and
                    # the client can tell "quiet" from "gone".
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            if run.state in ("done", "failed", "cancelled") and not events:
                return
            time.sleep(0.25)

    def do_GET(self):
        if self.path.startswith("/train/progress"):
            trainer = self._training()
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(self.path).query)
            run_id = (query.get("run") or [None])[0]
            run = trainer.get(run_id) if run_id else trainer.current
            if run is None:
                self._json({"ok": False, "error": "no such run"}, 404)
                return
            try:
                cursor = int((query.get("cursor") or ["-1"])[0])
            except ValueError:
                # A malformed cursor used to escape as an unhandled exception,
                # which drops the connection with no response at all.
                self._json({"ok": False, "error": "cursor must be an integer"}, 400)
                return
            try:
                self._train_progress(run, cursor)
            except (BrokenPipeError, ConnectionResetError):
                pass          # the window closed; the run keeps going
            return

        if self.path == "/train/runs":
            # list() first: history is a bounded deque, which cannot be
            # sliced. The cap is MAX_HISTORY, so this slice is belt and braces.
            history = list(self._training().history)[:50]
            self._json({"runs": [r.summary() for r in history]})
            return

        if self.path.startswith("/train/status"):
            trainer = self._training()
            run = trainer.current
            self._json({"run": run.summary() if run else None,
                        # list() first: metrics is a bounded deque, and a
                        # deque cannot be sliced.
                        "metrics": list(run.metrics)[-500:] if run else []})
            return

        if self.path == "/settings":
            cfg = load_settings()
            # The UI only needs to know whether a key is set, never its value.
            cfg["api_key"] = "\u2022" * 8 if cfg.get("api_key") else ""
            self._json(cfg)
            return
        if self.path == "/projects":
            names = sorted({(load_chat(c["id"]).get("project") or "")
                            for c in list_chats()} - {""})
            self._json({"projects": names})
            return
        if self.path == "/mcp":
            self._json({"servers": load_mcp()})
            return
        if self.path == "/update":
            self._json(check_for_update())
            return
        if self.path == "/logs":
            # The engine's own recent activity, so a user can see what happened
            # without leaving the app or finding a file.
            self._json({"lines": list(_LOG)})
            return
        if self.path.startswith("/search?"):
            from urllib.parse import parse_qs, urlparse
            q = (parse_qs(urlparse(self.path).query).get("q") or [""])[0].lower().strip()
            hits = []
            if q:
                for meta in list_chats():
                    chat = load_chat(meta["id"])
                    for m in chat.get("messages", []):
                        if q in str(m.get("content", "")).lower():
                            hits.append({"id": meta["id"], "title": meta["title"],
                                         "snippet": str(m.get("content"))[:120]})
                            break
            self._json({"hits": hits})
            return
        if self.path == "/chats":
            self._json({"chats": list_chats()})
            return
        if self.path.startswith("/chats/"):
            # 404 rather than an empty chat: /fork and /messages already refuse
            # an unknown id, and fabricating one here meant opening a deleted
            # conversation showed a blank transcript instead of saying so.
            cid = self.path.rsplit("/", 1)[-1]
            if not _chat_path(cid).is_file():
                self._json({"ok": False, "error": "no such conversation"}, 404)
                return
            chat = load_chat(cid)
            for m in chat.get("messages", []):
                if m.get("role") == "assistant" and m.get("versions"):
                    m["content"] = _active(m)
                    m["version_count"] = len(m["versions"])
                    m["version_active"] = min(
                        max(int(m.get("active", 0)), 0), len(m["versions"]) - 1)
                    m.pop("versions", None)   # the client only needs the one
            self._json(chat)
            return
        if self.path != "/health":
            self.send_error(404)
            return
        # ok:true plus a version, so the supervisor can tell "engine healthy"
        # from "something else answered on this port". data_dir is included
        # because the UI offers to copy that path, and it can be overridden by
        # PRAISONAI_DESKTOP_HOME or XDG_DATA_HOME -- so the page must ask
        # rather than reproduce the default and hand the user a path the app
        # is not actually using.
        body = json.dumps({"ok": True, "version": PROTOCOL_VERSION,
                           "shell_version": os.environ.get(
                               "PRAISONAI_DESKTOP_VERSION", "unknown"),
                           "agents_version": _installed_version(),
                           "data_dir": str(DATA_DIR)}).encode()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_DELETE(self):
        if not self.path.startswith("/chats/"):
            self.send_error(404)
            return
        try:
            _chat_path(self.path.rsplit("/", 1)[-1]).unlink(missing_ok=True)
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, 400)
            return
        except OSError as exc:
            # Reporting a delete that did not happen is how a conversation
            # closed on screen and was back in the sidebar on reopen.
            self._json({"ok": False, "error": str(exc)}, 500)
            return
        self._json({"ok": True})

    def do_POST(self):
        if self.path == "/train/start":
            payload = self._body()
            config = payload.get("config") or {}
            if not config.get("model_name") or not config.get("dataset"):
                self._json({"ok": False, "error":
                            "config needs at least model_name and dataset"}, 400)
                return
            try:
                # Reject what cannot work before a single byte is downloaded.
                from training import check_method_requirements
                check_method_requirements(config)
                run = self._training().start(config, payload.get("run_id"))
            except ValueError as exc:
                # A rejected run id is the caller's fault, not the server's.
                self._json({"ok": False, "error": str(exc)}, 400)
                return
            except RuntimeError as exc:
                # A live run is a conflict, not a server error: the client
                # should show the running job, not a traceback.
                self._json({"ok": False, "error": str(exc)}, 409)
                return
            except OSError as exc:
                # An unwritable runs directory escaped as an unhandled
                # exception, so the connection dropped with no response and
                # the UI reported "could not reach the engine" -- sending the
                # user after the wrong problem entirely.
                self._json({"ok": False, "error":
                            f"could not create the run directory: {exc}"}, 500)
                return
            self._json({"ok": True, "run": run.summary()})
            return

        # Parse the path, don't pattern-match the raw string. rsplit("/") on
        # "/train/stop/<stale-id>/" yielded "", which is falsy -- so the
        # stale-tab guard was skipped and a stale tab killed whatever run was
        # live. A bare startswith() also matched "/train/stopXXXX", and a
        # query string ("?force=1") was read as part of the run id, so a
        # legitimate stop was refused.
        route = urlparse(self.path).path
        if route == "/train/stop" or route.startswith("/train/stop/"):
            self._drain()
            run_id = route[len("/train/stop"):].strip("/") or None
            try:
                stopped = self._training().stop(run_id)
            except RuntimeError as exc:
                self._json({"ok": False, "error": str(exc)}, 409)
                return
            self._json({"ok": stopped,
                        "error": None if stopped else "nothing was running"},
                       200 if stopped else 404)
            return

        if self.path.startswith("/cancel/"):
            self._drain()
            run_id = self.path.rsplit("/", 1)[-1]
            known = cancel_run(run_id)
            body = json.dumps({"ok": known, "run_id": run_id,
                               "error": None if known else "no such active run"}).encode()
            self.send_response(200 if known else 404)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path.startswith("/approve/"):
            aid = self.path.rsplit("/", 1)[-1]
            # A malformed or absent body must never mean "allow".
            choice = self._body().get("choice", "deny")
            ok = resolve_approval(aid, choice)
            self._json({"ok": ok, "error": None if ok else "no such pending approval"},
                       200 if ok else 404)
            return

        if self.path == "/settings":
            length = int(self.headers.get("Content-Length") or 0)
            try:
                patch = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, TypeError):
                self.send_error(400)
                return
            if "launch_at_login" in patch:
                # Persist what actually happened, not what was asked. Writing
                # the request first made the toggle report a login item that
                # was never registered -- and survive restarts saying so.
                result = set_launch_at_login(bool(patch["launch_at_login"]))
                patch = {**patch, "launch_at_login": bool(result.get("enabled"))}
                saved = dict(save_settings(patch))
                saved["launch_at_login_result"] = result
            else:
                saved = save_settings(patch)
            self._json(saved)
            return

        if self.path == "/mcp":
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, TypeError):
                self.send_error(400)
                return
            servers = load_mcp()
            action = body.get("action")
            if action == "add":
                name = str(body.get("name", "")).strip()
                if not name:
                    self._json({"ok": False, "error": "name is required"}, 400)
                    return
                servers = [x for x in servers if x.get("name") != name]
                servers.append({"name": name,
                                "command": str(body.get("command", "")),
                                "args": body.get("args") or [],
                                "enabled": bool(body.get("enabled", True))})
            elif action == "remove":
                servers = [x for x in servers if x.get("name") != body.get("name")]
            elif action == "toggle":
                for x in servers:
                    if x.get("name") == body.get("name"):
                        x["enabled"] = not x.get("enabled", True)
            else:
                self._json({"ok": False, "error": "unknown action"}, 400)
                return
            save_mcp(servers)
            self._json({"ok": True, "servers": servers})
            return

        if self.path.startswith("/version/"):
            # Select which stored answer is the live one.
            self._drain()
            _, _, rest = self.path.partition("/version/")
            cid, _, rest2 = rest.partition("/")
            idx, _, want = rest2.partition("/")
            try:
                chat = load_chat(cid)
                if not _chat_path(cid).is_file():
                    raise KeyError
                msg = chat["messages"][int(idx) + 1]
                versions = msg.get("versions") or []
                n = int(want)
                if msg.get("role") != "assistant" or not versions \
                        or not 0 <= n < len(versions):
                    raise KeyError
                msg["active"] = n
                msg["content"] = versions[n]
                chat["id"] = cid
                chat["updated"] = int(time.time())
                save_chat(chat)
                self._json({"ok": True, "active": n, "count": len(versions),
                            "content": versions[n]})
            except (ValueError, KeyError, IndexError):
                self._json({"ok": False, "error": "no such version"}, 404)
            return

        if self.path.startswith("/fork/"):
            self._drain()
            # Copy a transcript up to and including message N into a new chat,
            # leaving the original untouched -- a fork, not a rewrite.
            _, _, rest = self.path.partition("/fork/")
            cid, _, idx = rest.partition("/")
            try:
                if not _chat_path(cid).is_file():
                    self._json({"ok": False, "error": "no such conversation"}, 404)
                    return
                src = load_chat(cid)
                n = int(idx) + 1
                new_id = f"{cid}-f{secrets.token_urlsafe(4)}"
                save_chat({"id": new_id,
                           "title": (src.get("title") or "New chat") + " (fork)",
                           "project": src.get("project", ""),
                           "messages": src.get("messages", [])[:n],
                           "updated": int(time.time())})
                self._json({"ok": True, "id": new_id})
            except (ValueError, KeyError):
                self._json({"ok": False, "error": "cannot fork"}, 404)
            return

        if self.path.startswith("/project/"):
            cid = self.path.rsplit("/", 1)[-1]
            name = self._body().get("project", "")
            chat = load_chat(cid)
            chat["id"] = cid
            chat["project"] = str(name)[:80]
            save_chat(chat)
            self._json({"ok": True, "project": chat["project"]})
            return

        if self.path.startswith("/messages/"):
            self._drain()
            # Drop one exchange (a user turn and the reply it produced).
            _, _, rest = self.path.partition("/messages/")
            cid, _, idx = rest.partition("/")
            try:
                if not _chat_path(cid).is_file():
                    self._json({"ok": False, "error": "no such conversation"}, 404)
                    return
                chat = load_chat(cid)
                i = int(idx)
                if i < 0 or i >= len(chat["messages"]):
                    # A slice delete silently succeeds out of range, so the
                    # bound is checked rather than inferred from an exception.
                    self._json({"ok": False, "error": "no such message"}, 404)
                    return
                del chat["messages"][i:i + 2]
                save_chat(chat)
                self._json({"ok": True, "remaining": len(chat["messages"])})
            except (ValueError, IndexError, KeyError):
                self._json({"ok": False, "error": "no such message"}, 404)
            return

        if self.path == "/reset":
            length = int(self.headers.get("Content-Length") or 0)
            try:
                session = json.loads(self.rfile.read(length) or b"{}").get("session", "default")
            except (ValueError, TypeError):
                session = "default"
            with _agent_lock:
                _agents.pop(session, None)
            body = json.dumps({"ok": True}).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path != "/chat":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            prompt = payload.get("prompt", "")
            run_id = str(payload.get("run_id") or "")
            session = payload.get("session", "default")
            chat_id = payload.get("chat_id") or session
            regenerate_of = payload.get("regenerate_of")
            tools_on = payload.get("tools", True) is not False
            for att in (payload.get("attachments") or [])[:5]:
                nm = str(att.get("name", "file"))[:120]
                body = str(att.get("text", ""))[:100_000]
                prompt = f"{prompt}\n\n--- attached: {nm} ---\n{body}"
        except (ValueError, TypeError):
            self.send_error(400)
            return

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        msg_id = f"m_{int(time.time()*1000):x}"

        def emit(event, data=None):
            payload = {"msg_id": msg_id, **(data or {})}
            self.wfile.write(f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode())
            self.wfile.flush()

        if run_id:
            with _cancel_lock:
                _active_runs.add(run_id)
        cfg_now = load_settings()
        started = time.perf_counter()
        first_token_at = None
        chars = 0
        reply = []
        tool_started = {}
        # praisonaiagents logs provider failures and falls back rather than
        # raising, so a 401 reaches us as an empty stream. Capture the log line
        # so the user is told "invalid API key" instead of "no output".
        captured = []

        class _Capture(logging.Handler):
            def emit(self, record):
                if record.levelno >= logging.ERROR:
                    captured.append(record.getMessage())

        _cap = _Capture()
        logging.getLogger().addHandler(_cap)
        try:
            log(f"turn start chat={chat_id} run={run_id or '-'}")
            _set_emitter(emit)
            _ensure_callbacks()
            _tool_queue().clear()
            _apply_env(load_settings())
            agent = _get_agent(session, tools=tools_on)
            # Before the turn, not at construction: the agent is cached per
            # session and the transcript is per chat, and a settings change
            # can drop the agent between one turn and the next.
            _seed_history(agent, chat_id)
            emit("start", {"run_id": run_id})
            streamed = False
            tools_shown = 0
            def _emit_drafting(name):
                emit("tool_drafting", {"name": name})

            def _drain_tools():
                """Emit any tool activity recorded since the last check."""
                shown = 0
                q = _tool_queue()
                while q:
                    ev = q.pop(0)
                    shown += 1
                    _emit_drafting(ev["name"])
                    emit("tool_call", {"call_id": ev["call_id"], "name": ev["name"],
                                       "args": ev["args"]})
                    log(f"tool {ev['name']} ok={ev['ok']} {ev.get('seconds')}s")
                    emit("tool_result", {"call_id": ev["call_id"], "name": ev["name"],
                                         "ok": ev["ok"], "output": ev["output"],
                                         "seconds": ev["seconds"]})
                return shown

            for chunk in agent.start(prompt, stream=True,
                                     **_llm_overrides(load_settings())):
                # Counted here too. This call drains the queue, so discarding
                # its result meant the tally further down always read zero
                # unless the loop body never ran at all -- and the tests only
                # covered that one case, so the count looked right while every
                # stream that yielded anything before dying still reported
                # "the engine produced no output" under its own tool cards.
                tools_shown += _drain_tools()
                if run_id and _is_cancelled(run_id):
                    # Verified by side effect: emission stops. The client is told
                    # explicitly rather than inferring it from a stream that ends.
                    emit("cancelled", {"run_id": run_id})
                    break
                event, frame = _classify_stream_item(chunk)
                if event == "delta":
                    text = frame["text"]
                    if not text:
                        continue
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    streamed = True
                    chars += len(text)
                    reply.append(text)
                    emit("delta", frame)
                elif event == "reasoning":
                    if cfg_now.get("show_reasoning", True):
                        emit("reasoning", frame)
                elif event == "tool_call":
                    tool_started[frame["call_id"]] = time.perf_counter()
                    emit("tool_call", frame)
                elif event == "tool_result":
                    began = tool_started.pop(frame["call_id"], None)
                    if began is not None:
                        frame["seconds"] = round(time.perf_counter() - began, 2)
                    emit("tool_result", frame)
                else:
                    emit(event, frame)
            else:
                # Tool activity belongs to the user even when the turn failed.
                # Draining only on the success path meant a turn that ran tools
                # and then died showed neither the answer nor the tools -- the
                # work happened and left no trace.
                tools_shown += _drain_tools()
                if not streamed:
                    # A stream that yielded nothing is a failure, not an empty
                    # answer -- and the cause is usually in the logs, not here.
                    detail = next((c for c in captured
                                   if "401" in c or "api key" in c.lower()), None)
                    if detail:
                        emit("error", {"kind": "auth", "message":
                             "The provider rejected the API key. Check it in "
                             "Settings \u2192 Models. " + detail[:200]})
                    elif captured:
                        emit("error", {"kind": "internal",
                                       "message": captured[-1][:300]})
                    elif tools_shown:
                        # Not the same failure as "nothing happened". The tools
                        # ran and their results are on screen; what is missing
                        # is the model's answer about them. Saying "no output"
                        # here described the turn to the user as a dead end
                        # when most of it had in fact succeeded.
                        emit("error", {"kind": "no_answer", "message":
                             f"{tools_shown} tool call(s) ran, but the model "
                             "sent no answer afterwards. Their results are above."})
                    else:
                        emit("error", {"message": "the engine produced no output",
                                       "kind": "empty"})
                else:
                    elapsed = time.perf_counter() - started
                    user_index = _persist(chat_id, prompt, reply, regenerate_of)
                    if cfg_now.get("show_stats", True):
                        emit("usage", {
                            "chars": chars,
                            "seconds": round(elapsed, 2),
                            "ttft": (round(first_token_at - started, 2)
                                     if first_token_at else None),
                        })
                    vinfo = version_info(chat_id, user_index)
                    emit("end", {"user_index": user_index,
                                 "assistant_index": None if user_index is None
                                 else user_index + 1,
                                 "versions": vinfo[0], "active": vinfo[1]})
        except Exception as exc:  # noqa: BLE001 - the client must see the cause
            # `kind` lets the UI offer the right recovery: a missing key needs
            # settings, a rate limit needs retry, a bug needs the log.
            name = type(exc).__name__
            kind = ("auth" if "auth" in name.lower() or "key" in str(exc).lower()
                    else "rate_limit" if "rate" in str(exc).lower()
                    else "internal")
            log(f"ERROR {name}: {exc}")
            emit("error", {"message": f"{name}: {exc}", "kind": kind})
        finally:
            try:
                logging.getLogger().removeHandler(_cap)
            except Exception:  # noqa: BLE001
                pass
            _set_emitter(None)
            _tool_queue().clear()
            if run_id:
                with _cancel_lock:
                    _active_runs.discard(run_id)
                _forget(run_id)


def main():
    # Port 0: the kernel assigns a free one, so a collision is impossible.
    # Set before construction: the socket is bound inside __init__, so a later
    # assignment would come too late to affect it.
    ThreadingHTTPServer.allow_reuse_address = allow_address_reuse()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    print(f"{PORT_MARKER}{port}", flush=True)
    print(f"praisonai runtime listening on 127.0.0.1:{port}", flush=True)
    write_lock(port)
    atexit.register(clear_lock)

    def _stop_everything(*_):
        # The trainer runs in its own session (start_new_session=True), so a
        # signal aimed at the engine's process group never reaches it. If the
        # engine simply exits, the fine-tune is reparented to init and keeps
        # the GPU with nothing left that can find or stop it. Trainer.stop()
        # terminates the trainer's own group first, so quit takes it down too.
        if _TRAINER is not None:
            try:
                _TRAINER.stop()
            except Exception:  # noqa: BLE001 - never block the quit
                pass
        sys.exit(0)

    register_exit_signals(_stop_everything)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        clear_lock()


if __name__ == "__main__":
    sys.exit(main())
