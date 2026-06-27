"""
Browser-based (OAuth / device-code) provider sign-in for the PraisonAI CLI.

This module implements the operator-onboarding OAuth flow for the ``auth login``
command. It intentionally lives in the wrapper layer (``praisonai``) because it
is heavy, provider-specific onboarding UX; it *reuses* the protocol-first OAuth
primitives shipped in the core SDK (``praisonaiagents.mcp``) rather than
reimplementing PKCE / a local-callback server.

Two flow styles are supported per provider:
- ``device``: RFC 8628 device-authorization grant (print a code + URL, poll).
- ``authcode``: RFC 7636 authorization-code + PKCE via a local callback.

Provider OAuth endpoints are not hardcoded for unknown providers; a provider is
"OAuth-capable" only if it appears in :data:`OAUTH_PROVIDERS` or the caller
supplies explicit endpoints. Providers without a config fall back to API-key
login automatically (handled by the CLI command).
"""

import time
import webbrowser
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass
class OAuthProviderConfig:
    """OAuth endpoint configuration for a single provider."""
    flow: str  # "device" or "authcode"
    client_id: str
    token_url: str
    device_authorization_url: Optional[str] = None
    authorization_url: Optional[str] = None
    scope: Optional[str] = None
    audience: Optional[str] = None
    extra_auth_params: Dict[str, str] = field(default_factory=dict)


# Built-in OAuth-capable providers. This registry is intentionally small and
# additive: providers absent here transparently fall back to API-key login.
# Endpoints can also be supplied at call-time (e.g. for self-hosted gateways).
OAUTH_PROVIDERS: Dict[str, OAuthProviderConfig] = {}


def get_provider_config(
    provider: str,
    overrides: Optional[Dict[str, Any]] = None,
) -> Optional[OAuthProviderConfig]:
    """
    Resolve an :class:`OAuthProviderConfig` for ``provider``.

    Args:
        provider: Provider name (case-insensitive).
        overrides: Optional dict of endpoint overrides. If it contains the
            minimum required fields it is used to construct an ad-hoc config,
            allowing OAuth for providers not in the built-in registry.

    Returns:
        Config if the provider supports OAuth, else None.
    """
    overrides = overrides or {}
    base = OAUTH_PROVIDERS.get(provider.lower())

    merged: Dict[str, Any] = {}
    if base is not None:
        merged.update(base.__dict__)
    merged.update({k: v for k, v in overrides.items() if v is not None})

    if not merged.get("client_id") or not merged.get("token_url"):
        return None
    if not merged.get("flow"):
        merged["flow"] = "device" if merged.get("device_authorization_url") else "authcode"

    return OAuthProviderConfig(
        flow=merged["flow"],
        client_id=merged["client_id"],
        token_url=merged["token_url"],
        device_authorization_url=merged.get("device_authorization_url"),
        authorization_url=merged.get("authorization_url"),
        scope=merged.get("scope"),
        audience=merged.get("audience"),
        extra_auth_params=merged.get("extra_auth_params") or {},
    )


def provider_supports_oauth(
    provider: str,
    overrides: Optional[Dict[str, Any]] = None,
) -> bool:
    """Return True if ``provider`` has a usable OAuth configuration."""
    return get_provider_config(provider, overrides) is not None


