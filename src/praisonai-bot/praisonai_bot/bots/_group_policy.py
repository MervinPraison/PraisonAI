"""
Shared group-admission glue for channel adapters (Issue #5962).

Every adapter feeds platform facts (chat type, how the bot was addressed,
whether the message is a command) into the core
:func:`praisonaiagents.bots.admission.resolve_ingress_admission` decision, so a
single ``group_policy`` in ``gateway.yaml`` behaves identically on Telegram,
Discord and Slack instead of each adapter re-deriving it inline.
"""

from __future__ import annotations

import logging

from praisonaiagents.bots.admission import (
    IngressDecision,
    MentionFacts,
    resolve_ingress_admission,
)

logger = logging.getLogger(__name__)

_GROUP_POLICIES = frozenset({"respond_all", "mention_only", "command_only", "observe"})


def effective_group_policy(config) -> str:
    """Resolve ``group_policy`` honouring the legacy ``mention_required`` flag.

    ``mention_required=False`` with the default ``mention_only`` policy (or an
    unrecognised policy) keeps its historical meaning of "respond to all group
    messages", so standalone bots configured only via ``mention_required`` are
    unaffected.
    """
    policy = str(getattr(config, "group_policy", "") or "mention_only").lower()
    mention_required = getattr(config, "mention_required", True)
    if policy not in _GROUP_POLICIES:
        policy = "mention_only"
    if policy == "mention_only" and not mention_required:
        return "respond_all"
    return policy


def decide_group_admission(
    config, *, chat_type: str, mention: MentionFacts, is_command: bool = False
) -> IngressDecision:
    """Decide whether a group message should run, be observed, or be dropped."""
    return resolve_ingress_admission(
        chat_type=chat_type,
        sender_id=None,
        mention=mention,
        is_command=is_command,
        group_policy=effective_group_policy(config),
    )


def record_passive_group_message(bot, message) -> None:
    """Record an unmentioned group message as passive session context.

    Issue #3380: used by the ``observe`` group policy so that unmentioned
    messages are retained in the transcript (without triggering an agent run)
    and are visible to the agent when it is next addressed. Best-effort — a
    missing session manager or any failure is swallowed so inbound handling is
    never broken by observation.
    """
    session_mgr = getattr(bot, "_session", None)
    if session_mgr is None or not hasattr(session_mgr, "record_passive"):
        return
    try:
        content = message.get_text() if hasattr(message, "get_text") else str(message.content)
        user_id = message.sender.user_id if message.sender else ""
        sender = (message.sender.display_name or user_id) if message.sender else user_id
        # Thread the same routing fields an addressed turn uses so that with
        # session_scope="per_chat" the passive entry lands on the shared group
        # key the next mentioned run reads from (Issue #3380 / #2376). With the
        # default per_user scope these are simply ignored.
        session_mgr.record_passive(
            user_id,
            content,
            sender=sender,
            chat_id=str(message.channel.channel_id) if message.channel and message.channel.channel_id else "",
            thread_id=str(message.thread_id) if getattr(message, "thread_id", None) else "",
            account=getattr(bot.config, "account", "default"),
        )
    except Exception as e:  # pragma: no cover — defensive
        logger.debug(f"Failed to record passive group message: {e}")
