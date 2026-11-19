"""A built-in OAuth 2.1 authorization server for the HTTP MCP transport.

It follows the MCP authorization spec so editors sign in on their own:

- ``401`` + ``WWW-Authenticate: Bearer resource_metadata=…`` on the MCP endpoint;
- Protected Resource Metadata (RFC 9728) and Authorization Server Metadata (RFC 8414);
- authorization code + PKCE S256 only (RFC 7636), public clients;
- Dynamic Client Registration (RFC 7591) and Client ID Metadata Documents
  (an https ``client_id`` whose document proves the client's domain);
- the token audience is the ``resource`` the client asked for (RFC 8707);
- rotating, single-use refresh tokens with reuse detection: a replayed refresh
  token revokes the whole grant;
- Deny redirects with ``error=access_denied`` (RFC 6749 §4.1.2.1);
- the device flow (RFC 8628) for SSH, containers and CI;
- revocation (RFC 7009) and a list of connected apps.

The consent page is the owner's: it asks once for the owner key (env
``PRAISONAI_MCP_OWNER_KEY``, or one generated and printed at start), then
shows the client, whether it is verified, where it will be sent, and the
scopes in plain words, each of which the owner may untick.

Local use stays zero-auth: the transport turns this on only with ``--oauth``
or when it binds to a non-loopback address without an API key. Tokens are
opaque; only their SHA-256 is stored (``oauth.json`` in the PraisonAI MCP
folder, mode 0600).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse

#: The scopes a client may ask for, in plain words for the consent page.
SCOPES: Dict[str, str] = {
    "tools:read": "See the list of your agents and tools",
    "tools:call": "Run your agents and tools",
    "resources:read": "Read resources the server shares",
    "prompts:read": "Use the server's prompts",
    "tasks:read": "See long-running tasks",
    "tasks:write": "Start and cancel long-running tasks",
}
READ_ONLY = ("tools:read", "resources:read", "prompts:read", "tasks:read")
DEFAULT_SCOPES = ("tools:read", "tools:call", "resources:read", "prompts:read")

ACCESS_TTL = 3600
CODE_TTL = 120
DEVICE_TTL = 600
LIFETIMES = {"30d": 30 * 86400, "7d": 7 * 86400, "1d": 86400, "never": 0}

#: Client ID Metadata Documents we know by URL: the domain proves the client.
TRUSTED_CIMD: Dict[str, str] = {
    "https://vscode.dev/oauth/client-metadata.json": "VS Code",
    "https://antigravity.google/oauth/client-metadata.json": "Antigravity",
    "https://zed.dev/oauth/client-metadata.json": "Zed",
    "https://kiro.dev/oauth/client-metadata.json": "Kiro",
    "https://claude.ai/oauth/claude-code-client-metadata": "Claude Code",
    "https://chatgpt.com/oauth/": "ChatGPT",
    "https://goose-docs.ai/oauth/client-metadata.json": "Goose",
    "https://opencode.ai/oauth/opencode/client.json": "OpenCode",
}
#: Official https callbacks of clients that register dynamically.
TRUSTED_REDIRECTS: Dict[str, str] = {
    "https://www.cursor.com/agents/mcp/oauth/callback": "Cursor",
    "cursor://anysphere.cursor-mcp/oauth/callback": "Cursor",
    "https://vscode.dev/redirect": "VS Code",
    "https://antigravity.google/oauth-callback": "Antigravity",
    "https://claude.ai/api/mcp/auth_callback": "Claude",
    "https://chatgpt.com/connector_platform_oauth_redirect": "ChatGPT",
    "https://chatgpt.com/connector/oauth/": "ChatGPT",
}
LOOPBACK = ("localhost", "127.0.0.1", "::1", "[::1]")


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _is_loopback(uri: str) -> bool:
    p = urlparse(uri)
    return p.scheme == "http" and (p.hostname or "") in LOOPBACK


def _known(table: Dict[str, str], value: str) -> Optional[str]:
    for key, label in table.items():
        if value == key or (key.endswith("/") and value.startswith(key)):
            return label
    return None


def redirect_matches(registered: List[str], uri: str) -> bool:
    """Exact match, except a loopback redirect may use any port (RFC 8252 §7.3)."""
    if uri in registered:
        return True
    if not _is_loopback(uri):
        return False
    p = urlparse(uri)
    for r in registered:
        q = urlparse(r)
        if _is_loopback(r) and q.hostname == p.hostname and (q.path or "/") == (p.path or "/"):
            return True
    return False


def fetch_client_metadata(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    """A Client ID Metadata Document (https only, at most 64 KiB)."""
    if urlparse(url).scheme != "https":
        raise ValueError("client_id metadata must be served over https")
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https only
        doc = json.loads(resp.read(65536).decode("utf-8"))
    if not isinstance(doc, dict) or doc.get("client_id") != url:
        raise ValueError("client_id in the metadata document does not match its URL")
    if not isinstance(doc.get("redirect_uris"), list) or not doc["redirect_uris"]:
        raise ValueError("the metadata document lists no redirect_uris")
    return doc


@dataclass
class Pending:
    """An authorization request waiting on the owner (code or device flow)."""

    client_id: str
    scopes: List[str]
    resource: str
    redirect_uri: str = ""
    state: Optional[str] = None
    challenge: str = ""
    user_code: str = ""
    expires: float = field(default_factory=lambda: time.time() + DEVICE_TTL)
    approved: Optional[Dict[str, Any]] = None  # device flow: the grant once approved
    denied: bool = False
    last_poll: float = 0.0


class OAuthServer:
    """The authorization server. ``validate_header`` plugs into the transport."""

    def __init__(self, issuer: str, resource: str, owner_key: Optional[str] = None,
                 store_path: Optional[Path] = None,
                 fetch_metadata=fetch_client_metadata) -> None:
        self.issuer = issuer.rstrip("/")
        self.resource = resource
        self.generated_key = not (owner_key or os.environ.get("PRAISONAI_MCP_OWNER_KEY"))
        self.owner_key = owner_key or os.environ.get("PRAISONAI_MCP_OWNER_KEY") or secrets.token_urlsafe(18)
        self.path = store_path
        self._fetch = fetch_metadata
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {"clients": {}, "grants": {}}
        self._codes: Dict[str, Tuple[Pending, float]] = {}
        self._pending: Dict[str, Pending] = {}
        self._devices: Dict[str, Pending] = {}
        self._cimd: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._load()

    # ── storage ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if self.path and self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._data = {"clients": data.get("clients", {}), "grants": data.get("grants", {})}
            except (OSError, ValueError):
                pass

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=1)
        os.replace(tmp, self.path)

    # ── metadata ─────────────────────────────────────────────────────

    @property
    def resource_metadata_url(self) -> str:
        path = urlparse(self.resource).path.strip("/")
        return f"{self.issuer}/.well-known/oauth-protected-resource" + (f"/{path}" if path else "")

    def www_authenticate(self, error: Optional[str] = None) -> str:
        parts = [f'resource_metadata="{self.resource_metadata_url}"', f'scope="{" ".join(DEFAULT_SCOPES)}"']
        if error:
            parts.append(f'error="{error}"')
        return "Bearer " + ", ".join(parts)

    def protected_resource_metadata(self) -> Dict[str, Any]:
        return {"resource": self.resource, "authorization_servers": [self.issuer],
                "bearer_methods_supported": ["header"], "scopes_supported": list(SCOPES)}

    def authorization_server_metadata(self) -> Dict[str, Any]:
        i = self.issuer
        return {
            "issuer": i,
            "authorization_endpoint": f"{i}/oauth/authorize",
            "token_endpoint": f"{i}/oauth/token",
            "registration_endpoint": f"{i}/oauth/register",
            "revocation_endpoint": f"{i}/oauth/revoke",
            "device_authorization_endpoint": f"{i}/oauth/device",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token",
                                      "urn:ietf:params:oauth:grant-type:device_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": list(SCOPES),
            "client_id_metadata_document_supported": True,
        }

    # ── clients ──────────────────────────────────────────────────────

    def register(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """Dynamic Client Registration (RFC 7591), public clients only."""
        uris = body.get("redirect_uris")
        if not isinstance(uris, list) or not uris or not all(isinstance(u, str) for u in uris):
            raise OAuthError("invalid_redirect_uri", "redirect_uris is required")
        for u in uris:
            p = urlparse(u)
            if p.fragment or not p.scheme or (p.scheme == "http" and not _is_loopback(u)):
                raise OAuthError("invalid_redirect_uri", f"{u} is not allowed (https, loopback or an app scheme)")
        client_id = "pmcp_" + secrets.token_urlsafe(16)
        client = {"client_id": client_id, "client_name": str(body.get("client_name") or "")[:80],
                  "redirect_uris": uris, "logo_uri": body.get("logo_uri"),
                  "client_id_issued_at": int(time.time()), "token_endpoint_auth_method": "none"}
        with self._lock:
            self._data["clients"][client_id] = client
            self._save()
        return {**client, "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]}

    def client(self, client_id: str) -> Dict[str, Any]:
        """A registered client, or a Client ID Metadata Document client."""
        stored = self._data["clients"].get(client_id)
        if stored:
            return stored
        if client_id.startswith("https://"):
            hit = self._cimd.get(client_id)
            if not hit or hit[0] < time.time():
                try:
                    hit = (time.time() + 3600, self._fetch(client_id))
                except Exception as exc:  # unreachable, too big, wrong client_id…
                    raise OAuthError("invalid_client", f"client metadata document: {exc}") from None
                self._cimd[client_id] = hit
            doc = hit[1]
            return {"client_id": client_id, "client_name": str(doc.get("client_name") or "")[:80],
                    "redirect_uris": doc["redirect_uris"], "logo_uri": doc.get("logo_uri"), "cimd": True}
        raise OAuthError("invalid_client", "unknown client_id")

    def trust(self, client: Dict[str, Any], redirect_uri: str) -> Tuple[str, str]:
        """``(label, level)``: level is ``verified``, ``local`` or ``unverified``."""
        if client.get("cimd"):
            label = _known(TRUSTED_CIMD, client["client_id"])
            # A metadata document proves its domain even when we do not list it.
            return (label or client.get("client_name") or urlparse(client["client_id"]).hostname or "App",
                    "verified")
        label = _known(TRUSTED_REDIRECTS, redirect_uri)
        if label:
            return label, "verified"
        name = client.get("client_name") or "An app"
        return (name, "local") if _is_loopback(redirect_uri) else (name, "unverified")

    # ── authorization code flow ──────────────────────────────────────

    def start(self, q: Dict[str, str]) -> Tuple[str, Pending, Dict[str, Any]]:
        """Validate an authorize request; errors that cannot redirect raise."""
        client = self.client(q.get("client_id", ""))
        redirect = q.get("redirect_uri") or (client["redirect_uris"][0] if len(client["redirect_uris"]) == 1 else "")
        if not redirect or not redirect_matches(client["redirect_uris"], redirect):
            raise OAuthError("invalid_request", "redirect_uri does not match the client's")
        pending = Pending(client_id=client["client_id"], scopes=[], resource="", redirect_uri=redirect,
                          state=q.get("state"), challenge=q.get("code_challenge", ""))
        if q.get("response_type") != "code":
            raise RedirectError(pending, "unsupported_response_type")
        if not pending.challenge or q.get("code_challenge_method") != "S256":
            raise RedirectError(pending, "invalid_request", "PKCE with S256 is required")
        pending.resource = q.get("resource") or self.resource
        if pending.resource.rstrip("/") != self.resource.rstrip("/"):
            raise RedirectError(pending, "invalid_target", "resource is not this server")
        asked = (q.get("scope") or " ".join(DEFAULT_SCOPES)).split()
        pending.scopes = [s for s in asked if s in SCOPES] or list(DEFAULT_SCOPES)
        rid = secrets.token_urlsafe(16)
        with self._lock:
            self._pending[rid] = pending
        return rid, pending, client

    def decide(self, rid: str, approve: bool, scopes: List[str], lifetime: str = "30d") -> str:
        """The redirect URL for the owner's answer."""
        with self._lock:
            pending = self._pending.pop(rid, None)
        if not pending or pending.expires < time.time():
            raise OAuthError("invalid_request", "this sign-in request expired; start again from the app")
        if not approve:
            return _redirect(pending, {"error": "access_denied", "error_description": "The owner declined."})
        granted = [s for s in scopes if s in pending.scopes]
        if not granted:
            return _redirect(pending, {"error": "access_denied", "error_description": "No access was granted."})
        code = secrets.token_urlsafe(32)
        pending.scopes = granted
        with self._lock:
            self._codes[_h(code)] = (pending, LIFETIMES.get(lifetime, LIFETIMES["30d"]))
        pending.expires = time.time() + CODE_TTL
        return _redirect(pending, {"code": code})

    # ── tokens ───────────────────────────────────────────────────────

    def token(self, form: Dict[str, str]) -> Dict[str, Any]:
        grant_type = form.get("grant_type")
        if grant_type == "authorization_code":
            with self._lock:
                entry = self._codes.pop(_h(form.get("code", "")), None)
            if not entry or entry[0].expires < time.time():
                raise OAuthError("invalid_grant", "the code is invalid or expired")
            pending, lifetime = entry
            if form.get("client_id") != pending.client_id or form.get("redirect_uri", pending.redirect_uri) != pending.redirect_uri:
                raise OAuthError("invalid_grant", "client_id or redirect_uri does not match")
            verifier = form.get("code_verifier", "")
            digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            if not verifier or not hmac.compare_digest(digest, pending.challenge):
                raise OAuthError("invalid_grant", "PKCE verification failed")
            if form.get("resource") and form["resource"].rstrip("/") != pending.resource.rstrip("/"):
                raise OAuthError("invalid_target", "resource does not match the authorization")
            return self._new_grant(pending, lifetime)
        if grant_type == "refresh_token":
            return self._refresh(form.get("refresh_token", ""), form.get("client_id"))
        if grant_type == "urn:ietf:params:oauth:grant-type:device_code":
            return self._device_token(form.get("device_code", ""), form.get("client_id"))
        raise OAuthError("unsupported_grant_type", f"{grant_type!r} is not supported")

    def _new_grant(self, pending: Pending, lifetime: int) -> Dict[str, Any]:
        client = self.client(pending.client_id)
        label, level = self.trust(client, pending.redirect_uri or "device:")
        gid = "g_" + secrets.token_urlsafe(10)
        now = time.time()
        grant = {"id": gid, "client_id": pending.client_id, "client": label, "trust": level,
                 "scopes": pending.scopes, "aud": pending.resource, "created": now, "last_used": now,
                 "expires": now + lifetime if lifetime else 0, "access": {}, "refresh": "", "used_refresh": []}
        with self._lock:
            self._data["grants"][gid] = grant
            return self._issue(grant)

    def _issue(self, grant: Dict[str, Any]) -> Dict[str, Any]:
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = time.time()
        grant["access"] = {k: v for k, v in grant["access"].items() if v > now}
        grant["access"][_h(access)] = now + ACCESS_TTL
        if grant["refresh"]:
            grant["used_refresh"] = (grant["used_refresh"] + [grant["refresh"]])[-20:]
        grant["refresh"] = _h(refresh)
        self._save()
        return {"access_token": access, "token_type": "Bearer", "expires_in": ACCESS_TTL,
                "refresh_token": refresh, "scope": " ".join(grant["scopes"])}

    def _refresh(self, token: str, client_id: Optional[str]) -> Dict[str, Any]:
        digest = _h(token)
        with self._lock:
            for gid, grant in list(self._data["grants"].items()):
                if digest in grant["used_refresh"]:
                    # Replay of a rotated token: someone else holds it. Revoke all.
                    del self._data["grants"][gid]
                    self._save()
                    raise OAuthError("invalid_grant", "refresh token reuse detected; the app was disconnected")
                if hmac.compare_digest(grant["refresh"], digest):
                    if client_id and client_id != grant["client_id"]:
                        raise OAuthError("invalid_grant", "client_id does not match")
                    if grant["expires"] and grant["expires"] < time.time():
                        raise OAuthError("invalid_grant", "access expired; sign in again")
                    return self._issue(grant)
        raise OAuthError("invalid_grant", "unknown refresh token")

    def validate_header(self, header: str) -> Tuple[bool, Optional[Any]]:
        """``(valid, holder-with-scopes)`` for the transport's auth check."""
        if not header.startswith("Bearer "):
            return False, None
        digest, now = _h(header[7:].strip()), time.time()
        with self._lock:
            for grant in self._data["grants"].values():
                exp = grant["access"].get(digest)
                if exp and exp > now and grant["aud"].rstrip("/") == self.resource.rstrip("/"):
                    if now - grant["last_used"] > 60:
                        grant["last_used"] = now
                        self._save()
                    return True, SimpleNamespace(scopes=list(grant["scopes"]), grant=grant["id"])
        return False, None

    def revoke_token(self, token: str) -> None:
        """RFC 7009: revoking either token ends the grant."""
        digest = _h(token)
        with self._lock:
            for gid, grant in list(self._data["grants"].items()):
                if digest == grant["refresh"] or digest in grant["access"]:
                    del self._data["grants"][gid]
                    self._save()
                    return

    # ── device flow ──────────────────────────────────────────────────

    def device_start(self, form: Dict[str, str]) -> Dict[str, Any]:
        client = self.client(form.get("client_id", ""))
        asked = (form.get("scope") or " ".join(DEFAULT_SCOPES)).split()
        resource = form.get("resource") or self.resource
        if resource.rstrip("/") != self.resource.rstrip("/"):
            raise OAuthError("invalid_target", "resource is not this server")
        alphabet = "BCDFGHJKLMNPQRSTVWXZ"
        user_code = "".join(secrets.choice(alphabet) for _ in range(8))
        device_code = secrets.token_urlsafe(32)
        pending = Pending(client_id=client["client_id"], scopes=[s for s in asked if s in SCOPES] or list(DEFAULT_SCOPES),
                          resource=resource, user_code=user_code)
        with self._lock:
            self._devices[_h(device_code)] = pending
        pretty = f"{user_code[:4]}-{user_code[4:]}"
        return {"device_code": device_code, "user_code": pretty,
                "verification_uri": f"{self.issuer}/oauth/device/verify",
                "verification_uri_complete": f"{self.issuer}/oauth/device/verify?user_code={pretty}",
                "expires_in": DEVICE_TTL, "interval": 5}

    def device_lookup(self, user_code: str) -> Optional[Pending]:
        code = user_code.replace("-", "").replace(" ", "").upper()
        return next((p for p in self._devices.values() if p.user_code == code and p.expires > time.time()), None)

    def device_decide(self, pending: Pending, approve: bool, scopes: List[str], lifetime: str = "30d") -> None:
        granted = [s for s in scopes if s in pending.scopes]
        if not approve or not granted:
            pending.denied = True
            return
        pending.scopes = granted
        pending.approved = {"lifetime": LIFETIMES.get(lifetime, LIFETIMES["30d"])}

    def _device_token(self, device_code: str, client_id: Optional[str]) -> Dict[str, Any]:
        key = _h(device_code)
        pending = self._devices.get(key)
        if not pending or pending.expires < time.time():
            raise OAuthError("expired_token", "the device code expired")
        if client_id and client_id != pending.client_id:
            raise OAuthError("invalid_grant", "client_id does not match")
        if pending.denied:
            self._devices.pop(key, None)
            raise OAuthError("access_denied", "The owner declined.")
        if not pending.approved:
            now, last = time.time(), pending.last_poll
            pending.last_poll = now
            raise OAuthError("slow_down" if now - last < 5 else "authorization_pending", "waiting for the owner")
        self._devices.pop(key, None)
        return self._new_grant(pending, pending.approved["lifetime"])

    # ── connected apps ───────────────────────────────────────────────

    def apps(self) -> List[Dict[str, Any]]:
        now = time.time()
        rows = [{k: g[k] for k in ("id", "client", "trust", "scopes", "created", "last_used", "expires")}
                for g in self._data["grants"].values() if not g["expires"] or g["expires"] > now]
        return sorted(rows, key=lambda r: r["last_used"], reverse=True)

    def revoke_grant(self, gid: str) -> bool:
        with self._lock:
            found = self._data["grants"].pop(gid, None) is not None
            if found:
                self._save()
            return found

    # ── owner session (consent pages) ────────────────────────────────

    def owner_cookie(self) -> str:
        return hmac.new(self.owner_key.encode(), b"owner-session", hashlib.sha256).hexdigest()

    def is_owner(self, cookie: Optional[str], key: Optional[str]) -> bool:
        if key and hmac.compare_digest(key.strip(), self.owner_key):
            return True
        return bool(cookie) and hmac.compare_digest(cookie, self.owner_cookie())

    def csrf(self, rid: str) -> str:
        return hmac.new(self.owner_key.encode(), f"csrf:{rid}".encode(), hashlib.sha256).hexdigest()


class OAuthError(Exception):
    def __init__(self, error: str, description: str = "") -> None:
        super().__init__(description or error)
        self.error, self.description = error, description

    def body(self) -> Dict[str, str]:
        return {"error": self.error, "error_description": self.description} if self.description else {"error": self.error}


class RedirectError(OAuthError):
    """An authorize error the client must hear about at its redirect_uri."""

    def __init__(self, pending: Pending, error: str, description: str = "") -> None:
        super().__init__(error, description)
        self.pending = pending


def _redirect(pending: Pending, params: Dict[str, str]) -> str:
    if pending.state is not None:
        params = {**params, "state": pending.state}
    sep = "&" if "?" in pending.redirect_uri else "?"
    return pending.redirect_uri + sep + urlencode(params)


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)
