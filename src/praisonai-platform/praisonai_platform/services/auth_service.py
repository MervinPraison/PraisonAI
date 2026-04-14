"""
Auth service — JWT-based authentication.

Implements AuthBackendProtocol from praisonaiagents.auth.
Influenced by Multica's issueJWT + findOrCreateUser pattern.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from praisonaiagents.auth import AuthIdentity

from ..db.models import Member, User

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_DEFAULT_SECRET = "dev-secret-change-me"
JWT_SECRET = os.environ.get("PLATFORM_JWT_SECRET", _DEFAULT_SECRET)
JWT_ALGORITHM = "HS256"
JWT_TTL_SECONDS = int(os.environ.get("PLATFORM_JWT_TTL", str(30 * 24 * 3600)))

if JWT_SECRET == _DEFAULT_SECRET and os.environ.get("PLATFORM_ENV", "dev") != "dev":
    raise RuntimeError(
        "PLATFORM_JWT_SECRET must be set to a strong random value in production. "
        "Set PLATFORM_ENV=dev to suppress this check during development."
    )


class AuthService:
    """JWT authentication service implementing AuthBackendProtocol."""

    def __init__(self, session: AsyncSession):
        self._session = session

    # ── AuthBackendProtocol methods ──────────────────────────────────────

    async def authenticate(
        self, credentials: Dict[str, Any]
    ) -> Optional[AuthIdentity]:
        """Authenticate via JWT token or email+password."""
        token = credentials.get("token")
        if token:
            return self._verify_token(token)

        email = credentials.get("email")
        password = credentials.get("password")
        if email and password:
            return await self._authenticate_password(email, password)

        return None

    async def authorize(
        self, identity: AuthIdentity, resource: str, action: str
    ) -> bool:
        """Check workspace-scoped RBAC authorization."""
        if not identity.workspace_id:
            return action == "read"

        stmt = select(Member).where(
            Member.workspace_id == identity.workspace_id,
            Member.user_id == identity.id,
        )
        result = await self._session.execute(stmt)
        member = result.scalar_one_or_none()
        if member is None:
            return False

        if member.role == "owner":
            return True
        if member.role == "admin":
            return action != "admin"
        if member.role == "member":
            return action in ("read", "write")
        return False

    # ── Registration & Login ─────────────────────────────────────────────

    async def register(
        self, email: str, password: str, name: Optional[str] = None
    ) -> tuple[User, str]:
        """Register a new user and return (user, jwt_token)."""
        user = User(
            email=email,
            name=name or email.split("@")[0],
            password_hash=_pwd_context.hash(password),
        )
        self._session.add(user)
        await self._session.flush()
        token = self._issue_token(user)
        return user, token

    async def login(self, email: str, password: str) -> Optional[tuple[User, str]]:
        """Login with email+password, return (user, jwt_token) or None."""
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None or not user.password_hash:
            return None
        if not _pwd_context.verify(password, user.password_hash):
            return None
        token = self._issue_token(user)
        return user, token

    # ── Token management ─────────────────────────────────────────────────

    def _issue_token(self, user: User) -> str:
        """Issue a JWT for a user."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user.id,
            "email": user.email,
            "name": user.name,
            "iat": now,
            "exp": now + timedelta(seconds=JWT_TTL_SECONDS),
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    def _verify_token(self, token: str) -> Optional[AuthIdentity]:
        """Decode and verify a JWT, returning AuthIdentity or None."""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return AuthIdentity(
                id=payload["sub"],
                type="user",
                email=payload.get("email"),
                name=payload.get("name"),
            )
        except jwt.InvalidTokenError:
            return None

    async def _authenticate_password(
        self, email: str, password: str
    ) -> Optional[AuthIdentity]:
        """Authenticate via email+password, return AuthIdentity."""
        result = await self.login(email, password)
        if result is None:
            return None
        user, _ = result
        return AuthIdentity(
            id=user.id,
            type="user",
            email=user.email,
            name=user.name,
        )
