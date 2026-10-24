"""Deterministic segregation engine (IMDG, IATA, warehouse).

The engine evaluates every pair, applies primary AND subsidiary hazards (most stringent
requirement wins), records the rule table and source used, and never issues an approval.
Missing data, demo/unverified rule tables or unloaded individual DGL provisions lead to
"HOLD — MANUAL VERIFICATION REQUIRED".
"""
from __future__ import annotations

from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import DGEntry, RuleTable
from . import compat
from . import textutil as tu
from .provenance import effective_status, source_record, table_is_authoritative

HOLD = "HOLD — MANUAL VERIFICATION REQUIRED"
CONFLICT = "CONFLICT IDENTIFIED — DO NOT LOAD/STOW AS PROPOSED"
NO_CONFLICT = "NO CONFLICT IDENTIFIED BY ENGINE — QUALIFIED REVIEW REQUIRED"

ARRANGEMENTS = {
    "same_ctu": "Same cargo transport unit (container / vehicle)",
    "same_hold": "Same hold / compartment, separate CTUs",
    "separate_ctus": "Separate CTUs (stowage positions not specified)",
    "same_uld": "Same ULD / adjacent in aircraft hold",
    "adjacent_storage": "Adjacent storage areas",
    "same_storage_area": "Same storage area / bay",
    "separate_facility": "Separate facilities",
}
_STRINGENCY = {"X": 0, "1": 1, "2": 2, "3": 3, "4": 4}
IMDG_INDEX = {"1.1": 0, "1.2": 0, "1.5": 0, "1.3": 1, "1.6": 1, "1.4": 2, "2.1": 3, "2.2": 4, "2.3": 5, "3": 6,
              "4.1": 7, "4.2": 8, "4.3": 9, "5.1": 10, "5.2": 11, "6.1": 12, "6.2": 13, "7": 14, "8": 15, "9": 16}


def _load_table(db: Session, code_prefix: str) -> RuleTable | None:
    tables = db.execute(select(RuleTable).options(selectinload(RuleTable.source))
                        .where(RuleTable.code.like(f"{code_prefix}%"))).scalars().all()
    usable = [t for t in tables if effective_status(t.source) == "current"]
    # Prefer verified tables over demo/unverified ones.
    usable.sort(key=lambda t: (t.verification_status != "verified", t.source.verification_status != "verified"))
    return usable[0] if usable else None


def enrich_items(db: Session, items: list[dict]) -> tuple[list[dict], list[str]]:
    """Fill class/subsidiary from loaded data when only a UN number is given (flagged as such)."""
    out, notes = [], []
    for i, raw in enumerate(items):
        it = dict(raw)
        it.setdefault("id", f"item{i + 1}")
        it["hazard_class"] = tu.normalize_class(it.get("hazard_class"))
        it["subsidiary_hazards"] = [tu.normalize_class(s) for s in (it.get("subsidiary_hazards") or []) if s]
        it["data_origin"] = "user"
        un, _ = tu.normalize_un(it.get("un_number"))
        it["un_number"] = un
        if un:
            entries = [e for e in db.execute(select(DGEntry).options(selectinload(DGEntry.source))
                                             .where(DGEntry.un_number == un)).scalars()
                       if effective_status(e.source) == "current"]
            if entries and not it["hazard_class"]:
                e = entries[0]
                it["hazard_class"] = e.hazard_class
                it["subsidiary_hazards"] = list(e.subsidiary_hazards)
                it["proper_shipping_name"] = e.proper_shipping_name
                it["data_origin"] = f"looked up from {e.source.code} ({e.source.verification_status})"
                notes.append(f"{it['id']}: class/subsidiary taken from {e.source.code} — "
                             f"{'NOT authoritative' if e.source.verification_status != 'verified' else 'verified'} data.")
            elif entries:
                e = entries[0]
                it.setdefault("proper_shipping_name", e.proper_shipping_name)
                if e.hazard_class != it["hazard_class"] or set(e.subsidiary_hazards) != set(it["subsidiary_hazards"]):
                    notes.append(f"{it['id']}: declared class/subsidiary ({it['hazard_class']} / "
                                 f"{it['subsidiary_hazards']}) differs from loaded data for {un} "
                                 f"({e.hazard_class} / {e.subsidiary_hazards}). Resolve before relying on result.")
                    it["data_conflict"] = True
            it["_entries"] = entries
        out.append(it)
    return out, notes


