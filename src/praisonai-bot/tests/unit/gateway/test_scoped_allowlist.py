"""Tests for the durable, scoped exec-approval allow-list (issue #2619).

Covers:
  - Durability: "allow always" grants survive a restart (new manager on the
    same SQLite path).
  - Scoping: a grant for one agent does not authorise a different agent.
  - Argument scoping: an arg-signature grant matches only the same arguments.
  - Fail-closed rehydration: a fresh manager only re-applies persisted grants.
  - Backward compatibility: the legacy name-only API still works.
"""

import pytest

from praisonai_bot.gateway.exec_approval import (
    ANY_AGENT,
    ExecApprovalManager,
    PermissionAllowlist,
    Resolution,
    ScopedAllowlistStore,
    make_arg_signature,
)


@pytest.fixture
def store_path(tmp_path):
    return tmp_path / "approvals.sqlite"


# ── ScopedAllowlistStore ─────────────────────────────────────────────

def test_store_add_and_allows_scoped(store_path):
    store = ScopedAllowlistStore(path=store_path)
    store.add(agent_id="agent-a", tool_name="shell")

    assert store.allows(agent_id="agent-a", tool_name="shell") is True
    # Different agent is NOT authorised by a scoped grant.
    assert store.allows(agent_id="agent-b", tool_name="shell") is False


def test_store_any_agent_grant_covers_everyone(store_path):
    store = ScopedAllowlistStore(path=store_path)
    store.add(agent_id=ANY_AGENT, tool_name="shell")
    assert store.allows(agent_id="anyone", tool_name="shell") is True


def test_store_arg_signature_scoping(store_path):
    store = ScopedAllowlistStore(path=store_path)
    sig = make_arg_signature({"cmd": "ls"})
    store.add(agent_id="agent-a", tool_name="shell", arg_signature=sig)

    assert store.allows(agent_id="agent-a", tool_name="shell", arg_signature=sig)
    other = make_arg_signature({"cmd": "rm -rf /"})
    assert not store.allows(
        agent_id="agent-a", tool_name="shell", arg_signature=other
    )


def test_store_tool_level_grant_covers_any_args(store_path):
    store = ScopedAllowlistStore(path=store_path)
    store.add(agent_id="agent-a", tool_name="shell")  # no arg signature
    sig = make_arg_signature({"cmd": "anything"})
    assert store.allows(agent_id="agent-a", tool_name="shell", arg_signature=sig)


def test_store_durable_across_instances(store_path):
    store1 = ScopedAllowlistStore(path=store_path)
    store1.add(agent_id="agent-a", tool_name="shell")

    # Simulate restart: brand new store on same path.
    store2 = ScopedAllowlistStore(path=store_path)
    assert store2.allows(agent_id="agent-a", tool_name="shell") is True


def test_store_revoke(store_path):
    store = ScopedAllowlistStore(path=store_path)
    store.add(agent_id="agent-a", tool_name="shell")
    assert store.revoke(agent_id="agent-a", tool_name="shell") is True
    assert store.allows(agent_id="agent-a", tool_name="shell") is False
    # Revoking again is a no-op.
    assert store.revoke(agent_id="agent-a", tool_name="shell") is False


def test_arg_signature_is_order_independent():
    a = make_arg_signature({"x": 1, "y": 2})
    b = make_arg_signature({"y": 2, "x": 1})
    assert a == b
    assert make_arg_signature({}) is None
    assert make_arg_signature(None) is None


# ── PermissionAllowlist (backward-compatible shim) ───────────────────

def test_allowlist_legacy_api(store_path):
    al = PermissionAllowlist(path=store_path)
    al.add("legacy_tool")
    assert "legacy_tool" in al
    assert al.list() == ["legacy_tool"]
    assert al.remove("legacy_tool") is True
    assert "legacy_tool" not in al


def test_allowlist_scoped_does_not_leak(store_path):
    al = PermissionAllowlist(path=store_path)
    al.add_scoped(agent_id="agent-a", tool_name="shell")
    assert al.allows(agent_id="agent-a", tool_name="shell") is True
    assert al.allows(agent_id="agent-b", tool_name="shell") is False
    # Legacy name-only membership only sees ANY_AGENT grants, so a scoped grant
    # must NOT appear as a global grant.
    assert "shell" not in al


def test_allowlist_rehydrates_on_restart(store_path):
    al1 = PermissionAllowlist(path=store_path)
    al1.add_scoped(agent_id="agent-a", tool_name="shell")

    al2 = PermissionAllowlist(path=store_path)  # simulate restart
    assert al2.allows(agent_id="agent-a", tool_name="shell") is True


def test_allowlist_non_durable_is_memory_only(store_path):
    al = PermissionAllowlist(path=store_path, durable=False)
    al.add_scoped(agent_id="agent-a", tool_name="shell")
    assert al.allows(agent_id="agent-a", tool_name="shell") is True
    # Nothing was persisted to the configured path.
    assert not store_path.exists()


# ── ExecApprovalManager integration ──────────────────────────────────

