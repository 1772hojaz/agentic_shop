"""Authentication and staff administration HTTP interfaces."""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select

from app.auth import (
    assign_role,
    create_session,
    current_principal,
    digest,
    hash_password,
    require,
    user_principal,
    verify_password,
)
from app.catalogue import get_record, serialize
from app.config import get_settings
from app.database import audit, get_db, utcnow
from app.models import (
    AdminBinding,
    AuthSession,
    LoginAttempt,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.schemas import Login, RoleUpdate, StaffInput, StaffUpdate
from app.whatsapp import pairing_code

router = APIRouter(prefix="/api/v1", tags=["Authentication and staff"])
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def login_throttle(db, email: str, host: str):
    """Persist a bounded login attempt window across process restarts."""
    key = digest(host + ":" + email.lower())
    record = db.get(LoginAttempt, key)
    if not record:
        record = LoginAttempt(
            key=key, attempts=0, reset_at=utcnow() + timedelta(minutes=15)
        )
        db.add(record)
    if record.reset_at <= utcnow():
        record.attempts = 0
        record.reset_at = utcnow() + timedelta(minutes=15)
    if record.attempts >= 10:
        raise HTTPException(429, "Too many login attempts; retry later")
    record.attempts += 1
    db.flush()
    return record


@router.post("/auth/login")
def login(
    data: Login, request: Request, response: Response, db=Depends(get_db)
):
    """Authenticate credentials and issue an HttpOnly session cookie."""
    host = request.client.host if request.client else "unknown"
    attempt = login_throttle(db, data.email, host)
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    stored = user.password_hash if user else DUMMY_HASH
    valid = verify_password(data.password, stored)
    if not user or not valid or not user.active:
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    attempt.attempts = 0
    token, session = create_session(db, user.id)
    settings = get_settings()
    response.set_cookie(
        "shop_session",
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    actor = user_principal(db, user)
    audit(db, actor.id, "auth.login", user.id)
    return {
        "user": serialize(user),
        "csrf_token": session.csrf,
        "permissions": sorted(actor.permissions),
    }


@router.get("/auth/me")
def me(request: Request, actor=Depends(current_principal), db=Depends(get_db)):
    """Return identity, current permissions and the session CSRF token."""
    token = request.cookies.get("shop_session", "")
    session = db.get(AuthSession, digest(token)) if token else None
    return {
        "id": actor.id,
        "name": actor.name,
        "context": actor.context,
        "permissions": sorted(actor.permissions),
        "csrf_token": session.csrf if session else "",
    }


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    actor=Depends(current_principal),
    db=Depends(get_db),
):
    """Revoke the current session and paired WhatsApp administrator access."""
    bearer = request.headers.get("authorization", "")
    token = (
        bearer[7:]
        if bearer.startswith("Bearer ")
        else (request.cookies.get("shop_session", ""))
    )
    db.execute(
        delete(AuthSession).where(AuthSession.token_hash == digest(token))
    )
    db.execute(delete(AdminBinding).where(AdminBinding.user_id == actor.id))
    response.delete_cookie("shop_session", path="/")
    return {"logged_out": True}


@router.post("/auth/whatsapp-pairing")
def pair(actor=Depends(current_principal), db=Depends(get_db)):
    """Generate an administrator pairing code after browser login."""
    return pairing_code(db, actor)


@router.get("/staff")
def staff(actor=Depends(require("staff.write")), db=Depends(get_db)):
    """List accounts and assigned roles without password hashes."""
    result = []
    for user in db.scalars(select(User).order_by(User.created_at)):
        roles = db.scalars(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        ).all()
        result.append({**serialize(user), "roles": roles})
    return {"items": result, "total": len(result)}


@router.post("/staff", status_code=201)
def create_staff(
    data: StaffInput, actor=Depends(require("staff.write")), db=Depends(get_db)
):
    """Register a password-protected staff account with an explicit role."""
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise HTTPException(409, "Email is already registered")
    user = User(
        email=data.email.lower(),
        name=data.name,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.flush()
    assign_role(db, user.id, data.role)
    audit(db, actor.id, "staff.create", user.id)
    return serialize(user)


@router.patch("/staff/{user_id}")
def update_staff(
    user_id: str,
    data: StaffUpdate,
    actor=Depends(require("staff.write")),
    db=Depends(get_db),
):
    """Modify roles without allowing the current owner to lock itself out."""
    user = get_record(db, User, user_id)
    if user.id == actor.id and (data.role != "owner" or not data.active):
        raise HTTPException(409, "Cannot remove your own owner access")
    assign_role(db, user.id, data.role)
    user.active = data.active
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(delete(AdminBinding).where(AdminBinding.user_id == user.id))
    audit(db, actor.id, "staff.update", user.id)
    return serialize(user)


@router.get("/roles")
def roles(actor=Depends(require("staff.write")), db=Depends(get_db)):
    """List role definitions and explicit backend permission grants."""
    return [
        {
            "id": role.id,
            "name": role.name,
            "permissions": list(
                db.scalars(
                    select(RolePermission.permission).where(
                        RolePermission.role_id == role.id
                    )
                )
            ),
        }
        for role in db.scalars(select(Role))
    ]


@router.patch("/roles/{role_id}")
def update_role(
    role_id: str,
    data: RoleUpdate,
    actor=Depends(require("staff.write")),
    db=Depends(get_db),
):
    """Configure operational grants while protecting the owner role."""
    from app.auth import PERMISSIONS

    role = get_record(db, Role, role_id)
    if role.name == "owner":
        raise HTTPException(409, "Owner permissions are fixed")
    grants = set(data.permissions)
    if not grants <= PERMISSIONS - {"staff.write", "settings.write"}:
        raise HTTPException(422, "Unknown or owner-only permission")
    db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    for permission in grants:
        db.add(RolePermission(role_id=role.id, permission=permission))
    audit(db, actor.id, "role.update", role.id)
    return {"id": role.id, "permissions": sorted(grants)}
