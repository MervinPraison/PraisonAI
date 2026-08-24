"""Tests for durable gateway approvals (persistence + rehydration).

Verifies that:
  - pending approvals persisted to an ``ApprovalStoreProtocol`` store survive a
    simulated restart and are rehydrated on boot;
  - ``allow_always`` grants persisted to a durable allowlist survive a restart;
  - the default in-memory path is unchanged when no store is configured.
"""

import asyncio

import pytest

from praisonai_bot.bots import ApprovalStore
from praisonai_bot.gateway.exec_approval import (
    ExecApprovalManager,
    PermissionAllowlist,
    Resolution,
)


def test_allowlist_in_memory_default(tmp_path):
    """With durable=False the allowlist is in-memory only (no file created)."""
    al = PermissionAllowlist(durable=False)
    al.add("shell_exec")
    assert "shell_exec" in al
    assert not list(tmp_path.iterdir())


def test_allowlist_persists_and_reloads(tmp_path):
    """allow_always grants survive a restart via the durable allowlist file."""
    path = tmp_path / "allow.sqlite"
    al = PermissionAllowlist(path=path)
    al.add("shell_exec")
    assert path.exists()

    # Simulate restart: new instance reloads from disk.
    al2 = PermissionAllowlist(path=path)
    assert "shell_exec" in al2
    assert al2.list() == ["shell_exec"]

    assert al2.remove("shell_exec") is True
    al3 = PermissionAllowlist(path=path)
    assert "shell_exec" not in al3


def test_register_persists_to_store(tmp_path):
    """register() writes the pending approval to the durable store."""
    store = ApprovalStore(path=tmp_path / "approvals.sqlite")
    mgr = ExecApprovalManager(
        ttl=300, store=store, allowlist_path=tmp_path / "allow.sqlite"
    )

    async def go():
        rid, _future = await mgr.register(
            tool_name="shell_exec",
            arguments={"cmd": "ls"},
            agent_name="agent-1",
        )
        return rid

    rid = asyncio.run(go())
    assert store.pending_count() == 1
    row = store.get(rid)
    assert row is not None
    assert row["status"] == "pending"


def test_rehydrate_reloads_pending_after_restart(tmp_path):
    """A fresh manager rehydrates pending approvals from the store."""
    store = ApprovalStore(path=tmp_path / "approvals.sqlite")

    async def register_only():
        mgr = ExecApprovalManager(
            ttl=300, store=store, allowlist_path=tmp_path / "allow.sqlite"
        )
        rid, _ = await mgr.register(
            tool_name="deploy",
            arguments={"env": "prod"},
            agent_name="deployer",
        )
        return rid

    rid = asyncio.run(register_only())

    # Simulate restart: brand-new manager, same store.
    async def restart_and_rehydrate():
        mgr2 = ExecApprovalManager(
            ttl=300, store=store, allowlist_path=tmp_path / "allow.sqlite"
        )
        count = await mgr2.rehydrate()
        return count, mgr2

    count, mgr2 = asyncio.run(restart_and_rehydrate())
    assert count == 1
    pending = mgr2.list_pending()
    assert len(pending) == 1
    assert pending[0]["request_id"] == rid
    assert pending[0]["tool_name"] == "deploy"


def test_resolve_records_audit_and_removes_pending(tmp_path):
    """resolve() clears the pending row and records the decision durably."""
    store = ApprovalStore(path=tmp_path / "approvals.sqlite")
    mgr = ExecApprovalManager(
        ttl=300, store=store, allowlist_path=tmp_path / "allow.sqlite"
    )

    async def go():
        rid, future = await mgr.register(
            tool_name="shell_exec",
            arguments={"cmd": "rm -rf /tmp/x"},
        )
        mgr.resolve(rid, Resolution(approved=True, reason="ok"))
        # Wait for the scheduled durable-resolve task to complete instead of a
        # fixed sleep (poll the store's pending count with a bounded timeout).
        for _ in range(100):
            if store.pending_count() == 0:
                break
            await asyncio.sleep(0.01)
        return rid, await future

    rid, resolution = asyncio.run(go())
    assert resolution.approved is True
    assert store.pending_count() == 0
    row = store.get(rid)
    assert row is not None
    assert row["status"] == "approved"


def test_no_store_is_in_memory_only():
    """Without a store the manager behaves exactly as before."""
    mgr = ExecApprovalManager(ttl=300, durable=False)

    async def go():
        rid, future = await mgr.register(tool_name="t", arguments={})
        assert mgr.list_pending()[0]["request_id"] == rid
        mgr.resolve(rid, Resolution(approved=False))
        return await future

    res = asyncio.run(go())
    assert res.approved is False
    assert asyncio.run(mgr.rehydrate()) == 0


