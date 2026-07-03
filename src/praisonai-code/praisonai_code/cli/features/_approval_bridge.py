"""Approval resolution for the standalone ``praisonai-code`` hot path.

The common backends (``console``/``plan``/``accept-edits``/``bypass``/``auto``/
``agent``/``none``) resolve locally against the core SDK and the local
``InteractiveCLIApprovalBackend`` — no wrapper package required. Channel bot
backends (``slack``/``telegram``/``discord``/``webhook``/``http``/``secure``/
``presentation``) live in the optional wrapper (``pip install praisonai``) and
are delegated there only when requested.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Backends that require praisonai-bot (channel approval handlers).
_WRAPPER_BACKENDS = frozenset(
    {"slack", "telegram", "discord", "webhook", "http", "secure", "presentation"}
)


def resolve_approval_backend(
    value: Optional[str],
    non_interactive: bool = False,
    permissions_config: Optional[dict] = None,
) -> Optional[Any]:
    """Resolve a CLI ``--approval`` value to an approval backend instance.

    Standalone-capable backends are built locally; channel bot backends are
    delegated to the wrapper package when available.
    """
    if value is None:
        return None

    if isinstance(value, bool):
        value = "true" if value else "false"

    name = str(value).lower().strip()

    if name in ("none", "false", "no", "0"):
        return None

    if name in ("true", "console", "yes", "1"):
        from praisonai_code.cli.approval_backend import InteractiveCLIApprovalBackend
        return InteractiveCLIApprovalBackend(
            non_interactive=non_interactive, permissions_config=permissions_config
        )

    if name == "auto":
        from praisonaiagents.approval.backends import AutoApproveBackend
        return AutoApproveBackend()

    if name in ("plan", "accept-edits", "bypass"):
        from praisonai_code.cli.approval_backend import InteractiveCLIApprovalBackend
        from praisonaiagents.permissions import PermissionMode
        mode = {
            "plan": PermissionMode.PLAN,
            "accept-edits": PermissionMode.ACCEPT_EDITS,
            "bypass": PermissionMode.BYPASS,
        }[name]
        return InteractiveCLIApprovalBackend(
            permission_mode=mode,
            non_interactive=non_interactive,
            permissions_config=permissions_config,
        )

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

    if name in _WRAPPER_BACKENDS:
        from praisonai_code._bot_bridge import import_bot_module

        mod = import_bot_module("praisonai_bot.cli.approval_backends")
        return mod.resolve_channel_approval_backend(name)

    from praisonai_code.cli.approval_backend import InteractiveCLIApprovalBackend  # noqa: F401
    valid = (
        "console, plan, accept-edits, bypass, auto, agent, none, "
        + ", ".join(sorted(_WRAPPER_BACKENDS))
    )
    raise ValueError(
        f"Unknown approval backend: {value!r}. Valid options: {valid}"
    )


def resolve_approval_config(
    backend_name: Optional[str] = None,
    all_tools: bool = False,
    timeout: Optional[str] = None,
    non_interactive: bool = False,
    permissions_config: Optional[dict] = None,
) -> Optional[Any]:
    """Build an approval value for ``Agent(approval=...)``.

    Returns the plain backend when no extra flags are set (backward
    compatible), otherwise an :class:`ApprovalConfig`.
    """
    backend = resolve_approval_backend(
        backend_name,
        non_interactive=non_interactive,
        permissions_config=permissions_config,
    )
    if backend is None:
        return None

    parsed_timeout: Optional[float] = 0  # 0 = use backend default
    if timeout is not None:
        if str(timeout).lower() == "none":
            parsed_timeout = None  # indefinite
        else:
            try:
                parsed_timeout = float(timeout)
            except ValueError:
                logger.warning(
                    "Invalid --approval-timeout value: %r, using backend default",
                    timeout,
                )
                parsed_timeout = 0

    if not all_tools and parsed_timeout == 0 and not permissions_config:
        return backend

    from praisonaiagents.approval.protocols import ApprovalConfig
    return ApprovalConfig(
        backend=backend,
        all_tools=all_tools,
        timeout=parsed_timeout,
        permissions=permissions_config,
    )
