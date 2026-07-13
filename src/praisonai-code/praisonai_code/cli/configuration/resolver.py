"""
Unified configuration resolver for PraisonAI CLI.

Implements a single, project-aware configuration hierarchy with proper precedence:
1. Built-in defaults
2. Managed non-policy defaults (optional; below local so teams suggest, not clobber)
3. Global user config (~/.praisonai/config.yaml)
4. Project config (discovered by walking up from cwd)
5. Environment variables
6. Explicit CLI flags
7. Managed policy (optional; above local so an org can enforce, not just suggest)

Supports deep-merge semantics and backward compatibility with legacy paths.

The managed layer is fully opt-in: with no managed source configured
(``PRAISONAI_MANAGED_CONFIG_URL`` / ``PRAISONAI_MANAGED_CONFIG_DIR`` or a global
``managed`` config section), resolution behaves exactly as before.
"""

import os
import json
import difflib
import hashlib
import ipaddress
import socket
import warnings
from urllib.parse import urlparse
import toml
import yaml
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..utils.project import get_git_root
from ..utils.env_utils import interpolate


# Policy keys sourced from a managed layer are enforced ABOVE local config so an
# organisation can guarantee (not merely suggest) them. Everything else from a
# managed source is treated as a default and layered BELOW local config.
MANAGED_POLICY_KEYS = ("permissions", "model_allowlist")

# Where the managed-config on-disk cache lives (fail-soft last-good copy).
_MANAGED_CACHE_DIRNAME = "state"

# Only these URL schemes may be fetched for a managed config. ``https`` is the
# safe default; plain ``http`` is permitted solely so an operator can point at an
# explicit loopback dev server (validated separately below).
_MANAGED_ALLOWED_SCHEMES = ("https", "http")


