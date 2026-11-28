"""``praisonai steward`` (S-4c): watch loop, attempt caps, stop conditions, and CLI."""

import subprocess

import pytest
from typer.testing import CliRunner

from praisonai_code.ship.flow import ShipRefused
from praisonai_code.ship.steward import PRState
from praisonai_code.ship.steward_loop import StewardSummary, watch_pr
from praisonai_code.ship.steward_turn import TurnResult


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("PRAISONAI_DISABLE_SHIP", raising=False)
    monkeypatch.delenv("PRAISONAI_SHIP_ENABLED", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praisonai"))


def _state(**over):
    base = dict(
        number=7,
        url="https://github.com/o/r/pull/7",
        state="OPEN",
        mergeable="MERGEABLE",
        head="feat/x",
        base="main",
        failing=[],
        threads=[],
    )
    base.update(over)
    return PRState(**base)


def test_refuses_when_ship_is_disabled(monkeypatch):
    monkeypatch.setenv("PRAISONAI_DISABLE_SHIP", "1")
    called = []
    monkeypatch.setattr("praisonai_code.ship.steward_loop.read_pr_state", lambda *a, **kw: called.append(a))
    with pytest.raises(ShipRefused, match="PRAISONAI_DISABLE_SHIP"):
        watch_pr("7", once=True)
    assert called == []


@pytest.mark.parametrize("state_name", ["MERGED", "CLOSED"])
def test_stops_on_merged_or_closed_pr(monkeypatch, state_name):
    sleeps = []
    monkeypatch.setattr("praisonai_code.ship.steward_loop.read_pr_state", lambda pr, run=None: _state(state=state_name))
    summary = watch_pr("7", sleep=sleeps.append)
    assert isinstance(summary, StewardSummary)
    assert state_name.lower() in summary.reason and summary.cycles == 1 and summary.turns == 0
    assert sleeps == []


def test_tracks_attempts_across_cycles_and_respects_max_attempts(monkeypatch):
    states = iter([
        _state(failing=["CI/test"]),
        _state(failing=["CI/test"]),
        _state(failing=["CI/test"]),  # attempt cap reached -> wait
        _state(state="MERGED"),
    ])
    turns = []
    sleeps = []
    monkeypatch.setattr("praisonai_code.ship.steward_loop.read_pr_state", lambda pr, run=None: next(states))

    def fake_turn(state, action, **kw):
        turns.append(action.key)
        return TurnResult(action.kind, True, "tried fix", pushed_sha="abc1234", commented=True)

    monkeypatch.setattr("praisonai_code.ship.steward_loop.run_steward_turn", fake_turn)
    summary = watch_pr("7", interval=5.0, max_attempts=2, sleep=sleeps.append)
    assert summary.turns == 2 and turns == ["check:CI/test", "check:CI/test"]
    assert summary.attempts == {"check:CI/test": 2}
    assert summary.cycles == 4 and sleeps == [5.0, 5.0, 5.0]
    assert "merged" in summary.reason


def test_once_runs_single_cycle_without_sleeping(monkeypatch):
    sleeps, events = [], []
    monkeypatch.setattr("praisonai_code.ship.steward_loop.read_pr_state", lambda pr, run=None: _state(failing=["CI/test"]))
    monkeypatch.setattr(
        "praisonai_code.ship.steward_loop.run_steward_turn",
        lambda state, action, **kw: TurnResult(action.kind, True, "ok", pushed_sha="def5678", commented=True),
    )
    summary = watch_pr("7", once=True, sleep=sleeps.append, on_event=events.append)
    assert summary.reason == "once" and summary.cycles == 1 and summary.turns == 1
    assert sleeps == [] and any("def5678" in e for e in events)


def test_stops_when_max_days_exceeded(monkeypatch):
    clock = iter([0.0, 10.0, 8.0 * 86400.0])
    monkeypatch.setattr("praisonai_code.ship.steward_loop.read_pr_state", lambda pr, run=None: _state())
    summary = watch_pr("7", max_days=7.0, sleep=lambda _: None, monotonic=lambda: next(clock))
    assert summary.reason == "max_days reached" and summary.cycles == 1


def test_stops_cleanly_on_keyboard_interrupt_during_sleep(monkeypatch):
    monkeypatch.setattr("praisonai_code.ship.steward_loop.read_pr_state", lambda pr, run=None: _state())

    def interrupt(_):
        raise KeyboardInterrupt()

    summary = watch_pr("7", sleep=interrupt)
    assert summary.reason == "interrupted" and summary.cycles == 1


def test_stops_when_local_branch_switches_when_pr_is_none(monkeypatch):
    branches = iter(["feat/x", "feat/x", "main"])

    def fake_run(cmd, **kw):
        if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{next(branches)}\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("praisonai_code.ship.steward_loop.read_pr_state", lambda pr, run=None: _state())
    summary = watch_pr(None, run=fake_run, sleep=lambda _: None)
    assert summary.reason == "branch switched" and summary.cycles == 1


def test_steward_is_registered_in_cli_app_and_cli_options(monkeypatch):
    from praisonai_code.cli import app as cli_app
    from praisonai_code.cli.commands import steward as steward_cmd
    from praisonai_code.ship import steward_loop

    assert cli_app._LAZY_COMMANDS["steward"][0] == ".commands.steward"

    runner = CliRunner(env={"NO_COLOR": "1", "FORCE_COLOR": None})
    help_res = runner.invoke(steward_cmd.app, ["--help"])
    assert help_res.exit_code == 0
    for flag in ("--once", "--interval", "--max-days", "--max-attempts", "--model"):
        assert flag in help_res.output

    seen = {}

    def fake_watch(pr=None, **kw):
        seen["pr"] = pr
        seen.update(kw)
        return StewardSummary("once", cycles=1, turns=0)

    monkeypatch.setattr(steward_loop, "watch_pr", fake_watch)
    res = CliRunner().invoke(steward_cmd.app, ["42", "--once", "--model", "ollama/llama3.2"])
    assert res.exit_code == 0
    assert seen["pr"] == "42" and seen["once"] is True and seen["llm"] == "ollama/llama3.2"


def test_steward_cli_exits_1_when_disabled(monkeypatch):
    from praisonai_code.cli.commands import steward as steward_cmd

    monkeypatch.setenv("PRAISONAI_DISABLE_SHIP", "1")
    monkeypatch.setattr(
        "praisonai_code.ship.steward_loop.read_pr_state",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("must not poll when disabled")),
    )
    res = CliRunner().invoke(steward_cmd.app, ["--once"])
    assert res.exit_code == 1 and "disabled" in res.output.lower()


