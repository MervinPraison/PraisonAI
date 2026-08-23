"""
Pre-run condition gates for the scheduler (bot layer).

A *condition gate* is a cheap, deterministic check that decides whether a
scheduled job's (expensive) model turn should happen at all. It implements the
core ``JobConditionProtocol`` and returns a ``GateResult``:

- ``run=False`` → the tick is recorded as ``skipped``; no model tokens are
  spent and no empty message is delivered.
- ``run=True`` → the run proceeds. Any text the gate produces is exposed as
  ``context`` and appended to the job message, so the same check both *gates*
  the run and *seeds* it with context.

This is a **cost/efficiency** concern, complementary to (and distinct from) the
wrapper's ``RunPolicy``, which is a **safety** gate on *what* a run may do.

The default :class:`ShellConditionGate` runs the job's ``pre_run`` value as a
shell command:

- exit code ``0`` with output → run, output becomes context;
- exit code ``0`` with empty output → run, no context;
- non-zero exit code → skip (nothing to do).

Deployments wanting a richer gate (a Python callable, an MCP/tool probe) can
supply any object implementing ``JobConditionProtocol`` — the executor accepts a
``condition_resolver`` for exactly this.
"""

from __future__ import annotations

import difflib
import hashlib
import http.client
import ipaddress
import logging
import os
import shlex
import socket
import ssl
import subprocess
import threading
import time
from collections.abc import Mapping
from typing import Any
from urllib import parse

from praisonaiagents.scheduler.protocols import GateResult

logger = logging.getLogger(__name__)

# On POSIX, start the shell in its own session so a timeout can kill the whole
# process group (shell + any children it spawned) rather than orphaning them.
_POSIX = os.name == "posix"

# Cap captured gate output so a chatty pre-run script cannot blow up the prompt.
_MAX_CONTEXT_CHARS = 8000
# Cap stderr surfaced in the skip ``reason`` so an audit record stays compact.
_MAX_REASON_CHARS = 500
_MAX_MONITOR_CHARS = 8000
_MAX_MONITOR_BYTES = 64 * 1024
_MAX_MONITOR_PREVIEW_BYTES = 2048


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, address: str, port: int, timeout: float) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._address = address
        self._raw_socket: socket.socket | None = None

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._address, self.port), self.timeout, self.source_address,
        )
        # http.client sets self.sock = None when it closes a close-delimited
        # response, which is exactly when a slow body can hang forever. Keep a
        # separate handle so the deadline watchdog still has something to shut
        # down. Cleared in ``_request_url``'s finally so the fd is not retained.
        self._raw_socket = self.sock


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, port: int, timeout: float) -> None:
        self._ssl_context = ssl.create_default_context()
        super().__init__(
            host,
            port=port,
            timeout=timeout,
            context=self._ssl_context,
        )
        self._address = address
        self._raw_socket: socket.socket | None = None

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._address, self.port), self.timeout, self.source_address,
        )
        try:
            self.sock = self._ssl_context.wrap_socket(
                raw_socket, server_hostname=self.host,
            )
        except Exception:
            raw_socket.close()
            raise
        # See ``_PinnedHTTPConnection.connect``: retain a handle the close path
        # does not clear so the deadline watchdog can still abort a hung body.
        self._raw_socket = self.sock


