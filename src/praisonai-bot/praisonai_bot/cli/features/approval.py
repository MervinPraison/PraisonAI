"""
Approval backend resolver for PraisonAI CLI.

Maps CLI --approval flag values to approval backend instances.
Used by run, chat, and main CLI commands for DRY approval wiring.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Valid backend names for CLI help text
VALID_BACKENDS = ["console", "slack", "telegram", "discord", "webhook", "http", "agent", "secure", "presentation", "auto", "none", "plan", "accept-edits", "bypass"]


def resolve_approval_backend(value: Optional[str], non_interactive: bool = False, permissions_config: Optional[dict] = None) -> Optional[Any]:
    """Resolve a CLI --approval flag value to an approval backend instance.

    Args:
        value: One of the backend names (slack, telegram, discord, webhook,
               http, console, auto, none) or None.  For webhook and http,
               additional config is read from environment variables.
        non_interactive: Whether to run in non-interactive mode.
        permissions_config: Declarative permission rules from YAML/CLI.

    Returns:
        An approval backend instance, or None if disabled.

    Raises:
        ValueError: If the value is not a recognised backend name.
    """
    if value is None:
        return None
        
    if isinstance(value, bool):
        value = "true" if value else "false"
        
    if str(value).lower() == "none":
        return None

    name = str(value).lower().strip()

    if name in ("true", "console", "yes", "1"):
        from praisonai_bot._code_bridge import import_code_module

        mod = import_code_module("praisonai_code.cli.approval_backend")
        return mod.InteractiveCLIApprovalBackend(
            non_interactive=non_interactive, permissions_config=permissions_config
        )

    if name in ("false", "no", "0"):
        return None

    if name == "auto":
        from praisonaiagents.approval.backends import AutoApproveBackend
        return AutoApproveBackend()
    
    if name == "plan":
        from praisonai_bot._code_bridge import import_code_module
        from praisonaiagents.permissions import PermissionMode

        mod = import_code_module("praisonai_code.cli.approval_backend")
        return mod.InteractiveCLIApprovalBackend(
            permission_mode=PermissionMode.PLAN,
            non_interactive=non_interactive,
            permissions_config=permissions_config,
        )

    if name == "accept-edits":
        from praisonai_bot._code_bridge import import_code_module
        from praisonaiagents.permissions import PermissionMode

        mod = import_code_module("praisonai_code.cli.approval_backend")
        return mod.InteractiveCLIApprovalBackend(
            permission_mode=PermissionMode.ACCEPT_EDITS,
            non_interactive=non_interactive,
            permissions_config=permissions_config,
        )

    if name == "bypass":
        from praisonai_bot._code_bridge import import_code_module
        from praisonaiagents.permissions import PermissionMode

        mod = import_code_module("praisonai_code.cli.approval_backend")
        return mod.InteractiveCLIApprovalBackend(
            permission_mode=PermissionMode.BYPASS,
            non_interactive=non_interactive,
            permissions_config=permissions_config,
        )

    if name in ("slack", "telegram", "discord", "webhook", "http", "secure", "presentation"):
        from praisonai_bot.cli.approval_backends import (
            CHANNEL_BACKENDS,
            resolve_channel_approval_backend,
        )

        if name not in CHANNEL_BACKENDS:
            raise ValueError(f"Unknown channel approval backend: {name!r}")
        return resolve_channel_approval_backend(name)

    if name == "agent":
        from praisonaiagents.approval import AgentApproval
        from praisonaiagents import Agent
        reviewer = Agent(
            name="approval-reviewer",
            instructions=(
                "You are a security reviewer. Only approve low-risk read "
                "operations. Deny anything destructive. Respond with exactly "
                "one word: APPROVE or DENY"
            ),
        )
        return AgentApproval(approver_agent=reviewer)

    raise ValueError(
        f"Unknown approval backend: {value!r}. "
        f"Valid options: {', '.join(VALID_BACKENDS)}"
    )


def resolve_approval_config(
    backend_name: Optional[str] = None,
    all_tools: bool = False,
    timeout: Optional[str] = None,
    non_interactive: bool = False,
    permissions_config: Optional[dict] = None,
) -> Optional[Any]:
    """Build an approval value for ``Agent(approval=...)``.

    If only a backend name is given (no extra flags), returns the plain
    backend object for backward compatibility.  When ``all_tools`` or
    ``timeout`` are specified, returns an :class:`ApprovalConfig`.

    Args:
        backend_name: CLI ``--approval`` value (slack, console, …).
        all_tools:    ``--approve-all-tools`` flag.
        timeout:      ``--approval-timeout`` value.  ``"none"`` means
                      indefinite; a numeric string is parsed as seconds.
        non_interactive: Whether to run in non-interactive mode.
        permissions_config: Declarative permission rules from YAML/CLI.
    """
    backend = resolve_approval_backend(backend_name, non_interactive=non_interactive, permissions_config=permissions_config)
    if backend is None:
        return None

    # Parse timeout
    parsed_timeout: Optional[float] = 0  # 0 = use backend default
    if timeout is not None:
        if timeout.lower() == "none":
            parsed_timeout = None  # indefinite
        else:
            try:
                parsed_timeout = float(timeout)
            except ValueError:
                logger.warning(f"Invalid --approval-timeout value: {timeout!r}, using backend default")
                parsed_timeout = 0

    # If no extra config needed, return plain backend (backward compatible)
    if not all_tools and parsed_timeout == 0 and not permissions_config:
        return backend

    from praisonaiagents.approval.protocols import ApprovalConfig
    return ApprovalConfig(
        backend=backend,
        all_tools=all_tools,
        timeout=parsed_timeout,
        permissions=permissions_config,
    )
