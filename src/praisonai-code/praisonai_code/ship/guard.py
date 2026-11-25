"""Never-merge guard for the ship and steward agents.

The user merges; the agent never does. A before_tool hook refuses any shell
command that merges, approves, enables auto-merge or force-pushes. A hook
runs before the permission store, so an earlier "always" approval of
``bash:gh pr *`` cannot let a merge through.

This is a guard rail, not a security boundary: a string filter cannot see
every form (for example ``python -c "os.system('gh pr merge 1')"``). The real
backstop is branch protection or a token without merge rights.
"""

from typing import List, Optional

from praisonaiagents.hooks import HookEvent, HookResult
from praisonaiagents.permissions.command_parser import parse_command

# Tool-input keys that carry a shell command.
_COMMAND_KEYS = ("command", "cmd", "script")
# gh / git global options that take a value before the subcommand.
_VALUE_FLAGS = {"-R", "--repo", "-C", "-c", "--git-dir", "--work-tree"}
# GraphQL mutations that merge, enable auto-merge or approve.
_MERGE_MUTATIONS = ("mergepullrequest", "enablepullrequestautomerge")
_FORCE_FLAGS = {"-f", "--force", "--force-with-lease", "--force-if-includes", "--mirror"}


def _words(args: List[str]) -> List[str]:
    """Positional words, skipping leading global options and their values."""
    out, skip = [], False
    for arg in args:
        if skip:
            skip = False
        elif arg in _VALUE_FLAGS:
            skip = True
        elif not arg.startswith("-"):
            out.append(arg)
    return out


def _api_reason(words: List[str], args: List[str]) -> Optional[str]:
    """Refuse ``gh api`` calls that merge or approve, over REST or GraphQL."""
    text = " ".join(args).lower().replace(" ", "")
    paths = [w.split("?", 1)[0].rstrip("/") for w in words]
    # .../pulls/N/merge merges a PR; .../merges merges one branch into another.
    if any(p.endswith(("/merge", "/merges")) for p in paths) or any(m in text for m in _MERGE_MUTATIONS):
        return "merging a pull request through the API is left to the user"
    if "event=approve" in text or ("addpullrequestreview" in text and "approve" in text):
        return "approving a pull request through the API is left to the user"
    if "graphql" in words and ("--input" in args or "=@" in text):
        return "a GraphQL query read from a file cannot be checked"
    return None


def _approves(args: List[str]) -> bool:
    """``gh pr review`` approves: ``--approve[=v]`` or ``-a``, also combined (``-ab x``)."""
    for arg in args:
        if arg.split("=", 1)[0] == "--approve":
            return True
        if arg.startswith("-") and not arg.startswith("--"):
            # Short flags combine until one that takes a value (-b body, -F file).
            for ch in arg[1:]:
                if ch == "a":
                    return True
                if ch in "bF":
                    break
    return False


def _op_reason(executable: str, args: List[str]) -> Optional[str]:
    name = executable.rsplit("/", 1)[-1]
    words = _words(args)
    if name == "gh":
        if words[:2] == ["pr", "merge"]:
            return "merging a pull request is left to the user"
        if words[:2] == ["pr", "review"] and _approves(args):
            return "approving a pull request is left to the user"
        if words[:1] == ["api"]:
            return _api_reason(words, args)
    if name == "git" and "push" in words:
        flags = {a.split("=", 1)[0] for a in args}
        short = "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--"))
        if _FORCE_FLAGS & flags or "f" in short:
            return "force-pushing is left to the user"
        if any(w.startswith("+") for w in words[words.index("push") + 1:]):
            return "force-pushing (a '+' refspec) is left to the user"
    return None


def forbidden_reason(command: str) -> Optional[str]:
    """Why ``command`` is refused, or ``None`` when it may run."""
    for op in parse_command(command or ""):
        reason = _op_reason(op.executable, op.args)
        if reason:
            return reason
    return None


def never_merge_hook(data) -> HookResult:
    """before_tool hook: deny a tool call whose command merges, approves or force-pushes."""
    tool_input = getattr(data, "tool_input", None) or {}
    for key in _COMMAND_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str):
            reason = forbidden_reason(value)
            if reason:
                return HookResult.deny(f"ship never merges: {reason} ({value!r})")
    return HookResult.allow()


def register_never_merge(registry) -> str:
    """Add the guard to a HookRegistry so it runs first and stops the chain."""
    return registry.register_function(
        HookEvent.BEFORE_TOOL,
        never_merge_hook,
        name="ship_never_merge",
        description="ship/steward never merge, approve or force-push",
        sequential=True,
        priority=0,
    )