def _imdg_pair(table: RuleTable, a: dict, b: dict, arrangement: str | None) -> dict:
    t = table.data
    issues, conds = [], []
    ha = [a["hazard_class"]] + a["subsidiary_hazards"] if a.get("hazard_class") else []
    hb = [b["hazard_class"]] + b["subsidiary_hazards"] if b.get("hazard_class") else []
    if not ha or not hb:
        return {"status": "hold", "code": None, "label": "Hazard class missing",
                "issues": ["Hazard class missing for one or both items — cannot evaluate."]}
    unmapped = [h for h in ha + hb if h not in IMDG_INDEX]
    if unmapped:
        return {"status": "hold", "code": None, "label": "Class not mapped",
                "issues": [f"Cannot map hazard(s) {unmapped} to the segregation table (division required for Class 1/2/4/5/6)."]}
    worst, worst_combo, star = "X", None, False
    for x in ha:
        for y in hb:
            code = t["matrix"][IMDG_INDEX[x]][IMDG_INDEX[y]]
            if code == "*":
                star = True
                continue
            if _STRINGENCY[code] > _STRINGENCY[worst]:
                worst, worst_combo = code, (x, y)
    if star:
        issues.append(t["codes"]["*"])
    if len(ha) + len(hb) > 2:
        conds.append("Subsidiary hazards were included and the most stringent requirement applied. The applicable "
                     "edition may contain exceptions or specific provisions that alter this — qualified review required.")
    if a["hazard_class"] == b["hazard_class"]:
        conds.append("Both items share the same primary class; check the applicable provisions for goods of the same "
                     "class and whether the substances react dangerously with each other.")
    sga, sgb = set(a.get("segregation_groups") or []), set(b.get("segregation_groups") or [])
    if sga and sgb and sga != sgb:
        conds.append(f"Segregation groups {sorted(sga)} vs {sorted(sgb)}: check DGL segregation codes "
                     "(e.g. acids vs alkalis) for specific requirements.")
    for it in (a, b):
        codes = [c for e in it.get("_entries", []) for c in (e.mode_data or {}).get("segregation_codes", [])]
        if codes:
            conds.append(f"{it['id']}: Dangerous Goods List segregation provisions {codes} must be applied.")
        else:
            conds.append(f"{it['id']}: individual Dangerous Goods List segregation provisions NOT LOADED — must be "
                         "checked manually.")
    label = t["codes"].get(worst, worst)
    if star:
        status = "hold"
    elif arrangement == "same_ctu" and worst != "X":
        status = "conflict"
        if worst == "1":
            issues.append("Goods requiring 'away from' segregation in the same CTU: only permissible where the "
                          "applicable provisions/competent authority allow — treat as prohibited until verified.")
        else:
            issues.append(f"'{label}' cannot be achieved within one cargo transport unit.")
    elif worst == "X":
        status = "no_general_requirement"
    else:
        status = "requirement"
        issues.append(f"Required segregation: '{label}'. Actual stowage positions must be verified against the "
                      "applicable stowage/segregation provisions for the ship type.")
    return {"status": status, "code": worst if not star else "*", "label": label if not star else t["codes"]["*"],
            "governing_combination": worst_combo, "issues": issues, "conditions": conds}


def _iata_pair(table: RuleTable, a: dict, b: dict, arrangement: str | None) -> dict:
    ha = set([a.get("hazard_class")] + a.get("subsidiary_hazards", [])) - {None}
    hb = set([b.get("hazard_class")] + b.get("subsidiary_hazards", [])) - {None}
    if not ha or not hb:
        return {"status": "hold", "code": None, "label": "Hazard class missing",
                "issues": ["Hazard class missing — cannot evaluate."]}
    issues, conds = [], []
    hit = None
    for p in table.data["pairs"]:
        if (p["a"] in ha and p["b"] in hb) or (p["b"] in ha and p["a"] in hb):
            hit = p
    for it, hs in ((a, ha), (b, hb)):
        if any(h.startswith("1") for h in hs) and not (it.get("explosive_compat_group", "").upper() == "S"
                                                        and "1.4" in hs):
            issues.append(f"{it['id']}: {table.data['class1_rule']}")
    if hit:
        status = "conflict" if arrangement in ("same_uld", "same_ctu") else "requirement"
        issues.append(f"Packages of {hit['a']} and {hit['b']} require segregation ({hit['note']}).")
    elif issues:
        status = "hold"
    else:
        status = "no_pair_in_loaded_subset"
        conds.append("No pair found in the LOADED subset. The loaded IATA table is partial; this is not evidence "
                     "that segregation is not required.")
    return {"status": status, "code": "segregate" if hit else None,
            "label": "Segregation required" if hit else "No pair in loaded subset",
            "issues": issues, "conditions": conds}


