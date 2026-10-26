"""Definitions whose graphs are pinned as golden JSON (see test_graph.py).

Kept in their own module so a subprocess can rebuild them and prove the node
ids do not depend on the process (hash seed, uuids, object ids).
"""


def search_web(query: str) -> str:
    """Search the web."""
    return query


def score(ctx):
    return "approved"


def fetch(ctx):
    return "a,b"


def tidy(ctx):
    return "ok"


def team():
    from praisonaiagents import Agent, Task
    from praisonaiagents.agents.agents import AgentTeam

    researcher = Agent(name="Researcher", instructions="Find facts", tools=[search_web])
    billing = Agent(name="Billing", instructions="Handle billing")
    writer = Agent(name="Writer", instructions="Write", handoffs=[billing])
    research = Task(name="research", description="Find facts", agent=researcher,
                    is_start=True, next_tasks=["draft"])
    draft = Task(name="draft", description="Write the piece", agent=writer,
                 context=[research], human_input=True,
                 condition={"approved": ["publish"], "rejected": ["research"]})
    publish = Task(name="publish", description="Ship it", agent=writer)
    unnamed = Task(description="Archive everything afterwards", agent=writer)
    return AgentTeam(agents=[researcher, writer], tasks=[research, draft, publish, unnamed],
                     process="workflow", name="newsroom")


def sequential_team():
    from praisonaiagents import Agent, Task
    from praisonaiagents.agents.agents import AgentTeam

    researcher = Agent(name="Researcher", instructions="Find facts", tools=[search_web])
    writer = Agent(name="Writer", instructions="Write")
    return AgentTeam(
        agents=[researcher, writer],
        tasks=[
            Task(name="research", description="Find facts", agent=researcher),
            Task(name="write", description="Write it up", agent=writer),
            Task(name="write", description="Write it again", agent=writer),
        ],
        name="pair",
    )


def hierarchical_team():
    from praisonaiagents import Agent, Task
    from praisonaiagents.agents.agents import AgentTeam

    researcher = Agent(name="Researcher", instructions="Find facts", tools=[search_web])
    writer = Agent(name="Writer", instructions="Write")
    return AgentTeam(
        agents=[researcher, writer],
        tasks=[
            Task(name="research", description="Find facts", agent=researcher),
            Task(name="write", description="Write it up", agent=writer),
        ],
        process="hierarchical",
        manager_llm="gpt-4o-mini",
        name="managed",
    )


def flow():
    from praisonaiagents import Agent
    from praisonaiagents.workflows.workflows import (
        AgentFlow, Discussion, If, Include, Loop, Parallel, Repeat, Route,
    )

    researcher = Agent(name="Researcher", instructions="Find facts", tools=[search_web])
    critic = Agent(name="Critic", instructions="Critique")
    return AgentFlow(
        name="pipeline",
        steps=[
            researcher,
            score,
            Route(routes={"approved": [tidy], "default": [fetch]}),
            Parallel(steps=[fetch, tidy]),
            Loop(step=tidy, over="items"),
            If(condition="{{score}} > 80", then_steps=[tidy], else_steps=[Repeat(fetch, max_iterations=2)]),
            Discussion(agents=[researcher, critic], rounds=1),
            researcher,
            Include(recipe="publisher"),
        ],
    )


BUILDERS = {
    "team": team,
    "sequential_team": sequential_team,
    "hierarchical_team": hierarchical_team,
    "flow": flow,
}
