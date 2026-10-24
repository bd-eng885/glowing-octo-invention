"""Chemical compatibility SCREENING (storage / spill context).

This is general reactive-chemistry screening, NOT a transport segregation rule set and
never a basis for approval. It flags well-known hazardous combinations so that a
qualified person reviews them alongside the SDS (Sections 7 and 10) and site rules.
"""
from __future__ import annotations

from itertools import combinations

GROUPS = {
    "ACID": "Acids", "BASE": "Bases / alkalis", "OXIDIZER": "Oxidizers", "FLAMMABLE": "Flammables / combustibles",
    "WATER_REACTIVE": "Water-reactive", "HYPOCHLORITE": "Hypochlorites", "AMMONIA": "Ammonia / ammonium compounds",
    "CYANIDE": "Cyanides", "ORGANIC_PEROXIDE": "Organic peroxides", "CORROSIVE_UNSPECIFIED": "Corrosive (acid/base not known)",
    "AQUEOUS": "Aqueous solutions", "TOXIC": "Toxic substances",
}

RULES = [
    ({"ACID"}, {"BASE"}, "high", "Violent neutralisation, heat and spattering."),
    ({"ACID"}, {"HYPOCHLORITE"}, "high", "Release of chlorine gas."),
    ({"AMMONIA"}, {"HYPOCHLORITE"}, "high", "Formation of toxic chloramine gases."),
    ({"ACID"}, {"CYANIDE"}, "high", "Release of highly toxic hydrogen cyanide."),
    ({"OXIDIZER"}, {"FLAMMABLE"}, "high", "Oxidizers intensify fire and may cause ignition/explosion of combustibles."),
    ({"ORGANIC_PEROXIDE"}, {"FLAMMABLE", "ACID", "BASE", "OXIDIZER", "AMMONIA"}, "high",
     "Organic peroxides may decompose violently on contamination."),
    ({"WATER_REACTIVE"}, {"AQUEOUS", "ACID", "BASE", "HYPOCHLORITE", "AMMONIA"}, "high",
     "Contact with water/aqueous material may release flammable or toxic gas and heat."),
    ({"CORROSIVE_UNSPECIFIED"}, {"CORROSIVE_UNSPECIFIED", "ACID", "BASE"}, "medium",
     "Possible acid/base incompatibility — determine whether each corrosive is acidic or alkaline."),
    ({"OXIDIZER"}, {"AMMONIA"}, "medium", "Some oxidizers react hazardously with ammonia/ammonium compounds."),
]


def groups_for(item: dict) -> set[str]:
    g = set(item.get("reactive_groups") or [])
    hazards = {item.get("hazard_class") or ""} | set(item.get("subsidiary_hazards") or [])
    name = " ".join(filter(None, [item.get("name"), item.get("proper_shipping_name")])).upper()
    if hazards & {"3", "2.1", "4.1"}:
        g.add("FLAMMABLE")
    if "5.1" in hazards:
        g.add("OXIDIZER")
    if "5.2" in hazards:
        g.add("ORGANIC_PEROXIDE")
    if "4.3" in hazards:
        g.add("WATER_REACTIVE")
    if hazards & {"6.1", "2.3"}:
        g.add("TOXIC")
    if "HYPOCHLORITE" in name:
        g |= {"HYPOCHLORITE", "OXIDIZER"}
    if "AMMONIA" in name or "AMMONIUM" in name:
        g.add("AMMONIA")
    if "CYANIDE" in name:
        g.add("CYANIDE")
    if "ACID" in name:
        g.add("ACID")
    if "HYDROXIDE" in name or "CAUSTIC" in name or "AMMONIA SOLUTION" in name:
        g.add("BASE")
    if "SOLUTION" in name or "AQUEOUS" in name:
        g.add("AQUEOUS")
    if "8" in hazards and not g & {"ACID", "BASE"}:
        g.add("CORROSIVE_UNSPECIFIED")
    return g


def screen(items: list[dict]) -> dict:
    enriched = [{**it, "groups": sorted(groups_for(it))} for it in items]
    pairs = []
    for a, b in combinations(enriched, 2):
        ga, gb = set(a["groups"]), set(b["groups"])
        hits = []
        for x, y, sev, why in RULES:
            if (ga & x and gb & y) or (gb & x and ga & y):
                hits.append({"severity": sev, "reason": why})
        pairs.append({"a": a.get("id") or a.get("name"), "b": b.get("id") or b.get("name"),
                      "result": "INCOMPATIBLE — REVIEW" if any(h["severity"] == "high" for h in hits)
                      else ("CAUTION — REVIEW" if hits else "NO SCREENING FLAG"),
                      "flags": hits})
    unknown = [it.get("id") or it.get("name") for it in enriched if not it["groups"]]
    return {
        "type": "chemical_compatibility_screening",
        "items": enriched, "pairs": pairs, "items_without_reactivity_data": unknown,
        "basis": "General reactive-chemistry screening rules (built-in). Not a regulatory segregation rule set.",
        "limitations": [
            "Screening is based on hazard class and keywords only; it cannot detect every incompatibility.",
            "'NO SCREENING FLAG' is not a confirmation of compatibility.",
            "Check SDS Section 7 (handling/storage) and Section 10 (stability/reactivity) for each product.",
            "Warehouse storage must also satisfy local fire codes, permits and the site-specific risk assessment.",
        ],
        "decision": "HOLD — MANUAL VERIFICATION REQUIRED" if (unknown or any(p["flags"] for p in pairs))
        else "SCREENING COMPLETE — QUALIFIED REVIEW REQUIRED",
    }
