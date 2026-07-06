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
    # Push protocols and dataclasses
    PushChannelProtocol,
    PresenceProtocol,
    DeliveryGuaranteeProtocol,
    OutboundDeliveryProtocol,
    ChannelInfo,
    PresenceInfo,
    # Home channel and delivery protocols
    HomeChannelRegistryProtocol,
    DeliveryResolverProtocol,
    # Agent-facing outbound messaging
    OutboundMessengerProtocol,
    DeliveryResult,
    TargetInfo,
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
    # Gateway graceful-drain on shutdown (Issue #2375)
    DrainDecision,
    GatewayDrainPolicyProtocol,
    DrainTimeoutPolicy,
    # Gateway inbound admission control (Issue #2454)
    AdmissionDecision,
    GatewayConcurrencyPolicyProtocol,
    GatewayConcurrencyPolicy,  # backward-compat alias
    ConcurrencyLimitPolicy,
    # Gateway rate-limit admission (Issue #2532)
    RateLimitDecision,
    RateLimitPolicyProtocol,
    RateLimitPolicy,  # backward-compat alias
    SlidingWindowRateLimitPolicy,
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
)
from .hooks import (
    HookAction,
    HookConfig,
    InboundTriggerProtocol,
    render_template,
    compute_idempotency_key,
)
from .config import (
    GatewayConfig,
    SessionConfig,
    ChannelRouteConfig,
    MultiChannelGatewayConfig,
    # Push config
    PushConfig,
    RedisConfig,
    PresenceConfig,
    DeliveryConfig,
    PollingConfig,
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
    # Push protocols (always available)
    "PushChannelProtocol",
    "PresenceProtocol",
    "DeliveryGuaranteeProtocol",
    "OutboundDeliveryProtocol",
    "ChannelInfo",
    "PresenceInfo",
    # Home channel and delivery protocols
    "HomeChannelRegistryProtocol",
    "DeliveryResolverProtocol",
    # Agent-facing outbound messaging
    "OutboundMessengerProtocol",
    "DeliveryResult",
    "TargetInfo",
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
    "DrainDecision",
    "GatewayDrainPolicyProtocol",
    "DrainTimeoutPolicy",
    # Gateway inbound admission control (Issue #2454)
    "AdmissionDecision",
    "GatewayConcurrencyPolicyProtocol",
    "GatewayConcurrencyPolicy",
    "ConcurrencyLimitPolicy",
    # Gateway rate-limit admission (Issue #2532)
    "RateLimitDecision",
    "RateLimitPolicyProtocol",
    "RateLimitPolicy",
    "SlidingWindowRateLimitPolicy",
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
    # Inbound trigger / webhook contract (Issue #2281)
    "HookAction",
    "HookConfig",
    "InboundTriggerProtocol",
    "render_template",
    "compute_idempotency_key",
    # Config (always available)
    "GatewayConfig",
    "SessionConfig",
    "ChannelRouteConfig",
    "MultiChannelGatewayConfig",
    "PushConfig",
    "RedisConfig",
    "PresenceConfig",
    "DeliveryConfig",
    "PollingConfig",
    # Implementations (lazy loaded from praisonai wrapper)
    "WebSocketGateway",
    "GatewaySession",
]
