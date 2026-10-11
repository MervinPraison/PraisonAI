"""``MCP.__del__`` must never block the garbage collector.

It used to call ``shutdown()``, which takes the class-level non-reentrant
``_active_server_names_lock`` and joins the stdio runner thread for up to the
operation timeout (60 s by default).
"""
import threading

from praisonaiagents.mcp.mcp import MCP


def _bare_mcp(names=("srv",)):
    m = MCP.__new__(MCP)
    m.runner = None
    m._registered_server_names = None
    m._adopt_registered_names(tuple(names))
    return m


def _run_with_timeout(fn, seconds=3.0):
    done = threading.Event()
    def target():
        fn()
        done.set()
    threading.Thread(target=target, daemon=True).start()
    return done.wait(seconds)


def test_finalizer_does_not_block_on_the_server_names_lock():
    m = _bare_mcp(("fin-a",))
    with MCP._active_server_names_lock:   # GC fires while this thread holds it
        assert _run_with_timeout(m.__del__), "MCP.__del__ blocked on _active_server_names_lock"
    # The deferred release is applied by the next lock holder.
    assert "fin-a" not in MCP.list_active_server_names()


def test_finalizer_releases_names_immediately_when_the_lock_is_free():
    m = _bare_mcp(("fin-b",))
    assert "fin-b" in MCP.list_active_server_names()
    m.__del__()
    assert "fin-b" not in MCP.list_active_server_names()


def test_finalizer_does_not_join_the_runner_thread():
    class SlowRunner:
        joined = False
        signalled = False
        def shutdown(self):
            self.signalled = True
        def stop(self, timeout=None):
            self.joined = True
        def is_alive(self):
            return True

    m = _bare_mcp(("fin-c",))
    m.runner = SlowRunner()
    m.__del__()
    assert m.runner.signalled and not m.runner.joined


def test_explicit_shutdown_still_joins_and_releases():
    class Runner:
        joined = False
        def shutdown(self):
            pass
        def stop(self, timeout=None):
            self.joined = True
        def is_alive(self):
            return False

    m = _bare_mcp(("fin-d",))
    runner = m.runner = Runner()
    m.shutdown()
    assert runner.joined
    assert "fin-d" not in MCP.list_active_server_names()


def test_finalizer_does_not_wait_for_the_websocket_close():
    import asyncio
    from praisonaiagents.mcp.mcp_websocket import WebSocketMCPClient

    loop = asyncio.new_event_loop()   # the session's loop; not running yet,
    ws = WebSocketMCPClient.__new__(WebSocketMCPClient)   # so a waiting close() would hang
    ws._closed = False
    ws.transport = None
    ws._loop = loop
    scheduled = []

    async def aclose():
        scheduled.append(True)

    ws.aclose = aclose
    m = _bare_mcp(("fin-e",))
    m.websocket_client = ws
    try:
        assert _run_with_timeout(m.__del__, seconds=2.0), "MCP.__del__ waited on the WebSocket close"
        # The close was still scheduled on the session's loop, not skipped.
        loop.run_until_complete(asyncio.sleep(0.05))
        assert scheduled == [True], "finalizer skipped the WebSocket cleanup"
    finally:
        loop.close()
    assert "fin-e" not in MCP.list_active_server_names()


def test_websocket_close_uses_the_sessions_loop_from_another_thread():
    """close() (and __del__) on a thread other than the one that connected must
    schedule cleanup on the loop that owns the session, not that thread's own
    idle thread-local loop, or the WebSocket is never closed."""
    import asyncio
    from praisonaiagents.mcp import mcp_websocket as ws

    owner = asyncio.new_event_loop()
    t = threading.Thread(target=owner.run_forever, daemon=True)
    t.start()
    try:
        client = ws.WebSocketMCPClient.__new__(ws.WebSocketMCPClient)
        client._closed = False
        client._loop = owner
        closed = threading.Event()

        async def aclose():
            closed.set()

        client.aclose = aclose
        threading.Thread(target=lambda: client.close(wait=False), daemon=True).start()
        assert closed.wait(3.0), "cleanup was not scheduled on the session's loop"
    finally:
        owner.call_soon_threadsafe(owner.stop)
        t.join(2)


def test_websocket_close_before_connect_does_not_create_a_loop():
    from praisonaiagents.mcp import mcp_websocket as ws

    client = ws.WebSocketMCPClient.__new__(ws.WebSocketMCPClient)
    client._closed = False
    client._loop = None
    client.close(wait=False)
    assert client._closed
