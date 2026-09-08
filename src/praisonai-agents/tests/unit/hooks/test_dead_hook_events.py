"""Regression tests for HookEvent members that were declared but never emitted.

Ten ``HookEvent`` members existed in ``hooks/types.py`` with zero production
emission sites. Registering a hook on any of them succeeded silently and then
never fired -- the worst possible failure mode for an observability API.

The most dangerous pair was ``BEFORE_MESSAGE`` / ``AFTER_MESSAGE``: the
plugin-facing *method* names ``before_message`` / ``after_message`` are live and
route to ``MESSAGE_RECEIVED`` / ``MESSAGE_SENDING`` (plugins/manager.py), while
the identically named *enum members* were dead. A developer reaching for the
obvious ``HookEvent.BEFORE_MESSAGE`` got silence.

These tests pin the resolution:
  * exact-duplicate names are enum aliases of the live event (registration works)
  * names with a real seam are emitted from that seam
  * names with no seam at all are gone, so the mistake fails loudly
"""

import pytest

from praisonaiagents.hooks.types import HookEvent, HookResult
from praisonaiagents.hooks.registry import (
    HookRegistry,
    add_hook,
    has_hook,
    get_default_registry,
    set_default_registry,
)


@pytest.fixture
def fresh_default_registry():
    """Swap in a clean default registry for tests that use global emission."""
    previous = get_default_registry()
    registry = HookRegistry()
    set_default_registry(registry)
    try:
        yield registry
    finally:
        set_default_registry(previous)


# ---------------------------------------------------------------------------
# Aliases: a plausible registration must reach the live event
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dead,live", [
    ("BEFORE_MESSAGE", "MESSAGE_RECEIVED"),
    ("AFTER_MESSAGE", "MESSAGE_SENDING"),
    ("TOOL_RESULT_PERSIST", "AFTER_TOOL"),
])
def test_alias_member_is_the_live_event(dead, live):
    """HookEvent.<dead> must BE the live member, not a separate dead slot."""
    assert getattr(HookEvent, dead) is getattr(HookEvent, live)


@pytest.mark.parametrize("dead,live", [
    ("BEFORE_MESSAGE", "MESSAGE_RECEIVED"),
    ("AFTER_MESSAGE", "MESSAGE_SENDING"),
    ("TOOL_RESULT_PERSIST", "AFTER_TOOL"),
])
def test_hook_registered_on_alias_is_found_for_live_event(dead, live):
    """Registering on the alias must be visible to the real emission site."""
    registry = HookRegistry()
    registry.register_function(
        event=getattr(HookEvent, dead), func=lambda data: HookResult.allow()
    )
    assert registry.has_hooks(getattr(HookEvent, live)), (
        f"a hook registered on HookEvent.{dead} is invisible to the "
        f"HookEvent.{live} emission site -- it would never fire"
    )


@pytest.mark.parametrize("dead_value,live", [
    ("before_message", "MESSAGE_RECEIVED"),
    ("after_message", "MESSAGE_SENDING"),
    ("tool_result_persist", "AFTER_TOOL"),
])
def test_legacy_string_event_name_resolves_to_live_event(dead_value, live, fresh_default_registry):
    """The string form (config files / add_hook) must resolve too."""
    assert HookEvent(dead_value) is getattr(HookEvent, live)
    add_hook(dead_value, lambda data: HookResult.allow())
    assert has_hook(getattr(HookEvent, live))


# ---------------------------------------------------------------------------
# ON_INIT / ON_SHUTDOWN: real emission point in the plugin manager
# ---------------------------------------------------------------------------

def _make_plugin():
    from praisonaiagents.plugins.plugin import Plugin, PluginInfo

    class _P(Plugin):
        @property
        def info(self):
            return PluginInfo(name="probe-plugin", version="9.9.9")

    return _P()


def test_on_init_fires_when_a_plugin_is_registered(fresh_default_registry):
    from praisonaiagents.plugins.manager import PluginManager

    seen = []
    fresh_default_registry.register_function(
        event=HookEvent.ON_INIT,
        func=lambda data: (seen.append(data), HookResult.allow())[1],
    )

    manager = PluginManager(disabled=False)
    assert manager.register(_make_plugin()) is True

    assert len(seen) == 1, "ON_INIT hook never fired on plugin registration"
    assert seen[0].plugin_name == "probe-plugin"
    assert seen[0].plugin_version == "9.9.9"
    assert seen[0].event_name == HookEvent.ON_INIT.value


def test_on_shutdown_fires_when_a_plugin_is_unregistered(fresh_default_registry):
    from praisonaiagents.plugins.manager import PluginManager

    manager = PluginManager(disabled=False)
    manager.register(_make_plugin())

    seen = []
    fresh_default_registry.register_function(
        event=HookEvent.ON_SHUTDOWN,
        func=lambda data: (seen.append(data), HookResult.allow())[1],
    )

    assert manager.unregister("probe-plugin") is True
    assert len(seen) == 1, "ON_SHUTDOWN hook never fired on plugin unregistration"
    assert seen[0].plugin_name == "probe-plugin"
    assert seen[0].event_name == HookEvent.ON_SHUTDOWN.value


# ---------------------------------------------------------------------------
# SUBAGENT_STOP: real emission point in the subagent tool
# ---------------------------------------------------------------------------

