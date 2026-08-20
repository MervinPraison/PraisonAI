"""A denied approval must actually block execution.

`tests/unit/test_tool_decorator_approval.py` only asserts registration metadata
(`requires_approval is True`, `get_risk_level(...) == "critical"`), so deleting
the `raise PermissionError` in `require_approval`'s sync *and* async wrappers
left the whole approval suite green. These tests exercise behaviour: they assert
the PermissionError *and* that the wrapped function body never ran, via a
side-effect flag that a metadata-only assertion cannot see.
"""
import asyncio

import pytest

from praisonaiagents.approval import (
    ApprovalDecision,
    clear_approval_context,
    get_approval_registry,
    remove_approval_requirement,
    require_approval,
)


class _StubBackend:
    """Approval backend returning a fixed decision (or raising)."""

    def __init__(self, decision=None, raises=None):
        self._decision = decision
        self._raises = raises
        self.calls = []

    async def request_approval(self, request):
        self.calls.append(request)
        if self._raises is not None:
            raise self._raises
        return self._decision


@pytest.fixture
def approval_env(monkeypatch):
    """Isolate the global approval registry and neutralise auto-approve escapes."""
    monkeypatch.delenv("PRAISONAI_AUTO_APPROVE", raising=False)
    reg = get_approval_registry()
    clear_approval_context()

    installed = []

    def install(backend):
        reg.set_backend(backend)
        installed.append(backend)
        return backend

    yield install

    reg.remove_backend()
    clear_approval_context()


# ── side-effect probes ───────────────────────────────────────────────────────

SIDE_EFFECTS = []


@require_approval(risk_level="critical")
def wipe_database(target: str) -> str:
    """Sync gated tool. Appends to SIDE_EFFECTS if the body ever runs."""
    SIDE_EFFECTS.append(("sync", target))
    return f"wiped {target}"


@require_approval(risk_level="critical")
async def wipe_database_async(target: str) -> str:
    """Async gated tool. Appends to SIDE_EFFECTS if the body ever runs."""
    SIDE_EFFECTS.append(("async", target))
    return f"wiped {target}"


@pytest.fixture(autouse=True)
def _reset_side_effects():
    SIDE_EFFECTS.clear()
    yield
    SIDE_EFFECTS.clear()


def teardown_module(_module):
    remove_approval_requirement("wipe_database")
    remove_approval_requirement("wipe_database_async")


class TestDeniedApprovalBlocksExecution:
    def test_sync_denial_raises_permission_error(self, approval_env):
        approval_env(_StubBackend(ApprovalDecision(approved=False, reason="nope")))

        with pytest.raises(PermissionError, match="denied"):
            wipe_database("prod")

    def test_sync_denial_does_not_run_the_body(self, approval_env):
        approval_env(_StubBackend(ApprovalDecision(approved=False, reason="nope")))

        with pytest.raises(PermissionError):
            wipe_database("prod")

        assert SIDE_EFFECTS == [], "denied tool body executed anyway"

    def test_async_denial_raises_permission_error(self, approval_env):
        approval_env(_StubBackend(ApprovalDecision(approved=False, reason="nope")))

        with pytest.raises(PermissionError, match="denied"):
            asyncio.run(wipe_database_async("prod"))

    def test_async_denial_does_not_run_the_body(self, approval_env):
        approval_env(_StubBackend(ApprovalDecision(approved=False, reason="nope")))

        with pytest.raises(PermissionError):
            asyncio.run(wipe_database_async("prod"))

        assert SIDE_EFFECTS == [], "denied async tool body executed anyway"

    def test_denial_is_not_cached_as_an_approval(self, approval_env):
        """A first denial must not seed the approved-args cache."""
        backend = approval_env(
            _StubBackend(ApprovalDecision(approved=False, reason="nope"))
        )

        for _ in range(2):
            with pytest.raises(PermissionError):
                wipe_database("prod")

        assert SIDE_EFFECTS == []
        assert len(backend.calls) == 2, "second call skipped the approval backend"


class TestApprovalPositiveControls:
    """Without these, the denial tests could pass on a tool that never runs at all."""

    def test_sync_approval_runs_the_body(self, approval_env):
        approval_env(_StubBackend(ApprovalDecision(approved=True, reason="ok")))

        assert wipe_database("staging") == "wiped staging"
        assert SIDE_EFFECTS == [("sync", "staging")]

    def test_async_approval_runs_the_body(self, approval_env):
        approval_env(_StubBackend(ApprovalDecision(approved=True, reason="ok")))

        assert asyncio.run(wipe_database_async("staging")) == "wiped staging"
        assert SIDE_EFFECTS == [("async", "staging")]

    def test_modified_args_are_applied(self, approval_env):
        """The approver may rewrite arguments; the rewrite must reach the body."""
        approval_env(
            _StubBackend(
                ApprovalDecision(
                    approved=True, reason="ok", modified_args={"target": "sandbox"}
                )
            )
        )

        assert wipe_database(target="prod") == "wiped sandbox"
        assert SIDE_EFFECTS == [("sync", "sandbox")]


class TestApprovalFailsClosed:
    def test_backend_error_blocks_execution(self, approval_env):
        """A broken backend must deny, not fall through to execution."""
        approval_env(_StubBackend(raises=RuntimeError("backend exploded")))

        with pytest.raises(PermissionError, match="Approval request failed"):
            wipe_database("prod")

        assert SIDE_EFFECTS == [], "tool ran despite a failed approval request"

    def test_sync_tool_called_from_async_context_is_refused(self, approval_env):
        """The sync wrapper cannot do console I/O on the loop, so it must refuse."""
        approval_env(_StubBackend(ApprovalDecision(approved=True, reason="ok")))
        # No backend can rescue this: the sync wrapper refuses *before* asking,
        # because it cannot do console I/O from a running event loop.
        get_approval_registry().remove_backend()

        async def caller():
            return wipe_database("prod")

        with pytest.raises(PermissionError, match="Approval request failed"):
            asyncio.run(caller())

        assert SIDE_EFFECTS == [], "tool ran from an async context without approval"
