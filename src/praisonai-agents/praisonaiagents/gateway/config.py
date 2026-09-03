"""
Gateway Configuration for PraisonAI Agents.

Provides configuration dataclasses for gateway and session settings.
"""

from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Set,
    Tuple,
    runtime_checkable,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import cost
    from .protocols import TurnExecutorProtocol


# ---------------------------------------------------------------------------
# Canonical config version + doctor-driven migration (Issue #3841)
# ---------------------------------------------------------------------------
#
# The gateway config carries a ``config_version`` stamp so the runtime, the
# operator, and ``gateway doctor --fix`` can all tell whether a config predates
# a breaking change. Migration is expressed as an ordered list of *declarative
# rules* (a detect predicate + a fix mutation as one unit) that ``doctor --fix``
# applies once to move an out-of-date config forward, then stamps the current
# version. This keeps migration a one-time repair rather than a permanent
# load-time heuristic, and gives the canonical config shape a single owner.
GATEWAY_CONFIG_VERSION = 1


class ConfigVersionError(ValueError):
    """Raised when a config carries a ``config_version`` this build can't handle.

    Two cases, both operator-actionable rather than silently corrupting data:
      * the stamp is a version *newer* than :data:`GATEWAY_CONFIG_VERSION` — an
        older binary must not downgrade / migrate a config written by a newer
        one (that would drop keys the newer schema added), so migration refuses;
      * the stamp is present but not a non-boolean integer — a malformed stamp
        (``true``, ``"1"``, ``1.0``) is a mistake, not "current", so it is
        rejected instead of being treated as version 1 via ``True == 1``.
    """


@dataclass
class LegacyConfigRule:
    """A single declarative config-migration rule.

    ``detect`` returns True when the (old) shape this rule fixes is present in
    the raw config mapping; ``fix`` returns the mutated mapping moving it toward
    the current version; ``reason`` is an operator-facing description rendered by
    ``gateway doctor --fix``. Rules are pure functions of the raw mapping so the
    same set can be reasoned about, tested, and applied identically everywhere.
    """

    detect: Callable[[Dict[str, Any]], bool]
    fix: Callable[[Dict[str, Any]], Dict[str, Any]]
    reason: str


def _detect_allowed_users_csv(raw: Dict[str, Any]) -> bool:
    channels = raw.get("channels")
    if not isinstance(channels, dict):
        return False
    return any(
        isinstance(ch, dict) and isinstance(ch.get("allowed_users"), str)
        for ch in channels.values()
    )


def _fix_allowed_users_csv(raw: Dict[str, Any]) -> Dict[str, Any]:
    for ch in raw.get("channels", {}).values():
        if isinstance(ch, dict) and isinstance(ch.get("allowed_users"), str):
            value = ch["allowed_users"]
            ch["allowed_users"] = (
                [u.strip() for u in value.split(",") if u.strip()] if value else []
            )
    return raw


def _detect_missing_group_policy(raw: Dict[str, Any]) -> bool:
    channels = raw.get("channels")
    if not isinstance(channels, dict):
        return False
    return any(
        isinstance(ch, dict) and "group_policy" not in ch
        for ch in channels.values()
    )


def _fix_missing_group_policy(raw: Dict[str, Any]) -> Dict[str, Any]:
    for ch in raw.get("channels", {}).values():
        if isinstance(ch, dict) and "group_policy" not in ch:
            ch["group_policy"] = "mention_only"
    return raw


# Ordered set of migration rules. Each moves an older config shape toward the
# current canonical form; ``migrate_config_with_doctor`` applies them once and
# stamps ``config_version``. New breaking renames/retirements append a rule here
# and bump ``GATEWAY_CONFIG_VERSION`` — the canonical shape has one owner.
GATEWAY_CONFIG_RULES: "List[LegacyConfigRule]" = [
    LegacyConfigRule(
        detect=_detect_allowed_users_csv,
        fix=_fix_allowed_users_csv,
        reason="migrating allowed_users (string) -> list [rule: allowed_users_csv_to_list]",
    ),
    LegacyConfigRule(
        detect=_detect_missing_group_policy,
        fix=_fix_missing_group_policy,
        reason="setting group_policy secure default 'mention_only' [rule: group_policy_default]",
    ),
]


