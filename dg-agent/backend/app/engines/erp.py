"""Emergency Response Plan generator: editable 18-section template.

Site-specific information that has not been supplied is emitted as
"[REQUIRED INPUT: ...]" and is never invented.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RegulatorySource
from . import spill
from .provenance import effective_status

SCENARIOS = {
    "chemical_spill": "Chemical spill or leak",
    "container_incident": "Dangerous goods container incident",
    "flammable_liquid_release": "Flammable liquid release",
    "toxic_gas_release": "Toxic gas release",
    "corrosive_spill": "Corrosive chemical spill",
    "oxidizer_incident": "Oxidizer incident",
    "chemical_fire": "Chemical fire",
    "damaged_package": "Damaged or leaking package",
    "loading_unloading": "DG incident during loading / unloading",
    "rail_truck_incident": "Rail-wagon or truck incident",
    "marine_pollutant_release": "Marine pollutant release / environmental emergency",
}


def req(label: str) -> str:
    return f"[REQUIRED INPUT: {label}]"


def _v(site: dict, key: str, label: str):
    v = site.get(key)
    return v if v not in (None, "", []) else req(label)


def _yes(v) -> bool | None:
    if v in (None, ""):
        return None
    return str(v).strip().lower() in ("1", "true", "yes", "y")


def source_references(db: Session) -> list[dict]:
    """Regulatory sources registered in the library, with their real verification state (never invented)."""
    out = []
    for s in db.execute(select(RegulatorySource).where(RegulatorySource.rule_set.in_(("IMDG", "IATA", "UN_MODEL")))
                        .order_by(RegulatorySource.rule_set, RegulatorySource.code)).scalars():
        st = effective_status(s)
        if st in ("superseded",):
            continue
        out.append({"source_code": s.code, "rule_set": s.rule_set, "publisher": s.publisher, "title": s.title,
                    "edition": f"{s.edition} {s.amendment}".strip(),
                    "effective_date": s.effective_date.isoformat() if s.effective_date else None,
                    "edition_status": st, "verification_status": s.verification_status,
                    "content_loaded": s.content_loaded,
                    "use_in_this_plan": "Reference only — content not loaded in this system" if not s.content_loaded
                    else ("DEMONSTRATION DATA — not authoritative" if s.verification_status == "demo_seed"
                          else ("Verified data" if s.verification_status == "verified" else "Unverified data"))})
    return out


def generate(db: Session, scenario: str, site: dict, substances: list[dict], contacts: list[dict] | None = None,
             author: str | None = None, capabilities: dict | None = None) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'")
    contacts = contacts or []
    cap = capabilities or {}
    trained = _yes(cap.get("trained_hazmat_team"))
    # The plan never assumes response capability: unknown capability is treated as "not available".
    subst_assess = [spill.assess(db, {**s, "trained_responders_available": bool(trained),
                                      "sds_available": s.get("sds_available"),
                                      "quantity_estimate": s.get("max_quantity")}) for s in substances]
    missing = []
    if trained is None:
        missing.append("on-site hazmat response capability (trained team yes/no)")

    def V(key, label):
        val = _v(site, key, label)
        if isinstance(val, str) and val.startswith("[REQUIRED INPUT"):
            missing.append(label)
        return val

    sections = []

    def add(title, content):
        sections.append({"number": len(sections) + 1, "title": title, "content": content})

    add("Purpose and scope", [
        f"This plan defines the response to: {SCENARIOS[scenario]} at {V('site_name', 'site name')}.",
        f"Applies to: {V('scope_areas', 'areas, operations and personnel covered')}.",
        "This plan is subordinate to applicable law, the competent authority's requirements and instructions of "
        "the emergency services.",
    ])
    add("Site information and scenario assumptions", [
        f"Site address / location: {V('address', 'site address and coordinates')}",
        f"Site description: {V('description', 'layout, storage areas, berths, rail/truck areas')}",
        f"Maximum DG inventory assumed: {V('max_inventory', 'maximum quantities by class and location')}",
        f"Environmental receptors: {V('receptors', 'drains, waterways, neighbouring populations')}",
        f"Scenario assumption: {site.get('scenario_assumptions') or req('credible worst-case scenario description')}",
    ])
    add("Emergency classification and escalation criteria", [
        "Level 1 — Minor: contained, identified material, no exposure, within site capability per approved procedure. "
        f"Site criteria: {V('level1_criteria', 'site-specific Level 1 criteria')}",
        "Level 2 — Site emergency: site ERT activation required.",
        "Level 3 — Major: external emergency services. Mandatory triggers include: unidentified material, fire, "
        "injury/exposure, toxic gas release, explosive/radioactive/infectious material, release to waterway, "
        "pressure receptacle failure, or no trained responders.",
    ])
    add("Roles and responsibilities", [
        f"Incident Controller: {V('incident_controller', 'name/role of incident controller')}",
        f"Deputy Incident Controller: {V('deputy_controller', 'deputy')}",
        f"Emergency Response Team leader: {V('ert_leader', 'ERT leader')}",
        f"Dangerous Goods Safety Adviser (DGSA): {V('dgsa', 'DGSA name and contact')}",
        f"HSE / Environmental officer: {V('hse_officer', 'HSE officer')}",
        "Security: access control and cordon; Communications: notifications log.",
    ])
    add("Alarm and communication procedures", [
        f"Alarm method: {V('alarm_method', 'alarm system and activation points')}",
        f"Primary communications: {V('radio_channels', 'radio channels / phone tree')}",
        "Maintain an incident log with times, decisions and notifications.",
    ])
    add("Isolation and evacuation arrangements", [
        f"Muster points: {V('muster_points', 'primary and secondary muster points')}",
        f"Shelter-in-place locations: {V('shelter_locations', 'shelter-in-place buildings')}",
        "Initial isolation and protective-action distances: per the applicable official emergency response guidance "
        "for each material (to be inserted by the plan owner).",
        "Account for all personnel and visitors at muster points.",
    ])
    add("Initial incident command actions", [
        "Raise alarm, protect life, isolate the area, deny entry.",
        "Identify the material from documents/placards at a safe distance — never by contact or smell.",
        "Assess escalation triggers and call external services if any apply.",
        "Establish incident control point upwind/uphill; brief arriving services with SDS and DG documents.",
    ])
    hazards_content = []
    for s, a in zip(substances, subst_assess):
        label = s.get("chemical_name") or s.get("un_number") or "unidentified substance"
        hazards_content.append({"substance": label, "un_number": a["material"]["un_number"],
                                "hazard_class": a["material"]["hazard_class"],
                                "subsidiary_hazards": a["material"]["subsidiary_hazards"],
                                "hazards": a["hazard_assessment"], "precautions": a["precautions_do_not"],
                                "data_notes": a["data_notes"]})
    if not substances:
        hazards_content.append(req("substances covered by this plan (UN number, name, class, max quantity)"))
        missing.append("substances covered")
    add("Substance-specific hazards", hazards_content)
    add("Responder PPE and competency requirements", [
        "PPE per SDS Section 8 and official emergency guidance, selected by a competent person.",
        f"Responder training/competency standard: {V('competency_standard', 'required hazmat training levels')}",
        "Respiratory protective equipment only for trained, fit-tested personnel.",
        f"PPE available on site: {V('ppe_inventory', 'PPE inventory and locations')}",
    ])
    if trained:
        strategy = ("On-site trained hazmat team may undertake containment using methods from SDS Section 6 and "
                    "verified guidance, within its declared competence and after confirming compatibility of materials "
                    "(absorbents, booms, neutralisers).")
    elif trained is False:
        strategy = ("NO on-site trained hazmat team: site personnel limit actions to alarm, isolation, evacuation and "
                    "notification. All containment and cleanup by external specialist responders.")
    else:
        strategy = (req("on-site hazmat response capability") + " — until confirmed, plan on the basis that site "
                    "personnel do NOT perform containment.")
    add("Containment and response strategy", [
        strategy,
        f"On-site emergency response team: {V('ert_capability', 'ERT size, shifts and competence level')}",
        f"External specialist / mutual-aid support: {V('external_support', 'external hazmat responders and expected arrival time')}",
        f"Fire service response time: {V('fire_response_time', 'expected fire service attendance time')}",
        f"Spill equipment available: {V('spill_equipment', 'spill kits, booms, drain covers and locations')}",
        "No water, absorbent or neutraliser is to be used unless confirmed compatible with the material.",
    ])
    add("Fire and explosion considerations", [
        "Fire-fighting media per SDS Section 5; some materials react dangerously with water.",
        f"Fixed fire protection: {V('fire_systems', 'hydrants, monitors, foam, sprinklers')}",
        "Cool exposed containers from a safe distance only if instructed by fire services.",
        "Contain fire-water run-off to prevent pollution.",
    ])
    add("Environmental protection", [
        f"Drain isolation points: {V('drain_isolation', 'drain valves / covers and locations')}",
        "Prevent releases entering drains, soil and waterways where safe to do so.",
        "Marine pollutant releases: notify port and environmental authorities.",
    ])
    add("Medical and exposure response", [
        "First aid per SDS Section 4; SDS to accompany casualties.",
        f"Nearest medical facility: {V('medical_facility', 'hospital / clinic and route')}",
        f"Eyewash / safety shower locations: {V('eyewash_locations', 'eyewash and shower locations')}",
        "Record exposures for medical surveillance and statutory reporting.",
    ])
    add("External notification requirements", [
        "Emergency services; port/terminal authority; environmental regulator; competent authority for DG incident "
        "reporting; carrier/shipper/consignee; insurer.",
        f"Jurisdiction-specific reporting obligations: {V('notification_obligations', 'legal reporting requirements and deadlines')}",
    ])
    add("Recovery, cleanup, waste management and site restoration", [
        "Area released only by the incident controller after atmospheric testing where relevant.",
        "Wastes in compatible, labelled containers; authorised hazardous-waste contractor; retain documentation.",
        f"Approved waste contractor: {V('waste_contractor', 'authorised waste contractor')}",
    ])
    add("Post-incident investigation and corrective actions", [
        "Preserve evidence; conduct root cause analysis; record corrective and preventive actions in the CAPA register.",
        "Review and update this ERP after every incident and drill.",
    ])
    contact_rows = contacts or [{"role": r, "name": req("name"), "phone": req("phone")} for r in
                                ("Emergency services", "Incident Controller", "DGSA", "Port authority",
                                 "Environmental regulator", "Poison centre / medical advice", "Waste contractor")]
    if not contacts:
        missing.append("emergency contacts")
    add("Emergency contacts and site-specific details", contact_rows)
    substance_evidence = []
    for a in subst_assess:
        for ev in a["evidence"]:
            substance_evidence.append(f"{ev['un_number']}: data from {ev['source_code']} ({ev['title']}; "
                                      f"verification: {ev['source_verification_status']}; authoritative: "
                                      f"{'yes' if ev['authoritative'] else 'NO'})")
    add("Regulatory references and approval history", {
        "regulatory_sources_in_library": source_references(db),
        "substance_data_used": substance_evidence or ["No substance data from the source library was used"],
        "other_references": [
            "National legislation on major hazards, DG handling in port areas and occupational safety: "
            + str(V("legislation", "jurisdiction-specific legislation")),
            "Product SDSs: " + str(V("sds_register", "SDS register location / revision dates")),
        ],
        "note": "References list what is registered in this system and its verification state. They are not "
                "citations of specific paragraphs and do not confirm regulatory compliance.",
        "approval_history": [{"version": "0.1 (draft)", "date": dt.date.today().isoformat(),
                              "author": author or req("author"), "status": "DRAFT — not approved"}],
    })
    return {"title": f"Emergency Response Plan — {SCENARIOS[scenario]}", "scenario": scenario,
            "scenario_label": SCENARIOS[scenario], "sections": sections,
            "required_inputs_missing": sorted(set(missing)), "response_capabilities": cap,
            "status": "DRAFT — requires completion, review and approval by authorised personnel",
            "disclaimer": "Generated template. Not an approved plan until reviewed, completed and authorised."}
