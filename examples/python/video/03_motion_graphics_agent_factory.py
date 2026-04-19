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
        "Create a 6-second title-card animation with the text 'Hello Motion' "
        "fading in and a cyan underline drawing across. Save as intro.mp4."
    )

    print("\nArtifacts in workspace:")
    for p in sorted(workspace.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(workspace)}  ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
