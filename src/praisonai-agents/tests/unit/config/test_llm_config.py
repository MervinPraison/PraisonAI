"""Tests for LLMConfig implementation with fallback models."""

import asyncio
import copy
import logging

import pytest

from praisonaiagents import Agent
from praisonaiagents.config import LLMConfig
from praisonaiagents.errors import LLMError


def test_llm_config_basic():
    """Test basic LLMConfig usage via llm parameter."""
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=["claude-3-5-sonnet", "gpt-4o-mini"],
        base_url="https://api.example.com",
        api_key="test-key",
    )

    agent = Agent(
        name="TestAgent",
        llm=config,
    )

    assert agent.llm == "gpt-4o"
    assert agent.fallback_models == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert agent.base_url == "https://api.example.com"
    assert agent.api_key == "test-key"
    assert getattr(agent, "_failover_manager", None) is None


def test_llm_config_via_model_param():
    """Test using LLMConfig via model parameter."""
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=["claude-3-5-sonnet", "gpt-4o-mini"],
        base_url="https://api.example.com",
    )

    agent = Agent(
        name="TestAgent",
        model=config,
    )

    assert agent.llm == "gpt-4o"
    assert agent.fallback_models == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert agent.base_url == "https://api.example.com"


def test_no_fallback_without_config():
    """Test that fallback_models can only be set via LLMConfig."""
    agent = Agent(
        name="TestAgent",
        model="gpt-4o",
        base_url="https://api.example.com",
        api_key="test-key",
    )

    assert agent.llm == "gpt-4o"
    assert agent.fallback_models == []
    assert agent.base_url == "https://api.example.com"
    assert agent.api_key == "test-key"


def test_fallback_models_defensive_copy():
    """Test that fallback_models creates defensive copy via LLMConfig."""
    original_list = ["claude-3-5-sonnet", "gpt-4o-mini"]
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=original_list,
    )

    agent = Agent(
        name="TestAgent",
        model=config,
    )

    original_list.append("gemini-pro")

    assert agent.fallback_models == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert "gemini-pro" not in agent.fallback_models


def test_llm_config_serialization():
    """Test LLMConfig serialization."""
    config = LLMConfig(
        model="gpt-4o",
        fallback_models=["claude-3-5-sonnet", "gpt-4o-mini"],
        base_url="https://api.example.com",
        api_key="test-key",
    )

    config_dict = config.to_dict()
    assert config_dict["model"] == "gpt-4o"
    assert config_dict["fallback_models"] == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert config_dict["base_url"] == "https://api.example.com"
    assert config_dict["api_key"] == "test-key"

    restored = LLMConfig.from_dict(config_dict)
    assert restored.model == "gpt-4o"
    assert restored.fallback_models == ["claude-3-5-sonnet", "gpt-4o-mini"]
    assert restored.base_url == "https://api.example.com"
    assert restored.api_key == "test-key"


def _profiles():
    return [
        {"provider": "openai", "api_key": "sk-primary"},
        {"provider": "openai", "api_key": "sk-backup"},
    ]


def _agent_with_profiles(**overrides):
    config = {"model": "gpt-4o-mini", "auth_profiles": _profiles()}
    config.update(overrides)
    return Agent(name="TestAgent", llm=LLMConfig(**config))


def _auth_failure(agent):
    def _raise_auth(**_kwargs):
        raise Exception("Invalid API key")

    agent._chat_completion_with_retry = _raise_auth
    with pytest.raises(LLMError) as caught:
        agent._chat_completion(
            [{"role": "user", "content": "hi"}],
            stream=False,
        )
    return caught.value


async def _async_auth_failure(agent):
    with pytest.raises(LLMError) as caught:
        await agent._handle_async_llm_error(
            Exception("Invalid API key"),
            [{"role": "user", "content": "hi"}],
        )
    return caught.value


def test_auth_profiles_build_failover_manager():
    """A bare model name with auth profiles builds a manager and a custom LLM."""
    agent = _agent_with_profiles()

    manager = agent._failover_manager
    assert manager.get_next_profile().api_key == "sk-primary"
    assert [profile.api_key for profile in manager.list_profiles()] == [
        "sk-primary",
        "sk-backup",
    ]
    assert agent._using_custom_llm is True
    assert agent._llm_init_params is not None
    assert "failover_manager" not in agent._llm_init_params


def test_auth_profiles_model_param_builds_manager():
    agent = Agent(name="TestAgent", model=LLMConfig(model="gpt-4o-mini", auth_profiles=_profiles()))
    assert [p.api_key for p in agent._failover_manager.list_profiles()] == ["sk-primary", "sk-backup"]


