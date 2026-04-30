"""
Integration tests for the web-UI side of the pairing flow.

Tests the Chainlit banner → click Approve → PairingStore updates flow
via HTTP API integration testing.
"""

import pytest
import tempfile
import shutil
import httpx
from unittest.mock import patch
from typing import Dict, Any

from praisonai.gateway.pairing import PairingStore
from praisonaiagents.bus import EventBus, get_default_bus


@pytest.mark.integration
class TestPairingUIApproval:
    """Test the web-UI side of pairing approval via HTTP API."""
    
    def setup_method(self):
        """Set up test environment."""
        self._pairing_dir = tempfile.mkdtemp(prefix="test_pairing_ui_")
        self.pairing_store = PairingStore(store_dir=self._pairing_dir)
        self.event_bus = get_default_bus()
        self.received_events = []
        
        # Subscribe to pairing events
        def capture_event(event):
            self.received_events.append({"type": event.type, "data": event.data})
        
        self.event_bus.subscribe(capture_event, ["pairing_approved"])

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self._pairing_dir, ignore_errors=True)
        self.received_events.clear()
    
    @pytest.mark.asyncio
    async def test_pairing_ui_approval_via_http_api(self):
        """Test pairing approval through HTTP API (simulating Chainlit UI)."""
        
        # 1. Seed a pending pairing entry
        code = self.pairing_store.generate_code(
            channel_type="ui",
            channel_id="test-session-123"
        )
        
        # Verify pending state
        pending = self.pairing_store.list_pending("ui")
        assert len(pending) == 1
        assert pending[0]["code"] == code
        assert not self.pairing_store.is_paired("test-session-123", "ui")
        
        # 2. Mock the FastAPI gateway pairing routes
        from praisonai.gateway.pairing_routes import create_pairing_routes
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.testclient import TestClient
        
        # Mock auth checker that simulates admin session
        def mock_auth_admin(request):
            return None  # No error = authenticated admin
        
        routes_dict = create_pairing_routes(self.pairing_store, mock_auth_admin)
        app = Starlette(routes=[
            Route('/api/pairing/pending', routes_dict['pending'], methods=['GET']),
            Route('/api/pairing/approve', routes_dict['approve'], methods=['POST']),
            Route('/api/pairing/revoke', routes_dict['revoke'], methods=['POST']),
        ])
        
        # Use TestClient for synchronous testing
        with TestClient(app) as client:
            # 3. Call POST /api/pairing/approve with admin session
            response = client.post(
                "/api/pairing/approve",
                json={
                    "code": code,
                    "channel": "ui"
                }
            )
            
            # 4. Verify response is 200
            assert response.status_code == 200
            data = response.json()
            assert data["approved"] is True
        
        # 5. Verify PairingStore was updated
        assert self.pairing_store.is_paired("test-session-123", "ui") is True
        
        # 6. Verify no more pending codes for this channel
        pending_after = self.pairing_store.list_pending("ui")
        assert len(pending_after) == 0
        
    @pytest.mark.asyncio
    async def test_pairing_ui_approval_non_admin_returns_403(self):
        """Test that non-admin users cannot approve pairing requests."""
        
        # Seed a pending pairing entry
        code = self.pairing_store.generate_code(
            channel_type="ui", 
            channel_id="test-session-456"
        )
        
        from praisonai.gateway.pairing_routes import create_pairing_routes
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.testclient import TestClient
        from starlette.responses import JSONResponse
        
        # Mock auth checker that simulates non-admin (returns 403)
        def mock_auth_non_admin(request):
            return JSONResponse({"error": "Forbidden"}, status_code=403)
        
        routes_dict = create_pairing_routes(self.pairing_store, mock_auth_non_admin)
        app = Starlette(routes=[
            Route('/api/pairing/approve', routes_dict['approve'], methods=['POST']),
        ])
        
        with TestClient(app) as client:
            response = client.post(
                "/api/pairing/approve",
                json={
                    "code": code,
                    "channel": "ui"
                }
            )
            
            # Should return 403 Forbidden
            assert response.status_code == 403
        
        # Verify pairing did NOT happen
        assert self.pairing_store.is_paired("test-session-456", "ui") is False
        
    @pytest.mark.asyncio
    async def test_pairing_ui_approval_invalid_code_returns_400(self):
        """Test that invalid pairing codes return 400."""
        
        from praisonai.gateway.pairing_routes import create_pairing_routes
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.testclient import TestClient
        
        # Mock auth checker that simulates admin session
        def mock_auth_admin(request):
            return None  # No error = authenticated admin
        
        routes_dict = create_pairing_routes(self.pairing_store, mock_auth_admin)
        app = Starlette(routes=[
            Route('/api/pairing/approve', routes_dict['approve'], methods=['POST']),
        ])
        
        with TestClient(app) as client:
            response = client.post(
                "/api/pairing/approve",
                json={
                    "code": "invalid-code-123",
                    "channel": "ui"
                }
            )
            
            # Should return 404 Not Found for invalid code
            assert response.status_code == 404
            data = response.json()
            assert "error" in data
        
        # Verify no pairing occurred
        assert self.pairing_store.is_paired("test-session-789", "ui") is False
    
    @pytest.mark.asyncio
    async def test_pairing_ui_list_pending_requests(self):
        """Test listing pending pairing requests via HTTP API."""
        
        # Seed multiple pending entries
        code1 = self.pairing_store.generate_code("ui", channel_id="session-1")
        code2 = self.pairing_store.generate_code("slack", channel_id="channel-2") 
        code3 = self.pairing_store.generate_code("ui", channel_id="session-3")
        
        from praisonai.gateway.pairing_routes import create_pairing_routes
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.testclient import TestClient
        
        # Mock auth checker that simulates admin session
        def mock_auth_admin(request):
            return None  # No error = authenticated admin
        
        routes_dict = create_pairing_routes(self.pairing_store, mock_auth_admin)
        app = Starlette(routes=[
            Route('/api/pairing/pending', routes_dict['pending'], methods=['GET']),
        ])
        
        with TestClient(app) as client:
            # Get all pending requests
            response = client.get("/api/pairing/pending")
            assert response.status_code == 200
            
            data = response.json()
            pending_list = data["pending"]
            assert len(pending_list) == 3
            
            # Verify all our codes are present
            codes = [item["code"] for item in pending_list]
            assert code1 in codes
            assert code2 in codes  
            assert code3 in codes
            
            # Filter by channel type (Note: current implementation doesn't support query params)
            # This test may need adjustment based on actual implementation
                    
    @pytest.mark.asyncio 
    async def test_pairing_ui_approval_emits_event(self):
        """Test that pairing approval emits event on EventBus."""
        
        # Seed pending entry
        code = self.pairing_store.generate_code("ui", channel_id="event-test-session")
        
        from praisonai.gateway.pairing_routes import create_pairing_routes
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.testclient import TestClient
        
        # Mock auth checker that simulates admin session
        def mock_auth_admin(request):
            return None  # No error = authenticated admin
        
        routes_dict = create_pairing_routes(self.pairing_store, mock_auth_admin)
        app = Starlette(routes=[
            Route('/api/pairing/approve', routes_dict['approve'], methods=['POST']),
        ])
        
        with TestClient(app) as client:
            response = client.post(
                "/api/pairing/approve",
                json={
                    "code": code,
                    "channel": "ui"
                }
            )
            
            assert response.status_code == 200
        
        # Verify event was emitted (events would be captured by our setup_method subscriber)
        # Check that the pairing_approved event was published
        assert len(self.received_events) >= 1
        event_found = any(
            event["type"] == "pairing_approved" and 
            "event-test-session" in str(event["data"])
            for event in self.received_events
        )
        assert event_found, f"pairing_approved event not found in {self.received_events}"
        
        # Also verify the pairing succeeded in the store
        assert self.pairing_store.is_paired("event-test-session", "ui") is True


if __name__ == "__main__":
    # Run the integration test
    import asyncio
    
    test = TestPairingUIApproval()
    test.setup_method()
    
    async def run_test():
        await test.test_pairing_ui_approval_via_http_api()
    
    asyncio.run(run_test())