def _parse_config_version(raw: Mapping[str, Any]) -> Optional[int]:
    """Return the config's ``config_version`` as an int, or None if unstamped.

    Rejects a malformed stamp so ``config_version: true`` cannot masquerade as
    version 1 (``True == 1``) and a string/float stamp cannot slip through.
    """
    if "config_version" not in raw:
        return None
    value = raw["config_version"]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigVersionError(
            f"Invalid gateway config_version {value!r}: expected an integer "
            f"(current is {GATEWAY_CONFIG_VERSION}). Fix or remove the stamp."
        )
    return value


def is_config_current(raw: Mapping[str, Any]) -> bool:
    """Return whether ``raw`` already carries the current ``config_version``.

    A malformed stamp (non-integer / boolean) is not "current" — it raises
    :class:`ConfigVersionError` so operators fix it rather than having it
    silently coerced (``True == 1``).
    """
    return _parse_config_version(raw) == GATEWAY_CONFIG_VERSION


def migrate_config_with_doctor(
    raw: Dict[str, Any],
) -> "Tuple[Dict[str, Any], List[str]]":
    """Apply the declarative migration rules once and stamp ``config_version``.

    Returns ``(migrated, applied_reasons)``. The input is copied shallowly (and
    per-channel dicts copied) so the caller's mapping is not mutated in place.
    Only rules whose ``detect`` fires contribute a reason, so a config already
    at the current shape migrates cleanly with an empty reason list while still
    receiving the version stamp. This is the single migration executor behind
    ``gateway doctor --fix``.

    Raises :class:`ConfigVersionError` when the config was written by a *newer*
    build (its stamp exceeds :data:`GATEWAY_CONFIG_VERSION`) or the stamp is
    malformed — an older binary must never downgrade a newer config or drop
    keys it does not understand.
    """
    source_version = _parse_config_version(raw)
    if source_version is not None and source_version > GATEWAY_CONFIG_VERSION:
        raise ConfigVersionError(
            f"gateway config_version {source_version} is newer than this "
            f"build supports ({GATEWAY_CONFIG_VERSION}). Upgrade praisonai / "
            "praisonai-bot to a version that understands this config instead "
            "of migrating it with an older one."
        )

    migrated: Dict[str, Any] = dict(raw)
    channels = migrated.get("channels")
    if isinstance(channels, dict):
        migrated["channels"] = {
            name: (dict(ch) if isinstance(ch, dict) else ch)
            for name, ch in channels.items()
        }

    applied: List[str] = []
    for rule in GATEWAY_CONFIG_RULES:
        if rule.detect(migrated):
            migrated = rule.fix(migrated)
            applied.append(rule.reason)

    migrated["config_version"] = GATEWAY_CONFIG_VERSION
    return migrated, applied


# ---------------------------------------------------------------------------
# Hot-reload registry (Issue #3378)
# ---------------------------------------------------------------------------
#
# Closed set of dotted config paths that are safe to apply *in place* on a
# running gateway without restarting channels or agents. Anything not listed
# here keeps falling through to the existing restart plans, so restart stays
# the safe default for unknown/structural changes (fail-safe).
#
# This is a pure protocol/registry with no heavy imports; the authoritative
# classification lives in core so every runtime reloads identically, while the
# wrapper/bot gateway server only implements the in-place ``apply_hot_reload``.
HOT_APPLIABLE_KEYS: "frozenset[str]" = frozenset({
    "gateway.logging.level",
    "gateway.drain_timeout",
    "gateway.reload_drain_timeout",
})


def is_hot_appliable(path: str) -> bool:
    """Return whether a dotted config ``path`` can be applied without restart.

    A change is hot-appliable when the path itself is registered, or when it is
    a leaf *under* a registered key (e.g. ``gateway.logging.level.extra``).
    Callers should treat every other path as requiring a restart plan.
    """
    if path in HOT_APPLIABLE_KEYS:
        return True
    return any(path.startswith(key + ".") for key in HOT_APPLIABLE_KEYS)


