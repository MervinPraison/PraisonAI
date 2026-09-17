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

from .._lazy import create_lazy_getattr

# Lazy import map: symbol -> (submodule, attr). Deferring these keeps the
# 283 KB / 7,201-line ``protocols.py`` (and siblings) out of package-import
# time; each submodule is parsed only when one of its symbols is first
# touched. Mirrors the ``mcp``/``skills`` packages (AGENTS.md §4.2).
_LAZY_IMPORTS = {
    # protocols.py (parsed lazily, on first touch)
    "GatewayProtocol": ("praisonaiagents.gateway.protocols", "GatewayProtocol"),
    "GatewaySessionProtocol": ("praisonaiagents.gateway.protocols", "GatewaySessionProtocol"),
    "GatewayClientProtocol": ("praisonaiagents.gateway.protocols", "GatewayClientProtocol"),
    "GatewayEvent": ("praisonaiagents.gateway.protocols", "GatewayEvent"),
    "GatewayMessage": ("praisonaiagents.gateway.protocols", "GatewayMessage"),
    "EventType": ("praisonaiagents.gateway.protocols", "EventType"),
    "OperatorScope": ("praisonaiagents.gateway.protocols", "OperatorScope"),
    "GatewayCloseCode": ("praisonaiagents.gateway.protocols", "GatewayCloseCode"),
    # Declarative method -> required-scope registry (Issue #3206)
    "GatewayMethodDescriptor": ("praisonaiagents.gateway.protocols", "GatewayMethodDescriptor"),
    "GATEWAY_METHODS": ("praisonaiagents.gateway.protocols", "GATEWAY_METHODS"),
    "register_gateway_method": ("praisonaiagents.gateway.protocols", "register_gateway_method"),
    "resolve_required_scope": ("praisonaiagents.gateway.protocols", "resolve_required_scope"),
    # Config hot-reload observability (Issue #3049)
    "ReloadStatus": ("praisonaiagents.gateway.protocols", "ReloadStatus"),
    "compute_config_revision": ("praisonaiagents.gateway.protocols", "compute_config_revision"),
    # Saturation / back-pressure observability (Issue #4265)
    "HealthPressure": ("praisonaiagents.gateway.protocols", "HealthPressure"),
    "evaluate_pressure": ("praisonaiagents.gateway.protocols", "evaluate_pressure"),
    # Push protocols and dataclasses
    "PushChannelProtocol": ("praisonaiagents.gateway.protocols", "PushChannelProtocol"),
    "PresenceProtocol": ("praisonaiagents.gateway.protocols", "PresenceProtocol"),
    "DeliveryGuaranteeProtocol": ("praisonaiagents.gateway.protocols", "DeliveryGuaranteeProtocol"),
    "OutboundDeliveryProtocol": ("praisonaiagents.gateway.protocols", "OutboundDeliveryProtocol"),
    "IdempotencyStoreProtocol": ("praisonaiagents.gateway.protocols", "IdempotencyStoreProtocol"),
    "InMemoryIdempotencyStore": ("praisonaiagents.gateway.protocols", "InMemoryIdempotencyStore"),
    "ChannelInfo": ("praisonaiagents.gateway.protocols", "ChannelInfo"),
    "PresenceInfo": ("praisonaiagents.gateway.protocols", "PresenceInfo"),
    # Home channel and delivery protocols
    "HomeChannelRegistryProtocol": ("praisonaiagents.gateway.protocols", "HomeChannelRegistryProtocol"),
    "DeliveryResolverProtocol": ("praisonaiagents.gateway.protocols", "DeliveryResolverProtocol"),
    # Creation-time delivery-target pre-flight (Issue #3800)
    "DeliveryPreflightProtocol": ("praisonaiagents.gateway.protocols", "DeliveryPreflightProtocol"),
    "DeliveryValidation": ("praisonaiagents.gateway.protocols", "DeliveryValidation"),
    "ScheduleTargetError": ("praisonaiagents.gateway.protocols", "ScheduleTargetError"),
    # Remote-sandbox outbound media bridge (Issue #4951)
    "RemoteMediaResolver": ("praisonaiagents.gateway.protocols", "RemoteMediaResolver"),
    # Agent-facing outbound messaging
    "OutboundMessengerProtocol": ("praisonaiagents.gateway.protocols", "OutboundMessengerProtocol"),
    "DeliveryResult": ("praisonaiagents.gateway.protocols", "DeliveryResult"),
    "TargetInfo": ("praisonaiagents.gateway.protocols", "TargetInfo"),
    # Agent-callable message reactions (Issue #3917)
    "ReactionResult": ("praisonaiagents.gateway.protocols", "ReactionResult"),
    "ReactionStatus": ("praisonaiagents.gateway.protocols", "ReactionStatus"),
    # Agent/gateway-callable thread creation (Issue #3987)
    "ThreadResult": ("praisonaiagents.gateway.protocols", "ThreadResult"),
    "ThreadStatus": ("praisonaiagents.gateway.protocols", "ThreadStatus"),
    # Agent-callable cross-conversation request/reply (Issue #3689)
    "ConversationReply": ("praisonaiagents.gateway.protocols", "ConversationReply"),
    "ConversationReplyStatus": ("praisonaiagents.gateway.protocols", "ConversationReplyStatus"),
    "ConversationRequestProtocol": ("praisonaiagents.gateway.protocols", "ConversationRequestProtocol"),
    # Agent-facing live status/health (Issue #3688)
    "GatewayStatusProtocol": ("praisonaiagents.gateway.protocols", "GatewayStatusProtocol"),
    "GatewayStatus": ("praisonaiagents.gateway.protocols", "GatewayStatus"),
    # Inbound route binding (Issue #2225)
    "RouteBinding": ("praisonaiagents.gateway.protocols", "RouteBinding"),
    "RouteFacts": ("praisonaiagents.gateway.protocols", "RouteFacts"),
    "RouteMatch": ("praisonaiagents.gateway.protocols", "RouteMatch"),
    "resolve_route": ("praisonaiagents.gateway.protocols", "resolve_route"),
    # Per-route, trust-tiered toolset scoping (Issue #2298)
    "ToolPolicy": ("praisonaiagents.gateway.protocols", "ToolPolicy"),
    "UNTRUSTED_DENY_SUBSTRINGS": ("praisonaiagents.gateway.protocols", "UNTRUSTED_DENY_SUBSTRINGS"),
    "TRUST_TIERS": ("praisonaiagents.gateway.protocols", "TRUST_TIERS"),
    # Outbound send-policy guard (Issue #2226)
    "SendDecision": ("praisonaiagents.gateway.protocols", "SendDecision"),
    "SendPolicyProtocol": ("praisonaiagents.gateway.protocols", "SendPolicyProtocol"),
    "SendPolicy": ("praisonaiagents.gateway.protocols", "SendPolicy"),
    # Gateway idle-dormancy / scale-to-zero (Issue #2332)
    "IdleDecision": ("praisonaiagents.gateway.protocols", "IdleDecision"),
    "GatewayIdlePolicyProtocol": ("praisonaiagents.gateway.protocols", "GatewayIdlePolicyProtocol"),
    "GatewayIdlePolicy": ("praisonaiagents.gateway.protocols", "GatewayIdlePolicy"),
    "ScaleToZeroPolicy": ("praisonaiagents.gateway.protocols", "ScaleToZeroPolicy"),
    # Gateway freeze-thaw (involuntary host-suspend gap) recovery (Issue #4767)
    "ThawDecision": ("praisonaiagents.gateway.protocols", "ThawDecision"),
    "ThawPolicyProtocol": ("praisonaiagents.gateway.protocols", "ThawPolicyProtocol"),
    "WallClockGapThawPolicy": ("praisonaiagents.gateway.protocols", "WallClockGapThawPolicy"),
    # Gateway graceful-drain on shutdown (Issue #2375)
    "DrainDecision": ("praisonaiagents.gateway.protocols", "DrainDecision"),
    "GatewayDrainPolicyProtocol": ("praisonaiagents.gateway.protocols", "GatewayDrainPolicyProtocol"),
    "DrainTimeoutPolicy": ("praisonaiagents.gateway.protocols", "DrainTimeoutPolicy"),
    # Gateway inbound admission control (Issue #2454)
    "AdmissionDecision": ("praisonaiagents.gateway.protocols", "AdmissionDecision"),
    "GatewayConcurrencyPolicyProtocol": ("praisonaiagents.gateway.protocols", "GatewayConcurrencyPolicyProtocol"),
    "GatewayConcurrencyPolicy": ("praisonaiagents.gateway.protocols", "GatewayConcurrencyPolicy"),
    "ConcurrencyLimitPolicy": ("praisonaiagents.gateway.protocols", "ConcurrencyLimitPolicy"),
    # Gateway resource-pressure admission (Issue #3445)
    "ResourceSample": ("praisonaiagents.gateway.protocols", "ResourceSample"),
    "ResourcePressurePolicyProtocol": ("praisonaiagents.gateway.protocols", "ResourcePressurePolicyProtocol"),
    "MemoryPressurePolicy": ("praisonaiagents.gateway.protocols", "MemoryPressurePolicy"),
    # Gateway memory-pressure cache eviction (Issue #3804)
    "WarmSession": ("praisonaiagents.gateway.protocols", "WarmSession"),
    "MemoryPressureProtocol": ("praisonaiagents.gateway.protocols", "MemoryPressureProtocol"),
    "plan_pressure_evictions": ("praisonaiagents.gateway.protocols", "plan_pressure_evictions"),
    # Gateway rate-limit admission (Issue #2532)
    "RateLimitDecision": ("praisonaiagents.gateway.protocols", "RateLimitDecision"),
    "RateLimitPolicyProtocol": ("praisonaiagents.gateway.protocols", "RateLimitPolicyProtocol"),
    "RateLimitPolicy": ("praisonaiagents.gateway.protocols", "RateLimitPolicy"),
    "SlidingWindowRateLimitPolicy": ("praisonaiagents.gateway.protocols", "SlidingWindowRateLimitPolicy"),
    # Gateway cost-aware spend-budget admission (Issue #4894)
    "SpendBudgetPolicyProtocol": ("praisonaiagents.gateway.protocols", "SpendBudgetPolicyProtocol"),
    "SpendBudgetPolicy": ("praisonaiagents.gateway.protocols", "SpendBudgetPolicy"),
    "WindowedSpendBudgetPolicy": ("praisonaiagents.gateway.protocols", "WindowedSpendBudgetPolicy"),
    # Durable-queue dead-letter decision (Issue #3519)
    "PERMANENT_ERROR_CLASSES": ("praisonaiagents.gateway.protocols", "PERMANENT_ERROR_CLASSES"),
    "DeadLetterDecision": ("praisonaiagents.gateway.protocols", "DeadLetterDecision"),
    "DeadLetterPolicyProtocol": ("praisonaiagents.gateway.protocols", "DeadLetterPolicyProtocol"),
    "AttemptAndAgeDeadLetterPolicy": ("praisonaiagents.gateway.protocols", "AttemptAndAgeDeadLetterPolicy"),
    # Port-less, restart-safe external drain trigger (Issue #2390)
    "current_epoch": ("praisonaiagents.gateway.protocols", "current_epoch"),
    "DrainMarkerPolicy": ("praisonaiagents.gateway.protocols", "DrainMarkerPolicy"),
    # Crash / shutdown forensics (Issue #2436)
    "ShutdownForensicsProtocol": ("praisonaiagents.gateway.protocols", "ShutdownForensicsProtocol"),
    "format_forensics_for_log": ("praisonaiagents.gateway.protocols", "format_forensics_for_log"),
    "is_supervised": ("praisonaiagents.gateway.protocols", "is_supervised"),
    "drain_timeout_has_headroom": ("praisonaiagents.gateway.protocols", "drain_timeout_has_headroom"),
    # Code-skew guard for hot operations (Issue #2460)
    "detect_code_skew": ("praisonaiagents.gateway.protocols", "detect_code_skew"),
    # Restart-intent exit-code protocol (Issue #2437)
    "GATEWAY_OK_EXIT_CODE": ("praisonaiagents.gateway.protocols", "GATEWAY_OK_EXIT_CODE"),
    "GATEWAY_RESTART_EXIT_CODE": ("praisonaiagents.gateway.protocols", "GATEWAY_RESTART_EXIT_CODE"),
    "GATEWAY_FATAL_CONFIG_EXIT_CODE": ("praisonaiagents.gateway.protocols", "GATEWAY_FATAL_CONFIG_EXIT_CODE"),
    "FatalConfigError": ("praisonaiagents.gateway.protocols", "FatalConfigError"),
    "classify_exit_reason": ("praisonaiagents.gateway.protocols", "classify_exit_reason"),
    "RestartLoopGuard": ("praisonaiagents.gateway.protocols", "RestartLoopGuard"),
    # Durable process-lifecycle record + unclean/OOM classification (Issue #4603)
    "LifecycleRecord": ("praisonaiagents.gateway.protocols", "LifecycleRecord"),
    "classify_unclean_exit": ("praisonaiagents.gateway.protocols", "classify_unclean_exit"),
    "RestartStoreProtocol": ("praisonaiagents.gateway.protocols", "RestartStoreProtocol"),
    "PersistentRestartLoopGuard": ("praisonaiagents.gateway.protocols", "PersistentRestartLoopGuard"),
    "classify_resource_pressure": ("praisonaiagents.gateway.protocols", "classify_resource_pressure"),
    # Fleet-level crash-loop breaker for channel supervision (Issue #3840)
    "FleetSupervisionPolicy": ("praisonaiagents.gateway.protocols", "FleetSupervisionPolicy"),
    # Protocol version negotiation
    "PROTOCOL_VERSION": ("praisonaiagents.gateway.protocols", "PROTOCOL_VERSION"),
    "MIN_PROTOCOL_VERSION": ("praisonaiagents.gateway.protocols", "MIN_PROTOCOL_VERSION"),
    "MAX_PROTOCOL_VERSION": ("praisonaiagents.gateway.protocols", "MAX_PROTOCOL_VERSION"),
    "ProtocolHello": ("praisonaiagents.gateway.protocols", "ProtocolHello"),
    "ProtocolHelloOk": ("praisonaiagents.gateway.protocols", "ProtocolHelloOk"),
    "GapInfo": ("praisonaiagents.gateway.protocols", "GapInfo"),
    "ResumeSnapshot": ("praisonaiagents.gateway.protocols", "ResumeSnapshot"),
    # Out-of-process platform-connector relay (Issue #2485)
    "CapabilityDescriptor": ("praisonaiagents.gateway.protocols", "CapabilityDescriptor"),
    "RelayTransport": ("praisonaiagents.gateway.protocols", "RelayTransport"),
    # Gateway pipeline span-tracing seam (Issue #2716)
    "GATEWAY_TRACE_STAGES": ("praisonaiagents.gateway.protocols", "GATEWAY_TRACE_STAGES"),
    "GatewayTraceHook": ("praisonaiagents.gateway.protocols", "GatewayTraceHook"),
    "NullGatewayTraceHook": ("praisonaiagents.gateway.protocols", "NullGatewayTraceHook"),
    "NULL_GATEWAY_TRACE_HOOK": ("praisonaiagents.gateway.protocols", "NULL_GATEWAY_TRACE_HOOK"),
    "resolve_trace_hook": ("praisonaiagents.gateway.protocols", "resolve_trace_hook"),
    # Gateway self-lifecycle command guardrail (Issue #2753)
    "LifecycleCommandDecision": ("praisonaiagents.gateway.protocols", "LifecycleCommandDecision"),
    "LifecycleCommandPolicyProtocol": ("praisonaiagents.gateway.protocols", "LifecycleCommandPolicyProtocol"),
    "LifecycleCommandPolicy": ("praisonaiagents.gateway.protocols", "LifecycleCommandPolicy"),
    "LifecycleCommandGuardPolicy": ("praisonaiagents.gateway.protocols", "LifecycleCommandGuardPolicy"),
    # Application-level connection liveness (Issue #2798)
    "LivenessDecision": ("praisonaiagents.gateway.protocols", "LivenessDecision"),
    "LivenessPolicyProtocol": ("praisonaiagents.gateway.protocols", "LivenessPolicyProtocol"),
    "LivenessPolicy": ("praisonaiagents.gateway.protocols", "LivenessPolicy"),
    # Cluster-wide per-turn serialisation (Issue #3643)
    "TurnLeaseToken": ("praisonaiagents.gateway.protocols", "TurnLeaseToken"),
    "TurnLockProtocol": ("praisonaiagents.gateway.protocols", "TurnLockProtocol"),
    "LocalTurnLock": ("praisonaiagents.gateway.protocols", "LocalTurnLock"),
    # Per-session turn-execution isolation (Issue #4011)
    "WorkerWedgedError": ("praisonaiagents.gateway.protocols", "WorkerWedgedError"),
    "TurnPlacement": ("praisonaiagents.gateway.protocols", "TurnPlacement"),
    "TurnExecutorProtocol": ("praisonaiagents.gateway.protocols", "TurnExecutorProtocol"),
    "InProcessTurnExecutor": ("praisonaiagents.gateway.protocols", "InProcessTurnExecutor"),
    # Global operator emergency-stop / pause brake (Issue #4220)
    "EmergencyStopState": ("praisonaiagents.gateway.protocols", "EmergencyStopState"),
    "EmergencyStopProtocol": ("praisonaiagents.gateway.protocols", "EmergencyStopProtocol"),
    "NullEmergencyStop": ("praisonaiagents.gateway.protocols", "NullEmergencyStop"),
    "FileEmergencyStop": ("praisonaiagents.gateway.protocols", "FileEmergencyStop"),
    # Per-session stop scope (Issue #5129)
    "StopScope": ("praisonaiagents.gateway.protocols", "StopScope"),
    "StopResult": ("praisonaiagents.gateway.protocols", "StopResult"),
    # Schema-validated inbound frame codec (Issue #2831)
    "HelloParams": ("praisonaiagents.gateway.protocols", "HelloParams"),
    "HelloResult": ("praisonaiagents.gateway.protocols", "HelloResult"),
    "HelloError": ("praisonaiagents.gateway.protocols", "HelloError"),
    "ConnectErrorCode": ("praisonaiagents.gateway.protocols", "ConnectErrorCode"),
    "ConnectRecoveryStep": ("praisonaiagents.gateway.protocols", "ConnectRecoveryStep"),
    "is_recoverable": ("praisonaiagents.gateway.protocols", "is_recoverable"),
    "MessageParams": ("praisonaiagents.gateway.protocols", "MessageParams"),
    "LeaveParams": ("praisonaiagents.gateway.protocols", "LeaveParams"),
    "JoinParams": ("praisonaiagents.gateway.protocols", "JoinParams"),
    "FrameDecodeError": ("praisonaiagents.gateway.protocols", "FrameDecodeError"),
    "ClientFrame": ("praisonaiagents.gateway.protocols", "ClientFrame"),
    "decode_client_frame": ("praisonaiagents.gateway.protocols", "decode_client_frame"),
    # Weak / placeholder secret guard (Issue #3259)
    "KNOWN_WEAK_SECRETS": ("praisonaiagents.gateway.protocols", "KNOWN_WEAK_SECRETS"),
    "WeakGatewaySecretError": ("praisonaiagents.gateway.protocols", "WeakGatewaySecretError"),
    "is_weak_secret": ("praisonaiagents.gateway.protocols", "is_weak_secret"),
    "assert_gateway_secret_strong": ("praisonaiagents.gateway.protocols", "assert_gateway_secret_strong"),
    # Per-platform identity canonicalization (Issue #3886)
    "IdentityCanonicalizerProtocol": ("praisonaiagents.gateway.protocols", "IdentityCanonicalizerProtocol"),
    # liveness.py — Event-loop liveness watchdog (Issue #3385)
    "LoopWatchdogPolicy": ("praisonaiagents.gateway.liveness", "LoopWatchdogPolicy"),
    "LoopWatchdog": ("praisonaiagents.gateway.liveness", "LoopWatchdog"),
    # degraded_state.py — Unified degraded-capability registry (Issue #3518)
    "DegradedOwner": ("praisonaiagents.gateway.degraded_state", "DegradedOwner"),
    "DegradedCapabilityProtocol": ("praisonaiagents.gateway.degraded_state", "DegradedCapabilityProtocol"),
    "DegradedCapabilityRegistry": ("praisonaiagents.gateway.degraded_state", "DegradedCapabilityRegistry"),
    "OWNER_KINDS": ("praisonaiagents.gateway.degraded_state", "OWNER_KINDS"),
    "DEGRADED_STATES": ("praisonaiagents.gateway.degraded_state", "DEGRADED_STATES"),
    # Fail-closed read of the degraded-owner contract (Issue #3640)
    "DegradedCapabilityLookupProtocol": ("praisonaiagents.gateway.degraded_state", "DegradedCapabilityLookupProtocol"),
    "OwnerUnavailable": ("praisonaiagents.gateway.degraded_state", "OwnerUnavailable"),
    "assert_owner_available": ("praisonaiagents.gateway.degraded_state", "assert_owner_available"),
    # hooks.py — Inbound trigger / webhook contract (Issue #2281)
    "HookAction": ("praisonaiagents.gateway.hooks", "HookAction"),
    "HookConfig": ("praisonaiagents.gateway.hooks", "HookConfig"),
    "InboundTriggerProtocol": ("praisonaiagents.gateway.hooks", "InboundTriggerProtocol"),
    "render_template": ("praisonaiagents.gateway.hooks", "render_template"),
    "compute_idempotency_key": ("praisonaiagents.gateway.hooks", "compute_idempotency_key"),
    "verify_webhook_signature": ("praisonaiagents.gateway.hooks", "verify_webhook_signature"),
    # config.py (always available)
    "GatewayConfig": ("praisonaiagents.gateway.config", "GatewayConfig"),
    "SessionConfig": ("praisonaiagents.gateway.config", "SessionConfig"),
    "ApiConfig": ("praisonaiagents.gateway.config", "ApiConfig"),
    "EmergencyStopConfig": ("praisonaiagents.gateway.config", "EmergencyStopConfig"),
    "ChannelRouteConfig": ("praisonaiagents.gateway.config", "ChannelRouteConfig"),
    "MultiChannelGatewayConfig": ("praisonaiagents.gateway.config", "MultiChannelGatewayConfig"),
    # Config version stamp + doctor-driven migration (Issue #3841)
    "GATEWAY_CONFIG_VERSION": ("praisonaiagents.gateway.config", "GATEWAY_CONFIG_VERSION"),
    "ConfigVersionError": ("praisonaiagents.gateway.config", "ConfigVersionError"),
    "LegacyConfigRule": ("praisonaiagents.gateway.config", "LegacyConfigRule"),
    "GATEWAY_CONFIG_RULES": ("praisonaiagents.gateway.config", "GATEWAY_CONFIG_RULES"),
    "is_config_current": ("praisonaiagents.gateway.config", "is_config_current"),
    "migrate_config_with_doctor": ("praisonaiagents.gateway.config", "migrate_config_with_doctor"),
    # Push config
    "PushConfig": ("praisonaiagents.gateway.config", "PushConfig"),
    "RedisConfig": ("praisonaiagents.gateway.config", "RedisConfig"),
    "PresenceConfig": ("praisonaiagents.gateway.config", "PresenceConfig"),
    "DeliveryConfig": ("praisonaiagents.gateway.config", "DeliveryConfig"),
    "PollingConfig": ("praisonaiagents.gateway.config", "PollingConfig"),
    "LivenessConfig": ("praisonaiagents.gateway.config", "LivenessConfig"),
    "TurnLockConfig": ("praisonaiagents.gateway.config", "TurnLockConfig"),
    # Hot-reload registry (Issue #3378)
    "HOT_APPLIABLE_KEYS": ("praisonaiagents.gateway.config", "HOT_APPLIABLE_KEYS"),
    "SupportsHotReload": ("praisonaiagents.gateway.config", "SupportsHotReload"),
    "is_hot_appliable": ("praisonaiagents.gateway.config", "is_hot_appliable"),
    # Reload scope classification (Issue #3440)
    "ReloadScope": ("praisonaiagents.gateway.config", "ReloadScope"),
    "classify_reload": ("praisonaiagents.gateway.config", "classify_reload"),
}

