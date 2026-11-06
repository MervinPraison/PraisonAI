"""Regression tests for issue #6156 (wrapper hardening)."""

import sys
import threading

import pytest

# `echo` and `env` are cmd.exe builtins / absent on Windows; execute_command
# runs without a shell by design (#6157), so these probes are POSIX-only.
_posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="echo/env are not executables on Windows (shell=False); see #6264",
)


# ── Gap 1: praisonai.code execute_command reuses core safety guards ─────


def test_code_execute_command_rejects_shell_syntax(tmp_path):
    from praisonai.code.tools.execute_command import execute_command

    result = execute_command('echo "written" > redir.txt', cwd=str(tmp_path))
    assert result["success"] is False
    assert "Shell syntax" in result["error"]
    assert not (tmp_path / "redir.txt").exists()


@_posix_only
def test_code_execute_command_allows_quoted_metachar(tmp_path):
    from praisonai.code.tools.execute_command import execute_command

    result = execute_command('echo "a > b"', cwd=str(tmp_path))
    assert result["success"] is True
    assert "a > b" in result["stdout"]


@_posix_only
def test_code_execute_command_scrubs_secret_env(tmp_path, monkeypatch):
    from praisonai.code.tools.execute_command import execute_command

    monkeypatch.setenv("FAKE_PROVIDER_API_KEY", "sk-should-not-leak")
    monkeypatch.delenv("PRAISONAI_SHELL_ENV_ALLOWLIST", raising=False)
    result = execute_command("env", cwd=str(tmp_path))
    assert result["success"] is True
    assert "sk-should-not-leak" not in result["stdout"]


@pytest.mark.skipif(
    any(c.isspace() for c in sys.executable),
    reason="interpreter path contains whitespace",
)
def test_code_execute_command_scrubs_secret_env_cross_platform(tmp_path, monkeypatch):
    """Platform-neutral env-scrub probe (#6264): a Python child dumps its env."""
    from praisonai.code.tools.execute_command import execute_command

    (tmp_path / "probe.py").write_text(
        "import os\nfor k, v in os.environ.items():\n    print(k + '=' + v)\n"
    )
    monkeypatch.setenv("FAKE_PROVIDER_API_KEY", "sk-should-not-leak")
    monkeypatch.delenv("PRAISONAI_SHELL_ENV_ALLOWLIST", raising=False)
    result = execute_command(f"{sys.executable} probe.py", cwd=str(tmp_path))
    assert result["success"] is True, result
    assert "PAGER=cat" in result["stdout"]
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


# ── Gap 2b: download path (success / redirect refused / size cap) ───────


@pytest.fixture
def local_image_server(monkeypatch):
    """Offline HTTP server; the public-host screen is bypassed so the real
    download path (opener, redirect handler, size cap) is exercised."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/img.png")
                self.end_headers()
                return
            body = b"x" * 64
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(
        "praisonai.jobs.models._resolve_and_screen_webhook_host",
        lambda url, label="": ["127.0.0.1"],
    )
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_image_save_downloads_public_url(tmp_path, local_image_server):
    from praisonai.capabilities.images import ImageResult

    out = tmp_path / "img.png"
    ImageResult(url=f"{local_image_server}/img.png").save(str(out))
    assert out.read_bytes() == b"x" * 64


def test_image_save_refuses_redirect(tmp_path, local_image_server):
    import urllib.error
    from praisonai.capabilities.images import ImageResult

    out = tmp_path / "img.png"
    with pytest.raises(urllib.error.HTTPError):
        ImageResult(url=f"{local_image_server}/redirect").save(str(out))
    assert not out.exists()


def test_image_save_enforces_size_cap(tmp_path, local_image_server, monkeypatch):
    import praisonai.capabilities.images as images

    monkeypatch.setattr(images, "_IMAGE_DOWNLOAD_MAX_BYTES", 16)
    out = tmp_path / "img.png"
    with pytest.raises(ValueError, match="maximum download size"):
        images.ImageResult(url=f"{local_image_server}/img.png").save(str(out))
    assert not out.exists()
