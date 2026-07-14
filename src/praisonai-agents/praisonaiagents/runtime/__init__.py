""" 
Runtime execution components and capability system for PraisonAI agents.

This module provides runtime execution abstractions, protocols, and capability
validation for standardizing agent execution across different harness types.

Key Components:
- Runtime execution contexts: PreparedTurnContext, TurnRuntimeProtocol  
- Agent runtime registry: AgentRuntimeProtocol, RuntimeRegistry
- Tool result middleware: RuntimeToolResultMiddleware, NormalizedToolResult
- Registry patterns for runtime resolution and middleware management
- Doctor migration protocol: DoctorContractProtocol for config migration
- Capability validation: RuntimeCapability, RuntimeCapabilityMatrix, validate_capabilities
- Runtime protocols: AgentRuntimeProtocol for capability reporting
- Turn-time runtime resolution for handoffs and sub-agents

Features:
- Turn-based runtime execution with PreparedTurnContext
- RuntimeCapability flags for feature detection
- RuntimeCapabilityMatrix for runtime capability sets
- Capability validation at runtime selection time
- Support for native, plugin harness, and managed runtimes
- Dynamic runtime resolution at handoff boundaries
"""

from .._lazy import create_lazy_getattr_with_groups

__all__ = [
    # Runtime execution contexts
    'PreparedTurnContext',
    'TurnRuntimeProtocol',
    'TurnContextBuilderProtocol',
    'ModelReference',
    'ToolSchema', 
    'TranscriptWindow',
    'DeliveryChannels',
    'SessionCorrelation',
    'RuntimeMode',
    'create_default_model_ref',
    'create_empty_transcript',
    'create_default_delivery',
    'create_session_correlation',
    'DefaultTurnContextBuilder',
    'default_context_builder',
    # Tool result middleware
    "RuntimeToolResultMiddleware",
    "NormalizedToolResult", 
    "MiddlewareContext",
    # Middleware registry management  
    "MiddlewareRegistry",
    "get_default_middleware_registry",
    "register_middleware",
    "get_middleware",
    # Agent runtime APIs
    'AgentRuntimeProtocol',
    'RuntimeConfig', 
    'RuntimeResult',
    'RuntimeDelta',
    'RuntimeRegistry',
    'register_runtime',
    'list_runtimes', 
    # Turn-time runtime resolution for handoffs
    'resolve_runtime',
    'RuntimeProtocol',
    'SessionContext',
    'get_runtime_cache',
    'clear_runtime_cache',
    'set_global_resolver',
    # Doctor migration protocol
    "DoctorContractProtocol",
    "Finding",
    "get_default_registry",
    "register_rule",
    "get_rules",
    "collect_findings",
    "apply_fixes",
    # Capability types
    "RuntimeCapability",
    "RuntimeCapabilityMatrix",
    # Validation
    "validate_capabilities",
    "CapabilityValidationError",
    # Built-in runtimes
    "get_native_runtime_capabilities",
    "get_reduced_harness_capabilities",
    # Durable run-state journal (resumable execution)
    "RunJournal",
    "JournalEvent",
    "RunMeta",
]

