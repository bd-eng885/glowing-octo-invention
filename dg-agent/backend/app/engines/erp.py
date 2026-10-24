"""Emergency Response Plan generator: editable 18-section template.

Site-specific information that has not been supplied is emitted as
"[REQUIRED INPUT: ...]" and is never invented.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from . import spill

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


def generate(db: Session, scenario: str, site: dict, substances: list[dict], contacts: list[dict] | None = None,
             author: str | None = None) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'")
    contacts = contacts or []
    subst_assess = [spill.assess(db, {**s, "trained_responders_available": True, "sds_available": s.get("sds_available"),
                                      "quantity_estimate": s.get("max_quantity")}) for s in substances]
    missing = []

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
        + req("site-specific Level 1 criteria"),
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
    add("Containment and response strategy", [
        "Containment only by trained responders using methods from SDS Section 6 and verified guidance, after "
        "confirming compatibility of materials (absorbents, booms, neutralisers).",
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
    add("Regulatory references and approval history", {
        "references": ["Applicable IMDG Code edition (sea) — edition to be confirmed by plan owner",
                       "Applicable IATA DGR edition (air) — edition to be confirmed by plan owner",
                       "National legislation on major hazards, DG handling in port areas and occupational safety "
                       + req("jurisdiction-specific legislation"),
                       "Product SDSs"],
        "approval_history": [{"version": "0.1 (draft)", "date": dt.date.today().isoformat(),
                              "author": author or req("author"), "status": "DRAFT — not approved"}],
    })
    return {"title": f"Emergency Response Plan — {SCENARIOS[scenario]}", "scenario": scenario,
            "scenario_label": SCENARIOS[scenario], "sections": sections,
            "required_inputs_missing": sorted(set(missing)),
            "status": "DRAFT — requires completion, review and approval by authorised personnel",
            "disclaimer": "Generated template. Not an approved plan until reviewed, completed and authorised."}
