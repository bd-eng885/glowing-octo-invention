"""Regulatory Source Library: catalogue, edition control, controlled import and verification."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .. import audit
from ..db import get_db
from ..engines import dg as dg_engine
from ..engines import textutil as tu
from ..engines.provenance import effective_status, table_is_authoritative
from ..models import RULE_SETS, SOURCE_STATUS, DGEntry, RegulatorySource, RuleTable, User, utcnow
from ..seed import import_entries
from ..security import current_user, require

router = APIRouter(prefix="/api/sources", tags=["regulatory sources"])


def src_out(s: RegulatorySource) -> dict:
    return {"id": s.id, "code": s.code, "rule_set": s.rule_set, "publisher": s.publisher, "title": s.title,
            "edition": s.edition, "amendment": s.amendment,
            "publication_date": s.publication_date, "effective_date": s.effective_date, "expiry_date": s.expiry_date,
            "licence": s.licence, "authorized_usage": s.authorized_usage, "location": s.location,
            "ingestion_date": s.ingestion_date, "verification_status": s.verification_status,
            "stored_status": s.status, "effective_status": effective_status(s), "content_loaded": s.content_loaded,
            "entry_count": len(s.entries), "notes": s.notes}


@router.get("")
def list_sources(db: Session = Depends(get_db), _: User = Depends(current_user)):
    rows = db.execute(select(RegulatorySource).options(selectinload(RegulatorySource.entries))
                      .order_by(RegulatorySource.rule_set, RegulatorySource.code)).scalars()
    return [src_out(s) for s in rows]


@router.get("/coverage")
def coverage(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return {m: dg_engine.mode_coverage(db, m) for m in dg_engine.MODES}


class SourceIn(BaseModel):
    code: str
    rule_set: str
    publisher: str
    title: str
    edition: str = ""
    amendment: str = ""
    publication_date: dt.date | None = None
    effective_date: dt.date | None = None
    expiry_date: dt.date | None = None
    licence: str = ""
    authorized_usage: str = ""
    location: str = ""
    status: str = "current"
    notes: str = ""


@router.post("")
def create_source(body: SourceIn, db: Session = Depends(get_db), user: User = Depends(require("manage_sources"))):
    if body.rule_set not in RULE_SETS or body.status not in SOURCE_STATUS:
        raise HTTPException(422, f"rule_set must be in {RULE_SETS}; status in {SOURCE_STATUS}")
    if db.execute(select(RegulatorySource).where(RegulatorySource.code == body.code)).scalar_one_or_none():
        raise HTTPException(409, "Source code exists")
    s = RegulatorySource(**body.model_dump(), verification_status="unverified", content_loaded=False)
    db.add(s)
    db.flush()
    audit.record(db, "source.create", user, "source", s.id, body.model_dump(mode="json"))
    return {"id": s.id}


class StatusIn(BaseModel):
    status: str
    note: str = ""


@router.post("/{sid}/status")
def set_status(sid: int, body: StatusIn, db: Session = Depends(get_db), user: User = Depends(require("manage_sources"))):
    s = db.get(RegulatorySource, sid)
    if not s or body.status not in SOURCE_STATUS:
        raise HTTPException(404 if not s else 422, "Invalid source or status")
    old = s.status
    s.status = body.status
    audit.record(db, "source.status", user, "source", sid, {"from": old, "to": body.status, "note": body.note})
    return src_out(s)


@router.post("/{sid}/verify")
def verify_source(sid: int, body: StatusIn, db: Session = Depends(get_db),
                  user: User = Depends(require("verify_regulatory_data"))):
    """A qualified data steward attests the source record (edition, licence, dates) is correct."""
    s = db.get(RegulatorySource, sid)
    if not s:
        raise HTTPException(404, "Not found")
    if s.verification_status in ("demo_seed", "test_fixture"):
        raise HTTPException(400, "Demonstration or test data cannot be marked verified. Import lawfully obtained "
                                 "data into a new source instead.")
    s.verification_status = "verified"
    audit.record(db, "source.verify", user, "source", sid, {"note": body.note})
    return src_out(s)


ENTRY_FIELDS = ("un_number", "variant", "proper_shipping_name", "hazard_class", "subsidiary_hazards", "packing_groups",
                "special_provisions", "marine_pollutant", "mode_data", "section_ref", "synonyms", "cas_numbers", "notes")
LIST_FIELDS = ("subsidiary_hazards", "packing_groups", "synonyms", "cas_numbers", "special_provisions")


def _parse_rows(raw: bytes, filename: str) -> list[dict]:
    if filename.lower().endswith(".json"):
        rows = json.loads(raw)
    else:
        rows = []
        for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
            row = {k: v for k, v in r.items() if k in ENTRY_FIELDS}
            # Lists are '|'-separated. special_provisions: blank = NOT LOADED, '-' = none assigned.
            for f in LIST_FIELDS:
                if f in row:
                    val = (row[f] or "").strip()
                    if f == "special_provisions" and val == "":
                        row[f] = None
                    else:
                        row[f] = [x.strip() for x in val.split("|") if x.strip() and x.strip() != "-"]
            if "mode_data" in row:
                row["mode_data"] = json.loads(row["mode_data"] or "{}")
            rows.append(row)
    cleaned, errors = [], []
    for i, r in enumerate(rows, 1):
        un, _ = tu.normalize_un(str(r.get("un_number", "")))
        if not un or not r.get("proper_shipping_name") or not r.get("hazard_class"):
            errors.append(f"row {i}: un_number, proper_shipping_name and hazard_class are required")
            continue
        r = {k: v for k, v in r.items() if k in ENTRY_FIELDS}
        r["un_number"] = un
        r["hazard_class"] = tu.normalize_class(r["hazard_class"])
        r.setdefault("subsidiary_hazards", [])
        r.setdefault("packing_groups", [])
        r["packing_groups"] = [tu.normalize_pg(p) for p in r["packing_groups"] if tu.normalize_pg(p)]
        cleaned.append(r)
    if errors:
        raise HTTPException(422, {"message": "Import rejected; no rows were imported.", "errors": errors[:50]})
    return cleaned


@router.post("/{sid}/import")
async def import_dataset(sid: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                         user: User = Depends(require("manage_sources"))):
    """Controlled import of lawfully obtained data. Imported entries start UNVERIFIED."""
    s = db.get(RegulatorySource, sid)
    if not s:
        raise HTTPException(404, "Not found")
    if s.verification_status in ("demo_seed",):
        raise HTTPException(400, "Cannot import into a demonstration source.")
    raw = await file.read()
    rows = _parse_rows(raw, file.filename or "upload.csv")
    n = import_entries(db, s, rows, "unverified")
    s.content_loaded = s.content_loaded or n > 0
    if s.status == "catalogue_only" and n:
        s.status = "current"
    audit.record(db, "source.import", user, "source", sid, {"file": file.filename, "imported": n, "rows": len(rows)})
    return {"imported": n, "skipped_existing": len(rows) - n, "verification_status": "unverified",
            "next_step": "Each entry must be verified against the source text by a DGSA approver."}


@router.get("/entries")
def search_entries(q: str = "", rule_set: str | None = None, db: Session = Depends(get_db),
                   _: User = Depends(current_user)):
    stmt = select(DGEntry).join(RegulatorySource).options(selectinload(DGEntry.source))
    if rule_set:
        stmt = stmt.where(RegulatorySource.rule_set == rule_set)
    if q:
        un, _n = tu.normalize_un(q)
        like = f"%{q.upper()}%"
        stmt = stmt.where(or_(DGEntry.un_number == (un or q.upper()), DGEntry.proper_shipping_name.ilike(like)))
    return [dg_engine.entry_view(e) for e in db.execute(stmt.order_by(DGEntry.un_number).limit(200)).scalars()]


class VerifyEntryIn(BaseModel):
    verification_ref: str  # e.g. "Checked against IMDG Code 2024 Ed., Vol 2, DGL row for UN1203"
    decision: str = "verified"  # verified | rejected


@router.post("/entries/{eid}/verify")
def verify_entry(eid: int, body: VerifyEntryIn, db: Session = Depends(get_db),
                 user: User = Depends(require("verify_regulatory_data"))):
    e = db.get(DGEntry, eid)
    if not e:
        raise HTTPException(404, "Not found")
    if e.source.verification_status in ("demo_seed", "test_fixture"):
        raise HTTPException(400, "Demonstration/test entries cannot be marked verified.")
    if not body.verification_ref.strip():
        raise HTTPException(422, "verification_ref (what was checked, where) is required")
    e.verification_status = "verified" if body.decision == "verified" else "rejected"
    e.verified_by = f"{user.full_name or user.email} ({user.qualification or 'qualification not recorded'})"
    e.verified_at = utcnow()
    e.verification_ref = body.verification_ref
    audit.record(db, "entry.verify", user, "dg_entry", eid, {"decision": e.verification_status, "ref": body.verification_ref})
    return dg_engine.entry_view(e)


@router.get("/rule-tables")
def rule_tables(db: Session = Depends(get_db), _: User = Depends(current_user)):
    out = []
    for t in db.execute(select(RuleTable).options(selectinload(RuleTable.source))).scalars():
        ok, reasons = table_is_authoritative(t)
        out.append({"id": t.id, "code": t.code, "name": t.name, "section_ref": t.section_ref, "complete": t.complete,
                    "verification_status": t.verification_status, "source_code": t.source.code,
                    "authoritative": ok, "limitations": reasons, "data": t.data})
    return out
