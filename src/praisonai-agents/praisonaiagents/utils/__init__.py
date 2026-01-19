"""
Utils Module for PraisonAI Agents.

Provides shared utilities used across the SDK:
- Variable providers: Dynamic variable substitution ({{today}}, {{now}}, etc.)
- Common helpers: Shared functions for Agent, Workflow, and other modules

All imports are lazy-loaded for zero performance impact.
"""

from .variables import (
    # Protocol
    DynamicVariableProvider,
    # Built-in providers
    NowProvider,
    TodayProvider,
    DateProvider,
    TimestampProvider,
    UUIDProvider,
    YearProvider,
    MonthProvider,
    # Registry
    VariableProviderRegistry,
    get_provider_registry,
    register_variable_provider,
    resolve_dynamic_variable,
    # Shared utility
    substitute_variables,
)

__all__ = [
    # Protocol
    "DynamicVariableProvider",
    # Built-in providers
    "NowProvider",
    "TodayProvider",
    "DateProvider",
    "TimestampProvider",
    "UUIDProvider",
    "YearProvider",
    "MonthProvider",
    # Registry
    "VariableProviderRegistry",
    "get_provider_registry",
    "register_variable_provider",
    "resolve_dynamic_variable",
    # Shared utility
    "substitute_variables",
]
