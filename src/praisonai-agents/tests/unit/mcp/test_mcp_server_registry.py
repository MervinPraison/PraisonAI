"""Regression tests for the MCP server-registry lifecycle (issue #5135).

The process-level registry backing skills' CapabilityValidator must shrink when
a server goes away, so a disconnected server stops satisfying a skill
requirement instead of staying visible forever.
"""

import threading

import pytest


def _make_mcp():
    """An MCP instance built without __init__: no transports, no tools."""
    from praisonaiagents.mcp.mcp import MCP

    mcp = MCP.__new__(MCP)
    mcp._tool_prefix = None
    mcp._registered_server_names = None
    mcp._tools = []
    return mcp


@pytest.fixture(autouse=True)
def isolated_registry():
    """Keep one test's registrations from leaking into the next."""
    from praisonaiagents.mcp.mcp import MCP

    saved = dict(MCP._active_server_names)
    MCP._active_server_names = {}
    yield
    MCP._active_server_names = saved


def test_registry_shrinks_on_shutdown():
    """A name added by with_tool_prefix() must disappear once the client shuts
    down — otherwise CapabilityValidator keeps reporting it as available."""
    from praisonaiagents.mcp.mcp import MCP

    mcp = _make_mcp()
    mcp.with_tool_prefix("docs")

    assert "docs" in MCP.list_active_server_names()

    mcp.shutdown()

    assert "docs" not in MCP.list_active_server_names()


def test_shutdown_is_idempotent():
    """shutdown() runs from several paths (explicit call, __exit__, __del__), so
    releasing a registration twice must not corrupt the count."""
    from praisonaiagents.mcp.mcp import MCP

    mcp = _make_mcp()
    mcp.with_tool_prefix("docs")

    mcp.shutdown()
    mcp.shutdown()
    mcp.shutdown()

    assert MCP.list_active_server_names() == set()
    assert MCP._active_server_names.get("docs", 0) == 0


def test_shared_name_survives_until_last_client_shuts_down():
    """Two clients may declare the same server name; closing one must not hide
    the name for the one still connected."""
    from praisonaiagents.mcp.mcp import MCP

    first = _make_mcp()
    second = _make_mcp()
    first.with_tool_prefix("docs")
    second.with_tool_prefix("docs")

    first.shutdown()
    assert "docs" in MCP.list_active_server_names()

    second.shutdown()
    assert "docs" not in MCP.list_active_server_names()


def test_shutdown_without_prefix_is_a_noop():
    """A single-server run never calls with_tool_prefix(); shutdown() must not
    touch the registry in that case."""
    from praisonaiagents.mcp.mcp import MCP

    prefixed = _make_mcp()
    prefixed.with_tool_prefix("keepme")

    unprefixed = _make_mcp()
    unprefixed.shutdown()

    assert MCP.list_active_server_names() == {"keepme"}


def test_invalid_prefix_registers_nothing():
    """with_tool_prefix() rejects a name with no usable characters and must
    leave no partial registration behind."""
    from praisonaiagents.mcp.mcp import MCP

    mcp = _make_mcp()
    with pytest.raises(ValueError):
        mcp.with_tool_prefix("___")

    assert MCP.list_active_server_names() == set()


def test_reapplying_same_prefix_does_not_double_count():
    """Re-applying an identical prefix must not need two shutdowns to clear."""
    from praisonaiagents.mcp.mcp import MCP

    mcp = _make_mcp()
    mcp.with_tool_prefix("docs")
    mcp.with_tool_prefix("docs")

    mcp.shutdown()

    assert MCP.list_active_server_names() == set()


def test_reprefixing_releases_the_previous_name():
    """Changing a client's prefix must release the names registered for the
    previous one instead of leaking them."""
    from praisonaiagents.mcp.mcp import MCP

    mcp = _make_mcp()
    mcp.with_tool_prefix("old")
    mcp.with_tool_prefix("new")

    assert MCP.list_active_server_names() == {"new"}


