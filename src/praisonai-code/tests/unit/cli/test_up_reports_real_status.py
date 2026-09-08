"""`praisonai up` must not report a dead service as running.

Two defects compounded:

1. `add_service` returned the Popen whenever the *spawn* succeeded. A bad
   flag, a missing dependency or a taken port all exit immediately, and the
   command printed "✅ Langflow started (PID: N)" for them. `stderr` goes to
   DEVNULL, so the reason was discarded too.

2. `services_started.append(...)` ran BEFORE the health check, and the check's
   return value was thrown away at both call sites -- `wait_for_service`
   returns a bool and nothing read it. A service that timed out printed a
   yellow warning and was then rendered "✅ Running" in a table titled
   "🎉 Services Ready", and the command exited 0.

So `praisonai up` reported success for services that were not running, which
is the worst possible answer for a command whose only job is to start them.
"""
import sys

import pytest

import praisonai_code.cli.commands.up as up


@pytest.fixture
def manager():
    mgr = up.ServiceManager()
    yield mgr
    for proc in list(mgr.services):
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass


class TestADeadServiceIsNotStarted:

    def test_a_process_that_exits_immediately_returns_none(self, manager):
        result = manager.add_service(
            [sys.executable, "-c", "import sys; sys.exit(1)"], "Langflow")
        assert result is None, "a service that died was reported as started"

    def test_it_is_not_left_in_the_managed_list(self, manager):
        manager.add_service(
            [sys.executable, "-c", "import sys; sys.exit(1)"], "Langflow")
        assert manager.services == [], (
            "a dead process stayed in the shutdown list"
        )

    def test_a_nonzero_exit_is_still_a_failure(self, manager):
        """Exit 0 immediately is also not a running service."""
        assert manager.add_service(
            [sys.executable, "-c", "pass"], "Langflow") is None


class TestALiveServiceStillWorks:

    def test_a_running_process_is_returned(self, manager):
        proc = manager.add_service(
            [sys.executable, "-c", "import time; time.sleep(30)"], "Langfuse")
        assert proc is not None
        assert proc.poll() is None

    def test_it_is_tracked_for_shutdown(self, manager):
        proc = manager.add_service(
            [sys.executable, "-c", "import time; time.sleep(30)"], "Langfuse")
        assert proc in manager.services


class TestHealthCheckResultIsUsed:

    def test_an_unreachable_service_reports_false(self, manager):
        """The bool that both call sites used to discard."""
        assert manager.wait_for_service(
            "http://127.0.0.1:59997", "Langflow", timeout=1) is False

    def test_the_command_gates_on_that_result(self):
        """Guards the wiring, not just the helper.

        Asserted against the source because driving the whole `up` command
        needs Langflow and Langfuse installed. What must hold is that the
        append happens after a checked health call, not before an unchecked
        one.
        """
        import inspect

        source = inspect.getsource(up)
        assert "if wait_timeout > 0 and not manager.wait_for_service(" in source, (
            "the health check result is not being tested"
        )
        assert "if False:" not in source
        for service in ("Langfuse", "Langflow"):
            gate = source.index(f'raise RuntimeError("{service} never became healthy")')
            append = source.index(f'services_started.append(("{service}"')
            assert gate < append, (
                f"{service} is recorded as started before its health is checked"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