class MonitorGate:
    """Stateful change-detection gate for a job's monitor source."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def should_run(
        self, job: Any, *, state: dict[str, Any] | None = None,
    ) -> GateResult:
        spec = getattr(job, "monitor", None) or {}
        if not isinstance(spec, Mapping):
            return GateResult(run=False, reason="monitor spec must be a mapping")
        command = spec.get("command")
        url = spec.get("url")
        has_command = isinstance(command, str) and bool(command.strip())
        has_url = isinstance(url, str) and bool(url.strip())
        if has_command == has_url:
            return GateResult(
                run=False,
                reason="monitor requires exactly one command or URL",
            )

        try:
            if has_command:
                output, stderr, code, timed_out, exceeded = self._run_command(
                    command,
                )
                if timed_out:
                    return GateResult(
                        run=False,
                        reason=f"monitor command timed out (>{self._timeout:.0f}s)",
                    )
                if exceeded:
                    return GateResult(
                        run=False,
                        reason="monitor command output exceeded 8000 character limit",
                    )
                if code != 0:
                    stderr = stderr.strip()
                    detail = f": {stderr}" if stderr else ""
                    return GateResult(
                        run=False,
                        reason=(
                            "monitor command failed "
                            f"(exit {code}{detail})"
                        ),
                    )
            else:
                output = self._fetch_url(url)
        except ValueError as e:
            return GateResult(run=False, reason=f"invalid monitor URL: {e}")
        except Exception as e:  # noqa: BLE001  # pragma: no cover - defensive
            logger.warning(
                "Monitor probe failed for job '%s': %s",
                getattr(job, "id", "?"), e,
            )
            return GateResult(run=False, reason=f"monitor probe error: {e}")

        digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        prior_state = state or {}
        if prior_state.get("monitor_sha256") == digest:
            return GateResult(no_change=True, reason="monitor source unchanged")

        stored_output = self._bounded_preview(output)
        previous = prior_state.get("monitor_output")
        context = stored_output
        if isinstance(previous, str):
            context = "\n".join(
                difflib.unified_diff(
                    previous.splitlines(),
                    stored_output.splitlines(),
                    fromfile="previous",
                    tofile="current",
                    lineterm="",
                )
            )
            context = context[:_MAX_MONITOR_CHARS]
            if not context:
                context = "Monitor output changed outside retained preview."
        return GateResult(
            run=True,
            context=context or None,
            state_updates={
                "monitor_sha256": digest,
                "monitor_output": stored_output,
            },
        )

    @staticmethod
    def _bounded_preview(output: str) -> str:
        encoded = output.encode("utf-8")[:_MAX_MONITOR_PREVIEW_BYTES]
        return encoded.decode("utf-8", errors="ignore")

    def _run_command(self, command: str) -> tuple[str, str, int, bool, bool]:
        popen_kwargs: dict = {}
        if _POSIX:
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **popen_kwargs,
        )
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        output_exceeded = threading.Event()

        def drain(stream, chunks: list[str], cap: int, *, stop_on_limit: bool) -> None:
            retained = 0
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                room = cap - retained
                if room > 0:
                    chunks.append(chunk[:room])
                    retained += min(len(chunk), room)
                if len(chunk) > room and stop_on_limit:
                    output_exceeded.set()
                    self._kill_process(proc)
                    break

        stdout_reader = threading.Thread(
            target=drain,
            args=(proc.stdout, stdout_chunks, _MAX_MONITOR_CHARS),
            kwargs={"stop_on_limit": True},
            daemon=True,
        )
        stderr_reader = threading.Thread(
            target=drain,
            args=(proc.stderr, stderr_chunks, _MAX_REASON_CHARS),
            kwargs={"stop_on_limit": False},
            daemon=True,
        )
        stdout_reader.start()
        stderr_reader.start()
        timed_out = False
        try:
            proc.wait(timeout=self._timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_process(proc)
            proc.wait(timeout=5)
        finally:
            stdout_reader.join(timeout=5)
            stderr_reader.join(timeout=5)
            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()

        return (
            "".join(stdout_chunks),
            "".join(stderr_chunks),
            proc.returncode if proc.returncode is not None else 0,
            timed_out,
            output_exceeded.is_set(),
        )

    @staticmethod
    def _kill_process(proc: subprocess.Popen) -> None:
        try:
            if _POSIX:
                os.killpg(os.getpgid(proc.pid), 9)
            else:  # pragma: no cover - non-POSIX
                proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    def _fetch_url(self, url: str) -> str:
        parsed = parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("scheme must be http or https")
        if not parsed.hostname:
            raise ValueError("hostname is required")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("embedded credentials are not allowed")

        try:
            addresses = socket.getaddrinfo(
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except OSError as e:
            raise ValueError(f"hostname could not be resolved: {e}") from e
        public_addresses = []
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise ValueError("target must resolve only to public addresses")
            public_addresses.append(str(ip))

        body = self._request_url(parsed, public_addresses[0])
        if len(body) > _MAX_MONITOR_BYTES:
            raise ValueError("response exceeded 64 KiB limit")
        return body.decode("utf-8", errors="replace")

    def _request_url(self, parsed: parse.SplitResult, address: str) -> bytes:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        connection_class = (
            _PinnedHTTPSConnection
            if parsed.scheme == "https"
            else _PinnedHTTPConnection
        )
        connection = connection_class(
            parsed.hostname or "", address, port, self._timeout,
        )
        path = parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        default_port = 443 if parsed.scheme == "https" else 80
        host = parsed.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        host_header = host if port == default_port else f"{host}:{port}"
        # Total wall-clock deadline for the whole probe: the per-socket
        # ``timeout`` only bounds each individual recv, so a server that
        # drip-feeds a byte just inside every socket window could keep the
        # synchronous body read alive indefinitely and stall the sequential
        # scheduler tick. Enforce an absolute deadline across connect + read.
        deadline = time.monotonic() + self._timeout
        watchdog = threading.Timer(
            self._timeout, self._abort_connection, args=(connection,),
        )
        watchdog.daemon = True
        watchdog.start()
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "Host": host_header,
                    "User-Agent": "PraisonAI-Monitor/1",
                    "Accept-Encoding": "identity",
                },
            )
            response = connection.getresponse()
            if not 200 <= response.status < 300:
                raise RuntimeError(f"HTTP {response.status}")
            return self._read_bounded(response, deadline)
        except Exception as e:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "monitor URL probe exceeded total deadline"
                ) from e
            raise
        finally:
            watchdog.cancel()
            connection.close()
            # Drop the retained raw-socket handle so the fd is not held past the
            # probe. Connections are per-probe, so this keeps the window short.
            if hasattr(connection, "_raw_socket"):
                connection._raw_socket = None

    @staticmethod
    def _abort_connection(connection: Any) -> None:
        # ``http.client.getresponse`` sets ``sock = None`` when it closes a
        # close-delimited reply — exactly the responses whose body can hang
        # forever — so fall back to the pinned raw socket the close path leaves
        # in place. Without it the watchdog fires with nothing to shut down.
        sock = getattr(connection, "sock", None) or getattr(
            connection, "_raw_socket", None,
        )
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        connection.close()

    @staticmethod
    def _read_bounded(response: Any, deadline: float) -> bytes:
        """Read up to the byte cap while enforcing a total wall-clock deadline.

        Reads in bounded chunks and checks an absolute ``deadline`` between
        each so a slow drip-feed cannot keep the synchronous read (and thus
        the scheduler tick) alive past the monitor timeout. Stops once the
        response is exhausted or one byte past the cap is seen (so the caller
        can detect an over-limit body).
        """
        chunks: list[bytes] = []
        remaining = _MAX_MONITOR_BYTES + 1
        while remaining > 0:
            if time.monotonic() >= deadline:
                raise TimeoutError("monitor URL read exceeded total deadline")
            chunk = response.read(min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


class ShellConditionGate:
    """Default pre-run gate: evaluate ``job.pre_run`` as a shell command.

    Implements the core ``JobConditionProtocol``.

    Args:
        timeout: Maximum seconds the pre-run command may run before it is
            treated as a failure (skip). Defaults to 30s.
    """

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def should_run(self, job: Any) -> GateResult:
        command = (getattr(job, "pre_run", None) or "").strip()
        if not command:
            # No gate configured → always run (unconditional, as today).
            return GateResult(run=True)

        # On POSIX, run the shell in a new session (its own process group) so a
        # timeout kills the whole group — otherwise ``subprocess.run`` only kills
        # the shell and leaves any children it spawned running as orphans.
        popen_kwargs: dict = {}
        if _POSIX:
            popen_kwargs["start_new_session"] = True

        proc = None
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **popen_kwargs,
            )
            stdout, stderr = proc.communicate(timeout=self._timeout)
            completed = subprocess.CompletedProcess(
                command, proc.returncode, stdout, stderr,
            )
        except subprocess.TimeoutExpired:
            # Kill the whole process group (POSIX) so children don't orphan,
            # then reap the shell to avoid a zombie.
            if proc is not None:
                try:
                    if _POSIX:
                        os.killpg(os.getpgid(proc.pid), 9)
                    else:  # pragma: no cover - non-POSIX
                        proc.kill()
                except (ProcessLookupError, PermissionError, OSError):  # pragma: no cover
                    proc.kill()
                try:
                    proc.communicate(timeout=5)
                except Exception:  # pragma: no cover - best-effort reap
                    pass
            logger.warning(
                "Pre-run gate timed out for job '%s' (>%.0fs); skipping tick",
                getattr(job, "id", "?"), self._timeout,
            )
            return GateResult(
                run=False,
                reason=f"pre-run gate timed out (>{self._timeout:.0f}s)",
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                "Pre-run gate failed to launch for job '%s': %s; skipping tick",
                getattr(job, "id", "?"), e,
            )
            return GateResult(run=False, reason=f"pre-run gate error: {e}")

        if completed.returncode != 0:
            # Surface a truncated stderr so audit/logs can distinguish a genuine
            # "nothing to do" from a misconfigured gate (auth failure, missing
            # binary, etc.) rather than discarding the diagnostic entirely.
            stderr = (completed.stderr or "").strip()
            reason = "pre-run gate: nothing to do"
            if stderr:
                if len(stderr) > _MAX_REASON_CHARS:
                    stderr = stderr[:_MAX_REASON_CHARS] + "…"
                reason = f"{reason} (exit {completed.returncode}: {stderr})"
            return GateResult(run=False, reason=reason)

        output = (completed.stdout or "").strip()
        if len(output) > _MAX_CONTEXT_CHARS:
            output = output[:_MAX_CONTEXT_CHARS]
        context = output or None
        return GateResult(run=True, context=context)

    # Allow the gate to be referenced by command string directly (helper).
    @staticmethod
    def quote(command: str) -> str:
        """Return a shell-safe quoting of ``command`` (convenience helper)."""
        return shlex.quote(command)
