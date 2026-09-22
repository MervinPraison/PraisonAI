"""Regression coverage for the multi-observer Gateway session contract (Issue #5192).

The new vocabulary — ``SessionVisibility``, ``SessionSharingRole`` and the
``SessionObserverProtocol`` — is a *contract* every client/impl must agree on.
These tests pin the public surface so a silent rename, a changed default role,
or a broken ``@runtime_checkable`` recognition fails here rather than downstream.
"""

from typing import List, Tuple

from praisonaiagents.gateway import (
    SessionObserverProtocol,
    SessionSharingRole,
    SessionVisibility,
)
from praisonaiagents.gateway.protocols import (
    SessionObserverProtocol as ProtocolsObserver,
    SessionSharingRole as ProtocolsRole,
    SessionVisibility as ProtocolsVisibility,
)


def test_gateway_reexports_match_protocols_module():
    """Lazy gateway exports resolve to the same objects as ``protocols.py``."""
    assert SessionVisibility is ProtocolsVisibility
    assert SessionSharingRole is ProtocolsRole
    assert SessionObserverProtocol is ProtocolsObserver


def test_visibility_values_and_default():
    """Wire values are stable and ``PRIVATE`` preserves today's 1:1 model."""
    assert SessionVisibility.PRIVATE.value == "private"
    assert SessionVisibility.SHARED.value == "shared"
    assert SessionVisibility.READ_ONLY.value == "read_only"
    assert {v.value for v in SessionVisibility} == {"private", "shared", "read_only"}


def test_sharing_role_values():
    """Role wire values are stable across the owner/member/viewer hierarchy."""
    assert SessionSharingRole.OWNER.value == "owner"
    assert SessionSharingRole.MEMBER.value == "member"
    assert SessionSharingRole.VIEWER.value == "viewer"
    assert {r.value for r in SessionSharingRole} == {"owner", "member", "viewer"}


def test_observer_protocol_is_runtime_checkable():
    """A conforming implementation satisfies ``isinstance`` and behaves as documented."""

    class _Observer:
        def __init__(self) -> None:
            self._by_session: dict = {}

        def attach(
            self,
            session_id: str,
            client_id: str,
            role: SessionSharingRole = SessionSharingRole.VIEWER,
        ) -> None:
            self._by_session.setdefault(session_id, {})[client_id] = role

        def detach(self, session_id: str, client_id: str) -> None:
            self._by_session.get(session_id, {}).pop(client_id, None)

        def observers(
            self, session_id: str
        ) -> "List[Tuple[str, SessionSharingRole]]":
            return list(self._by_session.get(session_id, {}).items())

    impl = _Observer()
    assert isinstance(impl, SessionObserverProtocol)

    impl.attach("s1", "owner-client", role=SessionSharingRole.OWNER)
    impl.attach("s1", "viewer-client")  # default VIEWER role
    assert dict(impl.observers("s1")) == {
        "owner-client": SessionSharingRole.OWNER,
        "viewer-client": SessionSharingRole.VIEWER,
    }

    impl.detach("s1", "viewer-client")
    assert dict(impl.observers("s1")) == {"owner-client": SessionSharingRole.OWNER}


def test_non_conforming_object_is_not_an_observer():
    """A bare object missing the attach/detach/observers surface is rejected."""

    class _NotAnObserver:
        pass

    assert not isinstance(_NotAnObserver(), SessionObserverProtocol)