def _tokens_to_credential_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a token endpoint response into store kwargs."""
    access_token = payload.get("access_token")
    expires_in = payload.get("expires_in")
    expires_at = (time.time() + float(expires_in)) if expires_in else None
    return {
        "access_token": access_token,
        "refresh_token": payload.get("refresh_token"),
        "expires_at": expires_at,
        "scope": payload.get("scope"),
    }


def run_device_code_flow(
    config: OAuthProviderConfig,
    *,
    open_browser: bool = True,
    on_prompt=None,
    poll_timeout: float = 300.0,
) -> Dict[str, Any]:
    """
    Run the RFC 8628 device-authorization flow.

    Args:
        config: Provider OAuth config (must have ``device_authorization_url``).
        open_browser: Whether to attempt opening the verification URL.
        on_prompt: Optional callback ``(verification_uri, user_code)`` used to
            display instructions to the user.
        poll_timeout: Max seconds to poll for authorization.

    Returns:
        Dict of credential kwargs (access_token, refresh_token, expires_at,
        scope) plus ``token_url`` and ``client_id`` for later refresh.

    Raises:
        RuntimeError: On request failure or timeout.
    """
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "OAuth login requires the optional 'requests' package. "
            "Install it with: pip install requests"
        ) from exc

    if not config.device_authorization_url:
        raise RuntimeError("Provider does not define a device authorization endpoint")

    data = {"client_id": config.client_id}
    if config.scope:
        data["scope"] = config.scope
    if config.audience:
        data["audience"] = config.audience

    resp = requests.post(config.device_authorization_url, data=data, timeout=30)
    resp.raise_for_status()
    dev = resp.json()

    device_code = dev.get("device_code")
    user_code = dev.get("user_code")
    verification_uri = dev.get("verification_uri") or dev.get("verification_url")
    verification_uri_complete = dev.get("verification_uri_complete")
    interval = float(dev.get("interval", 5))

    if on_prompt:
        on_prompt(verification_uri, user_code)

    if open_browser and (verification_uri_complete or verification_uri):
        try:
            webbrowser.open(verification_uri_complete or verification_uri)
        except Exception:
            pass

    deadline = time.time() + poll_timeout
    token_data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "device_code": device_code,
        "client_id": config.client_id,
    }

    while time.time() < deadline:
        time.sleep(interval)
        tok = requests.post(config.token_url, data=token_data, timeout=30)
        payload = tok.json()
        if tok.status_code == 200 and payload.get("access_token"):
            return _tokens_to_credential_kwargs(payload)

        error = payload.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        raise RuntimeError(f"Device authorization failed: {error or tok.status_code}")

    raise RuntimeError("Timed out waiting for device authorization")


def run_authcode_flow(
    config: OAuthProviderConfig,
    *,
    open_browser: bool = True,
    on_prompt=None,
    callback_timeout: float = 300.0,
) -> Dict[str, Any]:
    """
    Run the RFC 7636 authorization-code + PKCE flow via a local callback.

    Reuses the core SDK's :class:`OAuthCallbackHandler` and PKCE helpers so the
    wrapper does not reimplement OAuth client primitives.

    Returns:
        Dict of credential kwargs (access_token, refresh_token, expires_at,
        scope).

    Raises:
        RuntimeError: On request failure or timeout.
    """
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "OAuth login requires the optional 'requests' package. "
            "Install it with: pip install requests"
        ) from exc

    from praisonaiagents.mcp.mcp_oauth_callback import (
        OAuthCallbackHandler,
        OAUTH_CALLBACK_PORT,
        OAUTH_CALLBACK_PATH,
        generate_state,
        generate_code_verifier,
        generate_code_challenge,
        get_redirect_url,
    )

    if not config.authorization_url:
        raise RuntimeError("Provider does not define an authorization endpoint")

    handler = OAuthCallbackHandler()
    state = generate_state()
    verifier = generate_code_verifier()
    challenge = generate_code_challenge(verifier)
    redirect_uri = get_redirect_url()

    # ``OAuthCallbackHandler`` only holds in-memory state; it does not listen on
    # the redirect URI. Start a short-lived local HTTP server that receives the
    # provider redirect and forwards (state, code) into the handler so that
    # ``wait_for_callback`` can unblock.
    server = _start_callback_server(handler, OAUTH_CALLBACK_PORT, OAUTH_CALLBACK_PATH)

    params = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if config.scope:
        params["scope"] = config.scope
    if config.audience:
        params["audience"] = config.audience
    params.update(config.extra_auth_params)

    from urllib.parse import urlencode

    auth_url = f"{config.authorization_url}?{urlencode(params)}"

    if on_prompt:
        on_prompt(auth_url, None)
    if open_browser:
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass

    try:
        code = handler.wait_for_callback(state, timeout=callback_timeout)
    finally:
        handler.clear_state(state)
        server.shutdown()
        server.server_close()

    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": config.client_id,
        "code_verifier": verifier,
    }
    tok = requests.post(config.token_url, data=token_data, timeout=30)
    tok.raise_for_status()
    payload = tok.json()
    if not payload.get("access_token"):
        raise RuntimeError("Token endpoint did not return an access token")
    return _tokens_to_credential_kwargs(payload)


def _start_callback_server(handler, port: int, path: str):
    """
    Start a short-lived local HTTP server to receive the OAuth redirect.

    The provider redirects the browser to ``http://127.0.0.1:<port><path>?...``;
    this server parses the ``state``/``code`` (or ``error``) query parameters,
    forwards them into ``handler.receive_callback`` so a blocked
    ``wait_for_callback`` can unblock, and shows a minimal browser confirmation.

    Args:
        handler: An ``OAuthCallbackHandler`` to receive (state, code) pairs.
        port: Localhost port to listen on (matches the registered redirect URI).
        path: Expected callback path.

    Returns:
        A running ``http.server.HTTPServer`` whose ``serve_forever`` loop runs on
        a daemon thread. Callers must ``shutdown()`` + ``server_close()`` it.
    """
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import urlparse, parse_qs

    class _CallbackRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (stdlib-mandated name)
            parsed = urlparse(self.path)
            if parsed.path != path:
                self.send_response(404)
                self.end_headers()
                return

            params = parse_qs(parsed.query)
            state = (params.get("state") or [None])[0]
            code = (params.get("code") or [None])[0]
            error = (params.get("error") or [None])[0]

            if state and code:
                handler.receive_callback(state, code)
                body = b"Sign-in complete. You can close this tab."
            else:
                body = (
                    f"Sign-in failed: {error or 'missing code'}. "
                    "You can close this tab."
                ).encode()

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence default stderr logging
            return

    server = HTTPServer(("127.0.0.1", port), _CallbackRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run_oauth_login(
    provider: str,
    *,
    overrides: Optional[Dict[str, Any]] = None,
    open_browser: bool = True,
    on_prompt=None,
    timeout: float = 300.0,
) -> Tuple[OAuthProviderConfig, Dict[str, Any]]:
    """
    Run the appropriate OAuth flow for ``provider`` and return tokens.

    Args:
        provider: Provider name.
        overrides: Optional endpoint overrides (enables ad-hoc/self-hosted).
        open_browser: Whether to auto-open the browser.
        on_prompt: Optional callback for displaying instructions to the user.
        timeout: Max seconds to wait for authorization.

    Returns:
        Tuple of (resolved config, credential kwargs ready for the store).

    Raises:
        ValueError: If the provider does not support OAuth.
        RuntimeError: On flow failure/timeout.
    """
    config = get_provider_config(provider, overrides)
    if config is None:
        raise ValueError(f"Provider '{provider}' does not support OAuth login")

    if config.flow == "device":
        tokens = run_device_code_flow(
            config, open_browser=open_browser, on_prompt=on_prompt, poll_timeout=timeout
        )
    else:
        tokens = run_authcode_flow(
            config, open_browser=open_browser, on_prompt=on_prompt, callback_timeout=timeout
        )

    return config, tokens
