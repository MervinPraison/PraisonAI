"""Tests for GitHub-native PR Steward hardening: @praisonai stop/resume, openship-stop label, stateless CI circuit breaker."""

import json
import subprocess

from praisonai_code.ship.steward import next_action, read_pr_state
from praisonai_code.ship.steward_loop import watch_pr
from praisonai_code.ship.steward_turn import run_steward_turn


def _fake_gh(*, labels=(), comments=(), failing_checks=()):
    view = {
        "number": 42,
        "url": "https://github.com/MervinPraison/PraisonAI/pull/42",
        "state": "OPEN",
        "mergeable": "MERGEABLE",
        "headRefName": "feat/demo",
        "baseRefName": "main",
        "statusCheckRollup": [{"name": c, "conclusion": "FAILURE"} for c in failing_checks],
        "labels": [{"name": lb} for lb in labels],
        "comments": comments,
    }
    gql = {"data": {"viewer": {"login": "bot"}, "repository": {"pullRequest": {"reviewThreads": {"nodes": []}}}}}

    def runner(cmd, **kw):
        if cmd[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(view), stderr="")
        if cmd[:3] == ["gh", "api", "graphql"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(gql), stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return runner


def test_openship_stop_label_halts_steward():
    state = read_pr_state("42", run=_fake_gh(labels=["openship-stop"], failing_checks=["CI/test"]))
    assert state.stopped and "openship-stop" in state.stop_reason
    act = next_action(state, {})
    assert act.kind == "stop" and "openship-stop" in act.detail


def test_at_praisonai_stop_and_resume_comments():
    stopped_state = read_pr_state(
        "42",
        run=_fake_gh(comments=[{"id": "1", "body": "@praisonai stop"}], failing_checks=["CI/test"]),
    )
    assert stopped_state.stopped
    assert next_action(stopped_state, {}).kind == "stop"

    resumed_state = read_pr_state(
        "42",
        run=_fake_gh(
            comments=[{"id": "1", "body": "@praisonai stop"}, {"id": "2", "body": "@praisonai resume"}],
            failing_checks=["CI/test"],
        ),
    )
    assert not resumed_state.stopped
    assert next_action(resumed_state, {}).kind == "fix_check"


def test_stateless_ci_circuit_breaker_hydrates_attempts_from_pr_comments():
    comments = [
        {"id": "c1", "body": "Steward pushed `abc1234` (fix_check, check:CI/test):\n\nfix 1"},
        {"id": "c2", "body": "Steward attempted (check:CI/test):\n\nstill failing"},
        {"id": "c3", "body": "Steward pushed `def5678` (fix_check, check:CI/test):\n\nfix 3"},
    ]
    events = []
    called = []
    summary = watch_pr(
        "42",
        once=True,
        max_attempts=3,
        run=_fake_gh(comments=comments, failing_checks=["CI/test"]),
        agent=type("A", (), {"chat": lambda self, p: called.append(p) or "nope"})(),
        on_event=events.append,
    )
    assert summary.turns == 0 and called == []
    assert summary.attempts["check:CI/test"] == 3
    assert any("gave up on: check:CI/test" in e for e in events)


def test_directive_comment_triggers_answer_directive_and_records_attempt_in_once_mode():
    comments = [{"id": "d1", "body": "@praisonai please rename foo to bar"}]
    posted = []

    def runner(cmd, **kw):
        if cmd[:3] == ["gh", "pr", "comment"]:
            posted.append(cmd[cmd.index("--body") + 1])
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="samehead\n", stderr="")
        return _fake_gh(comments=comments)(cmd, **kw)

    state = read_pr_state("42", run=runner)
    act = next_action(state, state.prior_attempts)
    assert act.kind == "answer_directive" and act.key == "directive:d1"

    fake_agent = type("A", (), {"chat": lambda self, p: "Checked foo -> bar."})()
    res = run_steward_turn(state, act, agent=fake_agent, run=runner, record_attempt=True)
    assert res.acted and res.commented
    assert posted and "Steward attempted (directive:d1)" in posted[0]
