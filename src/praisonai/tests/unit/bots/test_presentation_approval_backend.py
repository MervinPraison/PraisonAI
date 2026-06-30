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


async def _request_with_timeout(backend, request, timeout):
    backend._timeout = timeout
    return await backend.request_approval(request)