def _subagent_tool(factory):
    from praisonaiagents.tools.subagent_tool import create_subagent_tool

    return create_subagent_tool(agent_factory=factory)["function"]


def test_subagent_stop_fires_when_a_subagent_completes(fresh_default_registry):
    seen = []
    fresh_default_registry.register_function(
        event=HookEvent.SUBAGENT_STOP,
        func=lambda data: (seen.append(data), HookResult.allow())[1],
    )

    class _Agent:
        def __init__(self, **kw):
            pass

        def chat(self, prompt):
            return "done: " + prompt

    spawn = _subagent_tool(lambda **kw: _Agent())
    result = spawn(task="summarise the log", agent_name="helper")
    assert result["success"] is True

    assert len(seen) == 1, "SUBAGENT_STOP hook never fired when the subagent finished"
    assert seen[0].agent_name == "helper"
    assert seen[0].task == "summarise the log"
    assert seen[0].success is True
    assert seen[0].event_name == HookEvent.SUBAGENT_STOP.value


def test_subagent_stop_fires_when_a_subagent_fails(fresh_default_registry):
    seen = []
    fresh_default_registry.register_function(
        event=HookEvent.SUBAGENT_STOP,
        func=lambda data: (seen.append(data), HookResult.allow())[1],
    )

    class _Boom:
        def __init__(self, **kw):
            pass

        def chat(self, prompt):
            raise RuntimeError("subagent exploded")

    spawn = _subagent_tool(lambda **kw: _Boom())
    result = spawn(task="do a thing")
    assert result["success"] is False

    assert len(seen) == 1, "SUBAGENT_STOP hook never fired on subagent failure"
    assert seen[0].success is False
    assert "subagent exploded" in (seen[0].error or "")


def test_subagent_stop_fires_for_a_background_subagent(fresh_default_registry):
    seen = []
    fresh_default_registry.register_function(
        event=HookEvent.SUBAGENT_STOP,
        func=lambda data: (seen.append(data), HookResult.allow())[1],
    )

    class _Agent:
        def __init__(self, **kw):
            pass

        def chat(self, prompt):
            return "bg done"

    spawn = _subagent_tool(lambda **kw: _Agent())
    handle = spawn(task="background work", background=True)
    collect = spawn._subagent_result
    collect(handle["job_id"], wait=True)

    assert len(seen) == 1, "SUBAGENT_STOP never fired for a background subagent"
    assert seen[0].task == "background work"
    assert seen[0].success is True


# ---------------------------------------------------------------------------
# Deleted: no sensible emission point exists, so the mistake must fail loudly
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["USER_PROMPT_SUBMIT", "NOTIFICATION", "SETUP"])
def test_unemittable_events_are_gone_from_the_enum(name):
    assert not hasattr(HookEvent, name), (
        f"HookEvent.{name} is still declared but has no emission site; "
        "registering on it is silent"
    )


@pytest.mark.parametrize("value", ["user_prompt_submit", "notification", "setup"])
def test_unemittable_event_strings_raise(value):
    with pytest.raises(ValueError):
        HookEvent(value)
    with pytest.raises(ValueError):
        add_hook(value, lambda data: HookResult.allow())


# ---------------------------------------------------------------------------
# Ratchet: the enum must not silently regrow a dead member
# ---------------------------------------------------------------------------

# HookEvent members that are still declared with no emission site anywhere in
# the monorepo. They are OUT OF SCOPE for this change (scheduler + kanban
# lifecycle), listed so this ratchet fails the moment a *new* dead member is
# added or one of the nine fixed here regresses. Shrink this list, never grow it.
KNOWN_DEAD_OUT_OF_SCOPE = {
    "SCHEDULE_ADD",
    "SCHEDULE_REMOVE",
    "KANBAN_TASK_CREATED",
    "KANBAN_TASK_CLAIMED",
    "KANBAN_TASK_MOVED",
    "KANBAN_TASK_DONE",
    "KANBAN_TASK_BLOCKED",
    "KANBAN_TASK_FAILED",
}


def test_no_new_hook_event_is_declared_without_an_emission_site():
    """Every canonical HookEvent must be referenced by non-test product code."""
    import subprocess
    from pathlib import Path

    # tests/unit/hooks/<file> -> repo root
    root = Path(__file__).resolve().parents[5]

    def _refs(name):
        hits = []
        for prefix in ("HookEvent.", "PluginHook."):
            hits += subprocess.run(
                ["grep", "-rn", "--include=*.py", f"{prefix}{name}", str(root)],
                capture_output=True, text=True,
            ).stdout.splitlines()
        return [
            h for h in hits
            if "/tests/" not in h and "hooks/types.py" not in h
        ]

    # Control probe (must be non-zero): a known-live event.
    assert _refs("BEFORE_TOOL"), "control probe failed - the grep found nothing for a live event"
    # Control probe (must be zero): a name that does not exist.
    assert not _refs("DEFINITELY_NOT_AN_EVENT"), "control probe failed - grep matched a bogus name"

    dead = sorted(m.name for m in HookEvent if not _refs(m.name))
    unexpected = sorted(set(dead) - KNOWN_DEAD_OUT_OF_SCOPE)
    assert unexpected == [], (
        "HookEvent members declared with no emission site (registering on one "
        f"is silent): {unexpected}"
    )
