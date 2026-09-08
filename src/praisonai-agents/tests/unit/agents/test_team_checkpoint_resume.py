"""A team that dies part-way can resume instead of restarting.

save_session_state persisted only the shared _state dict -- no task status, no
task outputs -- so a team that died on task 9 of 12 restarted from task 1 and
re-paid for eight completed tasks. Step-level resume existed, but only on the
YAML workflow path, which AgentTeam cannot reach.
"""
import pytest

from praisonaiagents import Agent, AgentTeam, Task


@pytest.fixture
def agent():
    return Agent(name="w", instructions="x", llm="gpt-4o")


def _team(agent, names=("t1", "t2")):
    return AgentTeam(
        agents=[agent],
        tasks=[Task(name=n, description=f"d-{n}", expected_output="e", agent=agent) for n in names],
    )


class TestPayload:
    def test_task_status_and_output_are_persisted(self, agent):
        team = _team(agent)
        first = list(team.tasks)[0]
        team.tasks[first].status = "completed"
        team.tasks[first].result = "FIRST DONE"

        payload = team._team_state_payload("s1")
        assert "tasks" in payload
        saved = payload["tasks"][str(first)]
        assert saved["status"] == "completed"
        assert saved["result"] == "FIRST DONE"

    def test_a_task_output_object_is_reduced_to_something_portable(self, agent):
        """A half-serialised object would lose the whole checkpoint, not one field."""
        class Output:
            raw = "TEXT"

        team = _team(agent)
        first = list(team.tasks)[0]
        team.tasks[first].result = Output()
        assert team._team_state_payload("s1")["tasks"][str(first)]["result"] == "TEXT"


class TestRestore:
    def test_completed_work_comes_back(self, agent):
        source = _team(agent)
        first = list(source.tasks)[0]
        source.tasks[first].status = "completed"
        source.tasks[first].result = "FIRST DONE"
        payload = source._team_state_payload("s1")

        target = _team(agent)
        assert target._restore_serialised_task_state(payload["tasks"]) == 2
        assert target.tasks[first].status == "completed"
        # Restored as a TaskOutput, not a bare string, so downstream consumers
        # that read result.raw (dependency context, routing) keep working.
        assert target.tasks[first].result.raw == "FIRST DONE"

    def test_control_an_unfinished_task_is_not_marked_done(self, agent):
        source = _team(agent)
        payload = source._team_state_payload("s1")
        target = _team(agent)
        target._restore_serialised_task_state(payload["tasks"])
        assert all(t.status != "completed" for t in target.tasks.values())

    def test_unknown_tasks_are_skipped_not_invented(self, agent):
        target = _team(agent)
        assert target._restore_serialised_task_state({"99": {"status": "completed"}}) == 0


class TestFingerprint:
    def test_the_same_task_set_fingerprints_the_same(self, agent):
        assert _team(agent)._task_set_fingerprint() == _team(agent)._task_set_fingerprint()

    def test_a_different_task_set_differs(self, agent):
        assert _team(agent)._task_set_fingerprint() != _team(agent, names=("x", "y"))._task_set_fingerprint()

    def test_the_payload_carries_it(self, agent):
        assert _team(agent)._team_state_payload("s1")["tasks_fingerprint"]

    def test_it_is_why_positional_keys_are_safe(self, agent):
        """Task keys are positional, so without this a checkpoint from another
        team would put task 3's output onto a different task 3."""
        assert list(_team(agent).tasks) == [0, 1]

    def test_a_changed_task_agent_changes_the_fingerprint(self, agent):
        """A different agent means a different task; the fingerprint must move
        so a restore cannot mark the changed task completed and skip it."""
        other = Agent(name="other", instructions="y", llm="gpt-4o")
        a = _team(agent)
        b = _team(agent)
        for t in b.tasks.values():
            t.agent = other
        assert a._task_set_fingerprint() != b._task_set_fingerprint()

    def test_a_changed_expected_output_changes_the_fingerprint(self, agent):
        a = _team(agent)
        b = _team(agent)
        for t in b.tasks.values():
            t.expected_output = "SOMETHING ELSE"
        assert a._task_set_fingerprint() != b._task_set_fingerprint()

    def test_a_late_description_change_is_not_missed(self, agent):
        """The old fingerprint truncated the description at 200 chars, so a
        change past that point was invisible. The full description is hashed."""
        a = _team(agent)
        b = _team(agent)
        for t in b.tasks.values():
            t.description = ("x" * 300) + "CHANGED"
        c = _team(agent)
        for t in c.tasks.values():
            t.description = ("x" * 300) + "DIFFERENT"
        assert b._task_set_fingerprint() != c._task_set_fingerprint()


class TestDurability:
    def test_a_nested_non_json_result_does_not_lose_the_checkpoint(self, agent):
        """A datetime inside a dict result would fail the JSON write and lose
        the WHOLE checkpoint; it must degrade to text for that field only."""
        import datetime
        import json

        team = _team(agent)
        first = list(team.tasks)[0]
        second = list(team.tasks)[1]
        team.tasks[first].status = "completed"
        team.tasks[first].result = {"when": datetime.datetime(2020, 1, 1)}
        team.tasks[second].status = "completed"
        team.tasks[second].result = "PLAIN"

        payload = team._team_state_payload("s1")
        # The whole payload must be JSON-writable; nothing is forfeited.
        json.dumps(payload)
        assert payload["tasks"][str(second)]["result"] == "PLAIN"

    def test_a_non_json_variable_does_not_lose_the_checkpoint(self, agent):
        import json

        team = _team(agent)
        first = list(team.tasks)[0]
        team.tasks[first].variables = {"bad": {object()}}
        payload = team._team_state_payload("s1")
        json.dumps(payload)
        assert payload["tasks"][str(first)]["variables"] == {}


class TestRestoredType:
    def test_a_restored_result_exposes_raw(self, agent):
        """process.py reads prev_task.result.raw; a bare string would raise
        AttributeError, so the restore must rebuild a TaskOutput."""
        source = _team(agent)
        first = list(source.tasks)[0]
        source.tasks[first].status = "completed"
        source.tasks[first].result = "DONE TEXT"
        payload = source._team_state_payload("s1")

        target = _team(agent)
        target._restore_serialised_task_state(payload["tasks"])
        assert target.tasks[first].result.raw == "DONE TEXT"
