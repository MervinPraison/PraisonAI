"""Every annotation on Agent.__init__ resolves once the module's TYPE_CHECKING
imports are in scope, so type checkers and IDEs see real types, not unknown names.

Seven string annotations (run_on, tools_run_on, runtime, tool_search,
message_steering, sandbox) named classes the module never imported.
"""
import ast
import typing
from pathlib import Path

import praisonaiagents.agent.agent as agent_mod


def _type_checking_names():
    tree = ast.parse(Path(agent_mod.__file__).read_text(encoding="utf-8"))
    block = next(n for n in tree.body if isinstance(n, ast.If)
                 and isinstance(n.test, ast.Name) and n.test.id == "TYPE_CHECKING")
    ns = {}
    code = compile(ast.Module(body=block.body, type_ignores=[]), agent_mod.__file__, "exec")
    exec(code, {"__name__": agent_mod.__name__, "__package__": agent_mod.__package__}, ns)
    return ns


def test_agent_init_annotations_resolve():
    hints = typing.get_type_hints(
        agent_mod.Agent.__init__, globalns={**vars(agent_mod), **_type_checking_names()}
    )
    assert "runtime" in hints and "sandbox" in hints
