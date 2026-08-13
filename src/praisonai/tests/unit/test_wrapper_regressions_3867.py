"""Regression coverage for wrapper issues reported in #3867."""

import builtins

import pytest


class _AsyncConversationStore:
    def __init__(self):
        self.sessions = {}
        self.messages = {}

    async def get_session(self, session_id):
        return self.sessions.get(session_id)

    async def create_session(self, session):
        self.sessions[session.session_id] = session

    async def get_messages(self, session_id):
        return list(self.messages.get(session_id, []))

    async def add_message(self, session_id, message):
        self.messages.setdefault(session_id, []).append(message)

    async def update_session(self, session):
        self.sessions[session.session_id] = session


class _AsyncStateStore:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value):
        self.values[key] = value


def _db_with_async_stores():
    from praisonai.db.adapter import PraisonAIDB

    db = PraisonAIDB()
    db._initialized = True
    db._conversation_store = _AsyncConversationStore()
    db._state_store = _AsyncStateStore()
    db._init_stores = lambda: None
    return db


def test_sync_conversation_hooks_complete_async_store_calls():
    db = _db_with_async_stores()

    assert db.on_agent_start("agent", "session") == []
    db.on_user_message("session", "hello")
    db.on_agent_message("session", "hi")
    db.on_tool_call("session", "lookup", {"q": "x"}, "result")
    db.on_agent_end("session")

    assert [m.role for m in db._conversation_store.messages["session"]] == [
        "user",
        "assistant",
        "tool",
    ]
    assert "ended_at" in db._conversation_store.sessions["session"].metadata

    imported = db.import_session(
        {
            "session_id": "imported",
            "messages": [{"role": "user", "content": "restored"}],
        }
    )
    assert imported == "imported"
    assert db._conversation_store.messages["imported"][0].content == "restored"


def test_sync_run_and_trace_hooks_complete_async_store_calls():
    db = _db_with_async_stores()

    db.on_run_start("session", "run")
    db.on_run_end("session", "run", status="failed")
    db.on_trace_start("trace", session_id="session")
    db.on_trace_end("trace", status="error")
    db.on_span_start("span", "trace", "work")
    db.on_span_end("span", status="error")

    values = db._state_store.values
    assert values["run:session:run"]["status"] == "failed"
    assert values["trace:trace"]["status"] == "error"
    assert values["span:span"]["status"] == "error"


def test_profile_detailed_records_without_losing_return_value():
    from praisonai.profiler import Profiler, get_profiler, profile_detailed

    Profiler.clear()
    Profiler.enable()

    @profile_detailed
    def increment(value):
        return value + 1

    try:
        assert increment(41) == 42
        records = list(get_profiler()._cprofile_stats)
        assert records[-1]["name"] == "increment"
        assert "function calls" in records[-1]["stats"]
    finally:
        Profiler.disable()
        Profiler.clear()


def test_import_profiler_survives_overlapping_out_of_order_scopes():
    from praisonai.profiler import ImportProfiler

    original = builtins.__import__
    first = ImportProfiler()
    second = ImportProfiler()
    first_entered = second_entered = False

    try:
        first.__enter__()
        first_entered = True
        shared_hook = builtins.__import__
        second.__enter__()
        second_entered = True

        assert builtins.__import__ is shared_hook
        first.__exit__(None, None, None)
        first_entered = False
        assert builtins.__import__ is shared_hook
        second.__exit__(None, None, None)
        second_entered = False
        assert builtins.__import__ is original
    finally:
        if first_entered:
            first.__exit__(None, None, None)
        if second_entered:
            second.__exit__(None, None, None)
        builtins.__import__ = original


@pytest.mark.parametrize(
    "cli_config, capability, message",
    [
        ({"resume_session": "session"}, "SUPPORTS_SESSION_CONTINUITY", "--resume"),
        ({"auto_save": "session"}, "SUPPORTS_SESSION_CONTINUITY", "--session"),
        ({"output": "stream-json"}, "SUPPORTS_STREAM_BRIDGE", "stream-json"),
    ],
)
def test_adapter_capability_gate_rejects_unsupported_cli_modes(
    cli_config, capability, message
):
    from praisonai.agents_generator import AgentsGenerator

    adapter = type(
        "ExternalAdapter",
        (),
        {"name": "external", capability: False},
    )()
    generator = object.__new__(AgentsGenerator)
    generator.cli_config = cli_config

    with pytest.raises(ValueError, match=message):
        generator._validate_adapter_cli_capabilities(adapter)


@pytest.mark.parametrize(
    "cli_config, message",
    [
        ({"resume_session": "session"}, "--resume"),
        ({"auto_save": "session"}, "workflow YAMLs"),
        ({"output": "stream-json"}, "stream-json"),
    ],
)
def test_workflow_path_rejects_unsupported_cli_modes(cli_config, message):
    from praisonai.agents_generator import AgentsGenerator

    generator = object.__new__(AgentsGenerator)
    generator.cli_config = cli_config

    with pytest.raises(ValueError, match=message):
        generator._validate_workflow_cli_capabilities()


def test_workflow_path_allows_supported_cli_modes():
    from praisonai.agents_generator import AgentsGenerator

    generator = object.__new__(AgentsGenerator)
    generator.cli_config = {"output": "json"}

    generator._validate_workflow_cli_capabilities()


def test_import_profiler_records_default_once_across_overlapping_scopes():
    import time

    from praisonai import profiler as profiler_module
    from praisonai.profiler import ImportProfiler, Profiler, get_profiler

    Profiler.clear()
    Profiler.enable()

    original = builtins.__import__
    first = ImportProfiler()
    second = ImportProfiler()
    try:
        first.__enter__()
        second.__enter__()

        def _slow_original(name, *args, **kwargs):
            time.sleep(0.005)
            return original(name, *args, **kwargs)

        profiler_module._IMPORT_HOOK_ORIGINAL = _slow_original
        builtins.__import__("json")

        first.__exit__(None, None, None)
        second.__exit__(None, None, None)

        default_json = [
            record for record in get_profiler()._imports if record.module == "json"
        ]
        first_json = [r for r in first._imports if r.module == "json"]
        second_json = [r for r in second._imports if r.module == "json"]

        assert len(default_json) == 1
        assert len(first_json) == 1
        assert len(second_json) == 1
    finally:
        second.__exit__(None, None, None)
        first.__exit__(None, None, None)
        builtins.__import__ = original
        Profiler.disable()
        Profiler.clear()


def test_native_adapter_declares_cli_runtime_capabilities():
    from praisonai.framework_adapters.base import BaseFrameworkAdapter
    from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter

    assert BaseFrameworkAdapter.SUPPORTS_SESSION_CONTINUITY is False
    assert BaseFrameworkAdapter.SUPPORTS_STREAM_BRIDGE is False
    assert PraisonAIAdapter.SUPPORTS_SESSION_CONTINUITY is True
    assert PraisonAIAdapter.SUPPORTS_STREAM_BRIDGE is True
