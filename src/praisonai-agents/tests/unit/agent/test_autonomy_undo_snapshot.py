"""Typed ``AutonomyConfig(snapshot=True)`` enables the pre-run snapshot — issue #6028."""

from praisonaiagents import Agent
from praisonaiagents.agent.autonomy import AutonomyConfig


def test_snapshot_field_defaults_off():
    assert AutonomyConfig().snapshot is False
    assert AutonomyConfig.from_dict({"snapshot": True}).snapshot is True


def test_typed_snapshot_reaches_autonomy_config_dict():
    agent = Agent(
        name="w",
        instructions="x",
        autonomy=AutonomyConfig(level="full_auto", snapshot=True),
        output="silent",
    )
    assert agent.autonomy_config["snapshot"] is True


def test_snapshot_off_by_default_in_agent():
    agent = Agent(name="w", instructions="x", autonomy="full_auto", output="silent")
    assert agent.autonomy_config["snapshot"] is False
