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
    """Async HTTP client for the PraisonAI Platform API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        token: Optional[str] = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._token = token

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self._base_url}/api/v1{path}"

    # ── Auth ─────────────────────────────────────────────────────────────

    async def register(self, email: str, password: str, name: Optional[str] = None) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                self._url("/auth/register"),
                json={"email": email, "password": password, "name": name},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["token"]
            return data

    async def login(self, email: str, password: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                self._url("/auth/login"),
                json={"email": email, "password": password},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["token"]
            return data

    # ── Workspaces ───────────────────────────────────────────────────────

    async def create_workspace(self, name: str, slug: Optional[str] = None) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                self._url("/workspaces/"),
                json={"name": name, "slug": slug},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def list_workspaces(self) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(self._url("/workspaces/"), headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def get_workspace(self, workspace_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    # ── Members ──────────────────────────────────────────────────────────

    async def add_member(self, workspace_id: str, user_id: str, role: str = "member") -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                self._url(f"/workspaces/{workspace_id}/members"),
                json={"user_id": user_id, "role": role},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def list_members(self, workspace_id: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/members"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    # ── Projects ─────────────────────────────────────────────────────────

    async def create_project(
        self, workspace_id: str, title: str, description: Optional[str] = None
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                self._url(f"/workspaces/{workspace_id}/projects/"),
                json={"title": title, "description": description},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def list_projects(self, workspace_id: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/projects/"),
                headers=self._headers(),
            )
            resp.raise_for_status()
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
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                self._url(f"/workspaces/{workspace_id}/issues/"),
                json=body,
                headers=self._headers(),
            )
            resp.raise_for_status()
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
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/issues/"),
                params=params,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_issue(self, workspace_id: str, issue_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/issues/{issue_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def update_issue(
        self, workspace_id: str, issue_id: str, **fields: Any
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.patch(
                self._url(f"/workspaces/{workspace_id}/issues/{issue_id}"),
                json=fields,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    # ── Comments ─────────────────────────────────────────────────────────

    async def add_comment(
        self, workspace_id: str, issue_id: str, content: str
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                self._url(f"/workspaces/{workspace_id}/issues/{issue_id}/comments"),
                json={"content": content},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def list_comments(
        self, workspace_id: str, issue_id: str
    ) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/issues/{issue_id}/comments"),
                headers=self._headers(),
            )
            resp.raise_for_status()
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
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                self._url(f"/workspaces/{workspace_id}/agents/"),
                json=body,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def list_agents(self, workspace_id: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/agents/"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_agent(self, workspace_id: str, agent_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/agents/{agent_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def update_agent(
        self, workspace_id: str, agent_id: str, **fields: Any
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.patch(
                self._url(f"/workspaces/{workspace_id}/agents/{agent_id}"),
                json=fields,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_agent(self, workspace_id: str, agent_id: str) -> None:
        async with httpx.AsyncClient() as c:
            resp = await c.delete(
                self._url(f"/workspaces/{workspace_id}/agents/{agent_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()

    # ── Member Operations ────────────────────────────────────────────────

    async def update_member_role(self, workspace_id: str, user_id: str, role: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.patch(
                self._url(f"/workspaces/{workspace_id}/members/{user_id}"),
                json={"role": role},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def remove_member(self, workspace_id: str, user_id: str) -> None:
        async with httpx.AsyncClient() as c:
            resp = await c.delete(
                self._url(f"/workspaces/{workspace_id}/members/{user_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()

    # ── User Profile ─────────────────────────────────────────────────────

    async def get_me(self) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(self._url("/auth/me"), headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    # ── Project Operations ───────────────────────────────────────────────

    async def get_project(self, workspace_id: str, project_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/projects/{project_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def update_project(
        self, workspace_id: str, project_id: str, **fields: Any
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.patch(
                self._url(f"/workspaces/{workspace_id}/projects/{project_id}"),
                json=fields,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_project(self, workspace_id: str, project_id: str) -> None:
        async with httpx.AsyncClient() as c:
            resp = await c.delete(
                self._url(f"/workspaces/{workspace_id}/projects/{project_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()

    async def get_project_stats(self, workspace_id: str, project_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/projects/{project_id}/stats"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    # ── Issue Operations ─────────────────────────────────────────────────

    async def delete_issue(self, workspace_id: str, issue_id: str) -> None:
        async with httpx.AsyncClient() as c:
            resp = await c.delete(
                self._url(f"/workspaces/{workspace_id}/issues/{issue_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()

    # ── Workspace Operations ─────────────────────────────────────────────

    async def update_workspace(self, workspace_id: str, **fields: Any) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.patch(
                self._url(f"/workspaces/{workspace_id}"),
                json=fields,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_workspace(self, workspace_id: str) -> None:
        async with httpx.AsyncClient() as c:
            resp = await c.delete(
                self._url(f"/workspaces/{workspace_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()

    # ── Labels ───────────────────────────────────────────────────────────

    async def create_label(
        self, workspace_id: str, name: str, color: str = "#007bff"
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                self._url(f"/workspaces/{workspace_id}/labels"),
                json={"name": name, "color": color},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def list_labels(self, workspace_id: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/labels"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def update_label(
        self, workspace_id: str, label_id: str, name: str = None, color: str = None
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if color is not None:
            body["color"] = color
        async with httpx.AsyncClient() as c:
            resp = await c.patch(
                self._url(f"/workspaces/{workspace_id}/labels/{label_id}"),
                json=body,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_label(self, workspace_id: str, label_id: str) -> None:
        async with httpx.AsyncClient() as c:
            resp = await c.delete(
                self._url(f"/workspaces/{workspace_id}/labels/{label_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()

    async def add_label_to_issue(
        self, workspace_id: str, issue_id: str, label_id: str
    ) -> None:
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                self._url(f"/workspaces/{workspace_id}/issues/{issue_id}/labels/{label_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()

    async def remove_label_from_issue(
        self, workspace_id: str, issue_id: str, label_id: str
    ) -> None:
        async with httpx.AsyncClient() as c:
            resp = await c.delete(
                self._url(f"/workspaces/{workspace_id}/issues/{issue_id}/labels/{label_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()

    async def list_issue_labels(
        self, workspace_id: str, issue_id: str
    ) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/issues/{issue_id}/labels"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    # ── Dependencies ─────────────────────────────────────────────────────

    async def create_dependency(
        self, workspace_id: str, issue_id: str, depends_on_issue_id: str, type: str = "blocks"
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient() as c:
            resp = await c.post(
                self._url(f"/workspaces/{workspace_id}/issues/{issue_id}/dependencies/"),
                json={"depends_on_issue_id": depends_on_issue_id, "type": type},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def list_dependencies(
        self, workspace_id: str, issue_id: str
    ) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/issues/{issue_id}/dependencies/"),
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_dependency(
        self, workspace_id: str, issue_id: str, dep_id: str
    ) -> None:
        async with httpx.AsyncClient() as c:
            resp = await c.delete(
                self._url(f"/workspaces/{workspace_id}/issues/{issue_id}/dependencies/{dep_id}"),
                headers=self._headers(),
            )
            resp.raise_for_status()

    # ── Activity ─────────────────────────────────────────────────────────

    async def list_workspace_activity(
        self, workspace_id: str, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        params = {"limit": str(limit), "offset": str(offset)}
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/activity"),
                params=params,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def list_issue_activity(
        self, workspace_id: str, issue_id: str, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        params = {"limit": str(limit), "offset": str(offset)}
        async with httpx.AsyncClient() as c:
            resp = await c.get(
                self._url(f"/workspaces/{workspace_id}/issues/{issue_id}/activity"),
                params=params,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
