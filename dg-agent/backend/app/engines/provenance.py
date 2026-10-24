"""Source provenance and edition control used by every engine."""
from __future__ import annotations

import datetime as dt

from ..config import settings
from ..models import DGEntry, RegulatorySource, RuleTable


def effective_status(src: RegulatorySource, today: dt.date | None = None) -> str:
    """Status after applying effective/expiry dates to the stored status."""
    today = today or dt.date.today()
    if src.status in ("superseded", "catalogue_only"):
        return src.status
    if src.effective_date and src.effective_date > today:
        return "not_yet_effective"
    if src.expiry_date and src.expiry_date < today:
        return "superseded"
    return src.status


def source_record(src: RegulatorySource, section_ref: str = "", today: dt.date | None = None) -> dict:
    return {
        "source_code": src.code,
        "rule_set": src.rule_set,
        "publisher": src.publisher,
        "title": src.title,
        "edition": src.edition,
        "amendment": src.amendment,
        "effective_date": src.effective_date.isoformat() if src.effective_date else None,
        "section_ref": section_ref,
        "source_verification_status": src.verification_status,
        "source_status": effective_status(src, today),
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }


def entry_is_authoritative(entry: DGEntry, today: dt.date | None = None) -> tuple[bool, list[str]]:
    """An entry is authoritative only if source AND entry are verified and the edition is in force."""
    reasons = []
    src = entry.source
    st = effective_status(src, today)
    if src.verification_status == "demo_seed":
        reasons.append(f"Source '{src.code}' is DEMONSTRATION DATA, not an authoritative regulatory source.")
    elif src.verification_status == "test_fixture":
        if not settings.test_mode:
            reasons.append(f"Source '{src.code}' is a TEST FIXTURE.")
    elif src.verification_status != "verified":
        reasons.append(f"Source '{src.code}' has not been verified by a qualified data steward.")
    if st != "current":
        reasons.append(f"Source '{src.code}' edition status is '{st}' (not currently in force).")
    if entry.verification_status != "verified":
        reasons.append(f"Entry {entry.un_number} has not been verified against the source text "
                       f"(status: {entry.verification_status}).")
    return not reasons, reasons


def entry_evidence(entry: DGEntry, today: dt.date | None = None) -> dict:
    ok, reasons = entry_is_authoritative(entry, today)
    rec = source_record(entry.source, entry.section_ref, today)
    rec.update({
        "entry_id": entry.id,
        "un_number": entry.un_number,
        "entry_verification_status": entry.verification_status,
        "verified_by": entry.verified_by,
        "verified_at": entry.verified_at.isoformat() if entry.verified_at else None,
        "verification_ref": entry.verification_ref,
        "authoritative": ok,
        "limitations": reasons,
    })
    return rec


def table_is_authoritative(table: RuleTable, today: dt.date | None = None) -> tuple[bool, list[str]]:
    reasons = []
    src = table.source
    if src.verification_status == "demo_seed" or (src.verification_status == "test_fixture"
                                                  and not settings.test_mode):
        reasons.append(f"Rule table '{table.code}' comes from {src.verification_status.replace('_', ' ').upper()} "
                       "source and is not authoritative.")
    elif src.verification_status not in ("verified", "test_fixture") or table.verification_status != "verified":
        reasons.append(f"Rule table '{table.code}' has not been verified by a qualified person.")
    if effective_status(src, today) != "current":
        reasons.append(f"Rule table source '{src.code}' is not currently in force.")
    if not table.complete:
        reasons.append(f"Rule table '{table.code}' is a partial subset; absent rules are not evidence of compliance.")
    return not reasons, reasons
