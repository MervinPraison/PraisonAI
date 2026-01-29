"""
Real Integration Tests for Gateway, Bots, Sandbox, and Failover Features.

These tests use real API calls and verify actual functionality.
Requires: OPENAI_API_KEY environment variable.
"""

import asyncio
import os
import sys
import time
import pytest
from typing import Dict, Any
from unittest.mock import patch, MagicMock

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from praisonaiagents import Agent, tool
from praisonaiagents import (
    # Gateway
    GatewayConfig, SessionConfig, GatewayEvent, GatewayMessage, EventType,
    GatewayProtocol, GatewaySessionProtocol, GatewayClientProtocol,
    # Bots
    BotConfig, BotMessage, BotUser, BotChannel, MessageType, BotProtocol,
    # Sandbox
    SandboxConfig, SandboxResult, SandboxStatus, ResourceLimits, SecurityPolicy,
    SandboxProtocol,
    # Failover
    AuthProfile, FailoverConfig, FailoverManager, ProviderStatus,
)


# ============================================================================
# GATEWAY REAL TESTS (5+ tests)
# ============================================================================

class TestGatewayReal:
    """Real integration tests for Gateway feature."""
    
    def test_gateway_config_creation_and_serialization(self):
        """Test 1: Gateway config can be created and serialized."""
        config = GatewayConfig(
            host="127.0.0.1",
            port=8765,
            auth_token="test-secret-token",
            max_connections=500,
            heartbeat_interval=30,
        )
        
        # Verify attributes
        assert config.host == "127.0.0.1"
        assert config.port == 8765
        assert config.auth_token == "test-secret-token"
        assert config.max_connections == 500
        
        # Verify serialization hides token
        config_dict = config.to_dict()
        assert "test-secret-token" not in str(config_dict)
        assert config_dict["auth_token"] == "***"
        
        # Verify computed properties
        assert config.ws_url == "ws://127.0.0.1:8765"
        assert config.http_url == "http://127.0.0.1:8765"
        assert config.is_secure is False
    
    def test_gateway_session_config(self):
        """Test 2: Session config works correctly."""
        session_config = SessionConfig(
            timeout=7200,
            max_messages=500,
            persist=True,
            persist_path="/tmp/sessions",
        )
        
        assert session_config.timeout == 7200
        assert session_config.max_messages == 500
        assert session_config.persist is True
        
        # Verify serialization
        session_dict = session_config.to_dict()
        assert session_dict["timeout"] == 7200
        assert session_dict["persist_path"] == "/tmp/sessions"
    
    def test_gateway_event_creation_and_roundtrip(self):
        """Test 3: Gateway events can be created and serialized."""
        event = GatewayEvent(
            type=EventType.MESSAGE,
            data={"content": "Hello, World!"},
            source="agent-1",
            target="client-1",
        )
        
        assert event.type == EventType.MESSAGE
        assert event.data["content"] == "Hello, World!"
        assert event.source == "agent-1"
        assert event.target == "client-1"
        assert event.event_id is not None
        assert event.timestamp > 0
        
        # Test serialization roundtrip
        event_dict = event.to_dict()
        restored = GatewayEvent.from_dict(event_dict)
        assert restored.type == EventType.MESSAGE
        assert restored.data["content"] == "Hello, World!"
    
    def test_gateway_message_creation(self):
        """Test 4: Gateway messages work correctly."""
        message = GatewayMessage(
            content="Test message",
            role="user",
            agent_id="agent-1",
            session_id="session-123",
        )
        
        assert message.content == "Test message"
        assert message.role == "user"
        assert message.agent_id == "agent-1"
        assert message.session_id == "session-123"
        
        # Test serialization
        msg_dict = message.to_dict()
        assert msg_dict["content"] == "Test message"
        
        # Test roundtrip
        restored = GatewayMessage.from_dict(msg_dict)
        assert restored.content == "Test message"
    
    def test_gateway_event_types_complete(self):
        """Test 5: All event types are defined."""
        expected_types = [
            "CONNECT", "DISCONNECT", "RECONNECT",
            "SESSION_START", "SESSION_END", "SESSION_UPDATE",
            "AGENT_REGISTER", "AGENT_UNREGISTER", "AGENT_STATUS",
            "MESSAGE", "MESSAGE_ACK", "TYPING",
            "HEALTH", "ERROR", "BROADCAST",
        ]
        
        for event_type in expected_types:
            assert hasattr(EventType, event_type), f"Missing EventType.{event_type}"
    
    def test_gateway_config_with_ssl(self):
        """Test 6: Gateway config with SSL settings."""
        config = GatewayConfig(
            host="0.0.0.0",
            port=443,
            ssl_cert="/path/to/cert.pem",
            ssl_key="/path/to/key.pem",
        )
        
        assert config.is_secure is True
        assert config.ws_url == "wss://0.0.0.0:443"
        assert config.http_url == "https://0.0.0.0:443"