def test_auth_profiles_to_dict_never_writes_a_literal_key():
    """Literal keys are masked like AuthProfile.to_dict; references stay as written."""
    secret_ref = {"source": "env", "id": "OPENAI_API_KEY_BACKUP"}
    config = LLMConfig(
        model="gpt-4o-mini",
        auth_profiles=[
            {"name": "a", "api_key": "sk-live-SECRET-9999"},
            {"name": "b", "api_key": "${OPENAI_API_KEY_BACKUP}"},
            {"name": "c", "api_key": secret_ref},
        ],
    )

    payload = config.to_dict()
    keys = [p["api_key"] for p in payload["auth_profiles"]]
    assert keys == ["***9999", "${OPENAI_API_KEY_BACKUP}", secret_ref]
    assert "sk-live-SECRET-9999" not in repr(payload)
    # to_dict does not mutate the live config.
    assert config.auth_profiles[0]["api_key"] == "sk-live-SECRET-9999"

    restored = LLMConfig.from_dict(payload)
    assert restored.auth_profiles == payload["auth_profiles"]
    assert restored.auth_profiles[1] is not payload["auth_profiles"][1]


def test_masked_key_is_refused_not_sent():
    """A masked key reloaded from to_dict raises instead of reaching the provider."""
    payload = LLMConfig(model="gpt-4o-mini", auth_profiles=[{"api_key": "sk-live-1234"}]).to_dict()
    with pytest.raises(ValueError) as caught:
        Agent(name="TestAgent", llm=LLMConfig.from_dict(payload))
    assert "1234" not in str(caught.value)


def test_auth_profiles_resolve_env_and_secret_ref(monkeypatch):
    """${ENV} and a secret ref both resolve onto the built profile."""
    monkeypatch.setenv("OPENAI_API_KEY_BACKUP", "sk-from-env")
    agent = Agent(
        name="TestAgent",
        llm=LLMConfig(
            model="gpt-4o-mini",
            auth_profiles=[
                {"api_key": "${OPENAI_API_KEY_BACKUP}"},
                {"api_key": {"source": "env", "id": "OPENAI_API_KEY_BACKUP"}},
            ],
        ),
    )

    keys = [profile.api_key for profile in agent._failover_manager.list_profiles()]
    assert keys == ["sk-from-env", "sk-from-env"]


def test_non_dict_profile_raises():
    from praisonaiagents.llm.failover import manager_from_auth_profiles

    with pytest.raises(TypeError, match="auth profile 1 must be a dict"):
        manager_from_auth_profiles(["sk-plain-string"])


def test_clone_and_deepcopy_share_failover_manager():
    """Channel clones and deepcopy share the manager, lock and all."""
    agent = _agent_with_profiles()
    clone = agent.clone_for_channel()
    assert clone._failover_manager is agent._failover_manager

    primary = agent._failover_manager.get_next_profile()
    agent._failover_manager.mark_failure(primary, "rate limit", is_rate_limit=True)
    assert clone._failover_manager.get_next_profile().api_key == "sk-backup"

    # An LLM holding the manager used to make deepcopy walk its RLock and raise.
    # LLM() itself imports litellm, so install a real instance shell instead.
    from praisonaiagents.llm.llm import LLM
    llm = LLM.__new__(LLM)
    llm.__dict__["_failover_manager"] = agent._failover_manager
    llm.__dict__["_current_profile"] = primary
    agent._llm_instance = llm

    copied = copy.deepcopy(agent)
    assert copied._failover_manager is agent._failover_manager
    assert copied._llm_instance is not agent._llm_instance
    assert copied._llm_instance._failover_manager is agent._failover_manager
    assert copied._llm_instance._current_profile is primary
    assert copied._failover_manager.get_next_profile().api_key == "sk-backup"


def test_failover_manager_deepcopy_returns_the_shared_pool():
    from praisonaiagents.llm.failover import manager_from_auth_profiles

    manager = manager_from_auth_profiles(_profiles())
    profile = manager.list_profiles()[0]
    copied_manager, copied_profile = copy.deepcopy((manager, profile))
    assert copied_manager is manager
    assert copied_profile is profile


def test_fallback_llm_for_keeps_requested_model():
    """A model fallback keeps its own model, not a primary profile's."""
    pytest.importorskip("litellm", reason="optional LLM provider dependency")
    agent = _agent_with_profiles(
        auth_profiles=[{"provider": "openai", "api_key": "sk-primary", "model": "gpt-4o-mini"}],
    )
    fallback = agent._fallback_llm_for("gpt-4o")

    assert fallback.model == "gpt-4o"
    assert fallback._failover_manager is None
    assert "failover_manager" not in agent._llm_init_params


def test_switch_model_keeps_rotation_notice_consistent():
    """switch_model() builds an LLM without the manager; the notice check follows it."""
    pytest.importorskip("litellm", reason="optional LLM provider dependency")
    agent = _agent_with_profiles()
    assert agent._credential_failover_active() is True
    assert agent.llm_instance._failover_manager is agent._failover_manager

    agent.switch_model("gpt-4o")

    active = agent._credential_failover_active()
    assert active is (agent._llm_instance._failover_manager is not None)
    notice = _auth_failure(agent).context["user_message"].endswith("Credential rotation is not yet implemented.")
    assert notice is (not active)