# Grouped lazy imports for efficient loading
_LAZY_GROUPS = {
    'turn_context': {
        'PreparedTurnContext': ('praisonaiagents.runtime.turn_context', 'PreparedTurnContext'),
        'ModelReference': ('praisonaiagents.runtime.turn_context', 'ModelReference'),
        'ToolSchema': ('praisonaiagents.runtime.turn_context', 'ToolSchema'),
        'TranscriptWindow': ('praisonaiagents.runtime.turn_context', 'TranscriptWindow'),
        'DeliveryChannels': ('praisonaiagents.runtime.turn_context', 'DeliveryChannels'),
        'SessionCorrelation': ('praisonaiagents.runtime.turn_context', 'SessionCorrelation'),
        'RuntimeMode': ('praisonaiagents.runtime.turn_context', 'RuntimeMode'),
        'create_default_model_ref': ('praisonaiagents.runtime.turn_context', 'create_default_model_ref'),
        'create_empty_transcript': ('praisonaiagents.runtime.turn_context', 'create_empty_transcript'),
        'create_default_delivery': ('praisonaiagents.runtime.turn_context', 'create_default_delivery'),
        'create_session_correlation': ('praisonaiagents.runtime.turn_context', 'create_session_correlation'),
    },
    'protocols': {
        'TurnRuntimeProtocol': ('praisonaiagents.runtime.protocols', 'TurnRuntimeProtocol'),
        'TurnContextBuilderProtocol': ('praisonaiagents.runtime.protocols', 'TurnContextBuilderProtocol'),
        'AgentRuntimeProtocol': ('praisonaiagents.runtime.protocols', 'AgentRuntimeProtocol'),
        'RuntimeConfig': ('praisonaiagents.runtime.protocols', 'RuntimeConfig'),
        'RuntimeResult': ('praisonaiagents.runtime.protocols', 'RuntimeResult'),
        'RuntimeDelta': ('praisonaiagents.runtime.protocols', 'RuntimeDelta'),
    },
    'context_builder': {
        'DefaultTurnContextBuilder': ('praisonaiagents.runtime.context_builder', 'DefaultTurnContextBuilder'),
        'default_context_builder': ('praisonaiagents.runtime.context_builder', 'default_context_builder'),
    },
    'middleware': {
        'RuntimeToolResultMiddleware': ('praisonaiagents.runtime.middleware', 'RuntimeToolResultMiddleware'),
        'NormalizedToolResult': ('praisonaiagents.runtime.middleware', 'NormalizedToolResult'),
        'MiddlewareContext': ('praisonaiagents.runtime.middleware', 'MiddlewareContext'),
    },
    'middleware_registry': {
        'MiddlewareRegistry': ('praisonaiagents.runtime.middleware_registry', 'MiddlewareRegistry'),
        'get_default_middleware_registry': ('praisonaiagents.runtime.middleware_registry', 'get_default_middleware_registry'),
        'register_middleware': ('praisonaiagents.runtime.middleware_registry', 'register_middleware'),
        'get_middleware': ('praisonaiagents.runtime.middleware_registry', 'get_middleware'),
    },
    'registry': {
        'RuntimeRegistry': ('praisonaiagents.runtime.registry', 'RuntimeRegistry'),
        'register_runtime': ('praisonaiagents.runtime.registry', 'register_runtime'),
        'list_runtimes': ('praisonaiagents.runtime.registry', 'list_runtimes'),
    },
    'resolve': {
        'resolve_runtime': ('praisonaiagents.runtime.resolve', 'resolve_runtime'),
        'RuntimeProtocol': ('praisonaiagents.runtime.resolve', 'RuntimeProtocol'),
        'SessionContext': ('praisonaiagents.runtime.resolve', 'SessionContext'),
        'get_runtime_cache': ('praisonaiagents.runtime.resolve', 'get_runtime_cache'),
        'clear_runtime_cache': ('praisonaiagents.runtime.resolve', 'clear_runtime_cache'),
        'set_global_resolver': ('praisonaiagents.runtime.resolve', 'set_global_resolver'),
    },
    'capabilities': {
        'RuntimeCapability': ('praisonaiagents.runtime.capabilities', 'RuntimeCapability'),
        'RuntimeCapabilityMatrix': ('praisonaiagents.runtime.capabilities', 'RuntimeCapabilityMatrix'),
        'validate_capabilities': ('praisonaiagents.runtime.capabilities', 'validate_capabilities'),
        'CapabilityValidationError': ('praisonaiagents.runtime.capabilities', 'CapabilityValidationError'),
        'get_native_runtime_capabilities': ('praisonaiagents.runtime.capabilities', 'get_native_runtime_capabilities'),
        'get_reduced_harness_capabilities': ('praisonaiagents.runtime.capabilities', 'get_reduced_harness_capabilities'),
    },
    'doctor_protocol': {
        'DoctorContractProtocol': ('praisonaiagents.runtime.doctor_protocol', 'DoctorContractProtocol'),
        'Finding': ('praisonaiagents.runtime.doctor_protocol', 'Finding'),
    },
    'doctor_registry': {
        'get_default_registry': ('praisonaiagents.runtime.doctor_registry', 'get_default_registry'),
        'register_rule': ('praisonaiagents.runtime.doctor_registry', 'register_rule'),
        'get_rules': ('praisonaiagents.runtime.doctor_registry', 'get_rules'),
        'collect_findings': ('praisonaiagents.runtime.doctor_registry', 'collect_findings'),
        'apply_fixes': ('praisonaiagents.runtime.doctor_registry', 'apply_fixes'),
    },
    'journal': {
        'RunJournal': ('praisonaiagents.runtime.journal', 'RunJournal'),
        'JournalEvent': ('praisonaiagents.runtime.journal', 'JournalEvent'),
        'RunMeta': ('praisonaiagents.runtime.journal', 'RunMeta'),
    },
}

# Create the __getattr__ function using centralized utility
__getattr__ = create_lazy_getattr_with_groups(_LAZY_GROUPS, __name__)