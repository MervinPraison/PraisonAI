"""Motion Graphics — full team pipeline (requires praisonaiagents + LLM key).

Runs the coordinator + animator team (optionally with researcher and
code-explorer specialists) under a hierarchical process, so the coordinator
validates outputs before marking a render as successful.

Requirements:
    pip install praisonai-tools[video-motion] praisonaiagents[llm]
    playwright install chromium
    export ANTHROPIC_API_KEY=...
    export MOTION_LLM=anthropic/claude-sonnet-4-20250514
"""

import os
import time
from pathlib import Path

from praisonai_tools.video.motion_graphics import motion_graphics_team


def main() -> None:
    workspace = Path("/tmp/motion_graphics_team_demo")
    workspace.mkdir(exist_ok=True)

    llm = os.getenv("MOTION_LLM", "anthropic/claude-sonnet-4-20250514")

    print(f"[setup] workspace={workspace}  llm={llm}")

    team = motion_graphics_team(
        research=False,           # set True to add a web-search researcher
        code_exploration=False,   # set True to add a GitTools code-explorer
        workspace=workspace,
        llm=llm,
    )

    print(f"[setup] {len(team.agents)} agents: {[a.name for a in team.agents]}")

    prompt = "Animate Dijkstra's algorithm on a small weighted graph, 30s."
    print(f"[run] prompt: {prompt}")

    t0 = time.time()
    result = team.start(prompt)
    elapsed = time.time() - t0

    print(f"[done] elapsed={elapsed:.1f}s")
    print(f"[result] {result!r}")

    print("\n[artifacts]")
    for p in sorted(workspace.rglob("*.mp4")):
        print(f"  mp4  {p}  ({p.stat().st_size} bytes)")
    for p in sorted(workspace.rglob("*.html")):
        print(f"  html {p}  ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
