"""The warm runtime must build the same agent the cold path would.

`praisonai run "<prompt>"` with a daemon up silently forwards to the warm
runtime. That runtime constructed a bare ``Agent(name, role, goal, llm)``: no
project-local ``.praisonai/tools/*.py``, and no AGENTS.md/CLAUDE.md subtree
hook. The agent then returns fluent text and exits 0 having touched nothing --
which reads as a completed task until you check the filesystem.

``run_main`` already keeps ``--tools``/``--toolset``/``--mcp``/``--instructions``
runs in-process, so what was missing is exactly the two *implicit*,
project-scoped sources tested here.
"""

import ast
from pathlib import Path

import pytest

from praisonai_code.runtime import server as server_mod
from praisonai_code.runtime.server import _apply_cold_path_parity


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project with a local tool and an AGENTS.md, made the cwd."""
    tools_dir = tmp_path / ".praisonai" / "tools"
    tools_dir.mkdir(parents=True)
    (tools_dir / "shout.py").write_text(
        "def shout(text: str) -> str:\n"
        '    """Return TEXT, loudly."""\n'
        "    return text.upper()\n"
    )
    (tmp_path / "AGENTS.md").write_text("# Rules\nAlways use tabs.\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")
    return tmp_path


def test_project_local_tools_reach_the_runtime_agent(project):
    config = {"name": "RuntimeAgent", "role": "Assistant", "goal": "Complete the task"}

    _apply_cold_path_parity(config)

    names = [getattr(t, "__name__", str(t)) for t in (config.get("tools") or [])]
    assert "shout" in names, (
        f"the daemon-built agent has no project-local tools: {names}"
    )


def test_project_rules_hook_reaches_the_runtime_agent(project):
    config = {"name": "RuntimeAgent", "role": "Assistant", "goal": "Complete the task"}

    _apply_cold_path_parity(config)

    assert config.get("hooks") is not None, (
        "AGENTS.md/CLAUDE.md subtree instructions were never wired"
    )


def test_no_rules_opt_out_is_honoured(project, monkeypatch):
    """PRAISON_NO_RULES must suppress the hook here as it does in-process."""
    monkeypatch.setenv("PRAISON_NO_RULES", "1")
    config = {"name": "RuntimeAgent"}

    _apply_cold_path_parity(config)

    assert config.get("hooks") is None


def test_local_tools_opt_in_is_honoured(project, monkeypatch):
    """Loading local tools runs user code; without the opt-in, load nothing."""
    monkeypatch.delenv("PRAISONAI_ALLOW_LOCAL_TOOLS", raising=False)
    config = {"name": "RuntimeAgent"}

    _apply_cold_path_parity(config)

    assert not config.get("tools")


def test_parity_never_breaks_a_turn(project, monkeypatch):
    """A failure in the parity wiring must not propagate to the daemon."""
    import praisonai_code.cli.commands.run as run_mod

    def _boom(*a, **k):
        raise RuntimeError("discovery exploded")

    monkeypatch.setattr(run_mod, "_auto_discover_project_tools", _boom)
    monkeypatch.setattr(run_mod, "_wire_subtree_context_hook", _boom)

    config = {"name": "RuntimeAgent"}
    _apply_cold_path_parity(config)  # must not raise
    assert config == {"name": "RuntimeAgent"}


def _methods_calling(name):
    """Names of WarmRuntime methods that call ``name``."""
    tree = ast.parse(Path(server_mod.__file__).read_text())
    cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "WarmRuntime"
    )
    found = set()
    for fn in cls.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == name:
                found.add(fn.name)
    return found


def test_both_agent_builders_are_wired():
    """The anonymous and per-session builders each construct their own Agent."""
    callers = _methods_calling("_apply_cold_path_parity")
    assert "_get_agent" in callers, "the anonymous warm agent is still bare"
    assert "_get_session_agent" in callers, "the per-session warm agent is still bare"
