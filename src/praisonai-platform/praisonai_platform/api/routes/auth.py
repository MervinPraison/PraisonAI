"""Auth routes — register, login, me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from praisonaiagents.auth import AuthIdentity

from ..deps import get_current_user, get_db
from ..schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from ...services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_db)):
    auth_svc = AuthService(session)
    try:
        user, token = await auth_svc.register(body.email, body.password, body.name)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return TokenResponse(
        token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)):
    auth_svc = AuthService(session)
    result = await auth_svc.login(body.email, body.password)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    user, token = result
    return TokenResponse(
        token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: AuthIdentity = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        name=current_user.name or "",
        email=current_user.email or "",
        created_at=None,  # type: ignore[arg-type]
    )
