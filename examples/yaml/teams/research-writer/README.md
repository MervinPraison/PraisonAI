# Simple Sequential Team (YAML)

A minimal 2-agent sequential team: a **researcher** gathers facts, then a
**writer** summarizes them. This is the copy-paste starting point for the most
common multi-agent pattern (2–5 agents, run in order).

```
research_task  ->  summary_task
 (researcher)       (writer)
```

## Files

| File | Purpose |
|------|---------|
| `agents.yaml` | Roles (who) + their tasks (what); tasks run in declaration order |

> **Which loader applies?** This example uses the canonical single-file format
> consumed by `AgentsGenerator.generate_crew_and_kickoff()`
> (`src/praisonai/praisonai/agents_generator.py`). Agents live under `roles:`,
> each with nested `tasks:`. **Tasks run in the order they are declared** — the
> researcher's task first, then the writer's. (An optional top-level
> `dependencies:` block is included to document intent and mirror the canonical
> fixture, but the roles-file loader sequences by declaration order, so keep
> tasks in the order you want them to run.) No new loader module is required —
> this is the existing YAML path.

## Run it

```bash
export OPENAI_API_KEY=sk-...
praisonai examples/yaml/teams/research-writer/agents.yaml
```

This positional-file form is the canonical roles-file entry point. From Python
the equivalent is `praisonai.run("agents.yaml")` (see
`src/praisonai/praisonai/_entrypoint.py`), which dispatches to the same
`AgentsGenerator`.

Change the subject by editing the `topic:` line in `agents.yaml` (interpolated
into every `{topic}` placeholder).

## When to use this vs a workflow YAML

| You need… | Use | Example |
|-----------|-----|---------|
| 2–5 agents, sequential/hierarchical | **This** (`roles:` + `tasks:`) | `agents.yaml` here |
| Routing by classifier output | workflow YAML | `../../workflows/routing_workflow.yaml` |
| Parallel branches | workflow YAML | `../../workflows/parallel_workflow.yaml` |
| Loops / planning / memory | workflow YAML | `../../workflows/complete_workflow.yaml` |

## Python equivalent

```python
from praisonaiagents import Agent, Task, PraisonAIAgents

researcher = Agent(role="Senior Researcher", goal="Find accurate information")
writer = Agent(role="Report Writer", goal="Turn research into summaries")

t1 = Task(description="Research renewable energy and list 5 key facts", agent=researcher)
t2 = Task(description="Write a 3-sentence summary from the research", agent=writer, context=[t1])

PraisonAIAgents(agents=[researcher, writer], tasks=[t1, t2]).start()
```
