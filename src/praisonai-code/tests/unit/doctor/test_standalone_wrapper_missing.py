"""Regression tests for doctor wrapper checks on a standalone install.

Guards against issue #2838 where, on a standalone ``praisonai-code`` install
(no ``praisonai`` wrapper), four wrapper-presence checks were scored as hard
failures (FAIL) instead of skips (SKIP), causing ``praisonai-code doctor`` to
exit 1 despite a healthy core agent path.
"""

import pytest

from praisonai_code.cli.features.doctor.models import CheckStatus, DoctorConfig
from praisonai_code.cli.features.doctor.checks import (
    acp_checks,
    packaging_checks,
    performance_checks,
)


@pytest.fixture
def wrapper_missing(monkeypatch):
    """Simulate a standalone install: praisonai wrapper NOT installed."""
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )


WRAPPER_SKIP_CHECKS = [
    performance_checks.check_performance_praisonai_import,
    acp_checks.check_acp_module,
    packaging_checks.check_praisonai_package_structure,
]


@pytest.mark.parametrize("check", WRAPPER_SKIP_CHECKS)
def test_wrapper_checks_skip_when_wrapper_missing(check, wrapper_missing):
    """Each wrapper-dependent check must SKIP, not FAIL, on standalone."""
    result = check(DoctorConfig())

    assert result.status == CheckStatus.SKIP
    assert result.status != CheckStatus.FAIL
    assert "pip install praisonai" in result.message


def test_python_module_execution_targets_product_entry(monkeypatch, wrapper_missing):
    """On standalone, module execution must test praisonai_code, not praisonai."""
    result = packaging_checks.check_python_module_execution(DoctorConfig())

    # The check must target the product's own entry point on a standalone
    # install rather than the absent wrapper module.
    assert "-m praisonai_code" in result.metadata["test_command"]
    assert " praisonai " not in result.metadata["test_command"]


def test_python_module_execution_targets_wrapper_when_present(monkeypatch):
    """With the wrapper installed, module execution must test praisonai."""
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: True
    )
    result = packaging_checks.check_python_module_execution(DoctorConfig())

    assert "-m praisonai " in result.metadata["test_command"]
