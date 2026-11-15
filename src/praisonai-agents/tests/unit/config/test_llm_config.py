"""Tests for LLMConfig implementation with fallback models."""

import asyncio
import copy
import logging

import pytest

from praisonaiagents import Agent
from praisonaiagents.config import LLMConfig
from praisonaiagents.errors import LLMError
from praisonaiagents.llm.quota import LocalQuotaCoordinator


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


def test_auth_profiles_round_trip_keeps_api_keys():
    """to_dict/from_dict keep the declared api_key, not a masked form."""
    profiles = _profiles()
    config = LLMConfig(
        model="gpt-4o-mini",
        auth_profiles=profiles,
        quota_coordinator="local",
        failover={"max_retries": 2},
    )

    payload = config.to_dict()
    assert payload["auth_profiles"] == profiles
    assert "***" not in payload["auth_profiles"][0]["api_key"]
    assert payload["quota_coordinator"] == "local"
    assert payload["failover"] == {"max_retries": 2}

    restored = LLMConfig.from_dict(payload)
    assert restored.auth_profiles == profiles
    assert restored.quota_coordinator == "local"
    assert restored.failover == {"max_retries": 2}


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


def test_clone_and_deepcopy_share_failover_manager():
    """Channel clones and deepcopy share the manager, lock and all."""
    agent = _agent_with_profiles()
    clone = agent.clone_for_channel()
    assert clone._failover_manager is agent._failover_manager

    primary = agent._failover_manager.get_next_profile()
    agent._failover_manager.mark_failure(primary, "rate limit", is_rate_limit=True)
    assert clone._failover_manager.get_next_profile().api_key == "sk-backup"

    # _llm_instance is inserted before _failover_manager. Once it holds the
    # manager, deepcopy used to walk FailoverManager's RLock and raise.
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


def test_fallback_llm_for_keeps_requested_model():
    """A model fallback keeps its own model and settings, not a primary profile's."""
    pytest.importorskip("litellm", reason="optional LLM provider dependency")
    agent = _agent_with_profiles(
        auth_profiles=[
            {"provider": "openai", "api_key": "sk-primary", "model": "gpt-4o-mini",
             "base_url": "https://primary.example.com/v1"},
        ],
    )
    same_provider = agent._fallback_llm_for("gpt-4o")
    other_provider = agent._fallback_llm_for("anthropic/claude-3-5-sonnet")

    assert same_provider.model == "gpt-4o"
    assert other_provider.model == "anthropic/claude-3-5-sonnet"
    assert same_provider._failover_manager is None
    assert other_provider._failover_manager is None
    # A same-provider fallback keeps the profile's key and endpoint.
    assert same_provider.api_key == "sk-primary"
    assert same_provider.base_url == "https://primary.example.com/v1"
    # Another provider gets neither.
    assert other_provider.api_key != "sk-primary"
    assert other_provider.base_url != "https://primary.example.com/v1"
    assert "failover_manager" not in agent._llm_init_params


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


def test_redis_quota_coordinator_stays_local():
    """A redis URL fail-opens to the local coordinator and does not connect."""
    agent = _agent_with_profiles(quota_coordinator="redis://localhost:6379/0")
    assert isinstance(agent._failover_manager._coordinator, LocalQuotaCoordinator)


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


def test_unknown_failover_key_raises():
    secret = "sk-do-not-leak"
    with pytest.raises(TypeError) as caught:
        Agent(
            name="TestAgent",
            llm=LLMConfig(
                model="gpt-4o-mini",
                auth_profiles=[{"api_key": secret}],
                failover={"not_a_failover_field": True},
            ),
        )
    message = str(caught.value)
    assert "not_a_failover_field" in message
    assert secret not in message


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


async def _async_auth_failure(agent):
    with pytest.raises(LLMError) as caught:
        await agent._handle_async_llm_error(
            Exception("Invalid API key"),
            [{"role": "user", "content": "hi"}],
        )
    return caught.value


