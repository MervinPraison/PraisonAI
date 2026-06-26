"""
Thin client used by ``praisonai run`` to forward a prompt to a warm runtime.

The client speaks a tiny loopback HTTP protocol against the runtime described by
the project lockfile. It uses only the standard library (``urllib``) so importing
it never pulls in heavy/optional dependencies, keeping the cold path fast.

If the runtime is unreachable, the client raises :class:`RuntimeUnavailable` so
the caller can fall back to in-process execution transparently.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, Optional
from urllib import request as _urlrequest
from urllib import error as _urlerror

from .descriptor import RuntimeDescriptor


class RuntimeUnavailable(Exception):
    """Raised when the warm runtime cannot be reached or returns an error."""


class RuntimeClient:
    """Minimal HTTP client for a warm PraisonAI runtime."""

    def __init__(self, descriptor: RuntimeDescriptor, timeout: float = 300.0):
        self._descriptor = descriptor
        self._timeout = timeout

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self._descriptor.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = _urlrequest.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self._descriptor.token}")
        try:
            with _urlrequest.urlopen(req, timeout=self._timeout) as resp:
                data = resp.read().decode("utf-8")
        except _urlerror.HTTPError as e:
            raise RuntimeUnavailable(f"runtime returned HTTP {e.code}") from e
        except (_urlerror.URLError, OSError) as e:
            raise RuntimeUnavailable(f"runtime unreachable: {e}") from e
        try:
            return json.loads(data) if data else {}
        except ValueError as e:
            raise RuntimeUnavailable("runtime returned invalid response") from e

    def ping(self) -> bool:
        """Return True if the runtime responds to a health check."""
        try:
            result = self._post("/healthz", {})
        except RuntimeUnavailable:
            return False
        return bool(result.get("ok"))

    def run(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Forward a prompt to the warm runtime and return the result text.

        Raises:
            RuntimeUnavailable: if the runtime is unreachable or errors out.
        """
        payload: Dict[str, Any] = {"prompt": prompt}
        if model:
            payload["model"] = model
        if session_id:
            payload["session_id"] = session_id
        result = self._post("/run", payload)
        if not result.get("ok", False):
            raise RuntimeUnavailable(result.get("error", "runtime run failed"))
        return str(result.get("result", ""))

    def attach(self, session_id: str) -> Iterator[Dict[str, Any]]:
        """Yield live events for ``session_id`` as they are published.

        Opens the runtime's Server-Sent Events stream for the session and yields
        each decoded event dict until the stream closes or the runtime goes away.
        Heartbeat/comment lines are skipped.

        Raises:
            RuntimeUnavailable: if the stream cannot be opened.
        """
        url = f"{self._descriptor.base_url}/sessions/{session_id}/events"
        req = _urlrequest.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {self._descriptor.token}")
        req.add_header("Accept", "text/event-stream")
        try:
            # No read timeout: the stream is long-lived and uses heartbeats.
            resp = _urlrequest.urlopen(req)
        except _urlerror.HTTPError as e:
            raise RuntimeUnavailable(f"runtime returned HTTP {e.code}") from e
        except (_urlerror.URLError, OSError) as e:
            raise RuntimeUnavailable(f"runtime unreachable: {e}") from e
        try:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                if not line or line.startswith(":"):
                    # Blank separators and comment/heartbeat lines.
                    continue
                if line.startswith("data:"):
                    data = line[len("data:"):].strip()
                    if not data:
                        continue
                    try:
                        yield json.loads(data)
                    except ValueError:
                        continue
        finally:
            try:
                resp.close()
            except Exception:
                pass
