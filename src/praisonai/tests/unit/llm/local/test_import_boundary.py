"""praisonaiagents.local must import nothing but the standard library.

This is the property that makes the package adoptable by the 21 modules which
currently bypass the LLM layer. An AST pass over 595 files found 26 mutually
importing subpackage pairs; llm/ already imports upward into agent/, so a helper
placed there could not be called from memory/ or eval/ without deepening the
knot. A leaf can be called from anywhere.

Treat a failure here as a build break, not a style issue.
"""

import ast
import pathlib
import sys

import pytest

pytestmark = pytest.mark.unit

FORBIDDEN_DISTRIBUTIONS = {
    "litellm", "openai", "pydantic", "httpx", "requests", "aiohttp", "anyio",
    "rich", "yaml", "posthog", "numpy", "chromadb", "mem0",
}


def _local_dir() -> pathlib.Path:
    import praisonaiagents.local as pkg
    return pathlib.Path(pkg.__file__).parent


def _modules():
    return sorted(_local_dir().glob("*.py"))


def _import_roots(path):
    """(absolute_roots, max_relative_level) for one module, without importing it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots, max_level = set(), 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            max_level = max(max_level, node.level or 0)
            if not node.level and node.module:
                roots.add(node.module.split(".")[0])
    return roots, max_level


def test_only_stdlib_imports():
    for path in _modules():
        roots, _ = _import_roots(path)
        outside = {r for r in roots if r not in sys.stdlib_module_names}
        assert not outside, f"{path.name} imports non-stdlib: {sorted(outside)}"


def test_no_praisonaiagents_import():
    for path in _modules():
        roots, _ = _import_roots(path)
        assert "praisonaiagents" not in roots, (
            f"{path.name} imports praisonaiagents; local/ must stay a dependency sink"
        )


def test_no_parent_relative_imports():
    """`from .. import x` is the escape hatch that would break the sink."""
    for path in _modules():
        _, level = _import_roots(path)
        assert level <= 1, (
            f"{path.name} uses a level-{level} relative import; only single-dot "
            "sibling imports are allowed"
        )


def test_forbidden_distributions():
    for path in _modules():
        roots, _ = _import_roots(path)
        hits = roots & FORBIDDEN_DISTRIBUTIONS
        assert not hits, f"{path.name} imports {sorted(hits)}"


def test_loads_standalone_without_the_parent_package():
    """Load local/ by file path, proving it needs no praisonaiagents __init__."""
    import importlib.util
    d = _local_dir()
    before = set(sys.modules)
    spec = importlib.util.spec_from_file_location(
        "_local_boundary_probe", d / "__init__.py", submodule_search_locations=[str(d)])
    module = importlib.util.module_from_spec(spec)
    sys.modules["_local_boundary_probe"] = module
    try:
        spec.loader.exec_module(module)
        assert callable(module.resolve)
        added = set(sys.modules) - before
        leaked = {m.split(".")[0] for m in added} & FORBIDDEN_DISTRIBUTIONS
        assert not leaked, f"loading local/ pulled in {sorted(leaked)}"
    finally:
        for name in set(sys.modules) - before:
            sys.modules.pop(name, None)


def test_no_subprocess_anywhere():
    """The package returns data; it never runs anything."""
    for path in _modules():
        roots, _ = _import_roots(path)
        assert not roots & {"subprocess", "pty", "multiprocessing"}, (
            f"{path.name} imports a process-spawning module"
        )
        src = path.read_text()
        for banned in ("os.system(", "os.popen(", "os.execv", "os.spawn"):
            assert banned not in src, f"{path.name} calls {banned}"


def test_sloc_ceiling():
    """A prior extraction in this repo grew 55% past its pre-split size in five
    months. The budget is a test, not a guideline."""
    # Ceilings are set just above measured reality so growth is a decision, not
    # a drift. discover.py and quirktable.py are the two data-heavy modules --
    # the probe table and the quirk catalogue are mostly literals and prose --
    # which is why their ceilings are higher than their logic warrants.
    ceilings = {
        "__init__.py": 90, "errors.py": 80, "capabilities.py": 200,
        "quirktable.py": 200, "discover.py": 345, "target.py": 200,
        "resolve.py": 270,
    }
    total = 0
    for path in _modules():
        sloc = sum(
            1 for line in path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        total += sloc
        ceiling = ceilings.get(path.name)
        if ceiling:
            assert sloc <= ceiling, f"{path.name} is {sloc} SLOC, ceiling {ceiling}"
    assert total <= 1160, f"package is {total} SLOC, ceiling 1160"
