"""
Unit tests for pairing routes.

Tests the REST API endpoints for pairing management.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from starlette.responses import JSONResponse
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
import json

from praisonai.gateway.pairing import PairingStore
from praisonai.gateway.pairing_routes import create_pairing_routes


@pytest.fixture
def mock_pairing_store():
    """Create a mock PairingStore for testing."""
    store = Mock(spec=PairingStore)
    store.list_pending.return_value = []
    store.approve.return_value = True
    store.revoke.return_value = True
    return store


@pytest.fixture
def mock_auth_checker():
    """Create a mock auth checker that always passes."""
    def auth_checker(request):
        return None  # No auth error
    return auth_checker


@pytest.fixture
def mock_auth_checker_fails():
    """Create a mock auth checker that always fails."""
    def auth_checker(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return auth_checker


@pytest.fixture
def pairing_routes(mock_pairing_store, mock_auth_checker):
    """Create pairing routes with mocked dependencies."""
    return create_pairing_routes(mock_pairing_store, mock_auth_checker)


@pytest.fixture
def pairing_routes_auth_fails(mock_pairing_store, mock_auth_checker_fails):
    """Create pairing routes with auth that fails."""
    return create_pairing_routes(mock_pairing_store, mock_auth_checker_fails)


@pytest.fixture
def test_app(pairing_routes):
    """Create a test Starlette app with pairing routes."""
    app = Starlette(routes=[
        Route("/api/pairing/pending", pairing_routes["pending"], methods=["GET"]),
        Route("/api/pairing/approve", pairing_routes["approve"], methods=["POST"]),
        Route("/api/pairing/revoke", pairing_routes["revoke"], methods=["POST"]),
    ])
    return app


@pytest.fixture
def test_app_auth_fails(pairing_routes_auth_fails):
    """Create a test app with failing auth."""
    app = Starlette(routes=[
        Route("/api/pairing/pending", pairing_routes_auth_fails["pending"], methods=["GET"]),
        Route("/api/pairing/approve", pairing_routes_auth_fails["approve"], methods=["POST"]),
        Route("/api/pairing/revoke", pairing_routes_auth_fails["revoke"], methods=["POST"]),
    ])
    return app


class TestPairingPendingEndpoint:
    """Test the /api/pairing/pending endpoint."""

    def test_pending_empty_list(self, test_app, mock_pairing_store):
        """Test pending endpoint returns empty list when no pending requests."""
        mock_pairing_store.list_pending.return_value = []
        
        with TestClient(test_app) as client:
            response = client.get("/api/pairing/pending")
        
        assert response.status_code == 200
        data = response.json()
        assert data == {"pending": []}
        mock_pairing_store.list_pending.assert_called_once()

    def test_pending_with_requests(self, test_app, mock_pairing_store):
        """Test pending endpoint returns pending requests."""
        mock_requests = [
            {
                "channel": "telegram",
                "code": "ABCD1234",
                "user_id": "ABCD1234",
                "user_name": "User ABCD1234",
                "age_seconds": 30,
            },
            {
                "channel": "slack",
                "code": "EFGH5678",
                "user_id": "EFGH5678",
                "user_name": "User EFGH5678",
                "age_seconds": 120,
            }
        ]
        mock_pairing_store.list_pending.return_value = mock_requests
        
        with TestClient(test_app) as client:
            response = client.get("/api/pairing/pending")
        
        assert response.status_code == 200
        data = response.json()
        assert data == {"pending": mock_requests}
        mock_pairing_store.list_pending.assert_called_once()

    def test_pending_auth_failure(self, test_app_auth_fails):
        """Test pending endpoint fails with auth error."""
        with TestClient(test_app_auth_fails) as client:
            response = client.get("/api/pairing/pending")
        
        assert response.status_code == 401
        data = response.json()
        assert data == {"error": "Unauthorized"}


class TestPairingApproveEndpoint:
    """Test the /api/pairing/approve endpoint."""

    def test_approve_success(self, test_app, mock_pairing_store):
        """Test successful pairing approval."""
        mock_pairing_store.approve.return_value = True
        
        with TestClient(test_app) as client:
            response = client.post(
                "/api/pairing/approve",
                json={"channel": "telegram", "code": "ABCD1234"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "approved": True,
            "channel": "telegram",
            "code": "ABCD1234"
        }
        mock_pairing_store.approve.assert_called_once_with("telegram", "ABCD1234")

    def test_approve_invalid_code(self, test_app, mock_pairing_store):
        """Test approval with invalid/expired code."""
        mock_pairing_store.approve.return_value = False
        
        with TestClient(test_app) as client:
            response = client.post(
                "/api/pairing/approve",
                json={"channel": "telegram", "code": "INVALID"}
            )
        
        assert response.status_code == 404
        data = response.json()
        assert data == {"error": "Invalid or expired code"}
        mock_pairing_store.approve.assert_called_once_with("telegram", "INVALID")

    def test_approve_missing_channel(self, test_app):
        """Test approval with missing channel."""
        with TestClient(test_app) as client:
            response = client.post(
                "/api/pairing/approve",
                json={"code": "ABCD1234"}
            )
        
        assert response.status_code == 400
        data = response.json()
        assert data == {"error": "Both 'channel' and 'code' are required"}

    def test_approve_missing_code(self, test_app):
        """Test approval with missing code."""
        with TestClient(test_app) as client:
            response = client.post(
                "/api/pairing/approve",
                json={"channel": "telegram"}
            )
        
        assert response.status_code == 400
        data = response.json()
        assert data == {"error": "Both 'channel' and 'code' are required"}

    def test_approve_invalid_json(self, test_app):
        """Test approval with invalid JSON body."""
        with TestClient(test_app) as client:
            response = client.post(
                "/api/pairing/approve",
                data="invalid json"
            )
        
        assert response.status_code == 400
        data = response.json()
        assert data == {"error": "Invalid JSON"}

    def test_approve_auth_failure(self, test_app_auth_fails):
        """Test approval endpoint fails with auth error."""
        with TestClient(test_app_auth_fails) as client:
            response = client.post(
                "/api/pairing/approve",
                json={"channel": "telegram", "code": "ABCD1234"}
            )
        
        assert response.status_code == 401
        data = response.json()
        assert data == {"error": "Unauthorized"}


class TestPairingRevokeEndpoint:
    """Test the /api/pairing/revoke endpoint."""

    def test_revoke_success(self, test_app, mock_pairing_store):
        """Test successful pairing revocation."""
        mock_pairing_store.revoke.return_value = True
        
        with TestClient(test_app) as client:
            response = client.post(
                "/api/pairing/revoke",
                json={"channel": "telegram", "user_id": "12345"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "revoked": True,
            "channel": "telegram",
            "user_id": "12345"
        }
        mock_pairing_store.revoke.assert_called_once_with("12345", "telegram")

    def test_revoke_not_found(self, test_app, mock_pairing_store):
        """Test revocation when channel not found."""
        mock_pairing_store.revoke.return_value = False
        
        with TestClient(test_app) as client:
            response = client.post(
                "/api/pairing/revoke",
                json={"channel": "telegram", "user_id": "99999"}
            )
        
        assert response.status_code == 404
        data = response.json()
        assert data == {"error": "Channel not found or not paired"}
        mock_pairing_store.revoke.assert_called_once_with("99999", "telegram")

    def test_revoke_missing_channel(self, test_app):
        """Test revocation with missing channel."""
        with TestClient(test_app) as client:
            response = client.post(
                "/api/pairing/revoke",
                json={"user_id": "12345"}
            )
        
        assert response.status_code == 400
        data = response.json()
        assert data == {"error": "Both 'channel' and 'user_id' are required"}

    def test_revoke_missing_user_id(self, test_app):
        """Test revocation with missing user_id."""
        with TestClient(test_app) as client:
            response = client.post(
                "/api/pairing/revoke",
                json={"channel": "telegram"}
            )
        
        assert response.status_code == 400
        data = response.json()
        assert data == {"error": "Both 'channel' and 'user_id' are required"}

    def test_revoke_invalid_json(self, test_app):
        """Test revocation with invalid JSON body."""
        with TestClient(test_app) as client:
            response = client.post(
                "/api/pairing/revoke",
                data="invalid json"
            )
        
        assert response.status_code == 400
        data = response.json()
        assert data == {"error": "Invalid JSON"}

    def test_revoke_auth_failure(self, test_app_auth_fails):
        """Test revoke endpoint fails with auth error."""
        with TestClient(test_app_auth_fails) as client:
            response = client.post(
                "/api/pairing/revoke",
                json={"channel": "telegram", "user_id": "12345"}
            )
        
        assert response.status_code == 401
        data = response.json()
        assert data == {"error": "Unauthorized"}


class TestCreatePairingRoutes:
    """Test the create_pairing_routes function."""

    def test_returns_all_routes(self, mock_pairing_store, mock_auth_checker):
        """Test that create_pairing_routes returns all expected routes."""
        routes = create_pairing_routes(mock_pairing_store, mock_auth_checker)
        
        assert "pending" in routes
        assert "approve" in routes
        assert "revoke" in routes
        assert len(routes) == 3

    def test_routes_are_callable(self, mock_pairing_store, mock_auth_checker):
        """Test that all returned routes are callable."""
        routes = create_pairing_routes(mock_pairing_store, mock_auth_checker)
        
        for route_name, route_func in routes.items():
            assert callable(route_func), f"Route {route_name} is not callable"