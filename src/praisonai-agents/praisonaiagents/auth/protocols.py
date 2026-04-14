"""
Auth protocol definitions for PraisonAI Agents.

Defines the structural contracts for authentication and authorization
backends via typing.Protocol. Any class implementing the required methods
satisfies the protocol without explicit inheritance (structural subtyping).

Design influenced by:
- Multica: JWT-based auth with email codes + Google OAuth, role-based
  workspace membership (owner/admin/member), agents as assignees.
- Paperclip: better-auth sessions, company memberships with principal
  types (user/agent), fine-grained permission grants.
- PraisonAI patterns: ApprovalProtocol, GatewayProtocol, DbAdapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class AuthIdentity:
    """Authenticated identity (user or agent).

    Attributes:
        id:           Unique identifier for this principal.
        type:         Principal type — ``"user"`` or ``"agent"``.
        workspace_id: Active workspace/tenant scope (optional).
        roles:        Roles within the workspace (e.g. ``["owner"]``).
        email:        Email address (users only, optional).
        name:         Display name (optional).
        metadata:     Arbitrary extra data for backend-specific info.
    """

    id: str
    type: str = "user"
    workspace_id: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    email: Optional[str] = None
    name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_user(self) -> bool:
        """Check if this identity is a human user."""
        return self.type == "user"

    @property
    def is_agent(self) -> bool:
        """Check if this identity is an agent."""
        return self.type == "agent"

    def has_role(self, role: str) -> bool:
        """Check if this identity has a specific role."""
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        """Check if this identity has any of the specified roles."""
        return bool(set(roles) & set(self.roles))


@dataclass
class AuthConfig:
    """Configuration for authentication behaviour.

    Follows PraisonAI's ``False/True/Config`` progressive-disclosure pattern:

    - ``auth=False`` — disabled (no auth checks).
    - ``auth=True``  — use default backend from registry.
    - ``auth=AuthConfig(...)`` — full control.

    Attributes:
        backend:    An :class:`AuthBackendProtocol` backend.
                    ``None`` falls back to registry default.
        token_ttl:  Token time-to-live in seconds (default: 30 days).
        require_workspace: Whether workspace_id is required for authorization.
    """

    backend: Any = None
    token_ttl: int = 30 * 24 * 3600
    require_workspace: bool = False


@runtime_checkable
class AuthBackendProtocol(Protocol):
    """Protocol for authentication/authorization backends.

    Implement ``authenticate`` and ``authorize`` to create custom auth:
    - JWT token validation
    - API key lookup
    - OAuth token exchange
    - Session cookie resolution

    Example::

        class JWTAuthBackend:
            async def authenticate(
                self, credentials: dict
            ) -> AuthIdentity | None:
                token = credentials.get("token")
                payload = decode_jwt(token)
                return AuthIdentity(
                    id=payload["sub"],
                    type="user",
                    email=payload.get("email"),
                    roles=payload.get("roles", []),
                )

            async def authorize(
                self, identity: AuthIdentity, resource: str, action: str
            ) -> bool:
                return identity.has_role("admin")
    """

    async def authenticate(
        self,
        credentials: Dict[str, Any],
    ) -> Optional[AuthIdentity]:
        """Authenticate credentials and return an identity.

        Args:
            credentials: Backend-specific credentials dict.
                Common keys: ``token``, ``api_key``, ``email``, ``password``,
                ``session_id``.

        Returns:
            AuthIdentity if authentication succeeds, None otherwise.
        """
        ...

    async def authorize(
        self,
        identity: AuthIdentity,
        resource: str,
        action: str,
    ) -> bool:
        """Check if an identity is authorized for an action on a resource.

        Args:
            identity: The authenticated identity.
            resource: Resource identifier (e.g. ``"workspace:ws-123"``
                      or ``"issue:ISS-42"``).
            action:   Action to perform (e.g. ``"read"``, ``"write"``,
                      ``"delete"``, ``"admin"``).

        Returns:
            True if authorized, False otherwise.
        """
        ...


@runtime_checkable
class WorkspaceContextProtocol(Protocol):
    """Protocol for providing workspace context to agents.

    Enables agents to access workspace-specific settings, instructions,
    and agent configurations from the platform layer.

    Example::

        class PlatformWorkspaceContext:
            async def get_workspace_context(self, workspace_id):
                ws = await db.get_workspace(workspace_id)
                return ws.context

            async def get_agent_config(self, workspace_id, agent_id):
                agent = await db.get_agent(workspace_id, agent_id)
                return {"system_prompt": agent.system_prompt, ...}
    """

    async def get_workspace_context(
        self,
        workspace_id: str,
    ) -> Optional[str]:
        """Get workspace-level context/instructions for agents.

        Args:
            workspace_id: The workspace identifier.

        Returns:
            Context string if available, None otherwise.
        """
        ...

    async def get_agent_config(
        self,
        workspace_id: str,
        agent_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get agent configuration from the platform.

        Args:
            workspace_id: The workspace identifier.
            agent_id:     The agent identifier.

        Returns:
            Agent configuration dict if found, None otherwise.
            Expected keys: ``system_prompt``, ``model``, ``tools``,
            ``max_concurrent_tasks``.
        """
        ...