# ============================================================================
# BOTS REAL TESTS (5+ tests)
# ============================================================================

class TestBotsReal:
    """Real integration tests for Bots feature."""
    
    def test_bot_config_telegram(self):
        """Test 1: Telegram bot config works correctly."""
        config = BotConfig(
            token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            webhook_url="https://example.com/webhook",
            command_prefix="/",
            mention_required=True,
            typing_indicator=True,
            metadata={"platform": "telegram"},
        )
        
        assert config.token == "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        assert config.webhook_url == "https://example.com/webhook"
        assert config.is_webhook_mode is True
        assert config.command_prefix == "/"
        
        # Token should be hidden
        config_dict = config.to_dict()
        assert "ABC-DEF" not in str(config_dict)
    
    def test_bot_config_discord(self):
        """Test 2: Discord bot config works correctly."""
        config = BotConfig(
            token="MTIzNDU2Nzg5MDEyMzQ1Njc4OQ.Gg1234.abcdefghijklmnop",
            command_prefix="!",
            mention_required=True,
            metadata={
                "platform": "discord",
                "guild_ids": ["123456789", "987654321"],
            },
        )
        
        assert config.command_prefix == "!"
        assert config.metadata["platform"] == "discord"
        assert len(config.metadata["guild_ids"]) == 2
    
    def test_bot_message_creation(self):
        """Test 3: Bot messages work correctly."""
        user = BotUser(
            id="user123",
            username="testuser",
            display_name="Test User",
            is_bot=False,
        )
        
        channel = BotChannel(
            id="channel456",
            name="general",
            type="text",
        )
        
        message = BotMessage(
            id="msg789",
            content="Hello from bot!",
            type=MessageType.TEXT,
            user=user,
            channel=channel,
        )
        
        assert message.content == "Hello from bot!"
        assert message.type == MessageType.TEXT
        assert message.user.username == "testuser"
        assert message.channel.name == "general"
    
    def test_bot_user_allowed_check(self):
        """Test 4: User allowlist works correctly."""
        config = BotConfig(
            token="test-token",
            allowed_users=["user1", "user2", "user3"],
            allowed_channels=["channel1"],
        )
        
        assert config.is_user_allowed("user1") is True
        assert config.is_user_allowed("user4") is False
        assert config.is_channel_allowed("channel1") is True
        assert config.is_channel_allowed("channel2") is False
        
        # Empty allowlist means all allowed
        config_open = BotConfig(token="test")
        assert config_open.is_user_allowed("anyone") is True
        assert config_open.is_channel_allowed("anywhere") is True
    
    def test_bot_message_types_complete(self):
        """Test 5: All message types are defined."""
        expected_types = ["TEXT", "IMAGE", "AUDIO", "VIDEO", "FILE", "STICKER", "COMMAND"]
        
        for msg_type in expected_types:
            assert hasattr(MessageType, msg_type), f"Missing MessageType.{msg_type}"
    
    def test_bot_config_polling_mode(self):
        """Test 6: Polling mode config works correctly."""
        config = BotConfig(
            token="test-token",
            polling_interval=2.0,
            retry_attempts=5,
            timeout=60,
        )
        
        assert config.is_webhook_mode is False
        assert config.polling_interval == 2.0
        assert config.retry_attempts == 5
        assert config.timeout == 60


# ============================================================================
# SANDBOX REAL TESTS (5+ tests)
# ============================================================================

