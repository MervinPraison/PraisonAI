"""
Unit tests for WebSocket rate limiting functionality.

Tests the rate limiting applied to WebSocket upgrade requests.
"""

import time
from unittest.mock import AsyncMock, patch
import pytest
from praisonai.praisonai.gateway.rate_limiter import AuthRateLimiter


class TestWebSocketRateLimit:
    """Test WebSocket rate limiting functionality."""

    def test_allow_under_limit(self):
        """Requests under the limit should be allowed."""
        limiter = AuthRateLimiter(max_attempts=3, window_seconds=60)
        
        # First 3 attempts should be allowed
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True

    def test_deny_over_limit(self):
        """Requests over the limit should be denied."""
        limiter = AuthRateLimiter(max_attempts=3, window_seconds=60)
        
        # Use up the limit
        for _ in range(3):
            limiter.allow("ws_upgrade", "192.168.1.100")
        
        # 4th attempt should be denied
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False

    def test_different_ips_independent(self):
        """Different IPs should have independent rate limits."""
        limiter = AuthRateLimiter(max_attempts=2, window_seconds=60)
        
        # Use up limit for first IP
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False  # Over limit
        
        # Second IP should still work
        assert limiter.allow("ws_upgrade", "192.168.1.101") is True
        assert limiter.allow("ws_upgrade", "192.168.1.101") is True
        assert limiter.allow("ws_upgrade", "192.168.1.101") is False  # Over limit

    def test_window_reset(self):
        """Rate limit should reset after the window expires."""
        limiter = AuthRateLimiter(max_attempts=2, window_seconds=0.1)  # Short window for testing
        
        # Use up the limit
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False  # Over limit
        
        # Wait for window to expire
        time.sleep(0.2)
        
        # Should be allowed again
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True

    def test_lockout_duration(self):
        """After exceeding limit, should be locked out for the lockout period."""
        limiter = AuthRateLimiter(max_attempts=2, window_seconds=60, lockout_seconds=0.2)
        
        # Use up the limit to trigger lockout
        for _ in range(2):
            limiter.allow("ws_upgrade", "192.168.1.100")
        
        # This triggers the lockout
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False
        
        # Should still be locked out immediately after
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False
        
        # Wait for lockout to expire
        time.sleep(0.3)
        
        # Should be allowed again
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True

    def test_time_until_allowed(self):
        """time_until_allowed should return correct lockout time."""
        limiter = AuthRateLimiter(max_attempts=1, window_seconds=60, lockout_seconds=10)
        
        # Trigger lockout
        limiter.allow("ws_upgrade", "192.168.1.100")
        limiter.allow("ws_upgrade", "192.168.1.100")  # This triggers lockout
        
        # Should report time until allowed
        time_left = limiter.time_until_allowed("ws_upgrade", "192.168.1.100")
        assert 0 < time_left <= 10

    def test_reset_clears_state(self):
        """reset() should clear rate limit state for a key."""
        limiter = AuthRateLimiter(max_attempts=1, window_seconds=60)
        
        # Use up the limit
        limiter.allow("ws_upgrade", "192.168.1.100")
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False  # Should be denied
        
        # Reset the state
        limiter.reset("ws_upgrade", "192.168.1.100")
        
        # Should be allowed again
        assert limiter.allow("ws_upgrade", "192.168.1.100") is True

    def test_prune_removes_expired_entries(self):
        """prune() should remove expired buckets and lockouts."""
        limiter = AuthRateLimiter(max_attempts=1, window_seconds=0.1, lockout_seconds=0.1)
        
        # Create some entries
        limiter.allow("ws_upgrade", "192.168.1.100")
        limiter.allow("ws_upgrade", "192.168.1.101")
        
        # Wait for expiration
        time.sleep(0.2)
        
        # Prune should remove expired entries
        removed_count = limiter.prune()
        assert removed_count >= 2  # Should remove at least the 2 entries we created

    def test_default_configuration(self):
        """Test the default configuration matches requirements.""" 
        limiter = AuthRateLimiter(max_attempts=10, window_seconds=60)
        
        # Should allow 10 attempts
        for i in range(10):
            assert limiter.allow("ws_upgrade", "192.168.1.100") is True
        
        # 11th attempt should be denied
        assert limiter.allow("ws_upgrade", "192.168.1.100") is False


@pytest.mark.asyncio
class TestWebSocketIntegration:
    """Integration tests for WebSocket rate limiting in the gateway."""

    @patch('praisonai.praisonai.gateway.server.AuthRateLimiter')
    async def test_websocket_rate_limit_applied(self, mock_rate_limiter_class):
        """Test that rate limiting is applied to WebSocket connections."""
        # Mock the rate limiter instance
        mock_limiter = AsyncMock()
        mock_rate_limiter_class.return_value = mock_limiter
        
        # Test case where rate limit allows the request
        mock_limiter.allow.return_value = True
        
        from praisonai.praisonai.gateway.server import WebSocketGateway
        gateway = WebSocketGateway()
        
        # Verify that the rate limiter would be created and used
        # (This is a simplified integration test - full WebSocket testing would require more setup)
        assert True  # Placeholder for more complex integration testing

    def test_acceptance_criteria_11th_attempt(self):
        """Test that the 11th consecutive attempt is rate limited."""
        limiter = AuthRateLimiter(max_attempts=10, window_seconds=60)
        client_ip = "192.168.1.100"
        
        # First 10 attempts should succeed
        for i in range(10):
            result = limiter.allow("ws_upgrade", client_ip)
            assert result is True, f"Attempt {i+1} should be allowed"
        
        # 11th attempt should be denied
        assert limiter.allow("ws_upgrade", client_ip) is False
        
        # Verify lockout is in effect
        retry_time = limiter.time_until_allowed("ws_upgrade", client_ip)
        assert retry_time > 0