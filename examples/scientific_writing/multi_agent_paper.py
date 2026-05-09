"""Multi-agent scientific paper workflow (Researcher -> Methodologist -> Writer).

Demonstrates the agent-centric pattern from AGENTS.md: compose specialised
Agents with ``AgentTeam`` + sequential ``Task``s instead of creating custom
Agent subclasses.  The writer uses the CAJAL-4B HuggingFace model; the
reviewer and methodologist use general-purpose LLMs.

Usage:
    python examples/scientific_writing/multi_agent_paper.py
"""
from praisonaiagents import Agent, AgentTeam, Task

from scientific_writer import (  # noqa: E402 — example imports a sibling file
    build_scientific_writer,
    format_citation,
    format_latex_section,
)


literature_reviewer = Agent(
    name="Literature Reviewer",
    instructions=(
        "You are an expert at surveying academic literature. "
        "Produce a concise literature review with 5-8 key citations in APA."
    ),
    tools=[format_citation],
)

methodology_designer = Agent(
    name="Methodology Designer",
    instructions=(
        "You design rigorous research methodologies. "
        "Output a clear, reproducible methods section."
    ),
    tools=[format_latex_section],
)

scientific_writer = build_scientific_writer()


def run(topic: str) -> str:
    """Run the 3-agent workflow for a given research ``topic``."""
    t1 = Task(
        name="review_literature",
        description=f"Review literature on: {topic}",
        agent=literature_reviewer,
        expected_output="APA literature review.",
    )
    t2 = Task(
        name="design_methodology",
        description=f"Design research methodology for: {topic}",
        agent=methodology_designer,
        expected_output="LaTeX methods section.",
    )
    t3 = Task(
        name="write_paper",
        description=(
            f"Combine the literature review and methodology into a full "
            f"scientific paper on: {topic}. Use LaTeX formatting."
        ),
        agent=scientific_writer,
        expected_output="Complete LaTeX paper.",
    )
    team = AgentTeam(
        agents=[literature_reviewer, methodology_designer, scientific_writer],
        tasks=[t1, t2, t3],
    )
    return team.start()


if __name__ == "__main__":
    result = run("Transformer architectures for protein folding prediction")
    print(result)