# Lazy loading cache (shared with wrapper-backed implementations below)
_lazy_cache = {}

_lazy_getattr = create_lazy_getattr(_LAZY_IMPORTS, __name__, cache=_lazy_cache)


def __getattr__(name: str):
    """Lazy load gateway symbols and heavy implementations.

    Protocols/policies/config are served from their submodules on first
    access via the ``_LAZY_IMPORTS`` map, so ``protocols.py`` is parsed only
    when actually touched. ``WebSocketGateway``/``GatewaySession`` are
    re-exported from ``praisonai-bot`` (C9); prefer ``praisonai_bot.gateway``
    or ``pip install praisonai`` for the full stack (Gap S2).
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
    
    # Everything else: lazy-load from the submodule map (protocols.py parsed
    # only if a protocol/policy symbol is actually requested).
    value = _lazy_getattr(name)
    # Bind the resolved symbol into the module globals so it behaves exactly
    # like an eager import: it becomes a real attribute (discoverable via
    # ``dir``, deletable, and patchable via ``monkeypatch.delattr``/``setattr``),
    # and future accesses skip ``__getattr__`` entirely.
    globals()[name] = value
    return value


def __dir__():
    """Expose the public API to ``dir()`` / IDE autocomplete without importing.

    Returns the union of names already resolved into the module globals and the
    declared public ``__all__``, so lazy exports remain discoverable before they
    are first accessed (matching the eager-import behaviour).
    """
    return sorted(set(globals()) | set(__all__))


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
    "RemoteMediaResolver",
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
    "SpendBudgetPolicyProtocol",
    "SpendBudgetPolicy",
    "WindowedSpendBudgetPolicy",
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
    "StopScope",
    "StopResult",
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
