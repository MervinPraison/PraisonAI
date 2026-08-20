"""The session module's documented quick start must actually run.

`session/__init__.py` and `session/README.md` documented
`Agent(name=..., session_id=...)`, which raises
``TypeError: Agent.__init__() got unexpected keyword argument(s): session_id``.
The working spelling puts session_id on the memory config.

The original guard *regexed the documentation text* for four hard-coded kwarg
names. That can only catch mistakes someone has already enumerated: changing
the fixed example from ``session_id=`` to ``sessionid=`` left the guard green
while the documented call raised (issue #4178). The primary guard here now
*executes* every self-contained example so the next mistake is caught too.
"""

import ast
import builtins as _builtins
import re
from pathlib import Path

import pytest

import praisonaiagents.session as session_pkg
from praisonaiagents import Agent, MemoryConfig

# ``Agent(`` ... ``session_id=`` with no *nested* call in between, so
# ``Agent(memory=MemoryConfig(session_id=...))`` is correctly not matched.
TOP_LEVEL_KWARG = r"Agent\((?:[^()]|\([^()]*\))*?\b{name}="

DOCS = (
    Path(session_pkg.__file__).parent / "__init__.py",
    Path(session_pkg.__file__).parent / "README.md",
)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    import praisonaiagents.session.store as store_module

    monkeypatch.setattr(store_module, "_default_store", None, raising=False)


# ---------------------------------------------------------------------------
# Executing guard: run the documented examples instead of matching their text.
#
# A doc example is a promise. Text matching can only catch mistakes we already
# made and enumerated; executing it catches the next one too.
# ---------------------------------------------------------------------------

_PY_FENCE = re.compile(r"^```(\w*)\s*$")

# ``<!-- praisonai: skip=true -->`` on the line(s) above a fence excludes a
# non-hermetic example (e.g. one that writes to an absolute path) from
# execution while keeping it visible in the docs. Mirrors the directive the
# suite_runner engine already honours, so the same marker works everywhere.
_SKIP_DIRECTIVE = re.compile(
    r"<!--\s*praisonai:[^>]*\bskip=(?:true|1|yes)\b[^>]*-->", re.IGNORECASE
)

# Backends under ``praisonaiagents.db`` need the optional ``praisonai`` wrapper
# for a live adapter. Examples that reach for one are skipped when the wrapper
# is absent rather than reported as a broken doc, mirroring the credential
# escape hatch (a missing optional dependency is not an API-shape mistake).
_WRAPPER_BACKED = re.compile(r"\bdb\s*\(|\bdb\.\w+\s*\(")

# Packages we ship. An ImportError naming one of these is a doc advertising a
# symbol we no longer export (or never did) — a regression to fail on — rather
# than a missing optional third-party dependency to skip.
_FIRST_PARTY = ("praisonaiagents", "praisonai")


def _is_first_party_import_error(exc):
    """True if *exc* came from importing one of our own packages.

    ``from praisonaiagents import Gone`` raises ``ImportError`` whose ``name``
    is the module (``praisonaiagents``); ``import praisonai.gone`` raises
    ``ModuleNotFoundError`` whose ``name`` is the dotted target. Both must fail
    the guard, so we match the top-level package of ``exc.name`` and fall back
    to scanning the message when ``name`` is unset (older tracebacks).
    """
    module = getattr(exc, "name", None)
    if module:
        return module.split(".")[0] in _FIRST_PARTY
    return any(pkg in str(exc) for pkg in _FIRST_PARTY)


def _python_blocks(text):
    """Yield the source of every ```python fenced block in *text*.

    A block preceded (within five lines) by a ``skip=true`` directive is
    omitted, so non-hermetic examples opt out explicitly rather than being
    silently excluded.
    """
    blocks = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        match = _PY_FENCE.match(lines[i])
        if match and match.group(1).lower() == "python":
            preamble = "\n".join(lines[max(0, i - 5):i])
            skipped = bool(_SKIP_DIRECTIVE.search(preamble))
            body = []
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                body.append(lines[j])
                j += 1
            if not skipped:
                blocks.append("\n".join(body))
            i = j + 1
        else:
            i += 1
    return blocks