@pytest.mark.asyncio
async def test_manager_allow_always_is_scoped_to_agent(store_path):
    mgr = ExecApprovalManager(allowlist_path=store_path)

    req_id, future = await mgr.register(
        tool_name="shell", arguments={"cmd": "ls"}, agent_name="agent-a",
    )
    assert mgr.resolve(req_id, Resolution(approved=True, allow_always=True))
    await future

    # Same agent → auto-approved.
    _id, fut_a = await mgr.register(
        tool_name="shell", arguments={"cmd": "ls"}, agent_name="agent-a",
    )
    res_a = await fut_a
    assert res_a.approved is True and res_a.reason == "allow-always"

    # Different agent → still needs approval (no auto).
    id_b, fut_b = await mgr.register(
        tool_name="shell", arguments={"cmd": "ls"}, agent_name="agent-b",
    )
    assert id_b != "auto"
    assert not fut_b.done()
    mgr.resolve(id_b, Resolution(approved=False, reason="cleanup"))
    await fut_b


@pytest.mark.asyncio
async def test_manager_allow_always_survives_restart(store_path):
    mgr1 = ExecApprovalManager(allowlist_path=store_path)
    req_id, future = await mgr1.register(
        tool_name="shell", arguments={}, agent_name="agent-a",
    )
    mgr1.resolve(req_id, Resolution(approved=True, allow_always=True))
    await future

    # Simulate gateway restart: brand-new manager on same durable path.
    mgr2 = ExecApprovalManager(allowlist_path=store_path)
    _id, fut = await mgr2.register(
        tool_name="shell", arguments={}, agent_name="agent-a",
    )
    res = await fut
    assert res.approved is True
    assert res.reason == "allow-always"


@pytest.mark.asyncio
async def test_manager_allow_always_can_widen_to_any_agent(store_path):
    mgr = ExecApprovalManager(allowlist_path=store_path)
    req_id, future = await mgr.register(
        tool_name="shell", arguments={}, agent_name="agent-a",
    )
    # Operator explicitly widens the grant to any agent.
    mgr.resolve(
        req_id,
        Resolution(approved=True, allow_always=True, scope_to_agent=False),
    )
    await future

    _id, fut = await mgr.register(
        tool_name="shell", arguments={}, agent_name="agent-z",
    )
    res = await fut
    assert res.approved is True


@pytest.mark.allow_sleep
def test_store_allows_enforces_ttl(store_path):
    # A grant older than the TTL must not authorise a call.
    store = ScopedAllowlistStore(path=store_path, ttl_seconds=1)
    store.add(agent_id="agent-a", tool_name="shell")
    assert store.allows(agent_id="agent-a", tool_name="shell") is True

    import time as _t
    _t.sleep(1.3)
    assert store.allows(agent_id="agent-a", tool_name="shell") is False


@pytest.mark.allow_sleep
def test_store_list_commits_eviction(store_path):
    store = ScopedAllowlistStore(path=store_path, ttl_seconds=1)
    store.add(agent_id="agent-a", tool_name="shell")

    import time as _t
    _t.sleep(1.3)
    # list() should evict AND persist the eviction.
    assert store.list() == []
    # A brand-new store instance (no in-memory state) confirms the row is gone.
    store2 = ScopedAllowlistStore(path=store_path, ttl_seconds=0)
    assert store2.list() == []


@pytest.mark.asyncio
async def test_manager_skips_scoped_grant_without_agent(store_path):
    # A scoped allow_always with no agent identity must NOT become a global grant.
    mgr = ExecApprovalManager(allowlist_path=store_path)
    req_id, future = await mgr.register(
        tool_name="shell", arguments={},  # no agent_name
    )
    mgr.resolve(req_id, Resolution(approved=True, allow_always=True))
    await future

    # No global grant leaked.
    assert "shell" not in mgr.allowlist
    # A different agent is still not auto-approved.
    _id, fut = await mgr.register(
        tool_name="shell", arguments={}, agent_name="agent-z",
    )
    assert _id != "auto"
    assert not fut.done()
    mgr.resolve(_id, Resolution(approved=False))
    await fut


@pytest.mark.asyncio
async def test_manager_allow_always_arg_scoped(store_path):
    mgr = ExecApprovalManager(allowlist_path=store_path)
    req_id, future = await mgr.register(
        tool_name="shell", arguments={"cmd": "ls"}, agent_name="agent-a",
    )
    mgr.resolve(
        req_id,
        Resolution(approved=True, allow_always=True, scope_to_args=True),
    )
    await future

    # Same args → auto-approved.
    _id, fut_same = await mgr.register(
        tool_name="shell", arguments={"cmd": "ls"}, agent_name="agent-a",
    )
    assert (await fut_same).approved is True

    # Different args → still needs approval.
    id_diff, fut_diff = await mgr.register(
        tool_name="shell", arguments={"cmd": "rm -rf /"}, agent_name="agent-a",
    )
    assert id_diff != "auto"
    assert not fut_diff.done()
    mgr.resolve(id_diff, Resolution(approved=False))
    await fut_diff