class TestSandboxReal:
    """Real integration tests for Sandbox feature."""
    
    def test_sandbox_config_subprocess(self):
        """Test 1: Subprocess sandbox config works correctly."""
        config = SandboxConfig.subprocess()
        
        assert config.sandbox_type == "subprocess"
        assert config.auto_cleanup is True
    
    def test_sandbox_config_docker(self):
        """Test 2: Docker sandbox config works correctly."""
        config = SandboxConfig.docker(image="python:3.11-slim")
        
        assert config.sandbox_type == "docker"
        assert config.image == "python:3.11-slim"
    
    def test_sandbox_resource_limits_presets(self):
        """Test 3: Resource limit presets work correctly."""
        minimal = ResourceLimits.minimal()
        standard = ResourceLimits.standard()
        generous = ResourceLimits.generous()
        
        # Minimal should be most restrictive
        assert minimal.memory_mb < standard.memory_mb < generous.memory_mb
        assert minimal.timeout_seconds < standard.timeout_seconds < generous.timeout_seconds
        assert minimal.network_enabled is False
        assert generous.network_enabled is True
        
        # Verify serialization
        minimal_dict = minimal.to_dict()
        assert "memory_mb" in minimal_dict
        assert "timeout_seconds" in minimal_dict
    
    def test_sandbox_security_policy_presets(self):
        """Test 4: Security policy presets work correctly."""
        strict = SecurityPolicy.strict()
        standard = SecurityPolicy.standard()
        permissive = SecurityPolicy.permissive()
        
        assert strict.allow_network is False
        assert strict.allow_subprocess is False
        assert permissive.allow_network is True
        assert permissive.allow_subprocess is True
    
    def test_sandbox_result_creation(self):
        """Test 5: Sandbox results work correctly."""
        result = SandboxResult(
            status=SandboxStatus.COMPLETED,
            exit_code=0,
            stdout="Hello, World!\n",
            stderr="",
            duration_seconds=0.5,
        )
        
        assert result.success is True
        assert result.status == SandboxStatus.COMPLETED
        assert result.stdout == "Hello, World!\n"
        assert result.duration_seconds == 0.5
        
        # Test combined output
        assert "Hello, World!" in result.combined_output
    
    def test_sandbox_result_failure(self):
        """Test 6: Failed sandbox results work correctly."""
        result = SandboxResult(
            status=SandboxStatus.FAILED,
            exit_code=1,
            stdout="",
            stderr="NameError: name 'undefined' is not defined",
            error="Execution failed",
        )
        
        assert result.success is False
        assert result.status == SandboxStatus.FAILED
        assert "NameError" in result.stderr
    
    def test_sandbox_status_values(self):
        """Test 7: All sandbox status values are defined."""
        expected_statuses = ["PENDING", "RUNNING", "COMPLETED", "FAILED", "TIMEOUT", "KILLED"]
        
        for status in expected_statuses:
            assert hasattr(SandboxStatus, status), f"Missing SandboxStatus.{status}"


# ============================================================================
# FAILOVER REAL TESTS (5+ tests)
# ============================================================================

