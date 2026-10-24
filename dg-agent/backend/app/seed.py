"""Idempotent seeding: source catalogue, demo datasets, default risk matrix, users.

Usage:  python -m app.seed
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit
from .config import settings
from .db import SessionLocal, init_db
from .engines.risk import DEFAULT_MATRIX
from .models import DGEntry, RegulatorySource, RiskMatrix, RuleTable, User
from .security import hash_password

SEED = Path(__file__).parent / "data" / "seed"
log = logging.getLogger("dg.seed")

DEMO_USERS = [
    ("admin@demo.local", "Demo Administrator", "admin", ""),
    ("approver@demo.local", "Demo DGSA Approver", "dgsa_approver", "DEMO — qualification to be recorded"),
    ("reviewer@demo.local", "Demo DG Reviewer", "dg_reviewer", ""),
    ("operator@demo.local", "Demo Operator", "operator", ""),
    ("viewer@demo.local", "Demo Viewer", "viewer", ""),
]


def _date(v):
    return dt.date.fromisoformat(v) if v else None


def upsert_source(db: Session, s: dict) -> RegulatorySource:
    src = db.execute(select(RegulatorySource).where(RegulatorySource.code == s["code"])).scalar_one_or_none()
    if src:
        return src
    src = RegulatorySource(**{**s, "publication_date": _date(s.get("publication_date")),
                              "effective_date": _date(s.get("effective_date")),
                              "expiry_date": _date(s.get("expiry_date"))})
    db.add(src)
    db.flush()
    return src


def import_entries(db: Session, src: RegulatorySource, rows: list[dict], verification_status: str = "unverified") -> int:
    n = 0
    for r in rows:
        exists = db.execute(select(DGEntry).where(DGEntry.source_id == src.id, DGEntry.un_number == r["un_number"],
                                                  DGEntry.variant == r.get("variant", ""))).scalar_one_or_none()
        if exists:
            continue
        db.add(DGEntry(source_id=src.id, verification_status=r.get("verification_status", verification_status),
                       **{k: v for k, v in r.items() if k != "verification_status"}))
        n += 1
    return n


def seed(db: Session, demo: bool | None = None) -> dict:
    demo = settings.seed_demo_data if demo is None else demo
    summary = {}
    if demo:
        srcs = {s["code"]: upsert_source(db, s) for s in json.loads((SEED / "sources.json").read_text())}
        summary["entries"] = import_entries(db, srcs["DEMO-UN-SEED"],
                                            json.loads((SEED / "un_entries_demo.json").read_text()), "demo_seed")
        for code, src_code, name, fname in [
            ("IMDG-SEG-DEMO", "DEMO-IMDG-SEG-SEED", "IMDG general segregation table (demo)", "imdg_segregation_table_demo.json"),
            ("IATA-SEG-DEMO", "DEMO-IATA-SEG-SEED", "IATA package segregation pairs (demo, partial)", "iata_segregation_demo.json")]:
            if not db.execute(select(RuleTable).where(RuleTable.code == code)).scalar_one_or_none():
                data = json.loads((SEED / fname).read_text())
                db.add(RuleTable(code=code, source_id=srcs[src_code].id, name=name, data=data,
                                 section_ref=data.get("section_ref", ""), complete=code.startswith("IMDG"),
                                 verification_status="demo_seed"))
    if not db.execute(select(RiskMatrix)).first():
        db.add(RiskMatrix(name=DEFAULT_MATRIX["name"], config=DEFAULT_MATRIX, is_default=True))
    users = []
    if settings.initial_admin_email and settings.initial_admin_password:
        users.append((settings.initial_admin_email, "Administrator", "admin", "", settings.initial_admin_password))
    if demo and settings.demo_users_password:
        users += [(*u, settings.demo_users_password) for u in DEMO_USERS]
    for email, name, role, qual, pw in users:
        if not db.execute(select(User).where(User.email == email)).scalar_one_or_none():
            db.add(User(email=email, full_name=name, role=role, qualification=qual, password_hash=hash_password(pw)))
    db.commit()
    audit.record(db, "system.seed", detail={"demo": demo, **summary})
    return summary


def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    with SessionLocal() as db:
        print("Seeded:", seed(db))
        if not db.execute(select(User)).first():
            print("WARNING: no users exist. Set INITIAL_ADMIN_EMAIL/INITIAL_ADMIN_PASSWORD (or DEMO_USERS_PASSWORD) and re-run.")


if __name__ == "__main__":
    main()