# ---------------------------------------------------------------------------
# Reload scope classification (Issue #3440)
# ---------------------------------------------------------------------------
#
# The wrapper/bot gateway builds a concrete reload plan (which channels to
# bounce, whether to recreate agents, whether to full-restart). The *rules*
# for that plan — hot-appliable vs channel-scoped vs full — must stay
# canonical in core so every runtime reloads identically, rather than being
# duplicated ad-hoc per runtime. This is a pure string classification with no
# heavy imports; the wrapper consumes it and only implements the effects.
class ReloadScope:
    """Canonical classification of a changed config ``path``'s reload scope.

    Values are plain strings so wrapper/runtime code can compare without
    importing this class. ``FULL`` is the fail-safe default for unknown or
    structural changes.

    - ``HOT``: apply in place, no restart (see :func:`is_hot_appliable`).
    - ``CHANNEL``: a change under ``channels.<name>`` — restart only that one
      channel; other channels keep their connections and in-flight turns.
    - ``AGENTS``: an agent/provider/guardrails change — recreate agents only,
      without bouncing channels.
    - ``FULL``: unknown or structural change — full restart (fail-safe).
    """

    HOT = "hot"
    CHANNEL = "channel"
    AGENTS = "agents"
    FULL = "full"


def classify_reload(path: str) -> str:
    """Classify a changed dotted config ``path`` into a :class:`ReloadScope`.

    Canonical, side-effect-free classification shared by every runtime so a
    hot-reload plan is built identically regardless of who loads the config.
    Anything not explicitly recognised falls through to ``ReloadScope.FULL``,
    keeping full restart the fail-safe default for structural changes.
    """
    if is_hot_appliable(path):
        return ReloadScope.HOT

    parts = path.split(".")
    head = parts[0] if parts else ""

    # A change scoped to a single channel (``channels.<name>...``) only needs
    # that channel restarted. The bare ``channels`` section (no name) — and a
    # malformed empty name like ``channels.`` — is a structural change and
    # stays a full restart (fail-safe).
    if head == "channels" and len(parts) >= 2 and parts[1]:
        return ReloadScope.CHANNEL

    # Agent-affecting changes recreate agents without bouncing channels.
    if head in ("agents", "provider", "guardrails"):
        return ReloadScope.AGENTS

    return ReloadScope.FULL


@runtime_checkable
class SupportsHotReload(Protocol):
    """Protocol a gateway implements to apply hot-reloadable config in place.

    The gateway calls :meth:`apply_hot_reload` with the subset of changed paths
    classified as hot-appliable (see :data:`HOT_APPLIABLE_KEYS`) and the newly
    loaded config, mutating the relevant live subsystems without a restart.
    """

    def apply_hot_reload(
        self, paths: Set[str], new_config: Mapping[str, Any]
    ) -> None:
        ...


