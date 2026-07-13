"""Tests for the automation-suggestion & blueprint chat helpers.

Covers the new /automations and /blueprint conversational surface that wires
the already-built consent-first SuggestionEngine + BlueprintCatalogue onto the
gateway. These run without any platform SDK by exercising the shared helpers in
``_automations`` directly.
"""

from praisonai_bot.bots import _automations
from praisonai_bot.bots._commands import CommandRegistry


def test_automations_and_blueprint_are_registered_builtins():
    reg = CommandRegistry()
    names = reg.get_command_names()
    assert "automations" in names
    assert "blueprint" in names
    assert reg.get_command("automations")["builtin"] is True
    assert reg.get_command("blueprint")["builtin"] is True


def test_callback_round_trip():
    assert _automations.accept_callback("sug_1") == "sug:accept:sug_1"
    assert _automations.dismiss_callback("sug_1") == "sug:dismiss:sug_1"


def test_parse_callback_valid():
    assert _automations.parse_callback("accept:sug_1") == ("accept", "sug_1")
    assert _automations.parse_callback("dismiss:sug_9") == ("dismiss", "sug_9")


def test_parse_callback_malformed():
    assert _automations.parse_callback("") == (None, None)
    assert _automations.parse_callback("accept") == (None, None)
    assert _automations.parse_callback("bogus:sug_1") == (None, None)
    assert _automations.parse_callback("accept:") == (None, None)


def test_parse_slot_args_coerces_ints():
    slots = _automations._parse_slot_args("hour=8 weekdays=mon-fri interval=30")
    assert slots == {"hour": 8, "weekdays": "mon-fri", "interval": 30}


def test_parse_slot_args_ignores_bad_tokens():
    slots = _automations._parse_slot_args("hour=8 garbage =bad key=")
    assert slots["hour"] == 8
    assert "garbage" not in slots


def test_format_automations_header():
    assert "no pending" in _automations.format_automations_header(0).lower()
    assert "1 pending automation suggestion:" in _automations.format_automations_header(1)
    assert "2 pending automation suggestions:" in _automations.format_automations_header(2)


class _FakeSuggestion:
    def __init__(self, sid, blueprint, slots, reason):
        self.id = sid
        self.blueprint_name = blueprint
        self.slots = slots
        self.reason = reason
        self.deliver = ""
        self.dismissed = False
        self.accepted = False
        self.expires_at = 0


class _FakeEngine:
    def __init__(self, pending):
        self._pending = pending
        self.dismissed = []

    def pending(self):
        return self._pending

    def dismiss(self, sug_id):
        self.dismissed.append(sug_id)
        return True

    def get_suggestion(self, sug_id):
        for s in self._pending:
            if s.id == sug_id:
                return s
        return None


def test_list_suggestions_renders_buttons(monkeypatch):
    fake = _FakeEngine([
        _FakeSuggestion("sug_1", "morning-brief", {"hour": 8}, "Daily pattern"),
    ])
    monkeypatch.setattr(_automations, "_engine", lambda: fake)

    items = _automations.list_suggestions()
    assert len(items) == 1
    item = items[0]
    assert item["id"] == "sug_1"
    assert "morning-brief" in item["text"]
    assert item["buttons"][0] == ("✓ Accept", "sug:accept:sug_1")
    assert item["buttons"][1] == ("✕ Dismiss", "sug:dismiss:sug_1")


def test_list_suggestions_empty_when_no_engine(monkeypatch):
    monkeypatch.setattr(_automations, "_engine", lambda: None)
    assert _automations.list_suggestions() == []


def test_dismiss_suggestion(monkeypatch):
    fake = _FakeEngine([_FakeSuggestion("sug_1", "morning-brief", {}, "r")])
    monkeypatch.setattr(_automations, "_engine", lambda: fake)
    result = _automations.dismiss_suggestion("sug_1")
    assert "sug_1" in fake.dismissed
    assert "Dismissed" in result


def test_accept_missing_suggestion(monkeypatch):
    fake = _FakeEngine([])
    monkeypatch.setattr(_automations, "_engine", lambda: fake)
    result = _automations.accept_suggestion("nope")
    assert "already been handled" in result or "not found" in result


def test_accept_unavailable_engine(monkeypatch):
    monkeypatch.setattr(_automations, "_engine", lambda: None)
    result = _automations.accept_suggestion("sug_1")
    assert "not available" in result


def test_create_from_blueprint_usage_when_empty():
    text = _automations.create_from_blueprint("")
    # Either usage help or unavailable message, but never a crash.
    assert isinstance(text, str) and text
