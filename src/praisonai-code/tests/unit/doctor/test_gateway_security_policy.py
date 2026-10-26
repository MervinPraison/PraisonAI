"""The gateway security check must reflect ``unknown_user_policy`` (Issue #5092).

An empty allowlist only opens the bot to everyone when the policy is
``allow``; under the default ``deny`` unknown DMs are dropped.
"""

from types import SimpleNamespace

import pytest

from praisonai_code.cli.features.doctor.models import CheckStatus, DoctorConfig
from praisonai_code.cli.features.doctor.checks import gateway_checks


def _run(monkeypatch, tmp_path, policy):
    (tmp_path / "gateway.yaml").write_text("channels: {}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", "x")
    monkeypatch.setattr(gateway_checks, "skip_if_no_wrapper", lambda *a, **k: None)
    monkeypatch.setattr(gateway_checks, "skip_if_no_bot_package", lambda *a, **k: None)
    monkeypatch.setattr(
        "praisonai_code.cli._paths.resolve_bot_config_path", lambda name: name
    )
    channel = SimpleNamespace(
        allowed_users=[], allowlist=[], blocklist=[],
        unknown_user_policy=policy, group_policy="mention_only", token="t",
    )
    schema = SimpleNamespace(
        load_and_validate_gateway_yaml=lambda path: SimpleNamespace(
            channels={"telegram": channel}
        )
    )
    monkeypatch.setattr(gateway_checks, "_bots_config_schema", lambda: schema)
    return gateway_checks.check_gateway_security(DoctorConfig())


def test_allow_policy_flags_open_access(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, "allow")
    assert result.status == CheckStatus.FAIL
    assert "EVERYONE" in result.details


@pytest.mark.parametrize("policy", [None, "deny"])
def test_deny_policy_does_not_claim_everyone(monkeypatch, tmp_path, policy):
    result = _run(monkeypatch, tmp_path, policy)
    assert result.status == CheckStatus.WARN
    assert "EVERYONE" not in result.details
    assert "dropped" in result.details


def test_pair_policy_passes(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, "pair")
    assert result.status == CheckStatus.PASS
