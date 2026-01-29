"""
Unit tests for Failover components.
"""

from praisonaiagents.llm.failover import (
    AuthProfile,
    ProviderStatus,
    FailoverConfig,
    FailoverManager,
)


class TestAuthProfile:
    """Tests for AuthProfile."""
    
    def test_profile_creation(self):
        """Test profile creation."""
        profile = AuthProfile(
            name="openai-primary",
            provider="openai",
            api_key="sk-test123",
        )
        assert profile.name == "openai-primary"
        assert profile.provider == "openai"
        assert profile.status == ProviderStatus.AVAILABLE
    
    def test_profile_is_available(self):
        """Test availability check."""
        profile = AuthProfile(name="test", provider="openai", api_key="key")
        assert profile.is_available is True
        
        profile.status = ProviderStatus.DISABLED
        assert profile.is_available is False
    
    def test_mark_rate_limited(self):
        """Test marking profile as rate limited."""
        profile = AuthProfile(name="test", provider="openai", api_key="key")
        profile.mark_rate_limited(cooldown_seconds=60)
        
        assert profile.status == ProviderStatus.RATE_LIMITED
        assert profile.is_available is False
        assert profile.cooldown_until is not None
    
    def test_mark_error(self):
        """Test marking profile with error."""
        profile = AuthProfile(name="test", provider="openai", api_key="key")
        profile.mark_error("Connection failed", cooldown_seconds=30)
        
        assert profile.status == ProviderStatus.ERROR
        assert profile.last_error == "Connection failed"
        assert profile.is_available is False
    
    def test_reset(self):
        """Test resetting profile."""
        profile = AuthProfile(name="test", provider="openai", api_key="key")
        profile.mark_error("Error")
        profile.reset()
        
        assert profile.status == ProviderStatus.AVAILABLE
        assert profile.cooldown_until is None
        assert profile.last_error is None
    
    def test_to_dict_hides_key(self):
        """Test that to_dict hides API key."""
        profile = AuthProfile(
            name="test",
            provider="openai",
            api_key="sk-verysecretkey123",
        )
        data = profile.to_dict()
        assert data["api_key"].startswith("***")
        assert len(data["api_key"]) == 7
    
    def test_from_dict(self):
        """Test creating profile from dict."""
        data = {
            "name": "test",
            "provider": "anthropic",
            "api_key": "key",
            "model": "claude-3",
            "priority": 1,
        }
        profile = AuthProfile.from_dict(data)
        assert profile.name == "test"
        assert profile.provider == "anthropic"
        assert profile.model == "claude-3"
        assert profile.priority == 1


class TestProviderStatus:
    """Tests for ProviderStatus enum."""
    
    def test_status_values(self):
        """Test status values."""
        assert ProviderStatus.AVAILABLE.value == "available"
        assert ProviderStatus.RATE_LIMITED.value == "rate_limited"
        assert ProviderStatus.ERROR.value == "error"
        assert ProviderStatus.DISABLED.value == "disabled"


