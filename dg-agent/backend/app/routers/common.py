from __future__ import annotations

from sqlalchemy.orm import Session

from .. import audit
from ..models import Report, User


def persist(db: Session, user: User, kind: str, title: str, inputs: dict, content: dict,
            criticality: str = "critical") -> Report:
    rep = Report(kind=kind, title=title, inputs=inputs, content=content, created_by=user.id,
                 criticality=criticality, status="draft")
    db.add(rep)
    db.flush()
    audit.record(db, f"report.create.{kind}", user, "report", rep.id,
                 {"title": title, "status": content.get("status") or content.get("decision")
                  or content.get("response_level") or content.get("overall")}, commit=False)
    db.commit()
    return rep


def analysis_audit(db: Session, user: User, action: str, detail: dict):
    audit.record(db, action, user, detail=detail)
