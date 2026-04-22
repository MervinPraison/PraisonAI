"""
Integration tests for UI pairing approval.

Tests the end-to-end flow: pending request → banner shown → approve action → PairingStore.is_approved()==True
"""

import pytest
import asyncio
import tempfile
import os
from unittest.mock import Mock, AsyncMock, patch

from praisonai.gateway.pairing import PairingStore
from praisonai.ui._pairing import (
    get_pending_pairings,
    approve_pairing,
    refresh_pending_banner,
    setup_pairing_banner,
)


@pytest.fixture
def temp_pairing_store():
    """Create a temporary PairingStore for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        store = PairingStore(store_dir=temp_dir)
        yield store


@pytest.fixture
def mock_gateway_server(temp_pairing_store):
    """Mock gateway server with actual PairingStore."""
    server = Mock()
    server.pairing_store = temp_pairing_store
    return server


@pytest.fixture
def mock_chainlit_user_admin():
    """Mock Chainlit user session with admin role."""
    with patch("chainlit.user_session") as mock_session:
        mock_user = Mock()
        mock_user.metadata = {"role": "admin"}
        mock_session.get.return_value = mock_user
        yield mock_session


@pytest.fixture
def mock_chainlit_user_regular():
    """Mock Chainlit user session with regular role."""
    with patch("chainlit.user_session") as mock_session:
        mock_user = Mock()
        mock_user.metadata = {"role": "user"}
        mock_session.get.return_value = mock_user
        yield mock_session


@pytest.fixture
def mock_chainlit_message():
    """Mock Chainlit Message class."""
    with patch("chainlit.Message") as mock_message_class:
        mock_message = Mock()
        mock_message.send = AsyncMock()
        mock_message_class.return_value = mock_message
        yield mock_message_class


@pytest.fixture
def mock_chainlit_action():
    """Mock Chainlit Action class."""
    with patch("chainlit.Action") as mock_action_class:
        yield mock_action_class


class TestGetPendingPairings:
    """Test the get_pending_pairings function."""

    @patch("praisonai.ui._pairing.GATEWAY_TOKEN", "test-token")
    @patch("aiohttp.ClientSession")
    async def test_get_pending_success(self, mock_session):
        """Test successful retrieval of pending pairings."""
        # Mock successful HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "pending": [
                {
                    "channel": "telegram",
                    "code": "ABCD1234", 
                    "user_id": "ABCD1234",
                    "user_name": "User ABCD1234",
                    "age_seconds": 30
                }
            ]
        })
        
        mock_session_instance = AsyncMock()
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session_instance.get = AsyncMock()
        mock_session_instance.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_instance.get.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_instance
        
        result = await get_pending_pairings()
        
        assert len(result) == 1
        assert result[0]["channel"] == "telegram"
        assert result[0]["code"] == "ABCD1234"

    @patch("praisonai.ui._pairing.GATEWAY_TOKEN", "")
    async def test_get_pending_no_token(self, caplog):
        """Test get_pending_pairings with no token."""
        result = await get_pending_pairings()
        
        assert result == []
        assert "No GATEWAY_AUTH_TOKEN set" in caplog.text

    @patch("praisonai.ui._pairing.GATEWAY_TOKEN", "test-token")
    @patch("aiohttp.ClientSession")
    async def test_get_pending_http_error(self, mock_session):
        """Test get_pending_pairings with HTTP error."""
        # Mock HTTP error response
        mock_response = AsyncMock()
        mock_response.status = 401
        
        mock_session_instance = AsyncMock()
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session_instance.get = AsyncMock()
        mock_session_instance.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_instance.get.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_instance
        
        result = await get_pending_pairings()
        
        assert result == []


class TestApprovePairing:
    """Test the approve_pairing function."""

    @patch("praisonai.ui._pairing.GATEWAY_TOKEN", "test-token")
    @patch("aiohttp.ClientSession")
    async def test_approve_success(self, mock_session):
        """Test successful pairing approval."""
        # Mock successful HTTP response
        mock_response = AsyncMock()
        mock_response.status = 200
        
        mock_session_instance = AsyncMock()
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session_instance.post = AsyncMock()
        mock_session_instance.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_instance.post.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_instance
        
        result = await approve_pairing("telegram", "ABCD1234")
        
        assert result is True

    @patch("praisonai.ui._pairing.GATEWAY_TOKEN", "")
    async def test_approve_no_token(self):
        """Test approve_pairing with no token."""
        result = await approve_pairing("telegram", "ABCD1234")
        
        assert result is False

    @patch("praisonai.ui._pairing.GATEWAY_TOKEN", "test-token")
    @patch("aiohttp.ClientSession")
    async def test_approve_http_error(self, mock_session):
        """Test approve_pairing with HTTP error."""
        # Mock HTTP error response
        mock_response = AsyncMock()
        mock_response.status = 404
        
        mock_session_instance = AsyncMock()
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session_instance.__aexit__ = AsyncMock(return_value=None)
        mock_session_instance.post = AsyncMock()
        mock_session_instance.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_instance.post.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session.return_value = mock_session_instance
        
        result = await approve_pairing("telegram", "ABCD1234")
        
        assert result is False


class TestRefreshPendingBanner:
    """Test the refresh_pending_banner function."""

    async def test_banner_not_shown_for_non_admin(
        self, 
        mock_chainlit_user_regular,
        mock_chainlit_message
    ):
        """Test that banner is not shown for non-admin users."""
        await refresh_pending_banner()
        
        # Message should not be sent for non-admin
        mock_chainlit_message.assert_not_called()

    async def test_banner_not_shown_with_no_pending(
        self,
        mock_chainlit_user_admin,
        mock_chainlit_message
    ):
        """Test that banner is not shown when no pending requests."""
        with patch("praisonai.ui._pairing.get_pending_pairings", return_value=[]):
            await refresh_pending_banner()
        
        # Message should not be sent when no pending
        mock_chainlit_message.assert_not_called()

    async def test_banner_shown_for_admin_with_pending(
        self,
        mock_chainlit_user_admin,
        mock_chainlit_message,
        mock_chainlit_action
    ):
        """Test that banner is shown for admin with pending requests."""
        mock_pending = [
            {
                "channel": "telegram",
                "code": "ABCD1234",
                "user_name": "User ABCD1234",
                "age_seconds": 30
            }
        ]
        
        with patch("praisonai.ui._pairing.get_pending_pairings", return_value=mock_pending):
            await refresh_pending_banner()
        
        # Message should be created and sent
        mock_chainlit_message.assert_called_once()
        mock_message_call = mock_chainlit_message.call_args
        
        # Check message content
        assert "🔔" in mock_message_call[1]["content"]
        assert "1 pending pairing request(s)" in mock_message_call[1]["content"]
        
        # Verify action contract
        actions = mock_message_call[1]["actions"]
        assert len(actions) == 2  # Should have both approve and deny actions
        
        # Check approve action
        approve_action = actions[0]
        assert approve_action.name == "approve_pairing"
        assert approve_action.value == "telegram:ABCD1234"
        assert "✅ Approve" in approve_action.label
        
        # Check deny action  
        deny_action = actions[1]
        assert deny_action.name == "deny_pairing"
        assert deny_action.value == "telegram:ABCD1234"
        assert "❌ Deny" in deny_action.label

    async def test_banner_multiple_pending(
        self,
        mock_chainlit_user_admin,
        mock_chainlit_message,
        mock_chainlit_action
    ):
        """Test banner with multiple pending requests."""
        mock_pending = [
            {
                "channel": "telegram",
                "code": "ABCD1234",
                "user_name": "User ABCD1234",
                "age_seconds": 30
            },
            {
                "channel": "slack", 
                "code": "EFGH5678",
                "user_name": "User EFGH5678",
                "age_seconds": 120
            }
        ]
        
        with patch("praisonai.ui._pairing.get_pending_pairings", return_value=mock_pending):
            await refresh_pending_banner()
        
        # Message should be created with 2 actions
        mock_chainlit_message.assert_called_once()
        mock_message_call = mock_chainlit_message.call_args
        
        assert "2 pending pairing request(s)" in mock_message_call[1]["content"]
        
        # Should have 4 actions total (2 pending × 2 actions each)
        actions = mock_message_call[1]["actions"] 
        assert len(actions) == 4
        
        # Verify first pairing actions
        assert actions[0].name == "approve_pairing"
        assert actions[0].value == "telegram:ABCD1234"
        assert actions[1].name == "deny_pairing" 
        assert actions[1].value == "telegram:ABCD1234"
        
        # Verify second pairing actions
        assert actions[2].name == "approve_pairing"
        assert actions[2].value == "slack:EFGH5678"
        assert actions[3].name == "deny_pairing"
        assert actions[3].value == "slack:EFGH5678"


class TestIntegrationFlow:
    """Test the complete integration flow."""

    async def test_end_to_end_pairing_flow(self, temp_pairing_store):
        """Test complete flow: generate code → pending request → approve → is_paired."""
        # 1. Generate a pairing code
        code = temp_pairing_store.generate_code(channel_type="telegram")
        assert len(code) == 8
        
        # 2. Verify it shows up in pending list
        pending = temp_pairing_store.list_pending()
        assert len(pending) == 1
        assert pending[0]["code"] == code
        assert pending[0]["channel"] == "telegram"
        
        # 3. Approve the pairing
        success = temp_pairing_store.approve("telegram", code, user_id="12345")
        assert success is True
        
        # 4. Verify it's now paired
        assert temp_pairing_store.is_paired("12345", "telegram") is True
        
        # 5. Verify no longer in pending
        pending_after = temp_pairing_store.list_pending()
        assert len(pending_after) == 0

    async def test_invalid_code_approval_flow(self, temp_pairing_store):
        """Test approval flow with invalid code."""
        # Try to approve non-existent code
        success = temp_pairing_store.approve("telegram", "INVALID", user_id="12345")
        assert success is False
        
        # Verify not paired
        assert temp_pairing_store.is_paired("12345", "telegram") is False

    async def test_expired_code_flow(self, temp_pairing_store):
        """Test that expired codes are cleaned up."""
        # Generate a code with very short TTL
        store_short_ttl = PairingStore(
            store_dir=temp_pairing_store._dir,
            code_ttl=0.1  # 100ms TTL
        )
        
        code = store_short_ttl.generate_code(channel_type="telegram")
        
        # Wait for expiration
        await asyncio.sleep(0.2)
        
        # Try to approve expired code
        success = store_short_ttl.approve("telegram", code, user_id="12345") 
        assert success is False
        
        # Verify not paired
        assert store_short_ttl.is_paired("12345", "telegram") is False