def test_rehydrate_preserves_original_expiry(tmp_path):
    """Rehydrated entries keep the original deadline, not a fresh TTL."""
    store = ApprovalStore(path=tmp_path / "approvals.sqlite")

    async def register_only():
        mgr = ExecApprovalManager(
            ttl=300, store=store, allowlist_path=tmp_path / "allow.sqlite"
        )
        rid, _ = await mgr.register(tool_name="deploy", arguments={})
        return rid

    rid = asyncio.run(register_only())
    original_expires = store.get(rid)["expires_at"]

    async def restart_and_rehydrate():
        mgr2 = ExecApprovalManager(
            ttl=300, store=store, allowlist_path=tmp_path / "allow.sqlite"
        )
        await mgr2.rehydrate()
        return mgr2.get_pending(rid)

    req = asyncio.run(restart_and_rehydrate())
    assert req is not None
    # created_at derived from stored expiry keeps the in-memory TTL aligned.
    assert abs((req.created_at + 300) - original_expires) < 1.0


def test_prune_marks_store_row_expired(tmp_path):
    """An in-memory prune marks the durable row 'expired' for the audit trail."""
    store = ApprovalStore(path=tmp_path / "approvals.sqlite")
    # ttl=0 so the entry is immediately expired on the next prune, regardless
    # of wall-clock timing (robust under any test event loop).
    mgr = ExecApprovalManager(
        ttl=0, store=store, allowlist_path=tmp_path / "allow.sqlite"
    )

    async def go():
        rid, _ = await mgr.register(tool_name="deploy", arguments={})
        # Trigger a prune via a query; expiry write is scheduled on the loop.
        assert mgr.list_pending() == []  # entry pruned
        # Await the scheduled durable-expiry task(s) so the assertion is
        # deterministic rather than timing-dependent.
        assert mgr._bg_tasks, "prune should schedule a durable expiry task"
        await asyncio.gather(*list(mgr._bg_tasks), return_exceptions=True)
        return store.get(rid)

    row = asyncio.run(go())
    assert row is not None
    assert row["status"] == "expired"


def test_resolver_identity_recorded_in_audit_trail(tmp_path):
    """resolve() records the resolving principal on the durable audit row."""
    store = ApprovalStore(path=tmp_path / "approvals.sqlite")
    mgr = ExecApprovalManager(
        ttl=300, store=store, allowlist_path=tmp_path / "allow.sqlite"
    )

    async def go():
        rid, future = await mgr.register(tool_name="shell_exec", arguments={})
        mgr.resolve(rid, Resolution(approved=True, resolver="operator:alice"))
        for _ in range(100):
            if store.pending_count() == 0:
                break
            await asyncio.sleep(0.01)
        return rid, await future

    rid, _ = asyncio.run(go())
    row = store.get(rid)
    assert row is not None
    assert row["approver"] == "operator:alice"


def test_resolver_identity_defaults_to_gateway(tmp_path):
    """No resolver keeps today's anonymous ``gateway`` attribution."""
    store = ApprovalStore(path=tmp_path / "approvals.sqlite")
    mgr = ExecApprovalManager(
        ttl=300, store=store, allowlist_path=tmp_path / "allow.sqlite"
    )

    async def go():
        rid, future = await mgr.register(tool_name="shell_exec", arguments={})
        mgr.resolve(rid, Resolution(approved=True))
        for _ in range(100):
            if store.pending_count() == 0:
                break
            await asyncio.sleep(0.01)
        return rid, await future

    rid, _ = asyncio.run(go())
    assert store.get(rid)["approver"] == "gateway"


def test_authorized_reviewer_binding_rejects_other_operator(tmp_path):
    """A bound request cannot be resolved by an unauthorised operator."""
    mgr = ExecApprovalManager(ttl=300, durable=False)

    async def go():
        rid, future = await mgr.register(
            tool_name="deploy",
            arguments={},
            authorized_reviewers=["operator:alice"],
        )
        # Wrong operator is rejected and the request stays pending.
        assert mgr.resolve(rid, Resolution(approved=True, resolver="operator:bob")) is False
        assert mgr.get_pending(rid) is not None
        # Authorised operator resolves (first-answer-wins preserved).
        assert mgr.resolve(rid, Resolution(approved=True, resolver="operator:alice")) is True
        return await future

    res = asyncio.run(go())
    assert res.approved is True


