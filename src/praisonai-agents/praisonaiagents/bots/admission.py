"""
Inbound admission primitive for bot gateways.

Provides a single, pure, dependency-free decision for "should the bot act on
this inbound message?" — channel/user allowlist, block-list, group policy
(``respond_all`` / ``mention_only`` / ``command_only`` / ``observe``) and
pairing for unknown users — returning a typed verdict with a machine-readable
reason code an operator can inspect.

Like :func:`praisonaiagents.bots.protocols.evaluate_channel_health` and
:class:`praisonaiagents.bots.silence.BotLoopGuard`, this is a zero-dependency
decision primitive: every channel adapter (built-in or plugin) feeds it native
message facts and acts on the verdict, so the admission decision cannot drift
across transports and a drop is no longer a silent ``logger.debug`` line but a
recorded ``reason_code``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

# Machine-readable reason codes. Kept as module constants so callers can record
# and compare them without re-typing string literals (which is exactly how the
# per-channel logic drifted).
REASON_ALLOWED = "allowed"
REASON_NOT_IN_ALLOWLIST = "not_in_allowlist"
REASON_BLOCKED = "blocked"
REASON_GROUP_MENTION_ONLY = "group_mention_only"
REASON_OBSERVE = "observe"
REASON_PAIRING_REQUIRED = "pairing_required"
REASON_COMMAND_ONLY = "command_only"

# Gate names — which stage of the ladder produced the verdict.
GATE_BLOCKLIST = "blocklist"
GATE_ALLOWLIST = "allowlist"
GATE_PAIRING = "pairing"
GATE_GROUP_POLICY = "group_policy"
GATE_DIRECT = "direct"

# Group policies, matching the existing YAML ``group_policy`` values.
_GROUP_POLICIES = frozenset(
    {"respond_all", "mention_only", "command_only", "observe"}
)

# Chat types treated as one-to-one (no group policy applies).
_DIRECT_CHAT_TYPES = frozenset({"dm", "private", "direct", "im"})


@dataclass(frozen=True)
class IngressDecision:
    """Typed verdict for an inbound admission decision.

    Attributes:
        admit: Whether the bot should run the agent on this message. ``False``
            means the message is dropped (or only passively observed).
        reason_code: A machine-readable reason (one of the ``REASON_*``
            constants) an operator can inspect to answer "why didn't the bot
            reply to that message?".
        gate: Which gate decided (one of the ``GATE_*`` constants), for
            diagnostics.
        observe: When ``True`` the message was not admitted for a run but SHOULD
            be recorded into the session transcript as passive context (the
            ``observe`` group policy). Adapters record it and skip the run.
    """

    admit: bool
    reason_code: str
    gate: str
    observe: bool = False


def _contains(collection: Optional[Iterable[str]], value: Optional[str]) -> bool:
    """Membership test tolerant of ``None`` collection/value.

    An empty or ``None`` collection means "no restriction configured" and is
    handled by the caller — this only answers whether ``value`` is present.
    """
    if not collection or value is None:
        return False
    return value in collection


def resolve_ingress_admission(
    *,
    chat_type: Optional[str],
    sender_id: Optional[str],
    is_mention: bool = False,
    is_command: bool = False,
    allowlist: Optional[Iterable[str]] = None,
    blocklist: Optional[Iterable[str]] = None,
    group_policy: Optional[str] = None,
    paired: bool = True,
) -> IngressDecision:
    """Decide whether the bot should act on an inbound message.

    Pure, deterministic and zero-dependency: the same inputs always yield the
    same verdict, so the decision cannot drift across transports or plugin
    channels. Every adapter replaces its bespoke ladder with one call and
    records ``decision.reason_code``.

    The ladder (first matching gate wins):

    1. **Block-list** — an explicitly blocked sender is always dropped
       (``blocked``), taking precedence over any allowlist entry.
    2. **Allow-list** — when an ``allowlist`` is configured and the sender is
       not in it, drop (``not_in_allowlist``). An empty/``None`` allowlist means
       "no allowlist restriction".
    3. **Pairing** — an unknown but not-yet-``paired`` sender that passed the
       allowlist gate requires pairing (``pairing_required``).
    4. **Group policy** — for group/channel chats only:
         - ``command_only``: admit commands, else drop (``command_only``);
         - ``mention_only``: admit mentions/commands, else drop
           (``group_mention_only``);
         - ``observe``: admit mentions/commands, else *observe* (recorded, no
           run) with reason ``observe``;
         - ``respond_all``: admit everything;
         - unset/unknown: treated as ``mention_only`` (the live
           ``BotConfig.group_policy`` default), so an adapter forwarding an
           unset policy does not silently reply to all group traffic.

    Direct (DM/private) chats skip the group-policy gate entirely.

    Args:
        chat_type: Native chat type (e.g. ``"dm"``, ``"private"``, ``"group"``,
            ``"channel"``, ``"supergroup"``). Anything not in the direct set is
            treated as a group for policy purposes.
        sender_id: Stable sender identifier used for allow/block-list checks.
        is_mention: Whether the bot was mentioned/@-addressed in the message.
        is_command: Whether the message is a bot command (always allowed under
            ``mention_only`` / ``command_only`` / ``observe``).
        allowlist: Optional collection of allowed sender ids to *enforce*.
            Empty/``None`` disables the allowlist gate (no restriction). This is
            the already-resolved list — an adapter that wants an empty allowlist
            to mean "deny unknown" (``BotConfig.is_explicitly_allowed`` +
            ``unknown_user_policy``) resolves that upstream into the ``paired``
            flag rather than passing an empty ``allowlist`` here.
        blocklist: Optional collection of blocked sender ids.
        group_policy: One of ``respond_all`` / ``mention_only`` /
            ``command_only`` / ``observe``. ``None`` or unknown values behave as
            ``mention_only`` — the live ``BotConfig.group_policy`` default — so
            an unset policy fails safe (mention-gated) rather than open.
        paired: Whether the sender is already paired/known. ``True`` (the
            default) means pairing is not required.

    Returns:
        An :class:`IngressDecision` with the verdict, a machine-readable
        ``reason_code``, the deciding ``gate`` and the ``observe`` flag.
    """
    # 1. Block-list wins over everything: an explicitly blocked sender never
    #    reaches an agent run regardless of allowlist membership.
    if _contains(blocklist, sender_id):
        return IngressDecision(
            admit=False, reason_code=REASON_BLOCKED, gate=GATE_BLOCKLIST
        )

    # 2. Allow-list: only enforced when configured. Absent/empty => no restriction.
    if allowlist and not _contains(allowlist, sender_id):
        return IngressDecision(
            admit=False,
            reason_code=REASON_NOT_IN_ALLOWLIST,
            gate=GATE_ALLOWLIST,
        )

    # 3. Pairing: an allowed-but-unknown sender must complete pairing first.
    if not paired:
        return IngressDecision(
            admit=False,
            reason_code=REASON_PAIRING_REQUIRED,
            gate=GATE_PAIRING,
        )

    # Direct chats bypass group policy entirely.
    is_direct = (chat_type or "").lower() in _DIRECT_CHAT_TYPES
    if is_direct:
        return IngressDecision(
            admit=True, reason_code=REASON_ALLOWED, gate=GATE_DIRECT
        )

    # 4. Group policy for group/channel chats. Unknown/None => mention_only,
    #    matching the live ``BotConfig.group_policy`` default so an adapter that
    #    forwards an unset policy does not silently start replying to all group
    #    traffic (a security-relevant regression).
    policy = (group_policy or "mention_only").lower()

    if policy == "command_only":
        if is_command:
            return IngressDecision(
                admit=True, reason_code=REASON_ALLOWED, gate=GATE_GROUP_POLICY
            )
        return IngressDecision(
            admit=False,
            reason_code=REASON_COMMAND_ONLY,
            gate=GATE_GROUP_POLICY,
        )

    if policy in ("mention_only", "observe"):
        if is_mention or is_command:
            return IngressDecision(
                admit=True, reason_code=REASON_ALLOWED, gate=GATE_GROUP_POLICY
            )
        if policy == "observe":
            # Recorded as passive context (no run) so the bot has memory of the
            # conversation when next addressed.
            return IngressDecision(
                admit=False,
                reason_code=REASON_OBSERVE,
                gate=GATE_GROUP_POLICY,
                observe=True,
            )
        return IngressDecision(
            admit=False,
            reason_code=REASON_GROUP_MENTION_ONLY,
            gate=GATE_GROUP_POLICY,
        )

    # respond_all (or any unknown policy): admit everything.
    return IngressDecision(
        admit=True, reason_code=REASON_ALLOWED, gate=GATE_GROUP_POLICY
    )
