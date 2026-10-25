"""Look up a local code entity through PraisonAI's existing MCP client.

Install: pip install 'praisonaiagents[mcp]'
Install Sem separately: https://github.com/Ataraxy-Labs/sem#installation
Run: python sem-mcp.py /path/to/git/repository function_name
Add --ask to have an agent explain the result (requires OPENAI_API_KEY).

The default path calls the tool directly: no model credentials or inference.
Only sem_find is exposed. Repository source stays local to the MCP process;
with --ask, retrieved context is sent to the configured model provider.
The repository argument is a lookup scope, not a filesystem security boundary.
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess

from praisonaiagents import MCP


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("entity", help="An exact entity name; qualify ambiguous names")
    parser.add_argument("--ask", action="store_true")
    args = parser.parse_args()
    repository = args.repository.expanduser().resolve()
    if not repository.is_dir():
        parser.error("repository must be an existing directory")
    if not shutil.which("sem"):
        parser.error("install the Sem executable and put it on PATH first")
    if not shutil.which("git"):
        parser.error("git must be on PATH")
    probe = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if probe.returncode:
        parser.error("repository must be inside a Git working tree")
    if args.ask and not os.environ.get("OPENAI_API_KEY"):
        parser.error("--ask requires OPENAI_API_KEY; omit it for a model-free lookup")

    # The stdio child inherits this working directory. Restore it on exit.
    previous = Path.cwd()
    try:
        os.chdir(repository)
        with MCP("sem", args=["mcp"], allowed_tools=["sem_find"]) as client:
            tools = client.get_tools()
            if len(tools) != 1 or tools[0].__name__ != "sem_find":
                raise RuntimeError("Expected exactly the sem_find tool")
            if args.ask:
                from praisonaiagents import Agent

                agent = Agent(
                    instructions="Look up the requested entity with sem_find. Report its "
                    "location and signature. Do not guess if the tool reports ambiguity.",
                    llm="gpt-4o-mini",
                    tools=tools,
                )
                agent.start(f"Find {args.entity!r} in the server's current repository.")
            else:
                result = tools[0](query=args.entity)
                if isinstance(result, dict) and result.get("mcp_error"):
                    raise RuntimeError(result.get("error", "Sem lookup failed"))
                print(result)
    finally:
        os.chdir(previous)


if __name__ == "__main__":
    main()
