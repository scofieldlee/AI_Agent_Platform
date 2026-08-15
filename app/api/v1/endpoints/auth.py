"""
Auth API endpoints: login, register, me, refresh, logout.
"""

from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.user import User, UserRole, Role, RolePermission, Permission
from app.auth.service import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    authenticate_user, get_user_role_codes, get_user_permissions,
)
from app.auth.schemas import (
    LoginRequest, RegisterRequest, TokenResponse,
    RefreshRequest, UserOut, UserCreateRequest, UserUpdateRequest, RoleOut,
)
from app.auth.dependencies import get_current_user, require_permission

router = APIRouter()


def _user_to_out(user: User, roles: list[str], permissions: list[str]) -> dict:
    """Convert User ORM to UserOut dict."""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "avatar": user.avatar,
        "phone": user.phone,
        "department": user.department,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "roles": roles,
        "permissions": permissions,
    }


@router.post("/login", response_model=TokenResponse, summary="Login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate and return JWT tokens."""
    user, error = await authenticate_user(db, body.username, body.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error or "Authentication failed",
        )

    # Get role codes for JWT
    role_codes = await get_user_role_codes(db, user.id)

    access_token = create_access_token(user.id, user.username, role_codes)
    refresh_token = create_refresh_token(user.id)

    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/register", response_model=UserOut, summary="Register a new user")
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user. Default role: 'user'."""
    # Check username / email uniqueness
    existing = await db.execute(
        select(User).where(
            (User.username == body.username) | (User.email == body.email)
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists",
        )

    # Create user
    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        department=body.department,
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()

    # Assign default 'user' role
    role_result = await db.execute(select(Role).where(Role.code == "user"))
    default_role = role_result.scalar_one_or_none()
    if default_role:
        db.add(UserRole(user_id=user.id, role_id=default_role.id))

    await db.commit()

    roles = await get_user_role_codes(db, user.id)
    permissions = await get_user_permissions(db, user.id)

    return _user_to_out(user, roles, permissions)


@router.get("/me", response_model=UserOut, summary="Get current user")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the authenticated user's profile."""
    roles = await get_user_role_codes(db, current_user.id)
    permissions = await get_user_permissions(db, current_user.id)
    return _user_to_out(current_user, roles, permissions)


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a refresh token for a new access token."""
    payload = decode_token(body.refresh_token)

    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
        )

    role_codes = await get_user_role_codes(db, user.id)

    return TokenResponse(
        access_token=create_access_token(user.id, user.username, role_codes),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/logout", summary="Logout")
async def logout(current_user: User = Depends(get_current_user)):
    """
    Stateless logout — client discards tokens.
    In production, add token to a Redis blacklist.
    """
    return {"message": "Logged out successfully"}


# --- Admin-only endpoints ---

@router.get("/users", summary="List all users (admin)")
async def list_users(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users. Requires admin role or superuser."""
    if not current_user.is_superuser:
        role_codes = await get_user_role_codes(db, current_user.id)
        if "super_admin" not in role_codes and "ai_admin" not in role_codes:
            raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()

    out = []
    for u in users:
        roles = await get_user_role_codes(db, u.id)
        out.append(_user_to_out(u, roles, []))

    return {"items": out, "total": len(out)}


@router.get("/roles", summary="List all roles (admin)")
async def list_roles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all available roles for role assignment UI."""
    result = await db.execute(select(Role).order_by(Role.id))
    roles = result.scalars().all()
    return [
        {"id": r.id, "code": r.code, "name": r.name, "description": r.description}
        for r in roles
    ]


@router.post("/users", response_model=UserOut, summary="Create user (admin)")
async def create_user(
    body: UserCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user with specified roles. Admin only."""
    # Check permission
    if not current_user.is_superuser:
        role_codes = await get_user_role_codes(db, current_user.id)
        if "super_admin" not in role_codes and "ai_admin" not in role_codes:
            raise HTTPException(status_code=403, detail="Admin access required")

    # Check uniqueness
    existing = await db.execute(
        select(User).where(
            (User.username == body.username) | (User.email == body.email)
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="Username or email already exists",
        )

    # Create user
    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        department=body.department,
        phone=body.phone,
        is_active=body.is_active,
        is_superuser=body.is_superuser,
    )
    db.add(user)
    await db.flush()

    # Assign roles
    for role_code in body.role_codes:
        role_result = await db.execute(select(Role).where(Role.code == role_code))
        role = role_result.scalar_one_or_none()
        if role:
            db.add(UserRole(user_id=user.id, role_id=role.id))

    await db.commit()

    roles = await get_user_role_codes(db, user.id)
    permissions = await get_user_permissions(db, user.id)
    return _user_to_out(user, roles, permissions)


@router.patch("/users/{user_id}", response_model=UserOut, summary="Update user (admin)")
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user info, roles, or active status. Admin only."""
    # Check permission
    if not current_user.is_superuser:
        role_codes = await get_user_role_codes(db, current_user.id)
        if "super_admin" not in role_codes and "ai_admin" not in role_codes:
            raise HTTPException(status_code=403, detail="Admin access required")

    # Find user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Update fields
    update_data = body.model_dump(exclude_unset=True)
    role_codes = None

    if "role_codes" in update_data:
        role_codes = update_data.pop("role_codes")

    for key, value in update_data.items():
        setattr(user, key, value)

    # Update roles if provided
    if role_codes is not None:
        # Remove existing roles
        existing_roles = await db.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        for ur in existing_roles.scalars().all():
            await db.delete(ur)

        # Assign new roles
        for role_code in role_codes:
            role_result = await db.execute(select(Role).where(Role.code == role_code))
            role = role_result.scalar_one_or_none()
            if role:
                db.add(UserRole(user_id=user_id, role_id=role.id))

    await db.commit()

    roles = await get_user_role_codes(db, user.id)
    permissions = await get_user_permissions(db, user.id)
    return _user_to_out(user, roles, permissions)
