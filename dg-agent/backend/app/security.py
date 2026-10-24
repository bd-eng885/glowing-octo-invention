"""Authentication (PBKDF2 password hashing + JWT) and role-based access control."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

PBKDF2_ITERATIONS = 310_000

# Segregation of duties: administrators manage users and data imports but cannot
# approve DG decisions or mark regulatory data verified; that is reserved for
# qualified DGSA approvers.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "viewer": {"read"},
    "operator": {"read", "analyze", "create_report", "upload", "submit_review"},
    "dg_reviewer": {"read", "analyze", "create_report", "upload", "submit_review", "review"},
    "dgsa_approver": {"read", "analyze", "create_report", "upload", "submit_review", "review",
                      "approve", "verify_regulatory_data"},
    "admin": {"read", "analyze", "create_report", "upload", "submit_review", "manage_users",
              "manage_sources", "manage_config"},
}
ROLES = tuple(ROLE_PERMISSIONS)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, dk_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False


def create_token(user: User) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {"sub": str(user.id), "role": user.role, "iat": now,
               "exp": now + dt.timedelta(minutes=settings.jwt_ttl_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


_bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or not found")
    return user


def has_perm(user: User, perm: str) -> bool:
    return perm in ROLE_PERMISSIONS.get(user.role, set())


def require(perm: str):
    def dep(user: User = Depends(current_user)) -> User:
        if not has_perm(user, perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"Role '{user.role}' is not authorised to perform '{perm}'")
        return user
    return dep
