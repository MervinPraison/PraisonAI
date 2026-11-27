"""``praisonai steward`` (S-4a): read a PR's state and pick the next action."""

import json
import subprocess

from praisonai_code.ship.steward import PRState, Thread, next_action, read_pr_state


def _view(**over):
    data = {
        "number": 7, "url": "https://github.com/o/r/pull/7", "state": "OPEN", "mergeable": "MERGEABLE",
        "headRefName": "feat/x", "baseRefName": "main",
        "statusCheckRollup": [
            {"__typename": "CheckRun", "name": "unit", "status": "COMPLETED", "conclusion": "FAILURE"},
            {"__typename": "CheckRun", "name": "lint", "status": "COMPLETED", "conclusion": "SUCCESS"},
            {"__typename": "CheckRun", "name": "slow", "status": "IN_PROGRESS", "conclusion": ""},
            {"__typename": "StatusContext", "context": "ci/legacy", "state": "ERROR"},
            {"__typename": "CheckRun", "name": "unit", "status": "COMPLETED", "conclusion": "FAILURE"},
        ],
    }
    data.update(over)
    return json.dumps(data)


def _threads(viewer="me"):
    def node(tid, resolved=False, outdated=False, last="alice"):
        return {"id": tid, "isResolved": resolved, "isOutdated": outdated, "path": "a.py", "line": 3,
                "comments": {"nodes": [{"author": {"login": last}, "body": f"fix {tid}"}]}}
    return json.dumps({"data": {"viewer": {"login": viewer}, "repository": {"pullRequest": {"reviewThreads": {
        "nodes": [node("T1"), node("T2", resolved=True), node("T3", outdated=True), node("T4", last=viewer),
                  {**node("T5"), "comments": {"nodes": []}}]}}}}})


class Runner:
    def __init__(self, view=None):
        self.view, self.calls = view or _view(), []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        out = self.view if cmd[:3] == ["gh", "pr", "view"] else _threads()
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")


def test_reads_failing_checks_and_open_threads():
    s = read_pr_state("7", run=Runner())
    assert (s.number, s.state, s.head, s.base) == (7, "OPEN", "feat/x", "main")
    assert s.failing == ["unit", "ci/legacy"]  # duplicate "unit" collapsed
    assert [t.id for t in s.threads] == ["T1"]  # resolved, outdated, answered and empty threads skipped
    assert s.threads[0].body == "fix T1" and s.threads[0].path == "a.py"


def test_threads_read_from_the_prs_own_repo():
    run = Runner(_view(url="https://github.com/other/proj/pull/7"))
    read_pr_state("https://github.com/other/proj/pull/7", run=run)
    gql = next(c for c in run.calls if c[:3] == ["gh", "api", "graphql"])
    assert "owner=other" in gql and "name=proj" in gql and "number=7" in gql


def test_reads_only_never_writes():
    run = Runner()
    read_pr_state(None, run=run)
    assert all(c[:3] == ["gh", "pr", "view"] or c[:3] == ["gh", "api", "graphql"] for c in run.calls)
    assert not any("mutation" in " ".join(c) for c in run.calls)


def _state(**over):
    base = dict(number=7, url="u", state="OPEN", mergeable="MERGEABLE", head="feat/x", base="main",
                failing=[], threads=[])
    base.update(over)
    return PRState(**base)


def test_stops_when_merged_or_closed():
    assert next_action(_state(state="MERGED"), {}).kind == "stop"
    assert next_action(_state(state="CLOSED"), {}).kind == "stop"


def test_conflict_comes_first():
    action = next_action(_state(mergeable="CONFLICTING", failing=["unit"]), {})
    assert (action.kind, action.key) == ("merge_base", "conflict")


def test_then_a_failing_check_then_a_thread():
    t = Thread(id="T1", path="a.py", line=3, author="alice", body="rename")
    assert next_action(_state(failing=["unit"], threads=[t]), {}).key == "check:unit"
    action = next_action(_state(threads=[t]), {})
    assert (action.kind, action.key) == ("answer_thread", "thread:T1")


def test_attempt_cap_skips_a_stuck_item():
    action = next_action(_state(failing=["unit", "docs"]), {"check:unit": 3})
    assert action.key == "check:docs"
    action = next_action(_state(failing=["unit"]), {"check:unit": 3})
    assert action.kind == "wait" and "unit" in action.detail


def test_waits_when_nothing_to_do_or_mergeability_unknown():
    assert next_action(_state(), {}).kind == "wait"
    assert next_action(_state(mergeable="UNKNOWN"), {}).kind == "wait"


def test_same_check_name_in_different_workflows_stays_distinct():
    rollup = [
        {"__typename": "CheckRun", "workflowName": "CI Python", "name": "test", "conclusion": "FAILURE"},
        {"__typename": "CheckRun", "workflowName": "CI TypeScript", "name": "test", "conclusion": "FAILURE"},
        {"__typename": "CheckRun", "workflowName": "CI Python", "name": "test", "conclusion": "FAILURE"},
    ]
    s = read_pr_state("7", run=Runner(_view(statusCheckRollup=rollup)))
    assert s.failing == ["CI Python/test", "CI TypeScript/test"]
    action = next_action(s, {"check:CI Python/test": 3})
    assert (action.kind, action.key) == ("fix_check", "check:CI TypeScript/test")


def test_check_without_workflow_and_status_context_stay_readable():
    rollup = [
        {"__typename": "CheckRun", "workflowName": "", "name": "unit", "conclusion": "FAILURE"},
        {"__typename": "CheckRun", "name": "lint", "conclusion": "FAILURE"},
        {"__typename": "StatusContext", "context": "ci/legacy", "state": "ERROR"},
    ]
    s = read_pr_state("7", run=Runner(_view(statusCheckRollup=rollup)))
    assert s.failing == ["unit", "lint", "ci/legacy"]


def test_nameless_or_null_check_entries_are_ignored():
    rollup = [
        None,
        {"__typename": "CheckRun", "conclusion": "FAILURE"},
        {"__typename": "StatusContext", "context": "   ", "state": "FAILURE"},
        {"__typename": "CheckRun", "workflowName": "CI", "name": "build", "conclusion": "FAILURE"},
    ]
    s = read_pr_state("7", run=Runner(_view(statusCheckRollup=rollup)))
    assert s.failing == ["CI/build"]
