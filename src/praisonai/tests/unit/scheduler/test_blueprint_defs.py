"""Tests for blueprint protocol definitions."""

import pytest
from praisonaiagents.scheduler.blueprint_defs import (
    Blueprint,
    BlueprintSlot,
    BlueprintStoreProtocol,
)


class TestBlueprintSlot:
    """Tests for BlueprintSlot dataclass."""

    def test_default_values(self):
        slot = BlueprintSlot(name="hour")
        assert slot.name == "hour"
        assert slot.type == "str"
        assert slot.label == ""
        assert slot.default is None
        assert slot.required is True
        assert slot.choices is None
        assert slot.description == ""

    def test_full_configuration(self):
        slot = BlueprintSlot(
            name="weekdays",
            type="choice",
            label="Days of week",
            default="mon-fri",
            required=True,
            choices=["mon-fri", "daily", "weekends"],
            description="Which days to run",
        )
        assert slot.name == "weekdays"
        assert slot.type == "choice"
        assert slot.label == "Days of week"
        assert slot.default == "mon-fri"
        assert slot.choices == ["mon-fri", "daily", "weekends"]
        assert slot.description == "Which days to run"

    def test_not_required(self):
        slot = BlueprintSlot(name="optional_field", required=False, default="fallback")
        assert slot.required is False
        assert slot.default == "fallback"

    def test_int_type_slot(self):
        slot = BlueprintSlot(name="interval", type="int", default=30)
        assert slot.type == "int"
        assert slot.default == 30


class TestBlueprint:
    """Tests for Blueprint dataclass."""

    def test_minimal_construction(self):
        bp = Blueprint(name="test-bp")
        assert bp.name == "test-bp"
        assert bp.version == "1.0.0"
        assert bp.description == ""
        assert bp.tags == []
        assert bp.category == "general"
        assert bp.slots == []
        assert bp.default_deliver == ""
        assert bp.default_agent == ""
        assert bp.prompt_template == ""
        assert bp.schedule_template == ""
        assert bp.builtin is True

    def test_full_construction(self):
        slots = [
            BlueprintSlot(name="hour", type="int", default=8),
            BlueprintSlot(name="focus", type="choice", choices=["tech", "business"]),
        ]
        bp = Blueprint(
            name="morning-brief",
            version="2.0.0",
            description="Daily morning briefing",
            tags=["daily", "news"],
            category="daily",
            slots=slots,
            default_deliver="telegram",
            default_agent="assistant",
            prompt_template="Provide a briefing about {focus}.",
            schedule_template="cron:{minute} {hour} * * {weekdays_expression}",
            builtin=True,
        )
        assert bp.name == "morning-brief"
        assert len(bp.slots) == 2
        assert bp.default_deliver == "telegram"
        assert bp.prompt_template == "Provide a briefing about {focus}."
        assert "{weekdays_expression}" in bp.schedule_template

    def test_custom_not_builtin(self):
        bp = Blueprint(name="custom-bp", builtin=False)
        assert bp.builtin is False


class TestBlueprintStoreProtocol:
    """Tests for BlueprintStoreProtocol."""

    def test_matching_class_is_detected(self):
        """A class with the right methods satisfies the protocol."""
        class MyStore:
            def list_blueprints(self, category=None):
                return []

            def get_blueprint(self, name):
                return None

            def register_blueprint(self, bp):
                pass

        store = MyStore()
        assert isinstance(store, BlueprintStoreProtocol)

    def test_missing_method_does_not_match(self):
        """A class missing a method does NOT satisfy the protocol."""
        class BadStore:
            def list_blueprints(self):
                return []

        store = BadStore()
        assert not isinstance(store, BlueprintStoreProtocol)
