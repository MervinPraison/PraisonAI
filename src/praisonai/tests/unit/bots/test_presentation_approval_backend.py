"""Tests for the durable, actor-authorised ApprovalProtocol backend that wires
the PresentationApprovalHandler into the standard approval contract."""

import asyncio

from praisonai.bots._presentation_approval_backend import PresentationApprovalBackend


def _make_request(approval_id="abc123", tool_name="delete_file"):
    from praisonaiagents.approval import ApprovalRequest

    return ApprovalRequest(
        tool_name=tool_name,
        arguments={"path": "/etc/passwd"},
        risk_level="high",
        approval_id=approval_id,
    )


def test_implements_approval_protocol():
    from praisonaiagents.approval import ApprovalProtocol

    backend = PresentationApprovalBackend(allowed_actors={"owner"})
    assert isinstance(backend, ApprovalProtocol)


def test_authorized_actor_approves_via_callback():
    async def run():
        backend = PresentationApprovalBackend(allowed_actors={"owner"})
        request = _make_request()

        async def approve_later():
            await asyncio.sleep(0.01)
            return await backend.handle_callback(
                request.approval_id, "allow", actor="owner"
            )

        async def ask():
            return await _request_with_timeout(backend, request, 1.0)

        decision, handled = await asyncio.gather(ask(), approve_later())
        return decision, handled

    decision, handled = asyncio.run(run())
    assert handled is True
    assert decision.approved is True
    assert decision.metadata["approval_id"] == "abc123"


def test_unauthorized_actor_cannot_approve():
    async def run():
        backend = PresentationApprovalBackend(allowed_actors={"owner"})
        request = _make_request()

        async def attacker():
            await asyncio.sleep(0.01)
            return await backend.handle_callback(
                request.approval_id, "allow", actor="stranger"
            )

        async def ask():
            return await _request_with_timeout(backend, request, 0.2)

        decision, handled = await asyncio.gather(ask(), attacker())
        return decision, handled

    decision, handled = asyncio.run(run())
    # Stranger's tap rejected; request fails closed (times out).
    assert handled is False
    assert decision.approved is False


def test_callback_id_binds_decision_to_request():
    async def run():
        backend = PresentationApprovalBackend(allowed_actors={"owner"})
        request = _make_request(approval_id="unguessable-id")

        async def approve_later():
            await asyncio.sleep(0.01)
            # Wrong id must not resolve the real request.
            wrong = await backend.handle_callback(
                "some-other-id", "allow", actor="owner"
            )
            right = await backend.handle_callback(
                "unguessable-id", "allow", actor="owner"
            )
            return wrong, right

        async def ask():
            return await _request_with_timeout(backend, request, 1.0)

        decision, (wrong, right) = await asyncio.gather(ask(), approve_later())
        return decision, wrong, right

    decision, wrong, right = asyncio.run(run())
    assert wrong is False
    assert right is True
    assert decision.approved is True


def test_replay_callback_rejected_after_resolution():
    async def run():
        backend = PresentationApprovalBackend(allowed_actors={"owner"})
        request = _make_request(approval_id="replay-id")

        async def approve_then_replay():
            await asyncio.sleep(0.01)
            first = await backend.handle_callback(
                "replay-id", "allow", actor="owner"
            )
            # A second tap on the same id must be a no-op (single-use).
            replay = await backend.handle_callback(
                "replay-id", "deny", actor="owner"
            )
            return first, replay

        async def ask():
            return await _request_with_timeout(backend, request, 1.0)

        decision, (first, replay) = await asyncio.gather(ask(), approve_then_replay())
        return decision, first, replay

    decision, first, replay = asyncio.run(run())
    assert first is True
    assert replay is False
    assert decision.approved is True


def test_rehydrated_approval_preserves_actor_allowlist(tmp_path):
    """A pending approval restored after restart must keep its actor
    authorisation, so a stranger cannot resolve it post-restart.

    Simulates a crash while an approval was still pending: the durable row is
    persisted with a future expiry (no resolution recorded), then a fresh
    backend rehydrates from the same store, mirroring a process restart.
    """
    import time

    from praisonai.bots import ApprovalStore

    store_path = tmp_path / "approvals.sqlite"

    async def create_pending():
        store = ApprovalStore(path=store_path)
        request = _make_request(approval_id="restart-id")
        # Persist a still-pending row directly (process "crashes" before any
        # decision is recorded), so list_pending() returns it after restart.
        await store.persist(
            request.approval_id, request, expires_at=time.time() + 300
        )

    asyncio.run(create_pending())

    async def after_restart():
        store = ApprovalStore(path=store_path)
        backend = PresentationApprovalBackend(store=store, allowed_actors={"owner"})
        rehydrated = await backend.rehydrate()
        stranger = await backend.handle_callback(
            "restart-id", "allow", actor="stranger"
        )
        owner = await backend.handle_callback(
            "restart-id", "allow", actor="owner"
        )
        return rehydrated, stranger, owner

    rehydrated, stranger, owner = asyncio.run(after_restart())
    assert rehydrated >= 1
    # Allowlist survived the restart: stranger rejected, owner accepted.
    assert stranger is False
    assert owner is True


async def _request_with_timeout(backend, request, timeout):
    backend._timeout = timeout
    return await backend.request_approval(request)
