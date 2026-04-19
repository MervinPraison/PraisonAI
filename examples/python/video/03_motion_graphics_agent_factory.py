"""Motion Graphics — single-agent factory (requires praisonaiagents + LLM key).

Creates a single motion-graphics authoring agent that writes HTML/GSAP and
renders to MP4 via the HTML backend. Good for quick, one-shot prompts.

Requirements:
    pip install praisonai-tools[video-motion] praisonaiagents[llm]
    playwright install chromium
    export ANTHROPIC_API_KEY=...        # or OPENAI_API_KEY, etc.

Set a working model via env (LiteLLM routing):
    export MOTION_LLM=anthropic/claude-sonnet-4-20250514
"""

import os
from pathlib import Path

from praisonai_tools.video.motion_graphics import create_motion_graphics_agent


def main() -> None:
    workspace = Path("/tmp/motion_graphics_agent_demo")
    workspace.mkdir(exist_ok=True)

    llm = os.getenv("MOTION_LLM", "anthropic/claude-sonnet-4-20250514")

    agent = create_motion_graphics_agent(
        backend="html",
        workspace=workspace,
        max_retries=3,
        llm=llm,
    )

    print(f"Agent:     {agent.name}")
    print(f"Backend:   {agent._motion_graphics_backend.__class__.__name__}")
    print(f"Workspace: {agent._motion_graphics_workspace}")
    print(f"Retries:   {agent._motion_graphics_max_retries}")
    print(f"LLM:       {llm}")
    print()
    print("Starting agent...\n")

    agent.start(
        "Create a short title-card animation.\n"
        "Steps you MUST follow, in order:\n"
        "  1. Call write_file with filepath='index.html' and content containing "
        "     a complete HTML document with GSAP 3.12 from cdnjs, a #stage div "
        "     with data-duration='3.0', visible text 'Hello Motion' that fades "
        "     in, and a cyan underline that draws across. The file MUST set "
        "     window.__timelines = [tl] at the end of its <script> block, and "
        "     the timeline MUST be created with { paused: true }.\n"
        "  2. Call lint_composition() and verify ok=True.\n"
        "  3. Call render_composition(output_name='intro.mp4', fps=30, "
        "     quality='standard') and report the resulting output_path.\n"
        "Return the concrete output_path of the MP4 or the exact stderr."
    )

    print("\nArtifacts in workspace:")
    for p in sorted(workspace.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(workspace)}  ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
