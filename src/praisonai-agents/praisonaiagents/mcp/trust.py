"""Which MCP servers a project file may start.

A project file (e.g. a cloned repository's ``.praisonai/config.yaml``) is
untrusted (SECURITY.md). A local server it declares starts only when the user
config lists its exact command line under ``mcp.trusted_servers``; its ``url``
must be a real URL, because ``MCP()`` runs any other string as a command.
"""

import os
import shlex
import warnings
from typing import Any, Dict, List
from urllib.parse import urlparse

from .._logging import get_logger

logger = get_logger(__name__)

#: Server keys that decide what runs. A project entry setting any of them is a launch.
LAUNCH_KEYS = ("command", "args", "env", "cwd")


def is_mcp_url(value: Any) -> bool:
    """Return True when ``value`` is an http(s) or ws(s) URL with a host."""
    if not isinstance(value, str) or value != value.strip():
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https", "ws", "wss") and bool(parsed.netloc)


def mcp_server_argv(command: Any, args: Any = None) -> List[str]:
    """Return the argv for ``command`` (a string or list) followed by ``args``."""
    parts = shlex.split(command) if isinstance(command, str) else [str(p) for p in command or []]
    return parts + [str(a) for a in args or []]


def trusted_mcp_servers() -> List[List[str]]:
    """Return the command lines listed under ``mcp.trusted_servers`` in the user config."""
    from ..config.loader import _parse_config_file
    from ..paths import get_data_dir

    trusted: List[List[str]] = []
    for name in ("config.yaml", "config.yml", "config.toml"):
        path = get_data_dir() / name
        mcp = _parse_config_file(path).get("mcp") if path.is_file() else None
        for entry in (mcp.get("trusted_servers") if isinstance(mcp, dict) else None) or []:
            try:
                trusted.append(mcp_server_argv(entry))
            except ValueError:
                logger.warning("Ignoring unparsable mcp.trusted_servers entry %r", entry)
    return trusted


def drop_untrusted_mcp_servers(servers: Any, source: str) -> Any:
    """Return ``servers`` (name -> entry) from an untrusted file without untrusted launches."""
    if not isinstance(servers, dict):
        return servers
    kept: Dict[str, Any] = {}
    trusted = None
    for name, entry in servers.items():
        if isinstance(entry, dict) and "url" in entry and not is_mcp_url(entry["url"]):
            logger.warning("Not starting MCP server %r from %s: url is not a URL", name, source)
            continue
        if not isinstance(entry, dict) or not any(k in entry for k in LAUNCH_KEYS):
            kept[name] = entry  # a remote (url) server or a plain toggle starts nothing
            continue
        if trusted is None:  # PRAISONAI_MCP_TRUST is the older opt-in, set by the operator
            trusted = trusted_mcp_servers()
            if os.environ.get("PRAISONAI_MCP_TRUST", "").strip().lower() in ("1", "true", "yes", "on"):
                warnings.warn("PRAISONAI_MCP_TRUST is deprecated: list the exact command lines "
                              "under mcp.trusted_servers in ~/.praisonai/config.yaml instead.",
                              DeprecationWarning, stacklevel=2)
                trusted = True
        try:
            argv = mcp_server_argv(entry.get("command"), entry.get("args"))
        except ValueError:
            argv = None
        if trusted is True or (argv and argv in trusted
                               and not entry.get("env") and not entry.get("cwd")):
            kept[name] = entry
            continue
        logger.warning("Not starting MCP server %r from %s: a project file cannot choose a program "
                       "to run. Declare it in your user config, or list its exact command line "
                       "under mcp.trusted_servers there.", name, source)
    return kept


def drop_untrusted_mcp_config(data: Any, source: str) -> Any:
    """Return config-file ``data`` (from an untrusted file) with its ``mcp.servers`` filtered."""
    mcp = data.get("mcp") if isinstance(data, dict) else None
    if not isinstance(mcp, dict) or "servers" not in mcp:
        return data
    return {**data, "mcp": {**mcp, "servers": drop_untrusted_mcp_servers(mcp["servers"], source)}}
