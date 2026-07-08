"""
Gateway Configuration for PraisonAI Agents.

Provides configuration dataclasses for gateway and session settings.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SessionConfig:
    """Configuration for gateway sessions.
    
    Attributes:
        timeout: Session timeout in seconds (0 = no timeout)
        max_messages: Maximum messages to keep in history (0 = unlimited)
        persist: Whether to persist session state
        persist_path: Path for session persistence
        resume_window: How long (seconds) a session stays resumable after disconnect
        max_inbox: Maximum queued messages per session (0 = unlimited, default 256)
        metadata: Additional session metadata
        mirror_runtime_state: Enable runtime state mirroring for native transcript replay (Issue #1943)
    """
    
    timeout: int = 3600  # 1 hour default
    max_messages: int = 1000
    persist: bool = False
    persist_path: Optional[str] = None
    resume_window: int = 86400  # 24 hours default
    max_inbox: int = 256  # Default bounded queue size
    metadata: Dict[str, Any] = field(default_factory=dict)
    mirror_runtime_state: bool = False  # Opt-in to avoid storage bloat
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.max_inbox < 0:
            raise ValueError(
                "max_inbox must be >= 0 (use 0 for unlimited queue size)"
            )
        if self.timeout < 0:
            raise ValueError("timeout must be >= 0")
        if self.max_messages < 0:
            raise ValueError("max_messages must be >= 0")
        if self.resume_window < 0:
            raise ValueError("resume_window must be >= 0")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timeout": self.timeout,
            "max_messages": self.max_messages,
            "persist": self.persist,
            "persist_path": self.persist_path,
            "resume_window": self.resume_window,
            "max_inbox": self.max_inbox,
            "metadata": self.metadata,
            "mirror_runtime_state": self.mirror_runtime_state,
        }


# ---------------------------------------------------------------------------
# Push notification configuration
# ---------------------------------------------------------------------------

@dataclass
class RedisConfig:
    """Redis connection configuration for push service scaling.
    
    Attributes:
        url: Full Redis URL (takes precedence over host/port)
        host: Redis host
        port: Redis port
        db: Redis database number
        password: Redis password
        prefix: Key prefix namespace
        max_connections: Connection pool size
    """
    
    url: Optional[str] = None
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    prefix: str = "praison:push:"
    max_connections: int = 20
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (hides sensitive data)."""
        return {
            "url": "***" if self.url else None,
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "password": "***" if self.password else None,
            "prefix": self.prefix,
            "max_connections": self.max_connections,
        }


@dataclass
class PresenceConfig:
    """Configuration for presence tracking.
    
    Attributes:
        enabled: Toggle presence tracking
        heartbeat_interval: Expected heartbeat frequency from clients (seconds)
        offline_timeout: Mark offline after this many seconds without heartbeat
        broadcast_changes: Broadcast presence changes to subscribed channels
    """
    
    enabled: bool = True
    heartbeat_interval: int = 15
    offline_timeout: int = 45
    broadcast_changes: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "heartbeat_interval": self.heartbeat_interval,
            "offline_timeout": self.offline_timeout,
            "broadcast_changes": self.broadcast_changes,
        }


@dataclass
class DeliveryConfig:
    """Configuration for at-least-once delivery guarantees.
    
    Attributes:
        enabled: Toggle delivery guarantees
        ack_timeout: Seconds to wait for ACK before retrying
        max_retries: Maximum retry attempts
        retry_backoff: Exponential backoff multiplier
        message_ttl: How long to retain unacknowledged messages (seconds)
        store_backend: Message store backend ("memory" or "redis")
    """
    
    enabled: bool = True
    ack_timeout: int = 30
    max_retries: int = 3
    retry_backoff: float = 2.0
    message_ttl: int = 86400
    store_backend: str = "memory"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "ack_timeout": self.ack_timeout,
            "max_retries": self.max_retries,
            "retry_backoff": self.retry_backoff,
            "message_ttl": self.message_ttl,
            "store_backend": self.store_backend,
        }


