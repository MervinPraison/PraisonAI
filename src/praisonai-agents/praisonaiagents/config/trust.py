"""Which config keys a project file may set.

A project file (``.praisonai/config.yaml``, ``praisonai.yaml``, command or agent
front matter in a cloned repository) is untrusted (SECURITY.md). It may tune
behaviour but not grant a capability: run code or shell, approve tools, or
choose where the user's secrets go. Those keys count only from the user config
(``~/.praisonai``, ``PRAISONAI_HOME``), the environment or code. Every reader of
a project file calls :func:`drop_project_trust_keys`.
"""

from pathlib import Path
from typing import Any, Dict, List

from .._logging import get_logger

logger = get_logger(__name__)

_KEY, _URL = "the provider API key variable", "OPENAI_BASE_URL"
#: Keys that grant a capability, and how the operator grants it instead.
TRUST_KEYS: Dict[str, str] = {
    "defaults.base_url": _URL, "defaults.api_key": _KEY, "agent.base_url": _URL,
    "agent.api_key": _KEY, "llm.base_url": _URL, "model.base_url": _URL, "model.api_key": _KEY,
    "plugins.allow_project_plugins": "PRAISONAI_ALLOW_PROJECT_PLUGINS=true",
    "commands.allow_shell": "PRAISONAI_ALLOW_SHELL=true",
    "allow_shell": "PRAISONAI_ALLOW_SHELL=true (or keep the command in ~/.praisonai/commands)",
}
#: Permission blocks: a project file may restrict (deny/ask), never allow.
GRANT_KEYS = ("permissions", "permission")
_warned: set = set()


def is_user_source(source: Any) -> bool:
    """True when ``source`` is a file in a user config dir (or one level below it)."""
    from ..paths import get_data_dir
    roots = [p.resolve() for p in (get_data_dir(), Path.home() / ".praisonai", Path.home() / ".praison")]
    try:
        path = Path(source).expanduser().resolve()
    except (OSError, RuntimeError, TypeError):
        return False
    return path.parent in roots or path.parent.parent in roots


def key_allowed(key: str, source: Any) -> bool:
    """Whether dotted config ``key`` may be honoured from ``source``."""
    granting = key in TRUST_KEYS or key.split(".")[0] in GRANT_KEYS or key.startswith("mcp.servers.")
    return not granting or is_user_source(source)


def _warn(source: Any, key: str, how: str) -> None:
    if (str(source), key) not in _warned:
        _warned.add((str(source), key))
        logger.warning("Ignoring %s from project file %s: a project file cannot grant this. "
                       "To trust it, %s.", key, source, how)


def _has_env(value: Any) -> bool:
    """True when ``value`` holds a ``${VAR}`` or ``{env:VAR}`` interpolation."""
    if isinstance(value, (dict, list)):
        return any(_has_env(v) for v in (value.values() if isinstance(value, dict) else value))
    return isinstance(value, str) and ("${" in value or "{env:" in value)


def _strip_allow(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_allow(v) for k, v in value.items() if v != "allow"}
    if isinstance(value, list):
        return [_strip_allow(v) for v in value if not (isinstance(v, dict) and v.get("action") == "allow")]
    return value


def _trusted_urls() -> List[str]:
    """Entries under ``mcp.trusted_servers`` in the user config (the store ``mcp.trust`` uses)."""
    from .loader import _parse_config_file
    from ..paths import get_data_dir
    urls: List[str] = []
    for path in (get_data_dir() / n for n in ("config.yaml", "config.yml", "config.toml")):
        mcp = _parse_config_file(path).get("mcp") if path.is_file() else None
        urls += [str(u) for u in (mcp.get("trusted_servers") or [])] if isinstance(mcp, dict) else []
    return urls


def drop_project_trust_keys(data: Any, source: Any) -> Any:
    """Return ``data`` read from ``source`` without the keys a project file may not set.

    User config data is returned unchanged. Call it before ``${VAR}`` interpolation.
    """
    if not isinstance(data, dict) or is_user_source(source):
        return data
    data = dict(data)
    for key, how in TRUST_KEYS.items():
        head, _, leaf = key.rpartition(".")
        section = data.get(head) if head else data
        if isinstance(section, dict) and leaf in section:
            section = {k: v for k, v in section.items() if k != leaf}
            data = {**data, head: section} if head else section
            _warn(source, key, f"set {key} in ~/.praisonai/config.yaml or use {how}")
    for key in GRANT_KEYS:
        if key in data and _strip_allow(data[key]) != data[key]:
            data[key] = _strip_allow(data[key])
            _warn(source, f"{key} (allow rules)", "put allow rules in ~/.praisonai/config.yaml")
    servers = data["mcp"].get("servers") if isinstance(data.get("mcp"), dict) else None
    if isinstance(servers, dict):
        servers = dict(servers)
        for name, entry in list(servers.items()):  # a remote server must not get the user's env
            if isinstance(entry, dict) and entry.get("url") and _has_env(entry) \
                    and entry["url"] not in _trusted_urls():
                del servers[name]
                _warn(source, f"mcp.servers.{name}",
                      "list its url under mcp.trusted_servers in ~/.praisonai/config.yaml")
        data["mcp"] = {**data["mcp"], "servers": servers}
    return data
