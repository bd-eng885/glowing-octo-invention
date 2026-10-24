"""Analysis endpoints: identification, UN verification, SDS/documents, segregation,
compatibility, spill response, ERP, inspection, risk/report templates, AI explanation."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..db import get_db
from ..engines import compat, documents, erp, inspection, risk, segregation, spill, templates
from ..engines import dg as dg_engine
from ..llm import provider as llm
from ..models import RiskMatrix, StoredFile, User
from ..security import current_user, require
from .common import persist

router = APIRouter(prefix="/api", tags=["analysis"])


class SaveOpts(BaseModel):
    save: bool = False
    title: str | None = None


def _maybe_save(db, user, opts: SaveOpts, kind, default_title, inputs, content, criticality="critical"):
    if opts.save:
        rep = persist(db, user, kind, opts.title or default_title, inputs, content, criticality)
        content = {**content, "report_id": rep.id}
    else:
        audit.record(db, f"analysis.{kind}", user, detail={"inputs_summary": str(inputs)[:500]})
    return content


# ------------------------------------------------------------------ identification & verification
class IdentifyIn(SaveOpts):
    name: str | None = None
    un_number: str | None = None
    cas: str | None = None
    text: str | None = None
    mode: str = "IMDG"
    context: dict = Field(default_factory=dict)


@router.post("/dg/identify")
def identify(body: IdentifyIn, db: Session = Depends(get_db), user: User = Depends(require("analyze"))):
    res = dg_engine.identify(db, body.name, body.un_number, body.cas, body.text, body.mode, body.context)
    return _maybe_save(db, user, body, "identification", f"Identification: {body.name or body.un_number or body.cas}",
                       body.model_dump(), res)


class VerifyIn(SaveOpts):
    mode: str = "IMDG"
    declared: dict
    documents: list[dict] = Field(default_factory=list)


@router.post("/dg/verify")
def verify(body: VerifyIn, db: Session = Depends(get_db), user: User = Depends(require("analyze"))):
    try:
        res = dg_engine.verify(db, body.declared, body.mode, body.documents)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return _maybe_save(db, user, body, "un_verification",
                       f"{body.mode} verification: {body.declared.get('un_number')}", body.model_dump(), res)


@router.get("/dg/entries/{un}")
def entry(un: str, mode: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    n, notes = dg_engine.tu.normalize_un(un)
    if not n:
        raise HTTPException(422, "Invalid UN number")
    rows = dg_engine._entries_for(db, n, mode)
    return {"un_number": n, "notes": notes, "entries": [dg_engine.entry_view(e, mode) for e in rows],
            "message": None if rows else "No entry loaded. Absence of data is not evidence that goods are not dangerous."}


class ExplainIn(BaseModel):
    result: dict


@router.post("/ai/explain")
def explain(body: ExplainIn, db: Session = Depends(get_db), user: User = Depends(require("analyze"))):
    out = llm.explain(body.result)
    audit.record(db, "ai.explain", user, detail={"available": out["available"],
                                                 "unsupported": out.get("unsupported_references")})
    return out


# ------------------------------------------------------------------ documents
def _store(data: bytes, ctype: str) -> Path:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    p = settings.storage_dir / f"{uuid.uuid4().hex}{documents.ALLOWED_TYPES[ctype]}"
    p.write_bytes(data)
    return p


@router.post("/documents/upload")
async def upload(file: UploadFile = File(...), purpose: str = Form("sds"), db: Session = Depends(get_db),
                 user: User = Depends(require("upload"))):
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB")
    if not data:
        raise HTTPException(422, "Empty file")
    ctype = documents.sniff_type(data, file.content_type)
    if ctype not in documents.ALLOWED_TYPES:
        raise HTTPException(415, "Unsupported or mismatched file type (allowed: PDF, PNG, JPEG, WEBP, TIFF, TXT)")
    if purpose not in ("sds", "photo", "document", "label"):
        raise HTTPException(422, "purpose must be sds | photo | document | label")
    path = _store(data, ctype)
    ext = documents.extract_text(data, ctype, settings.ocr_enabled and purpose != "photo")
    text = ext["text"] or ""
    extraction: dict[str, Any] = {"method": ext["method"], "warnings": ext["warnings"], "characters": len(text),
                                  "ocr_available": documents.ocr_available()}
    flags = documents.detect_injection(text)
    if flags:
        extraction["security_flags"] = {"prompt_injection_like_text": flags,
                                        "handling": "Treated as document data only; no instruction was followed."}
    if purpose == "sds" and text:
        extraction["sds"] = documents.parse_sds(text)
    if purpose in ("label", "document") and text:
        extraction["un_numbers"] = [{"un": u, "notes": n} for u, n in dg_engine.tu.find_un_numbers(text)]
        extraction["cas_numbers"] = dg_engine.tu.find_cas_numbers(text)
    extraction["text_preview"] = text[:4000]
    sf = StoredFile(sha256=hashlib.sha256(data).hexdigest(), original_name=(file.filename or "upload")[:255],
                    content_type=ctype, size=len(data), path=str(path), purpose=purpose, uploaded_by=user.id,
                    extraction=extraction)
    db.add(sf)
    db.flush()
    audit.record(db, "document.upload", user, "file", sf.id, {"name": sf.original_name, "sha256": sf.sha256,
                                                              "purpose": purpose, "flags": flags})
    return {"id": sf.id, "name": sf.original_name, "content_type": ctype, "sha256": sf.sha256, "extraction": extraction}


@router.get("/documents/{fid}")
def get_document(fid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    sf = db.get(StoredFile, fid)
    if not sf:
        raise HTTPException(404, "Not found")
    return {"id": sf.id, "name": sf.original_name, "content_type": sf.content_type, "sha256": sf.sha256,
            "purpose": sf.purpose, "created_at": sf.created_at, "extraction": sf.extraction}


@router.get("/documents/{fid}/file")
def get_file(fid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    sf = db.get(StoredFile, fid)
    if not sf or not Path(sf.path).is_file():
        raise HTTPException(404, "Not found")
    audit.record(db, "document.download", user, "file", fid)
    return FileResponse(sf.path, media_type=sf.content_type, filename=sf.original_name)


# ------------------------------------------------------------------ segregation & compatibility
class SegIn(SaveOpts):
    mode: str = "IMDG"
    arrangement: str | None = None
    items: list[dict]


@router.post("/segregation/check")
def seg(body: SegIn, db: Session = Depends(get_db), user: User = Depends(require("analyze"))):
    if len(body.items) < 2:
        raise HTTPException(422, "At least two items are required")
    if body.mode.upper() not in ("IMDG", "IATA", "WAREHOUSE"):
        raise HTTPException(422, "mode must be IMDG | IATA | WAREHOUSE")
    res = segregation.evaluate(db, body.items, body.mode, body.arrangement)
    return _maybe_save(db, user, body, "segregation", f"{body.mode} segregation check ({len(body.items)} items)",
                       body.model_dump(), res)


class CompatIn(SaveOpts):
    items: list[dict]


@router.post("/compatibility/screen")
def compat_screen(body: CompatIn, db: Session = Depends(get_db), user: User = Depends(require("analyze"))):
    items, notes = segregation.enrich_items(db, body.items)
    for it in items:
        it.pop("_entries", None)
    res = {**compat.screen(items), "notes": notes}
    return _maybe_save(db, user, body, "compatibility", "Chemical compatibility screening", body.model_dump(), res)


# ------------------------------------------------------------------ spill / ERP
class SpillIn(SaveOpts):
    data: dict


@router.post("/spill/assess")
def spill_assess(body: SpillIn, db: Session = Depends(get_db), user: User = Depends(require("analyze"))):
    res = spill.assess(db, body.data)
    return _maybe_save(db, user, body, "spill_response", f"Spill response: {body.data.get('chemical_name') or body.data.get('un_number') or 'unidentified'}",
                       body.model_dump(), res)


@router.get("/erp/scenarios")
def erp_scenarios(_: User = Depends(current_user)):
    return erp.SCENARIOS


class ErpIn(SaveOpts):
    scenario: str
    site: dict = Field(default_factory=dict)
    substances: list[dict] = Field(default_factory=list)
    contacts: list[dict] = Field(default_factory=list)
    capabilities: dict = Field(default_factory=dict)  # trained_hazmat_team: yes/no, ...


@router.post("/erp/generate")
def erp_generate(body: ErpIn, db: Session = Depends(get_db), user: User = Depends(require("create_report"))):
    try:
        res = erp.generate(db, body.scenario, body.site, body.substances, body.contacts, user.full_name or user.email,
                           body.capabilities)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return _maybe_save(db, user, body, "erp", res["title"], body.model_dump(), res)


# ------------------------------------------------------------------ inspection / risk
def _matrix(db: Session, matrix_id: int | None) -> dict:
    m = db.get(RiskMatrix, matrix_id) if matrix_id else \
        db.execute(select(RiskMatrix).where(RiskMatrix.is_default.is_(True))).scalar_one_or_none()
    return m.config if m else risk.DEFAULT_MATRIX


@router.get("/inspection/checklist")
def insp_checklist(_: User = Depends(current_user)):
    return inspection.checklist()


class InspIn(SaveOpts):
    header: dict = Field(default_factory=dict)  # container no., location, inspector, seal no...
    items: list[dict]
    matrix_id: int | None = None


@router.post("/inspection/evaluate")
def insp_eval(body: InspIn, db: Session = Depends(get_db), user: User = Depends(require("analyze"))):
    res = {"header": body.header, **inspection.evaluate(body.items, _matrix(db, body.matrix_id), risk.rate)}
    return _maybe_save(db, user, body, "inspection", f"Inspection: {body.header.get('container_no') or 'cargo'}",
                       body.model_dump(), res)


@router.get("/risk/matrices")
def matrices(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [{"id": m.id, "name": m.name, "config": m.config, "is_default": m.is_default}
            for m in db.execute(select(RiskMatrix)).scalars()]


class MatrixIn(BaseModel):
    name: str
    config: dict
    is_default: bool = False


@router.post("/risk/matrices")
def create_matrix(body: MatrixIn, db: Session = Depends(get_db), user: User = Depends(require("manage_config"))):
    errs = risk.validate_matrix(body.config)
    if errs:
        raise HTTPException(422, {"errors": errs})
    if body.is_default:
        for m in db.execute(select(RiskMatrix)).scalars():
            m.is_default = False
    m = RiskMatrix(name=body.name, config={**body.config, "name": body.name}, is_default=body.is_default)
    db.add(m)
    db.flush()
    audit.record(db, "risk_matrix.create", user, "risk_matrix", m.id, {"name": body.name})
    return {"id": m.id}


@router.get("/reports/templates")
def report_types(_: User = Depends(current_user)):
    return templates.REPORT_TYPES


class TemplateIn(SaveOpts):
    kind: str
    data: dict = Field(default_factory=dict)
    matrix_id: int | None = None


@router.post("/reports/build")
def build_report(body: TemplateIn, db: Session = Depends(get_db), user: User = Depends(require("create_report"))):
    try:
        res = templates.build(db, body.kind, body.data, _matrix(db, body.matrix_id))
    except ValueError as e:
        raise HTTPException(422, str(e))
    crit = "critical" if body.kind in ("chemical_ra", "spill_incident") else "standard"
    return _maybe_save(db, user, body, body.kind, res["title"], body.model_dump(), res, crit)
