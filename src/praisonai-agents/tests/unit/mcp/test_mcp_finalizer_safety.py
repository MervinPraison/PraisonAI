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
