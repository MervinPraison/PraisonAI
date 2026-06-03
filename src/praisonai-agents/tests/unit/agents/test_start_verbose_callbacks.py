from types import SimpleNamespace
import sys


def test_start_verbose_composed_callbacks_forward_all_arguments(monkeypatch):
    from praisonaiagents import Agent, AgentTeam

    on_start_calls = []
    on_complete_calls = []
    debug_messages = []

    def on_task_start(task, task_id):
        on_start_calls.append((task, task_id))

    def on_task_complete(task, task_output):
        on_complete_calls.append((task, task_output))

    team = AgentTeam(
        agents=[
            Agent(name="Researcher", instructions="Research"),
            Agent(name="Writer", instructions="Write"),
        ],
        hooks={
            "on_task_start": on_task_start,
            "on_task_complete": on_task_complete,
        },
    )

    def fake_run_all_tasks():
        task_id, task = next(iter(team.tasks.items()))
        task_output = SimpleNamespace(raw="done")
        team.on_task_start(task, task_id)
        team.on_task_complete(task, task_output)

    monkeypatch.setattr(team, "run_all_tasks", fake_run_all_tasks)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr("praisonaiagents.agents.agents.logging.debug", lambda msg: debug_messages.append(str(msg)))

    team.start(output="verbose")

    assert len(on_start_calls) == 1
    assert len(on_complete_calls) == 1
    assert on_start_calls[0][1] == next(iter(team.tasks.keys()))
    assert on_complete_calls[0][1].raw == "done"
    assert all("Error in verbose task" not in message for message in debug_messages)
