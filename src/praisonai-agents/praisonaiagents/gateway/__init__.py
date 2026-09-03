"""
Gateway module for PraisonAI Agents.

Provides protocols and base classes for building gateway/control plane
implementations that coordinate multi-agent deployments.

This module contains only protocols and lightweight utilities.
Heavy implementations live in the ``praisonai-bot`` package (C9); the
``praisonai`` wrapper re-exports them for full-stack installs.

Gap S2: WebSocketGateway is re-exported here for convenience but requires
``praisonai-bot`` (or ``pip install praisonai``) to be installed.
"""

from .protocols import (
    GatewayProtocol,
    GatewaySessionProtocol,
    GatewayClientProtocol,
    GatewayEvent,
    GatewayMessage,
    EventType,
    OperatorScope,
    GatewayCloseCode,
    # Declarative method -> required-scope registry (Issue #3206)
    GatewayMethodDescriptor,
    GATEWAY_METHODS,
    register_gateway_method,
    resolve_required_scope,
    # Config hot-reload observability (Issue #3049)
    ReloadStatus,
    compute_config_revision,
    # Saturation / back-pressure observability (Issue #4265)
    HealthPressure,
    evaluate_pressure,
    # Push protocols and dataclasses
    PushChannelProtocol,
    PresenceProtocol,
    DeliveryGuaranteeProtocol,
    OutboundDeliveryProtocol,
    IdempotencyStoreProtocol,
    InMemoryIdempotencyStore,
    ChannelInfo,
    PresenceInfo,
    # Home channel and delivery protocols
    HomeChannelRegistryProtocol,
    DeliveryResolverProtocol,
    # Creation-time delivery-target pre-flight (Issue #3800)
    DeliveryPreflightProtocol,
    DeliveryValidation,
    ScheduleTargetError,
    # Agent-facing outbound messaging
    OutboundMessengerProtocol,
    DeliveryResult,
    TargetInfo,
    # Agent-callable message reactions (Issue #3917)
    ReactionResult,
    ReactionStatus,
    # Agent/gateway-callable thread creation (Issue #3987)
    ThreadResult,
    ThreadStatus,
    # Agent-callable cross-conversation request/reply (Issue #3689)
    ConversationReply,
    ConversationReplyStatus,
    ConversationRequestProtocol,
    # Agent-facing live status/health (Issue #3688)
    GatewayStatusProtocol,
    GatewayStatus,
    # Inbound route binding (Issue #2225)
    RouteBinding,
    RouteFacts,
    RouteMatch,
    resolve_route,
    # Per-route, trust-tiered toolset scoping (Issue #2298)
    ToolPolicy,
    UNTRUSTED_DENY_SUBSTRINGS,
    TRUST_TIERS,
    # Outbound send-policy guard (Issue #2226)
    SendDecision,
    SendPolicyProtocol,
    SendPolicy,
    # Gateway idle-dormancy / scale-to-zero (Issue #2332)
    IdleDecision,
    GatewayIdlePolicyProtocol,
    GatewayIdlePolicy,  # backward-compat alias
    ScaleToZeroPolicy,
    # Gateway freeze-thaw (involuntary host-suspend gap) recovery (Issue #4767)
    ThawDecision,
    ThawPolicyProtocol,
    WallClockGapThawPolicy,
    # Gateway graceful-drain on shutdown (Issue #2375)
    DrainDecision,
    GatewayDrainPolicyProtocol,
    DrainTimeoutPolicy,
    # Gateway inbound admission control (Issue #2454)
    AdmissionDecision,
    GatewayConcurrencyPolicyProtocol,
    GatewayConcurrencyPolicy,  # backward-compat alias
    ConcurrencyLimitPolicy,
    # Gateway resource-pressure admission (Issue #3445)
    ResourceSample,
    ResourcePressurePolicyProtocol,
    MemoryPressurePolicy,
    # Gateway memory-pressure cache eviction (Issue #3804)
    WarmSession,
    MemoryPressureProtocol,
    plan_pressure_evictions,
    # Gateway rate-limit admission (Issue #2532)
    RateLimitDecision,
    RateLimitPolicyProtocol,
    RateLimitPolicy,  # backward-compat alias
    SlidingWindowRateLimitPolicy,
    # Durable-queue dead-letter decision (Issue #3519)
    PERMANENT_ERROR_CLASSES,
    DeadLetterDecision,
    DeadLetterPolicyProtocol,
    AttemptAndAgeDeadLetterPolicy,
    # Port-less, restart-safe external drain trigger (Issue #2390)
    current_epoch,
    DrainMarkerPolicy,
    # Crash / shutdown forensics (Issue #2436)
    ShutdownForensicsProtocol,
    format_forensics_for_log,
    is_supervised,
    drain_timeout_has_headroom,
    # Code-skew guard for hot operations (Issue #2460)
    detect_code_skew,
    # Restart-intent exit-code protocol (Issue #2437)
    GATEWAY_OK_EXIT_CODE,
    GATEWAY_RESTART_EXIT_CODE,
    GATEWAY_FATAL_CONFIG_EXIT_CODE,
    FatalConfigError,
    classify_exit_reason,
    RestartLoopGuard,
    # Durable process-lifecycle record + unclean/OOM classification (Issue #4603)
    LifecycleRecord,
    classify_unclean_exit,
    RestartStoreProtocol,
    PersistentRestartLoopGuard,
    classify_resource_pressure,
    # Fleet-level crash-loop breaker for channel supervision (Issue #3840)
    FleetSupervisionPolicy,
    # Protocol version negotiation
    PROTOCOL_VERSION,
    MIN_PROTOCOL_VERSION,
    MAX_PROTOCOL_VERSION,
    ProtocolHello,
    ProtocolHelloOk,
    GapInfo,
    ResumeSnapshot,
    # Out-of-process platform-connector relay (Issue #2485)
    CapabilityDescriptor,
    RelayTransport,
    # Gateway pipeline span-tracing seam (Issue #2716)
    GATEWAY_TRACE_STAGES,
    GatewayTraceHook,
    NullGatewayTraceHook,
    NULL_GATEWAY_TRACE_HOOK,
    resolve_trace_hook,
    # Gateway self-lifecycle command guardrail (Issue #2753)
    LifecycleCommandDecision,
    LifecycleCommandPolicyProtocol,
    LifecycleCommandPolicy,  # backward-compat alias
    LifecycleCommandGuardPolicy,
    # Application-level connection liveness (Issue #2798)
    LivenessDecision,
    LivenessPolicyProtocol,
    LivenessPolicy,
    # Cluster-wide per-turn serialisation (Issue #3643)
    TurnLeaseToken,
    TurnLockProtocol,
    LocalTurnLock,
    # Per-session turn-execution isolation (Issue #4011)
    WorkerWedgedError,
    TurnPlacement,
    TurnExecutorProtocol,
    InProcessTurnExecutor,
    # Global operator emergency-stop / pause brake (Issue #4220)
    EmergencyStopState,
    EmergencyStopProtocol,
    NullEmergencyStop,
    FileEmergencyStop,
    # Schema-validated inbound frame codec (Issue #2831)
    HelloParams,
    HelloResult,
    HelloError,
    ConnectErrorCode,
    ConnectRecoveryStep,
    is_recoverable,
    MessageParams,
    LeaveParams,
    JoinParams,
    FrameDecodeError,
    ClientFrame,
    decode_client_frame,
    # Weak / placeholder secret guard (Issue #3259)
    KNOWN_WEAK_SECRETS,
    WeakGatewaySecretError,
    is_weak_secret,
    assert_gateway_secret_strong,
    # Per-platform identity canonicalization (Issue #3886)
    IdentityCanonicalizerProtocol,
)
from .liveness import (
    # Event-loop liveness watchdog (Issue #3385)
    LoopWatchdogPolicy,
    LoopWatchdog,
)
from .degraded_state import (
    # Unified degraded-capability registry (Issue #3518)
    DegradedOwner,
    DegradedCapabilityProtocol,
    DegradedCapabilityRegistry,
    OWNER_KINDS,
    DEGRADED_STATES,
    # Fail-closed read of the degraded-owner contract (Issue #3640)
    DegradedCapabilityLookupProtocol,
    OwnerUnavailable,
    assert_owner_available,
)
from .hooks import (
    HookAction,
    HookConfig,
    InboundTriggerProtocol,
    render_template,
    compute_idempotency_key,
    verify_webhook_signature,
)
from .config import (
    GatewayConfig,
    SessionConfig,
    ApiConfig,
    EmergencyStopConfig,
    ChannelRouteConfig,
    MultiChannelGatewayConfig,
    # Config version stamp + doctor-driven migration (Issue #3841)
    GATEWAY_CONFIG_VERSION,
    ConfigVersionError,
    LegacyConfigRule,
    GATEWAY_CONFIG_RULES,
    is_config_current,
    migrate_config_with_doctor,
    # Push config
    PushConfig,
    RedisConfig,
    PresenceConfig,
    DeliveryConfig,
    PollingConfig,
    LivenessConfig,
    TurnLockConfig,
    # Hot-reload registry (Issue #3378)
    HOT_APPLIABLE_KEYS,
    SupportsHotReload,
    is_hot_appliable,
    # Reload scope classification (Issue #3440)
    ReloadScope,
    classify_reload,
)

