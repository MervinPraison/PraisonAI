"""
MCP Tools Loader for PraisonAI Agents.

Provides a thin helper function to load MCP tools for agents
following the agent-centric design principles in AGENTS.md.
"""

import os
import re
from typing import Any, Dict, List, Optional

from .._logging import get_logger
from ..memory.mcp_config import MCPConfig, MCPConfigManager
from .mcp import MCP
from .trust import is_mcp_url

logger = get_logger(__name__)

# Shapes written by Claude Code, Cursor, VS Code, Gemini CLI, Codex and PraisonAI YAML.
_CONTAINER_KEYS = ("mcpServers", "servers", "mcp_servers")
_FIELD_ALIASES = {
    "httpUrl": "url", "server_url": "url", "http_headers": "headers", "auth": "oauth",
    "includeTools": "allowed_tools", "enabled_tools": "allowed_tools",
    "include_tools": "allowed_tools", "tool_filter": "allowed_tools",
    "excludeTools": "disabled_tools", "exclude_tools": "disabled_tools",
    "transport": "type", "tool_timeout_sec": "timeout",
}
# Harmless editor fields with no meaning here: dropped without a warning.
_QUIET_FIELDS = {"name", "description", "trust", "alwaysAllow", "autoApprove", "startup_timeout_sec"}
_FIELDS = {"type", "command", "args", "env", "cwd", "url", "headers", "oauth",
           "allowed_tools", "disabled_tools", "timeout", "enabled"}
_TYPE_ALIASES = {"local": "stdio", "remote": "http", "streamable-http": "http",
                 "streamable_http": "http", "streamableHttp": "http", "websocket": "ws"}
_ENV_VAR = re.compile(r"\$\{(?:env:)?([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _normalize_entry(name: str, raw: Any) -> Dict[str, Any]:
    """Return one server entry in the shared shape (see :func:`parse_mcp_servers`)."""
    if isinstance(raw, str):
        raw = {"command": raw}
    if not isinstance(raw, dict):
        raise ValueError(f"MCP server '{name}' must be a mapping or a command string")
    entry = {_FIELD_ALIASES.get(k, k): v for k, v in raw.items()}
    bearer_var = entry.pop("bearer_token_env_var", None)
    if entry.pop("disabled", False):  # Claude Code, Cline, VS Code
        entry["enabled"] = False
    unknown = [k for k in entry if k not in _FIELDS | _QUIET_FIELDS]
    entry = {k: v for k, v in entry.items() if k in _FIELDS}
    if unknown:
        logger.warning("MCP server '%s': ignoring unknown field(s): %s", name, ", ".join(unknown))
    if bearer_var:
        entry["headers"] = {**(entry.get("headers") or {}), "Authorization": f"Bearer ${{{bearer_var}}}"}
    oauth = entry.get("oauth")
    if isinstance(oauth, dict):
        client_id = oauth.get("client_id") or oauth.get("clientId") or oauth.get("CLIENT_ID")
        entry["oauth"] = {k: v for k, v in {"client_id": client_id, "scopes": oauth.get("scopes")}.items() if v}
    url = entry.get("url")
    if not url and not entry.get("command"):
        raise ValueError(f"MCP server '{name}' needs a 'command' or a 'url'")
    kind = entry.get("type") or ("stdio" if not url else "ws" if str(url).startswith("ws") else
                                 "sse" if str(url).endswith("/sse") else "http")
    entry["type"] = _TYPE_ALIASES.get(kind, kind)
    return entry


def parse_mcp_servers(data: Any) -> Dict[str, Dict[str, Any]]:
    """Return ``{name: entry}`` from ``mcpServers``/``servers``/``mcp_servers``/``mcp.servers``
    or a bare mapping, with editor field names mapped to one shape. ``${VAR}`` is kept as is.
    It does not apply ``mcp/trust.py``: callers reading a project file must still call
    ``drop_untrusted_mcp_servers`` first.
    """
    if not data:
        return {}
    if not isinstance(data, dict):
        raise ValueError("MCP server config must be a mapping")
    servers = next((data[k] for k in _CONTAINER_KEYS if isinstance(data.get(k), dict)), None)
    if servers is None:
        nested = data.get("mcp")
        servers = nested["servers"] if isinstance(nested, dict) and isinstance(nested.get("servers"), dict) else data
    return {name: _normalize_entry(name, entry) for name, entry in servers.items()}


def _expand(value: Any, name: str) -> Any:
    """Expand ``${VAR}``, ``${env:VAR}`` and ``${VAR:-default}`` from the environment."""
    if isinstance(value, dict):
        return {k: _expand(v, name) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v, name) for v in value]
    if not isinstance(value, str):
        return value

    def _sub(match):
        var, default = match.groups()
        if var not in os.environ and default is None:
            raise ValueError(f"MCP server '{name}': environment variable {var} is not set")
        return os.environ.get(var, default)

    return _ENV_VAR.sub(_sub, value)


