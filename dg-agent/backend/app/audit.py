"""Tamper-evident audit trail: each record hashes its content plus the previous hash."""
from __future__ import annotations

import hashlib
import json
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, User, utcnow

GENESIS = "0" * 64
_lock = threading.Lock()


def _digest(prev_hash: str, ts: str, user_id, action: str, entity: str, entity_id: str, detail: dict) -> str:
    body = json.dumps({"prev": prev_hash, "ts": ts, "user": user_id, "action": action,
                       "entity": entity, "entity_id": entity_id, "detail": detail},
                      sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def _ts(value) -> str:
    # SQLite drops tzinfo on read-back; normalise so the hash is stable across backends.
    return value.replace(tzinfo=None).isoformat(timespec="microseconds")


def record(db: Session, action: str, user: User | None = None, entity: str = "", entity_id="",
           detail: dict | None = None, commit: bool = True) -> AuditLog:
    detail = json.loads(json.dumps(detail or {}, default=str))
    with _lock:
        last = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).scalar_one_or_none()
        prev = last.hash if last else GENESIS
        ts = utcnow()
        uid = user.id if user else None
        entry = AuditLog(ts=ts, user_id=uid, user_email=user.email if user else None, action=action,
                         entity=entity, entity_id=str(entity_id), detail=detail, prev_hash=prev,
                         hash=_digest(prev, _ts(ts), uid, action, entity, str(entity_id), detail))
        db.add(entry)
        if commit:
            db.commit()
        else:
            db.flush()
    return entry


def verify_chain(db: Session) -> dict:
    prev = GENESIS
    count = 0
    for row in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars():
        expected = _digest(prev, _ts(row.ts), row.user_id, row.action, row.entity, row.entity_id, row.detail)
        if row.prev_hash != prev or row.hash != expected:
            return {"valid": False, "broken_at_id": row.id, "checked": count}
        prev = row.hash
        count += 1
    return {"valid": True, "checked": count, "head": prev}