# Lazy loading cache
_lazy_cache = {}


def __getattr__(name: str):
    """Lazy load heavy gateway implementations from praisonai-bot (C9).

    Gap S2: Re-export WebSocketGateway for convenience. Prefer
    ``praisonai_bot.gateway`` or ``pip install praisonai`` for full stack.
    """
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "WebSocketGateway":
        try:
            from praisonai_bot.gateway import WebSocketGateway
            _lazy_cache[name] = WebSocketGateway
            return WebSocketGateway
        except ImportError:
            pass
        try:
            from praisonai.gateway import WebSocketGateway
            _lazy_cache[name] = WebSocketGateway
            return WebSocketGateway
        except ImportError:
            raise ImportError(
                "WebSocketGateway requires praisonai-bot or praisonai. "
                "Install with: pip install praisonai-bot or pip install praisonai"
            )

    if name == "GatewaySession":
        try:
            from praisonai_bot.gateway import GatewaySession
            _lazy_cache[name] = GatewaySession
            return GatewaySession
        except ImportError:
            pass
        try:
            from praisonai.gateway import GatewaySession
            _lazy_cache[name] = GatewaySession
            return GatewaySession
        except ImportError:
            raise ImportError(
                "GatewaySession requires praisonai-bot or praisonai. "
                "Install with: pip install praisonai-bot or pip install praisonai"
            )
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Protocols (always available)
    "GatewayProtocol",
    "GatewaySessionProtocol",
    "GatewayClientProtocol",
    "GatewayEvent",
    "GatewayMessage",
    "EventType",
    "OperatorScope",
    "GatewayCloseCode",
    # Declarative method -> required-scope registry (Issue #3206)
    "GatewayMethodDescriptor",
    "GATEWAY_METHODS",
    "register_gateway_method",
    "resolve_required_scope",
    # Config hot-reload observability (Issue #3049)
    "ReloadStatus",
    "compute_config_revision",
    "HealthPressure",
    "evaluate_pressure",
    # Push protocols (always available)
    "PushChannelProtocol",
    "PresenceProtocol",
    "DeliveryGuaranteeProtocol",
    "OutboundDeliveryProtocol",
    "IdempotencyStoreProtocol",
    "InMemoryIdempotencyStore",
    "ChannelInfo",
    "PresenceInfo",
    # Home channel and delivery protocols
    "HomeChannelRegistryProtocol",
    "DeliveryResolverProtocol",
    "DeliveryPreflightProtocol",
    "DeliveryValidation",
    "ScheduleTargetError",
    # Agent-facing outbound messaging
    "OutboundMessengerProtocol",
    "DeliveryResult",
    "TargetInfo",
    "ReactionResult",
    "ReactionStatus",
    "ThreadResult",
    "ThreadStatus",
    # Agent-callable cross-conversation request/reply (Issue #3689)
    "ConversationReply",
    "ConversationReplyStatus",
    "ConversationRequestProtocol",
    # Agent-facing live status/health (Issue #3688)
    "GatewayStatusProtocol",
    "GatewayStatus",
    # Inbound route binding (Issue #2225)
    "RouteBinding",
    "RouteFacts",
    "RouteMatch",
    "resolve_route",
    # Per-route, trust-tiered toolset scoping (Issue #2298)
    "ToolPolicy",
    "UNTRUSTED_DENY_SUBSTRINGS",
    "TRUST_TIERS",
    # Outbound send-policy guard (Issue #2226)
    "SendDecision",
    "SendPolicyProtocol",
    "SendPolicy",
    # Gateway idle-dormancy / scale-to-zero (Issue #2332)
    "IdleDecision",
    "GatewayIdlePolicyProtocol",
    "GatewayIdlePolicy",
    "ScaleToZeroPolicy",
    # Gateway freeze-thaw (involuntary host-suspend gap) recovery (Issue #4767)
    "ThawDecision",
    "ThawPolicyProtocol",
    "WallClockGapThawPolicy",
    "DrainDecision",
    "GatewayDrainPolicyProtocol",
    "DrainTimeoutPolicy",
    # Gateway inbound admission control (Issue #2454)
    "AdmissionDecision",
    "GatewayConcurrencyPolicyProtocol",
    "GatewayConcurrencyPolicy",
    "ConcurrencyLimitPolicy",
    # Gateway resource-pressure admission (Issue #3445)
    "ResourceSample",
    "ResourcePressurePolicyProtocol",
    "MemoryPressurePolicy",
    # Gateway memory-pressure cache eviction (Issue #3804)
    "WarmSession",
    "MemoryPressureProtocol",
    "plan_pressure_evictions",
    # Gateway rate-limit admission (Issue #2532)
    "RateLimitDecision",
    "RateLimitPolicyProtocol",
    "RateLimitPolicy",
    "SlidingWindowRateLimitPolicy",
    # Durable-queue dead-letter decision (Issue #3519)
    "PERMANENT_ERROR_CLASSES",
    "DeadLetterDecision",
    "DeadLetterPolicyProtocol",
    "AttemptAndAgeDeadLetterPolicy",
    # Port-less, restart-safe external drain trigger (Issue #2390)
    "current_epoch",
    "DrainMarkerPolicy",
    # Crash / shutdown forensics (Issue #2436)
    "ShutdownForensicsProtocol",
    "format_forensics_for_log",
    "is_supervised",
    "drain_timeout_has_headroom",
    # Code-skew guard for hot operations (Issue #2460)
    "detect_code_skew",
    # Restart-intent exit-code protocol (Issue #2437)
    "GATEWAY_OK_EXIT_CODE",
    "GATEWAY_RESTART_EXIT_CODE",
    "GATEWAY_FATAL_CONFIG_EXIT_CODE",
    "FatalConfigError",
    "classify_exit_reason",
    "RestartLoopGuard",
    # Durable process-lifecycle record + unclean/OOM classification (Issue #4603)
    "LifecycleRecord",
    "classify_unclean_exit",
    "RestartStoreProtocol",
    "PersistentRestartLoopGuard",
    "classify_resource_pressure",
    # Fleet-level crash-loop breaker for channel supervision (Issue #3840)
    "FleetSupervisionPolicy",
    # Protocol version negotiation
    "PROTOCOL_VERSION",
    "MIN_PROTOCOL_VERSION",
    "MAX_PROTOCOL_VERSION",
    "ProtocolHello",
    "ProtocolHelloOk",
    "GapInfo",
    "ResumeSnapshot",
    # Out-of-process platform-connector relay (Issue #2485)
    "CapabilityDescriptor",
    "RelayTransport",
    # Gateway pipeline span-tracing seam (Issue #2716)
    "GATEWAY_TRACE_STAGES",
    "GatewayTraceHook",
    "NullGatewayTraceHook",
    "NULL_GATEWAY_TRACE_HOOK",
    "resolve_trace_hook",
    # Gateway self-lifecycle command guardrail (Issue #2753)
    "LifecycleCommandDecision",
    "LifecycleCommandPolicyProtocol",
    "LifecycleCommandPolicy",
    "LifecycleCommandGuardPolicy",
    # Application-level connection liveness (Issue #2798)
    "LivenessDecision",
    "LivenessPolicyProtocol",
    "LivenessPolicy",
    # Cluster-wide per-turn serialisation (Issue #3643)
    "TurnLeaseToken",
    "TurnLockProtocol",
    "LocalTurnLock",
    # Per-session turn-execution isolation (Issue #4011)
    "WorkerWedgedError",
    "TurnPlacement",
    "TurnExecutorProtocol",
    "InProcessTurnExecutor",
    # Global operator emergency-stop / pause brake (Issue #4220)
    "EmergencyStopState",
    "EmergencyStopProtocol",
    "NullEmergencyStop",
    "FileEmergencyStop",
    # Schema-validated inbound frame codec (Issue #2831)
    "HelloParams",
    "HelloResult",
    "HelloError",
    "ConnectErrorCode",
    "ConnectRecoveryStep",
    "is_recoverable",
    "MessageParams",
    "LeaveParams",
    "JoinParams",
    "FrameDecodeError",
    "ClientFrame",
    "decode_client_frame",
    # Weak / placeholder secret guard (Issue #3259)
    "KNOWN_WEAK_SECRETS",
    "WeakGatewaySecretError",
    "is_weak_secret",
    "assert_gateway_secret_strong",
    # Per-platform identity canonicalization (Issue #3886)
    "IdentityCanonicalizerProtocol",
    # Event-loop liveness watchdog (Issue #3385)
    "LoopWatchdogPolicy",
    "LoopWatchdog",
    # Unified degraded-capability registry (Issue #3518)
    "DegradedOwner",
    "DegradedCapabilityProtocol",
    "DegradedCapabilityRegistry",
    "OWNER_KINDS",
    "DEGRADED_STATES",
    # Fail-closed read of the degraded-owner contract (Issue #3640)
    "DegradedCapabilityLookupProtocol",
    "OwnerUnavailable",
    "assert_owner_available",
    # Inbound trigger / webhook contract (Issue #2281)
    "HookAction",
    "HookConfig",
    "InboundTriggerProtocol",
    "render_template",
    "compute_idempotency_key",
    "verify_webhook_signature",
    # Config (always available)
    "GatewayConfig",
    "SessionConfig",
    "ApiConfig",
    "EmergencyStopConfig",
    "ChannelRouteConfig",
    "MultiChannelGatewayConfig",
    # Config version stamp + doctor-driven migration (Issue #3841)
    "GATEWAY_CONFIG_VERSION",
    "ConfigVersionError",
    "LegacyConfigRule",
    "GATEWAY_CONFIG_RULES",
    "is_config_current",
    "migrate_config_with_doctor",
    "PushConfig",
    "RedisConfig",
    "PresenceConfig",
    "DeliveryConfig",
    "PollingConfig",
    "LivenessConfig",
    "TurnLockConfig",
    # Hot-reload registry (Issue #3378)
    "HOT_APPLIABLE_KEYS",
    "SupportsHotReload",
    "is_hot_appliable",
    "ReloadScope",
    "classify_reload",
    # Implementations (lazy loaded from praisonai wrapper)
    "WebSocketGateway",
    "GatewaySession",
]
