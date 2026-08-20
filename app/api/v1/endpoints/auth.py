"""
Auth API endpoints: login, register, me, refresh, logout.
"""

from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
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
    RefreshRequest, UserOut, UserCreateRequest, UserUpdateRequest,
    RoleOut, RoleDetailOut, RoleCreateRequest, RoleUpdateRequest,
    PermissionOut, PermissionGroupOut,
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


@router.get("/roles", response_model=list[RoleOut], summary="List all roles (admin)")
async def list_roles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all available roles for role assignment UI."""
    result = await db.execute(select(Role).order_by(Role.id))
    roles = result.scalars().all()

    role_ids = [r.id for r in roles]

    # Count users per role
    user_counts = {}
    if role_ids:
        result = await db.execute(
            select(UserRole.role_id, func.count(UserRole.user_id))
            .where(UserRole.role_id.in_(role_ids))
            .group_by(UserRole.role_id)
        )
        user_counts = {role_id: count for role_id, count in result.fetchall()}

    # Count permissions per role
    perm_counts = {}
    if role_ids:
        result = await db.execute(
            select(RolePermission.role_id, func.count(RolePermission.permission_id))
            .where(RolePermission.role_id.in_(role_ids))
            .group_by(RolePermission.role_id)
        )
        perm_counts = {role_id: count for role_id, count in result.fetchall()}

    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "description": r.description,
            "is_system": r.is_system,
            "user_count": user_counts.get(r.id, 0),
            "permission_count": perm_counts.get(r.id, 0),
        }
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


# --- Role & permission management ---


async def _require_admin(current_user: User, db: AsyncSession) -> None:
    """Require superuser, super_admin or ai_admin role."""
    if current_user.is_superuser:
        return
    role_codes = await get_user_role_codes(db, current_user.id)
    if "super_admin" not in role_codes and "ai_admin" not in role_codes:
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/permissions", response_model=list[PermissionGroupOut], summary="List all permissions")
async def list_permissions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all permissions grouped by resource_type."""
    await _require_admin(current_user, db)

    result = await db.execute(select(Permission).order_by(Permission.resource_type, Permission.id))
    permissions = result.scalars().all()

    groups: dict[str, list[PermissionOut]] = {}
    for p in permissions:
        groups.setdefault(p.resource_type, []).append(
            PermissionOut.model_validate(p)
        )

    return [
        {"resource_type": resource_type, "permissions": perms}
        for resource_type, perms in groups.items()
    ]


@router.get("/roles/{role_id}", response_model=RoleDetailOut, summary="Get role detail")
async def get_role(
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get role details including assigned permission codes."""
    await _require_admin(current_user, db)

    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")

    perm_codes = await get_role_permission_codes(db, role.id)
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "permissions": perm_codes,
    }


async def get_role_permission_codes(db: AsyncSession, role_id: int) -> list[str]:
    """Get permission codes assigned to a role."""
    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
    )
    return [row[0] for row in result.fetchall()]


async def set_role_permissions(db: AsyncSession, role_id: int, permission_codes: list[str]) -> None:
    """Replace role's permissions."""
    # Validate permission codes
    result = await db.execute(select(Permission).where(Permission.code.in_(permission_codes)))
    valid_perms = {p.code: p for p in result.scalars().all()}
    invalid = set(permission_codes) - set(valid_perms.keys())
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid permission codes: {', '.join(sorted(invalid))}",
        )

    # Remove existing mappings
    existing = await db.execute(
        select(RolePermission).where(RolePermission.role_id == role_id)
    )
    for rp in existing.scalars().all():
        await db.delete(rp)

    # Add new mappings
    for perm in valid_perms.values():
        db.add(RolePermission(role_id=role_id, permission_id=perm.id))


@router.post("/roles", response_model=RoleDetailOut, summary="Create role")
async def create_role(
    body: RoleCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new role and assign permissions."""
    await _require_admin(current_user, db)

    # Check uniqueness
    existing = await db.execute(
        select(Role).where((Role.code == body.code) | (Role.name == body.name))
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Role code or name already exists")

    role = Role(
        code=body.code,
        name=body.name,
        description=body.description,
        is_system=False,
    )
    db.add(role)
    await db.flush()

    await set_role_permissions(db, role.id, body.permission_codes)
    await db.commit()

    perm_codes = await get_role_permission_codes(db, role.id)
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "permissions": perm_codes,
    }


@router.patch("/roles/{role_id}", response_model=RoleDetailOut, summary="Update role")
async def update_role(
    role_id: int,
    body: RoleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update role name, description or permissions."""
    await _require_admin(current_user, db)

    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")

    # System roles cannot be renamed (allow same name for permission updates)
    if role.is_system and body.name is not None and body.name != role.name:
        raise HTTPException(status_code=403, detail="Cannot rename system roles")

    update_data = body.model_dump(exclude_unset=True)
    permission_codes = update_data.pop("permission_codes", None)

    # Check name uniqueness if changing
    if "name" in update_data:
        existing = await db.execute(
            select(Role).where(
                (Role.name == update_data["name"]) & (Role.id != role_id)
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Role name already exists")

    for key, value in update_data.items():
        setattr(role, key, value)

    if permission_codes is not None:
        await set_role_permissions(db, role.id, permission_codes)

    await db.commit()

    perm_codes = await get_role_permission_codes(db, role.id)
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "permissions": perm_codes,
    }


@router.delete("/roles/{role_id}", summary="Delete role")
async def delete_role(
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a role. System roles cannot be deleted."""
    await _require_admin(current_user, db)

    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.is_system:
        raise HTTPException(status_code=403, detail="Cannot delete system roles")

    await db.delete(role)
    await db.commit()
    return {"message": "Role deleted successfully"}


@router.get("/roles/{role_id}/users", summary="List users bound to role")
async def list_role_users(
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List users who have this role assigned."""
    await _require_admin(current_user, db)

    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="Role not found")

    result = await db.execute(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.role_id == role_id)
        .order_by(User.id)
    )
    users = result.scalars().all()

    out = []
    for u in users:
        roles = await get_user_role_codes(db, u.id)
        out.append(_user_to_out(u, roles, []))

    return {"items": out, "total": len(out)}
