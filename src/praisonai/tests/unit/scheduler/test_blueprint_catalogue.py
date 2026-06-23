"""Tests for BlueprintCatalogue."""

import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from praisonai.scheduler.blueprint_catalogue import (
    BlueprintCatalogue,
    BUILTIN_BLUEPRINTS,
)
from praisonaiagents.scheduler.blueprint_defs import Blueprint, BlueprintSlot


class TestBuiltinBlueprints:
    """Verify the three built-in blueprints exist and have expected shape."""

    def test_morning_brief_exists(self):
        bp = BUILTIN_BLUEPRINTS["morning-brief"]
        assert bp.name == "morning-brief"
        assert bp.category == "daily"
        assert bp.default_deliver == "telegram"
        slot_names = {s.name for s in bp.slots}
        assert slot_names == {"hour", "minute", "weekdays", "focus"}
        assert "{focus}" in bp.prompt_template
        assert "{weekdays_expression}" in bp.schedule_template

    def test_important_mail_exists(self):
        bp = BUILTIN_BLUEPRINTS["important-mail"]
        assert bp.name == "important-mail"
        assert bp.category == "monitoring"
        slot_names = {s.name for s in bp.slots}
        assert slot_names == {"interval_minutes", "keywords"}
        assert "*/{interval_minutes}m" in bp.schedule_template

    def test_weekly_review_exists(self):
        bp = BUILTIN_BLUEPRINTS["weekly-review"]
        assert bp.name == "weekly-review"
        assert bp.category == "weekly"
        slot_names = {s.name for s in bp.slots}
        assert "focus" in slot_names
        assert "weekdays" in slot_names


class TestGetBlueprint:
    """Tests for get_blueprint()."""

    def test_get_known_blueprint(self):
        catalogue = BlueprintCatalogue()
        bp = catalogue.get_blueprint("morning-brief")
        assert bp is not None
        assert bp.name == "morning-brief"

    def test_get_unknown_blueprint(self):
        catalogue = BlueprintCatalogue()
        bp = catalogue.get_blueprint("nonexistent")
        assert bp is None


class TestListBlueprints:
    """Tests for list_blueprints()."""

    def test_list_all(self):
        catalogue = BlueprintCatalogue()
        blueprints = catalogue.list_blueprints()
        assert len(blueprints) >= 3
        names = {bp.name for bp in blueprints}
        assert "morning-brief" in names
        assert "important-mail" in names
        assert "weekly-review" in names

    def test_list_by_category(self):
        catalogue = BlueprintCatalogue()
        daily = catalogue.list_blueprints(category="daily")
        assert len(daily) >= 1
        assert all(bp.category == "daily" for bp in daily)

    def test_list_by_unknown_category(self):
        catalogue = BlueprintCatalogue()
        empty = catalogue.list_blueprints(category="nonexistent")
        assert empty == []


