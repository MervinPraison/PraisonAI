"""Tests for durable gateway approvals (persistence + rehydration).

Verifies that:
  - pending approvals persisted to an ``ApprovalStoreProtocol`` store survive a
    simulated restart and are rehydrated on boot;
  - ``allow_always`` grants persisted to a JSON allowlist survive a restart;
  - the default in-memory path is unchanged when no store is configured.
"""

import asyncio

import pytest

from praisonai.bots import ApprovalStore
from praisonai.gateway.exec_approval import (
    ExecApprovalManager,
    PermissionAllowlist,
    Resolution,
)


def test_allowlist_in_memory_default(tmp_path):
    """Without a path the allowlist is in-memory only (no file created)."""
    al = PermissionAllowlist()
    al.add("shell_exec")
    assert "shell_exec" in al
    assert not list(tmp_path.iterdir())


def test_allowlist_persists_and_reloads(tmp_path):
    """allow_always grants survive a restart via the JSON allowlist file."""
    path = tmp_path / "allow.json"
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
    mgr = ExecApprovalManager(ttl=300, store=store)

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
        mgr = ExecApprovalManager(ttl=300, store=store)
        rid, _ = await mgr.register(
            tool_name="deploy",
            arguments={"env": "prod"},
            agent_name="deployer",
        )
        return rid

    rid = asyncio.run(register_only())

    # Simulate restart: brand-new manager, same store.
    async def restart_and_rehydrate():
        mgr2 = ExecApprovalManager(ttl=300, store=store)
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
    mgr = ExecApprovalManager(ttl=300, store=store)

    async def go():
        rid, future = await mgr.register(
            tool_name="shell_exec",
            arguments={"cmd": "rm -rf /tmp/x"},
        )
        mgr.resolve(rid, Resolution(approved=True, reason="ok"))
        # Let the scheduled durable-resolve task run.
        await asyncio.sleep(0.05)
        return rid, await future

    rid, resolution = asyncio.run(go())
    assert resolution.approved is True
    assert store.pending_count() == 0
    row = store.get(rid)
    assert row is not None
    assert row["status"] == "approved"


def test_no_store_is_in_memory_only():
    """Without a store the manager behaves exactly as before."""
    mgr = ExecApprovalManager(ttl=300)

    async def go():
        rid, future = await mgr.register(tool_name="t", arguments={})
        assert mgr.list_pending()[0]["request_id"] == rid
        mgr.resolve(rid, Resolution(approved=False))
        return await future

    res = asyncio.run(go())
    assert res.approved is False
    assert asyncio.run(mgr.rehydrate()) == 0


def test_allow_always_grant_persists_across_manager_restart(tmp_path):
    """allow_always via resolve() persists and short-circuits after restart."""
    store = ApprovalStore(path=tmp_path / "approvals.sqlite")
    allow_path = tmp_path / "allow.json"

    async def grant():
        mgr = ExecApprovalManager(
            ttl=300, store=store, allowlist_path=allow_path
        )
        rid, future = await mgr.register(tool_name="safe_tool", arguments={})
        mgr.resolve(rid, Resolution(approved=True, allow_always=True))
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