def test_unbound_request_resolvable_by_anyone(tmp_path):
    """Without a reviewer binding any resolver may resolve (legacy behaviour)."""
    mgr = ExecApprovalManager(ttl=300, durable=False)

    async def go():
        rid, future = await mgr.register(tool_name="deploy", arguments={})
        assert mgr.resolve(rid, Resolution(approved=True, resolver="operator:bob")) is True
        return await future

    assert asyncio.run(go()).approved is True


def test_authorized_reviewers_survive_restart(tmp_path):
    """Per-request custody binding is durable across a rehydrate."""
    store = ApprovalStore(path=tmp_path / "approvals.sqlite")
    allow_path = tmp_path / "allow.sqlite"

    async def register_only():
        mgr = ExecApprovalManager(ttl=300, store=store, allowlist_path=allow_path)
        rid, _ = await mgr.register(
            tool_name="deploy",
            arguments={},
            authorized_reviewers=["operator:alice"],
        )
        return rid

    rid = asyncio.run(register_only())

    async def restart_and_check():
        mgr2 = ExecApprovalManager(ttl=300, store=store, allowlist_path=allow_path)
        await mgr2.rehydrate()
        req = mgr2.get_pending(rid)
        # Wrong operator still rejected after restart.
        assert mgr2.resolve(rid, Resolution(approved=True, resolver="operator:bob")) is False
        assert mgr2.resolve(rid, Resolution(approved=True, resolver="operator:alice")) is True
        return req

    req = asyncio.run(restart_and_check())
    assert req is not None
    assert req.authorized_reviewers == frozenset({"operator:alice"})


def test_allow_always_grant_persists_across_manager_restart(tmp_path):
    """allow_always via resolve() persists and short-circuits after restart."""
    store = ApprovalStore(path=tmp_path / "approvals.sqlite")
    allow_path = tmp_path / "allow.sqlite"

    async def grant():
        mgr = ExecApprovalManager(
            ttl=300, store=store, allowlist_path=allow_path
        )
        rid, future = await mgr.register(tool_name="safe_tool", arguments={})
        # scope_to_agent=False grants globally (any agent), matching the
        # legacy "allow-always for this tool everywhere" behaviour.
        mgr.resolve(
            rid,
            Resolution(approved=True, allow_always=True, scope_to_agent=False),
        )
        await future

    asyncio.run(grant())
    assert allow_path.exists()

    async def restart_fast_path():
        mgr2 = ExecApprovalManager(
            ttl=300, store=store, allowlist_path=allow_path
        )
        rid, future = await mgr2.register(tool_name="safe_tool", arguments={})
        return rid, await future

    rid, res = asyncio.run(restart_fast_path())
    assert rid == "auto"
    assert res.approved is True


def test_gateway_backend_forwards_authorized_reviewers(tmp_path):
    """The production backend must bind per-request reviewer custody.

    Regression guard: ``GatewayApprovalBackend`` previously dropped
    ``ApprovalRequest.authorized_reviewers`` on the way to ``register()``,
    leaving every request unbound. This verifies the custody set reaches the
    manager so an unauthorised operator is rejected end-to-end.
    """
    from praisonaiagents.approval.protocols import ApprovalRequest
    from praisonai_bot.gateway.gateway_approval import GatewayApprovalBackend

    mgr = ExecApprovalManager(ttl=300, allowlist_path=tmp_path / "allow.sqlite")
    backend = GatewayApprovalBackend(manager=mgr, timeout=5)

    async def go():
        request = ApprovalRequest(
            tool_name="deploy",
            arguments={"target": "prod"},
            risk_level="high",
            agent_name="deployer",
            authorized_reviewers=["operator:alice"],
        )
        task = asyncio.create_task(backend.request_approval(request))
        # Let the backend register the pending request.
        await asyncio.sleep(0)
        pending = mgr.list_pending()
        assert len(pending) == 1
        rid = pending[0]["request_id"]

        # The bound pending request carries the custody set.
        req = mgr.get_pending(rid)
        assert req is not None
        assert req.authorized_reviewers == frozenset({"operator:alice"})

        # An unauthorised operator cannot resolve it.
        assert mgr.resolve(
            rid, Resolution(approved=True, resolver="operator:bob")
        ) is False
        # The authorised operator can, completing the awaited request.
        assert mgr.resolve(
            rid, Resolution(approved=True, resolver="operator:alice")
        ) is True
        decision = await task
        assert decision.approved is True

    asyncio.run(go())
