"""Regression tests for issue #5960 wrapper gaps."""

import json
import logging
import subprocess
from unittest.mock import patch

import pytest


def _fake_getaddrinfo(ip):
    def _inner(host, port, *args, **kwargs):
        return [(None, None, None, "", (ip, port))]
    return _inner


class TestPassthroughApiBaseSSRF:
    def test_localhost_rejected(self):
        from praisonai.capabilities.passthrough import _validate_api_base
        with pytest.raises(ValueError):
            _validate_api_base("http://localhost/x")

    def test_hostname_resolving_to_metadata_rejected(self):
        from praisonai.capabilities.passthrough import _validate_api_base
        with patch("socket.getaddrinfo", _fake_getaddrinfo("169.254.169.254")):
            with pytest.raises(ValueError, match="api_base URL"):
                _validate_api_base("http://evil.example.com/")

    def test_public_hostname_allowed(self):
        from praisonai.capabilities.passthrough import _validate_api_base
        with patch("socket.getaddrinfo", _fake_getaddrinfo("93.184.216.34")):
            assert _validate_api_base("https://api.example.com") == ["93.184.216.34"]

    def test_fallback_pins_connection_to_screened_ip(self):
        import httpx
        from praisonai.capabilities.passthrough import _build_request
        req = _build_request(httpx.Client(), "POST", "https://api.example.com/v1/x",
                             ["93.184.216.34"], json={})
        assert req.url.host == "93.184.216.34"
        assert req.headers["Host"] == "api.example.com"
        assert req.extensions["sni_hostname"] == "api.example.com"

    def test_async_fallback_screens_off_event_loop(self):
        import asyncio
        import sys
        import types
        from praisonai.capabilities import passthrough as pt

        async def _missing(**kwargs):
            raise AttributeError
        fake_litellm = types.SimpleNamespace(allm_passthrough_route=_missing)
        with patch.dict(sys.modules, {"litellm": fake_litellm}), \
             patch("socket.getaddrinfo", _fake_getaddrinfo("10.0.0.1")), \
             patch("asyncio.to_thread", wraps=asyncio.to_thread) as to_thread:
            with pytest.raises(ValueError, match="private"):
                asyncio.run(pt.apassthrough("/x", api_base="http://evil.example.com"))
        assert to_thread.called

    def test_bad_scheme_rejected(self):
        from praisonai.capabilities.passthrough import _validate_api_base
        with pytest.raises(ValueError):
            _validate_api_base("file:///etc/passwd")


class TestVulnerabilityScan:
    DEPS = [{"name": "requests", "version": "2.0.0"}]

    def test_missing_pip_audit_reported(self):
        from praisonai.recipe.security import _check_vulnerabilities
        fake = subprocess.CompletedProcess([], 1, stdout="", stderr="No module named pip_audit")
        with patch("subprocess.run", return_value=fake):
            vulns, error = _check_vulnerabilities(self.DEPS)
        assert vulns == []
        assert "not installed" in error

    def test_timeout_reported(self):
        from praisonai.recipe.security import _check_vulnerabilities
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("x", 60)):
            vulns, error = _check_vulnerabilities(self.DEPS)
        assert vulns == [] and "timed out" in error

    def test_findings_parsed_on_nonzero_exit_and_deps_scanned(self):
        from praisonai.recipe.security import _check_vulnerabilities
        out = json.dumps({"dependencies": [{"name": "requests", "version": "2.0.0",
                                            "vulns": [{"id": "PYSEC-1", "fix_versions": ["2.1"]}]}]})
        fake = subprocess.CompletedProcess([], 1, stdout=out, stderr="")
        with patch("subprocess.run", return_value=fake) as run:
            vulns, error = _check_vulnerabilities(self.DEPS)
        assert error is None
        assert vulns[0]["vulnerability_id"] == "PYSEC-1"
        assert "--requirement" in run.call_args[0][0]

    def test_skipped_packages_reported(self):
        from praisonai.recipe.security import _check_vulnerabilities
        out = json.dumps({"dependencies": [{"name": "privpkg", "version": "1.0",
                                            "skip_reason": "not found on PyPI"}]})
        fake = subprocess.CompletedProcess([], 0, stdout=out, stderr="")
        with patch("subprocess.run", return_value=fake):
            vulns, error = _check_vulnerabilities(self.DEPS)
        assert vulns == [] and "privpkg" in error

    def test_audit_report_warns_when_scan_skipped(self, tmp_path):
        from praisonai.recipe import security
        with patch.object(security, "_get_python_deps", return_value=self.DEPS), \
             patch.object(security, "_check_vulnerabilities", return_value=([], "pip-audit is not installed")), \
             patch.object(security, "_check_outdated", return_value=[]):
            report = security.audit_dependencies(tmp_path)
        assert any("Vulnerability scan incomplete" in w for w in report["warnings"])


def test_claude_code_use_sdk_fallback_warns(caplog):
    from praisonai.integrations import claude_code
    with patch.object(claude_code, "CLAUDE_SDK_AVAILABLE", False):
        with caplog.at_level(logging.WARNING, logger=claude_code.__name__):
            integration = claude_code.ClaudeCodeIntegration(use_sdk=True)
    assert integration.use_sdk is False
    assert "claude-agent-sdk is not installed" in caplog.text
