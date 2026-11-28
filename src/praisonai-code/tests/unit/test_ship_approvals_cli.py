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
    runner = CliRunner(env={"NO_COLOR": "1", "FORCE_COLOR": None})
    res = runner.invoke(approvals_cmd.app, ["--help"])
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


def test_approvals_comment_flag_upserts_existing_or_posts_new(monkeypatch):
    import subprocess

    report = _report(False, "observe")
    calls = []

    def fake_run_existing(cmd, **kw):
        calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout=json.dumps({
                    "number": 42,
                    "url": "https://github.com/o/r/pull/42",
                    "comments": [{"url": "https://github.com/o/r/pull/42#issuecomment-999", "body": "<!-- openship-approvals -->\nold"}],
                }),
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    assert approvals_mod.post_policy_comment("42", report, run=fake_run_existing) is True
    patch = [c for c in calls if "repos/o/r/issues/comments/999" in c]
    assert len(patch) == 1 and "--method" in patch[0] and "PATCH" in patch[0]
    assert any("OpenShip Approvals (observe mode)" in a and "python-core" in a for a in patch[0])

    # Fresh PR with no prior marker comment -> posts new comment
    calls.clear()

    def fake_run_new(cmd, **kw):
        calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout=json.dumps({"number": 42, "url": "https://github.com/o/r/pull/42", "comments": []}),
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    assert approvals_mod.post_policy_comment("42", report, run=fake_run_new) is True
    assert any(c[:3] == ["gh", "pr", "comment"] for c in calls)

    # Failed PATCH or failed lookup must return False without creating duplicate comments
    dup_calls = []

    def fail_patch(cmd, **kw):
        dup_calls.append(cmd)
        if cmd[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout=json.dumps({
                    "number": 42,
                    "url": "https://ghe.example.com/o/r/pull/42",
                    "comments": [{"url": "https://ghe.example.com/o/r/pull/42#issuecomment-77", "body": "<!-- openship-approvals -->\nold"}],
                }),
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="transient error")

    assert approvals_mod.post_policy_comment("42", report, run=fail_patch) is False
    assert any("--hostname" in c and "ghe.example.com" in c for c in dup_calls)
    assert not any(c[:3] == ["gh", "pr", "comment"] for c in dup_calls)

    # Markdown table escapes pipes and newlines in rule names/reasons and honors custom source
    weird = PolicyReport(
        passed=False,
        mode="observe",
        verdicts=[RuleVerdict("Backend | Python\nTier", False, ["needs 1 | review\nnow"])],
        summary="failed",
    )
    md = approvals_mod.format_policy_comment(weird, source="local file `custom.yml`")
    assert "Backend \\| Python Tier" in md and "needs 1 \\| review now" in md
    assert "local file `custom.yml`" in md

    # CLI --comment wires post_policy_comment with policy provenance without changing exit code
    posted = []
    monkeypatch.setattr(approvals_mod, "check_pr_policy", lambda pr=None, policy_path=None: report)
    monkeypatch.setattr(
        approvals_mod,
        "post_policy_comment",
        lambda pr, rep, **kw: posted.append((pr, rep, kw.get("source", ""))) or True,
    )
    res = CliRunner().invoke(approvals_cmd.app, ["42", "--policy", "/tmp/p.yml", "--comment"])
    assert res.exit_code == 0 and len(posted) == 1 and posted[0][0] == "42" and "/tmp/p.yml" in posted[0][2]