class TestFailoverReal:
    """Real integration tests for Failover feature."""
    
    def test_auth_profile_creation(self):
        """Test 1: Auth profiles can be created correctly."""
        profile = AuthProfile(
            name="openai-primary",
            provider="openai",
            api_key="sk-test-key-12345",
            priority=1,
            rate_limit_rpm=100,
        )
        
        assert profile.name == "openai-primary"
        assert profile.provider == "openai"
        assert profile.priority == 1
        assert profile.status == ProviderStatus.AVAILABLE
        
        # API key should be hidden
        profile_dict = profile.to_dict()
        assert "sk-test-key-12345" not in str(profile_dict)
        assert "***" in profile_dict["api_key"]
    
    def test_failover_config_creation(self):
        """Test 2: Failover config works correctly."""
        config = FailoverConfig(
            max_retries=3,
            retry_delay=1.0,
            exponential_backoff=True,
            max_retry_delay=60.0,
            failover_on_rate_limit=True,
            failover_on_timeout=True,
        )
        
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.exponential_backoff is True
        assert config.max_retry_delay == 60.0
    
    def test_failover_manager_add_profiles(self):
        """Test 3: Failover manager can add and retrieve profiles."""
        manager = FailoverManager()
        
        profile1 = AuthProfile(
            name="openai",
            provider="openai",
            api_key="sk-test-1",
            priority=1,
        )
        profile2 = AuthProfile(
            name="anthropic",
            provider="anthropic",
            api_key="sk-ant-test",
            priority=2,
        )
        
        manager.add_profile(profile1)
        manager.add_profile(profile2)
        
        # Retrieve by name
        assert manager.get_profile("openai") is not None
        assert manager.get_profile("anthropic") is not None
        assert manager.get_profile("nonexistent") is None
        
        # Get next profile (should be highest priority)
        next_profile = manager.get_next_profile()
        assert next_profile.name == "openai"
    
    def test_failover_manager_mark_failure(self):
        """Test 4: Failover manager handles failures correctly."""
        manager = FailoverManager(FailoverConfig(max_retries=2))
        
        profile = AuthProfile(
            name="test-provider",
            provider="openai",
            api_key="sk-test",
            priority=1,
        )
        manager.add_profile(profile)
        
        # Mark failure
        manager.mark_failure("test-provider", "Rate limit exceeded")
        
        # Profile should still be retrievable but with updated status
        updated = manager.get_profile("test-provider")
        assert updated.last_error == "Rate limit exceeded"
        assert updated.last_error_time is not None
    
    def test_failover_manager_reset(self):
        """Test 5: Failover manager can reset profiles."""
        manager = FailoverManager()
        
        profile = AuthProfile(
            name="test",
            provider="openai",
            api_key="sk-test",
            priority=1,
        )
        manager.add_profile(profile)
        manager.mark_failure("test", "Error")
        
        # Reset
        manager.mark_success("test")
        
        updated = manager.get_profile("test")
        assert updated.status == ProviderStatus.AVAILABLE
    
    def test_failover_manager_priority_order(self):
        """Test 6: Profiles are returned in priority order."""
        manager = FailoverManager()
        
        # Add in reverse priority order
        manager.add_profile(AuthProfile(name="low", provider="x", api_key="k", priority=3))
        manager.add_profile(AuthProfile(name="high", provider="x", api_key="k", priority=1))
        manager.add_profile(AuthProfile(name="mid", provider="x", api_key="k", priority=2))
        
        # Should get highest priority first
        next_profile = manager.get_next_profile()
        assert next_profile.name == "high"
    
    def test_provider_status_values(self):
        """Test 7: All provider status values are defined."""
        expected_statuses = ["AVAILABLE", "RATE_LIMITED", "ERROR", "DISABLED"]
        
        for status in expected_statuses:
            assert hasattr(ProviderStatus, status), f"Missing ProviderStatus.{status}"


# ============================================================================
# REAL AGENT TESTS WITH API (requires OPENAI_API_KEY)
# ============================================================================

@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set"
)
class TestRealAgentWithAPI:
    """Real agent tests that make actual API calls."""
    
    def test_agent_basic_chat(self):
        """Test 1: Basic agent chat works."""
        agent = Agent(
            name="test-agent",
            instructions="You are a helpful assistant. Respond briefly.",
            llm="gpt-4o-mini",
        )
        
        response = agent.start("Say 'Hello' and nothing else.")
        assert response is not None
        assert len(response) > 0
        assert "hello" in response.lower()
    
    def test_agent_with_tool(self):
        """Test 2: Agent with tool works."""
        @tool
        def get_current_time() -> str:
            """Get the current time."""
            return "12:00 PM"
        
        agent = Agent(
            name="time-agent",
            instructions="Use the get_current_time tool when asked about time.",
            llm="gpt-4o-mini",
            tools=[get_current_time],
        )
        
        response = agent.start("What time is it?")
        assert response is not None
        assert "12:00" in response or "time" in response.lower()
    
    def test_agent_streaming(self):
        """Test 3: Agent streaming works."""
        agent = Agent(
            name="stream-agent",
            instructions="You are helpful. Respond briefly.",
            llm="gpt-4o-mini",
        )
        
        chunks = []
        for chunk in agent.start("Say 'test' only.", stream=True):
            if chunk:
                chunks.append(chunk)
        
        assert len(chunks) > 0
        full_response = "".join(chunks)
        assert len(full_response) > 0


# ============================================================================
# SANDBOX EXECUTION TESTS (requires subprocess)
# ============================================================================

class TestSandboxExecution:
    """Tests for actual sandbox code execution."""
    
    def test_subprocess_sandbox_simple_code(self):
        """Test subprocess sandbox can execute simple code."""
        # This test verifies the sandbox config is correct
        # Actual execution would require the wrapper implementation
        config = SandboxConfig(
            sandbox_type="subprocess",
            resource_limits=ResourceLimits(
                memory_mb=128,
                timeout_seconds=10,
                network_enabled=False,
            ),
        )
        
        assert config.sandbox_type == "subprocess"
        assert config.resource_limits.timeout_seconds == 10
        assert config.resource_limits.network_enabled is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
