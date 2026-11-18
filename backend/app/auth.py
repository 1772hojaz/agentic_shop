"""Revocable authentication, role enforcement and explicit confirmations."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db, utcnow
from app.models import (
    AuthSession,
    Confirmation,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)

PERMISSIONS = {
    "products.read",
    "products.write",
    "inventory.read",
    "inventory.write",
    "orders.read",
    "orders.write",
    "customers.read",
    "reports.read",
    "staff.write",
    "settings.write",
    "ai.read",
    "ai.chat",
    "notifications.write",
    "audit.read",
    "payments.write",
}
CUSTOMER_PERMISSIONS = {
    "products.read",
    "inventory.read",
    "cart.own",
    "orders.own",
    "ai.chat",
}


def digest(value: str) -> str:
    """Hash a high-entropy session or one-time code before storage."""
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    """Derive a salted scrypt hash using bounded memory."""
    salt = secrets.token_hex(16)
    result = hashlib.scrypt(
        password.encode(), salt=salt.encode(), n=16384, r=8, p=1
    )
    return f"scrypt${salt}${result.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Compare derived hashes without timing-dependent string equality."""
    try:
        scheme, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        result = hashlib.scrypt(
            password.encode(), salt=salt.encode(), n=16384, r=8, p=1
        )
        return hmac.compare_digest(result.hex(), expected)
    except (ValueError, TypeError):
        return False


@dataclass
class Principal:
    """Identity resolved by the backend, never by model arguments."""

    id: str
    context: str
    permissions: set[str]
    name: str = "Customer"

    def require(self, permission: str) -> None:
        """Reject missing capabilities at every service entry point."""
        if permission not in self.permissions:
            raise HTTPException(403, "Permission denied")


def user_principal(db: Session, user: User) -> Principal:
    """Resolve current role permissions rather than trusting a token claim."""
    if not user.active:
        raise HTTPException(401, "Account disabled")
    query = (
        select(RolePermission.permission)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user.id)
    )
    return Principal(user.id, "admin", set(db.scalars(query)), user.name)


def current_principal(
    request: Request, db: Session = Depends(get_db)
) -> Principal:
    """Authenticate opaque bearer tokens or CSRF-protected cookies."""
    bearer = request.headers.get("authorization", "")
    bearer_token = bearer[7:] if bearer.startswith("Bearer ") else ""
    token = bearer_token or request.cookies.get("shop_session", "")
    session = db.get(AuthSession, digest(token)) if token else None
    if not session or session.expires_at <= utcnow():
        raise HTTPException(401, "Authentication required")
    if not bearer_token and request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(csrf, session.csrf):
            raise HTTPException(403, "Invalid CSRF token")
    if session.user_id:
        user = db.get(User, session.user_id)
        if user:
            return user_principal(db, user)
    if session.customer_id:
        return Principal(session.customer_id, "customer", CUSTOMER_PERMISSIONS)
    raise HTTPException(401, "Invalid session")


