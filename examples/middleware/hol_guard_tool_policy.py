"""
HOL Guard Tool Policy Example - PraisonAI Agents

Demonstrates using HOL Guard (an optional, external runtime security engine)
at the existing `wrap_tool_call` middleware boundary to inspect command-bearing
tool calls *before* they execute.

HOL Guard is installed and versioned separately. Its side-effect-free CLI can
classify a shell command before execution:

    hol-guard command test '<command>' --json

Fail-closed policy: the wrapped tool only runs when Guard returns an explicit
allow/benign classification. Review/block/unknown verdicts, malformed output,
timeouts, or CLI failures all short-circuit the call so the tool never runs.

    pip install hol-guard   # optional, external dependency
"""

import json
import shutil
import subprocess

from praisonaiagents import Agent, tool
from praisonaiagents.hooks import wrap_tool_call, ToolRequest, ToolResponse


COMMAND_BEARING_TOOLS = {"run_shell"}
GUARD_TIMEOUT_SECONDS = 10


@tool
def run_shell(command: str) -> str:
    """Run a shell command and return its output."""
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True
    )
    return result.stdout or result.stderr


def _inspect_with_hol_guard(command: str) -> bool:
    """Return True only if HOL Guard explicitly allows the command.

    Fails closed (returns False) on any ambiguity: missing CLI, non-zero exit,
    timeout, malformed JSON, or a non-allow verdict.
    """
    if not shutil.which("hol-guard"):
        return False

    try:
        completed = subprocess.run(
            ["hol-guard", "command", "test", command, "--json"],
            capture_output=True,
            text=True,
            timeout=GUARD_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False

    if completed.returncode != 0:
        return False

    try:
        verdict = json.loads(completed.stdout)
    except (json.JSONDecodeError, ValueError):
        return False

    decision = str(verdict.get("decision", "")).lower()
    return decision in ("allow", "benign")


@wrap_tool_call
def hol_guard_tool_policy(request: ToolRequest, call_next):
    """Gate command-bearing tools through HOL Guard before execution."""
    if request.tool_name not in COMMAND_BEARING_TOOLS:
        return call_next(request)

    command = request.arguments.get("command", "")

    if _inspect_with_hol_guard(command):
        return call_next(request)

    return ToolResponse(
        tool_name=request.tool_name,
        result=None,
        error="Blocked by HOL Guard: command was not explicitly allowed.",
        context=request.context,
    )


agent = Agent(
    name="GuardedShellBot",
    instructions="You run shell commands only when they are safe.",
    tools=[run_shell],
    hooks=[hol_guard_tool_policy],
)


if __name__ == "__main__":
    print("HOL Guard tool policy registered on 'run_shell'.")
    print("Commands are only executed when Guard returns an explicit allow.")
    print("\n✓ HOL Guard example complete")
