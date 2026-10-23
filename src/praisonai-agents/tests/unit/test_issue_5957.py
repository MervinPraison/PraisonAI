"""Regression tests for issue #5957 (doom-loop window, download_file SSRF/size cap)."""

import socket
import time
from unittest.mock import MagicMock, patch

import pytest

from praisonaiagents.approval import reset_yaml_approved_tools, set_yaml_approved_tools
from praisonaiagents.permissions.doom_loop import DoomLoopDetector
from praisonaiagents.tools import url_safety


def test_doom_loop_tool_count_is_windowed():
    detector = DoomLoopDetector(window_seconds=0.05, max_tool_calls=10)
    # One call per window with fresh arguments is not a loop.
    for i in range(8):
        result = detector.record_and_check("read_file", {"path": f"f{i}"})
        assert not result.is_loop, result.reason
        time.sleep(0.06)
    # Lifetime totals are still reported for stats.
    assert detector.get_stats()["call_counts"]["read_file"] == 8


def test_doom_loop_tool_count_still_trips_within_window():
    detector = DoomLoopDetector(window_seconds=60, max_tool_calls=10)
    for i in range(5):
        detector.record("read_file", {"path": f"f{i}"})
    result = detector.check("read_file", {"path": "new"})
    assert result.is_loop
    assert "excessively" in result.reason


def _addrinfo(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]


@pytest.mark.parametrize("ip", ["100.100.100.200", "100.64.0.1"])
def test_url_safety_blocks_shared_address_space(ip, monkeypatch):
    monkeypatch.delenv("ALLOW_LOCAL_CRAWL", raising=False)
    with patch.object(url_safety.socket, "getaddrinfo", return_value=_addrinfo(ip)):
        assert not url_safety.is_safe_http_url(f"http://{ip}/latest/meta-data/")


def test_url_safety_allows_public_address(monkeypatch):
    monkeypatch.delenv("ALLOW_LOCAL_CRAWL", raising=False)
    with patch.object(url_safety.socket, "getaddrinfo", return_value=_addrinfo("93.184.216.34")):
        assert url_safety.is_safe_http_url("https://example.com/")


@pytest.fixture
def file_tools(tmp_path, monkeypatch):
    pytest.importorskip("httpx")
    from praisonaiagents.tools.file_tools import FileTools

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ALLOW_LOCAL_CRAWL", raising=False)
    tools = FileTools()
    monkeypatch.setattr(tools, "_require_workspace_access", lambda write=False: None)
    monkeypatch.setattr(tools, "_validate_path", lambda p: str(tmp_path / p))
    token = set_yaml_approved_tools(["download_file"])
    try:
        yield tools
    finally:
        reset_yaml_approved_tools(token)


@pytest.mark.parametrize("url", [
    "http://localhost./x",
    "http://169.254.169.254./x",
    "http://0177.0.0.1/x",
])
def test_download_file_uses_shared_ssrf_guard(file_tools, url):
    with patch("httpx.stream") as stream:
        result = file_tools.download_file(url, "out.bin")
    assert not result["success"]
    stream.assert_not_called()


def test_download_file_fails_closed_on_unresolvable_host(file_tools):
    with patch.object(url_safety.socket, "getaddrinfo", side_effect=socket.gaierror), \
            patch("httpx.stream") as stream:
        result = file_tools.download_file("http://does-not-resolve.invalid/x", "out.bin")
    assert not result["success"]
    stream.assert_not_called()


def test_download_file_enforces_byte_cap(file_tools, tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_MAX_DOWNLOAD_BYTES", "10000")
    response = MagicMock()
    response.headers = {}
    response.iter_bytes.return_value = iter([b"x" * 8192] * 10)
    ctx = MagicMock()
    ctx.__enter__.return_value = response
    with patch.object(url_safety.socket, "getaddrinfo", return_value=_addrinfo("93.184.216.34")), \
            patch("httpx.stream", return_value=ctx):
        result = file_tools.download_file("https://example.com/big", "big.bin")
    assert not result["success"]
    assert "exceeds" in result["error"]
    assert not (tmp_path / "big.bin").exists()
