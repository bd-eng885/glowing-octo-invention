"""Spill response decision support.

Fail-safe principles implemented here:
* Unknown/unidentified material => isolate, alarm, evacuate as appropriate, specialist assessment.
* Never recommend water, absorbents, neutralisers or a cleanup method without verified compatibility.
* Never direct untrained persons into hazardous atmospheres or to handle unknown chemicals.
* Output is decision support, subordinate to the approved site ERP, the SDS, emergency services
  and specialist responders.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import DGEntry
from . import compat
from . import textutil as tu
from .provenance import effective_status, entry_evidence

# Site-configurable defaults (not regulatory values).
DEFAULT_THRESHOLDS = {"large_spill_litres_or_kg": 200}

HAZARD_PROFILES = {
    "1": ("Explosive", ["Explosion / mass detonation risk. Do not approach if fire threatens the cargo.",
                        "Evacuate and call emergency services immediately."]),
    "2.1": ("Flammable gas", ["Vapour cloud ignition / explosion risk.", "Pressure receptacle failure if heated."]),
    "2.2": ("Non-flammable gas", ["Asphyxiation in confined/low areas.", "Pressure receptacle failure if heated.",
                                  "Cryogenic burns if refrigerated liquefied gas."]),
    "2.3": ("Toxic gas", ["Inhalation hazard — potentially fatal.", "Treat as major incident: evacuate/shelter-in-place."]),
    "3": ("Flammable liquid", ["Flammable vapours; vapours may travel to ignition sources and flash back.",
                               "Vapour accumulation in drains/low areas."]),
    "4.1": ("Flammable solid", ["Readily combustible; some are self-reactive or desensitised explosives."]),
    "4.2": ("Spontaneously combustible", ["May ignite on contact with air."]),
    "4.3": ("Dangerous when wet", ["Contact with water emits flammable and/or toxic gas."]),
    "5.1": ("Oxidizer", ["Intensifies fire; may ignite combustibles (wood, paper, absorbents, oils)."]),
    "5.2": ("Organic peroxide", ["Thermally unstable; may decompose explosively; contamination sensitive."]),
    "6.1": ("Toxic", ["Toxic by ingestion, skin contact and/or inhalation."]),
    "6.2": ("Infectious", ["Biological hazard — specialist response."]),
    "7": ("Radioactive", ["Radiation exposure — notify radiation protection authority; specialist response."]),
    "8": ("Corrosive", ["Severe skin/eye damage; may react with metals releasing hydrogen; may react with water."]),
    "9": ("Miscellaneous", ["Hazards vary (e.g. environmentally hazardous, lithium batteries, elevated temperature)."]),
}

PRECAUTIONS = {
    "3": ["Eliminate ignition sources; use only intrinsically safe/explosion-protected equipment if trained.",
          "Prevent entry to drains and confined spaces."],
    "2.1": ["Eliminate ignition sources; do not operate electrical switches in the vapour area."],
    "4.3": ["Do NOT apply water or aqueous agents; keep material dry."],
    "5.1": ["Do NOT use combustible absorbents (sawdust, paper, rags)."],
    "5.2": ["Do NOT use combustible absorbents; avoid confinement; keep away from heat."],
    "8": ["Avoid all skin/eye contact; do not use incompatible metal tools/containers.",
          "Do NOT apply neutralising chemicals unless the SDS / specialist confirms the method."],
    "2.3": ["Approach only from upwind by trained responders with appropriate respiratory protection."],
    "6.1": ["Avoid contact and inhalation; prevent spread; trained responders only."],
    "7": ["Do not touch or move damaged packages; minimise time, maximise distance."],
    "6.2": ["Do not touch damaged packages; isolate; notify public health authority."],
    "1": ["Do not fight fire involving the cargo; evacuate to a safe distance."],
}


def assess(db: Session, data: dict) -> dict:
    t = {**DEFAULT_THRESHOLDS, **(data.get("thresholds") or {})}
    un, un_notes = tu.normalize_un(data.get("un_number"))
    hc = tu.normalize_class(data.get("hazard_class"))
    subs = [tu.normalize_class(s) for s in (data.get("subsidiary_hazards") or []) if s]
    evidence, data_notes = [], list(un_notes)
    entry = None
    if un:
        entries = [e for e in db.execute(select(DGEntry).options(selectinload(DGEntry.source))
                                         .where(DGEntry.un_number == un)).scalars() if effective_status(e.source) == "current"]
        if entries:
            entry = entries[0]
            evidence.append(entry_evidence(entry))
            if not hc:
                hc, subs = entry.hazard_class, list(entry.subsidiary_hazards)
                data_notes.append(f"Hazard class taken from {entry.source.code} "
                                  f"({entry.source.verification_status}) — confirm against transport documents/SDS.")
        else:
            data_notes.append(f"{un} not found in loaded data — hazards cannot be inferred from the UN number.")
    identified = bool(hc) and bool(un or data.get("chemical_name"))
    hazards = ([hc] if hc else []) + subs
    qty = data.get("quantity_estimate")
    concerns = {k: bool(data.get(k)) for k in ("fire", "vapour_release", "injuries_or_exposure", "reaction_observed",
                                                "drains_nearby", "waterway_nearby", "personnel_nearby",
                                                "container_damaged", "pressure_receptacle_involved")}
    trained = bool(data.get("trained_responders_available"))
    sds = bool(data.get("sds_available"))

    triggers = []
    if not identified:
        triggers.append("Material unidentified or hazard class unknown")
    if concerns["fire"]:
        triggers.append("Fire present or imminent")
    if concerns["injuries_or_exposure"]:
        triggers.append("Injury or personnel exposure")
    if concerns["vapour_release"] or set(hazards) & {"2.3"}:
        triggers.append("Toxic/flammable vapour or gas release")
    if set(hazards) & {"1", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "6.2", "7", "5.2"}:
        triggers.append("Explosive, infectious, radioactive or organic peroxide material")
    if concerns["waterway_nearby"]:
        triggers.append("Waterway / environmental receptor at risk")
    if concerns["pressure_receptacle_involved"]:
        triggers.append("Pressure receptacle involved")
    if qty is None:
        triggers.append("Quantity unknown")
    elif float(qty) >= t["large_spill_litres_or_kg"]:
        triggers.append(f"Quantity ≥ {t['large_spill_litres_or_kg']} (site threshold)")
    if not trained:
        triggers.append("No trained hazmat responders available on site")

    if triggers:
        level = "MAJOR — ESCALATE TO EXTERNAL EMERGENCY SERVICES / SPECIALIST HAZMAT RESPONSE"
    else:
        level = "SITE EMERGENCY RESPONSE TEAM — SUPERVISED RESPONSE PER APPROVED SITE ERP"

    immediate = [
        "Protect life first: raise the alarm and warn people nearby.",
        "Isolate the area, establish a cordon upwind/uphill, and prevent unauthorised entry.",
        "Do not touch, walk through or attempt to identify the material by smell or contact.",
        "Notify the designated site emergency response team / incident controller.",
        "Eliminate ignition sources only if this can be done without entering the hazard area.",
        "Decide evacuation or shelter-in-place with the incident controller based on wind direction, "
        "vapour release and the emergency response guidance for the material.",
    ]
    if triggers:
        immediate.insert(3, "Call external emergency services now (escalation trigger(s) present).")
    if not identified:
        immediate.append("Treat as UNKNOWN and potentially severe: maximise distance, stay upwind, await specialist "
                         "assessment. No containment or cleanup by site personnel.")
    if concerns["injuries_or_exposure"]:
        immediate.append("Move casualties to fresh air only if rescuers are not exposed; obtain medical help; "
                         "follow SDS Section 4 first aid.")

    hazard_assessment = []
    for h in hazards:
        key = h if h in HAZARD_PROFILES else h.split(".")[0]
        if key in HAZARD_PROFILES:
            name, points = HAZARD_PROFILES[key]
            hazard_assessment.append({"hazard": h, "name": name, "considerations": points,
                                      "role": "primary" if h == hc else "subsidiary"})
    if concerns["drains_nearby"] or concerns["waterway_nearby"] or "9" in hazards:
        hazard_assessment.append({"hazard": "ENV", "name": "Environmental",
                                  "considerations": ["Risk of release to drains/waterways — protect drains only "
                                                     "if it can be done safely and with compatible materials."]})
    groups = sorted(compat.groups_for({"hazard_class": hc, "subsidiary_hazards": subs,
                                       "name": data.get("chemical_name"),
                                       "proper_shipping_name": entry.proper_shipping_name if entry else None}))

    precautions = sorted({p for h in hazards for p in PRECAUTIONS.get(h, PRECAUTIONS.get(h.split(".")[0], []))})
    ems = (entry.mode_data or {}).get("ems") if entry else None
    references = [
        "SDS Section 4 (first aid), 5 (fire-fighting), 6 (accidental release), 8 (exposure controls/PPE), "
        "10 (stability/reactivity), 13 (disposal)" + ("" if sds else " — SDS NOT AVAILABLE: obtain urgently"),
        f"IMDG Emergency Schedule (EmS): {ems}" if ems else "IMDG EmS / transport emergency guidance: NOT LOADED for this "
        "material — consult the official publication",
        "Approved site Emergency Response Plan and the incident controller's instructions",
        "Initial isolation / protective action distances: use the applicable official emergency response guide "
        "adopted in your jurisdiction (not loaded in this system)",
    ]
    containment = []
    if not identified:
        containment.append("WITHHELD: material not identified. No containment or cleanup by site personnel.")
    elif not trained:
        containment.append("WITHHELD: no trained responders. Isolate and await the emergency response team.")
    else:
        containment.append("Containment/cleanup method: select ONLY from SDS Section 6 and verified emergency guidance, "
                           "after confirming compatibility of absorbents/booms/neutralisers with the material.")
        containment.append("Not recommended automatically by this system: water, absorbents, neutralising chemicals.")
    ppe = ("PPE: select from SDS Section 8 and the emergency guidance, by a competent person, matched to the substance, "
           "concentration and exposure. Respiratory protection only by trained, fit-tested personnel. "
           "This system does not specify PPE without verified substance data.")
    medical = ["Follow SDS Section 4; provide SDS to medical personnel.",
               "Record all persons potentially exposed (name, duration, route) for medical surveillance.",
               "Decontaminate casualties per SDS and medical advice before transport where safe.",
               "Report occupational exposure/injury per local legal requirements."]
    waste = ["Collect residues only by trained personnel into compatible, closed, labelled containers.",
             "Do not mix wastes; segregate from incompatible materials (screening groups: "
             f"{', '.join(groups) or 'unknown'}).",
             "Store temporarily in a designated, bunded, secure area.",
             "Dispose only through an authorised hazardous-waste contractor with documentation (SDS Section 13)."]
    notifications = ["Site incident controller / HSE manager", "Port / terminal authority (if in port area)",
                     "Environmental regulator if release to drains, soil or water",
                     "Carrier / shipper / consignee and DGSA",
                     "Competent authority reporting of dangerous goods incidents as required by applicable regulations"]
    return {
        "response_level": level, "escalation_triggers": triggers, "identified": identified,
        "material": {"un_number": un, "chemical_name": data.get("chemical_name"), "hazard_class": hc,
                     "subsidiary_hazards": subs, "proper_shipping_name": entry.proper_shipping_name if entry else None},
        "immediate_priorities": immediate, "hazard_assessment": hazard_assessment,
        "incompatible_material_groups": groups,
        "precautions_do_not": precautions, "response_references": references, "containment": containment,
        "ppe": ppe, "medical": medical, "waste": waste, "notifications": notifications,
        "data_notes": data_notes, "evidence": evidence, "thresholds_used": t,
        "limitations": [
            "Decision support only. Does not replace the approved site ERP, the SDS, emergency services or specialist responders.",
            "Untrained personnel must not enter hazardous atmospheres or attempt cleanup.",
            "Hazard considerations are generic for the hazard class and must be confirmed against substance-specific data.",
        ],
        "requires_human_approval": True,
    }