@dataclass
class PollingConfig:
    """Configuration for HTTP long-polling fallback.
    
    Attributes:
        enabled: Toggle polling fallback
        long_poll_timeout: Long-poll hang duration (seconds)
        max_batch_size: Max messages per poll response
    """
    
    enabled: bool = True
    long_poll_timeout: int = 30
    max_batch_size: int = 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "long_poll_timeout": self.long_poll_timeout,
            "max_batch_size": self.max_batch_size,
        }


@dataclass
class PushConfig:
    """Top-level configuration for the push notification service.
    
    All push capabilities are opt-in. When enabled=False (default),
    zero overhead is added to the gateway.
    
    Attributes:
        enabled: Feature toggle (push is opt-in)
        redis: Redis config for cross-server scaling (None = local-only)
        presence: Presence tracking settings
        delivery: Delivery guarantee settings
        polling: Polling fallback settings
    """
    
    enabled: bool = False
    redis: Optional[RedisConfig] = None
    presence: PresenceConfig = field(default_factory=PresenceConfig)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "redis": self.redis.to_dict() if self.redis else None,
            "presence": self.presence.to_dict(),
            "delivery": self.delivery.to_dict(),
            "polling": self.polling.to_dict(),
        }


@dataclass
class LivenessConfig:
    """Configuration for application-level connection liveness (Issue #2798).

    Drives the transport-agnostic ping/pong heartbeat contract: the gateway
    emits a ``PING`` every ``interval_ms`` and reaps any connection whose
    last activity is older than ``interval_ms × missed_beats_before_reap``
    (closing it with ``GatewayCloseCode.LIVENESS_TIMEOUT``), while the
    reference client sends heartbeats on the same cadence and force-reconnects
    after a silence watchdog fires.

    This maps directly onto the pure core :class:`~praisonaiagents.gateway.
    protocols.LivenessPolicy`; :meth:`to_policy` builds one.

    Attributes:
        enabled: Toggle liveness heartbeat/reaping. When False (default),
            behaviour is unchanged — ``last_activity`` is stamped but never
            acted upon, so upgrading is fully backward-compatible.
        interval_ms: Heartbeat interval in milliseconds (advertised to clients
            as ``heartbeat_ms``).
        missed_beats_before_reap: How many consecutive missed heartbeat
            intervals of silence before a connection is reaped (>= 1).
    """

    enabled: bool = False
    interval_ms: int = 30_000
    missed_beats_before_reap: int = 2

    def __post_init__(self) -> None:
        if self.interval_ms < 0:
            raise ValueError(
                "interval_ms must be >= 0 (use enabled=False to disable liveness)"
            )
        if self.missed_beats_before_reap < 1:
            raise ValueError("missed_beats_before_reap must be >= 1")

    def to_policy(self):
        """Build the pure core ``LivenessPolicy`` this config describes.

        When ``enabled`` is False the policy is constructed with
        ``interval_ms=0`` so its ``evaluate`` always returns ``KEEP`` —
        reaping is a no-op, preserving today's behaviour.
        """
        from .protocols import LivenessPolicy

        return LivenessPolicy(
            interval_ms=self.interval_ms if self.enabled else 0,
            missed_beats_before_reap=self.missed_beats_before_reap,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "interval_ms": self.interval_ms,
            "missed_beats_before_reap": self.missed_beats_before_reap,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "LivenessConfig":
        """Create from a parsed ``gateway.liveness`` mapping (tolerant of None)."""
        if not isinstance(data, dict):
            return cls()
        return cls(
            enabled=bool(data.get("enabled", False)),
            interval_ms=int(data.get("interval_ms", 30_000)),
            missed_beats_before_reap=int(data.get("missed_beats_before_reap", 2)),
        )


@dataclass
class ApiConfig:
    """Configuration for additive protocol surfaces on the gateway app.

    All surfaces are opt-in. When both are False (default), no extra routes
    are mounted and the gateway behaves exactly as before.

    Attributes:
        openai: Serve OpenAI-compatible endpoints
            (``/v1/chat/completions``, ``/v1/responses``, ``/v1/models``)
            backed by the gateway's live agents and sessions.
        mcp: Serve an MCP JSON-RPC endpoint (``/mcp``) exposing the gateway's
            registered agents as callable tools.
    """

    openai: bool = False
    mcp: bool = False

    @property
    def enabled(self) -> bool:
        """Whether any additional protocol surface is enabled."""
        return bool(self.openai or self.mcp)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {"openai": self.openai, "mcp": self.mcp}

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ApiConfig":
        """Create from a parsed ``gateway.api`` mapping (tolerant of None)."""
        if not isinstance(data, dict):
            return cls()
        return cls(
            openai=bool(data.get("openai", False)),
            mcp=bool(data.get("mcp", False)),
        )


@dataclass
class GatewayConfig:
    """Configuration for the gateway server.
    
    Attributes:
        host: Host to bind to
        port: Port to listen on
        cors_origins: Allowed CORS origins
        allowed_origins: Allowed origins for WebSocket connections (CSWSH defense)
        auth_token: Optional authentication token
        max_connections: Maximum concurrent connections
        max_sessions_per_agent: Maximum sessions per agent (0 = unlimited)
        session_config: Default session configuration
        heartbeat_interval: Heartbeat interval in seconds
        reconnect_timeout: Time to wait for reconnection before closing session
        ssl_cert: Path to SSL certificate (for HTTPS/WSS)
        ssl_key: Path to SSL key
        max_buffered_bytes: Maximum buffered bytes before slow consumer disconnect (default 1MB)
        max_queued_frames: Maximum queued outbound frames per client before slow
            consumer disconnect (0 = unlimited frame count; byte ceiling still
            applies). Default 1000.
        push: Push notification service configuration
        auth_scopes: Optional operator scope policy mapping token -> list of
            scope names (see OperatorScope). When None/empty (default), any
            successfully authenticated client is granted all scopes — identical
            to the previous binary behaviour. Single-operator setups are
            unaffected.
    """
    
    host: str = "127.0.0.1"
    port: int = 8765
    bind_host: Optional[str] = None
    cors_origins: List[str] = field(default_factory=lambda: [])
    allowed_origins: List[str] = field(default_factory=lambda: [])
    auth_token: Optional[str] = None
    max_connections: int = 1000
    max_sessions_per_agent: int = 0  # 0 = unlimited
    session_config: SessionConfig = field(default_factory=SessionConfig)
    heartbeat_interval: int = 30
    reconnect_timeout: int = 60
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    max_buffered_bytes: int = 1024 * 1024  # 1MB default
    max_queued_frames: int = 1000  # Per-client outbound frame ceiling
    # Issue #2454: gateway-wide inbound admission control. 0 disables the gate
    # (today's behaviour: every inbound turn dispatches immediately).
    max_concurrent_runs: int = 0  # Aggregate concurrency ceiling (0 = unlimited)
    queue_depth: int = 0  # Bounded wait queue when at the ceiling
    overflow_policy: str = "reject"  # reject | queue | shed_oldest
    # Issue #2620: pre-auth edge protections for internet-exposed deployments.
    # Cap concurrent *unauthenticated* WebSocket connections per source IP so a
    # hostile client cannot park many half-open sockets up to max_connections
    # (0 = disabled). Loopback is always exempt at the enforcement layer.
    preauth_max_connections_per_ip: int = 32
    # Close a connection after this many unauthorized frames and log-sample the
    # rest so a hostile client cannot flood logs / burn per-frame work
    # (0 = disabled).
    max_unauthorized_frames: int = 10
    push: PushConfig = field(default_factory=PushConfig)
    auth_scopes: Optional[Dict[str, List[str]]] = None
    # Additive protocol surfaces (OpenAI-compatible / MCP) served on the same
    # app and auth. Opt-in; disabled by default so the gateway is unchanged.
    api: ApiConfig = field(default_factory=ApiConfig)
    # Issue #2798: application-level connection liveness (ping/pong heartbeat +
    # half-open reaper). Opt-in; disabled by default so behaviour is unchanged.
    liveness: LivenessConfig = field(default_factory=LivenessConfig)

    def __post_init__(self) -> None:
        """Post-initialization to set bind_host from host if not specified and validate values."""
        if self.bind_host is None:
            self.bind_host = self.host
        if self.max_buffered_bytes < 0:
            raise ValueError(
                "max_buffered_bytes must be >= 0 (use 0 to disable slow-consumer checks)"
            )
        if self.max_queued_frames < 0:
            raise ValueError(
                "max_queued_frames must be >= 0 (use 0 to disable the frame-count ceiling)"
            )
        if self.max_connections < 0:
            raise ValueError("max_connections must be >= 0")
        if self.heartbeat_interval < 0:
            raise ValueError("heartbeat_interval must be >= 0")
        if self.reconnect_timeout < 0:
            raise ValueError("reconnect_timeout must be >= 0")
        if self.max_concurrent_runs < 0:
            raise ValueError(
                "max_concurrent_runs must be >= 0 (use 0 to disable admission control)"
            )
        if self.queue_depth < 0:
            raise ValueError("queue_depth must be >= 0")
        if self.overflow_policy not in ("reject", "queue", "shed_oldest"):
            raise ValueError(
                "overflow_policy must be one of 'reject', 'queue', 'shed_oldest'"
            )
        if self.preauth_max_connections_per_ip < 0:
            raise ValueError(
                "preauth_max_connections_per_ip must be >= 0 (use 0 to disable "
                "the pre-auth connection budget)"
            )
        if self.max_unauthorized_frames < 0:
            raise ValueError(
                "max_unauthorized_frames must be >= 0 (use 0 to disable the "
                "unauthorized-frame flood guard)"
            )

    @property
    def has_scope_policy(self) -> bool:
        """Whether an operator scope policy is configured.

        When False (the default), every authenticated client is granted all
        scopes — preserving the original binary auth behaviour.
        """
        return bool(self.auth_scopes)

    def resolve_scopes(self, token: Optional[str]) -> List[str]:
        """Resolve the operator scopes granted to ``token``.

        Backward-compatible contract:
          * No scope policy configured  -> all scopes (today's behaviour).
          * Policy configured + token listed -> that token's scopes.
          * Policy configured + token absent/None -> no scopes (deny).

        Scope names are returned as plain strings so callers in the wrapper
        can compare against ``OperatorScope`` values without importing them.
        Unknown scope names (e.g. typos in ``gateway.yaml``) are dropped and a
        warning is logged so misconfiguration surfaces early instead of
        silently denying all access.
        """
        from .protocols import OperatorScope

        valid_scopes = {s.value for s in OperatorScope.all()}
        all_scopes = list(valid_scopes)
        if not self.auth_scopes:
            return all_scopes
        if token is None:
            return []
        granted = self.auth_scopes.get(token)
        if granted is None:
            return []
        resolved: List[str] = []
        unknown: List[str] = []
        for s in granted:
            name = str(s)
            if name in valid_scopes:
                resolved.append(name)
            else:
                unknown.append(name)
        if unknown:
            import logging
            logging.getLogger(__name__).warning(
                "Ignoring unknown operator scope(s) %s; valid scopes are %s",
                unknown,
                sorted(valid_scopes),
            )
        return resolved

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (hides sensitive data)."""
        return {
            "host": self.host,
            "port": self.port,
            "cors_origins": self.cors_origins,
            "allowed_origins": self.allowed_origins,
            "auth_token": "***" if self.auth_token else None,
            "max_connections": self.max_connections,
            "max_sessions_per_agent": self.max_sessions_per_agent,
            "session_config": self.session_config.to_dict(),
            "heartbeat_interval": self.heartbeat_interval,
            "reconnect_timeout": self.reconnect_timeout,
            "ssl_enabled": bool(self.ssl_cert and self.ssl_key),
            "max_buffered_bytes": self.max_buffered_bytes,
            "max_queued_frames": self.max_queued_frames,
            "max_concurrent_runs": self.max_concurrent_runs,
            "queue_depth": self.queue_depth,
            "overflow_policy": self.overflow_policy,
            "preauth_max_connections_per_ip": self.preauth_max_connections_per_ip,
            "max_unauthorized_frames": self.max_unauthorized_frames,
            "push": self.push.to_dict(),
            "scope_policy_enabled": self.has_scope_policy,
            "api": self.api.to_dict(),
            "liveness": self.liveness.to_dict(),
        }
    
    @property
    def is_secure(self) -> bool:
        """Whether SSL/TLS is enabled."""
        return bool(self.ssl_cert and self.ssl_key)
    
    @property
    def ws_url(self) -> str:
        """WebSocket URL for this gateway."""
        protocol = "wss" if self.is_secure else "ws"
        return f"{protocol}://{self.host}:{self.port}"
    
    @property
    def http_url(self) -> str:
        """HTTP URL for this gateway."""
        protocol = "https" if self.is_secure else "http"
        return f"{protocol}://{self.host}:{self.port}"


@dataclass
class ChannelRouteConfig:
    """Configuration for routing channel messages to agents.
    
    Attributes:
        channel_type: Platform name (telegram, discord, slack, etc.)
        token_env: Environment variable name for the channel token
        app_token_env: Optional env var for app token (Slack Socket Mode)
        routes: Mapping of context → agent_id
                Keys: "dm", "group", "channel", "default"
                Values: agent ID strings
        enabled: Whether this channel is enabled
        metadata: Additional channel-specific configuration
    """
    
    channel_type: str
    token_env: str = ""
    app_token_env: Optional[str] = None
    routes: Dict[str, str] = field(default_factory=lambda: {"default": "default"})
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_agent_id(self, context: str = "default") -> str:
        """Resolve agent ID for a given message context.
        
        Args:
            context: Message context (dm, group, channel, default)
            
        Returns:
            The agent ID for the given context, falling back to "default" route.
        """
        return self.routes.get(context, self.routes.get("default", "default"))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "channel_type": self.channel_type,
            "token_env": self.token_env,
            "app_token_env": self.app_token_env,
            "routes": dict(self.routes),
            "enabled": self.enabled,
            "metadata": dict(self.metadata),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChannelRouteConfig":
        """Create from dictionary."""
        return cls(
            channel_type=data.get("channel_type", ""),
            token_env=data.get("token_env", ""),
            app_token_env=data.get("app_token_env"),
            routes=data.get("routes", {"default": "default"}),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
        )


@dataclass
class MultiChannelGatewayConfig:
    """Configuration for multi-channel gateway mode.
    
    Loaded from gateway.yaml. Defines agents, channels, and routing.
    
    Attributes:
        gateway: Base gateway configuration
        agents: Agent configurations by ID (name → config dict)
        channels: Channel routing configurations by name
    """
    
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    agents: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    channels: Dict[str, ChannelRouteConfig] = field(default_factory=dict)
    hooks: List[Any] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultiChannelGatewayConfig":
        """Create from parsed YAML dictionary.
        
        Expected format::
        
            gateway:
              host: "127.0.0.1"
              port: 8765
            agents:
              personal:
                instructions: "You are a helpful assistant"
                model: gpt-4o-mini
            channels:
              telegram:
                token: ${TELEGRAM_BOT_TOKEN}
                routes:
                  dm: personal
                  default: personal
        
        Args:
            data: Parsed YAML dictionary
            
        Returns:
            Configured MultiChannelGatewayConfig instance
        """
        # Parse gateway section
        gw_data = data.get("gateway", {})
        
        # Parse session config if provided
        session_config = SessionConfig()
        if "session_config" in gw_data:
            sc_data = gw_data["session_config"]
            if isinstance(sc_data, dict):
                session_config = SessionConfig(
                    timeout=sc_data.get("timeout", 3600),
                    max_messages=sc_data.get("max_messages", 1000),
                    persist=sc_data.get("persist", False),
                    persist_path=sc_data.get("persist_path"),
                    resume_window=sc_data.get("resume_window", 86400),
                    max_inbox=sc_data.get("max_inbox", 256),
                    metadata=sc_data.get("metadata", {}),
                )
        
        # Parse optional operator scope policy. Two supported shapes:
        #   gateway:
        #     auth:
        #       tokens:
        #         - token: "${VIEWER_TOKEN}"
        #           scopes: [read]
        # or a flat mapping:
        #   gateway:
        #     auth_scopes:
        #       "${VIEWER_TOKEN}": [read]
        auth_scopes: Optional[Dict[str, List[str]]] = None
        auth_section = gw_data.get("auth")
        if isinstance(auth_section, dict) and isinstance(auth_section.get("tokens"), list):
            auth_scopes = {}
            for entry in auth_section["tokens"]:
                if isinstance(entry, dict) and entry.get("token"):
                    auth_scopes[str(entry["token"])] = list(entry.get("scopes", []))
        elif isinstance(gw_data.get("auth_scopes"), dict):
            auth_scopes = {
                str(tok): list(scopes)
                for tok, scopes in gw_data["auth_scopes"].items()
            }

        gateway_config = GatewayConfig(
            host=gw_data.get("host", "127.0.0.1"),
            port=gw_data.get("port", 8765),
            cors_origins=gw_data.get("cors_origins", []),
            allowed_origins=gw_data.get("allowed_origins", []),
            auth_token=gw_data.get("auth_token"),
            max_connections=gw_data.get("max_connections", 1000),
            max_sessions_per_agent=gw_data.get("max_sessions_per_agent", 0),
            session_config=session_config,
            heartbeat_interval=gw_data.get("heartbeat_interval", 30),
            reconnect_timeout=gw_data.get("reconnect_timeout", 60),
            ssl_cert=gw_data.get("ssl_cert"),
            ssl_key=gw_data.get("ssl_key"),
            max_buffered_bytes=int(gw_data.get("max_buffered_bytes", 1024 * 1024)),
            max_queued_frames=int(gw_data.get("max_queued_frames", 1000)),
            max_concurrent_runs=int(gw_data.get("max_concurrent_runs", 0) or 0),
            queue_depth=int(gw_data.get("queue_depth", 0) or 0),
            overflow_policy=str(gw_data.get("overflow_policy", "reject") or "reject"),
            preauth_max_connections_per_ip=int(
                gw_data.get("preauth_max_connections_per_ip", 32)
            ),
            max_unauthorized_frames=int(
                gw_data.get("max_unauthorized_frames", 10)
            ),
            auth_scopes=auth_scopes,
            api=ApiConfig.from_dict(gw_data.get("api")),
            liveness=LivenessConfig.from_dict(gw_data.get("liveness")),
        )
        
        # Parse agents section (pass through as dicts)
        agents = data.get("agents", {})
        
        # Parse channels section
        channels: Dict[str, ChannelRouteConfig] = {}
        for name, ch_data in data.get("channels", {}).items():
            if isinstance(ch_data, dict):
                channels[name] = ChannelRouteConfig(
                    channel_type=name,
                    token_env=ch_data.get("token", ""),
                    app_token_env=ch_data.get("app_token"),
                    routes=ch_data.get("routes", {"default": "default"}),
                    enabled=ch_data.get("enabled", True),
                    metadata={
                        k: v for k, v in ch_data.items()
                        if k not in ("token", "app_token", "routes", "enabled")
                    },
                )
        
        # Parse inbound trigger hooks (Issue #2281). The hooks live either at
        # the top level (``hooks:``) or nested under ``gateway:`` for grouping.
        from .hooks import HookConfig

        raw_hooks = data.get("hooks")
        if raw_hooks is None:
            raw_hooks = gw_data.get("hooks")
        hooks: List[HookConfig] = []
        for entry in raw_hooks or []:
            if isinstance(entry, dict) and entry.get("path"):
                try:
                    hooks.append(HookConfig.from_dict(entry))
                except (ValueError, TypeError):
                    import logging
                    logging.getLogger(__name__).warning(
                        "Skipping invalid gateway hook entry: %s", entry
                    )

        return cls(
            gateway=gateway_config,
            agents=agents,
            channels=channels,
            hooks=hooks,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "gateway": self.gateway.to_dict(),
            "agents": dict(self.agents),
            "channels": {
                name: ch.to_dict() for name, ch in self.channels.items()
            },
            "hooks": [h.to_dict() for h in self.hooks],
        }
