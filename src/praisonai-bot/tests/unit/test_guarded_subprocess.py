"""Tests for the bounded subprocess wrapper.

The behaviour that matters: a command that would block forever returns, the
caller can still branch on returncode, and the stderr it gets back says *why*
the command stalled.
"""

import os
import subprocess
import sys

import pytest

from praisonai_bot._guarded_subprocess import (
    DEFAULT_TIMEOUT,
    TIMEOUT_RETURNCODE,
    diagnose,
    run_guarded,
)


class TestHappyPath:
    """A bounded call must stay a faithful subprocess.run replacement."""
    def test_returns_completed_process(self):
        result = run_guarded([sys.executable, "-c", "print('ok')"])
        assert result.returncode == 0
        assert result.stdout.strip() == "ok"

    def test_propagates_nonzero_exit(self):
        result = run_guarded([sys.executable, "-c", "import sys; sys.exit(3)"])
        assert result.returncode == 3

    def test_honours_cwd(self, tmp_path):
        result = run_guarded(
            [sys.executable, "-c", "import os; print(os.getcwd())"],
            cwd=str(tmp_path),
        )
        assert os.path.realpath(result.stdout.strip()) == os.path.realpath(str(tmp_path))


class TestTimeout:
    """A stalled command returns a value; it never raises and never blocks."""
    def test_hanging_command_returns_instead_of_blocking(self):
        result = run_guarded(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.5,
        )
        assert result.returncode == TIMEOUT_RETURNCODE

    def test_timeout_does_not_raise(self):
        # The whole point: existing `returncode == 0` call sites keep working
        # without growing an exception handler.
        run_guarded([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.3)

    def test_stderr_names_the_command_and_the_limit(self):
        result = run_guarded(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.4,
        )
        assert "killed after 0.4s" in result.stderr
        assert "time.sleep(30)" in result.stderr

    def test_reading_stdin_is_not_a_hang(self):
        # stdin is /dev/null, so a command that reads it gets EOF immediately
        # rather than waiting for the timeout to save it.
        result = run_guarded(
            [sys.executable, "-c", "import sys; sys.stdin.read(); print('done')"],
            timeout=5,
        )
        assert result.returncode == 0
        assert "done" in result.stdout


class TestDiagnosis:
    """Stall output is turned into guidance a caller can act on."""
    def test_credential_prompt(self):
        assert "credential prompt" in diagnose("Username for 'https://github.com':")

    def test_git_lock(self):
        msg = diagnose("fatal: Unable to create '/repo/.git/index.lock': File exists")
        assert "lock contention" in msg

    def test_confirmation_prompt(self):
        assert "confirmation prompt" in diagnose("Overwrite existing file? [y/N]")

    def test_host_key_prompt(self):
        assert "host-key" in diagnose("The authenticity of host ... key fingerprint is")

    def test_unknown_output_gets_generic_guidance(self):
        msg = diagnose("compiling module 41 of 900")
        assert "No interactive prompt was detected" in msg

    def test_empty_output_is_safe(self):
        # A process blocked on stdin often emits nothing at all.
        assert diagnose("") == diagnose(None)

    def test_diagnosis_is_attached_on_timeout(self):
        script = (
            "import sys, time; "
            "sys.stderr.write(\"Username for 'https://github.com':\"); "
            "sys.stderr.flush(); time.sleep(30)"
        )
        result = run_guarded([sys.executable, "-c", script], timeout=1.0)
        assert result.returncode == TIMEOUT_RETURNCODE
        assert "credential prompt" in result.stderr


class TestEnvironment:
    """Prompt suppression is layered under the caller, never over it."""
    def test_suppresses_git_prompting_by_default(self):
        result = run_guarded(
            [sys.executable, "-c", "import os; print(os.environ['GIT_TERMINAL_PROMPT'])"]
        )
        assert result.stdout.strip() == "0"

    def test_caller_env_wins(self):
        result = run_guarded(
            [sys.executable, "-c", "import os; print(os.environ['GIT_TERMINAL_PROMPT'])"],
            env={"GIT_TERMINAL_PROMPT": "1", "PATH": os.environ.get("PATH", "")},
        )
        assert result.stdout.strip() == "1"

    def test_interactive_mode_adds_no_suppression(self, monkeypatch):
        # Clear the ambient value first -- CI images commonly export
        # GIT_TERMINAL_PROMPT=0 already, which would mask the behaviour under
        # test. Interactive mode must not *introduce* the variable itself.
        monkeypatch.delenv("GIT_TERMINAL_PROMPT", raising=False)
        result = run_guarded(
            [
                sys.executable,
                "-c",
                "import os; print(os.environ.get('GIT_TERMINAL_PROMPT', 'unset'))",
            ],
            interactive=True,
        )
        assert result.stdout.strip() == "unset"

    def test_default_mode_suppresses_even_when_ambient_is_unset(self, monkeypatch):
        monkeypatch.delenv("GIT_TERMINAL_PROMPT", raising=False)
        result = run_guarded(
            [sys.executable, "-c", "import os; print(os.environ['GIT_TERMINAL_PROMPT'])"]
        )
        assert result.stdout.strip() == "0"


class TestTimeoutResolution:
    """Explicit argument beats env var beats default; junk never wins."""
    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("PRAISONAI_SUBPROCESS_TIMEOUT", "0.3")
        result = run_guarded([sys.executable, "-c", "import time; time.sleep(30)"])
        assert result.returncode == TIMEOUT_RETURNCODE

    @pytest.mark.parametrize("bad", ["", "abc", "0", "-5"])
    def test_unusable_override_falls_back_to_default(self, monkeypatch, bad):
        monkeypatch.setenv("PRAISONAI_SUBPROCESS_TIMEOUT", bad)
        # Must not raise, and must not adopt a non-positive timeout that would
        # kill every command instantly.
        result = run_guarded([sys.executable, "-c", "print('fine')"])
        assert result.returncode == 0
        assert DEFAULT_TIMEOUT > 0

    def test_explicit_timeout_beats_env(self, monkeypatch):
        monkeypatch.setenv("PRAISONAI_SUBPROCESS_TIMEOUT", "30")
        result = run_guarded(
            [sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.3
        )
        assert result.returncode == TIMEOUT_RETURNCODE


class TestCompatibility:
    """Call sites read .returncode/.stdout/.stderr unconditionally."""
    def test_result_is_a_real_completed_process(self):
        result = run_guarded([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.3)
        assert isinstance(result, subprocess.CompletedProcess)
        assert result.args == [sys.executable, "-c", "import time; time.sleep(5)"]
        # Call sites read .stdout/.stderr unconditionally; both must be str.
        assert isinstance(result.stdout, str)
        assert isinstance(result.stderr, str)


class TestKanbanGitTimeout:
    """The dispatcher's git ceiling must bound hangs without failing slow work."""

    def test_default_is_generous(self):
        from praisonai_bot.gateway.kanban_dispatcher import _git_timeout

        # Worktree add / merge on a large repo can legitimately run for
        # minutes; the bound exists to stop an indefinite hang, not slow work.
        assert _git_timeout() >= 300.0

    def test_env_override(self, monkeypatch):
        from praisonai_bot.gateway.kanban_dispatcher import _git_timeout

        monkeypatch.setenv("PRAISONAI_KANBAN_GIT_TIMEOUT", "42")
        assert _git_timeout() == 42.0

    @pytest.mark.parametrize("bad", ["", "abc", "0", "-1"])
    def test_unusable_override_falls_back(self, monkeypatch, bad):
        from praisonai_bot.gateway.kanban_dispatcher import _git_timeout

        monkeypatch.setenv("PRAISONAI_KANBAN_GIT_TIMEOUT", bad)
        assert _git_timeout() >= 300.0

    def test_run_git_is_bounded(self, monkeypatch):
        """_run_git must route through run_guarded, not raw subprocess.run."""
        from praisonai_bot.gateway import kanban_dispatcher as kd

        seen = {}

        def fake_run_guarded(cmd, **kwargs):
            seen["cmd"] = cmd
            seen["timeout"] = kwargs.get("timeout")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        monkeypatch.setattr(kd, "run_guarded", fake_run_guarded)
        dispatcher = kd.KanbanDispatcher.__new__(kd.KanbanDispatcher)
        dispatcher._run_git("status")

        assert seen["cmd"][0] == "git"
        assert seen["timeout"] is not None and seen["timeout"] > 0


class TestDescendantTermination:
    """A grandchild must not outlive the kill, nor hold the caller open.

    subprocess.run's own timeout path kills only the direct child: on POSIX it
    then wait()s (orphaning the grandchild), and on Windows it communicate()s
    with no timeout, which blocks until the grandchild releases the inherited
    pipe. Both are why run_guarded kills the whole process group.
    """

    def test_returns_promptly_despite_a_surviving_descendant(self):
        import time

        script = (
            "import subprocess, sys, time; "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
            "time.sleep(60)"
        )
        started = time.monotonic()
        result = run_guarded([sys.executable, "-c", script], timeout=1.0)
        elapsed = time.monotonic() - started

        assert result.returncode == TIMEOUT_RETURNCODE
        # Generous bound: the point is that it does not wait out the 60s
        # sleeps, on any platform.
        assert elapsed < 20, f"took {elapsed:.1f}s; descendant blocked the reap"

    def test_grandchild_is_actually_killed(self, tmp_path):
        marker = tmp_path / "grandchild-survived.txt"
        grandchild = (
            f"import time; time.sleep(4); "
            f"open({str(marker)!r}, 'w').write('alive')"
        )
        script = (
            "import subprocess, sys, time; "
            f"subprocess.Popen([sys.executable, '-c', {grandchild!r}]); "
            "time.sleep(60)"
        )
        result = run_guarded([sys.executable, "-c", script], timeout=1.0)
        assert result.returncode == TIMEOUT_RETURNCODE

        # Outlive the grandchild's sleep. If the group kill worked it never
        # gets to write; if only the direct child died, the marker appears.
        import time

        time.sleep(6)
        assert not marker.exists(), "grandchild survived the group kill"


class TestCheck:
    """check= matches subprocess.run, except a timeout still returns."""
    def test_check_raises_on_nonzero(self):
        with pytest.raises(subprocess.CalledProcessError):
            run_guarded([sys.executable, "-c", "import sys; sys.exit(2)"], check=True)

    def test_check_is_off_by_default(self):
        result = run_guarded([sys.executable, "-c", "import sys; sys.exit(2)"])
        assert result.returncode == 2

    def test_timeout_returns_even_with_check(self):
        # A timeout is reported as a value, never an exception, so callers
        # branching on returncode keep working.
        result = run_guarded(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.4,
            check=True,
        )
        assert result.returncode == TIMEOUT_RETURNCODE


class TestNonFiniteTimeoutOverrides:
    """An override that parses as positive can still be unbounded.

    float("inf") passes a bare `value > 0` check, which would hand back an
    infinite timeout and silently reinstate the hang this module prevents.
    """

    @pytest.mark.parametrize("bad", ["inf", "Infinity", "+inf", "1e400", "nan"])
    def test_subprocess_timeout_rejects_non_finite(self, monkeypatch, bad):
        import math

        from praisonai_bot._guarded_subprocess import DEFAULT_TIMEOUT, _default_timeout

        # Assert on the resolver, not on run_guarded with an explicit
        # timeout= -- an explicit argument bypasses the env var entirely, so
        # that spelling would pass even with the bug present.
        monkeypatch.setenv("PRAISONAI_SUBPROCESS_TIMEOUT", bad)
        resolved = _default_timeout()
        assert math.isfinite(resolved)
        assert resolved == DEFAULT_TIMEOUT

    @pytest.mark.parametrize("bad", ["inf", "Infinity", "+inf", "1e400", "nan"])
    def test_git_timeout_rejects_non_finite(self, monkeypatch, bad):
        import math

        from praisonai_bot.gateway.kanban_dispatcher import _git_timeout

        monkeypatch.setenv("PRAISONAI_KANBAN_GIT_TIMEOUT", bad)
        resolved = _git_timeout()
        assert math.isfinite(resolved)
        assert resolved >= 300.0

    def test_default_resolver_stays_finite_without_override(self, monkeypatch):
        import math

        from praisonai_bot._guarded_subprocess import _default_timeout

        monkeypatch.delenv("PRAISONAI_SUBPROCESS_TIMEOUT", raising=False)
        assert math.isfinite(_default_timeout())

