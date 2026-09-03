"""The auxiliary-model fallback must be configurable everywhere, not just in some places.

Roughly a dozen sites resolved their small helper model as
`os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")`, and roughly twenty more
hardcoded `"gpt-4o-mini"` directly. Same value, same purpose -- but only half of
them could be pointed anywhere else.

That is the real obstacle to running fully locally. It is NOT the endpoint:
litellm and the openai SDK both honour OPENAI_BASE_URL from the environment
(verified), so the bypass call sites do reach a local server. They then ask it
for a model called "gpt-4o-mini", which no local server serves.
"""

import pytest

from praisonaiagents.llm.model_providers import (DEFAULT_AUXILIARY_MODEL,
                                                 default_auxiliary_model)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL_NAME", raising=False)
    monkeypatch.delenv("PRAISONAI_AUXILIARY_MODEL", raising=False)


def test_default_is_unchanged_when_nothing_is_set():
    assert default_auxiliary_model() == DEFAULT_AUXILIARY_MODEL == "gpt-4o-mini"


def test_openai_model_name_is_honoured(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_NAME", "ollama/llama3.2")
    assert default_auxiliary_model() == "ollama/llama3.2"


def test_dedicated_override_wins_over_the_general_one(monkeypatch):
    """A local setup often wants a *smaller* model for helper calls than for the
    agent itself, so the specific variable must beat the general one."""
    monkeypatch.setenv("OPENAI_MODEL_NAME", "ollama/llama3.3:70b")
    monkeypatch.setenv("PRAISONAI_AUXILIARY_MODEL", "ollama/qwen3:0.6b")
    assert default_auxiliary_model() == "ollama/qwen3:0.6b"


def test_explicit_argument_beats_every_environment_variable(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_NAME", "ollama/llama3.2")
    assert default_auxiliary_model("gpt-4o") == "gpt-4o"


def test_empty_environment_value_is_ignored(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_NAME", "   ")
    assert default_auxiliary_model() == DEFAULT_AUXILIARY_MODEL


def test_no_heavy_import(monkeypatch):
    """These call sites are on hot paths; resolving a model name must stay cheap."""
    import subprocess, sys, textwrap
    code = textwrap.dedent("""
        import sys
        from praisonaiagents.llm.model_providers import default_auxiliary_model
        default_auxiliary_model()
        bad = [m for m in sys.modules if m.split('.')[0] in ('litellm', 'chromadb')]
        print('HEAVY' if bad else 'CLEAN')
    """)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert "CLEAN" in out.stdout, out.stdout + out.stderr


# --- the call sites ------------------------------------------------------------

CALL_SITES = [
    ("memory/memory.py", 2),
    ("memory/learn/manager.py", 2),
    ("context/compressor.py", 2),
    ("context/optimizer.py", 1),
    ("workflows/workflows.py", 1),
    ("lite/__init__.py", 2),
    ("task/task.py", 1),
    ("session/title.py", 1),
]


@pytest.mark.parametrize("relative, expected", CALL_SITES)
def test_call_site_uses_the_helper(relative, expected):
    import pathlib
    import praisonaiagents
    path = pathlib.Path(praisonaiagents.__file__).parent / relative
    source = path.read_text()
    assert source.count("default_auxiliary_model") >= expected, (
        f"{relative} still hardcodes its auxiliary model fallback"
    )


def test_memory_quality_scoring_does_not_construct_a_bare_openai_client():
    """`OpenAI()` with no arguments ignores any configured endpoint.

    It happens to work today because the SDK reads OPENAI_BASE_URL itself, but it
    silently ignores a base_url passed through config, which is the shape the
    rest of the memory layer uses.
    """
    import pathlib
    import praisonaiagents
    source = (pathlib.Path(praisonaiagents.__file__).parent / "memory/memory.py").read_text()
    assert "client = OpenAI()" not in source
