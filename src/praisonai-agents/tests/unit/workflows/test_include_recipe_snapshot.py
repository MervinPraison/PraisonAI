"""Included recipes must cache the exact text accepted by their parser."""

import builtins
from pathlib import Path
import sys

import pytest

from praisonaiagents.workflows.workflows import AgentFlow, Include, Parallel
from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser


def _definition(action):
    return f"name: recipe\nsteps:\n  - name: leaf\n    action: {action}\n"


def _local_parser(monkeypatch, calls, after_parse=None):
    original = YAMLWorkflowParser.parse_string

    def parse_string(parser, text, *args, **kwargs):
        flow = original(parser, text, *args, **kwargs)
        action = flow.steps[0].action
        flow.steps[0].handler = lambda ctx: calls.append(action) or action
        if after_parse:
            after_parse()
        return flow

    monkeypatch.setattr(YAMLWorkflowParser, "parse_string", parse_string)
    monkeypatch.setitem(sys.modules, "agent_recipes", None)


def test_recipe_change_after_parse_cannot_poison_new_definition_cache(tmp_path, monkeypatch):
    definition = tmp_path / "workflow.yaml"
    definition.write_text(_definition("old"), encoding="utf-8")
    calls = []
    edited = []

    def edit_once():
        if not edited:
            definition.write_text(_definition("new"), encoding="utf-8")
            edited.append(True)

    _local_parser(monkeypatch, calls, edit_once)
    flow = AgentFlow(steps=[Parallel(steps=[Include(recipe=str(tmp_path))])], cache=True)
    assert flow.run("same", verbose=False)["output"] == "old"
    assert flow.run("same", verbose=False)["output"] == "new"
    assert flow.run("same", verbose=False)["output"] == "new"
    assert calls == ["old", "new"]


@pytest.mark.parametrize("cache", [False, True])
def test_include_preserves_parser_default_codec_with_cache(tmp_path, monkeypatch, cache):
    definition = tmp_path / "workflow.yaml"
    definition.write_bytes(_definition("café").encode("cp1252"))
    calls = []
    original_open = builtins.open

    def local_open(file, mode="r", *args, **kwargs):
        if Path(file) == definition and mode == "r" and not kwargs.get("encoding"):
            kwargs["encoding"] = "cp1252"
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", local_open)
    _local_parser(monkeypatch, calls)
    flow = AgentFlow(steps=[Parallel(steps=[Include(recipe=str(tmp_path))])], cache=cache)
    assert flow.run("same", verbose=False)["output"] == "café"
    assert flow.run("same", verbose=False)["output"] == "café"
    assert calls == (["café"] if cache else ["café", "café"])


def test_tool_edit_invalidates_include_cache_without_yaml_edit(tmp_path, monkeypatch):
    import os

    definition = tmp_path / "workflow.yaml"
    definition.write_text(_definition("produce"), encoding="utf-8")
    tools = tmp_path / "tools.py"
    tools.write_text("def produce(ctx):\n    return \"old\"\n", encoding="utf-8")
    before = tools.stat()
    original = YAMLWorkflowParser.parse_string
    calls = []

    def parse_string(parser, text, *args, **kwargs):
        flow = original(parser, text, *args, **kwargs)
        tool = parser.tool_registry["produce"]
        flow.steps[0].handler = lambda ctx: calls.append(tool(ctx)) or calls[-1]
        return flow

    monkeypatch.setattr(YAMLWorkflowParser, "parse_string", parse_string)
    monkeypatch.setitem(sys.modules, "agent_recipes", None)
    monkeypatch.setenv("PRAISONAI_ALLOW_LOCAL_TOOLS", "true")
    flow = AgentFlow(steps=[Parallel(steps=[Include(recipe=str(tmp_path))])], cache=True)
    assert flow.run("same", verbose=False)["output"] == "old"
    tools.write_text("def produce(ctx):\n    return \"new\"\n", encoding="utf-8")
    os.utime(tools, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert flow.run("same", verbose=False)["output"] == "new"
    assert flow.run("same", verbose=False)["output"] == "new"
    assert calls == ["old", "new"]