def test_agent_turn_recovers_through_backup_profile(monkeypatch):
    """One Agent chat turn: the primary key fails auth, the backup key answers."""
    litellm = pytest.importorskip("litellm", reason="optional LLM provider dependency")
    from praisonaiagents.llm.llm import LLM

    # Pin the Chat Completions path so one stub covers the whole turn.
    monkeypatch.setattr(LLM, "_supports_responses_api", lambda self: False)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise Exception("AuthenticationError: 401 Unauthorized")
        return litellm.ModelResponse(
            model="gpt-4o-mini",
            choices=[{"message": {"role": "assistant", "content": "backup answered"}}],
        )

    monkeypatch.setattr(litellm, "completion", fake_completion)
    agent = _agent_with_profiles()

    reply = agent.chat("hi")

    assert reply == "backup answered"
    assert len(calls) == 2
    assert calls[0]["api_key"] == "sk-primary"
    assert calls[1]["api_key"] == "sk-backup"


def _keyed_profiles(count):
    return [{"provider": "openai", "api_key": f"sk-{index}"} for index in range(1, count + 1)]


def test_failover_max_retries_zero_tries_one_profile(monkeypatch):
    pytest.importorskip("litellm", reason="optional LLM provider dependency")
    from unittest.mock import Mock

    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    agent = _agent_with_profiles(failover={"max_retries": 0})
    llm = agent.llm_instance
    call = Mock(side_effect=[Exception("AuthenticationError: 401 Unauthorized"), "ok"])

    with pytest.raises(Exception, match="401"):
        llm._call_with_retry(call, model="gpt-4o-mini")
    assert call.call_count == 1


def test_failover_retry_settings_reach_later_profiles(monkeypatch):
    pytest.importorskip("litellm", reason="optional LLM provider dependency")
    from unittest.mock import Mock

    sleeps = []
    monkeypatch.setattr("time.sleep", sleeps.append)
    agent = _agent_with_profiles(
        auth_profiles=_keyed_profiles(5),
        failover={"max_retries": 4, "retry_delay": 0.25, "max_retry_delay": 1.0},
    )
    llm = agent.llm_instance
    auth_error = Exception("AuthenticationError: 401 Unauthorized")
    call = Mock(side_effect=[auth_error] * 4 + ["ok"])

    assert llm._call_with_retry(call, model="gpt-4o-mini", api_key=llm.api_key) == "ok"
    assert [c.kwargs["api_key"] for c in call.call_args_list] == [
        "sk-1", "sk-2", "sk-3", "sk-4", "sk-5",
    ]
    assert sleeps == [0.25, 0.5, 1.0, 1.0]


def test_explicit_llm_max_retries_beats_failover_config():
    pytest.importorskip("litellm", reason="optional LLM provider dependency")
    from praisonaiagents.llm.failover import manager_from_auth_profiles
    from praisonaiagents.llm.llm import LLM

    manager = manager_from_auth_profiles(_profiles(), failover={"max_retries": 0})
    assert LLM(model="gpt-4o-mini", failover_manager=manager)._max_retries == 0
    assert LLM(model="gpt-4o-mini", failover_manager=manager, max_retries=5)._max_retries == 5


@pytest.mark.parametrize("message", [
    "AuthenticationError: Incorrect API key provided",
    "Error: insufficient quota for this key",
])
def test_rejected_key_turn_moves_to_backup_profile(monkeypatch, message):
    """A key the provider rejects for good, or one out of quota, falls to the backup."""
    litellm = pytest.importorskip("litellm", reason="optional LLM provider dependency")
    from praisonaiagents.llm.llm import LLM

    monkeypatch.setattr(LLM, "_supports_responses_api", lambda self: False)
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        if kwargs.get("api_key") == "sk-primary":
            raise Exception(message)
        return litellm.ModelResponse(
            model="gpt-4o-mini",
            choices=[{"message": {"role": "assistant", "content": "backup answered"}}],
        )

    monkeypatch.setattr(litellm, "completion", fake_completion)
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