class TestFailoverConfig:
    """Tests for FailoverConfig."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = FailoverConfig()
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.exponential_backoff is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = FailoverConfig(
            max_retries=5,
            retry_delay=2.0,
            cooldown_on_rate_limit=120,
        )
        assert config.max_retries == 5
        assert config.retry_delay == 2.0
        assert config.cooldown_on_rate_limit == 120
    
    def test_to_dict(self):
        """Test config serialization."""
        config = FailoverConfig(max_retries=5)
        data = config.to_dict()
        assert data["max_retries"] == 5


class TestFailoverManager:
    """Tests for FailoverManager."""
    
    def test_add_profile(self):
        """Test adding profiles."""
        manager = FailoverManager()
        profile = AuthProfile(name="test", provider="openai", api_key="key")
        manager.add_profile(profile)
        
        assert len(manager.list_profiles()) == 1
    
    def test_remove_profile(self):
        """Test removing profiles."""
        manager = FailoverManager()
        profile = AuthProfile(name="test", provider="openai", api_key="key")
        manager.add_profile(profile)
        
        assert manager.remove_profile("test") is True
        assert manager.remove_profile("nonexistent") is False
        assert len(manager.list_profiles()) == 0
    
    def test_get_profile(self):
        """Test getting profile by name."""
        manager = FailoverManager()
        profile = AuthProfile(name="test", provider="openai", api_key="key")
        manager.add_profile(profile)
        
        found = manager.get_profile("test")
        assert found is not None
        assert found.name == "test"
        
        assert manager.get_profile("nonexistent") is None
    
    def test_get_next_profile(self):
        """Test getting next available profile."""
        manager = FailoverManager()
        
        assert manager.get_next_profile() is None
        
        profile1 = AuthProfile(name="p1", provider="openai", api_key="k1", priority=0)
        profile2 = AuthProfile(name="p2", provider="openai", api_key="k2", priority=1)
        manager.add_profile(profile2)
        manager.add_profile(profile1)
        
        next_profile = manager.get_next_profile()
        assert next_profile.name == "p1"
    
    def test_priority_ordering(self):
        """Test profiles are ordered by priority."""
        manager = FailoverManager()
        
        manager.add_profile(AuthProfile(name="low", provider="openai", api_key="k", priority=10))
        manager.add_profile(AuthProfile(name="high", provider="openai", api_key="k", priority=0))
        manager.add_profile(AuthProfile(name="mid", provider="openai", api_key="k", priority=5))
        
        profiles = manager.list_profiles()
        assert profiles[0].name == "high"
        assert profiles[1].name == "mid"
        assert profiles[2].name == "low"
    
    def test_failover_on_rate_limit(self):
        """Test failover when rate limited."""
        manager = FailoverManager()
        
        p1 = AuthProfile(name="p1", provider="openai", api_key="k1", priority=0)
        p2 = AuthProfile(name="p2", provider="openai", api_key="k2", priority=1)
        manager.add_profile(p1)
        manager.add_profile(p2)
        
        manager.mark_failure(p1, "Rate limit", is_rate_limit=True)
        
        next_profile = manager.get_next_profile()
        assert next_profile.name == "p2"
    
    def test_mark_success(self):
        """Test marking profile as successful."""
        manager = FailoverManager()
        profile = AuthProfile(name="test", provider="openai", api_key="key")
        manager.add_profile(profile)
        
        profile.mark_error("Error")
        assert profile.status == ProviderStatus.ERROR
        
        manager.mark_success(profile)
        assert profile.status == ProviderStatus.AVAILABLE
    
    def test_get_retry_delay(self):
        """Test retry delay calculation."""
        config = FailoverConfig(retry_delay=1.0, exponential_backoff=True)
        manager = FailoverManager(config=config)
        
        assert manager.get_retry_delay(0) == 1.0
        assert manager.get_retry_delay(1) == 2.0
        assert manager.get_retry_delay(2) == 4.0
    
    def test_get_retry_delay_no_backoff(self):
        """Test retry delay without exponential backoff."""
        config = FailoverConfig(retry_delay=2.0, exponential_backoff=False)
        manager = FailoverManager(config=config)
        
        assert manager.get_retry_delay(0) == 2.0
        assert manager.get_retry_delay(1) == 2.0
        assert manager.get_retry_delay(5) == 2.0
    
    def test_max_retry_delay(self):
        """Test max retry delay cap."""
        config = FailoverConfig(retry_delay=10.0, max_retry_delay=30.0)
        manager = FailoverManager(config=config)
        
        assert manager.get_retry_delay(5) == 30.0
    
    def test_status(self):
        """Test status report."""
        manager = FailoverManager()
        manager.add_profile(AuthProfile(name="p1", provider="openai", api_key="k1"))
        manager.add_profile(AuthProfile(name="p2", provider="openai", api_key="k2"))
        
        status = manager.status()
        assert status["total_profiles"] == 2
        assert status["available_profiles"] == 2
    
    def test_reset_all(self):
        """Test resetting all profiles."""
        manager = FailoverManager()
        p1 = AuthProfile(name="p1", provider="openai", api_key="k1")
        p2 = AuthProfile(name="p2", provider="openai", api_key="k2")
        manager.add_profile(p1)
        manager.add_profile(p2)
        
        p1.mark_error("Error")
        p2.mark_rate_limited()
        
        manager.reset_all()
        
        assert p1.status == ProviderStatus.AVAILABLE
        assert p2.status == ProviderStatus.AVAILABLE
    
    def test_on_failover_callback(self):
        """Test failover callback."""
        manager = FailoverManager()
        
        p1 = AuthProfile(name="p1", provider="openai", api_key="k1", priority=0)
        p2 = AuthProfile(name="p2", provider="openai", api_key="k2", priority=1)
        manager.add_profile(p1)
        manager.add_profile(p2)
        
        callback_called = []
        
        def on_failover(failed, new):
            callback_called.append((failed.name, new.name))
        
        manager.on_failover(on_failover)
        manager.mark_failure(p1, "Error")
        
        assert len(callback_called) == 1
        assert callback_called[0] == ("p1", "p2")
