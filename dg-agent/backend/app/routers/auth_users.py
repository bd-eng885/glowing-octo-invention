from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import User
from ..security import ROLE_PERMISSIONS, ROLES, create_token, current_user, hash_password, require, verify_password

router = APIRouter(prefix="/api", tags=["auth & users"])


class LoginIn(BaseModel):
    email: str
    password: str


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role, "qualification": u.qualification,
            "is_active": u.is_active, "permissions": sorted(ROLE_PERMISSIONS.get(u.role, []))}


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.execute(select(User).where(User.email == body.email.lower().strip())).scalar_one_or_none()
    if not u or not u.is_active or not verify_password(body.password, u.password_hash):
        audit.record(db, "auth.login_failed", detail={"email": body.email})
        raise HTTPException(401, "Invalid credentials")
    audit.record(db, "auth.login", u)
    return {"access_token": create_token(u), "token_type": "bearer", "user": user_out(u)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


class UserIn(BaseModel):
    email: str
    full_name: str = ""
    role: str = "viewer"
    qualification: str = ""
    password: str = Field(min_length=10)


class UserPatch(BaseModel):
    full_name: str | None = None
    role: str | None = None
    qualification: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10)


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require("manage_users"))):
    return [user_out(u) for u in db.execute(select(User).order_by(User.id)).scalars()]


@router.get("/roles")
def roles(_: User = Depends(current_user)):
    return {r: sorted(p) for r, p in ROLE_PERMISSIONS.items()}


@router.post("/users")
def create_user(body: UserIn, db: Session = Depends(get_db), admin: User = Depends(require("manage_users"))):
    if body.role not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    email = body.email.lower().strip()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(409, "User exists")
    u = User(email=email, full_name=body.full_name, role=body.role, qualification=body.qualification,
             password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit.record(db, "user.create", admin, "user", u.id, {"email": email, "role": body.role})
    return user_out(u)


@router.patch("/users/{uid}")
def update_user(uid: int, body: UserPatch, db: Session = Depends(get_db), admin: User = Depends(require("manage_users"))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Not found")
    changes = body.model_dump(exclude_none=True)
    if "role" in changes and changes["role"] not in ROLES:
        raise HTTPException(422, f"role must be one of {ROLES}")
    if u.id == admin.id and (changes.get("role", u.role) != "admin" or changes.get("is_active") is False):
        raise HTTPException(400, "Administrators cannot demote or deactivate themselves")
    for k, v in changes.items():
        if k == "password":
            u.password_hash = hash_password(v)
        else:
            setattr(u, k, v)
    audit.record(db, "user.update", admin, "user", u.id, {k: v for k, v in changes.items() if k != "password"})
    return user_out(u)