def build_mcp(entry: Any, name: str = "server", cls: type = MCP) -> MCP:
    """Build an ``MCP`` client from one config entry. Used by :meth:`MCP.from_config`."""
    entry = _normalize_entry(name, entry)
    if entry.get("enabled") is False:
        raise ValueError(f"MCP server '{name}' is disabled")
    kwargs: Dict[str, Any] = {}
    args = _expand(entry.get("args"), name)
    if entry.get("url"):
        target = _expand(entry["url"], name)
        if not is_mcp_url(target):
            raise ValueError(f"MCP server '{name}': url must be an http(s) or ws(s) URL")
        headers = entry.get("headers")
        if headers and target.rstrip("/").endswith("/sse"):
            # The legacy SSE client cannot send headers; never connect without auth.
            if any(k.lower() == "authorization" for k in headers):
                raise ValueError(f"MCP server '{name}': legacy SSE URLs cannot send an Authorization header")
            logger.warning("MCP server '%s': headers are not supported for legacy SSE URLs and are ignored", name)
        elif headers:
            kwargs["headers"] = _expand(headers, name)
        if entry.get("oauth"):
            logger.warning("MCP server '%s': oauth sign-in is not applied by this client yet", name)
    else:
        target = _expand(entry["command"], name)
        if isinstance(target, list):  # ["npx", "-y", "pkg"]
            target, args = str(target[0]), [str(a) for a in target[1:]] + list(args or [])
        for key in ("env", "cwd"):
            if entry.get(key):
                kwargs[key] = _expand(entry[key], name)
    timeout = entry.get("timeout")
    if timeout is not None:
        kwargs["timeout"] = timeout / 1000 if timeout >= 1000 else timeout  # 1000+ is ms (code schema)
    for key in ("allowed_tools", "disabled_tools"):
        if entry.get(key):
            kwargs[key] = entry[key]
    return cls(target, args=args, **kwargs)


def _sanitize_server_name(name: str) -> str:
    """Sanitize a server name for use as a stable, deterministic tool prefix.

    Delegates to :meth:`MCP._sanitize_prefix` so collision detection here can
    never drift from the prefix actually applied by ``MCP.with_tool_prefix``.
    """
    return MCP._sanitize_prefix(name or "")


def load_mcp_tools(
    names: Optional[List[str]] = None,
    *,
    configs: Optional[List[MCPConfig]] = None,
    prefix_tools: bool = True,
) -> List[MCP]:
    """
    Load MCP tools for use with agents.
    
    This is a thin helper that bridges the gap between configuration
    and agent tool setup, following the "few lines to run an agent"
    principle from AGENTS.md.
    
    Args:
        names: Specific config names to load (None = all enabled)
        configs: Optional injected configs from wrapper TOML loader
        prefix_tools: Whether to prefix tool names when multiple servers
            are loaded to avoid collisions (default: True). When more than
            one server is loaded, each server's tools are namespaced as
            ``<server_name>_<tool_name>`` (e.g. ``filesystem_read_file``).
            Single-server loads keep bare tool names for backward
            compatibility.

    Raises:
        ValueError: If two loaded configs share the same (sanitized) server
            name, which would produce ambiguous namespaced tool names.
    
    Returns:
        List of MCP client instances ready for agent use
    
    Examples:
        # Load all enabled MCP servers from JSON config
        >>> from praisonaiagents import Agent
        >>> from praisonaiagents.mcp import load_mcp_tools
        >>> agent = Agent(name="assistant", tools=load_mcp_tools())
        
        # Load specific servers only
        >>> tools = load_mcp_tools(["filesystem", "github"])
        >>> agent = Agent(name="coder", tools=tools)
        
        # Inject configs from wrapper TOML
        >>> from praisonai.cli.configuration import get_config_loader
        >>> loader = get_config_loader()
        >>> config = loader.load()
        >>> toml_configs = [MCPConfig(...) for server in config.mcp.servers]
        >>> tools = load_mcp_tools(configs=toml_configs)
    """
    mcp_clients: List[MCP] = []
    
    if configs is not None:
        # Use injected configs from wrapper (TOML loading)
        target_configs = configs
        if names:
            # Filter by names if specified
            target_configs = [c for c in configs if c.name in names]
    else:
        # Load from MCPConfigManager (JSON files)
        manager = MCPConfigManager()
        if names:
            target_configs = [manager.get_config(name) for name in names]
            target_configs = [c for c in target_configs if c and c.enabled]
        else:
            target_configs = manager.get_enabled_configs()
    
    enabled_configs = [c for c in target_configs if c and c.enabled]

    # Detect residual collisions: two servers whose sanitized names are
    # identical would produce ambiguous namespaced tool names. Fail loudly
    # instead of silently shadowing (the very bug this loader guards against).
    if prefix_tools and len(enabled_configs) > 1:
        seen: dict = {}
        for config in enabled_configs:
            sanitized = _sanitize_server_name(config.name)
            if sanitized in seen:
                raise ValueError(
                    f"MCP server name collision: '{config.name}' and "
                    f"'{seen[sanitized]}' both map to prefix '{sanitized}'. "
                    "Use distinct server names to keep tool namespacing unambiguous."
                )
            seen[sanitized] = config.name

    # First materialize the MCP instances and apply per-server tool filters.
    # We defer the prefixing decision until we know how many instances were
    # actually created: a config may yield None (e.g. missing optional deps),
    # and a lone surviving server must keep bare names for backward compat.
    loaded: list = []
    for config in enabled_configs:
        mcp = config.to_mcp_instance()
        if not mcp:
            continue

        # Apply include/exclude tool filtering if configured (B3).
        # Filters may be declared on the config (forward-compatible via
        # getattr so older MCPConfig objects without these fields work).
        allowed = getattr(config, "allowed_tools", None) or getattr(config, "include_tools", None)
        disabled = getattr(config, "disabled_tools", None) or getattr(config, "exclude_tools", None)
        if allowed or disabled:
            mcp.apply_tool_filters(allowed_tools=allowed, disabled_tools=disabled)

        loaded.append((config, mcp))

    # Apply tool prefix only when more than one server was actually loaded
    # (B4) to avoid collisions while preserving single-server bare names.
    multiple_servers = len(loaded) > 1
    for config, mcp in loaded:
        if prefix_tools and multiple_servers:
            mcp.with_tool_prefix(config.name)
        mcp_clients.append(mcp)

    return mcp_clients