"""D-01/D-02: ``@tool("name")`` names the tool, as ``@tool(name="name")`` does.

A positional string was treated as the function, so ``@tool("my_name")``
raised ``AttributeError: 'str' object has no attribute '__name__'``. The
built-in ``artifact_tools`` module uses that spelling, so it failed to import
and an agent with an artifact store never got its six artifact tools.
"""

import importlib
import sys

from praisonaiagents.tools.decorator import tool


def test_positional_string_is_the_name():
    @tool("lookup_city")
    def find(city: str) -> str:
        """Find a city."""
        return city

    assert find.name == "lookup_city"
    assert find("Paris") == "Paris"


def test_positional_name_with_other_options():
    @tool("echo_tool", description="Echo the input")
    def echo(text: str) -> str:
        return text

    assert (echo.name, echo.description) == ("echo_tool", "Echo the input")


def test_bare_and_keyword_forms_unchanged():
    @tool
    def plain(x: int) -> int:
        """Plain."""
        return x

    @tool(name="kw_name")
    def keyword(x: int) -> int:
        """Keyword."""
        return x

    assert (plain.name, keyword.name) == ("plain", "kw_name")


def test_artifact_tools_module_imports_with_six_tools():
    sys.modules.pop("praisonaiagents.tools.artifact_tools", None)
    mod = importlib.import_module("praisonaiagents.tools.artifact_tools")
    names = {"artifact_head", "artifact_tail", "artifact_grep", "artifact_chunk", "artifact_load", "artifact_list"}
    assert names <= {getattr(getattr(mod, n, None), "name", None) for n in names}


def test_agent_registers_the_artifact_tools(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    from praisonaiagents import Agent
    agent = Agent(name="a", instructions="x", llm="gpt-4o-mini", output="silent")
    agent._artifact_store = object()
    agent._register_artifact_tools()
    names = {getattr(t, "__name__", getattr(t, "name", None)) for t in agent.tools}
    assert {"artifact_head", "artifact_tail", "artifact_grep", "artifact_chunk",
            "artifact_load", "artifact_list"} <= names


def test_artifact_load_round_trips_and_stays_inside_the_store(tmp_path, monkeypatch):
    import pathlib
    from praisonaiagents.context.artifact_store import FileSystemArtifactStore
    from praisonaiagents.context.artifacts import ArtifactMetadata
    from praisonaiagents.tools import artifact_tools

    store = FileSystemArtifactStore(base_dir=str(tmp_path / "store"))
    ref = store.store({"k": 1}, ArtifactMetadata(agent_id="a", run_id="r"))
    artifact_tools.set_artifact_store(store)
    assert artifact_tools.artifact_load(ref.path) == {"k": 1}

    outside = tmp_path / "secret.json"
    outside.write_text('{"artifact_id": "leak"}')
    read = []
    real = pathlib.Path.read_text
    monkeypatch.setattr(pathlib.Path, "read_text", lambda self, *a, **k: read.append(self) or real(self, *a, **k))
    assert artifact_tools.artifact_load(str(outside)).startswith("Error")
    assert outside not in read