def evaluate(db: Session, items: list[dict], mode: str, arrangement: str | None = None) -> dict:
    mode = mode.upper()
    items, notes = enrich_items(db, items)
    assumptions = [f"Arrangement evaluated: {ARRANGEMENTS.get(arrangement, 'not specified')}."]
    missing = []
    for it in items:
        for k in ("quantity", "package"):
            if not it.get(k):
                missing.append(f"{it['id']}: {k} not provided")
        if not it.get("hazard_class"):
            missing.append(f"{it['id']}: hazard class unknown")
    result = {"mode": mode, "arrangement": arrangement, "notes": notes, "assumptions": assumptions,
              "missing_information": missing, "requires_human_approval": True}

    if mode == "WAREHOUSE":
        scr = compat.screen(items)
        result.update(
            screening=scr, pairs=scr["pairs"], decision=HOLD,
            limitations=["Transport segregation rules are not storage rules. Warehouse storage requires the "
                         "site-specific risk assessment, local fire code and permit conditions, and SDS Sections 7/10."],
            rule_table=None)
        return result

    table = _load_table(db, "IMDG-SEG" if mode == "IMDG" else "IATA-SEG")
    if table is None:
        result.update(decision=HOLD, pairs=[], matrix=None,
                      limitations=[f"No {mode} segregation rule table is loaded for the current edition."])
        return result
    authoritative, limitations = table_is_authoritative(table)
    pair_fn = _imdg_pair if mode == "IMDG" else _iata_pair
    pairs, matrix = [], {it["id"]: {} for it in items}
    for a, b in combinations(items, 2):
        r = pair_fn(table, a, b, arrangement)
        if a.get("data_conflict") or b.get("data_conflict"):
            r["status"] = "hold" if r["status"] != "conflict" else "conflict"
            r.setdefault("issues", []).append("Declared data conflicts with loaded data — resolve first.")
        r.update(a=a["id"], b=b["id"])
        pairs.append(r)
        matrix[a["id"]][b["id"]] = matrix[b["id"]][a["id"]] = {"status": r["status"], "code": r.get("code")}
    # Non-regulatory chemistry screening, so that e.g. an acid and an alkali of the same class are not
    # presented as unproblematic just because the general class table shows no requirement.
    screening = compat.screen(items)
    by_pair = {frozenset((p["a"], p["b"])): p for p in screening["pairs"]}
    for p in pairs:
        sp = by_pair.get(frozenset((p["a"], p["b"])))
        if sp and sp["flags"]:
            p.setdefault("conditions", []).extend(
                f"NON-REGULATORY screening ({f['severity']}): {f['reason']} Check DGL segregation provisions "
                "(e.g. segregation groups) and SDS Section 10." for f in sp["flags"])
            p["screening_flags"] = sp["flags"]
            if p["status"] in ("no_general_requirement", "no_pair_in_loaded_subset") and \
                    any(f["severity"] == "high" for f in sp["flags"]):
                p["status"] = "hold"
                p.setdefault("issues", []).append("Chemical compatibility screening flags a hazardous reaction; "
                                                  "the general table alone cannot clear this pair.")
            matrix[p["a"]][p["b"]] = matrix[p["b"]][p["a"]] = {"status": p["status"], "code": p.get("code")}
    statuses = {p["status"] for p in pairs}
    if "conflict" in statuses:
        decision = CONFLICT
    elif not authoritative or statuses & {"hold", "requirement", "no_pair_in_loaded_subset"} or missing or notes:
        decision = HOLD
    else:
        # Even with verified tables, individual DGL provisions are always listed as conditions.
        decision = HOLD if any(p.get("conditions") for p in pairs) else NO_CONFLICT
    alternatives = None
    if "conflict" in statuses and arrangement == "same_ctu" and not missing:
        alternatives = ["Load the conflicting items in separate CTUs and determine the required stowage "
                        "separation between those CTUs from the applicable stowage/segregation provisions."]
    for it in items:
        it.pop("_entries", None)
    result.update(items=items, pairs=pairs, matrix=matrix, decision=decision,
                  rule_table={"code": table.code, "name": table.name, "section_ref": table.section_ref,
                              "verification_status": table.verification_status, "complete": table.complete,
                              "authoritative": authoritative, "source": source_record(table.source, table.section_ref)},
                  limitations=limitations + ["A generic class-vs-class table is never the sole basis for approval: "
                                             "individual entry provisions, segregation groups, special provisions "
                                             "and exceptions apply."],
                  alternative_arrangement=alternatives,
                  manual_checks=table.data.get("manual_checks", []))
    return result
