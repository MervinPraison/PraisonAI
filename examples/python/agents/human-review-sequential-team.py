"""
Human Review Between Sequential AgentTeam Tasks
================================================

Demonstrates a human-in-the-loop review gate between sequential tasks using the
existing ``on_task_complete`` hook — no new API required.

IMPORTANT — two different ``on_task_complete`` hooks exist, with DIFFERENT
signatures. Do not confuse them:

    AgentTeam(hooks=MultiAgentHooksConfig(on_task_complete=fn))
        -> fn(task, task_output)          # team-level; gets the Task and its output

    Task(on_task_complete=fn)
        -> fn(task_output)                # 1 param: just the TaskOutput
        -> fn(task_output, metadata)      # 2+ params: TaskOutput + metadata dict
                                          #   NOTE: NOT (task, task_output)

This example uses the TEAM-level hook so we get ``(task, task_output)`` and can
filter which tasks require review by ``task.name``.

Approve / reject / edit:
- approve -> return, workflow continues
- reject  -> raise; see "stopping the workflow" note below
- edit    -> mutate ``task_output.raw``; downstream tasks that read this task via
             ``context=[...]`` pick up the edited text

Stopping the workflow on reject
-------------------------------
The TEAM-level hook logs and swallows exceptions, so a bare ``raise`` inside it
does NOT stop the sequential run today. To hard-stop on reject, use the PER-TASK
callback path with the 1-argument signature and ``fail_on_callback_error=True``
(see ``review_output`` / ``t1_strict`` at the bottom of this file).
"""

from praisonaiagents import Agent, Task, AgentTeam
from praisonaiagents.config.feature_configs import MultiAgentHooksConfig

# Only these task names trigger a human review gate.
REVIEW_TASKS = {"research"}


# --- Team-level review gate: signature is (task, task_output) ---------------
def review_gate(task, task_output):
    if task.name not in REVIEW_TASKS:
        return

    print(f"\n--- Review: {task.name} ---\n{task_output.raw}\n")
    choice = input("Approve (y), reject (n), edit (e)? ").strip().lower()

    if choice == "n":
        # NOTE: team-level hook swallows this; see per-task strict path below
        # for a version that actually halts the workflow.
        raise RuntimeError(f"Human rejected task '{task.name}'")

    if choice == "e":
        # task.result is the same object as task_output, so mutating .raw here
        # propagates to downstream tasks that use context=[this_task].
        task_output.raw = input("Edited output: ").strip()


researcher = Agent(name="Researcher", role="Researcher", goal="Research", backstory="Expert")
writer = Agent(name="Writer", role="Writer", goal="Write", backstory="Writer")

t1 = Task(
    name="research",
    description="List 5 facts about {{topic}}",  # {{...}} is the substitution syntax
    expected_output="5 bullets",
    agent=researcher,
)
t2 = Task(
    name="summary",
    description="Write 3-sentence summary",
    expected_output="3 sentences",
    agent=writer,
    context=[t1],  # reads the (possibly edited) output of t1
)

team = AgentTeam(
    agents=[researcher, writer],
    tasks=[t1, t2],
    process="sequential",
    variables={"topic": "REST APIs"},  # substituted into {{topic}} in task descriptions
    hooks=MultiAgentHooksConfig(on_task_complete=review_gate),
)


# --- Alternative: per-task strict gate that HALTS on reject -----------------
# Per-task Task.on_task_complete uses the 1-argument signature (task_output).
# With fail_on_callback_error=True a raised exception re-raises and stops the run.
def review_output(task_output):
    print(f"\n--- Review output ---\n{task_output.raw}\n")
    if input("Approve? (y/n) ").strip().lower() == "n":
        raise RuntimeError("Human rejected output")


t1_strict = Task(
    name="research",
    description="List 5 facts about {{topic}}",
    expected_output="5 bullets",
    agent=researcher,
    variables={"topic": "REST APIs"},
    on_task_complete=review_output,     # signature: (task_output)
    fail_on_callback_error=True,        # required so reject halts the workflow
)


if __name__ == "__main__":
    # NOTE: template values come from AgentTeam(variables=...), NOT start(inputs=...).
    # start() forwards **kwargs but does not consume an ``inputs`` argument.
    team.start()
