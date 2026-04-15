"""
PlatformClient — httpx-based SDK for agents to interact with the platform API.

Uses connection pooling via a single httpx.AsyncClient lifecycle.

Usage::

    async with PlatformClient("http://localhost:8000") as client:
        await client.register("agent@example.com", "password")
        workspaces = await client.list_workspaces()
        issue = await client.create_issue(
            workspace_id="ws-1",
            title="Fix bug",
            description="The thing is broken",
        )

    # Or without context manager (auto-creates client per request):
    client = PlatformClient("http://localhost:8000", token="jwt-token")
    workspaces = await client.list_workspaces()
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class PlatformClient:
    """Async HTTP client for the PraisonAI Platform API.

    Supports both context-manager (pooled) and standalone (per-request) usage.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        token: Optional[str] = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client: Optional[httpx.AsyncClient] = None
        self._owned_client = False

    async def __aenter__(self) -> "PlatformClient":
        self._client = httpx.AsyncClient()
        self._owned_client = True
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client and self._owned_client:
            await self._client.aclose()
            self._client = None
            self._owned_client = False

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """Central request method with connection pooling support."""
        url = f"{self._base_url}/api/v1{path}"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        if self._client and self._owned_client:
            resp = await self._client.request(
                method, url, json=json, params=params, headers=headers,
            )
        else:
            async with httpx.AsyncClient() as c:
                resp = await c.request(
                    method, url, json=json, params=params, headers=headers,
                )
        resp.raise_for_status()
        return resp

    # ── Auth ─────────────────────────────────────────────────────────────

    async def register(self, email: str, password: str, name: Optional[str] = None) -> Dict[str, Any]:
        resp = await self._request("POST", "/auth/register", json={
            "email": email, "password": password, "name": name,
        })
        data = resp.json()
        self._token = data["token"]
        return data

    async def login(self, email: str, password: str) -> Dict[str, Any]:
        resp = await self._request("POST", "/auth/login", json={
            "email": email, "password": password,
        })
        data = resp.json()
        self._token = data["token"]
        return data

    async def get_me(self) -> Dict[str, Any]:
        resp = await self._request("GET", "/auth/me")
        return resp.json()

    # ── Workspaces ───────────────────────────────────────────────────────

    async def create_workspace(self, name: str, slug: Optional[str] = None, description: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"name": name}
        if slug is not None:
            body["slug"] = slug
        if description is not None:
            body["description"] = description
        resp = await self._request("POST", "/workspaces/", json=body)
        return resp.json()

    async def list_workspaces(self) -> List[Dict[str, Any]]:
        resp = await self._request("GET", "/workspaces/")
        return resp.json()

    async def get_workspace(self, workspace_id: str) -> Dict[str, Any]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}")
        return resp.json()

    async def update_workspace(self, workspace_id: str, **fields: Any) -> Dict[str, Any]:
        resp = await self._request("PATCH", f"/workspaces/{workspace_id}", json=fields)
        return resp.json()

    async def delete_workspace(self, workspace_id: str) -> None:
        await self._request("DELETE", f"/workspaces/{workspace_id}")

    # ── Members ──────────────────────────────────────────────────────────

    async def add_member(self, workspace_id: str, user_id: str, role: str = "member") -> Dict[str, Any]:
        resp = await self._request("POST", f"/workspaces/{workspace_id}/members", json={
            "user_id": user_id, "role": role,
        })
        return resp.json()

    async def list_members(self, workspace_id: str) -> List[Dict[str, Any]]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/members")
        return resp.json()

    async def update_member_role(self, workspace_id: str, user_id: str, role: str) -> Dict[str, Any]:
        resp = await self._request("PATCH", f"/workspaces/{workspace_id}/members/{user_id}", json={
            "role": role,
        })
        return resp.json()

    async def remove_member(self, workspace_id: str, user_id: str) -> None:
        await self._request("DELETE", f"/workspaces/{workspace_id}/members/{user_id}")

    # ── Projects ─────────────────────────────────────────────────────────

    async def create_project(
        self, workspace_id: str, title: str, description: Optional[str] = None
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"title": title}
        if description is not None:
            body["description"] = description
        resp = await self._request("POST", f"/workspaces/{workspace_id}/projects/", json=body)
        return resp.json()

    async def list_projects(self, workspace_id: str) -> List[Dict[str, Any]]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/projects/")
        return resp.json()

    async def get_project(self, workspace_id: str, project_id: str) -> Dict[str, Any]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/projects/{project_id}")
        return resp.json()

    async def update_project(self, workspace_id: str, project_id: str, **fields: Any) -> Dict[str, Any]:
        resp = await self._request("PATCH", f"/workspaces/{workspace_id}/projects/{project_id}", json=fields)
        return resp.json()

    async def delete_project(self, workspace_id: str, project_id: str) -> None:
        await self._request("DELETE", f"/workspaces/{workspace_id}/projects/{project_id}")

    async def get_project_stats(self, workspace_id: str, project_id: str) -> Dict[str, Any]:
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
        parent_issue_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"title": title, "priority": priority}
        if description is not None:
            body["description"] = description
        if project_id is not None:
            body["project_id"] = project_id
        if assignee_type is not None:
            body["assignee_type"] = assignee_type
        if assignee_id is not None:
            body["assignee_id"] = assignee_id
        if parent_issue_id is not None:
            body["parent_issue_id"] = parent_issue_id
        resp = await self._request("POST", f"/workspaces/{workspace_id}/issues/", json=body)
        return resp.json()

    async def list_issues(
        self,
        workspace_id: str,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if status:
            params["status"] = status
        if project_id:
            params["project_id"] = project_id
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        resp = await self._request("GET", f"/workspaces/{workspace_id}/issues/", params=params)
        return resp.json()

    async def get_issue(self, workspace_id: str, issue_id: str) -> Dict[str, Any]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/issues/{issue_id}")
        return resp.json()

    async def update_issue(self, workspace_id: str, issue_id: str, **fields: Any) -> Dict[str, Any]:
        resp = await self._request("PATCH", f"/workspaces/{workspace_id}/issues/{issue_id}", json=fields)
        return resp.json()

    async def delete_issue(self, workspace_id: str, issue_id: str) -> None:
        await self._request("DELETE", f"/workspaces/{workspace_id}/issues/{issue_id}")

    # ── Comments ─────────────────────────────────────────────────────────

    async def add_comment(
        self, workspace_id: str, issue_id: str, content: str, parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"content": content}
        if parent_id is not None:
            body["parent_id"] = parent_id
        resp = await self._request("POST", f"/workspaces/{workspace_id}/issues/{issue_id}/comments", json=body)
        return resp.json()

    async def list_comments(self, workspace_id: str, issue_id: str) -> List[Dict[str, Any]]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/issues/{issue_id}/comments")
        return resp.json()

    # ── Agents ────────────────────────────────────────────────────────────

    async def create_agent(
        self,
        workspace_id: str,
        name: str,
        runtime_mode: str = "local",
        instructions: Optional[str] = None,
        max_concurrent_tasks: int = 1,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"name": name, "runtime_mode": runtime_mode, "max_concurrent_tasks": max_concurrent_tasks}
        if instructions is not None:
            body["instructions"] = instructions
        resp = await self._request("POST", f"/workspaces/{workspace_id}/agents/", json=body)
        return resp.json()

    async def list_agents(
        self,
        workspace_id: str,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if status:
            params["status"] = status
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        resp = await self._request("GET", f"/workspaces/{workspace_id}/agents/", params=params)
        return resp.json()

    async def get_agent(self, workspace_id: str, agent_id: str) -> Dict[str, Any]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/agents/{agent_id}")
        return resp.json()

    async def update_agent(self, workspace_id: str, agent_id: str, **fields: Any) -> Dict[str, Any]:
        resp = await self._request("PATCH", f"/workspaces/{workspace_id}/agents/{agent_id}", json=fields)
        return resp.json()

    async def delete_agent(self, workspace_id: str, agent_id: str) -> None:
        await self._request("DELETE", f"/workspaces/{workspace_id}/agents/{agent_id}")

    # ── Labels ───────────────────────────────────────────────────────────

    async def create_label(self, workspace_id: str, name: str, color: str = "#6B7280") -> Dict[str, Any]:
        resp = await self._request("POST", f"/workspaces/{workspace_id}/labels", json={
            "name": name, "color": color,
        })
        return resp.json()

    async def list_labels(self, workspace_id: str) -> List[Dict[str, Any]]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/labels")
        return resp.json()

    async def update_label(self, workspace_id: str, label_id: str, **fields: Any) -> Dict[str, Any]:
        resp = await self._request("PATCH", f"/workspaces/{workspace_id}/labels/{label_id}", json=fields)
        return resp.json()

    async def delete_label(self, workspace_id: str, label_id: str) -> None:
        await self._request("DELETE", f"/workspaces/{workspace_id}/labels/{label_id}")

    async def add_label_to_issue(self, workspace_id: str, issue_id: str, label_id: str) -> None:
        await self._request("POST", f"/workspaces/{workspace_id}/issues/{issue_id}/labels/{label_id}")

    async def remove_label_from_issue(self, workspace_id: str, issue_id: str, label_id: str) -> None:
        await self._request("DELETE", f"/workspaces/{workspace_id}/issues/{issue_id}/labels/{label_id}")

    async def list_issue_labels(self, workspace_id: str, issue_id: str) -> List[Dict[str, Any]]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/issues/{issue_id}/labels")
        return resp.json()

    # ── Dependencies ─────────────────────────────────────────────────────

    async def create_dependency(
        self, workspace_id: str, issue_id: str, depends_on_issue_id: str, dep_type: str = "blocks",
    ) -> Dict[str, Any]:
        resp = await self._request("POST", f"/workspaces/{workspace_id}/issues/{issue_id}/dependencies/", json={
            "depends_on_issue_id": depends_on_issue_id, "type": dep_type,
        })
        return resp.json()

    async def list_dependencies(self, workspace_id: str, issue_id: str) -> List[Dict[str, Any]]:
        resp = await self._request("GET", f"/workspaces/{workspace_id}/issues/{issue_id}/dependencies/")
        return resp.json()

    async def delete_dependency(self, workspace_id: str, issue_id: str, dep_id: str) -> None:
        await self._request("DELETE", f"/workspaces/{workspace_id}/issues/{issue_id}/dependencies/{dep_id}")

    # ── Activity ─────────────────────────────────────────────────────────

    async def list_workspace_activity(
        self, workspace_id: str, limit: Optional[int] = None, offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        resp = await self._request("GET", f"/workspaces/{workspace_id}/activity", params=params)
        return resp.json()

    async def list_issue_activity(
        self, workspace_id: str, issue_id: str, limit: Optional[int] = None, offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        resp = await self._request("GET", f"/workspaces/{workspace_id}/issues/{issue_id}/activity", params=params)
        return resp.json()
