"""Reports, human review/approval workflow, CAPA register, exports and audit trail."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import audit
from ..db import get_db
from ..exports.render import EXPORTERS
from ..models import AuditLog, CorrectiveAction, Report, User, utcnow
from ..security import current_user, has_perm, require

router = APIRouter(prefix="/api", tags=["reports & audit"])


def rep_out(r: Report, full: bool = False) -> dict:
    d = {"id": r.id, "kind": r.kind, "title": r.title, "status": r.status, "criticality": r.criticality,
         "created_by": r.created_by, "created_at": r.created_at, "updated_at": r.updated_at,
         "approvals": [{"id": a.id, "user_id": a.user_id, "decision": a.decision, "comment": a.comment,
                        "qualification": a.qualification, "created_at": a.created_at} for a in r.approvals]}
    if full:
        d.update(content=r.content, inputs=r.inputs)
    return d


@router.get("/reports")
def list_reports(kind: str | None = None, status: str | None = None, db: Session = Depends(get_db),
                 _: User = Depends(current_user)):
    q = select(Report).options(selectinload(Report.approvals)).order_by(Report.id.desc())
    if kind:
        q = q.where(Report.kind == kind)
    if status:
        q = q.where(Report.status == status)
    return [rep_out(r) for r in db.execute(q.limit(500)).scalars()]


def _get(db, rid) -> Report:
    r = db.get(Report, rid)
    if not r:
        raise HTTPException(404, "Report not found")
    return r


@router.get("/reports/{rid}")
def get_report(rid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return rep_out(_get(db, rid), full=True)


class DecisionIn(BaseModel):
    comment: str = ""


def _approval(db, r: Report, user: User, decision: str, comment: str):
    from ..models import Approval

    a = Approval(report_id=r.id, user_id=user.id, decision=decision, comment=comment, qualification=user.qualification)
    db.add(a)
    db.flush()
    audit.record(db, f"report.{decision}", user, "report", r.id, {"comment": comment, "status": r.status}, commit=False)
    db.commit()
    db.refresh(r)
    return rep_out(r)


@router.post("/reports/{rid}/submit")
def submit(rid: int, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(require("submit_review"))):
    r = _get(db, rid)
    if r.status not in ("draft", "rejected"):
        raise HTTPException(409, f"Cannot submit a report in status '{r.status}'")
    r.status = "pending_review"
    return _approval(db, r, user, "submitted", body.comment)


@router.post("/reports/{rid}/review")
def review(rid: int, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(require("review"))):
    r = _get(db, rid)
    if r.status != "pending_review":
        raise HTTPException(409, "Report is not pending review")
    return _approval(db, r, user, "reviewed", body.comment)


@router.post("/reports/{rid}/approve")
def approve(rid: int, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    r = _get(db, rid)
    if not has_perm(user, "approve"):
        audit.record(db, "report.approve_denied", user, "report", rid, {"role": user.role})
        raise HTTPException(403, f"Role '{user.role}' is not authorised to approve. Approval requires an "
                                 "authorised DGSA approver.")
    if r.status != "pending_review":
        raise HTTPException(409, "Only reports pending review can be approved")
    if r.created_by == user.id:
        audit.record(db, "report.approve_denied", user, "report", rid, {"reason": "self-approval"})
        raise HTTPException(403, "Self-approval is not permitted; a different authorised approver is required.")
    if not body.comment.strip():
        raise HTTPException(422, "An approval comment stating the basis of the decision is required")
    r.status = "approved"
    return _approval(db, r, user, "approved", body.comment)


@router.post("/reports/{rid}/reject")
def reject(rid: int, body: DecisionIn, db: Session = Depends(get_db), user: User = Depends(require("review"))):
    r = _get(db, rid)
    if r.status != "pending_review":
        raise HTTPException(409, "Only reports pending review can be rejected")
    r.status = "rejected"
    return _approval(db, r, user, "rejected", body.comment)


@router.get("/reports/{rid}/export/{fmt}")
def export(rid: int, fmt: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if fmt not in EXPORTERS:
        raise HTTPException(422, f"format must be one of {list(EXPORTERS)}")
    r = db.execute(select(Report).options(selectinload(Report.approvals)).where(Report.id == rid)).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Report not found")
    fn, ctype = EXPORTERS[fmt]
    data = fn(r)
    audit.record(db, "report.export", user, "report", rid, {"format": fmt})
    return Response(data, media_type=ctype,
                    headers={"Content-Disposition": f'attachment; filename="dg-report-{rid}.{fmt}"'})


# ------------------------------------------------------------------ CAPA
class CapaIn(BaseModel):
    report_id: int | None = None
    description: str
    action_type: str = "corrective"
    responsible: str = ""
    due_date: dt.date | None = None


class CapaPatch(BaseModel):
    status: str | None = None
    closure_note: str | None = None
    responsible: str | None = None
    due_date: dt.date | None = None


def capa_out(c: CorrectiveAction) -> dict:
    return {k: getattr(c, k) for k in ("id", "report_id", "description", "action_type", "responsible", "due_date",
                                       "status", "closure_note", "closed_by", "closed_at", "created_at")}


@router.get("/capa")
def list_capa(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [capa_out(c) for c in db.execute(select(CorrectiveAction).order_by(CorrectiveAction.id.desc())).scalars()]


@router.post("/capa")
def create_capa(body: CapaIn, db: Session = Depends(get_db), user: User = Depends(require("create_report"))):
    c = CorrectiveAction(**body.model_dump())
    db.add(c)
    db.flush()
    audit.record(db, "capa.create", user, "capa", c.id, body.model_dump(mode="json"))
    return capa_out(c)


@router.patch("/capa/{cid}")
def update_capa(cid: int, body: CapaPatch, db: Session = Depends(get_db), user: User = Depends(require("create_report"))):
    c = db.get(CorrectiveAction, cid)
    if not c:
        raise HTTPException(404, "Not found")
    ch = body.model_dump(exclude_none=True)
    if ch.get("status") == "closed":
        if not (ch.get("closure_note") or c.closure_note):
            raise HTTPException(422, "Closure requires a closure note describing the evidence of completion")
        c.closed_by, c.closed_at = user.id, utcnow()
    for k, v in ch.items():
        setattr(c, k, v)
    audit.record(db, "capa.update", user, "capa", cid, {k: str(v) for k, v in ch.items()})
    return capa_out(c)


# ------------------------------------------------------------------ audit
@router.get("/audit")
def audit_list(limit: int = 200, db: Session = Depends(get_db), _: User = Depends(require("read"))):
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000))).scalars()
    return [{"id": a.id, "ts": a.ts, "user_email": a.user_email, "action": a.action, "entity": a.entity,
             "entity_id": a.entity_id, "detail": a.detail, "hash": a.hash[:16]} for a in rows]


@router.get("/audit/verify")
def audit_verify(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return audit.verify_chain(db)