def test_omitted_profile_names_are_indexed():
    agent = Agent(
        name="TestAgent",
        llm=LLMConfig(
            model="gpt-4o-mini",
            auth_profiles=[{"api_key": "sk-a"}, {"api_key": "sk-b"}],
        ),
    )
    assert [profile.name for profile in agent._failover_manager.list_profiles()] == [
        "openai-1",
        "openai-2",
    ]


def test_empty_auth_profiles_build_no_manager():
    agent = Agent(
        name="TestAgent",
        llm=LLMConfig(model="gpt-4o-mini", auth_profiles=[]),
    )
    assert getattr(agent, "_failover_manager", None) is None


def test_missing_env_api_key_raises_with_locator(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY_BACKUP", raising=False)
    with pytest.raises(ValueError) as caught:
        Agent(
            name="TestAgent",
            llm=LLMConfig(
                model="gpt-4o-mini",
                auth_profiles=[{"api_key": "${OPENAI_API_KEY_BACKUP}"}],
            ),
        )
    message = str(caught.value)
    assert "OPENAI_API_KEY_BACKUP" in message
    assert "sk-" not in message


def test_empty_api_key_raises_with_locator():
    with pytest.raises(ValueError) as caught:
        Agent(
            name="TestAgent",
            llm=LLMConfig(
                model="gpt-4o-mini",
                auth_profiles=[{"api_key": ""}],
            ),
        )
    message = str(caught.value)
    assert "profile 1" in message
    assert "sk-" not in message


def test_auth_error_without_manager_reports_unimplemented_rotation(caplog):
    agent = Agent(name="TestAgent", llm="gpt-4o-mini")
    with caplog.at_level(logging.WARNING):
        error = _auth_failure(agent)
        async_error = asyncio.run(
            _async_auth_failure(agent)
        )
    for caught in (error, async_error):
        assert caught.context["user_message"].endswith(
            "Credential rotation is not yet implemented."
        )
    assert "credential rotation not yet implemented" in caplog.text


def test_auth_error_with_manager_skips_unimplemented_rotation(caplog):
    agent = _agent_with_profiles()
    with caplog.at_level(logging.WARNING):
        error = _auth_failure(agent)
        async_error = asyncio.run(
            _async_auth_failure(agent)
        )
    for caught in (error, async_error):
        assert "Credential rotation is not yet implemented." not in caught.context["user_message"]
    assert "credential rotation not yet implemented" not in caplog.text


def _completion_failing_for(litellm, bad_key, message, calls):
    def fake_completion(**kwargs):
        calls.append(kwargs)
        if kwargs.get("api_key") == bad_key:
            raise Exception(message)
        return litellm.ModelResponse(
            model="gpt-4o-mini",
            choices=[{"message": {"role": "assistant", "content": "backup answered"}}],
        )
    return fake_completion


@pytest.mark.parametrize("message", [
    "AuthenticationError: 401 Unauthorized",
    "AuthenticationError: Incorrect API key provided",
    "Error: insufficient quota for this key",
])
def test_agent_turn_moves_to_backup_profile(monkeypatch, message):
    """One Agent chat turn: the primary key is rejected, the backup key answers."""
    litellm = pytest.importorskip("litellm", reason="optional LLM provider dependency")
    from praisonaiagents.llm.llm import LLM

    # Pin the Chat Completions path so one stub covers the whole turn.
    monkeypatch.setattr(LLM, "_supports_responses_api", lambda self: False)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    calls = []
    monkeypatch.setattr(litellm, "completion", _completion_failing_for(litellm, "sk-primary", message, calls))
    agent = _agent_with_profiles()

    assert agent.chat("hi") == "backup answered"
    assert [call["api_key"] for call in calls] == ["sk-primary", "sk-backup"]


def test_rejected_key_without_backup_still_surfaces():
    pytest.importorskip("litellm", reason="optional LLM provider dependency")
    from unittest.mock import Mock

    agent = _agent_with_profiles(auth_profiles=[{"provider": "openai", "api_key": "sk-only"}])
    llm = agent.llm_instance
    call = Mock(side_effect=Exception("Incorrect API key provided"))

    with pytest.raises(Exception, match="Incorrect API key"):
        llm._call_with_retry(call, model="gpt-4o-mini", api_key=llm.api_key)
    assert call.call_count == 1


def test_import_does_not_load_failover_module():
    import subprocess
    import sys

    code = (
        "import sys, warnings; warnings.simplefilter('ignore');"
        "import praisonaiagents; from praisonaiagents import Agent;"
        "Agent(name='x', llm='gpt-4o-mini');"
        "print('praisonaiagents.llm.failover' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == "False"
