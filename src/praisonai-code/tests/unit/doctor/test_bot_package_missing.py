"""Regression tests for bot/gateway doctor checks when ``praisonai-bot`` is missing.

Guards against issue #2783 where, with the wrapper installed but the optional
``praisonai-bot`` package absent, five bot/gateway checks failed with misleading
"Fix bot.yaml syntax" remediations instead of pointing at the real fix
(``pip install 'praisonai[bot]'``).
"""

import pytest

from praisonai_code.cli.features.doctor.models import CheckStatus, DoctorConfig
from praisonai_code.cli.features.doctor.checks import _wrapper_checks, bot_checks, gateway_checks


@pytest.fixture
def wrapper_present_bot_missing(monkeypatch):
    """Simulate: wrapper installed, praisonai-bot NOT installed."""
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: True
    )
    monkeypatch.setattr(
        "praisonai_code._bot_bridge.bot_package_available", lambda: False
    )


BOT_CHECKS = [
    bot_checks.check_bot_config,
    bot_checks.check_bot_security,
    bot_checks.check_multi_channel_tokens,
]

GATEWAY_CHECKS = [
    gateway_checks.check_gateway_config_validation,
    gateway_checks.check_gateway_security,
    gateway_checks.check_gateway_config_migration,
]


@pytest.mark.parametrize("check", BOT_CHECKS + GATEWAY_CHECKS)
def test_checks_skip_when_bot_package_missing(check, wrapper_present_bot_missing):
    """Each schema-dependent check must SKIP with an install hint, not fail."""
    result = check(DoctorConfig())

    assert result.status == CheckStatus.SKIP
    assert "praisonai-bot not installed" in result.message
    assert result.remediation == "pip install 'praisonai[bot]'"
    # The misleading "bot.yaml syntax" remediation must never appear.
    assert "bot.yaml syntax" not in (result.remediation or "")


def test_skip_helper_returns_none_when_bot_present(monkeypatch):
    """When the bot package is available the helper must not short-circuit."""
    monkeypatch.setattr(
        "praisonai_code._bot_bridge.bot_package_available", lambda: True
    )
    assert _wrapper_checks.skip_if_no_bot_package("x", "X") is None
