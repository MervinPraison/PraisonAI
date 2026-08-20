"""
Tests for failover profile isolation in LLM.

Covers the fix for issue #3613 Gap 2: ``LLM._switch_to_profile`` mutated
shared instance state (``self.api_key`` / ``self.base_url`` / ``self.model``)
without a lock, so concurrent requests on one shared ``LLM`` instance could
cross-talk credentials and model after a failover rotation.

The fix threads the active profile through per-call kwargs instead of
mutating shared attributes, so an in-flight request on another coroutine can
never observe another request's failover credentials.
"""

from unittest.mock import Mock, patch

from praisonaiagents.llm.failover import AuthProfile, FailoverManager
from praisonaiagents.llm.llm import LLM


def _make_llm_with_profiles():
    """Build an LLM with a failover manager holding two profiles."""
    manager = FailoverManager()
    manager.add_profile(
        AuthProfile(name="primary", provider="openai", api_key="sk-primary", priority=0)
    )
    manager.add_profile(
        AuthProfile(
            name="backup",
            provider="openai",
            api_key="sk-backup",
            base_url="https://backup.example.com/v1",
            model="backup-model",
            priority=1,
        )
    )
    return LLM(model="gpt-4o-mini", failover_manager=manager), manager


class TestProfileSwitchDoesNotMutateSharedState:
    """The core regression: _switch_to_profile must not leak into self.*"""

    def test_initial_profile_applied_to_instance(self):
        """Init still applies the first available profile to the instance."""
        llm, _ = _make_llm_with_profiles()
        assert llm._current_profile is not None
        assert llm._current_profile.name == "primary"
        # Instance attributes reflect the initial profile (backward compat).
        assert llm.api_key == "sk-primary"

    def test_rotate_after_failure_keeps_instance_state_intact(self):
        """After failover rotation, self.* must keep the initial values."""
        llm, manager = _make_llm_with_profiles()
        original_api_key = llm.api_key
        original_base_url = llm.base_url
        original_model = llm.model

        primary = manager.get_profile("primary")
        backup = manager.get_profile("backup")
        manager.mark_failure(primary, "401 Unauthorized")
        next_profile = manager.get_next_profile()
        assert next_profile is not None and next_profile.name == "backup"

        # The fix: _switch_to_profile is gone; rotation is per-call kwargs.
        # The old behaviour mutated llm.api_key/base_url/model here.
        if hasattr(llm, "_switch_to_profile"):
            llm._switch_to_profile(next_profile)

        assert llm.api_key == original_api_key, "api_key leaked to shared instance"
        assert llm.base_url == original_base_url, "base_url leaked to shared instance"
        assert llm.model == original_model, "model leaked to shared instance"


class TestFailoverRetryUsesProfileCredentials:
    """End-to-end: the retry loop sends the rotated profile's credentials."""

    def test_retry_call_uses_backup_credentials(self):
        """A 401 on the primary profile retries with the backup's creds."""
        llm, _ = _make_llm_with_profiles()
        llm._max_retries = 2
        llm._retry_delay = 0.01

        # First call raises an auth error; second call succeeds.
        mock_func = Mock(
            side_effect=[
                Exception("AuthenticationError: 401 Unauthorized"),
                "ok",
            ]
        )

        with patch("time.sleep"):
            result = llm._call_with_retry(mock_func, model="gpt-4o-mini", api_key="sk-primary")

        assert result == "ok"
        # The retried call must carry the backup profile's credentials.
        assert mock_func.call_count == 2
        second_call_kwargs = mock_func.call_args_list[1].kwargs
        assert second_call_kwargs["api_key"] == "sk-backup"
        assert second_call_kwargs["base_url"] == "https://backup.example.com/v1"
        assert second_call_kwargs["model"] == "backup-model"

    def test_retry_call_backup_credentials_do_not_leak_to_instance(self):
        """Even after a rotated retry, self.* stays on the initial profile."""
        llm, _ = _make_llm_with_profiles()
        llm._max_retries = 2
        llm._retry_delay = 0.01

        mock_func = Mock(
            side_effect=[
                Exception("AuthenticationError: 401 Unauthorized"),
                "ok",
            ]
        )

        with patch("time.sleep"):
            llm._call_with_retry(mock_func, model="gpt-4o-mini", api_key="sk-primary")

        assert llm.api_key == "sk-primary"
        assert llm.base_url is None
        assert llm.model == "gpt-4o-mini"
