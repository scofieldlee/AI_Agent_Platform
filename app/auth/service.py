"""
Authentication service: password hashing, JWT management, user authentication.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User, Role, Permission, UserRole, RolePermission

# --- Password hashing ---


def hash_password(plain: str) -> str:
    """Hash a password with bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# --- JWT ---


def create_access_token(user_id: int, username: str, roles: list[str]) -> str:
    """Create a short-lived access token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "roles": roles,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: int) -> str:
    """Create a long-lived refresh token."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# --- User authentication ---


async def authenticate_user(db: AsyncSession, username_or_email: str, password: str) -> Tuple[Optional[User], Optional[str]]:
    """
    Authenticate a user by username/email + password.
    Returns (user, error_message).
    """
    # Try username first, then email
    result = await db.execute(
        select(User).where(
            (User.username == username_or_email) | (User.email == username_or_email)
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        return None, "User not found"

    if not user.is_active:
        return None, "Account is disabled"

    if not verify_password(password, user.hashed_password):
        return None, "Invalid password"

    # Update last_login
    user.last_login = datetime.now(timezone.utc)
    await db.flush()

    return user, None


# --- Permission helpers ---


async def get_user_permissions(db: AsyncSession, user_id: int) -> list[str]:
    """Get all permission codes for a user via their roles."""
    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
        .distinct()
    )
    return [row[0] for row in result.fetchall()]


async def get_user_role_codes(db: AsyncSession, user_id: int) -> list[str]:
    """Get all role codes for a user."""
    result = await db.execute(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    return [row[0] for row in result.fetchall()]


async def user_has_permission(db: AsyncSession, user_id: int, permission_code: str) -> bool:
    """Check if a user has a specific permission."""
    if permission_code is None:
        return True
    permissions = await get_user_permissions(db, user_id)
    return permission_code in permissions


async def user_has_role(db: AsyncSession, user_id: int, role_codes: list[str]) -> bool:
    """Check if a user has any of the specified roles."""
    user_roles = await get_user_role_codes(db, user_id)
    return any(r in role_codes for r in user_roles)
