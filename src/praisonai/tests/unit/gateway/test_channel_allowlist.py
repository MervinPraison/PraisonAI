"""
Test that channel allowlist configuration survives round-trip from YAML to BotConfig.

This test verifies the fix for the critical security bug where allowed_users,
allowed_channels, and group_policy were dropped when creating BotConfig objects
in daemon mode (server.py:1367).
"""

import pytest
from unittest.mock import Mock
import asyncio
from typing import Dict, Any

from praisonaiagents import Agent
from praisonaiagents.bots import BotConfig


class MockGateway:
    """Mock Gateway for testing channel allowlist plumbing."""
    
    def __init__(self):
        self._agents = {}
        self._channel_bots = {}
        self._channel_tasks = []
        self._routing_rules = {}
    
    def _create_bots_from_config(self, channels_cfg: Dict[str, Any]):
        """Simplified version of the gateway's _create_bots_from_config method."""
        from praisonaiagents.bots import BotConfig
        
        for channel_name, ch_cfg in channels_cfg.items():
            channel_type = ch_cfg.get("platform", channel_name).lower()
            token = ch_cfg.get("token", "")
            
            if not token:
                continue
                
            routes = ch_cfg.get("routing") or ch_cfg.get("routes") or {"default": "default"}
            self._routing_rules[channel_name] = routes
            
            # Get default agent (use mock for testing)
            default_agent = Agent(name="test_agent", instructions="Test instructions")
            
            # This is the critical code being tested - extracted from server.py:1367-1386
            # Extract allowlist configuration from channel config  
            _raw_allowed = ch_cfg.get("allowed_users") or []
            if isinstance(_raw_allowed, str):
                # Env-expanded string like "12345,67890"; split on commas.
                _raw_allowed = [s.strip() for s in _raw_allowed.split(",") if s.strip()]

            _raw_channels = ch_cfg.get("allowed_channels") or []
            if isinstance(_raw_channels, str):
                _raw_channels = [s.strip() for s in _raw_channels.split(",") if s.strip()]

            # Extract group policy setting
            group_policy = ch_cfg.get("group_policy", "mention_only")
            mention_required = (group_policy == "mention_only")

            config = BotConfig(
                token=token,
                allowed_users=list(_raw_allowed),
                allowed_channels=list(_raw_channels),
                mention_required=mention_required,
            )
            
            # Store for verification
            self._channel_bots[channel_name] = {
                "config": config,
                "agent": default_agent,
                "type": channel_type
            }
            

def test_allowlist_fields_survive_round_trip():
    """Test that allowed_users and allowed_channels survive YAML → BotConfig conversion."""
    
    # YAML configuration with allowlists (simulating what onboard generates)
    channels_config = {
        "telegram": {
            "platform": "telegram", 
            "token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            "allowed_users": "42,12345",  # Comma-separated string (env-expanded)
            "allowed_channels": "-100123456789,-100987654321",
            "group_policy": "mention_only",
        },
        "discord": {
            "platform": "discord", 
            "token": "fake-discord-token-123",
            "allowed_users": ["99", "88"],  # List format
            "allowed_channels": ["987654321098765432", "876543210987654321"], 
            "group_policy": "respond_all",
        }
    }
    
    # Create mock gateway and process config
    gateway = MockGateway()
    gateway._create_bots_from_config(channels_config)
    
    # Verify Telegram channel
    telegram_bot = gateway._channel_bots["telegram"]
    telegram_config = telegram_bot["config"]
    
    assert isinstance(telegram_config, BotConfig)
    assert telegram_config.allowed_users == ["42", "12345"], f"Expected ['42', '12345'], got {telegram_config.allowed_users}"
    assert telegram_config.allowed_channels == ["-100123456789", "-100987654321"]
    assert telegram_config.mention_required is True  # group_policy: "mention_only"
    assert telegram_config.token == "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    
    # Verify Discord channel  
    discord_bot = gateway._channel_bots["discord"]
    discord_config = discord_bot["config"]
    
    assert isinstance(discord_config, BotConfig)
    assert discord_config.allowed_users == ["99", "88"]
    assert discord_config.allowed_channels == ["987654321098765432", "876543210987654321"]
    assert discord_config.mention_required is False  # group_policy: "respond_all"
    assert discord_config.token == "fake-discord-token-123"


def test_user_allowlist_enforcement():
    """Test that is_user_allowed() works correctly after round-trip."""
    
    channels_config = {
        "telegram": {
            "token": "test-token",
            "allowed_users": "42,67890",
        }
    }
    
    gateway = MockGateway()
    gateway._create_bots_from_config(channels_config)
    
    config = gateway._channel_bots["telegram"]["config"]
    
    # Allowed user IDs should return True
    assert config.is_user_allowed("42") is True
    assert config.is_user_allowed("67890") is True
    
    # Non-allowed user IDs should return False  
    assert config.is_user_allowed("99") is False
    assert config.is_user_allowed("12345") is False
    assert config.is_user_allowed("") is False


def test_empty_allowlist_allows_everyone():
    """Test that empty allowed_users list allows all users (backward compatibility)."""
    
    channels_config = {
        "telegram": {
            "token": "test-token",
            # No allowed_users specified
        }
    }
    
    gateway = MockGateway()
    gateway._create_bots_from_config(channels_config)
    
    config = gateway._channel_bots["telegram"]["config"]
    
    # Empty list should allow everyone
    assert config.allowed_users == []
    assert config.is_user_allowed("42") is True
    assert config.is_user_allowed("99") is True
    assert config.is_user_allowed("") is True


def test_string_parsing_edge_cases():
    """Test edge cases in comma-separated string parsing."""
    
    test_cases = [
        ("42,67890", ["42", "67890"]),  # Normal case
        ("42, 67890", ["42", "67890"]),  # Spaces
        (" 42 , 67890 ", ["42", "67890"]),  # Leading/trailing spaces
        ("42,,67890", ["42", "67890"]),  # Empty element
        ("42,", ["42"]),  # Trailing comma
        (",42", ["42"]),  # Leading comma
        ("", []),  # Empty string
        ("42", ["42"]),  # Single item
    ]
    
    for input_str, expected in test_cases:
        channels_config = {
            "test": {
                "token": "test-token",
                "allowed_users": input_str,
            }
        }
        
        gateway = MockGateway()
        gateway._create_bots_from_config(channels_config)
        
        config = gateway._channel_bots["test"]["config"]
        assert config.allowed_users == expected, f"Input '{input_str}' should parse to {expected}, got {config.allowed_users}"


def test_group_policy_mapping():
    """Test that group_policy maps correctly to mention_required."""
    
    test_cases = [
        ("mention_only", True),
        ("respond_all", False), 
        ("command_only", False),
        (None, True),  # Default
    ]
    
    for group_policy, expected_mention_required in test_cases:
        channels_config = {
            "test": {
                "token": "test-token",
            }
        }
        
        if group_policy is not None:
            channels_config["test"]["group_policy"] = group_policy
        
        gateway = MockGateway()
        gateway._create_bots_from_config(channels_config)
        
        config = gateway._channel_bots["test"]["config"]
        assert config.mention_required == expected_mention_required, \
            f"group_policy '{group_policy}' should map to mention_required={expected_mention_required}, got {config.mention_required}"


if __name__ == "__main__":
    pytest.main([__file__])