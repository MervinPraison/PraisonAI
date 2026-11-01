"""
MCP OAuth Provider — zero-config orchestration.

Composes the OAuth building blocks into a single ``ensure_authenticated`` entry
point that transports invoke on a ``401``:

    discovery  ->  dynamic client registration (if no client stored)
               ->  PKCE authorization-code flow (browser + loopback callback)
               ->  token persistence
               ->  transparent refresh on expiry

All heavy work (network I/O, browser, loopback HTTP server) is lazily imported
and only runs when a server actually challenges for OAuth, so servers without
auth — or with pre-supplied client info/tokens — behave exactly as before.
"""

import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Lock, Thread
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode, urlparse, parse_qs

from praisonaiagents._logging import get_logger

from .mcp_oauth_callback import (
    OAuthCallbackHandler,
    OAUTH_CALLBACK_PORT,
    OAUTH_CALLBACK_PATH,
    generate_state,
    generate_code_verifier,
    generate_code_challenge,
    get_redirect_url,
)

logger = get_logger("mcp-oauth-provider")


class InteractiveAuthRequired(RuntimeError):
    """Raised when interactive OAuth is needed but not possible (headless/CI)."""


def _make_callback_server(handler: OAuthCallbackHandler, port: int) -> HTTPServer:
    """Build a minimal loopback HTTP server that feeds codes to ``handler``."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - required name
            parsed = urlparse(self.path)
            if parsed.path != OAUTH_CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return
            params = parse_qs(parsed.query)
            state = (params.get("state") or [""])[0]
            code = (params.get("code") or [""])[0]
            if state and code:
                handler.receive_callback(state, code)
                body = b"Authentication complete. You can close this window."
            else:
                body = b"Authentication failed: missing code or state."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args, **kwargs):  # silence default logging
            pass

    return HTTPServer(("127.0.0.1", port), _Handler)


# One loopback callback server per process, shared by every in-flight flow.
# The redirect URI is fixed (it is what dynamic registration whitelisted), so
# concurrent flows must not each try to bind the port; the state-keyed
# ``OAuthCallbackHandler`` already routes each code to the right flow.
_callback_lock = Lock()
_callback_server: Optional[HTTPServer] = None
_callback_handler: Optional[OAuthCallbackHandler] = None
_callback_refs = 0


def _acquire_callback() -> OAuthCallbackHandler:
    global _callback_server, _callback_handler, _callback_refs
    with _callback_lock:
        if _callback_server is None:
            handler = OAuthCallbackHandler()
            server = _make_callback_server(handler, OAUTH_CALLBACK_PORT)
            Thread(target=server.serve_forever, daemon=True).start()
            _callback_server, _callback_handler = server, handler
        _callback_refs += 1
        return _callback_handler


def _release_callback() -> None:
    global _callback_server, _callback_handler, _callback_refs
    with _callback_lock:
        _callback_refs -= 1
        if _callback_refs <= 0 and _callback_server is not None:
            _callback_server.shutdown()
            _callback_server.server_close()
            _callback_server, _callback_handler, _callback_refs = None, None, 0


def _parse_redirect(url: str) -> Tuple[str, str]:
    """Extract ``(state, code)`` from a pasted redirect URL."""
    params = parse_qs(urlparse(url.strip()).query)
    return (params.get("state") or [""])[0], (params.get("code") or [""])[0]


# Headless fallback: a single terminal reader shared by all flows waiting on a
# pasted redirect. Per-flow readers would race for stdin and drop each other's
# pastes; one reader routes each paste to the shared state-keyed handler.
_paste_states: set = set()
_paste_reader: Optional[Thread] = None


def _paste_loop() -> None:
    global _paste_reader
    while True:
        try:
            line: Optional[str] = input("Or paste the full redirect URL here: ")
        except (EOFError, OSError):
            line = None
        handler = None
        got_state, code = _parse_redirect(line or "")
        with _callback_lock:
            if line is not None and code and got_state in _paste_states:
                _paste_states.discard(got_state)
                handler = _callback_handler
            stop = line is None or not _paste_states
            if stop:
                _paste_reader = None  # nothing left waiting; next flow restarts us
        if handler is not None:
            handler.receive_callback(got_state, code)
        elif line is not None:
            print("Pasted URL has no matching state/code; ignored.", file=sys.stderr)
        if stop:
            return


def _await_paste(state: str) -> None:
    global _paste_reader
    with _callback_lock:
        _paste_states.add(state)
        if _paste_reader is None:
            _paste_reader = Thread(target=_paste_loop, daemon=True)
            _paste_reader.start()


class MCPOAuthProvider:
    """
    Orchestrates zero-config OAuth for a single remote MCP server.

    Args:
        mcp_name: Stable identifier used as the storage key.
        server_url: The MCP server URL.
        storage: Optional pre-built ``MCPAuthStorage`` (created lazily otherwise).
        open_browser: Whether to open a browser for interactive auth. Set False
            for headless/CI to get a single actionable ``InteractiveAuthRequired``.
    """

    def __init__(
        self,
        mcp_name: str,
        server_url: str,
        storage: Optional[Any] = None,
        open_browser: bool = True,
    ):
        self.mcp_name = mcp_name
        self.server_url = server_url
        self.open_browser = open_browser
        if storage is None:
            from .mcp_auth_storage import MCPAuthStorage
            storage = MCPAuthStorage()
        self.storage = storage

    def get_valid_token(self) -> Optional[str]:
        """Return a non-expired access token if one is stored, else None."""
        entry = self.storage.get_for_url(self.mcp_name, self.server_url)
        if not entry or not entry.get("tokens"):
            return None
        if self.storage.is_token_expired(self.mcp_name):
            refreshed = self._try_refresh(entry)
            if not refreshed:
                return None
            entry = self.storage.get_for_url(self.mcp_name, self.server_url) or {}
        tokens = entry.get("tokens") or {}
        return tokens.get("access_token")

    def ensure_authenticated(
        self,
        www_authenticate: Optional[str] = None,
        timeout: float = 10.0,
    ) -> str:
        """
        Ensure a valid access token exists, running the full flow if needed.

        Returns:
            A valid bearer access token.

        Raises:
            InteractiveAuthRequired: If interactive auth is needed but disabled.
            RuntimeError: If discovery fails or the flow cannot complete.
        """
        token = self.get_valid_token()
        if token:
            return token

        from .oauth_discovery import discover_oauth_metadata

        metadata = discover_oauth_metadata(
            self.server_url,
            www_authenticate=www_authenticate,
            timeout=timeout,
        )
        if not metadata:
            raise RuntimeError(
                f"Could not discover OAuth metadata for {self.server_url}. "
                "The server may not advertise standard authorization-server "
                "metadata; supply client credentials manually."
            )

        client_info = self._ensure_client(metadata, timeout=timeout)

        scope = None
        scopes = metadata.get("scopes_supported")
        if scopes:
            scope = " ".join(scopes)

        return self._run_pkce_flow(metadata, client_info, scope, timeout=timeout)

    def _ensure_client(
        self,
        metadata: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        """Return stored client info or perform dynamic client registration."""
        entry = self.storage.get_for_url(self.mcp_name, self.server_url)
        if entry and entry.get("client_info", {}).get("client_id"):
            return entry["client_info"]

        registration_endpoint = metadata.get("registration_endpoint")
        if not registration_endpoint:
            raise RuntimeError(
                f"No client is registered for {self.server_url} and the "
                "authorization server does not support dynamic client "
                "registration (no registration_endpoint)."
            )

        from .oauth_registration import register_client

        scope = None
        scopes = metadata.get("scopes_supported")
        if scopes:
            scope = " ".join(scopes)

        client_info = register_client(
            registration_endpoint,
            redirect_uris=[get_redirect_url()],
            scope=scope,
            timeout=timeout,
        )
        self.storage.set_client_info(
            self.mcp_name, client_info, server_url=self.server_url
        )
        return client_info

    def _run_pkce_flow(
        self,
        metadata: Dict[str, Any],
        client_info: Dict[str, Any],
        scope: Optional[str],
        timeout: float,
    ) -> str:
        """Run the interactive PKCE authorization-code flow and store tokens."""
        if not self.open_browser:
            raise InteractiveAuthRequired(
                f"Interactive OAuth is required to authenticate with "
                f"{self.server_url}. Run `praisonai mcp auth {self.mcp_name}` "
                f"from a terminal on this host (works headless/over SSH), or "
                f"pre-supply tokens, to complete authentication."
            )

        state = generate_state()
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)

        params = {
            "response_type": "code",
            "client_id": client_info["client_id"],
            "redirect_uri": get_redirect_url(),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if scope:
            params["scope"] = scope
        if metadata.get("resource"):
            params["resource"] = metadata["resource"]

        auth_url = f"{metadata['authorization_endpoint']}?{urlencode(params)}"

        callback = _acquire_callback()
        try:
            logger.debug(f"Opening browser for OAuth authorization: {auth_url}")
            try:
                opened = webbrowser.open(auth_url)
            except Exception:  # noqa: BLE001 - no usable browser
                opened = False
            if not opened:
                # Headless/remote host: let the operator consent on any device.
                print(
                    f"Open this URL on any device to authorise "
                    f"{self.mcp_name}:\n  {auth_url}\n"
                    f"After consenting, the browser is redirected to "
                    f"{get_redirect_url()} (it may fail to load on another "
                    f"device; that is expected).",
                    file=sys.stderr,
                )
                if sys.stdin is not None and sys.stdin.isatty():
                    _await_paste(state)
            code = callback.wait_for_callback(state, timeout=300.0)
        finally:
            with _callback_lock:
                _paste_states.discard(state)
            callback.clear_state(state)
            _release_callback()

        tokens = self._exchange_code(
            metadata, client_info, code, code_verifier, timeout=timeout
        )
        self.storage.set_tokens(
            self.mcp_name, tokens, server_url=self.server_url
        )
        return tokens["access_token"]

    def _exchange_code(
        self,
        metadata: Dict[str, Any],
        client_info: Dict[str, Any],
        code: str,
        code_verifier: str,
        timeout: float,
    ) -> Dict[str, Any]:
        """Exchange an authorization code for tokens at the token endpoint."""
        import requests  # lazy import — optional dependency

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": get_redirect_url(),
            "client_id": client_info["client_id"],
            "code_verifier": code_verifier,
        }
        if client_info.get("client_secret"):
            data["client_secret"] = client_info["client_secret"]
        if metadata.get("resource"):
            data["resource"] = metadata["resource"]

        resp = requests.post(
            metadata["token_endpoint"],
            data=data,
            headers={"Accept": "application/json"},
            timeout=timeout,
            allow_redirects=False,  # never re-send credentials to a redirect target
        )
        from .oauth_discovery import _require_success

        _require_success(resp)
        return self._normalize_tokens(
            resp.json(), token_endpoint=metadata["token_endpoint"]
        )

    def _try_refresh(self, entry: Dict[str, Any]) -> bool:
        """Attempt a refresh-token grant; return True on success."""
        tokens = entry.get("tokens") or {}
        refresh_token = tokens.get("refresh_token")
        token_endpoint = tokens.get("token_endpoint")
        client_info = entry.get("client_info") or {}
        client_id = client_info.get("client_id")
        if not (refresh_token and token_endpoint and client_id):
            return False

        try:
            from .oauth_discovery import _require_https, _require_success

            # Defense in depth: never POST a refresh token / client secret to a
            # persisted endpoint that isn't HTTPS (or loopback).
            _require_https(token_endpoint)

            import requests  # lazy import — optional dependency

            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            }
            if client_info.get("client_secret"):
                data["client_secret"] = client_info["client_secret"]

            resp = requests.post(
                token_endpoint,
                data=data,
                headers={"Accept": "application/json"},
                timeout=10.0,
                allow_redirects=False,  # never re-send credentials to a redirect target
            )
            _require_success(resp)
            new_tokens = self._normalize_tokens(
                resp.json(), token_endpoint=token_endpoint
            )
            # Preserve refresh_token if the server didn't return a new one.
            if not new_tokens.get("refresh_token"):
                new_tokens["refresh_token"] = refresh_token
            self.storage.set_tokens(
                self.mcp_name, new_tokens, server_url=self.server_url
            )
            return True
        except Exception as exc:  # noqa: BLE001 - refresh is best-effort
            logger.debug(f"Token refresh failed for {self.mcp_name}: {exc}")
            return False

    @staticmethod
    def _normalize_tokens(
        raw: Dict[str, Any],
        token_endpoint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Normalise a token response, computing an absolute ``expires_at``."""
        tokens = dict(raw)
        expires_in = tokens.get("expires_in")
        if expires_in and not tokens.get("expires_at"):
            try:
                tokens["expires_at"] = time.time() + float(expires_in)
            except (TypeError, ValueError):
                pass
        if token_endpoint:
            tokens["token_endpoint"] = token_endpoint
        return tokens
