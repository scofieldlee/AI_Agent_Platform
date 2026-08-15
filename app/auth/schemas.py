"""
Auth request/response schemas.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Login request body."""

    username: str = Field(..., min_length=1, max_length=100, description="Username or email")
    password: str = Field(..., min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    """Register request body."""

    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=200)
    full_name: Optional[str] = None
    department: Optional[str] = None


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600  # seconds


class RefreshRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str


class UserOut(BaseModel):
    """User info for API responses."""

    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    avatar: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    last_login: Optional[datetime] = None
    roles: List[str] = []          # role codes, e.g. ["super_admin"]
    permissions: List[str] = []    # permission codes, e.g. ["dashboard:view"]

    model_config = {"from_attributes": True}


class UserCreateRequest(BaseModel):
    """Admin creating a new user with role assignment."""

    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=200)
    full_name: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    role_codes: List[str] = Field(default=["user"], description="Role codes to assign")
    is_active: bool = True
    is_superuser: bool = False


class UserUpdateRequest(BaseModel):
    """Admin updating an existing user."""

    full_name: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    role_codes: Optional[List[str]] = None


class RoleOut(BaseModel):
    """Role info for API responses."""

    id: int
    code: str
    name: str
    description: Optional[str] = None

    model_config = {"from_attributes": True}
