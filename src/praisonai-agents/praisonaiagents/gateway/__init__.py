"""
Gateway module for PraisonAI Agents.

Provides protocols and base classes for building gateway/control plane
implementations that coordinate multi-agent deployments.

This module contains only protocols and lightweight utilities.
Heavy implementations live in the praisonai wrapper package.

Gap S2: WebSocketGateway is re-exported here for convenience but requires
the praisonai wrapper package to be installed.
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
    # Protocol version negotiation
    PROTOCOL_VERSION,
    MIN_PROTOCOL_VERSION,
    MAX_PROTOCOL_VERSION,
    ProtocolHello,
    ProtocolHelloOk,
    GapInfo,
    ResumeSnapshot,
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
    """Lazy load heavy gateway implementations from praisonai wrapper.
    
    Gap S2: Re-export WebSocketGateway from praisonai wrapper for convenience.
    This allows downstream packages to import from praisonaiagents.gateway
    without needing to know about the praisonai wrapper.
    """
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "WebSocketGateway":
        try:
            from praisonai.gateway import WebSocketGateway
            _lazy_cache[name] = WebSocketGateway
            return WebSocketGateway
        except ImportError:
            raise ImportError(
                "WebSocketGateway requires the praisonai wrapper package. "
                "Install with: pip install praisonai"
            )
    
    if name == "GatewaySession":
        try:
            from praisonai.gateway import GatewaySession
            _lazy_cache[name] = GatewaySession
            return GatewaySession
        except ImportError:
            raise ImportError(
                "GatewaySession requires the praisonai wrapper package. "
                "Install with: pip install praisonai"
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
    # Protocol version negotiation
    "PROTOCOL_VERSION",
    "MIN_PROTOCOL_VERSION",
    "MAX_PROTOCOL_VERSION",
    "ProtocolHello",
    "ProtocolHelloOk",
    "GapInfo",
    "ResumeSnapshot",
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
