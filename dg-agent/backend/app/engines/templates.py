"""Structured report templates: HIRA, JSA, chemical RA, RCA, toolbox talk, drill evaluation, incident report."""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import risk, spill

REPORT_TYPES = {
    "hira": "Hazard Identification and Risk Assessment (HIRA)",
    "jsa": "Job Safety Analysis (JSA)",
    "chemical_ra": "Chemical Risk Assessment",
    "rca": "Root Cause Analysis",
    "toolbox_talk": "Toolbox Talk",
    "drill_evaluation": "Emergency Drill Evaluation",
    "spill_incident": "Spill Incident Report",
}
REQ = "[REQUIRED INPUT: {}]"


def build(db: Session, kind: str, data: dict, matrix_cfg: dict) -> dict:
    if kind not in REPORT_TYPES:
        raise ValueError(f"Unknown report type '{kind}'")
    missing = []

    def g(key, label):
        v = data.get(key)
        if v in (None, "", []):
            missing.append(label)
            return REQ.format(label)
        return v

    body: dict = {"title": data.get("title") or REPORT_TYPES[kind], "type": REPORT_TYPES[kind],
                  "activity_or_site": g("activity", "activity / location")}
    if kind in ("hira", "chemical_ra"):
        rows = data.get("rows") or []
        if not rows:
            missing.append("hazard rows")
        body["rows"] = risk.assess_rows(matrix_cfg, rows)
        body["matrix"] = matrix_cfg
        if kind == "chemical_ra":
            body["substances"] = g("substances", "substances (name, UN, CAS, quantity)")
            body["exposure_routes"] = g("exposure_routes", "exposure routes and duration")
            body["sds_references"] = g("sds_references", "SDS references (revision dates)")
    elif kind == "jsa":
        steps = data.get("steps") or []
        if not steps:
            missing.append("job steps")
        body["steps"] = [{**s, "rating": risk.assess_rows(matrix_cfg, [s])[0].get("initial_rating")} for s in steps]
        body["required_ppe"] = g("required_ppe", "required PPE (from SDS Section 8 / site rules)")
        body["permits"] = data.get("permits") or []
    elif kind == "rca":
        body["incident_summary"] = g("incident_summary", "incident summary")
        body["five_whys"] = data.get("five_whys") or [REQ.format("why 1..5")]
        body["contributing_factors"] = {c: data.get("factors", {}).get(c, []) for c in
                                        ("People", "Procedures", "Equipment / packaging", "Materials",
                                         "Environment", "Management / organisation")}
        body["root_causes"] = g("root_causes", "root cause(s) agreed by investigation team")
        body["capa"] = data.get("capa") or []
    elif kind == "toolbox_talk":
        a = spill.assess(db, {"un_number": data.get("un_number"), "hazard_class": data.get("hazard_class"),
                              "chemical_name": data.get("chemical_name"), "trained_responders_available": True,
                              "quantity_estimate": 0})
        body["topic"] = data.get("topic") or f"Safe handling: {data.get('chemical_name') or data.get('un_number') or 'dangerous goods'}"
        body["key_hazards"] = a["hazard_assessment"]
        body["precautions"] = a["precautions_do_not"]
        body["if_spill_occurs"] = a["immediate_priorities"][:5]
        body["discussion_points"] = ["Where is the SDS kept and what do Sections 4, 6 and 8 say?",
                                     "Where are the spill kit, eyewash and muster point?",
                                     "Who do you call first?"]
        body["attendance"] = data.get("attendance") or [REQ.format("attendee names and signatures")]
    elif kind == "drill_evaluation":
        body["scenario"] = g("scenario", "drill scenario")
        body["objectives"] = data.get("objectives") or [REQ.format("drill objectives")]
        crit = data.get("criteria") or [
            {"criterion": "Alarm raised promptly"}, {"criterion": "Area isolated and cordoned"},
            {"criterion": "Head count completed at muster point"}, {"criterion": "Correct escalation / notifications"},
            {"criterion": "Responders used correct PPE per plan"}, {"criterion": "Communication effective"}]
        body["criteria"] = [{**c, "rating": c.get("rating") or REQ.format("rating (met / partially / not met)")} for c in crit]
        body["timeline"] = data.get("timeline") or []
        body["improvements"] = data.get("improvements") or []
    elif kind == "spill_incident":
        body["incident"] = {k: data.get(k) or REQ.format(k.replace("_", " ")) for k in
                            ("date_time", "location", "material", "quantity_released", "cause", "persons_involved",
                             "actions_taken", "notifications_made")}
        body["response_assessment"] = spill.assess(db, data.get("spill") or {})
    body["missing_information"] = missing
    return body
