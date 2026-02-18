"""
praisonai.security — Agent security utilities for PraisonAI.

Provides:
- Prompt injection defense (6-check pipeline)
- Append-only audit log for tool calls
- Protected paths guard for code tools

All features are opt-in with zero overhead when not enabled.

Usage (simplest):
    from praisonai.security import enable_security
    enable_security()

    from praisonaiagents import Agent
    agent = Agent(instructions="You are a researcher")
    agent.start("Research the latest AI news")

Usage (selective):
    from praisonai.security import enable_injection_defense, enable_audit_log
    enable_injection_defense()
    enable_audit_log()
"""

from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    from .injection import InjectionDefense, ScanResult, ThreatLevel
    from .audit import AuditLogHook
    from .protected import is_protected, get_protection_reason, PROTECTED_PATHS

__all__ = [
    # Classes
    "InjectionDefense",
    "AuditLogHook",
    # Functions — injection
    "scan_text",
    "detect_instruction_patterns",
    "detect_authority_claims",
    "detect_boundary_manipulation",
    "detect_obfuscation",
    "detect_financial_manipulation",
    "detect_self_harm_instructions",
    # Functions — protected paths
    "is_protected",
    "get_protection_reason",
    "PROTECTED_PATHS",
    # One-line enable helpers
    "enable_injection_defense",
    "enable_audit_log",
    "enable_security",
]


def __getattr__(name: str):
    """Lazy load all security components."""
    _injection_exports = {
        "InjectionDefense", "ScanResult", "ThreatLevel",
        "scan_text",
        "detect_instruction_patterns",
        "detect_authority_claims",
        "detect_boundary_manipulation",
        "detect_obfuscation",
        "detect_financial_manipulation",
        "detect_self_harm_instructions",
    }
    _audit_exports = {"AuditLogHook"}
    _protected_exports = {"is_protected", "get_protection_reason", "PROTECTED_PATHS", "PROTECTED_PATTERNS"}

    if name in _injection_exports:
        from . import injection as _inj
        return getattr(_inj, name)
    if name in _audit_exports:
        from . import audit as _aud
        return getattr(_aud, name)
    if name in _protected_exports:
        from . import protected as _prot
        return getattr(_prot, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ─── One-line enable helpers ──────────────────────────────────────────────────

def enable_injection_defense(
    extra_patterns: Optional[List[str]] = None,
    block_threshold: Optional[int] = None,
    trusted_sources: Optional[List[str]] = None,
) -> str:
    """
    Enable prompt injection defense globally for all agents.

    Registers hooks on BEFORE_TOOL and BEFORE_AGENT events that scan
    inputs through a 6-check pipeline and block critical threats.

    Args:
        extra_patterns: Additional regex patterns to detect (appended to defaults).
        block_threshold: Override the threat level that triggers blocking.
                         3 = CRITICAL (default), 2 = HIGH, 1 = MEDIUM.
        trusted_sources: Source names that bypass blocking (in addition to defaults).

    Returns:
        Hook ID string (can be used to remove the hook later).

    Example:
        >>> from praisonai.security import enable_injection_defense
        >>> enable_injection_defense()
    """
    from .injection import InjectionDefense, ThreatLevel
    from praisonaiagents.hooks import add_hook

    threshold = ThreatLevel(block_threshold) if block_threshold is not None else ThreatLevel.CRITICAL

    defense = InjectionDefense(
        extra_patterns=extra_patterns,
        block_threshold=threshold,
        trusted_sources=trusted_sources,
    )

    # Register both before_tool and before_agent hooks
    tool_hook_id = add_hook("before_tool", defense.create_hook())
    add_hook("before_agent", defense.create_agent_hook())

    return tool_hook_id


def enable_audit_log(
    log_path: Optional[str] = None,
    include_output: bool = False,
) -> str:
    """
    Enable an append-only JSONL audit log for all agent tool calls.

    Args:
        log_path: Path to the audit log file.
                  Defaults to ~/.praisonai/audit.jsonl.
        include_output: Whether to include tool output in log entries.

    Returns:
        Hook ID string.

    Example:
        >>> from praisonai.security import enable_audit_log
        >>> enable_audit_log()
    """
    from .audit import AuditLogHook
    from praisonaiagents.hooks import add_hook

    audit = AuditLogHook(log_path=log_path, include_output=include_output)
    hook_id = add_hook("after_tool", audit.create_after_tool_hook())
    return hook_id


def enable_security(
    log_path: Optional[str] = None,
    include_output: bool = False,
    extra_patterns: Optional[List[str]] = None,
) -> dict:
    """
    Enable all security features in one call.

    Activates both injection defense and audit logging globally.

    Args:
        log_path: Audit log path (default: ~/.praisonai/audit.jsonl).
        include_output: Include tool output in audit entries.
        extra_patterns: Extra injection detection patterns.

    Returns:
        Dict with hook IDs: {"injection": str, "audit": str}

    Example:
        >>> from praisonai.security import enable_security
        >>> enable_security()

        Then use Agent normally — no extra parameters needed:
        >>> from praisonaiagents import Agent
        >>> agent = Agent(instructions="You are a researcher")
        >>> agent.start("Research AI news")
    """
    injection_id = enable_injection_defense(extra_patterns=extra_patterns)
    audit_id = enable_audit_log(log_path=log_path, include_output=include_output)
    return {"injection": injection_id, "audit": audit_id}
