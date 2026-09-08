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
        assert target.tasks[first].result == "FIRST DONE"

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
