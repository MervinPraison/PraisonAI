"""Tests for coordinated session-learning defaults on bot/gateway agents.

Covers Issue #4864 and the follow-up review fixes:
  * default-on learning for a bot-injected memory,
  * config opt-out that flows through ``config.metadata`` (gateway path) and
    through mapping/attribute configs,
  * user-supplied *dict* memory gets a LearnManager merged in (auto_memory),
  * a live user memory instance / explicit agent opt-out is left untouched.
"""

import pytest

from praisonaiagents import Agent
from praisonaiagents.bots.config import BotConfig
from praisonai_bot.bots._defaults import (
    apply_bot_smart_defaults,
    _config_learn_value,
    _learning_opt_out,
)


def test_default_on_for_bot_injected_memory():
    agent = Agent(name="d1")
    apply_bot_smart_defaults(agent, BotConfig())
    assert agent._learn_config is not None
    assert agent._learn_config.nudge_min_tool_iters == 0
    assert agent._learn_config.nudge_interval == 10
    assert agent._auto_memory is True


def test_opt_out_via_config_metadata():
    # Gateway forwards ``learn: false`` into BotConfig.metadata (no native field).
    cfg = BotConfig()
    cfg.metadata["learn"] = False
    assert _learning_opt_out(cfg) is True

    agent = Agent(name="d2")
    apply_bot_smart_defaults(agent, cfg)
    assert agent._learn_config is None


def test_opt_out_via_session_learning_metadata_string():
    cfg = BotConfig()
    cfg.metadata["session_learning"] = "false"
    assert _learning_opt_out(cfg) is True


def test_opt_out_via_mapping_config():
    assert _learning_opt_out({"learn": False}) is True
    assert _learning_opt_out({"session_learning": "off"}) is True
    assert _learning_opt_out({}) is False


def test_config_learn_value_precedence_and_unset():
    assert _config_learn_value(None) is None
    assert _config_learn_value(BotConfig()) is None
    cfg = BotConfig()
    cfg.metadata["learn"] = True
    assert _config_learn_value(cfg) is True


def test_user_supplied_memory_gets_nudge_but_is_not_rewritten():
    # A user-supplied memory is never swapped out: the nudge cadence is enabled
    # (drives the auto-injected store_learning tool) but the memory instance the
    # operator chose is preserved. This is the deliberate safety tradeoff.
    agent = Agent(name="d4", memory={"history": True, "history_limit": 10})
    original_instance = agent._memory_instance
    apply_bot_smart_defaults(agent, BotConfig())
    assert agent._learn_config is not None
    assert agent._learn_config.nudge_min_tool_iters == 0
    assert agent._memory_instance is original_instance


def test_user_dict_memory_with_explicit_learn_is_respected():
    # A user who already set learn in their memory dict keeps their intent:
    # the default learn posture must NOT overwrite an explicit propose mode.
    agent = Agent(name="d4b", memory={"history": True, "learn": {"mode": "propose"}})
    apply_bot_smart_defaults(agent, BotConfig())
    learn = agent.memory.get("learn")
    assert isinstance(learn, dict)
    assert learn.get("mode") == "propose"


def test_explicit_agent_learn_false_is_untouched():
    agent = Agent(name="d5", learn=False)
    apply_bot_smart_defaults(agent, BotConfig())
    assert agent._learn_config is None
    assert agent._learn_enabled is False


def test_preconfigured_agent_learn_true_is_untouched():
    agent = Agent(name="d6", learn=True)
    existing = agent._learn_config
    apply_bot_smart_defaults(agent, BotConfig())
    # apply_bot_smart_defaults must not overwrite a pre-configured learn posture.
    assert agent._learn_config is existing
