"""
Agent-Centric Compliance Auditor for PraisonAI SDK.

This module provides tools to audit and fix Python examples and documentation
to ensure they follow agent-centric principles.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent_centric import AgentCentricAuditor, ComplianceResult

__all__ = ["AgentCentricAuditor", "ComplianceResult"]

def __getattr__(name: str):
    """Lazy loading for audit components."""
    if name == "AgentCentricAuditor":
        from .agent_centric import AgentCentricAuditor
        return AgentCentricAuditor
    if name == "ComplianceResult":
        from .agent_centric import ComplianceResult
        return ComplianceResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