def test_fallback_keeps_profile_key_and_server_together():
    """Config base_url A plus a profile with its own key and server B: both clients use B."""
    pytest.importorskip("litellm", reason="optional LLM provider dependency")
    agent = _agent_with_profiles(
        base_url="https://server-a.example.com/v1",
        auth_profiles=[{"provider": "openai", "api_key": "sk-b",
                        "base_url": "https://server-b.example.com/v1"}],
    )
    primary = agent.llm_instance
    fallback = agent._fallback_llm_for("gpt-4o")

    assert (primary.api_key, primary.base_url) == ("sk-b", "https://server-b.example.com/v1")
    assert (fallback.api_key, fallback.base_url) == (primary.api_key, primary.base_url)
    assert fallback.model == "gpt-4o"


def test_prefixed_fallback_skips_profile_for_another_provider():
    """An OpenAI profile's key never reaches an anthropic/ fallback."""
    pytest.importorskip("litellm", reason="optional LLM provider dependency")
    agent = Agent(
        name="TestAgent",
        llm=LLMConfig(
            model="anthropic/claude-3-5-haiku-latest",
            auth_profiles=[
                {"provider": "openai", "api_key": "sk-openai",
                 "base_url": "https://openai-proxy.example.com/v1"},
            ],
        ),
    )
    fallback = agent._fallback_llm_for("anthropic/claude-3-5-sonnet-latest")

    assert fallback.model == "anthropic/claude-3-5-sonnet-latest"
    assert fallback.api_key != "sk-openai"
    assert fallback.base_url != "https://openai-proxy.example.com/v1"


def test_prefixed_fallback_takes_profile_for_same_provider():
    pytest.importorskip("litellm", reason="optional LLM provider dependency")
    agent = Agent(
        name="TestAgent",
        llm=LLMConfig(
            model="anthropic/claude-3-5-haiku-latest",
            auth_profiles=[{"provider": "anthropic", "api_key": "sk-ant"}],
        ),
    )
    fallback = agent._fallback_llm_for("anthropic/claude-3-5-sonnet-latest")

    assert fallback.api_key == "sk-ant"


@pytest.mark.parametrize("configured, expected", [
    (None, None),
    ("https://configured.example.com/v1", "https://configured.example.com/v1"),
])
def test_rotation_drops_the_failed_profiles_server(monkeypatch, configured, expected):
    """A backup with no base_url never sends its key to the failed profile's server."""
    pytest.importorskip("litellm", reason="optional LLM provider dependency")
    from unittest.mock import Mock
    from praisonaiagents.llm.failover import manager_from_auth_profiles
    from praisonaiagents.llm.llm import LLM

    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    manager = manager_from_auth_profiles([
        {"provider": "openai", "api_key": "sk-proxy", "base_url": "https://proxy.example.com/v1"},
        {"provider": "openai", "api_key": "sk-direct"},
    ])
    llm = LLM(model="gpt-4o-mini", base_url=configured, failover_manager=manager)
    call = Mock(side_effect=[Exception("AuthenticationError: 401 Unauthorized"), "ok"])

    assert llm._call_with_retry(
        call, model="gpt-4o-mini", api_key=llm.api_key, base_url=llm.base_url,
    ) == "ok"
    first, second = (c.kwargs for c in call.call_args_list)
    assert (first["api_key"], first["base_url"]) == ("sk-proxy", "https://proxy.example.com/v1")
    assert second["api_key"] == "sk-direct"
    assert second.get("base_url") == expected


@pytest.mark.parametrize("primary, fallback_model, provider", [
    ("gemini/gemini-2.0-flash", "gemini/gemini-1.5-pro", "google"),
    ("anthropic/claude-3-5-haiku-latest", "anthropic/claude-3-5-sonnet-latest", "claude"),
])
def test_prefixed_fallback_accepts_provider_aliases(primary, fallback_model, provider):
    """A profile named by a provider alias still serves its prefixed fallback."""
    pytest.importorskip("litellm", reason="optional LLM provider dependency")
    agent = Agent(
        name="TestAgent",
        llm=LLMConfig(model=primary, auth_profiles=[{"provider": provider, "api_key": "sk-alias"}]),
    )

    assert agent._fallback_llm_for(fallback_model).api_key == "sk-alias"
