"""D-04: the package is typed for editors and type checkers (PEP 561).

There was no ``py.typed`` and the root exports came only from a module
``__getattr__``, so mypy reported "missing library stubs or py.typed marker"
and saw ``Agent``, ``Task`` and ``team.start()`` as ``Any``: no completion and
no typo detection (``expected_outptu=`` was not flagged).
"""

import ast
import os

import praisonaiagents

PKG = os.path.dirname(praisonaiagents.__file__)


def test_py_typed_marker_exists():
    assert os.path.isfile(os.path.join(PKG, "py.typed"))


def test_type_checking_block_covers_every_root_export():
    with open(os.path.join(PKG, "__init__.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    typed = set()
    for node in tree.body:
        if isinstance(node, ast.If) and getattr(node.test, "id", None) == "TYPE_CHECKING":
            for stmt in node.body:
                if isinstance(stmt, ast.ImportFrom):
                    typed.update(a.asname or a.name for a in stmt.names)
    module_level = {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    missing = set(praisonaiagents.__all__) - typed - module_level - {"__version__"}
    assert missing == set()
