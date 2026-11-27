"""``praisonai approvals`` CLI wiring tests (S-7)."""

import json

from typer.testing import CliRunner

from praisonai_code.cli.commands import approvals as approvals_cmd
from praisonai_code.ship import approvals as approvals_mod
from praisonai_code.ship.approvals import PolicyReport, RuleVerdict
from praisonai_code.ship.flow import ShipRefused


def _report(passed: bool, mode: str = "observe") -> PolicyReport:
    verdict = RuleVerdict("python-core", passed, [] if passed else ["needs 2 approval(s), has 1"])
    return PolicyReport(
        passed=passed,
        mode=mode,
        protected_touched=[],
        verdicts=[verdict],
        summary=f"passed ({mode})" if passed else f"failed ({mode}): python-core",
    )


def test_registered_in_cli_app():
    from praisonai_code.cli import app as cli_app

    assert cli_app._LAZY_COMMANDS["approvals"][0] == ".commands.approvals"
    res = CliRunner().invoke(approvals_cmd.app, ["--help"])
    assert res.exit_code == 0
    for flag in ("--policy", "--enforce", "--json"):
        assert flag in res.output


def test_passing_policy_exits_0_and_prints_verdicts(monkeypatch):
    monkeypatch.setattr(approvals_mod, "check_pr_policy", lambda pr=None, policy_path=None: _report(True, "enforce"))
    res = CliRunner().invoke(approvals_cmd.app, ["42"])
    assert res.exit_code == 0
    assert "passed (enforce)" in res.output and "PASS" in res.output and "python-core" in res.output


def test_observe_failure_exits_0_unless_enforce_flag_set(monkeypatch):
    monkeypatch.setattr(approvals_mod, "check_pr_policy", lambda pr=None, policy_path=None: _report(False, "observe"))
    res_obs = CliRunner().invoke(approvals_cmd.app, ["42"])
    assert res_obs.exit_code == 0 and "FAIL" in res_obs.output and "needs 2 approval" in res_obs.output

    res_enf = CliRunner().invoke(approvals_cmd.app, ["42", "--enforce"])
    assert res_enf.exit_code == 1 and "FAIL" in res_enf.output


def test_enforce_mode_failure_exits_1(monkeypatch):
    monkeypatch.setattr(approvals_mod, "check_pr_policy", lambda pr=None, policy_path=None: _report(False, "enforce"))
    res = CliRunner().invoke(approvals_cmd.app, ["42"])
    assert res.exit_code == 1 and "failed (enforce)" in res.output


def test_json_output_includes_blocking_and_verdicts(monkeypatch):
    seen = {}

    def fake_check(pr=None, policy_path=None):
        seen.update(pr=pr, policy_path=policy_path)
        return _report(False, "enforce")

    monkeypatch.setattr(approvals_mod, "check_pr_policy", fake_check)
    res = CliRunner().invoke(approvals_cmd.app, ["42", "--policy", "/tmp/p.yml", "--json"])
    assert res.exit_code == 1
    assert seen == {"pr": "42", "policy_path": "/tmp/p.yml"}
    payload = json.loads(res.output)
    assert payload["passed"] is False and payload["mode"] == "enforce" and payload["blocking"] is True
    assert payload["verdicts"][0]["rule"] == "python-core"


def test_ship_refused_exits_1_with_clean_stderr(monkeypatch):
    def refuse(pr=None, policy_path=None):
        raise ShipRefused("no .praisonai/approvals.yml found on base branch 'main'")

    monkeypatch.setattr(approvals_mod, "check_pr_policy", refuse)
    res = CliRunner().invoke(approvals_cmd.app, [])
    assert res.exit_code == 1
    assert "approvals: no .praisonai/approvals.yml found" in res.output