@dataclass
class SessionConfig:
    """Configuration for gateway sessions.
    
    Attributes:
        timeout: Session timeout in seconds (0 = no timeout)
        max_messages: Maximum messages to keep in history (0 = unlimited)
        persist: Whether to persist session state. Defaults to True so a
            gateway started from the out-of-box path remembers conversations
            across restarts/redeploys via the SQLite transcript store. Set
            ``persist: false`` in the config to opt into ephemeral, in-memory
            sessions.
        persist_path: Path for session persistence
        store: Persistence backend when ``persist`` is set — ``"sqlite"``
            (default: transcripts in a WAL SQLite DB with concurrent readers
            and indexed lookups) or ``"file"`` (legacy per-session JSON files)
        resume_window: How long (seconds) a session stays resumable after disconnect
        max_inbox: Maximum queued messages per session (0 = unlimited, default 256)
        metadata: Additional session metadata
        mirror_runtime_state: Enable runtime state mirroring for native transcript replay (Issue #1943)
    """
    
    timeout: int = 3600  # 1 hour default
    max_messages: int = 1000
    persist: bool = True  # durable by default; set persist=False for ephemeral
    persist_path: Optional[str] = None
    store: str = "sqlite"  # "sqlite" (concurrent, indexed) | "file" (legacy JSON)
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
        if self.store not in ("sqlite", "file"):
            raise ValueError(
                f"Invalid session store {self.store!r}; expected 'sqlite' or 'file'"
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timeout": self.timeout,
            "max_messages": self.max_messages,
            "persist": self.persist,
            "persist_path": self.persist_path,
            "store": self.store,
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
        store_backend: Message store backend — ``"sqlite"`` (default,
            zero-dependency durable store so the at-least-once guarantee
            survives a gateway restart/redeploy), ``"redis"`` (durable +
            multi-process horizontal fan-out) or ``"memory"`` (explicit,
            ephemeral opt-out for testing/single-process throwaway use).
    """
    
    enabled: bool = True
    ack_timeout: int = 30
    max_retries: int = 3
    retry_backoff: float = 2.0
    message_ttl: int = 86400
    store_backend: str = "sqlite"
    
    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.store_backend not in ("sqlite", "redis", "memory"):
            raise ValueError(
                f"Invalid delivery store_backend {self.store_backend!r}; "
                "expected 'sqlite', 'redis' or 'memory'"
            )
    
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
        max_queue_size: Per-client in-memory queue bound. When >0 the queue
            overflows once full, routing further events to the durable store
            (at-least-once). 0 keeps the queue unbounded (no overflow).
    """
    
    enabled: bool = True
    long_poll_timeout: int = 30
    max_batch_size: int = 100
    max_queue_size: int = 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "long_poll_timeout": self.long_poll_timeout,
            "max_batch_size": self.max_batch_size,
            "max_queue_size": self.max_queue_size,
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
        if self.enabled and self.interval_ms == 0:
            raise ValueError(
                "interval_ms must be > 0 when enabled=True "
                "(use enabled=False to disable liveness)"
            )

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
class TurnLockConfig:
    """Configuration for cluster-wide per-turn serialisation (Issue #3643).

    Selects the backend for the gateway's per-turn lock — the guarantee that
    only one turn runs against a given resolved session at a time. The default
    ``"local"`` backend reproduces today's in-process ``asyncio.Lock`` /
    ``LockMap`` behaviour exactly (zero cost, no new dependency), so
    single-replica deployments are byte-for-byte unchanged. Selecting
    ``"redis"`` extends serialisation across every replica so a
    horizontally-scaled gateway (``replicas > 1``) no longer runs concurrent
    turns on one session — the concrete distributed lock lives in the
    wrapper/bot package and reuses the existing ``RedisConfig`` connection and
    the scheduler's proven owner+TTL lease pattern.

    This maps onto the pure core
    :class:`~praisonaiagents.gateway.protocols.TurnLockProtocol`.

    Attributes:
        backend: ``"local"`` (default, in-process ``asyncio.Lock``) or
            ``"redis"`` (distributed lease, cluster-wide serialisation).
        ttl: Lease time-to-live in seconds for a distributed backend. Bounds
            how long a crashed holder's lease survives before it is reclaimable,
            so a dead replica cannot wedge a healthy session (fail-open /
            self-healing, as the scheduler already does). Inert for ``"local"``.
        url: Optional Redis URL for the ``"redis"`` backend. When omitted the
            distributed lock reuses the gateway's configured ``RedisConfig``.
    """

    backend: str = "local"
    ttl: float = 60.0
    url: Optional[str] = None

    def __post_init__(self) -> None:
        if self.backend not in ("local", "redis"):
            raise ValueError(
                f"Invalid turn_lock backend {self.backend!r}; "
                "expected 'local' or 'redis'"
            )
        if not self.ttl > 0:
            raise ValueError("turn_lock ttl must be > 0")

    @property
    def enabled(self) -> bool:
        """Whether a distributed (cross-replica) turn lock is selected."""
        return self.backend != "local"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (hides sensitive URL)."""
        return {
            "backend": self.backend,
            "ttl": self.ttl,
            "url": "***" if self.url else None,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "TurnLockConfig":
        """Create from a parsed ``gateway.turn_lock`` mapping (tolerant of None)."""
        if not isinstance(data, dict):
            return cls()
        return cls(
            backend=str(data.get("backend") or "local"),
            ttl=float(data.get("ttl") or 60.0),
            url=data.get("url"),
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
class EmergencyStopConfig:
    """Configuration for the global operator emergency-stop brake (Issue #4220).

    Selects the backend for the durable, fail-safe operator brake consulted at
    every new-work admission seam (WebSocket inbound, HTTP/MCP inbound, kanban
    dispatch, scheduler due-loop). The default ``"off"`` backend engages a
    no-op brake so ``is_engaged()`` is always ``False`` — behaviour is
    byte-for-byte today's, no new dependency, no hot-path change. Selecting
    ``"file"`` persists the engaged state to a sentinel at ``path`` so it
    survives a crash/restart and is shared across lanes; an unreadable/corrupt
    sentinel counts as *engaged* (fail-safe).

    This maps onto the pure core
    :class:`~praisonaiagents.gateway.protocols.EmergencyStopProtocol`;
    :meth:`to_estop` builds the concrete brake.

    Attributes:
        backend: ``"off"`` (default, no-op) or ``"file"`` (durable sentinel).
        path: Sentinel location for the ``"file"`` backend (required for it).
    """

    backend: str = "off"
    path: Optional[str] = None

    def __post_init__(self) -> None:
        if self.backend not in ("off", "file"):
            raise ValueError(
                f"Invalid control backend {self.backend!r}; expected 'off' or 'file'"
            )
        if self.backend == "file" and not self.path:
            raise ValueError("control backend 'file' requires a 'path'")

    @property
    def enabled(self) -> bool:
        """Whether a real (non-``off``) brake backend is selected."""
        return self.backend != "off"

    def to_estop(self):
        """Build the pure core emergency-stop brake this config describes.

        ``"off"`` returns a :class:`NullEmergencyStop` (never engaged);
        ``"file"`` returns a durable, fail-safe :class:`FileEmergencyStop`.
        """
        from .protocols import FileEmergencyStop, NullEmergencyStop

        if self.backend == "file" and self.path:
            return FileEmergencyStop(self.path)
        return NullEmergencyStop()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {"backend": self.backend, "path": self.path}

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "EmergencyStopConfig":
        """Create from a parsed ``gateway.control`` mapping (tolerant of None)."""
        if not isinstance(data, dict):
            return cls()
        return cls(
            backend=str(data.get("backend") or "off"),
            path=data.get("path"),
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
    # Issue #3467: per-turn wall-clock ceiling. When > 0, a single agent turn
    # that runs longer than this many seconds is cancelled (cooperatively via
    # the agent's interrupt controller and by cancelling the driving task) so a
    # runaway turn cannot wedge the serial per-session queue. 0 = no timeout
    # (today's behaviour: a turn runs to completion).
    per_turn_timeout: float = 0.0
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
    # Issue #3643: cluster-wide per-turn serialisation. Default "local" backend
    # keeps today's in-process asyncio.Lock behaviour (single-replica); "redis"
    # serialises turns across replicas so a horizontally-scaled gateway does not
    # run concurrent turns on one session.
    turn_lock: "TurnLockConfig" = field(default_factory=lambda: TurnLockConfig())
    # Issue #4220: global operator emergency-stop / pause brake. Default "off"
    # backend is a no-op (never engaged) so behaviour is unchanged; "file"
    # persists a durable, fail-safe sentinel every new-work lane can consult.
    control: "EmergencyStopConfig" = field(
        default_factory=lambda: EmergencyStopConfig()
    )
    # Issue #4766: per-session turn-execution seam. Selects *where* a session's
    # agent turn runs (see ``TurnExecutorProtocol``). ``None`` (the default)
    # resolves to ``InProcessTurnExecutor`` at runtime — today's on-loop
    # behaviour, byte-for-byte, with no dependency introduced. Supplying an
    # isolated executor (subprocess / container / remote, in the wrapper)
    # contains a wedged/runaway turn to its own worker instead of forcing the
    # whole-process ``os._exit`` remedy.
    executor: "Optional[TurnExecutorProtocol]" = None

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
        if self.per_turn_timeout < 0:
            raise ValueError(
                "per_turn_timeout must be >= 0 (use 0 to disable the per-turn timeout)"
            )
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
            "per_turn_timeout": self.per_turn_timeout,
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
            "turn_lock": self.turn_lock.to_dict(),
            "control": self.control.to_dict(),
            # Report the active executor type so ``gateway doctor`` can surface
            # it; ``None`` means the in-process default (today's behaviour).
            "executor": (
                type(self.executor).__name__
                if self.executor is not None
                else "inprocess"
            ),
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
                    persist=sc_data.get("persist", True),
                    persist_path=sc_data.get("persist_path"),
                    store=sc_data.get("store", "sqlite"),
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
            per_turn_timeout=float(gw_data.get("per_turn_timeout", 0.0) or 0.0),
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
            turn_lock=TurnLockConfig.from_dict(gw_data.get("turn_lock")),
            control=EmergencyStopConfig.from_dict(gw_data.get("control")),
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
