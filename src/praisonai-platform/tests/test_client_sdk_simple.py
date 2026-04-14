"""
Simple integration tests for the PlatformClient SDK.

This test suite verifies that the SDK methods are callable and can make HTTP requests.
Since the database module is not available, we use mock endpoints.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from praisonai_platform.client.platform_client import PlatformClient


@pytest_asyncio.fixture
async def app():
    """Create a basic FastAPI app with mock endpoints."""
    app = FastAPI()
    
    # Mock authentication endpoints
    @app.post("/api/v1/auth/register")
    async def register():
        return {
            "token": "test-token-12345", 
            "user": {"id": "user-1", "email": "test@example.com", "name": "Test User"}
        }
    
    @app.post("/api/v1/auth/login")
    async def login():
        return {
            "token": "test-token-12345",
            "user": {"id": "user-1", "email": "test@example.com", "name": "Test User"}
        }
    
    @app.get("/api/v1/auth/me")
    async def get_me():
        return {"id": "user-1", "email": "test@example.com", "name": "Test User"}
    
    # Mock workspace endpoints
    @app.post("/api/v1/workspaces/")
    async def create_workspace():
        return {"id": "ws-1", "name": "Test Workspace", "slug": "test-ws"}
    
    @app.get("/api/v1/workspaces/")
    async def list_workspaces():
        return [{"id": "ws-1", "name": "Test Workspace", "slug": "test-ws"}]
    
    @app.get("/api/v1/workspaces/{workspace_id}")
    async def get_workspace(workspace_id: str):
        return {"id": workspace_id, "name": "Test Workspace", "slug": "test-ws"}
    
    # Mock project endpoints
    @app.post("/api/v1/workspaces/{workspace_id}/projects/")
    async def create_project(workspace_id: str):
        return {"id": "project-1", "title": "Test Project", "workspace_id": workspace_id}
    
    @app.get("/api/v1/workspaces/{workspace_id}/projects/")
    async def list_projects(workspace_id: str):
        return [{"id": "project-1", "title": "Test Project", "workspace_id": workspace_id}]
    
    # Mock issue endpoints
    @app.post("/api/v1/workspaces/{workspace_id}/issues/")
    async def create_issue(workspace_id: str):
        return {"id": "issue-1", "title": "Test Issue", "workspace_id": workspace_id}
    
    @app.get("/api/v1/workspaces/{workspace_id}/issues/")
    async def list_issues(workspace_id: str):
        return [{"id": "issue-1", "title": "Test Issue", "workspace_id": workspace_id}]
    
    # Mock agent endpoints
    @app.post("/api/v1/workspaces/{workspace_id}/agents/")
    async def create_agent(workspace_id: str):
        return {"id": "agent-1", "name": "Test Agent", "workspace_id": workspace_id}
    
    @app.get("/api/v1/workspaces/{workspace_id}/agents/")
    async def list_agents(workspace_id: str):
        return [{"id": "agent-1", "name": "Test Agent", "workspace_id": workspace_id}]
    
    # Mock label endpoints
    @app.post("/api/v1/workspaces/{workspace_id}/labels")
    async def create_label(workspace_id: str):
        return {"id": "label-1", "name": "Bug", "color": "#ff0000", "workspace_id": workspace_id}
    
    @app.get("/api/v1/workspaces/{workspace_id}/labels")
    async def list_labels(workspace_id: str):
        return [{"id": "label-1", "name": "Bug", "color": "#ff0000", "workspace_id": workspace_id}]
    
    yield app


@pytest_asyncio.fixture
async def httpx_client(app):
    """httpx async client for the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def client_sdk(httpx_client, monkeypatch):
    """PlatformClient that uses the test httpx client."""
    # Mock httpx.AsyncClient to use our test client
    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        
        async def __aenter__(self):
            return httpx_client
        
        async def __aexit__(self, *args):
            pass
    
    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)
    
    client = PlatformClient(base_url="http://test")
    yield client


