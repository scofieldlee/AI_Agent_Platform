"""
Seed default permissions and admin user on startup.
"""

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, Role, Permission, UserRole, RolePermission
from app.auth.service import hash_password

logger = logging.getLogger(__name__)

# --- Permission catalog ---
# Format: (code, name, resource_type, action, description)
PERMISSION_CATALOG = [
    # Dashboard
    ("dashboard:view", "View Dashboard", "dashboard", "view", "Access the admin dashboard"),

    # Agents
    ("agent:view", "View Agents", "agent", "view", "View agent configurations"),
    ("agent:manage", "Manage Agents", "agent", "manage", "Create, update, delete agents"),

    # Conversations
    ("conversation:view", "View Conversations", "conversation", "view", "View all conversations"),
    ("conversation:manage", "Manage Conversations", "conversation", "manage", "Delete conversations"),

    # Knowledge
    ("knowledge:view", "View Knowledge Base", "knowledge", "view", "Browse knowledge bases and documents"),
    ("knowledge:manage", "Manage Knowledge Base", "knowledge", "manage", "Add, sync, delete knowledge documents"),

    # Tools
    ("tool:view", "View Tools", "tool", "view", "View registered tools"),
    ("tool:manage", "Manage Tools", "tool", "manage", "Register, update, delete tools"),

    # Models
    ("model:view", "View Models", "model", "view", "View model configurations"),
    ("model:manage", "Manage Models", "model", "manage", "Configure model providers and settings"),

    # Memory
    ("memory:view", "View Memories", "memory", "view", "View stored memories"),
    ("memory:manage", "Manage Memories", "memory", "manage", "Delete memories"),

    # Human Tasks (tickets)
    ("ticket:view", "View Tickets", "ticket", "view", "View human tasks / tickets"),
    ("ticket:manage", "Manage Tickets", "ticket", "manage", "Assign and resolve tickets"),

    # Analytics
    ("analytics:view", "View Analytics", "analytics", "view", "View execution traces and stats"),

    # Users & Permissions (admin only)
    ("user:view", "View Users", "user", "view", "View user list"),
    ("user:manage", "Manage Users", "user", "manage", "Create, update, disable users"),

    # System
    ("system:config", "System Configuration", "system", "manage", "Access system settings"),
]

# --- Role -> permission mapping ---
# super_admin gets all permissions automatically (also is_superuser bypasses checks)
ROLE_PERMISSIONS = {
    "super_admin": "*",  # all permissions
    "ai_admin": [
        "dashboard:view", "agent:view", "agent:manage",
        "knowledge:view", "knowledge:manage",
        "tool:view", "tool:manage",
        "model:view", "model:manage",
        "analytics:view",
        "conversation:view",
        "ticket:view", "ticket:manage",
        "memory:view", "memory:manage",
    ],
    "business_admin": [
        "dashboard:view",
        "conversation:view", "conversation:manage",
        "ticket:view", "ticket:manage",
        "analytics:view",
        "memory:view",
    ],
    "developer": [
        "dashboard:view",
        "agent:view", "agent:manage",
        "knowledge:view", "knowledge:manage",
        "tool:view",
        "model:view",
        "analytics:view",
    ],
    "customer_service": [
        "dashboard:view",
        "conversation:view",
        "ticket:view", "ticket:manage",
        "memory:view",
        "knowledge:view",
    ],
    "user": [
        "dashboard:view",
    ],
}

# --- Default admin user ---
DEFAULT_ADMIN = {
    "username": "admin",
    "email": "admin@ai-agent.local",
    "password": "admin123456",
    "full_name": "System Administrator",
    "department": "IT",
}


async def seed_permissions(db: AsyncSession):
    """Seed the permission catalog if not exists."""
    created = 0
    for code, name, resource_type, action, desc in PERMISSION_CATALOG:
        result = await db.execute(select(Permission).where(Permission.code == code))
        if result.scalar_one_or_none() is None:
            db.add(Permission(
                name=name, code=code,
                resource_type=resource_type, action=action,
                description=desc,
            ))
            created += 1
    if created:
        logger.info(f"Seeded {created} permissions.")
    return created


async def seed_role_permissions(db: AsyncSession):
    """Assign permissions to roles based on ROLE_PERMISSIONS mapping."""
    # Get all permissions
    result = await db.execute(select(Permission))
    all_permissions = {p.code: p for p in result.scalars().all()}

    # Get all roles
    result = await db.execute(select(Role))
    all_roles = {r.code: r for r in result.scalars().all()}

    assigned = 0
    for role_code, perm_codes in ROLE_PERMISSIONS.items():
        role = all_roles.get(role_code)
        if role is None:
            continue

        # Get current role permissions
        result = await db.execute(
            select(RolePermission).where(RolePermission.role_id == role.id)
        )
        existing = {rp.permission_id for rp in result.scalars().all()}

        if perm_codes == "*":
            # All permissions
            target_perms = list(all_permissions.values())
        else:
            target_perms = [all_permissions[c] for c in perm_codes if c in all_permissions]

        for perm in target_perms:
            if perm.id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))
                assigned += 1

    if assigned:
        logger.info(f"Assigned {assigned} role-permission mappings.")
    return assigned


async def seed_admin_user(db: AsyncSession):
    """Create the default admin user if no users exist."""
    result = await db.execute(select(User).limit(1))
    if result.scalar_one_or_none() is not None:
        return False  # Users already exist

    # Create admin
    admin = User(
        username=DEFAULT_ADMIN["username"],
        email=DEFAULT_ADMIN["email"],
        hashed_password=hash_password(DEFAULT_ADMIN["password"]),
        full_name=DEFAULT_ADMIN["full_name"],
        department=DEFAULT_ADMIN["department"],
        is_active=True,
        is_superuser=True,
    )
    db.add(admin)
    await db.flush()

    # Assign super_admin role
    result = await db.execute(select(Role).where(Role.code == "super_admin"))
    super_admin_role = result.scalar_one_or_none()
    if super_admin_role:
        db.add(UserRole(user_id=admin.id, role_id=super_admin_role.id))

    # Create a customer service demo user
    cs_user = User(
        username="cs_agent",
        email="cs@ai-agent.local",
        hashed_password=hash_password("cs123456"),
        full_name="Demo Customer Service",
        department="Customer Service",
        is_active=True,
        is_superuser=False,
    )
    db.add(cs_user)
    await db.flush()

    result = await db.execute(select(Role).where(Role.code == "customer_service"))
    cs_role = result.scalar_one_or_none()
    if cs_role:
        db.add(UserRole(user_id=cs_user.id, role_id=cs_role.id))

    logger.info(
        f"Seeded admin user: {DEFAULT_ADMIN['username']}/{DEFAULT_ADMIN['password']} "
        f"and demo CS user: cs_agent/cs123456"
    )
    return True


async def run_auth_seed(db: AsyncSession):
    """Run all auth seed steps."""
    await seed_permissions(db)
    await seed_role_permissions(db)
    await seed_admin_user(db)
    await db.commit()
    logger.info("Auth seed completed.")