def test_normalizes_hash_prefixed_pr_number(monkeypatch):
    seen = []

    def fake_read(pr, run=None):
        seen.append(pr)
        return _state(state="MERGED")

    monkeypatch.setattr("praisonai_code.ship.steward_loop.read_pr_state", fake_read)
    watch_pr("#42", once=True)
    assert seen == ["42"]


@pytest.mark.parametrize(
    "kwargs",
    [{"interval": 0}, {"interval": -5}, {"max_days": 0}, {"max_attempts": 0}],
)
def test_invalid_numeric_bounds_raise_value_error(kwargs):
    with pytest.raises(ValueError):
        watch_pr("7", **kwargs)


def test_steward_cli_exits_1_cleanly_on_called_process_error(monkeypatch):
    from praisonai_code.cli.commands import steward as steward_cmd
    from praisonai_code.ship import steward_loop

    def fail(*a, **kw):
        raise subprocess.CalledProcessError(1, ["gh", "pr", "view"], stderr="no pull requests found for branch")

    monkeypatch.setattr(steward_loop, "watch_pr", fail)
    res = CliRunner().invoke(steward_cmd.app, ["--once"])
    assert res.exit_code == 1
    assert "no pull requests found" in res.output
    assert res.exception is None or isinstance(res.exception, SystemExit)
