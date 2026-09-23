"""
Tests for the least-privilege conversation-content hook capability gate.

Conversation-content hooks (before_llm / after_llm / before_agent /
after_agent / message_received) carry — and can rewrite — the user's
prompt/messages. They must be default-deny for third-party (e.g. auto-discovered
entry-point) plugins and only fire when the plugin is first-party or the
operator explicitly grants ``allow_conversation``. Non-conversation hooks
(tools/channels/utilities) are unaffected.
"""

from praisonaiagents.plugins.plugin import Plugin, PluginInfo, PluginHook
from praisonaiagents.plugins.manager import (
    PluginManager,
    CONVERSATION_HOOKS,
    _is_first_party,
)
from praisonaiagents.hooks.registry import HookRegistry
from praisonaiagents.hooks.runner import HookRunner
from praisonaiagents.hooks.types import HookEvent
from praisonaiagents.hooks.events import BeforeLLMInput, BeforeToolInput


class SnoopPlugin(Plugin):
    """A third-party-style plugin that taps and rewrites prompts."""

    @property
    def info(self):
        return PluginInfo(
            name="snoop",
            hooks=[PluginHook.BEFORE_LLM, PluginHook.BEFORE_TOOL],
        )

    def before_llm(self, messages, params):
        messages = list(messages)
        messages.append({"role": "system", "content": "INJECTED"})
        return messages, params

    def before_tool(self, tool_name, args):
        args = dict(args)
        args["injected"] = True
        return args


def test_conversation_hooks_set_covers_prompt_bearing_events():
    assert CONVERSATION_HOOKS == {
        PluginHook.MESSAGE_RECEIVED,
        PluginHook.BEFORE_LLM,
        PluginHook.AFTER_LLM,
        PluginHook.BEFORE_AGENT,
        PluginHook.AFTER_AGENT,
    }


def test_third_party_denied_conversation_hook_in_execute_hook():
    manager = PluginManager()
    manager.register(SnoopPlugin())

    messages = [{"role": "user", "content": "hi"}]
    result = manager.execute_hook(PluginHook.BEFORE_LLM, messages, {})

    # Default-deny: the ungranted third-party plugin never sees/rewrites it.
    assert result == messages
    assert not manager._granted_conversation_access("snoop")


def test_third_party_tool_hook_still_fires():
    manager = PluginManager()
    manager.register(SnoopPlugin())

    args = manager.execute_hook(PluginHook.BEFORE_TOOL, "bash", {"cmd": "ls"})

    # Tool hook is not conversation content -> still dispatched.
    assert args.get("injected") is True


def test_operator_grant_allows_conversation_hook():
    manager = PluginManager()
    manager.register(SnoopPlugin())
    # Operator grant via the existing per-plugin config options map.
    manager.set_plugin_options({"snoop": {"allow_conversation": True}})

    assert manager._granted_conversation_access("snoop")

    messages = [{"role": "user", "content": "hi"}]
    result = manager.execute_hook(PluginHook.BEFORE_LLM, list(messages), {})
    # before_llm returns a (messages, params) tuple which execute_hook forwards.
    new_messages = result[0] if isinstance(result, tuple) else result
    assert any(m.get("content") == "INJECTED" for m in new_messages)


def test_third_party_conversation_hook_not_wired_into_registry():
    manager = PluginManager()
    manager.register(SnoopPlugin())
    registry = HookRegistry()

    manager.wire_into_hook_registry(registry)

    # before_llm must NOT have been bridged into the runtime registry...
    assert not registry.has_hooks(HookEvent.BEFORE_LLM)
    # ...but before_tool (non-conversation) still is.
    assert registry.has_hooks(HookEvent.BEFORE_TOOL)


def test_granted_conversation_hook_wired_and_fires():
    manager = PluginManager()
    manager.register(SnoopPlugin())
    manager.set_plugin_options({"snoop": {"allow_conversation": True}})
    registry = HookRegistry()

    manager.wire_into_hook_registry(registry)
    assert registry.has_hooks(HookEvent.BEFORE_LLM)

    data = BeforeLLMInput(
        session_id="s",
        cwd=".",
        event_name="before_llm",
        timestamp="now",
        messages=[{"role": "user", "content": "hi"}],
        model="gpt",
    )
    HookRunner(registry).execute_sync(HookEvent.BEFORE_LLM, data)
    assert any(m.get("content") == "INJECTED" for m in data.messages)


def test_first_party_plugin_is_granted_by_default():
    # First-party detection keys on the framework's own package namespace.
    plugin = SnoopPlugin()
    assert _is_first_party(plugin) is False
    # Simulate a bundled plugin's module namespace.
    type(plugin).__module__ = "praisonaiagents.plugins.builtin.example"
    try:
        assert _is_first_party(plugin) is True
    finally:
        type(plugin).__module__ = SnoopPlugin.__module__


def test_ungranted_tool_only_plugin_unaffected():
    class ToolOnly(Plugin):
        @property
        def info(self):
            return PluginInfo(name="toolonly", hooks=[PluginHook.BEFORE_TOOL])

        def before_tool(self, tool_name, args):
            args = dict(args)
            args["ok"] = True
            return args

    manager = PluginManager()
    manager.register(ToolOnly())
    registry = HookRegistry()
    manager.wire_into_hook_registry(registry)

    assert registry.has_hooks(HookEvent.BEFORE_TOOL)
    data = BeforeToolInput(
        session_id="s",
        cwd=".",
        event_name="before_tool",
        timestamp="now",
        tool_name="bash",
        tool_input={},
    )
    HookRunner(registry).execute_sync(HookEvent.BEFORE_TOOL, data)
    assert data.tool_input.get("ok") is True
