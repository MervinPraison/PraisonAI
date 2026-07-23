"""
Pydantic-based config schema validation for bot.yaml / gateway.yaml.

Provides clear, human-friendly error messages when configuration is invalid.
This is the canonical configuration schema for all bot/gateway configurations.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


def _register_redaction(value: str) -> None:
    """Register a resolved secret value for log redaction (best-effort).

    Delegates to the core redaction registry (Issue #3102) but never fails
    config validation if core is unavailable.
    """
    try:
        from praisonaiagents.secrets import register_secret_for_redaction

        register_secret_for_redaction(value)
    except Exception:  # pragma: no cover - redaction is best-effort
        pass


class AgentConfigSchema(BaseModel):
    """Schema for agent configuration in bot.yaml."""
    name: str = "assistant"
    instructions: str = ""
    model: Optional[str] = "gpt-4o-mini"
    llm: Optional[str] = None  # Alias for model
    memory: bool = False
    tools: List[str] = Field(default_factory=list)
    knowledge: Union[bool, List[str]] = False
    web_search: bool = False
    web_search_provider: str = "duckduckgo"
    auto_approve: bool = False
    
    @model_validator(mode="after")
    def handle_model_aliases(self):
        """Handle model/llm aliases."""
        # Use llm if provided and model wasn't explicitly set
        if self.llm and "model" not in self.model_fields_set:
            self.model = self.llm
        return self


class SessionResetConfigSchema(BaseModel):
    """Schema for session reset policy configuration."""
    mode: str = "none"  # none | idle | daily | both
    idle_minutes: int = 60  # Reset after N minutes of inactivity
    at_hour: Optional[int] = None  # Daily reset hour (0-23)
    
    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = {"none", "idle", "daily", "both"}
        if v not in allowed:
            raise ValueError(
                f"Invalid reset mode '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v
    
    @field_validator("idle_minutes")
    @classmethod
    def validate_idle_minutes(cls, v: int) -> int:
        if v < 1:
            raise ValueError("idle_minutes must be at least 1")
        return v
    
    @field_validator("at_hour")
    @classmethod
    def validate_at_hour(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (0 <= v <= 23):
            raise ValueError("at_hour must be between 0 and 23")
        return v
    
    @model_validator(mode="after")
    def validate_config_consistency(self):
        """Ensure at_hour is set when mode requires it."""
        if self.mode in ("daily", "both") and self.at_hour is None:
            raise ValueError(f"at_hour is required when mode is '{self.mode}'")
        return self


class SessionCompactionConfigSchema(BaseModel):
    """Schema for session history compaction configuration.

    When enabled, older turns in a long-lived bot/gateway session are
    summarised (rather than hard-truncated) once the history exceeds the
    configured budget, so context survives across weeks-long conversations
    and restarts. Disabled by default to preserve legacy behaviour.
    """
    enabled: bool = False
    strategy: str = "summarize"  # truncate | sliding | summarize | smart | prune | llm_summarize
    max_messages: int = 100  # Approx. compaction threshold (converted to a token budget; max_history remains a hard cap)
    max_tokens: Optional[int] = None  # Optional token-based budget (overrides messages)
    keep_recent: int = 10  # Number of most-recent messages kept verbatim

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        allowed = {"truncate", "sliding", "summarize", "smart", "prune", "llm_summarize"}
        if v not in allowed:
            raise ValueError(
                f"Invalid compaction strategy '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v

    @field_validator("max_messages")
    @classmethod
    def validate_max_messages(cls, v: int) -> int:
        if v < 1:
            raise ValueError("max_messages must be at least 1")
        return v

    @field_validator("keep_recent")
    @classmethod
    def validate_keep_recent(cls, v: int) -> int:
        if v < 0:
            raise ValueError("keep_recent must be non-negative")
        return v


class SessionConfigSchema(BaseModel):
    """Schema for session configuration."""
    max_history: int = 100
    reset: Optional[SessionResetConfigSchema] = None
    compaction: Optional[SessionCompactionConfigSchema] = None
    # Group/channel session scope (Issue #2376). ``per_user`` (default) keeps
    # today's per-sender isolation; ``per_chat`` routes group/channel messages
    # to a single shared session so the agent follows one multi-party thread.
    session_scope: str = "per_user"
    # Sender-attribution template applied to each turn in per_chat scope.
    # Supports ``{sender}`` and ``{time}`` placeholders.
    attribution: str = "[{sender}] "
    # Temporal grounding (Issue #2834). When enabled, each inbound turn is
    # prefixed with its real arrival time so an always-on gateway agent can
    # reason about "now", gaps between messages and relative-time requests
    # ("in 2 hours"). Applied to both per_user (DM) and per_chat (group)
    # scopes. De-duplicated on history replay so prefixes never accumulate.
    timestamps: bool = False
    # strftime template for the per-message arrival-time prefix. To keep replay
    # de-duplication working (see ``strip_leading_timestamps`` in ``_session.py``),
    # a custom template should render a ``YYYY-MM-DD HH:MM`` date-time inside the
    # bracket (i.e. include ``%Y-%m-%d %H:%M``); the leading ``%a`` weekday and
    # ``%Z`` timezone are optional and locale-independent for de-duplication.
    timestamp_template: str = "[%a %Y-%m-%d %H:%M %Z] "

    @field_validator("session_scope")
    @classmethod
    def validate_session_scope(cls, v: str) -> str:
        allowed = {"per_user", "per_chat"}
        if v not in allowed:
            raise ValueError(
                f"Invalid session_scope '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v


class StreamingConfigSchema(BaseModel):
    """Schema for streaming reply configuration."""
    mode: str = "off"  # off | draft | progress | auto
    min_interval: float = 1.5  # Minimum seconds between edits
    min_delta: int = 120  # Minimum character delta before edit
    placeholder_text: str = "🤔 Thinking..."
    progress_prefix: str = "🤔 "
    # Progress rendering style: "line" (single overwritten tool line) or
    # "feed" (bounded multi-line rolling status feed). Applies to progress mode.
    progress_style: str = "line"
    progress_max_lines: int = 8  # Max trailing lines shown in feed style
    progress_max_line_chars: int = 120  # Per-line char cap in feed style
    # Flood-control / resilience for progressive edits
    disable_progressive_edits_after: int = 3  # Consecutive edit failures before giving up
    flood_backoff_factor: float = 2.0  # Multiply interval on each flood/429
    max_interval: float = 30.0  # Cap for the adaptively-widened interval
    strip_reasoning_tags: bool = True  # Strip <think>/<reasoning> from output
    
    @field_validator("mode")
    @classmethod
    def validate_streaming_mode(cls, v: str) -> str:
        allowed = {"off", "draft", "progress", "auto"}
        if v not in allowed:
            raise ValueError(
                f"Invalid streaming mode '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v
    
    @field_validator("min_interval")
    @classmethod
    def validate_min_interval(cls, v: float) -> float:
        if v < 0.1:
            raise ValueError("min_interval must be at least 0.1 seconds")
        return v
    
    @field_validator("min_delta")
    @classmethod
    def validate_min_delta(cls, v: int) -> int:
        if v < 1:
            raise ValueError("min_delta must be at least 1 character")
        return v

    @field_validator("progress_style")
    @classmethod
    def validate_progress_style(cls, v: str) -> str:
        allowed = {"line", "feed"}
        if v not in allowed:
            raise ValueError(
                f"Invalid progress_style '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v


class OutboundResilienceSchema(BaseModel):
    """Schema for outbound message retry configuration."""
    enabled: bool = True
    initial_ms: float = 1000.0  # Initial retry delay in ms
    max_ms: float = 10000.0  # Maximum retry delay in ms
    factor: float = 1.5  # Exponential backoff factor
    max_attempts: int = 3  # Maximum retry attempts
    jitter: float = 0.25  # Random jitter fraction
    dlq_path: Optional[str] = None  # Path to outbound DLQ database
    
    @field_validator("initial_ms")
    @classmethod
    def validate_initial_ms(cls, v: float) -> float:
        if v < 100:
            raise ValueError("initial_ms must be at least 100ms")
        return v
    
    @field_validator("max_attempts")
    @classmethod
    def validate_max_attempts(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("max_attempts must be between 1 and 10")
        return v


class DeliveryConfigSchema(BaseModel):
    """Schema for durable inbound/outbound delivery configuration.

    Durability is **on by default** for long-running gateway/bot runs: a
    deduplicating inbound journal and an inbound dead-letter queue are wired
    against a single canonical per-agent SQLite store so a crash mid-turn or a
    platform webhook redelivery never silently loses or double-processes a
    message. Advanced operators can override the store location or disable
    durability entirely.
    """
    durable: bool = True  # default on for gateway/bot runs
    store: Optional[str] = None  # optional canonical SQLite store override


class SttConfigSchema(BaseModel):
    """Schema for inbound speech-to-text (STT) configuration (Issue #2721).

    Inbound voice notes are transcribed and fed to the agent by default so the
    conversation continues seamlessly by voice. Set ``enabled: false`` to opt
    out; when disabled (or on failure) the turn still reaches the agent with a
    visible placeholder rather than being silently dropped.
    """
    enabled: bool = True
    echo_transcripts: bool = False  # Echo the recognised text back to the user
    language: Optional[str] = None  # Optional forced language code (e.g. "en")
    model: Optional[str] = None  # Optional STT model override (default whisper-1)


class ChannelConfigSchema(BaseModel):
    """Schema for a single channel configuration.

    Accepts plugin-declared config keys: a channel registered via
    ``register_platform(..., descriptor=...)`` (Issue #2801) can declare its
    own config fields (e.g. IRC's ``server``/``nickserv_password``) which are
    preserved here instead of being silently dropped. ``extra="allow"`` keeps
    unknown keys so they reach the adapter, and ``apply_channel_descriptor``
    resolves env fallbacks and enforces required plugin fields.
    """
    model_config = ConfigDict(extra="allow")

    platform: Optional[str] = None
    # Credential fields accept plaintext, a ``${ENV}`` reference, or the
    # additive secret-reference form ``{source: file|env|exec, id: ...}``
    # (Issue #3102). The reference form is resolved by the core secret
    # resolver and the resolved value is registered for log redaction.
    token: Union[str, Dict[str, Any]] = ""
    app_token: Optional[Union[str, Dict[str, Any]]] = None  # For Slack Socket Mode
    mode: str = "poll"  # poll | ws | webhook | hybrid
    group_policy: str = "mention_only"  # Default to secure: respond_all, mention_only, command_only
    allow_silence: bool = False  # Allow agent to return NO_REPLY to stay silent
    silence_token: Optional[str] = None  # Custom silence token (defaults to NO_REPLY)
    allowlist: List[str] = Field(default_factory=list)
    blocklist: List[str] = Field(default_factory=list)
    allowed_users: List[str] = Field(default_factory=list)  # Changed to List for consistency
    admin_users: Optional[str] = None  # Comma-separated list of admin user IDs
    user_allowed_commands: Optional[str] = None  # Comma-separated list of allowed commands
    routes: Dict[str, str] = Field(default_factory=dict)  # Context -> agent_id mapping
    routing: Optional[Dict[str, str]] = None  # Alias for routes
    bindings: List[Dict[str, Any]] = Field(default_factory=list)  # Priority-ordered route bindings (Issue #2225)
    webhook_url: Optional[str] = None
    webhook_port: int = 8080
    streaming: Optional[StreamingConfigSchema] = None
    home_channel: Optional[str] = None  # Default channel for this platform
    aliases: Dict[str, str] = Field(default_factory=dict)  # Friendly name -> channel_id mapping
    outbound_resilience: Optional[OutboundResilienceSchema] = None
    delivery: Optional[DeliveryConfigSchema] = None  # Durable inbound/outbound delivery
    session: Optional[SessionConfigSchema] = None
    max_history: Optional[int] = None  # Backward compatibility
    # Inbound media (Issue #2350): when a user sends a photo/document/video,
    # adapters download and validate it (SSRF-safe, magic-byte checked) and
    # forward the cached path to the agent's vision capability. Set to 0 to
    # disable inbound media handling.
    max_inbound_media_bytes: int = Field(default=20 * 1024 * 1024, ge=0)
    # Inbound speech-to-text (Issue #2721): when a user sends a voice note,
    # adapters transcribe it and feed the transcript to the agent. On by
    # default; set ``stt.enabled: false`` to opt out.
    stt: Optional[SttConfigSchema] = None

    # Shell execution opt-in for inbound channel bots (Slack/Telegram/etc.)
    allow_shell: bool = False
    auto_approve_shell: bool = True
    approval_channel: Optional[str] = None
    approval_users: Optional[Union[str, List[str]]] = None
    # channel (default) | gateway | http | webhook
    approval_mode: Optional[str] = None
    approval_webhook_url: Optional[str] = None
    approval_http_host: Optional[str] = None
    approval_http_port: Optional[int] = None
    
    # Platform-specific fields
    phone_number_id: Optional[str] = None  # WhatsApp
    verify_token: Optional[Union[str, Dict[str, Any]]] = None  # WhatsApp
    whatsapp_mode: Optional[str] = None  # WhatsApp-specific mode: "cloud" or "web"
    creds_dir: Optional[str] = None  # WhatsApp web mode credentials directory
    email_address: Optional[str] = None  # Email
    imap_server: Optional[str] = None  # Email  
    smtp_server: Optional[str] = None  # Email
    inbox_id: Optional[str] = None  # AgentMail
    domain: Optional[str] = None  # AgentMail
    
    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = {"poll", "ws", "webhook", "hybrid"}
        if v not in allowed:
            raise ValueError(
                f"Invalid mode '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v
    
    @field_validator("token", "app_token", "verify_token", mode="before")
    @classmethod
    def resolve_secret_ref(cls, v):
        """Resolve credential inputs for every secret field (Issue #3102).

        Backward compatible: plaintext and ``${ENV}`` continue to work. The
        additive reference form ``{source: file|env|exec, id: ...}`` (or a
        core ``SecretRef``) is resolved via the core secret resolver, and the
        resolved value is registered for log redaction so it never leaks into
        logs or tracebacks.
        """
        if v is None or v == "":
            return v

        # Plain ${ENV} kept inline to avoid importing core for the common case.
        if isinstance(v, str):
            if v.startswith("${") and v.endswith("}"):
                env_key = v[2:-1]
                resolved = os.environ.get(env_key, "")
                if not resolved:
                    # Partial-credential isolation (Issue #3159): an unset
                    # channel token env var (rotation, expiry, a fresh deploy)
                    # must NOT abort the whole gateway. Return an empty token
                    # so the runtime skips just this channel and every healthy
                    # channel keeps serving; ``gateway status``/``doctor``
                    # report it as configured-unavailable.
                    logger.warning(
                        "Channel token env var '%s' not set — channel will be "
                        "skipped (degraded). Set it with: export %s=your_token",
                        env_key,
                        env_key,
                    )
                    return ""
                _register_redaction(resolved)
                return resolved
            _register_redaction(v)
            return v

        # Reference form (dict / SecretRef) → resolve via core.
        try:
            from praisonaiagents.secrets import resolve_secret
        except ImportError:  # pragma: no cover - core always present in-tree
            raise ValueError(
                "Secret-reference form requires praisonaiagents.secrets; "
                "use a plaintext string or ${ENV} reference instead."
            )
        result = resolve_secret(v)
        if not result.available or result.value is None:
            # Partial-credential isolation (Issue #3159): a channel whose
            # secret is ``configured-but-unavailable``/``missing`` (rotation,
            # expiry, a secret-store blip) must NOT abort the whole gateway.
            # Return an empty token and mark the channel degraded so the
            # runtime skips just this channel and every healthy channel keeps
            # serving. Fail-closed stays reserved for structurally invalid
            # config and the gateway's own ingress/auth secret (validated
            # elsewhere). ``gateway status``/``doctor`` still report the
            # per-channel availability from the raw reference.
            detail = result.detail or "unavailable"
            logger.warning(
                "Channel secret configured-unavailable — channel will be "
                "skipped (degraded): %s",
                detail,
            )
            return ""
        return result.value
    
    @field_validator("group_policy")
    @classmethod
    def validate_group_policy(cls, v: str) -> str:
        allowed = {"respond_all", "mention_only", "command_only"}
        if v not in allowed:
            raise ValueError(
                f"Invalid group_policy '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v

    @field_validator("approval_mode")
    @classmethod
    def validate_approval_mode(cls, v: Optional[str]) -> Optional[str]:
        """Fail-closed on an unknown shell-approval backend selector.

        A typo (``chanel``/``webook``) must be rejected at load time rather
        than silently falling through to the gateway-queue fallback, which
        would leave shell approvals stuck where the operator never looks.
        """
        if v is None:
            return v
        allowed = {"channel", "gateway", "http", "webhook"}
        normalized = v.strip().lower()
        if normalized not in allowed:
            raise ValueError(
                f"Invalid approval_mode '{v}'. Must be one of: "
                f"{', '.join(sorted(allowed))}"
            )
        return normalized
    
    @model_validator(mode="after")
    def validate_security(self):
        """Validate security settings and warn about unsafe configurations."""
        # Merge routing and routes
        if self.routing and not self.routes:
            self.routes = self.routing
            
        # Warn about empty allowed_users (open to everyone)
        if not self.allowed_users and not self.allowlist and not self.blocklist:
            logger.warning(
                "Channel has no user restrictions (allowed_users/allowlist/blocklist). "
                "Bot will respond to EVERYONE. Consider adding allowed_users for security."
            )
            
        # Warn about respond_all in production
        if self.group_policy == "respond_all":
            logger.warning(
                "Channel uses 'respond_all' group_policy. "
                "Consider 'mention_only' for better security."
            )
        return self

    def apply_channel_descriptor(self, descriptor: Any) -> "ChannelConfigSchema":
        """Wire plugin-declared config fields from a channel descriptor.

        For each ``ChannelField`` the descriptor declares (Issue #2801):
        - if the value is missing but an ``env`` fallback is set and present in
          the environment, populate it (so a plugin's secret can come from the
          environment just like the built-in ``token`` field);
        - if the field is ``required`` and still missing, raise a clear error
          instead of the value being silently dropped.

        No-op when the descriptor is None or declares no fields, so built-in
        platforms are unaffected.
        """
        fields = getattr(descriptor, "config_fields", None)
        if not fields:
            return self
        for spec in fields:
            name = getattr(spec, "name", None)
            if not name:
                continue
            current = getattr(self, name, None)
            if current in (None, ""):
                env_key = getattr(spec, "env", None)
                if env_key:
                    resolved = os.environ.get(env_key)
                    if resolved:
                        setattr(self, name, resolved)
                        current = resolved
            if getattr(spec, "required", False) and current in (None, ""):
                raise ValueError(
                    f"Missing required config field '{name}' for this channel. "
                    + (f"Set it in the config or via the '{getattr(spec, 'env', '')}' "
                       "environment variable." if getattr(spec, "env", None)
                       else "Set it in the channel config.")
                )
        return self


class RoutingConfigSchema(BaseModel):
    """Schema for agent routing configuration."""
    default: str = "assistant"
    rules: Dict[str, str] = Field(default_factory=dict)


class DaemonConfigSchema(BaseModel):
    """Schema for daemon/service configuration."""
    enabled: bool = False
    restart: str = "always"  # always, on_failure, never
    
    @field_validator("restart")
    @classmethod
    def validate_restart(cls, v: str) -> str:
        allowed = {"always", "on_failure", "never"}
        if v not in allowed:
            raise ValueError(f"Invalid restart policy '{v}'. Must be one of: {', '.join(sorted(allowed))}")
        return v


class HealthMonitorSchema(BaseModel):
    """Schema for the gateway channel health-monitor block (``gateway.health``).

    Mirrors the knobs read by ``gateway/server.py`` (via
    ``HealthMonitorConfig.from_dict``) so a misspelled threshold is caught at
    load time instead of silently falling back to the default.
    """
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    interval: float = Field(300.0, gt=0)
    startup_grace: float = Field(60.0, ge=0)
    stale_after: float = Field(120.0, gt=0)
    stuck_after: float = Field(900.0, gt=0)
    max_restarts_per_hour: int = Field(10, ge=0)


class GatewayServerSchema(BaseModel):
    """Typed schema for the ``gateway:`` server block (issue #3050).

    Replaces the previous opaque ``Dict[str, Any]`` so a misspelled or
    mistyped server knob (``drain_timout``, ``"10s"`` instead of ``10``) is
    rejected at load time with a friendly, field-named error instead of being
    silently dropped and running with the default. Field names/types/ranges
    mirror core's ``praisonaiagents.gateway.config.GatewayConfig`` so there is
    one definition of a gateway server setting.

    ``extra="forbid"`` surfaces unknown keys; ``hooks`` is validated as a
    nested list here too since the runtime accepts hooks nested under
    ``gateway:``.
    """
    model_config = ConfigDict(extra="forbid")

    host: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    bind_host: Optional[str] = None
    cors_origins: Optional[List[str]] = None
    allowed_origins: Optional[List[str]] = None
    auth_token: Optional[str] = None
    auth: Optional[Dict[str, Any]] = None
    auth_scopes: Optional[Dict[str, List[str]]] = None
    max_connections: Optional[int] = Field(None, ge=0)
    max_sessions_per_agent: Optional[int] = Field(None, ge=0)
    session_config: Optional[Dict[str, Any]] = None
    heartbeat_interval: Optional[int] = Field(None, ge=0)
    reconnect_timeout: Optional[int] = Field(None, ge=0)
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    max_buffered_bytes: Optional[int] = Field(None, ge=0)
    max_queued_frames: Optional[int] = Field(None, ge=0)
    # Admission control (#2454)
    max_concurrent_runs: Optional[int] = Field(None, ge=0)
    queue_depth: Optional[int] = Field(None, ge=0)
    overflow_policy: Optional[str] = None
    preauth_max_connections_per_ip: Optional[int] = Field(None, ge=0)
    max_unauthorized_frames: Optional[int] = Field(None, ge=0)
    # Graceful-drain windows (#2375 / #2533)
    drain_timeout: Optional[float] = Field(None, ge=0)
    reload_drain_timeout: Optional[float] = Field(None, ge=0)
    # Single-switch reliability preset (#2531)
    reliability: Optional[str] = None
    # Close-the-loop on permanently-undelivered replies (#3297). Opt-in; when
    # enabled a permanent delivery failure fires MESSAGE_UNDELIVERED and
    # best-effort sends a short plain-text notice on the same channel.
    notify_on_undelivered: Optional[bool] = None
    undelivered_template: Optional[str] = None
    # Additive protocol surfaces (#2715), liveness (#2798), health monitor
    api: Optional[Dict[str, Any]] = None
    liveness: Optional[Dict[str, Any]] = None
    health: Optional[HealthMonitorSchema] = None
    # Crash/shutdown forensics (#2436)
    forensics: Optional[Dict[str, Any]] = None
    # Hooks may be nested under ``gateway:`` for grouping
    hooks: Optional[List["HookSchema"]] = None

    @field_validator("overflow_policy")
    @classmethod
    def validate_overflow_policy(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("reject", "queue", "shed_oldest"):
            raise ValueError(
                "overflow_policy must be one of 'reject', 'queue', 'shed_oldest'"
            )
        return v


class HookSchema(BaseModel):
    """Schema for a single inbound trigger hook (``hooks:`` entries, #2281).

    Mirrors ``praisonaiagents.gateway.hooks.HookConfig``; ``extra="allow"``
    keeps free-form extras (folded into ``metadata`` by ``HookConfig.from_dict``)
    while still requiring a non-empty ``path`` and a valid ``action``.
    """
    model_config = ConfigDict(extra="allow")

    path: str
    agent: Optional[str] = None
    action: str = "agent"
    auth: Optional[str] = None
    session_key: Optional[str] = None
    idempotency_key: Optional[str] = None
    deliver_to: Optional[str] = None
    message: Optional[str] = None
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # Provider signature verification (#3165)
    secret: Optional[str] = None
    signature_header: Optional[str] = None
    signature_algo: str = "sha256"
    signature_prefix: Optional[str] = None
    # Event-type filtering (#3165)
    events: Optional[List[str]] = None
    event_header: Optional[str] = None
    # No-LLM pass-through delivery (#3165)
    deliver_only: bool = False

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: str) -> str:
        if not (v or "").strip().strip("/"):
            raise ValueError("hook 'path' must be a non-empty path segment")
        return v

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        allowed = {"agent", "wake"}
        if v not in allowed:
            raise ValueError(
                f"Invalid hook action '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v


# Resolve the forward reference to ``HookSchema`` in
# ``GatewayServerSchema.hooks`` now that ``HookSchema`` is defined.
GatewayServerSchema.model_rebuild()


class GatewayConfigSchema(BaseModel):
    """Unified schema for gateway.yaml/bot.yaml configuration.
    
    This is the canonical schema that supports all configuration patterns:
    - Single-bot bot.yaml (platform + token + agent)
    - Gateway gateway.yaml (agents dict + channels dict with routing)
    - BotOS config (agent + platforms dict)
    """
    # Top-level fields for single-bot compatibility
    platform: Optional[str] = None
    token: Optional[str] = None
    
    # Agent configuration (single or multiple)
    agent: Optional[AgentConfigSchema] = None
    agents: Optional[Dict[str, AgentConfigSchema]] = None
    
    # Channel configuration
    channels: Dict[str, ChannelConfigSchema] = Field(default_factory=dict)
    
    # Platform dict for BotOS compatibility
    platforms: Optional[Dict[str, Dict[str, Any]]] = None
    
    # Routing and daemon config
    routing: Optional[RoutingConfigSchema] = None
    daemon: Optional[DaemonConfigSchema] = None

    # Gateway server settings (host/port, drain_timeout, admission control,
    # etc.) and inbound trigger hooks. Kept as dicts/lists on this model so
    # downstream consumers (``gateway/server.py`` reads them via ``.get(...)``)
    # and existing dict-style access keep working, but validated field-by-field
    # in ``normalize_and_validate`` via ``GatewayServerSchema``/``HookSchema``
    # so a misspelled or mistyped server knob is rejected at load time with a
    # friendly, field-named error instead of being silently dropped (#3050).
    gateway: Optional[Dict[str, Any]] = None
    hooks: Optional[List[Dict[str, Any]]] = None
    
    @model_validator(mode="after")
    def normalize_and_validate(self):
        """Normalize different config formats to canonical form and validate."""
        # Validate the gateway server block + inbound hooks field-by-field
        # (#3050). These are stored as dicts for downstream dict access, but a
        # typo/wrong-type/out-of-range value must fail closed here instead of
        # silently running with the default. ``GatewayServerSchema`` forbids
        # unknown keys, so ``drain_timout`` names itself in the error.
        if self.gateway is not None:
            GatewayServerSchema(**self.gateway)
        if self.hooks is not None:
            for entry in self.hooks:
                HookSchema(**entry)
        # Migrate single-bot format (platform + token at top level)
        if self.platform and self.token and not self.channels:
            self.channels = {
                self.platform: ChannelConfigSchema(
                    platform=self.platform,
                    token=self.token
                )
            }
            
        # Migrate BotOS platforms format to channels
        if self.platforms and not self.channels:
            for platform_name, platform_config in self.platforms.items():
                self.channels[platform_name] = ChannelConfigSchema(
                    platform=platform_name,
                    **platform_config
                )
                
        # Ensure at least one channel is configured
        if not self.channels:
            raise ValueError(
                "No channels configured. Add at least one channel "
                "(telegram, discord, slack, whatsapp) to your config"
            )
            
        # Validate platform names against the platform registry (single source
        # of truth). This includes built-in platforms, entry-point discovered
        # channels (``praisonai.channels`` / ``praisonai.bots``), and any
        # channel registered at runtime via ``register_platform()``.
        try:
            from ._registry import list_platforms
            valid_platforms = set(list_platforms())
        except Exception:
            import logging
            logging.getLogger(__name__).debug(
                "Platform registry unavailable; falling back to built-in "
                "platform list.", exc_info=True
            )
            # Fall back to the built-in set (single source of truth) if the
            # registry is unavailable.
            try:
                from ._registry import _BUILTIN_PLATFORMS
                valid_platforms = set(_BUILTIN_PLATFORMS)
            except Exception:
                valid_platforms = {
                    "telegram", "discord", "slack", "whatsapp",
                    "email", "agentmail", "linear",
                }
        for name, channel in self.channels.items():
            platform = (channel.platform or name).lower()
            if platform not in valid_platforms:
                raise ValueError(
                    f"Unknown channel '{name}' (platform '{platform}'). "
                    f"Supported platforms: {', '.join(sorted(valid_platforms))}"
                )
                
        # Set platform if not explicitly set
        for name, channel in self.channels.items():
            if not channel.platform:
                channel.platform = name

        # Wire plugin-declared config fields (Issue #2801): a channel registered
        # with a descriptor can resolve env fallbacks and enforce its required
        # fields. Descriptor lookup is best-effort — built-in platforms without
        # a descriptor are unaffected.
        try:
            from ._registry import get_platform_descriptor
        except Exception:
            get_platform_descriptor = None
        if get_platform_descriptor is not None:
            for name, channel in self.channels.items():
                platform = (channel.platform or name).lower()
                try:
                    descriptor = get_platform_descriptor(platform)
                except Exception:
                    descriptor = None
                if descriptor is not None:
                    channel.apply_channel_descriptor(descriptor)

        return self


# Legacy alias for backward compatibility
BotYamlSchema = GatewayConfigSchema


def validate_gateway_config(raw: Dict[str, Any], apply_env_substitution: bool = True) -> GatewayConfigSchema:
    """Validate a raw YAML dict against the unified gateway config schema.
    
    Args:
        raw: Parsed YAML dictionary
        apply_env_substitution: Whether to apply ${VAR} substitution
        
    Returns:
        Validated GatewayConfigSchema
        
    Raises:
        ValueError: With human-friendly error messages
    """
    # Apply environment variable substitution if requested
    if apply_env_substitution:
        from praisonai_bot._code_bridge import import_code_module

        substitute_env_vars = import_code_module("praisonai_code.cli.utils.env_utils").substitute_env_vars
        raw = substitute_env_vars(raw)
        
    try:
        return GatewayConfigSchema(**raw)
    except Exception as e:
        # Re-raise with user-friendly message
        msg = str(e)
        # Strip pydantic internals for cleaner output
        if "validation error" in msg.lower():
            lines = msg.split("\n")
            clean_lines = [line for line in lines if line.strip() and not line.strip().startswith("For further")]
            msg = "\n".join(clean_lines)
        raise ValueError(f"Invalid gateway/bot configuration:\n{msg}") from None


def validate_bot_config(raw: Dict[str, Any]) -> GatewayConfigSchema:
    """Validate a raw YAML dict against the bot config schema.
    
    Legacy function for backward compatibility.
    
    Args:
        raw: Parsed YAML dictionary
        
    Returns:
        Validated GatewayConfigSchema
        
    Raises:
        ValueError: With human-friendly error messages
    """
    return validate_gateway_config(raw)


def load_and_validate_gateway_yaml(path: str, apply_env_substitution: bool = True) -> GatewayConfigSchema:
    """Load and validate a gateway.yaml or bot.yaml file.
    
    This is the canonical loader for all bot/gateway configurations.
    
    Args:
        path: Path to the YAML file
        apply_env_substitution: Whether to apply ${VAR} substitution
        
    Returns:
        Validated config schema
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If config is invalid
    """
    import yaml
    
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"Run 'praisonai onboard' to create one, or create it manually."
        )
    
    # Load env file if not already loaded
    from praisonai_bot._code_bridge import import_code_module

    load_env_file = import_code_module("praisonai_code.cli.utils.env_utils").load_env_file
    load_env_file()
    
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    
    return validate_gateway_config(raw, apply_env_substitution)


def load_and_validate_bot_yaml(path: str) -> GatewayConfigSchema:
    """Load and validate a bot.yaml file.
    
    Legacy function for backward compatibility.
    
    Args:
        path: Path to the YAML file
        
    Returns:
        Validated config schema
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If config is invalid
    """
    return load_and_validate_gateway_yaml(path)


def migrate_legacy_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate legacy configuration formats to the canonical schema.
    
    Handles migration from:
    - Old single-bot format (top-level platform/token)
    - Old BotOS format (platforms dict)
    - Old gateway format (missing security defaults)
    
    Args:
        raw: Raw configuration dictionary
        
    Returns:
        Migrated configuration dictionary
    """
    migrated = dict(raw)
    
    # Log migrations for transparency
    migrations = []
    
    # Migrate old allowed_users string to list
    if "channels" in migrated:
        for channel_name, channel in migrated["channels"].items():
            if isinstance(channel.get("allowed_users"), str):
                old_value = channel["allowed_users"]
                if old_value:
                    channel["allowed_users"] = [u.strip() for u in old_value.split(",") if u.strip()]
                else:
                    channel["allowed_users"] = []
                migrations.append(f"Migrated {channel_name}.allowed_users from string to list")
                
            # Set secure defaults if not specified
            if "group_policy" not in channel:
                channel["group_policy"] = "mention_only"
                migrations.append(f"Set {channel_name}.group_policy to secure default 'mention_only'")
                
    # Log any migrations performed
    if migrations:
        logger.info(f"Config migrations applied: {'; '.join(migrations)}")
        
    return migrated
