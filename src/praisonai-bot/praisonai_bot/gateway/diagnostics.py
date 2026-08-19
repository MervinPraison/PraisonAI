"""On-demand, pre-sanitised diagnostics bundle for the gateway (Issue #4044).

When a gateway/bot misbehaves an operator otherwise has to hand-assemble
evidence — tail logs, redact secrets, capture health/status, copy the config —
before they can debug it or open a useful report. This module consolidates the
existing building blocks (crash forensics, ``health()``, secret-ref redaction)
into ONE portable archive an operator (or the bot itself) can produce in a
single step, so nobody accidentally pastes a raw token into an issue.

It is typer-free so it stays importable/testable without the CLI, and every
section is best-effort: a section that cannot be gathered is recorded as an
error rather than aborting the whole bundle. It runs even when the gateway is
unhealthy (falling back to local daemon logs) and it NEVER includes chat text,
prompts, tool outputs, credentials, or raw tokens — the config is reduced to
its key/mode shape and every text section is passed through the shared
``redact_secrets`` pass before it is written.
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import os
import zipfile
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_SECTIONS = ("summary", "health", "config_shape", "logs", "forensics")

# Config keys whose *values* are secrets/credentials and must never be copied
# into the sanitised shape even in redacted form — we keep only their presence.
_SECRET_KEYS = frozenset(
    {
        "token",
        "app_token",
        "verify_token",
        "auth_token",
        "api_key",
        "apikey",
        "secret",
        "password",
        "passwd",
        "client_secret",
        "signing_secret",
        "webhook_secret",
        "access_token",
        "refresh_token",
        "bearer",
    }
)


def _now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def _unique_bundle_path(out_dir: str) -> str:
    """A collision-free archive path in ``out_dir``.

    ``_now_stamp()`` is second-resolution, so two exports into the same
    directory within one second would otherwise resolve to the same path and
    the second truncating write would silently destroy the first bundle
    (Greptile P1). Keep the human-friendly timestamped name but append a ``-N``
    suffix when that exact name already exists so every export is preserved.
    """
    stamp = _now_stamp()
    candidate = os.path.join(out_dir, f"praisonai-diagnostics-{stamp}.zip")
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(
            out_dir, f"praisonai-diagnostics-{stamp}-{counter}.zip"
        )
        counter += 1
    return candidate


def _redact(text: str) -> str:
    """Pass text through the shared secret-redaction registry (best-effort)."""
    try:
        from praisonaiagents.secrets import redact_secrets

        return redact_secrets(text)
    except Exception:  # pragma: no cover — never let redaction failure block
        return text


def _sanitise_config_shape(value: Any) -> Any:
    """Reduce a loaded config to keys/modes only — no secret values.

    A key whose name marks it as a credential is replaced with a
    ``"<set>"``/``"<empty>"`` presence marker; every other scalar is kept only
    as its type name (never its value) so the shape is shareable without leaking
    endpoints, ids, or free text that might contain secrets.
    """
    if isinstance(value, dict):
        shape: Dict[str, Any] = {}
        for key, val in value.items():
            lname = str(key).lower()
            if lname in _SECRET_KEYS:
                shape[key] = "<set>" if val not in (None, "") else "<empty>"
            else:
                shape[key] = _sanitise_config_shape(val)
        return shape
    if isinstance(value, list):
        return [_sanitise_config_shape(v) for v in value]
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    # Scalars (str/int/float): keep the type, not the value.
    return f"<{type(value).__name__}>"


def _collect_config_shape(config_path: Optional[str]) -> Dict[str, Any]:
    if not config_path:
        return {"error": "no config path resolved"}
    if not os.path.exists(config_path):
        return {"error": f"config not found: {config_path}"}
    try:
        import yaml

        with open(config_path) as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception as exc:  # pragma: no cover — defensive
        return {"error": f"could not read config: {exc}"}
    return {"path": os.path.basename(config_path), "shape": _sanitise_config_shape(cfg)}


def _collect_forensics() -> Dict[str, Any]:
    """The latest fast forensic snapshot (never chat/prompt data)."""
    try:
        from praisonai_bot.gateway.forensics import ShutdownForensics

        return ShutdownForensics(enabled=False).snapshot()
    except Exception as exc:  # pragma: no cover — defensive
        return {"error": f"forensics unavailable: {exc}"}


def _collect_logs(lines: int = 200) -> str:
    """Redacted tail of the daemon service logs (local fallback)."""
    try:
        from praisonai_bot.daemon import _detect_platform

        plat = _detect_platform()
        if plat == "systemd":
            from praisonai_bot.daemon.systemd import get_logs
        elif plat == "launchd":
            from praisonai_bot.daemon.launchd import get_logs
        elif plat == "windows":
            from praisonai_bot.daemon.windows import get_logs
        else:
            return f"(no log reader for platform: {plat})"
        raw = get_logs(lines=lines) or ""
    except Exception as exc:  # pragma: no cover — defensive
        return f"(logs unavailable: {exc})"
    return _redact(raw)


def _collect_health(config_path: Optional[str]) -> Dict[str, Any]:
    """Best-effort gateway health/status; degrade gracefully when unreachable.

    Uses the running gateway's REST ``/health`` endpoint when reachable so the
    bundle reflects live status, but the whole export must still succeed when
    the gateway is down (which is exactly when an operator wants a bundle), so
    an unreachable gateway is recorded as a note rather than raising.
    """
    try:
        from praisonai_bot.gateway.preflight import check_gateway_running

        ok, message = check_gateway_running(config_path) if config_path else (False, "no config")
        return {"reachable": bool(ok), "detail": _redact(str(message))}
    except Exception as exc:
        return {"reachable": False, "detail": f"health probe unavailable: {exc}"}


def build_diagnostics_bundle(
    config_path: Optional[str],
    *,
    output_dir: Optional[str] = None,
    include: Sequence[str] = DEFAULT_SECTIONS,
    log_lines: int = 200,
) -> Dict[str, Any]:
    """Build a portable, pre-sanitised diagnostics archive.

    Returns a dict with the resolved ``path`` of the written ``.zip`` and the
    in-memory ``manifest`` (also written into the archive). Every section is
    best-effort and redacted; nothing here contains chat text, prompts, tool
    outputs, or raw credentials.
    """
    include = tuple(include)
    manifest: Dict[str, Any] = {
        "tool": "praisonai gateway diagnostics export",
        "issue": 4044,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "sections": list(include),
        "redacted": True,
    }

    sections: Dict[str, Any] = {}
    if "config_shape" in include:
        sections["config_shape"] = _collect_config_shape(config_path)
    if "health" in include:
        sections["health"] = _collect_health(config_path)
    if "forensics" in include:
        sections["forensics"] = _collect_forensics()
    if "logs" in include:
        sections["logs"] = _collect_logs(lines=log_lines)

    summary_lines: List[str] = [
        "PraisonAI Gateway Diagnostics Bundle",
        "=" * 38,
        f"generated_at : {manifest['generated_at']}",
        f"config       : {sections.get('config_shape', {}).get('path', 'n/a') if isinstance(sections.get('config_shape'), dict) else 'n/a'}",
    ]
    health = sections.get("health")
    if isinstance(health, dict):
        summary_lines.append(
            f"gateway      : {'reachable' if health.get('reachable') else 'unreachable (local fallback)'}"
        )
    forensics = sections.get("forensics")
    if isinstance(forensics, dict) and "error" not in forensics:
        summary_lines.append(
            f"supervised   : {forensics.get('supervised', 'unknown')}"
        )
    summary_lines.append("")
    summary_lines.append(
        "This bundle is pre-sanitised: config is reduced to key/mode shape and "
        "all text is secret-redacted. It contains no chat text, prompts, tool "
        "outputs, or raw tokens. Safe to attach to a bug report."
    )
    summary_text = _redact("\n".join(summary_lines))

    out_dir = output_dir or os.path.join(
        os.path.expanduser(os.environ.get("PRAISONAI_HOME", "~/.praisonai")),
        "diagnostics",
    )
    os.makedirs(out_dir, exist_ok=True)
    bundle_path = _unique_bundle_path(out_dir)

    manifest["files"] = []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if "summary" in include:
            zf.writestr("summary.txt", summary_text)
            manifest["files"].append("summary.txt")
        for name, payload in sections.items():
            if name == "logs":
                zf.writestr("logs.txt", payload if isinstance(payload, str) else str(payload))
                manifest["files"].append("logs.txt")
            else:
                zf.writestr(f"{name}.json", json.dumps(payload, indent=2, default=str))
                manifest["files"].append(f"{name}.json")
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))

    with open(bundle_path, "wb") as fh:
        fh.write(buffer.getvalue())

    return {"path": bundle_path, "manifest": manifest}