def test_rename_sanitizing_to_the_same_prefix_refreshes_the_spelling():
    """A rename that sanitizes to the same prefix still changes the original
    spelling, which is what a skill requirement may name, so it must not be
    skipped as a no-op."""
    from praisonaiagents.mcp.mcp import MCP

    mcp = _make_mcp()
    mcp.with_tool_prefix("my-server")
    mcp.with_tool_prefix("my server")

    assert MCP.list_active_server_names() == {"my server", "my_server"}


def test_both_spellings_registered_and_released_together():
    """The original and sanitized spellings are both stored so a skill
    requirement matches either; one shutdown must release both."""
    from praisonaiagents.mcp.mcp import MCP

    mcp = _make_mcp()
    mcp.with_tool_prefix("my-server")

    assert MCP.list_active_server_names() == {"my-server", "my_server"}

    mcp.shutdown()

    assert MCP.list_active_server_names() == set()


def test_list_active_server_names_still_returns_a_set():
    """The public return type is unchanged even though the registry now counts."""
    from praisonaiagents.mcp.mcp import MCP

    mcp = _make_mcp()
    mcp.with_tool_prefix("docs")

    assert isinstance(MCP.list_active_server_names(), set)


def test_concurrent_register_and_unregister_settle_at_zero():
    """Registration and release are lock-guarded; concurrent churn must not
    leave a stale entry behind."""
    from praisonaiagents.mcp.mcp import MCP

    clients = [_make_mcp() for _ in range(20)]
    barrier = threading.Barrier(len(clients))
    errors = []

    def _churn(client):
        # Collected rather than raised: an exception inside a thread would
        # otherwise be swallowed and let this test pass vacuously.
        try:
            barrier.wait()
            client.with_tool_prefix("shared")
            client.shutdown()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_churn, args=(client,)) for client in clients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert MCP.list_active_server_names() == set()


def test_concurrent_shutdown_on_one_instance_releases_only_once():
    """Concurrent lifecycle calls on the *same* instance must not each consume
    the registration: exactly one caller may claim it. Otherwise a second
    client sharing the name loses its count and disappears from the registry
    while still connected."""
    import sys

    from praisonaiagents.mcp.mcp import MCP

    survivor = _make_mcp()
    survivor.with_tool_prefix("shared")

    errors = []
    previous_interval = sys.getswitchinterval()
    try:
        # The claim window is only a couple of bytecodes wide, so the default
        # 5 ms GIL interval rarely interleaves it. Shrink it and repeat, checking
        # the surviving client's count after every round: a set-valued check at
        # the end would hide the drift, because a later round re-registers the name.
        sys.setswitchinterval(1e-6)
        for _ in range(50):
            target = _make_mcp()
            target.with_tool_prefix("shared")
            assert MCP._active_server_names.get("shared") == 2

            barrier = threading.Barrier(16)

            def _shutdown(client=target):
                try:
                    barrier.wait()
                    client.shutdown()
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=_shutdown) for _ in range(16)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            # Only one of the 16 callers may release the target's registration.
            assert MCP._active_server_names.get("shared") == 1
    finally:
        sys.setswitchinterval(previous_interval)

    assert errors == []
    # The survivor still holds the name.
    assert MCP.list_active_server_names() == {"shared"}

    survivor.shutdown()
    assert MCP.list_active_server_names() == set()


def test_remove_mcp_server_clears_capability_gating():
    """End-to-end: Agent.remove_mcp_server() must stop the server from
    satisfying a skill requirement, not just drop it from the agent."""
    from praisonaiagents import Agent
    from praisonaiagents.mcp.mcp import MCP
    from praisonaiagents.skills.capability_validator import CapabilityValidator

    mcp = _make_mcp()
    mcp.with_tool_prefix("files")

    agent = Agent(instructions="test", llm="gpt-4o-mini")
    agent.add_mcp_server("files", mcp)

    assert "files" in CapabilityValidator()._get_available_servers()

    assert agent.remove_mcp_server("files") is True

    assert "files" not in CapabilityValidator()._get_available_servers()