def _is_safe_managed_url(url: str) -> bool:
    """Whether a managed-config URL is safe to fetch (SSRF guard).

    Rejects non-http(s) schemes (``file:``, ``gopher:``, etc.) and any host that
    resolves to a private, loopback, link-local, or otherwise non-global
    address. This blocks the managed layer from being pointed at internal
    services or cloud metadata endpoints (e.g. ``169.254.169.254``) during a
    normal CLI run. Plain ``http`` is allowed only for explicit loopback.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    scheme = (parsed.scheme or "").lower()
    if scheme not in _MANAGED_ALLOWED_SCHEMES:
        return False

    host = parsed.hostname
    if not host:
        return False

    # Resolve the host to every candidate address and require all of them to be
    # global (public). If any resolves to a private/internal range, reject —
    # this defends against DNS entries that point inward.
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if scheme == "https" else 80))
    except (socket.gaierror, UnicodeError, ValueError):
        return False

    saw_address = False
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False
        saw_address = True
        is_loopback = ip.is_loopback
        if not (ip.is_global and not ip.is_private):
            # Plain http is tolerated only for an explicit loopback dev server.
            if scheme == "http" and is_loopback:
                continue
            return False
        if scheme == "http":
            # http to a public host is not allowed (loopback-only above).
            return False

    return saw_address


# Known top-level sections the resolver consumes.
KNOWN_TOP_LEVEL_KEYS = {
    "agent", "rag", "output", "telemetry", "sources",
    # Reserved editor-tooling pointer written by `praisonai init`.
    "$schema",
    # Tolerated extension sections (validated leniently, not dropped).
    "traces", "mcp", "permissions", "model", "llm", "session", "rules",
    # Custom command settings (e.g. opt-in live shell substitution gate).
    "commands",
    # Auto workspace checkpointing for the coding loop ({auto, storage_dir}).
    "checkpoints",
    # Plugin enablement + per-plugin options (unified project config surface).
    "plugins",
    # Optional managed/remote config source ({url, dir, timeout, enforce}).
    "managed",
    # Managed model allow-list (enforceable policy key).
    "model_allowlist",
}

# Reserved keys in the plugins section; any other key is a per-plugin option map.
KNOWN_PLUGINS_KEYS = {"enabled", "auto_discover", "directories"}

# Known keys for the nested output section.
KNOWN_OUTPUT_KEYS = {"format", "color", "verbose", "quiet"}


def _strict_mode_enabled() -> bool:
    """Whether strict config validation is enabled via environment."""
    return os.environ.get("PRAISONAI_STRICT_CONFIG", "").lower() in ("1", "true", "yes")


def _suggest(key: str, valid_keys: set) -> Optional[str]:
    """Return the closest valid key for a typo, if any."""
    matches = difflib.get_close_matches(key, valid_keys, n=1, cutoff=0.6)
    return matches[0] if matches else None


def _format_unknown_key_message(
    key: str, valid_keys: set, section: str, source: Optional[str]
) -> str:
    """Build an actionable message for an unknown config key."""
    location = f" in {source}" if source else ""
    suggestion = _suggest(key, valid_keys)
    hint = f" Did you mean '{suggestion}'?" if suggestion else ""
    return f"Unknown config key '{key}'{location} (section: {section}).{hint}"


def validate_config_data(
    data: Dict[str, Any],
    source: Optional[str] = None,
    strict: Optional[bool] = None,
) -> List[str]:
    """
    Validate a raw config dict against the known schema.

    Emits actionable messages for unknown/typo keys. In warn mode (default) the
    messages are returned and surfaced as warnings; in strict mode the first
    problem raises ``ValueError``.

    Args:
        data: Raw config dict loaded from a file.
        source: Path of the originating file (for messages).
        strict: Force strict mode. Defaults to the env-driven setting.

    Returns:
        List of warning messages (empty when the config is clean).
    """
    if strict is None:
        strict = _strict_mode_enabled()

    messages: List[str] = []

    def _record(message: str) -> None:
        if strict:
            raise ValueError(message)
        messages.append(message)

    if not isinstance(data, dict):
        _record(f"Configuration must be a mapping{f' in {source}' if source else ''}.")
        return messages

    agent_fields = {f.name for f in AgentDefaults.__dataclass_fields__.values()}
    rag_fields = {f.name for f in RAGConfig.__dataclass_fields__.values()}

    for key, value in data.items():
        if key == "_source":
            continue
        if key not in KNOWN_TOP_LEVEL_KEYS:
            _record(_format_unknown_key_message(key, KNOWN_TOP_LEVEL_KEYS, "top-level", source))
            continue

        if key == "plugins":
            if not isinstance(value, dict):
                location = f" in {source}" if source else ""
                _record(f"Configuration section 'plugins'{location} must be a mapping.")
                continue
            # Reserved keys carry scalars/lists; per-plugin option maps are dicts
            # and use free-form names, so only typo-check the non-dict scalars.
            for sub, sub_value in value.items():
                if sub in KNOWN_PLUGINS_KEYS or isinstance(sub_value, dict):
                    continue
                _record(_format_unknown_key_message(sub, KNOWN_PLUGINS_KEYS, "plugins", source))
            continue

        section_fields = {
            "agent": agent_fields,
            "rag": rag_fields,
            "output": KNOWN_OUTPUT_KEYS,
        }.get(key)
        if section_fields is not None:
            if not isinstance(value, dict):
                location = f" in {source}" if source else ""
                _record(f"Configuration section '{key}'{location} must be a mapping.")
                continue
            for sub in value:
                if sub not in section_fields:
                    _record(_format_unknown_key_message(sub, section_fields, key, source))

    return messages


@dataclass
class AgentDefaults:
    """Agent configuration defaults."""
    model: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None  # Note: Only stored for env var reference, not in file
    tools: List[str] = field(default_factory=list)
    toolset: Optional[str] = None
    default_agent: Optional[str] = None
    memory: Optional[Union[bool, Dict[str, Any]]] = None
    stream: bool = True
    temperature: float = 0.7
    max_tokens: int = 16000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values and api_key."""
        result = {}
        for key, value in asdict(self).items():
            if key == 'api_key':
                continue  # Never serialize API key
            if value is not None:
                if isinstance(value, list) and not value:
                    continue  # Skip empty lists
                result[key] = value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentDefaults":
        """Create from dictionary."""
        # Filter to only known fields
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class RAGConfig:
    """RAG/Knowledge configuration."""
    collection: str = "default"
    top_k: int = 5
    hybrid: bool = False
    rerank: bool = False
    min_score: float = 0.0
    include_citations: bool = True
    max_context_tokens: int = 4000
    vector_store: str = "chroma"
    vector_store_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        # Remove None values
        return {k: v for k, v in result.items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RAGConfig":
        """Create from dictionary."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class ResolvedConfig:
    """
    Complete resolved configuration with provenance tracking.
    
    Combines all configuration sources into a single, validated structure.
    """
    # Core agent defaults
    agent: AgentDefaults = field(default_factory=AgentDefaults)
    
    # RAG configuration
    rag: RAGConfig = field(default_factory=RAGConfig)
    
    # Output settings (from existing schema)
    output_format: str = "text"
    color: bool = True
    verbose: bool = False
    quiet: bool = False
    
    # Telemetry
    telemetry: bool = True
    
    # MCP servers declared in project config (single source of truth)
    mcp: Dict[str, Any] = field(default_factory=dict)
    
    # Permission policy declared in project config (single source of truth)
    permissions: Dict[str, Any] = field(default_factory=dict)
    
    # Model allow-list (enforceable policy key; may be set by a managed source)
    model_allowlist: List[str] = field(default_factory=list)
    
    # Plugin enablement + per-plugin options declared in project config.
    # Reserved keys: enabled/auto_discover/directories; any other key is a
    # per-plugin option map delivered to that plugin's on_config hook.
    plugins: Dict[str, Any] = field(default_factory=dict)
    
    # Provenance tracking
    sources: List[str] = field(default_factory=list)
    
    # Extra settings for extensibility
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "agent": self.agent.to_dict(),
            "rag": self.rag.to_dict(),
            "output": {
                "format": self.output_format,
                "color": self.color,
                "verbose": self.verbose,
                "quiet": self.quiet,
            },
            "telemetry": self.telemetry,
            **self.extra
        }
        if self.mcp:
            result["mcp"] = self.mcp
        if self.permissions:
            result["permissions"] = self.permissions
        if self.model_allowlist:
            result["model_allowlist"] = self.model_allowlist
        if self.plugins:
            result["plugins"] = self.plugins
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResolvedConfig":
        """Create from dictionary."""
        agent_data = data.get("agent", {})
        rag_data = data.get("rag", {})
        output_data = data.get("output", {})
        
        # Extract known top-level fields
        known_keys = {"agent", "rag", "output", "telemetry", "mcp", "permissions",
                      "model_allowlist", "managed", "plugins", "sources", "$schema", "_source"}
        extra = {k: v for k, v in data.items() if k not in known_keys}
        
        return cls(
            agent=AgentDefaults.from_dict(agent_data),
            rag=RAGConfig.from_dict(rag_data),
            output_format=output_data.get("format", "text"),
            color=output_data.get("color", True),
            verbose=output_data.get("verbose", False),
            quiet=output_data.get("quiet", False),
            telemetry=data.get("telemetry", True),
            mcp=mcp_data if isinstance(mcp_data := data.get("mcp"), dict) else {},
            permissions=perm_data if isinstance(perm_data := data.get("permissions"), dict) else {},
            model_allowlist=allow if isinstance(allow := data.get("model_allowlist"), list) else [],
            plugins=plugins_data if isinstance(plugins_data := data.get("plugins"), dict) else {},
            sources=data.get("sources", []),
            extra=extra,
        )


class ConfigResolver:
    """
    Unified configuration resolver with project-aware hierarchy.
    
    Implements walk-up discovery and deep-merge semantics.
    """
    
    # Config file names to search for (in order of preference)
    PROJECT_CONFIG_NAMES = [
        ".praisonai/config.yaml",
        ".praisonai/config.yml",
        "praison.yaml",
        "praison.yml",
        ".praison/config.toml",  # Legacy, backward compat
    ]
    
    def __init__(self, cwd: Optional[Path] = None, strict: Optional[bool] = None):
        """
        Initialize the resolver.
        
        Args:
            cwd: Current working directory to start discovery from
            strict: Force strict validation (unknown keys raise). Defaults to
                the ``PRAISONAI_STRICT_CONFIG`` environment setting.
        """
        self.cwd = Path(cwd) if cwd else Path.cwd()
        self.strict = strict
        self._cache: Optional[ResolvedConfig] = None

    def _validate(self, data: Dict[str, Any], source: Optional[str] = None) -> None:
        """Validate a loaded config dict; warn (or raise in strict mode)."""
        messages = validate_config_data(data, source=source, strict=self.strict)
        for message in messages:
            warnings.warn(message, UserWarning, stacklevel=2)
    
    def resolve(
        self,
        cli_args: Optional[Dict[str, Any]] = None,
        force_refresh: bool = False
    ) -> ResolvedConfig:
        """
        Resolve configuration from all sources.
        
        Args:
            cli_args: CLI arguments (highest precedence)
            force_refresh: Force re-resolution, ignoring cache
            
        Returns:
            Fully resolved configuration with provenance
        """
        if self._cache and not force_refresh and not cli_args:
            return self._cache
        
        # Load the optional managed source once and split it into a
        # (non-policy defaults, enforced policy) pair. When no managed source is
        # configured both are empty and precedence is unchanged.
        managed = self._load_managed_config()
        managed_source = managed.get("_source") if managed else None
        managed_defaults, managed_policy = self._split_managed_config(managed)

        # Start with defaults
        config = ResolvedConfig()
        config.sources.append("defaults")
        
        # Layer 2: Managed non-policy defaults (below local so teams set
        # defaults without clobbering deliberate local choices).
        if managed_defaults:
            config = self._merge_configs(config, managed_defaults)
            config.sources.append(f"managed:{managed_source}")
        
        # Layer 3: Global user config
        global_config = self._load_global_config()
        if global_config:
            config = self._merge_configs(config, global_config)
            config.sources.append(f"global:{global_config['_source']}")
        
        # Layer 4: Project config (with walk-up discovery)
        project_config = self._load_project_config()
        if project_config:
            config = self._merge_configs(config, project_config)
            config.sources.append(f"project:{project_config['_source']}")
        
        # Layer 5: Environment variables
        env_config = self._load_env_config()
        if env_config:
            config = self._merge_configs(config, env_config)
            config.sources.append("environment")
        
        # Layer 6: CLI arguments (if provided)
        if cli_args:
            cli_config = self._process_cli_args(cli_args)
            config = self._merge_configs(config, cli_config)
            config.sources.append("cli")
        
        # Layer 7: Managed policy (permissions, model allow-list) enforced ABOVE
        # all local layers so an org policy cannot be silently overridden.
        # Enforced keys REPLACE (not merge/concat) any local counterpart wholesale
        # so a local override of an enforced key is ignored — including nested
        # local sub-keys the managed policy does not itself mention.
        if managed_policy:
            config = self._enforce_policy(config, managed_policy)
            config.sources.append(f"managed-policy:{managed_source}")
        
        # Cache if no CLI args (CLI args are transient)
        if not cli_args:
            self._cache = config
        
        return config
    
    def _load_global_config(self) -> Optional[Dict[str, Any]]:
        """Load global user configuration."""
        configs = []
        
        # Check ~/.praisonai/config.yaml (preferred)
        praisonai_home = Path.home() / ".praisonai"
        for name in ["config.yaml", "config.yml"]:
            config_path = praisonai_home / name
            if config_path.exists():
                data = self._read_config_file(config_path)
                if data:
                    data["_source"] = str(config_path)
                    self._validate(data, str(config_path))
                    configs.append(data)
                    break
        
        # Check legacy ~/.praison/config.toml for backward compat
        legacy_path = Path.home() / ".praison" / "config.toml"
        if legacy_path.exists() and not configs:
            data = self._read_config_file(legacy_path)
            if data:
                data["_source"] = str(legacy_path)
                # Map legacy RAG-centric config to new schema
                data = self._migrate_legacy_config(data)
                configs.append(data)
        
        # Check legacy ~/.praisonai/.env for model/provider
        env_path = praisonai_home / ".env"
        if env_path.exists():
            env_data = self._read_env_file(env_path)
            if env_data and not configs:
                env_data["_source"] = str(env_path)
                configs.append(env_data)
            elif env_data and configs:
                # Merge env data into existing config
                configs[0] = self._deep_merge(configs[0], env_data)
        
        return configs[0] if configs else None
    
    def _load_project_config(self) -> Optional[Dict[str, Any]]:
        """Load project configuration with walk-up discovery."""
        # Build search paths from current directory up to git root (or filesystem root)
        git_root = get_git_root(str(self.cwd))
        search_paths = []
        
        # Walk up from cwd to root (or git root if found)
        current = self.cwd.resolve()
        stop_at = Path("/")
        
        # Collect paths from current directory upward
        while current != current.parent:
            search_paths.append(current)
            if git_root and current == git_root:
                break  # Stop at git root if found
            current = current.parent
        
        # Search for config files
        for search_dir in search_paths:
            for config_name in self.PROJECT_CONFIG_NAMES:
                config_path = search_dir / config_name
                if config_path.exists():
                    data = self._read_config_file(config_path)
                    if data:
                        data["_source"] = str(config_path)
                        # Validate before any migration (TOML legacy is skipped).
                        if not config_name.endswith(".toml"):
                            self._validate(data, str(config_path))
                        else:
                            data = self._migrate_legacy_config(data)
                        return data
        
        return None
    
    def _managed_source_spec(self) -> Dict[str, Any]:
        """Resolve where the managed config should be fetched from, if anywhere.

        Precedence: environment variables override the global config's
        ``managed`` section. Returns an empty dict when no managed source is
        configured (the fully opt-in / backward-compatible path).
        """
        spec: Dict[str, Any] = {}

        # Global config may declare a `managed` section.
        global_config = self._load_global_config()
        if global_config and isinstance(global_config.get("managed"), dict):
            spec.update(global_config["managed"])

        # Environment overrides take precedence over the global section.
        env_url = os.environ.get("PRAISONAI_MANAGED_CONFIG_URL")
        if env_url:
            spec["url"] = env_url
        env_dir = os.environ.get("PRAISONAI_MANAGED_CONFIG_DIR")
        if env_dir:
            spec["dir"] = env_dir
        env_timeout = os.environ.get("PRAISONAI_MANAGED_CONFIG_TIMEOUT")
        if env_timeout:
            try:
                spec["timeout"] = float(env_timeout)
            except ValueError:
                pass

        return spec

    def _managed_cache_path(self, url: str) -> Path:
        """Deterministic on-disk cache location for a managed URL."""
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        cache_dir = Path.home() / ".praison" / _MANAGED_CACHE_DIRNAME
        return cache_dir / f"managed-config-{digest}.json"

    def _fetch_managed_url(self, url: str, timeout: float) -> Optional[Dict[str, Any]]:
        """Fetch managed config from a URL, fail-soft to the cached copy.

        Never blocks a run on the network: a short timeout is used and any
        failure falls back to the last good on-disk cache, else ``None`` so the
        managed layer is simply skipped (offline == local-only behaviour).
        """
        cache_path = self._managed_cache_path(url)
        data: Optional[Dict[str, Any]] = None

        # SSRF guard: only fetch http(s) URLs that resolve to a public host (or
        # explicit loopback for http). A rejected URL falls through to the cache
        # fallback below, exactly like an offline fetch, so behaviour stays
        # fail-soft and never targets internal/metadata endpoints.
        if _is_safe_managed_url(url):
            try:
                import urllib.request

                with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310
                    raw = resp.read().decode("utf-8")
                parsed = yaml.safe_load(raw)
                if isinstance(parsed, dict):
                    data = parsed
            except Exception:
                data = None
        else:
            warnings.warn(
                f"Ignoring unsafe managed config URL '{url}': only https (or "
                "loopback http) URLs resolving to a public host are fetched.",
                UserWarning,
                stacklevel=2,
            )

        if data is not None:
            # Persist the last good copy for offline fail-soft.
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(data))
            except OSError:
                pass
            return data

        # Fetch failed: fall back to the cached last-good copy if present.
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text())
                if isinstance(cached, dict):
                    return cached
            except (OSError, json.JSONDecodeError):
                return None
        return None

    def _load_managed_dir(self, dir_path: str) -> Optional[Dict[str, Any]]:
        """Load managed config from a managed/enterprise directory on disk."""
        try:
            base = Path(dir_path).expanduser()
        except (OSError, ValueError):
            return None
        for name in ("config.yaml", "config.yml", "config.json"):
            candidate = base / name
            if candidate.exists():
                data = self._read_config_file(candidate)
                if isinstance(data, dict):
                    data = dict(data)
                    data["_source"] = str(candidate)
                    return data
        return None

    def _load_managed_config(self) -> Optional[Dict[str, Any]]:
        """Load the optional managed config (remote URL and/or managed dir).

        Returns the merged managed config dict (with ``_source`` provenance) or
        ``None`` when no managed source is configured or nothing could be
        loaded. Backward-compatible: absent configuration is a no-op.
        """
        spec = self._managed_source_spec()
        if not spec:
            return None

        merged: Dict[str, Any] = {}
        sources: List[str] = []

        # Managed directory (MDM/config-management) first.
        dir_path = spec.get("dir")
        if dir_path:
            dir_data = self._load_managed_dir(str(dir_path))
            if dir_data:
                src = dir_data.pop("_source", str(dir_path))
                merged = self._deep_merge(merged, dir_data)
                sources.append(src)

        # Remote URL (fail-soft, cached) layered on top of the managed dir.
        url = spec.get("url")
        if url:
            timeout = float(spec.get("timeout", 3.0))
            url_data = self._fetch_managed_url(str(url), timeout)
            if url_data:
                merged = self._deep_merge(merged, url_data)
                sources.append(str(url))

        if not merged:
            return None

        # Validate the config body only; the ``enforce`` flag is a managed
        # control key, not a config section, so it is excluded from validation.
        self._validate(
            {k: v for k, v in merged.items() if k != "enforce"}, source="managed"
        )
        merged["_source"] = ", ".join(sources) if sources else "managed"
        return merged

    def _split_managed_config(
        self, managed: Optional[Dict[str, Any]]
    ) -> tuple:
        """Split a managed config into (non-policy defaults, enforced policy).

        Policy keys (``permissions``, ``model_allowlist``) are enforced above
        local config unless the managed source opts out via ``enforce: false``.
        Everything else is treated as an overridable default below local config.
        """
        if not managed:
            return {}, {}

        enforce = managed.get("enforce", True)
        body = {k: v for k, v in managed.items() if k not in ("_source", "managed", "enforce")}

        if not enforce:
            # Opt-out: the whole managed source is advisory (below local).
            return body, {}

        policy = {k: body[k] for k in MANAGED_POLICY_KEYS if k in body}
        defaults = {k: v for k, v in body.items() if k not in MANAGED_POLICY_KEYS}
        return defaults, policy

    def resolve_with_provenance(
        self, cli_args: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Resolve config and record, per dotted key, which layer/file set it.

        Returns a mapping of ``"agent.model" -> {"value", "layer", "source"}``
        reflecting the deep-merged winner for each key. This is the reconciled
        provenance view: for any value a CLI-first developer can see exactly
        which file (and layer) supplied it.
        """
        provenance: Dict[str, Dict[str, Any]] = {}

        def _record(layer: str, source: Optional[str], data: Dict[str, Any]) -> None:
            for dotted, value in self._flatten(data).items():
                provenance[dotted] = {
                    "value": value,
                    "layer": layer,
                    "source": source,
                }

        managed = self._load_managed_config()
        managed_source = managed.get("_source") if managed else None
        managed_defaults, managed_policy = self._split_managed_config(managed)

        # Layer 1: built-in defaults (from an empty ResolvedConfig).
        _record("defaults", None, ResolvedConfig().to_dict())

        # Layer 2: managed non-policy defaults (below local).
        if managed_defaults:
            _record(f"managed:{managed_source}", managed_source, managed_defaults)

        # Layer 3: global user config.
        global_config = self._load_global_config()
        if global_config:
            source = global_config.get("_source")
            _record("global", source, {k: v for k, v in global_config.items() if k != "_source"})

        # Layer 4: project config (walk-up discovery).
        project_config = self._load_project_config()
        if project_config:
            source = project_config.get("_source")
            _record("project", source, {k: v for k, v in project_config.items() if k != "_source"})

        # Layer 5: environment variables.
        env_config = self._load_env_config()
        if env_config:
            _record("environment", None, env_config)

        # Layer 6: CLI arguments.
        if cli_args:
            _record("cli", None, self._process_cli_args(cli_args))

        # Layer 7: managed policy — enforced above local; marked non-overridable
        # so it is obvious an org policy won over any local setting.
        if managed_policy:
            for dotted, value in self._flatten(managed_policy).items():
                provenance[dotted] = {
                    "value": value,
                    "layer": f"managed-policy:{managed_source}",
                    "source": managed_source,
                    "enforced": True,
                }

        return provenance

    def _flatten(self, data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """Flatten a nested config dict into dotted keys (leaves only)."""
        flat: Dict[str, Any] = {}
        for key, value in data.items():
            if key == "_source":
                continue
            dotted = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                # Recurse into non-empty dicts; skip empty dicts entirely so the
                # flattened map only ever contains scalar/list leaves (no {}).
                if value:
                    flat.update(self._flatten(value, dotted))
            else:
                flat[dotted] = value
        return flat

    def discover_raw_configs(self) -> List[Dict[str, Any]]:
        """
        Return the raw discovered config dicts (global then project), without
        normalisation through ``ResolvedConfig``.

        Unlike ``resolve()``, this preserves unknown/typo keys so that
        ``validate_config_data`` can surface nested mistakes (e.g.
        ``agent.temprature``) that the resolver would otherwise drop.
        """
        raw: List[Dict[str, Any]] = []
        global_config = self._load_global_config()
        if global_config:
            raw.append(global_config)
        project_config = self._load_project_config()
        if project_config:
            raw.append(project_config)
        return raw

    def _load_env_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables."""
        config = {}
        
        # Model/provider settings
        model_env_vars = [
            ("MODEL_NAME", ["agent", "model"]),
            ("OPENAI_MODEL_NAME", ["agent", "model"]),
            ("PRAISONAI_MODEL", ["agent", "model"]),
            ("PRAISONAI_PROVIDER", ["agent", "provider"]),
            ("OPENAI_BASE_URL", ["agent", "base_url"]),
            ("OPENAI_API_BASE", ["agent", "base_url"]),
            ("PRAISONAI_BASE_URL", ["agent", "base_url"]),
        ]
        
        for env_var, path in model_env_vars:
            value = os.environ.get(env_var)
            if value:
                self._set_nested(config, path, value)
        
        # Output settings
        output_env_vars = [
            ("PRAISONAI_OUTPUT_FORMAT", ["output", "format"]),
            ("PRAISONAI_COLOR", ["output", "color"]),
            ("PRAISONAI_VERBOSE", ["output", "verbose"]),
            ("PRAISONAI_QUIET", ["output", "quiet"]),
        ]
        
        for env_var, path in output_env_vars:
            value = os.environ.get(env_var)
            if value:
                # Convert string bools
                if env_var.endswith(("COLOR", "VERBOSE", "QUIET")):
                    value = value.lower() in ("true", "1", "yes")
                self._set_nested(config, path, value)
        
        # Telemetry
        telemetry = os.environ.get("PRAISONAI_TELEMETRY")
        if telemetry:
            config["telemetry"] = telemetry.lower() in ("true", "1", "yes")
        
        return config if config else {}
    
    def _process_cli_args(self, cli_args: Dict[str, Any]) -> Dict[str, Any]:
        """Process CLI arguments into config structure."""
        config = {}
        
        # Map common CLI args to config paths
        arg_mapping = {
            "model": ["agent", "model"],
            "provider": ["agent", "provider"],
            "base_url": ["agent", "base_url"],
            "temperature": ["agent", "temperature"],
            "max_tokens": ["agent", "max_tokens"],
            "verbose": ["output", "verbose"],
            "quiet": ["output", "quiet"],
            "no_color": ["output", "color"],
            "output_format": ["output", "format"],
        }
        
        for arg, path in arg_mapping.items():
            if arg in cli_args and cli_args[arg] is not None:
                value = cli_args[arg]
                # Handle no_color flag
                if arg == "no_color":
                    value = not value
                self._set_nested(config, path, value)
        
        # Handle tools/toolset
        if "tools" in cli_args and cli_args["tools"]:
            config.setdefault("agent", {})["tools"] = cli_args["tools"]
        if "toolset" in cli_args and cli_args["toolset"]:
            config.setdefault("agent", {})["toolset"] = cli_args["toolset"]
        
        return config
    
    def _read_config_file(self, path: Path) -> Optional[Dict[str, Any]]:
        """Read a configuration file (YAML or TOML) with value interpolation.

        ``${VAR}``, ``{env:VAR}`` and ``{file:./path}`` directives are resolved
        at load time so secrets and reused prompt bodies can live outside the
        tracked config file. Relative ``{file:...}`` paths resolve against the
        directory containing this config file.
        """
        try:
            content = path.read_text()

            if path.suffix in (".yaml", ".yml"):
                data = yaml.safe_load(content) or {}
            elif path.suffix == ".toml":
                data = toml.loads(content)
            elif path.suffix == ".json":
                data = json.loads(content)
            else:
                # Try to detect format
                try:
                    data = yaml.safe_load(content) or {}
                except yaml.YAMLError:
                    try:
                        data = toml.loads(content)
                    except toml.TomlDecodeError:
                        return None

            if isinstance(data, dict):
                data = interpolate(data, base_dir=path.parent)
            return data
        except (OSError, json.JSONDecodeError, toml.TomlDecodeError, yaml.YAMLError):
            return None
    
    def _read_env_file(self, path: Path) -> Dict[str, Any]:
        """Read a .env file and convert to config structure."""
        config = {}
        
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    
                    # Map known .env keys to config structure
                    if key == "model":
                        self._set_nested(config, ["agent", "model"], value)
                    elif key == "provider":
                        self._set_nested(config, ["agent", "provider"], value)
        except Exception:
            pass
        
        return config
    
    def _migrate_legacy_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate legacy config format to new schema."""
        migrated = {}
        
        # Handle old RAGCliConfig format
        if "collection" in data or "vector_store_provider" in data:
            migrated["rag"] = {}
            rag_keys = [
                "collection", "top_k", "hybrid", "rerank", "min_score",
                "include_citations", "max_context_tokens", "vector_store_path",
                "vector_store_provider"
            ]
            for key in rag_keys:
                if key in data:
                    if key == "vector_store_provider":
                        migrated["rag"]["vector_store"] = data[key]
                    else:
                        migrated["rag"][key] = data[key]
        
        # Handle model in legacy format
        if "model" in data and "agent" not in migrated:
            migrated.setdefault("agent", {})["model"] = data["model"]
        
        # Preserve other keys
        for key, value in data.items():
            if key not in ["collection", "top_k", "hybrid", "rerank", "min_score",
                           "include_citations", "max_context_tokens", "vector_store_path",
                           "vector_store_provider", "model", "_source"]:
                migrated[key] = value
        
        # Preserve source
        if "_source" in data:
            migrated["_source"] = data["_source"]
        
        return migrated
    
    def _enforce_policy(
        self, base: ResolvedConfig, policy: Dict[str, Any]
    ) -> ResolvedConfig:
        """Enforce managed-policy keys ABOVE local config by REPLACING them.

        Unlike a deep merge, each enforced top-level key (``permissions``,
        ``model_allowlist``) is swapped out wholesale so that no local sub-key
        (e.g. a project ``permissions.default: allow`` or extra ``rules``)
        survives when the managed policy narrows or omits it. A managed policy
        that documents "replace local permissions" must not silently inherit
        local allow rules.
        """
        base_dict = base.to_dict()
        base_dict["sources"] = base.sources

        # Drop any local counterpart of an enforced key before applying policy so
        # nested local entries cannot survive, then set the managed value outright.
        for key, value in policy.items():
            if key == "_source":
                continue
            base_dict[key] = value

        result = ResolvedConfig.from_dict(base_dict)
        result.sources = base.sources
        return result

    def _merge_configs(
        self,
        base: ResolvedConfig,
        overlay: Dict[str, Any],
        replace_lists: bool = False,
    ) -> ResolvedConfig:
        """Merge overlay config into base config.

        Args:
            replace_lists: When True, overlay lists replace base lists instead
                of concatenating. Used for enforced managed-policy so an org
                allow-list wins outright rather than being appended to.
        """
        # Convert base to dict for merging
        base_dict = base.to_dict()
        base_dict["sources"] = base.sources
        
        # Deep merge
        merged_dict = self._deep_merge(base_dict, overlay, replace_lists=replace_lists)
        
        # Convert back to ResolvedConfig
        result = ResolvedConfig.from_dict(merged_dict)
        result.sources = base.sources  # Preserve sources list
        
        return result
    
    def _deep_merge(
        self,
        base: Dict[str, Any],
        overlay: Dict[str, Any],
        replace_lists: bool = False,
    ) -> Dict[str, Any]:
        """Deep merge overlay into base dictionary.

        When ``replace_lists`` is True, overlay lists replace base lists rather
        than being concatenated (used for enforced managed policy values).
        """
        result = base.copy()
        
        for key, value in overlay.items():
            if key == "_source":
                continue  # Skip internal metadata
                
            if key in result:
                if isinstance(result[key], dict) and isinstance(value, dict):
                    # Recursive merge for nested dicts
                    result[key] = self._deep_merge(result[key], value, replace_lists=replace_lists)
                elif isinstance(result[key], list) and isinstance(value, list):
                    # Concatenate lists (or replace when enforcing policy).
                    result[key] = list(value) if replace_lists else result[key] + value
                else:
                    # Scalar override
                    result[key] = value
            else:
                result[key] = value
        
        return result
    
    def _set_nested(self, d: Dict[str, Any], path: List[str], value: Any) -> None:
        """Set a nested value in a dictionary."""
        for key in path[:-1]:
            d = d.setdefault(key, {})
        d[path[-1]] = value


# Singleton instance for convenient access
_default_resolver: Optional[ConfigResolver] = None


def get_resolver(cwd: Optional[Path] = None, reset: bool = False) -> ConfigResolver:
    """
    Get the default configuration resolver.
    
    Args:
        cwd: Working directory for project discovery
        reset: Force create a new resolver
        
    Returns:
        ConfigResolver instance
    """
    global _default_resolver
    
    if reset or _default_resolver is None or (cwd and _default_resolver.cwd != cwd):
        _default_resolver = ConfigResolver(cwd)
    
    return _default_resolver


def resolve_config(
    cwd: Optional[Path] = None,
    cli_args: Optional[Dict[str, Any]] = None
) -> ResolvedConfig:
    """
    Convenience function to resolve configuration.
    
    Args:
        cwd: Working directory for project discovery
        cli_args: CLI arguments to overlay
        
    Returns:
        Resolved configuration
    """
    resolver = get_resolver(cwd)
    return resolver.resolve(cli_args)