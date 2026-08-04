"""
AST lint guard preventing AgentTeam API drift (invalid ``verbose=`` kwarg).

``AgentTeam.__init__`` does not accept ``verbose``; verbosity is controlled via
the consolidated ``output`` parameter (e.g. ``output="silent"`` /
``output="verbose"``). This test AST-parses example and internal-CLI source and
fails if any ``AgentTeam(...)`` call passes a keyword not present in the real
constructor signature, so broken copy-paste snippets can't be reintroduced.

The valid kwarg set is read from the ``AgentTeam.__init__`` source via AST
(not ``inspect.signature``) because ``AgentTeam`` subclasses ``typing.Protocol``,
which makes ``inspect`` report a generic ``(*args, **kwargs)`` signature.
"""
import ast
from pathlib import Path

# Repo root: .../src/praisonai-agents/tests/unit/agents/<this file>
_REPO_ROOT = Path(__file__).resolve().parents[5]
_AGENTS_SRC = (
    _REPO_ROOT
    / "src"
    / "praisonai-agents"
    / "praisonaiagents"
    / "agents"
    / "agents.py"
)

# Directories whose ``AgentTeam(...)`` calls must use valid kwargs only.
#
# Scope note: we intentionally guard copy-paste / shipped surfaces (public
# ``examples/`` and internal CLI code) plus the specific test files migrated by
# this change, rather than the whole ``src/praisonai-agents/tests`` tree. That
# tree contains dozens of legacy ad-hoc example scripts using the removed
# ``verbose=``/``max_iter=`` kwargs; sweeping them all in here would conflate an
# unrelated cleanup with this regression guard. Individual migrated test files
# are listed in ``_SCAN_FILES`` so the calls this PR fixed stay protected.
_SCAN_DIRS = [
    _REPO_ROOT / "examples",
    _REPO_ROOT / "src" / "praisonai" / "praisonai",
    _REPO_ROOT / "src" / "praisonai-code" / "praisonai_code",
]

# Individual files (outside the scanned dirs) whose ``AgentTeam(...)`` calls were
# migrated by this change and must not regress.
_SCAN_FILES = [
    _REPO_ROOT / "src" / "praisonai-agents" / "tests" / "crewai-tools-example.py",
]


def _valid_agentteam_kwargs():
    """Extract real ``AgentTeam.__init__`` parameter names by parsing source."""
    tree = ast.parse(_AGENTS_SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AgentTeam":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    args = item.args
                    names = {a.arg for a in args.args}
                    names.update(a.arg for a in args.kwonlyargs)
                    has_var_keyword = args.kwarg is not None
                    names.discard("self")
                    return names, has_var_keyword
    raise AssertionError("AgentTeam.__init__ not found in agents.py")


def _is_agentteam_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "AgentTeam"
    if isinstance(func, ast.Attribute):
        return func.attr == "AgentTeam"
    return False


def _iter_python_files():
    for base in _SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            yield path
    for path in _SCAN_FILES:
        if path.exists():
            yield path


def _find_bad_kwargs(path: Path, valid_kwargs):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_agentteam_call(node):
            for kw in node.keywords:
                if kw.arg is None:
                    continue  # **kwargs spread — can't statically validate
                if kw.arg not in valid_kwargs:
                    bad.append((kw.arg, node.lineno))
    return bad


def test_real_agentteam_init_has_no_verbose_or_var_keyword():
    valid_kwargs, has_var_keyword = _valid_agentteam_kwargs()
    assert "verbose" not in valid_kwargs
    assert "output" in valid_kwargs
    assert not has_var_keyword, (
        "AgentTeam.__init__ gained **kwargs; the lint guard below would be "
        "silently bypassed. Update this test if that change is intentional."
    )


def test_no_invalid_agentteam_kwargs_in_examples_and_cli():
    valid_kwargs, _ = _valid_agentteam_kwargs()

    failures = []
    for path in _iter_python_files():
        for arg, lineno in _find_bad_kwargs(path, valid_kwargs):
            rel = path.relative_to(_REPO_ROOT)
            failures.append(f"{rel}:{lineno} — invalid AgentTeam kwarg '{arg}'")

    assert not failures, (
        "AgentTeam called with invalid kwargs (use output='silent'/'verbose' "
        "instead of verbose=):\n" + "\n".join(sorted(failures))
    )
