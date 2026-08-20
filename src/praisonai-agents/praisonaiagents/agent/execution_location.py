"""Describe, in plain English, where an agent's work actually happens.

PraisonAI can run the thinking (LLM calls) and the tools in different places:
this machine, a container, or a provider's cloud. Which one you get depends on
``run_on=``, ``backend=`` and ``sandbox=``, and until now none of that was
visible from the object -- ``repr(agent)`` was the bare default.

This module is the single source of that answer, shared by ``Agent``,
``AgentTeam`` and ``AgentFlow`` so all three describe themselves identically.

Vocabulary note: the fields are ``thinks_on`` / ``tools_run_on``, never
``loop``. "Loop" is already a public workflow primitive here
(``praisonaiagents.workflows.loop()``), asyncio's event loop, and agent-loop
jargon a beginner would not know -- three meanings for one word is exactly the
problem this module exists to fix.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Provider name -> how a human would say it out loud.
_PLACE_WORDS = {
    "local": "this machine",
    "subprocess": "a separate process on this machine",
    "sandlock": "a locked-down process on this machine",
    "docker": "a Docker container",
    "e2b": "an E2B cloud sandbox",
    "modal": "a Modal cloud sandbox",
    "daytona": "a Daytona cloud sandbox",
    "flyio": "a Fly.io machine",
    "tenki": "a Tenki cloud sandbox",
    "novita": "a Novita cloud sandbox",
    "ssh": "a remote machine over SSH",
    "anthropic": "Anthropic's cloud",
}

HERE = "this machine"

# Public sandbox aliases the SandboxManager collapses before it picks a backend
# (see praisonaiagents/sandbox/manager.py). We must describe the backend that
# actually runs, not the alias the user typed, or "native"/"local" would report
# a place that never executes.
_ALIASES = {"native": "sandlock", "local": "subprocess"}

# ...but only for the SANDBOX registry. "local" resolves to two different
# backends depending on which parameter carried it:
#   run_in="local"        -> SandboxManager collapses it to subprocess:
#                            scrubbed environment, blocked commands and paths
#   tools_run_on="local"  -> the wrapper's LocalCompute: a plain shell in the
#                            current directory, full environment inherited,
#                            no security policy at all
# Describing the second in the first's words overstates it, which is the exact
# failure this module exists to prevent. One word, two backends -- so the
# phrase has to depend on where the word came from.
_COMPUTE_ONLY_WORDS = {"local": "a plain shell on this machine (no policy applied)"}

# Tiers that separate a process but do NOT contain it. Verified: under the
# subprocess backend, outbound network still works and ~/.ssh is readable even
# though SecurityPolicy declares them blocked.
# `native` is deliberately absent: it aliases sandlock, which applies Landlock,
# seccomp, a scrubbed environment and deny-all networking. Listing it here made
# tools_run_on="native" and tools_run_on="sandlock" -- the same backend --
# disagree about whether they contain anything.
_NOT_A_BOUNDARY = {"subprocess", "local"}


def say_place(name: Any, *, via: str = "sandbox") -> str:
    """Turn a place name into a phrase a non-developer can read.

    ``via`` says which registry resolved the name -- ``"compute"`` for
    ``tools_run_on=``, ``"sandbox"`` for ``run_in=``. It only matters for names
    that mean different backends in each (see ``_COMPUTE_ONLY_WORDS``).
    """
    if name is None:
        return HERE
    if name is True:
        return _PLACE_WORDS["subprocess"]
    if not isinstance(name, str):
        # A configured provider instance: use its own declared name if it has
        # one. Normalise BEFORE the compute-only check, or a backend holding a
        # LocalCompute object (provider_name="local") skips the branch and gets
        # described in the subprocess backend's stronger words -- the exact
        # overstatement this module exists to prevent.
        name = getattr(name, "provider_name", None) or type(name).__name__
    if via == "compute" and name.lower() in _COMPUTE_ONLY_WORDS:
        return _COMPUTE_ONLY_WORDS[name.lower()]
    key = str(name).lower()
    key = _ALIASES.get(key, key)

    known = _PLACE_WORDS.get(key)
    if known:
        return known

    # A place contributed by another package can name itself; the bare name is
    # the last resort rather than the only option, because the phrase table is
    # a literal that cannot know about packages installed later.
    try:
        from ..managed._compute_bridge import contributed_display_name

        declared = contributed_display_name(key)
        if declared:
            return declared
    except Exception:
        pass
    return str(name)


def _backend_places(backend: Any) -> Optional[Dict[str, str]]:
    """Where does a managed ``backend=`` put the thinking and the tools?"""
    if backend is None:
        return None

    # Ask the backend what it is, rather than guessing from its class name.
    # Name-matching missed any backend that did not happen to contain "Hosted"
    # or "Anthropic" -- a self-hosted docker backend reported that it was
    # thinking on this machine while the whole loop ran in a container.
    declared = getattr(backend, "provider_name", None)
    if isinstance(declared, str):
        try:
            from .placement import managed_runtimes

            if declared.lower() in managed_runtimes():
                where = say_place(declared)
                return {"thinks_on": where, "tools_run_on": where}
        except Exception:
            pass

    cls = type(backend).__name__
    # Hosted runtimes move the entire turn off this machine.
    if "Hosted" in cls or "Anthropic" in cls:
        provider = getattr(backend, "provider", None) or "anthropic"
        where = say_place(provider)
        return {"thinks_on": where, "tools_run_on": where}

    # Local/sandboxed agents keep the loop here and may push tools out. A
    # backend's compute object is a COMPUTE-registry provider, so it is read
    # with the compute vocabulary: a LocalCompute here is the unrestricted
    # shell, not the subprocess backend "local" collapses to under run_in=.
    compute = getattr(backend, "_compute", None) or getattr(backend, "compute", None)
    if compute is not None:
        return {"thinks_on": HERE, "tools_run_on": say_place(compute, via="compute")}
    return {"thinks_on": HERE, "tools_run_on": HERE}


def describe(obj: Any, *, shared: bool = False) -> Dict[str, str]:
    """Return ``{thinks_on, tools_run_on, code_runs_on?}`` for an object.

    Never raises: a description of where things run must not be able to break
    the thing it describes.
    """
    places: Dict[str, str] = {"thinks_on": HERE, "tools_run_on": HERE}
    try:
        from_backend = _backend_places(getattr(obj, "backend", None))
        if from_backend:
            places.update(from_backend)

        where_tools = getattr(obj, "tools_run_on", None)
        if where_tools is not None:
            where = say_place(where_tools, via="compute")
            places["tools_run_on"] = f"{where} (shared)" if shared else where

        # run_on= puts the WHOLE agent on a managed runtime, so it moves the
        # thinking as well. _backend_places() already reports that (run_on= is
        # turned into a backend at construction); this only covers an object
        # that carries the name without a built backend.
        whole = getattr(obj, "run_on", None)
        if whole is not None and not from_backend:
            everywhere = say_place(whole)
            places["thinks_on"] = everywhere
            places["tools_run_on"] = everywhere

        sandbox_config = getattr(obj, "sandbox_config", None)
        if sandbox_config is not None:
            places["code_runs_on"] = say_place(
                getattr(sandbox_config, "sandbox_type", None)
            )
    except Exception:  # pragma: no cover - description must never break callers
        pass
    return places


def _tools_staying_here(obj: Any) -> list:
    """Names of the object's own tools, which do NOT move to the sandbox.

    Only four tool names are bridged (``execute_command``, ``read_file``,
    ``write_file``, ``list_files``); everything else the user passed keeps
    running in this process, against this filesystem. The capability prompt
    tells the model the sandbox is where things happen, so anything staying
    behind has to be said out loud.

    Reads the pre-attach tool list when a sandbox is already attached: by then
    ``agent.tools`` has been rewritten and the originals live in the sandbox's
    restore record.
    """
    try:
        from ..managed.shared_compute import BRIDGED_TOOL_NAMES
    except Exception:
        BRIDGED_TOOL_NAMES = ("execute_command", "read_file", "write_file", "list_files")

    tools = None
    shared = getattr(obj, "_tools_sandbox", None)
    if shared is not None:
        for patched, original_tools, _ in getattr(shared, "_patched", []):
            if patched is obj:
                tools = original_tools
                break
    if tools is None:
        tools = getattr(obj, "tools", None) or []

    names = []
    for tool in tools:
        name = getattr(tool, "__name__", None) or getattr(tool, "name", None)
        if isinstance(name, str) and name not in BRIDGED_TOOL_NAMES:
            names.append(name)
    return names


def repr_fields(obj: Any, *, shared: bool = False) -> str:
    """Render the places as ``key='value'`` pairs for a ``__repr__``."""
    return ", ".join(f"{k}={v!r}" for k, v in describe(obj, shared=shared).items())


def explain(obj: Any, *, shared: bool = False) -> str:
    """Plain-sentence answer to "where does this actually run?".

    Deliberately uses only words a non-engineer already knows -- no "loop",
    "harness", "provision" or "runtime".
    """
    places = describe(obj, shared=shared)
    lines = [
        f"Thinking (the AI model calls) happens on {places['thinks_on']}.",
        f"Tools run on {places['tools_run_on']}.",
    ]

    if shared and getattr(obj, "tools_run_on", None) is not None:
        lines.append(
            "Every step shares that same sandbox, so a file written by one step "
            "is visible to the next."
        )

    staying = _tools_staying_here(obj)
    if staying and places["tools_run_on"] != places["thinks_on"]:
        listed = ", ".join(staying[:6]) + ("..." if len(staying) > 6 else "")
        lines.append(
            f"Your own tools ({listed}) still run on {HERE} -- only shell, file "
            f"and code tools move. They read and write this machine's files."
        )

    if "code_runs_on" in places:
        lines.append(
            f"Code you run yourself with execute_code() runs on {places['code_runs_on']}."
        )

    # Say plainly when the chosen tier is not a security boundary.
    raw = [
        getattr(obj, "tools_run_on", None),
        getattr(obj, "run_on", None),
        getattr(getattr(obj, "sandbox_config", None), "sandbox_type", None),
    ]
    if any(isinstance(v, str) and v.lower() in _NOT_A_BOUNDARY for v in raw) or any(
        v is True for v in raw
    ):
        lines.append(
            "Note: a separate process is not a security boundary -- it can still "
            "reach the network and read your files, and its blocked-command "
            "list can be worked around by ordinary shell syntax. Use docker or a cloud "
            "provider for untrusted code."
        )

    if places["thinks_on"] == HERE and places["tools_run_on"] == HERE:
        lines.append(
            "Nothing is isolated: tools you pass run in this program, with your "
            "permissions."
        )
    return "\n".join(lines)
