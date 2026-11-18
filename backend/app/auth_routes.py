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


