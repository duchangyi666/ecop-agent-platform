"""Model registry for Alembic autogeneration."""

from backend.database.base import Base
from backend.database.models.identity import Permission, Role, Tenant, User, UserRole

__all__ = ["Base", "Permission", "Role", "Tenant", "User", "UserRole"]
