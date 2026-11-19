"""Starlette routes for :class:`~.server.OAuthServer`: metadata, registration,
the consent and device pages, tokens, revocation and connected apps.

The two pages are plain server-rendered HTML (no script, every value
escaped), light and dark, and work at phone width.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib.parse import urlparse

from .server import LIFETIMES, READ_ONLY, SCOPES, OAuthError, OAuthServer, Pending, RedirectError, esc

COOKIE = "pmcp_owner"

_CSS = """
:root{--bg:#fafaf9;--fg:#1c1917;--mut:#57534e;--line:#e7e5e4;--card:#fff;--acc:#1d4ed8;--ok:#15803d;--warn:#b45309;--bad:#b91c1c}
@media (prefers-color-scheme:dark){:root{--bg:#0c0a09;--fg:#f5f5f4;--mut:#a8a29e;--line:#292524;--card:#1c1917;--acc:#93c5fd;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:30rem;margin:2rem auto;padding:0 1rem}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1.25rem}
h1{font-size:1.25rem;margin:0 0 .25rem}p{margin:.5rem 0}.mut{color:var(--mut);font-size:.875rem}
.badge{display:inline-block;font-size:.75rem;font-weight:600;border-radius:999px;padding:.1rem .55rem;border:1px solid currentColor}
.verified{color:var(--ok)}.local{color:var(--acc)}.unverified{color:var(--bad)}
.warn{border:1px solid var(--bad);color:var(--bad);border-radius:8px;padding:.6rem .75rem;margin:.75rem 0;font-size:.875rem}
label.scope{display:flex;gap:.6rem;align-items:flex-start;padding:.45rem 0;border-top:1px solid var(--line)}
input[type=checkbox]{width:1.1rem;height:1.1rem;margin-top:.2rem}input[type=password],input[type=text],select{width:100%;padding:.55rem;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:inherit}
.row{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:1rem}button{font:inherit;border-radius:8px;padding:.55rem 1rem;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button.primary{background:var(--acc);border-color:var(--acc);color:var(--bg);font-weight:600}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
code{font-size:.8rem;word-break:break-all}details{margin-top:.75rem}
"""


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<meta name=referrer content=no-referrer><title>{esc(title)}</title><style>{_CSS}</style></head>"
            f"<body><main><div class=card>{body}</div></main></body></html>")


def _scope_boxes(scopes: List[str]) -> str:
    return "".join(
        f"<label class=scope><input type=checkbox name=scope value='{esc(s)}' checked>"
        f"<span>{esc(SCOPES[s])}<br><span class=mut><code>{esc(s)}</code></span></span></label>"
        for s in scopes
    )


def _owner_field(is_owner: bool) -> str:
    if is_owner:
        return "<p class=mut>Signed in as the server owner.</p>"
    return ("<p><label for=k>Owner key</label><br><input id=k type=password name=owner_key autocomplete=current-password required>"
            "<span class=mut>Printed when the server started, or <code>PRAISONAI_MCP_OWNER_KEY</code>.</span></p>")


def _consent(server: OAuthServer, rid: str, pending: Pending, client: Dict[str, Any], is_owner: bool,
             action: str, error: str = "") -> str:
    label, level = server.trust(client, pending.redirect_uri or "device:")
    host = urlparse(pending.redirect_uri).hostname or urlparse(pending.redirect_uri).scheme or "this device"
    badge = {"verified": "Verified", "local": "On this device", "unverified": "Not verified"}[level]
    warning = (f"<div class=warn role=alert>We could not verify this app. After you allow it you are sent to "
               f"<strong>{esc(host)}</strong>. Allow only if you started this sign-in.</div>") if level == "unverified" else ""
    lifetimes = "".join(f"<option value={k}>{t}</option>" for k, t in
                        (("30d", "30 days"), ("7d", "7 days"), ("1d", "1 day"), ("never", "Until I revoke it")))
    err = f"<div class=warn role=alert>{esc(error)}</div>" if error else ""
    details = (f"<details><summary class=mut>Details</summary><p class=mut>Redirect: <code>{esc(pending.redirect_uri)}</code><br>"
               f"Client: <code>{esc(client['client_id'])}</code><br>Server: <code>{esc(pending.resource)}</code></p></details>"
               if pending.redirect_uri else "")
    body = (f"<h1>Connect {esc(label)}</h1><p><span class='badge {level}'>{badge}</span></p>"
            f"<p>{esc(label)} wants to use this PraisonAI server.</p>{warning}{err}"
            f"<form method=post action='{esc(action)}'><input type=hidden name=rid value='{esc(rid)}'>"
            f"<input type=hidden name=csrf value='{esc(server.csrf(rid))}'>{_owner_field(is_owner)}"
            f"<p><strong>It may</strong></p>{_scope_boxes(pending.scopes)}"
            f"<p><label for=life>Access lasts</label><select id=life name=lifetime>{lifetimes}</select></p>"
            f"<div class=row><button class=primary name=decision value=allow>Allow</button>"
            f"<button name=decision value=read>Allow read-only</button><button name=decision value=deny formnovalidate>Deny</button></div>"
            f"</form>{details}")
    return _page(f"Connect {label}", body)


def build_routes(server: OAuthServer, mcp_path: str = "/mcp") -> list:
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
    from starlette.routing import Route

    no_store = {"Cache-Control": "no-store", "Pragma": "no-cache"}
    # The consent pages never render inside another site's frame (clickjacking).
    page_headers = {**no_store, "X-Frame-Options": "DENY",
                    # No form-action: Allow redirects on to the app's own scheme (cursor://…).
                    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"}

    def _html(content: str, status: int = 200) -> HTMLResponse:
        return HTMLResponse(content, status_code=status, headers=page_headers)

    def jerr(exc: OAuthError, status: int = 400) -> JSONResponse:
        return JSONResponse(exc.body(), status_code=401 if exc.error == "invalid_client" else status, headers=no_store)

    def owner(request: Request, form_key: str = "") -> bool:
        bearer = request.headers.get("authorization", "")
        key = form_key or (bearer[7:] if bearer.startswith("Bearer ") else "")
        return server.is_owner(request.cookies.get(COOKIE), key)

    def with_cookie(resp, request: Request):
        resp.set_cookie(COOKIE, server.owner_cookie(), httponly=True, samesite="lax",
                        secure=server.issuer.startswith("https://"), max_age=30 * 86400)
        return resp

    async def prm(request: Request):
        return JSONResponse(server.protected_resource_metadata())

    async def asm(request: Request):
        return JSONResponse(server.authorization_server_metadata())

    async def register(request: Request):
        try:
            body = await request.json()
        except (ValueError, json.JSONDecodeError):
            body = None
        if not isinstance(body, dict):
            return jerr(OAuthError("invalid_client_metadata", "send a JSON object"))
        try:
            return JSONResponse(server.register(body), status_code=201, headers=no_store)
        except OAuthError as exc:
            return jerr(exc)

    async def authorize_get(request: Request):
        try:
            rid, pending, client = server.start(dict(request.query_params))
        except RedirectError as exc:
            from .server import _redirect

            return RedirectResponse(_redirect(exc.pending, exc.body()), status_code=302)
        except OAuthError as exc:
            return _html(_page("Cannot connect", f"<h1>Cannot connect</h1><p>{esc(exc.description or exc.error)}</p>"), 400)
        return _html(_consent(server, rid, pending, client, owner(request), "/oauth/authorize"))

    async def authorize_post(request: Request):
        form = await request.form()
        rid, decision = str(form.get("rid", "")), str(form.get("decision", ""))
        pending = server._pending.get(rid)
        if not pending or str(form.get("csrf", "")) != server.csrf(rid):
            return _html(_page("Expired", "<h1>This sign-in expired</h1><p>Start again from the app.</p>"), 400)
        if decision != "deny" and not owner(request, str(form.get("owner_key", ""))):
            client = server.client(pending.client_id)
            return _html(_consent(server, rid, pending, client, False, "/oauth/authorize", "That owner key is not right."), 401)
        scopes = list(READ_ONLY) if decision == "read" else [str(s) for s in form.getlist("scope")]
        try:
            url = server.decide(rid, decision in ("allow", "read"), scopes, str(form.get("lifetime", "30d")))
        except OAuthError as exc:
            return _html(_page("Expired", f"<h1>Cannot connect</h1><p>{esc(exc.description)}</p>"), 400)
        resp = RedirectResponse(url, status_code=303)
        return with_cookie(resp, request) if decision != "deny" else resp

    async def token(request: Request):
        form = {k: str(v) for k, v in (await request.form()).items()}
        try:
            return JSONResponse(server.token(form), headers=no_store)
        except OAuthError as exc:
            return jerr(exc)

    async def revoke(request: Request):
        form = await request.form()
        server.revoke_token(str(form.get("token", "")))
        return JSONResponse({}, headers=no_store)  # RFC 7009: 200 whatever the token was

    async def device(request: Request):
        form = {k: str(v) for k, v in (await request.form()).items()}
        try:
            return JSONResponse(server.device_start(form), headers=no_store)
        except OAuthError as exc:
            return jerr(exc)

    def device_form(code: str = "", error: str = "") -> HTMLResponse:
        err = f"<div class=warn role=alert>{esc(error)}</div>" if error else ""
        return _html(_page("Connect a device", (
            f"<h1>Connect a device</h1><p>Enter the code the app shows.</p>{err}<form method=get>"
            f"<p><input type=text name=user_code value='{esc(code)}' autocomplete=one-time-code required aria-label='Device code'></p>"
            f"<div class=row><button class=primary>Continue</button></div></form>")), 400 if error else 200)

    async def device_verify_get(request: Request):
        code = request.query_params.get("user_code", "")
        if not code:
            return device_form()
        pending = server.device_lookup(code)
        if not pending:
            return device_form(code, "That code is not valid or has expired.")
        return _html(_consent(server, pending.user_code, pending, server.client(pending.client_id),
                                     owner(request), "/oauth/device/verify"))

    async def device_verify_post(request: Request):
        form = await request.form()
        rid, decision = str(form.get("rid", "")), str(form.get("decision", ""))
        pending = server.device_lookup(rid)
        if not pending or str(form.get("csrf", "")) != server.csrf(rid):
            return device_form(error="That code is not valid or has expired.")
        if decision != "deny" and not owner(request, str(form.get("owner_key", ""))):
            return _html(_consent(server, rid, pending, server.client(pending.client_id), False,
                                         "/oauth/device/verify", "That owner key is not right."), 401)
        scopes = list(READ_ONLY) if decision == "read" else [str(s) for s in form.getlist("scope")]
        server.device_decide(pending, decision in ("allow", "read"), scopes, str(form.get("lifetime", "30d")))
        done = "You can go back to the app." if decision != "deny" else "The app was not connected."
        resp = _html(_page("Done", f"<h1>{'Connected' if decision != 'deny' else 'Declined'}</h1><p>{done}</p>"))
        return with_cookie(resp, request) if decision != "deny" else resp

    async def apps(request: Request):
        if not owner(request):
            return JSONResponse({"error": "owner key required"}, status_code=401)
        return JSONResponse({"apps": server.apps()}, headers=no_store)

    async def app_revoke(request: Request):
        if not owner(request):
            return JSONResponse({"error": "owner key required"}, status_code=401)
        return JSONResponse({"revoked": server.revoke_grant(request.path_params["gid"])})

    suffix = mcp_path.strip("/")
    prm_paths = ["/.well-known/oauth-protected-resource"] + ([f"/.well-known/oauth-protected-resource/{suffix}"] if suffix else [])
    return [
        *[Route(p, prm, methods=["GET"]) for p in prm_paths],
        Route("/.well-known/oauth-authorization-server", asm, methods=["GET"]),
        Route("/oauth/register", register, methods=["POST"]),
        Route("/oauth/authorize", authorize_get, methods=["GET"]),
        Route("/oauth/authorize", authorize_post, methods=["POST"]),
        Route("/oauth/token", token, methods=["POST"]),
        Route("/oauth/revoke", revoke, methods=["POST"]),
        Route("/oauth/device", device, methods=["POST"]),
        Route("/oauth/device/verify", device_verify_get, methods=["GET"]),
        Route("/oauth/device/verify", device_verify_post, methods=["POST"]),
        Route("/oauth/apps", apps, methods=["GET"]),
        Route("/oauth/apps/{gid}/revoke", app_revoke, methods=["POST"]),
    ]


__all__ = ["build_routes", "COOKIE", "LIFETIMES"]