class TestRegisterBlueprint:
    """Tests for register_blueprint()."""

    def test_register_new_blueprint(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(name="test-new", description="A test blueprint")
        catalogue.register_blueprint(bp)
        retrieved = catalogue.get_blueprint("test-new")
        assert retrieved is not None
        assert retrieved.description == "A test blueprint"

    def test_register_overrides_builtin(self):
        catalogue = BlueprintCatalogue()
        custom = Blueprint(
            name="morning-brief",
            description="Custom override",
            builtin=False,
        )
        catalogue.register_blueprint(custom)
        bp = catalogue.get_blueprint("morning-brief")
        assert bp is not None
        assert bp.description == "Custom override"


class TestResolveSlots:
    """Tests for resolve_slots()."""

    def test_default_filling(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            slots=[BlueprintSlot(name="x", type="int", default=42)],
        )
        resolved = catalogue.resolve_slots(bp, {})
        assert resolved["x"] == 42

    def test_user_overrides_default(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            slots=[BlueprintSlot(name="x", type="int", default=42)],
        )
        resolved = catalogue.resolve_slots(bp, {"x": 99})
        assert resolved["x"] == 99

    def test_missing_required_raises(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            slots=[BlueprintSlot(name="x", type="str", required=True)],
        )
        with pytest.raises(ValueError, match="Required slot 'x' is missing"):
            catalogue.resolve_slots(bp, {})

    def test_choice_validation(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            slots=[BlueprintSlot(name="color", type="choice",
                                 choices=["red", "blue"], default="red")],
        )
        resolved = catalogue.resolve_slots(bp, {"color": "blue"})
        assert resolved["color"] == "blue"

    def test_choice_validation_rejects_invalid(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            slots=[BlueprintSlot(name="color", type="choice",
                                 choices=["red", "blue"])],
        )
        with pytest.raises(ValueError, match="not in allowed choices"):
            catalogue.resolve_slots(bp, {"color": "green"})

    def test_multiple_slots(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            slots=[
                BlueprintSlot(name="a", type="int", default=1),
                BlueprintSlot(name="b", type="str", default="hello"),
            ],
        )
        resolved = catalogue.resolve_slots(bp, {"a": 10})
        assert resolved["a"] == 10
        assert resolved["b"] == "hello"


class TestMaterializePrompt:
    """Tests for materialize_prompt()."""

    def test_simple_substitution(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            prompt_template="Focus on {topic} today.",
        )
        result = catalogue.materialize_prompt(bp, {"topic": "security"})
        assert result == "Focus on security today."

    def test_multiple_substitutions(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            prompt_template="{greeting}! Today's focus: {topic}.",
        )
        result = catalogue.materialize_prompt(
            bp, {"greeting": "Hello", "topic": "tech"}
        )
        assert result == "Hello! Today's focus: tech."

    def test_missing_key_raises_keyerror(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            prompt_template="Hi {name}.",
        )
        with pytest.raises(KeyError):
            catalogue.materialize_prompt(bp, {})


class TestMaterializeSchedule:
    """Tests for materialize_schedule()."""

    def test_cron_with_weekdays(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            schedule_template="cron:{minute} {hour} * * {weekdays_expression}",
        )
        result = catalogue.materialize_schedule(
            bp, {"minute": 0, "hour": 8, "weekdays": "mon-fri"}
        )
        assert result == "cron:0 8 * * 1-5"

    def test_weekend_cron(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            schedule_template="cron:{minute} {hour} * * {weekdays_expression}",
        )
        result = catalogue.materialize_schedule(
            bp, {"minute": 30, "hour": 9, "weekdays": "weekends"}
        )
        assert result == "cron:30 9 * * 0,6"

    def test_interval_based(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            schedule_template="*/{interval_minutes}m",
        )
        result = catalogue.materialize_schedule(
            bp, {"interval_minutes": 15}
        )
        assert result == "*/15m"

    def test_no_weekdays_placeholder_plain_format(self):
        catalogue = BlueprintCatalogue()
        bp = Blueprint(
            name="test",
            schedule_template="daily",
        )
        result = catalogue.materialize_schedule(bp, {})
        assert result == "daily"


class TestWeekdaysToCron:
    """Tests for _weekdays_to_cron()."""

    @pytest.mark.parametrize("friendly,expected", [
        ("mon-fri", "1-5"),
        ("daily", "*"),
        ("weekends", "0,6"),
        ("mon", "1"),
        ("tue", "2"),
        ("wed", "3"),
        ("thu", "4"),
        ("fri", "5"),
        ("sat", "6"),
        ("sun", "0"),
        ("MON-FRI", "1-5"),
    ])
    def test_all_mappings(self, friendly, expected):
        result = BlueprintCatalogue._weekdays_to_cron(friendly)
        assert result == expected


class TestYamlBlueprintLoading:
    """Tests for loading blueprints from YAML files on disk."""

    def test_load_from_yaml_directory(self):
        catalogue = BlueprintCatalogue()
        bp = catalogue.get_blueprint("morning-brief")

        # Build a YAML file from the builtin blueprint's data
        yaml_content = textwrap.dedent("""\
        name: morning-brief
        version: "2.0.0"
        description: Custom morning briefing
        category: daily
        tags: [daily, custom]
        default_deliver: origin
        prompt_template: "Custom: {focus}"
        schedule_template: "cron:0 {hour} * * {weekdays_expression}"
        slots:
          - name: hour
            type: int
            default: 9
          - name: minute
            type: int
            default: 30
          - name: weekdays
            type: choice
            default: daily
            choices: [mon-fri, daily, weekends]
          - name: focus
            type: choice
            default: tech
            choices: [general, tech, business, science, custom]
        """)

        with tempfile.TemporaryDirectory() as tmpdir:
            bp_dir = Path(tmpdir) / "morning-brief"
            bp_dir.mkdir()
            (bp_dir / "blueprint.yaml").write_text(yaml_content)

            cat = BlueprintCatalogue(custom_dirs=[tmpdir])
            bp = cat.get_blueprint("morning-brief")
            assert bp is not None
            assert bp.version == "2.0.0"
            assert bp.description == "Custom morning briefing"
            assert bp.default_deliver == "origin"
            assert bp.builtin is False

            # Resolve slots against the loaded blueprint
            resolved = cat.resolve_slots(bp, {"focus": "business"})
            assert resolved["hour"] == 9
            assert resolved["minute"] == 30
            assert resolved["weekdays"] == "daily"
            assert resolved["focus"] == "business"

            prompt = cat.materialize_prompt(bp, resolved)
            assert "business" in prompt

            schedule = cat.materialize_schedule(bp, resolved)
            assert schedule == "cron:0 9 * * *"

    def test_load_does_not_crash_on_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cat = BlueprintCatalogue(custom_dirs=[tmpdir])
            # Should still have builtins
            assert cat.get_blueprint("morning-brief") is not None

    def test_load_does_not_crash_on_missing_dir(self):
        cat = BlueprintCatalogue(custom_dirs=["/nonexistent/path/xyz"])
        assert cat.get_blueprint("morning-brief") is not None


class TestBlueprintCatalogueInit:
    """Tests for BlueprintCatalogue constructor and basic init."""

    def test_default_constructor(self):
        cat = BlueprintCatalogue()
        # Lazy load — builtins available after first access
        bp = cat.get_blueprint("morning-brief")
        assert bp is not None

    def test_implements_store_protocol(self):
        from praisonaiagents.scheduler.blueprint_defs import BlueprintStoreProtocol
        cat = BlueprintCatalogue()
        assert isinstance(cat, BlueprintStoreProtocol)
