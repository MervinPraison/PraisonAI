import asyncio
import json
import shlex
import sys

import pytest

from praisonaiagents.agent.agent import Agent
from praisonaiagents.compaction import ContextCompactor, CompactionResult
from praisonaiagents.config.feature_configs import ExecutionConfig
from praisonaiagents.context.adapters import ContextCompactionPolicyAdapter
from praisonaiagents.hooks.registry import HookRegistry
from praisonaiagents.hooks.types import HookEvent, HookInput, HookResult
from praisonaiagents.plugins.manager import PluginManager
from praisonaiagents.plugins.plugin import Plugin, PluginInfo, PluginHook


@pytest.mark.parametrize("kind", ["proactive", "in_run"])
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("strict", [False, True])
def test_after_compaction_command_and_function_hooks_receive_result(tmp_path, kind, asynchronous, strict):
    target = tmp_path / "payload.json"
    script = tmp_path / "record.py"
    script.write_text("import pathlib,sys\npathlib.Path(sys.argv[1]).write_text(sys.stdin.read())\n")
    registry = HookRegistry()
    registry.register_command(HookEvent.AFTER_COMPACTION, f"{shlex.quote(sys.executable)} {shlex.quote(str(script))} {shlex.quote(str(target))}")
    seen = []
    def observe(data):
        seen.append(data)
        return HookResult.allow()
    registry.register_function(HookEvent.AFTER_COMPACTION, observe)

    class Observer(Plugin):
        def __init__(self):
            self.payloads = []

        @property
        def info(self):
            return PluginInfo(name="compaction-observer", hooks=[PluginHook.AFTER_COMPACTION])

        def after_compaction(self, context):
            self.payloads.append(context)

    observer = Observer()
    manager = PluginManager()
    manager.register(observer)
    manager.wire_into_hook_registry(registry)
    agent = Agent(name="audit", instructions="test", model="gpt-4o", hooks=registry)
    agent._strict_hooks = strict
    agent.execution = ExecutionConfig(context_compaction=True, max_context_tokens=100)
    messages = [{"role": "user", "content": "word " * 1000}, {"role": "assistant", "content": "answer"}, {"role": "user", "content": "latest"}]
    if kind == "proactive":
        compactor, policy = ContextCompactor(max_tokens=100), ContextCompactionPolicyAdapter()
        if asynchronous:
            asyncio.run(agent._apply_compaction_async(messages, compactor, policy))
        else:
            agent._apply_compaction(messages, compactor, policy)
    elif asynchronous:
        assert asyncio.run(agent._apply_context_compaction_async(messages, HookEvent))
    else:
        assert agent._apply_context_compaction(messages, HookEvent)
    assert len(seen) == 1
    assert isinstance(seen[0], HookInput)
    assert isinstance(seen[0], CompactionResult)
    payload = json.loads(target.read_text())
    assert payload["event_name"] == "after_compaction"
    assert payload["cwd"]
    assert payload["original_tokens"] == seen[0].original_tokens
    assert payload["compacted_tokens"] == seen[0].compacted_tokens
    assert observer.payloads == [payload]


def test_no_after_hook_when_compaction_not_needed():
    registry = HookRegistry()
    seen = []
    registry.register_function(HookEvent.AFTER_COMPACTION, lambda data: seen.append(data))
    agent = Agent(name="audit", instructions="test", model="gpt-4o", hooks=registry)
    agent.execution = ExecutionConfig(context_compaction=True, max_context_tokens=10000)
    assert not agent._apply_context_compaction([{"role": "user", "content": "hi"}], HookEvent)
    assert seen == []


def test_no_after_hook_when_compaction_fails(monkeypatch):
    registry = HookRegistry()
    seen = []
    registry.register_function(HookEvent.AFTER_COMPACTION, lambda data: seen.append(data))
    agent = Agent(name="audit", instructions="test", model="gpt-4o", hooks=registry)
    agent.execution = ExecutionConfig(context_compaction=True, max_context_tokens=100)
    def fail(self, messages):
        raise RuntimeError("compaction failed")
    monkeypatch.setattr(ContextCompactor, "compact", fail)
    messages = [{"role": "user", "content": "word " * 1000}]
    assert not agent._apply_context_compaction(messages, HookEvent)
    assert seen == []
