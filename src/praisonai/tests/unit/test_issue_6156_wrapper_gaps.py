"""Regression tests for issue #6156 (wrapper hardening)."""

import threading

import pytest


# ── Gap 1: praisonai.code execute_command reuses core safety guards ─────


def test_code_execute_command_rejects_shell_syntax(tmp_path):
    from praisonai.code.tools.execute_command import execute_command

    result = execute_command('echo "written" > redir.txt', cwd=str(tmp_path))
    assert result["success"] is False
    assert "Shell syntax" in result["error"]
    assert not (tmp_path / "redir.txt").exists()


def test_code_execute_command_allows_quoted_metachar(tmp_path):
    from praisonai.code.tools.execute_command import execute_command

    result = execute_command('echo "a > b"', cwd=str(tmp_path))
    assert result["success"] is True
    assert "a > b" in result["stdout"]


def test_code_execute_command_scrubs_secret_env(tmp_path, monkeypatch):
    from praisonai.code.tools.execute_command import execute_command

    monkeypatch.setenv("FAKE_PROVIDER_API_KEY", "sk-should-not-leak")
    monkeypatch.delenv("PRAISONAI_SHELL_ENV_ALLOWLIST", raising=False)
    result = execute_command("env", cwd=str(tmp_path))
    assert result["success"] is True
    assert "sk-should-not-leak" not in result["stdout"]


# ── Gap 2: ImageResult.save() refuses unsafe URLs ────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x.png",
        "http://127.0.0.1/x.png",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]:8080/admin",
        "http://localhost/x.png",
    ],
)
def test_image_save_rejects_unsafe_urls(tmp_path, url):
    from praisonai.capabilities.images import ImageResult

    out = tmp_path / "img.png"
    with pytest.raises(ValueError):
        ImageResult(url=url).save(str(out))
    assert not out.exists()


def test_image_save_b64_still_works(tmp_path):
    import base64
    from praisonai.capabilities.images import ImageResult

    out = tmp_path / "img.png"
    ImageResult(b64_json=base64.b64encode(b"png").decode()).save(str(out))
    assert out.read_bytes() == b"png"


# ── Gap 3: schedule runner is start-once and stoppable ───────────────────


def test_schedule_runner_starts_once_and_stops(monkeypatch):
    import praisonai.integration.bridges.schedules_runner as sr

    monkeypatch.setattr(sr, "_runner_started", False)
    monkeypatch.setattr(sr, "_loop", None)
    monkeypatch.setattr(sr, "_executor", None)
    monkeypatch.setattr(sr, "_build_executor", lambda store: object())

    starts, stops = [], []

    class _FakeLoop:
        def __init__(self, *a, **k):
            pass

        def start(self):
            starts.append(self)

        def stop(self, timeout=5.0):
            stops.append(self)

    monkeypatch.setattr("praisonaiagents.scheduler.ScheduleLoop", _FakeLoop)

    threads = [threading.Thread(target=sr.ensure_schedule_runner) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(starts) == 1
    assert sr._runner_started is True

    sr.stop_schedule_runner()
    assert stops == starts
    assert sr._runner_started is False and sr._loop is None

    sr.stop_schedule_runner()  # idempotent
    assert len(stops) == 1
