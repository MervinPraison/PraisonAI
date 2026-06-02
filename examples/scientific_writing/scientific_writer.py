"""Scientific Paper Writer — single-agent example using the CAJAL model.

CAJAL (``Agnuxo/CAJAL-4B-P2PCLAW``) is a 4B-parameter HuggingFace model
specialised for LaTeX-formatted academic writing.  This example shows how
to use it with a regular ``Agent`` and ``@tool`` functions — no new Agent
subclass is needed.  Run 3 ways: Python (this file), CLI, or YAML.

Requirements:
    pip install "praisonaiagents[llm]"          # for litellm / HuggingFace
    export HUGGINGFACE_API_KEY=...              # or run a local inference server

Usage:
    python examples/scientific_writing/scientific_writer.py
"""
from praisonaiagents import Agent, tool


@tool
def format_latex_section(title: str, content: str) -> str:
    """Wrap prose content in a LaTeX ``\\section{}`` block.

    Args:
        title: Section heading (e.g. ``"Introduction"``).
        content: The body text.

    Returns:
        LaTeX-formatted section string.
    """
    return f"\\section{{{title}}}\n{content}\n"


@tool
def format_citation(authors: str, year: int, title: str, venue: str) -> str:
    """Render a single APA-style citation line.

    Args:
        authors: ``"Smith, J. & Jones, A."``
        year: Publication year.
        title: Paper title.
        venue: Journal / conference name.

    Returns:
        One APA-formatted citation string.
    """
    return f"{authors} ({year}). {title}. *{venue}*."


SCIENTIFIC_INSTRUCTIONS = """You are a specialised scientific paper writer.

Produce high-quality academic content with:
- Clear structure (Abstract, Introduction, Methodology, Results, Discussion,
  Conclusion, References)
- Rigorous methodology and precise language
- Proper APA citations and LaTeX formatting
- Honest limitations and future work sections

Use ``format_latex_section`` to wrap each section in LaTeX, and
``format_citation`` to build the References list.
"""


def build_scientific_writer(
    model: str = "huggingface/Agnuxo/CAJAL-4B-P2PCLAW",
) -> Agent:
    """Construct a scientific-writing Agent.

    Override ``model`` for any HuggingFace / local / API model — the default
    targets the CAJAL-4B checkpoint for LaTeX-style academic output.
    """
    return Agent(
        name="Scientific Writer",
        instructions=SCIENTIFIC_INSTRUCTIONS,
        llm=model,
        tools=[format_latex_section, format_citation],
    )


if __name__ == "__main__":
    agent = build_scientific_writer()
    paper = agent.start(
        "Write a short scientific paper (Abstract + Introduction + Conclusion) "
        "on 'Climate change effects on coral reef biodiversity'. "
        "Use LaTeX formatting and include at least 3 APA citations."
    )
    print(paper)