class TestPlatformClientBasic:
    """Basic tests to verify SDK methods work."""
    
    @pytest.mark.asyncio
    async def test_auth_methods(self, client_sdk):
        """Test authentication methods."""
        # Test register
        result = await client_sdk.register("test@example.com", "password", "Test User")
        assert result["token"] == "test-token-12345"
        assert result["user"]["email"] == "test@example.com"
        
        # Test login
        result = await client_sdk.login("test@example.com", "password")
        assert result["token"] == "test-token-12345"
        
        # Test get_me
        result = await client_sdk.get_me()
        assert result["email"] == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_workspace_methods(self, client_sdk):
        """Test workspace methods."""
        # Register first to get token
        await client_sdk.register("test@example.com", "password", "Test User")
        
        # Test create workspace
        workspace = await client_sdk.create_workspace("Test Workspace", "test-ws")
        assert workspace["name"] == "Test Workspace"
        assert workspace["slug"] == "test-ws"
        
        # Test list workspaces
        workspaces = await client_sdk.list_workspaces()
        assert len(workspaces) == 1
        
        # Test get workspace
        workspace = await client_sdk.get_workspace("ws-1")
        assert workspace["id"] == "ws-1"
    
    @pytest.mark.asyncio
    async def test_project_methods(self, client_sdk):
        """Test project methods."""
        # Register first
        await client_sdk.register("test@example.com", "password", "Test User")
        
        # Test create project
        project = await client_sdk.create_project("ws-1", "Test Project", "A test project")
        assert project["title"] == "Test Project"
        
        # Test list projects
        projects = await client_sdk.list_projects("ws-1")
        assert len(projects) == 1
    
    @pytest.mark.asyncio
    async def test_issue_methods(self, client_sdk):
        """Test issue methods."""
        # Register first
        await client_sdk.register("test@example.com", "password", "Test User")
        
        # Test create issue
        issue = await client_sdk.create_issue("ws-1", "Test Issue", "A test issue")
        assert issue["title"] == "Test Issue"
        
        # Test list issues
        issues = await client_sdk.list_issues("ws-1")
        assert len(issues) == 1
    
    @pytest.mark.asyncio
    async def test_agent_methods(self, client_sdk):
        """Test agent methods."""
        # Register first
        await client_sdk.register("test@example.com", "password", "Test User")
        
        # Test create agent
        agent = await client_sdk.create_agent("ws-1", "Test Agent", "local", "Test instructions")
        assert agent["name"] == "Test Agent"
        
        # Test list agents
        agents = await client_sdk.list_agents("ws-1")
        assert len(agents) == 1
    
    @pytest.mark.asyncio
    async def test_label_methods(self, client_sdk):
        """Test label methods."""
        # Register first
        await client_sdk.register("test@example.com", "password", "Test User")
        
        # Test create label
        label = await client_sdk.create_label("ws-1", "Bug", "#ff0000")
        assert label["name"] == "Bug"
        assert label["color"] == "#ff0000"
        
        # Test list labels
        labels = await client_sdk.list_labels("ws-1")
        assert len(labels) == 1


class TestPlatformClientComprehensive:
    """Test that all required SDK methods exist."""
    
    @pytest.mark.asyncio
    async def test_all_methods_exist(self, client_sdk):
        """Verify all required methods exist on the client."""
        # Auth methods
        assert hasattr(client_sdk, 'register')
        assert hasattr(client_sdk, 'login')
        assert hasattr(client_sdk, 'get_me')
        
        # Workspace methods
        assert hasattr(client_sdk, 'create_workspace')
        assert hasattr(client_sdk, 'list_workspaces')
        assert hasattr(client_sdk, 'get_workspace')
        assert hasattr(client_sdk, 'update_workspace')
        assert hasattr(client_sdk, 'delete_workspace')
        
        # Member methods
        assert hasattr(client_sdk, 'add_member')
        assert hasattr(client_sdk, 'list_members')
        assert hasattr(client_sdk, 'update_member_role')
        assert hasattr(client_sdk, 'remove_member')
        
        # Project methods
        assert hasattr(client_sdk, 'create_project')
        assert hasattr(client_sdk, 'list_projects')
        assert hasattr(client_sdk, 'get_project')
        assert hasattr(client_sdk, 'update_project')
        assert hasattr(client_sdk, 'delete_project')
        assert hasattr(client_sdk, 'get_project_stats')
        
        # Issue methods
        assert hasattr(client_sdk, 'create_issue')
        assert hasattr(client_sdk, 'list_issues')
        assert hasattr(client_sdk, 'get_issue')
        assert hasattr(client_sdk, 'update_issue')
        assert hasattr(client_sdk, 'delete_issue')
        
        # Comment methods
        assert hasattr(client_sdk, 'add_comment')
        assert hasattr(client_sdk, 'list_comments')
        
        # Agent methods
        assert hasattr(client_sdk, 'create_agent')
        assert hasattr(client_sdk, 'list_agents')
        assert hasattr(client_sdk, 'get_agent')
        assert hasattr(client_sdk, 'update_agent')
        assert hasattr(client_sdk, 'delete_agent')
        
        # Label methods
        assert hasattr(client_sdk, 'create_label')
        assert hasattr(client_sdk, 'list_labels')
        assert hasattr(client_sdk, 'update_label')
        assert hasattr(client_sdk, 'delete_label')
        assert hasattr(client_sdk, 'add_label_to_issue')
        assert hasattr(client_sdk, 'remove_label_from_issue')
        assert hasattr(client_sdk, 'list_issue_labels')
        
        # Dependency methods
        assert hasattr(client_sdk, 'create_dependency')
        assert hasattr(client_sdk, 'list_dependencies')
        assert hasattr(client_sdk, 'delete_dependency')
        
        # Activity methods
        assert hasattr(client_sdk, 'list_workspace_activity')
        assert hasattr(client_sdk, 'list_issue_activity')
        
        print("✅ All required SDK methods exist on PlatformClient")


if __name__ == "__main__":
    print("Running basic SDK integration tests...")
    pytest.main([__file__, "-v"])