# Names that legitimately appear free in an *excluded* block: symbols an API
# reference stub type-annotates against (``Optional``/``List`` etc.) and objects
# a documentation walkthrough binds in an earlier fence and reuses in a later
# continuation snippet (``Agent``/``MemoryConfig``). A free name outside this
# set means a *typo* in an otherwise-complete example — an omitted import or a
# misspelled identifier — which must surface as a failure rather than silently
# dropping the block from execution (greptile #4179).
_ALLOWED_FREE_NAMES = frozenset(
    {
        # typing / dataclass vocabulary used only in reference stubs
        "Optional", "List", "Dict", "Any", "dataclass",
        # doc-local classes referenced by the reference stubs
        "SessionData", "SessionMessage",
        # objects a prior fence binds and a continuation snippet reuses
        "Agent", "MemoryConfig", "store",
    }
)


def _free_names(code):
    """Names *code* reads that it neither binds nor inherits from builtins.

    Returns ``None`` for a block that does not parse. Uses ``ast`` rather than
    regex so snippet fragments (a bare ``Agent(...)`` with no import) and
    class-stub transcripts are identifiable by their leftover free names.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    bound = set()
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store):
                bound.add(node.id)
            else:
                used.add(node.id)

    return used - bound - set(dir(_builtins))


def _is_self_contained(code):
    """True if every name the block reads is bound within it or a builtin.

    Snippet fragments (a bare ``Agent(...)`` with no import) and class-stub
    transcripts drop out automatically: ``used - bound - builtins == set()``.
    """
    return _free_names(code) == set()


def _partition_python_blocks(*docs):
    """Split every non-empty python fence into (runnable, excluded).

    A block is runnable when it is self-contained; otherwise it is excluded and
    carried with the free names that excluded it, so a later test can prove the
    exclusion was a known documentation idiom and not a silent-dropped typo.
    """
    runnable, excluded = [], []
    for doc in docs:
        for index, code in enumerate(_python_blocks(doc.read_text())):
            if not code.strip():
                continue
            free = _free_names(code)
            if free == set():
                runnable.append((doc.name, index, code))
            elif free:  # None (syntax error) or non-empty free-name set
                excluded.append((doc.name, index, code, free))
    return runnable, excluded


_DOC_BLOCKS, _EXCLUDED_BLOCKS = _partition_python_blocks(*DOCS)


def _block_id(block):
    name, index, _ = block
    return f"{name}#{index}"


@pytest.mark.parametrize("block", _DOC_BLOCKS, ids=_block_id)
def test_documented_example_runs(block, monkeypatch):
    """Every self-contained session-doc example must execute without error.

    This is what #4127's guard should have done. Terminal actions that would
    hit the network (``Agent.start``/``chat``) are stubbed so the example is
    hermetic; blocks needing the optional ``praisonai`` wrapper are skipped.
    """
    _, _, code = block

    monkeypatch.setattr(Agent, "start", lambda self, *a, **k: "stub", raising=False)
    monkeypatch.setattr(Agent, "chat", lambda self, *a, **k: "stub", raising=False)

    if _WRAPPER_BACKED.search(code):
        pytest.importorskip(
            "praisonai",
            reason="example uses a db backend from the optional praisonai wrapper",
        )

    try:
        exec(compile(code, f"<{_block_id(block)}>", "exec"),
             {"__name__": "__doc_example__"})
    except ImportError as exc:
        # A missing *optional* dependency is an environment gap, not a broken
        # doc, so it skips. But an import that fails from our own packages
        # (``praisonaiagents``/``praisonai``) is a real API regression — a
        # renamed/removed symbol the doc still advertises — and must *fail*,
        # not hide behind the optional-dependency escape hatch (greptile #4179).
        if _is_first_party_import_error(exc):
            raise
        pytest.skip(f"optional dependency missing: {exc}")


@pytest.mark.parametrize(
    "block", _EXCLUDED_BLOCKS, ids=lambda b: f"{b[0]}#{b[1]}"
)
def test_excluded_block_is_a_known_idiom_not_a_typo(block):
    """A block dropped from execution must be dropped for a *known* reason.

    ``_is_self_contained`` filters snippet fragments and API-reference stubs so
    they are not exec'd. But the same filter would silently swallow an
    otherwise-complete example ruined by a typo (``Agnet(...)``) or an omitted
    import, leaving exactly that documentation mistake outside the guard
    (greptile #4179). Pinning every free name to ``_ALLOWED_FREE_NAMES`` turns
    such a mistake into a failure: the new free name is not a recognised
    documentation idiom, so this test — not silence — reports it.
    """
    name, index, _, free = block
    unexpected = free - _ALLOWED_FREE_NAMES
    assert not unexpected, (
        f"{name}#{index} was excluded from execution because of unexpected "
        f"free name(s) {sorted(unexpected)!r}. If this is a real example, fix "
        f"the typo/import so it runs; if it is a deliberate fragment, add the "
        f"name(s) to _ALLOWED_FREE_NAMES."
    )


# ---------------------------------------------------------------------------
# Behavioural contract: the kwargs the docs must never show really are rejected,
# and the spelling the fixed docs show constructs and restores history.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["session_id", "user_id", "db", "prompt_caching"])
def test_agent_rejects_those_kwargs(name):
    """The other half of the contract: they really are rejected."""
    with pytest.raises(TypeError, match=name):
        Agent(name="Assistant", **{name: "x"})


def test_documented_spellings_construct_and_restore():
    """The spelling the fixed docs show works, and restores history."""
    from praisonaiagents.session import get_default_session_store

    assert (
        Agent(name="A", memory={"session_id": "my-session-123"})
        ._memory_config.session_id
        == "my-session-123"
    )

    get_default_session_store().add_user_message(
        "my-session-123", "Hello, my name is Alice"
    )
    agent = Agent(name="Assistant", memory=MemoryConfig(session_id="my-session-123"))
    agent._init_session_store()

    assert agent.chat_history == [
        {"role": "user", "content": "Hello, my name is Alice"}
    ]


# ---------------------------------------------------------------------------
# #4161 example-file guards: the same broken spelling regressed in the db
# package docstrings and the redis example. These still read text because those
# roots ship reST docstrings and whole runnable files a ```python fence walk
# never reaches; see issue #4161 for wiring them through an executor too.
# ---------------------------------------------------------------------------

# Repo root, walked up from this test file
# (.../src/praisonai-agents/tests/unit/session/test_...py -> repo root).
_REPO_ROOT = Path(__file__).resolve().parents[5]

_EXAMPLE_ROOTS = (
    _REPO_ROOT / "src" / "praisonai" / "praisonai" / "db",
    _REPO_ROOT / "examples" / "persistence",
)

_FICTIONAL_IMPORTS = ("PostgresAdapter",)


def _example_files():
    """Collect every ``Agent(`` example under the known roots.

    A missing root is a *hard* error rather than an empty parametrization:
    if a root is renamed/moved the guard would otherwise silently stop
    examining those examples and let the very regression it exists to catch
    slip back in (issue #4161).
    """
    missing = [str(root) for root in _EXAMPLE_ROOTS if not root.exists()]
    if missing:
        raise RuntimeError(
            "Session-doc example root(s) not found: "
            + ", ".join(missing)
            + " — update _EXAMPLE_ROOTS so coverage is not silently lost."
        )
    files = []
    for root in _EXAMPLE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if "Agent(" in path.read_text():
                files.append(path)
    return files


_EXAMPLE_FILES = _example_files()


@pytest.mark.parametrize("path", _EXAMPLE_FILES, ids=lambda p: p.name)
@pytest.mark.parametrize("name", ["session_id", "db", "user_id"])
def test_example_files_do_not_pass_rejected_kwargs_to_agent(path, name):
    """Neither docstrings nor runnable examples may show a rejected kwarg.

    The textual session-doc guard only covered two files; the identical broken
    spelling shipped in the db package docstrings and the redis example too.
    """
    hit = re.search(TOP_LEVEL_KWARG.format(name=name), path.read_text())
    assert hit is None, f"{path.name} shows Agent({name}=...): {hit.group(0)!r}"


@pytest.mark.parametrize(
    "path", _EXAMPLE_FILES + list(DOCS), ids=lambda p: p.name
)
def test_examples_do_not_reference_nonexistent_classes(path):
    """A doc that imports a class we do not ship (e.g. ``PostgresAdapter``)."""
    text = path.read_text()
    for fictional in _FICTIONAL_IMPORTS:
        assert fictional not in text, f"{path.name} references {fictional!r}"
