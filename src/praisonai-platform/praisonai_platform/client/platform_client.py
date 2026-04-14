"""
PlatformClient — httpx-based SDK for agents to interact with the platform API.

Usage::

    client = PlatformClient("http://localhost:8000", token="jwt-token")
    workspaces = await client.list_workspaces()
    issue = await client.create_issue(
        workspace_id="ws-1",
        title="Fix bug",
        description="The thing is broken",
    )
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class PlatformClient:
    """Async HTTP client for the PraisonAI Platform API.
    
    Supports both context-managed (connection pooling) and standalone usage:
    
    # Context-managed (recommended)
    async with PlatformClient("http://localhost:8000") as client:
        workspaces = await client.list_workspaces()
    
    # Standalone (falls back to per-request clients)
    client = PlatformClient("http://localhost:8000")
    workspaces = await client.list_workspaces()
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        token: Optional[str] = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client: Optional[httpx.AsyncClient] = None

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self._base_url}/api/v1{path}"

    async def __aenter__(self) -> "PlatformClient":
        """Enter async context manager - creates pooled httpx.AsyncClient."""
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager - closes pooled client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """Central request method with connection pooling support."""
        url = self._url(path)
        headers = self._headers()
        
        if self._client:  # Context-managed: use pooled client
            resp = await self._client.request(method, url, json=json, params=params, headers=headers)
        else:  # Standalone: use per-request client
            async with httpx.AsyncClient() as c:
                resp = await c.request(method, url, json=json, params=params, headers=headers)
        
        resp.raise_for_status()
        return resp

    # ── Auth ─────────────────────────────────────────────────────────────

    async def register(self, email: str, password: str, name: Optional[str] = None) -> Dict[str, Any]:
        resp = await self._request(
            "POST",
            "/auth/register",
            json={"email": email, "password": password, "name": name},
        )
        data = resp.json()
        self._token = data["token"]
        return data

    async def login(self, email: str, password: str) -> Dict[str, Any]:
        resp = await self._request(
            "POST",
            "/auth/login",
            json={"email": email, "password": password},
        )
        data = resp.json()
        self._token = data["token"]
        return data

    async def get_me(self) -> Dict[str, Any]:
        """Get current user information."""
        resp = await self._request("GET", "/auth/me")
        return resp.json()

    # ── Workspaces ───────────────────────────────────────────────────────

    async def create_workspace(self, name: str, slug: Optional[str] = None) -> Dict[str, Any]:
        resp = await self._request(
            "POST",
            "/workspaces/",
            json={"name": name, "slug": slug},
        )
        return resp.json()

    async def list_workspaces(self) -> List[Dict[str, Any]]:
        resp = await self._request("GET", "/workspaces/")
        return resp.json()

    async def get_workspace(self, workspace_id: str) -> Dict[str, Any]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}")
        return resp.json()

    async def update_workspace(self, workspace_id: str, **fields: Any) -> Dict[str, Any]:
        """Update workspace fields."""
        resp = await self._request("PATCH", f"/workspaces/{workspace_id}", json=fields)
        return resp.json()

    async def delete_workspace(self, workspace_id: str) -> Dict[str, Any]:
        """Delete a workspace."""
        resp = await self._request("DELETE", f"/workspaces/{workspace_id}")
        return resp.json()

    # ── Members ──────────────────────────────────────────────────────────

    async def add_member(self, workspace_id: str, user_id: str, role: str = "member") -> Dict[str, Any]:
        resp = await self._request(
            "POST",
            f"/workspaces/{workspace_id}/members",
            json={"user_id": user_id, "role": role},
        )
        return resp.json()

    async def list_members(self, workspace_id: str) -> List[Dict[str, Any]]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/members")
        return resp.json()

    async def update_member_role(self, workspace_id: str, member_id: str, role: str) -> Dict[str, Any]:
        """Update a member's role in the workspace."""
        resp = await self._request(
            "PATCH",
            f"/workspaces/{workspace_id}/members/{member_id}",
            json={"role": role},
        )
        return resp.json()

    async def remove_member(self, workspace_id: str, member_id: str) -> Dict[str, Any]:
        """Remove a member from the workspace."""
        resp = await self._request("DELETE", f"/workspaces/{workspace_id}/members/{member_id}")
        return resp.json()

    # ── Projects ─────────────────────────────────────────────────────────

    async def create_project(
        self, workspace_id: str, title: str, description: Optional[str] = None
    ) -> Dict[str, Any]:
        resp = await self._request(
            "POST",
            f"/workspaces/{workspace_id}/projects/",
            json={"title": title, "description": description},
        )
        return resp.json()

    async def list_projects(self, workspace_id: str) -> List[Dict[str, Any]]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/projects/")
        return resp.json()

    async def get_project(self, workspace_id: str, project_id: str) -> Dict[str, Any]:
        """Get a specific project."""
        resp = await self._request("GET", f"/workspaces/{workspace_id}/projects/{project_id}")
        return resp.json()

    async def update_project(self, workspace_id: str, project_id: str, **fields: Any) -> Dict[str, Any]:
        """Update project fields."""
        resp = await self._request(
            "PATCH",
            f"/workspaces/{workspace_id}/projects/{project_id}",
            json=fields,
        )
        return resp.json()

    async def delete_project(self, workspace_id: str, project_id: str) -> Dict[str, Any]:
        """Delete a project."""
        resp = await self._request("DELETE", f"/workspaces/{workspace_id}/projects/{project_id}")
        return resp.json()

    async def get_project_stats(self, workspace_id: str, project_id: str) -> Dict[str, Any]:
        """Get project statistics."""
        resp = await self._request("GET", f"/workspaces/{workspace_id}/projects/{project_id}/stats")
        return resp.json()

    # ── Issues ───────────────────────────────────────────────────────────

    async def create_issue(
        self,
        workspace_id: str,
        title: str,
        description: Optional[str] = None,
        project_id: Optional[str] = None,
        priority: str = "none",
        assignee_type: Optional[str] = None,
        assignee_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"title": title, "priority": priority}
        if description:
            body["description"] = description
        if project_id:
            body["project_id"] = project_id
        if assignee_type:
            body["assignee_type"] = assignee_type
        if assignee_id:
            body["assignee_id"] = assignee_id
        resp = await self._request(
            "POST",
            f"/workspaces/{workspace_id}/issues/",
            json=body,
        )
        return resp.json()

    async def list_issues(
        self,
        workspace_id: str,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, str] = {}
        if status:
            params["status"] = status
        if project_id:
            params["project_id"] = project_id
        resp = await self._request(
            "GET",
            f"/workspaces/{workspace_id}/issues/",
            params=params,
        )
        return resp.json()

    async def get_issue(self, workspace_id: str, issue_id: str) -> Dict[str, Any]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/issues/{issue_id}")
        return resp.json()

    async def update_issue(
        self, workspace_id: str, issue_id: str, **fields: Any
    ) -> Dict[str, Any]:
        resp = await self._request(
            "PATCH",
            f"/workspaces/{workspace_id}/issues/{issue_id}",
            json=fields,
        )
        return resp.json()

    async def delete_issue(self, workspace_id: str, issue_id: str) -> Dict[str, Any]:
        """Delete an issue."""
        resp = await self._request("DELETE", f"/workspaces/{workspace_id}/issues/{issue_id}")
        return resp.json()

    # ── Comments ─────────────────────────────────────────────────────────

    async def add_comment(
        self, workspace_id: str, issue_id: str, content: str
    ) -> Dict[str, Any]:
        resp = await self._request(
            "POST",
            f"/workspaces/{workspace_id}/issues/{issue_id}/comments",
            json={"content": content},
        )
        return resp.json()

    async def list_comments(
        self, workspace_id: str, issue_id: str
    ) -> List[Dict[str, Any]]:
        resp = await self._request(
            "GET",
            f"/workspaces/{workspace_id}/issues/{issue_id}/comments",
        )
        return resp.json()

    # ── Agents ────────────────────────────────────────────────────────────

    async def create_agent(
        self,
        workspace_id: str,
        name: str,
        runtime_mode: str = "local",
        instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"name": name, "runtime_mode": runtime_mode}
        if instructions:
            body["instructions"] = instructions
        resp = await self._request(
            "POST",
            f"/workspaces/{workspace_id}/agents/",
            json=body,
        )
        return resp.json()

    async def list_agents(self, workspace_id: str) -> List[Dict[str, Any]]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/agents/")
        return resp.json()

    async def get_agent(self, workspace_id: str, agent_id: str) -> Dict[str, Any]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/agents/{agent_id}")
        return resp.json()

    async def update_agent(
        self, workspace_id: str, agent_id: str, **fields: Any
    ) -> Dict[str, Any]:
        resp = await self._request(
            "PATCH",
            f"/workspaces/{workspace_id}/agents/{agent_id}",
            json=fields,
        )
        return resp.json()

    async def delete_agent(self, workspace_id: str, agent_id: str) -> Dict[str, Any]:
        """Delete an agent."""
        resp = await self._request("DELETE", f"/workspaces/{workspace_id}/agents/{agent_id}")
        return resp.json()

    # ── Labels ───────────────────────────────────────────────────────────

    async def create_label(
        self, workspace_id: str, name: str, color: str = "#000000", description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a label."""
        body = {"name": name, "color": color}
        if description:
            body["description"] = description
        resp = await self._request("POST", f"/workspaces/{workspace_id}/labels/", json=body)
        return resp.json()

    async def list_labels(self, workspace_id: str) -> List[Dict[str, Any]]:
        """List all labels in the workspace."""
        resp = await self._request("GET", f"/workspaces/{workspace_id}/labels/")
        return resp.json()

    async def update_label(self, workspace_id: str, label_id: str, **fields: Any) -> Dict[str, Any]:
        """Update label fields."""
        resp = await self._request(
            "PATCH",
            f"/workspaces/{workspace_id}/labels/{label_id}",
            json=fields,
        )
        return resp.json()

    async def delete_label(self, workspace_id: str, label_id: str) -> Dict[str, Any]:
        """Delete a label."""
        resp = await self._request("DELETE", f"/workspaces/{workspace_id}/labels/{label_id}")
        return resp.json()

    async def add_label_to_issue(
        self, workspace_id: str, issue_id: str, label_id: str
    ) -> Dict[str, Any]:
        """Add a label to an issue."""
        resp = await self._request(
            "POST",
            f"/workspaces/{workspace_id}/issues/{issue_id}/labels/{label_id}",
        )
        return resp.json()

    async def remove_label_from_issue(
        self, workspace_id: str, issue_id: str, label_id: str
    ) -> Dict[str, Any]:
        """Remove a label from an issue."""
        resp = await self._request(
            "DELETE",
            f"/workspaces/{workspace_id}/issues/{issue_id}/labels/{label_id}",
        )
        return resp.json()

    async def list_issue_labels(
        self, workspace_id: str, issue_id: str
    ) -> List[Dict[str, Any]]:
        """List all labels on an issue."""
        resp = await self._request(
            "GET",
            f"/workspaces/{workspace_id}/issues/{issue_id}/labels",
        )
        return resp.json()

    # ── Dependencies ─────────────────────────────────────────────────────

    async def create_dependency(
        self, workspace_id: str, issue_id: str, depends_on_issue_id: str
    ) -> Dict[str, Any]:
        """Create an issue dependency."""
        resp = await self._request(
            "POST",
            f"/workspaces/{workspace_id}/issues/{issue_id}/dependencies",
            json={"depends_on_issue_id": depends_on_issue_id},
        )
        return resp.json()

    async def list_dependencies(
        self, workspace_id: str, issue_id: str
    ) -> List[Dict[str, Any]]:
        """List issue dependencies."""
        resp = await self._request(
            "GET",
            f"/workspaces/{workspace_id}/issues/{issue_id}/dependencies",
        )
        return resp.json()

    async def delete_dependency(
        self, workspace_id: str, issue_id: str, dependency_id: str
    ) -> Dict[str, Any]:
        """Delete an issue dependency."""
        resp = await self._request(
            "DELETE",
            f"/workspaces/{workspace_id}/issues/{issue_id}/dependencies/{dependency_id}",
        )
        return resp.json()

    # ── Activity ─────────────────────────────────────────────────────────

    async def list_workspace_activity(
        self, workspace_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List recent activity in the workspace."""
        resp = await self._request(
            "GET",
            f"/workspaces/{workspace_id}/activity",
            params={"limit": str(limit)},
        )
        return resp.json()

    async def list_issue_activity(
        self, workspace_id: str, issue_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List recent activity on an issue."""
        resp = await self._request(
            "GET",
            f"/workspaces/{workspace_id}/issues/{issue_id}/activity",
            params={"limit": str(limit)},
        )
        return resp.json()
