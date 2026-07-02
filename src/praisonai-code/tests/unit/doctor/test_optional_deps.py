"""Regression tests for the optional-dependencies doctor check.

Guards against the deep-doctor timeout reported in issue #2552 where a single
hanging optional import (e.g. ``chromadb``) blocked the entire
``praisonai doctor env --deep`` pass and tripped the engine-wide timeout.
"""

import time

from praisonai_code.cli.features.doctor.models import (
    CheckStatus,
    DoctorConfig,
)
from praisonai_code.cli.features.doctor.checks import env_checks


def test_optional_deps_completes_and_passes():
    """The check should always complete with PASS regardless of installs."""
    config = DoctorConfig(deep=True, timeout=10.0)
    result = env_checks.check_optional_deps(config)

    assert result.status == CheckStatus.PASS
    assert "available" in result.metadata
    assert "missing" in result.metadata
    assert "slow" in result.metadata


def test_optional_deps_slow_import_does_not_block(monkeypatch):
    """A hanging import must be reported as slow, not block the whole check."""
    original_probe = env_checks._probe_optional_package

    def fake_probe(package):
        if package == "chromadb":
            # Simulate a hanging import that never returns in a reasonable time.
            time.sleep(30)
            return True
        return original_probe(package)

    monkeypatch.setattr(env_checks, "_probe_optional_package", fake_probe)

    config = DoctorConfig(deep=True, timeout=8.0)
    start = time.monotonic()
    result = env_checks.check_optional_deps(config)
    elapsed = time.monotonic() - start

    # Must not block for the full 30s sleep, and must stay within engine budget.
    assert elapsed < config.timeout
    assert result.status == CheckStatus.PASS

    slow = result.metadata.get("slow", [])
    assert any("chromadb" in entry for entry in slow)


def test_optional_deps_missing_package_reported(monkeypatch):
    """Missing packages should be reported without failing the check."""
    def fake_probe(package):
        raise ImportError(f"No module named {package!r}")

    monkeypatch.setattr(env_checks, "_probe_optional_package", fake_probe)

    config = DoctorConfig(deep=True, timeout=10.0)
    result = env_checks.check_optional_deps(config)

    assert result.status == CheckStatus.PASS
    assert result.metadata["available"] == []
    assert len(result.metadata["missing"]) == 8
    assert result.metadata["slow"] == []
