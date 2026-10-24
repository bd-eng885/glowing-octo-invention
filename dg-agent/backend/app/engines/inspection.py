"""Container / package / cargo inspection.

Visible observations are kept distinct from verified non-compliance: a finding can only be
recorded as VERIFIED NON-COMPLIANCE when it is supported by document verification. A
photograph alone cannot establish chemical identity or full regulatory compliance.
"""
from __future__ import annotations

CHECKLIST = [
    ("id_container", "identification", "Container / package identification legible and matches documents", 3),
    ("un_psn_marked", "marking", "UN number and Proper Shipping Name marked on packages", 4),
    ("hazard_labels", "marking", "Hazard labels (primary and subsidiary) present and correct", 4),
    ("placards", "marking", "Placards on CTU where applicable", 3),
    ("mp_mark", "marking", "Marine pollutant mark where applicable", 3),
    ("pkg_damage", "condition", "No packaging damage or leakage", 5),
    ("corrosion", "condition", "No visible corrosion, deformation or contamination", 4),
    ("heat_smoke", "condition", "No signs of heat, smoke, vapour or pressure-related damage", 5),
    ("dgd_complete", "documents", "Dangerous Goods Declaration complete and consistent", 4),
    ("sds_available", "documents", "SDS available for each product", 3),
    ("seal_docs", "documents", "Seal number and cargo documents consistent", 3),
    ("segregation", "storage", "Segregation and storage conditions as required", 5),
    ("emergency_access", "readiness", "Emergency access clear; spill kit and fire equipment available", 4),
]
RESULTS = ("ok", "observation", "nonconformity", "na", "not_checked")
EVIDENCE = ("visual_observation", "document_verified", "measurement", "not_checked")


def checklist() -> list[dict]:
    return [{"key": k, "category": c, "label": label, "default_severity": s} for k, c, label, s in CHECKLIST]


def evaluate(items: list[dict], matrix_cfg: dict, rate_fn) -> dict:
    by_key = {k: (c, label, s) for k, c, label, s in CHECKLIST}
    rows, actions = [], []
    counts = {r: 0 for r in RESULTS}
    for it in items:
        key = it.get("key")
        cat, label, sev = by_key.get(key, ("custom", it.get("label", key), 3))
        result = it.get("result", "not_checked")
        if result not in RESULTS:
            result = "not_checked"
        evidence = it.get("evidence_type") or ("not_checked" if result == "not_checked" else "visual_observation")
        classification = {"ok": "Satisfactory (as observed)", "na": "Not applicable",
                          "not_checked": "NOT CHECKED", "observation": "Visual observation — requires follow-up"}.get(result)
        if result == "nonconformity":
            if evidence == "document_verified" or evidence == "measurement":
                classification = "VERIFIED NON-COMPLIANCE"
            else:
                classification = "SUSPECTED NON-COMPLIANCE — visual only, requires verification"
        counts[result] += 1
        row = {"key": key, "category": cat, "label": label, "result": result, "evidence_type": evidence,
               "classification": classification, "comment": it.get("comment", ""),
               "photo_ids": it.get("photo_ids", [])}
        if result in ("observation", "nonconformity"):
            L = int(it.get("likelihood") or 3)
            S = int(it.get("severity") or min(sev, len(matrix_cfg["severity"])))
            row["risk"] = rate_fn(matrix_cfg, min(L, len(matrix_cfg["likelihood"])), min(S, len(matrix_cfg["severity"])))
            actions.append({"item": key, "description": it.get("corrective_action") or f"Rectify: {label}",
                            "responsible": it.get("responsible") or "[REQUIRED INPUT: responsible person]",
                            "due_date": it.get("due_date"), "status": "open"})
        rows.append(row)
    checked_keys = {it.get("key") for it in items}
    not_covered = [label for k, _, label, _ in CHECKLIST if k not in checked_keys]
    critical = [r for r in rows if r["result"] in ("observation", "nonconformity")
                and r["key"] in ("pkg_damage", "heat_smoke")]
    if critical:
        overall = "STOP — QUARANTINE CARGO AND NOTIFY EMERGENCY / DG RESPONSIBLE PERSON"
    elif counts["nonconformity"] or counts["observation"]:
        overall = "HOLD — CORRECTIVE ACTION AND QUALIFIED REVIEW REQUIRED"
    elif counts["not_checked"] or not_covered:
        overall = "INCOMPLETE — NOT ALL CHECKS PERFORMED"
    else:
        overall = "NO DEFECTS OBSERVED — QUALIFIED REVIEW REQUIRED BEFORE ACCEPTANCE"
    return {"rows": rows, "counts": counts, "not_covered": not_covered, "corrective_actions": actions,
            "overall": overall,
            "limitations": ["Visual inspection cannot establish chemical identity or full regulatory compliance.",
                            "Photographs are supporting evidence only."]}
