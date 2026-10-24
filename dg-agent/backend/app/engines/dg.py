"""Dangerous goods identification and UN / Proper Shipping Name verification.

Design rules (safety-critical):
* Results are computed deterministically from stored regulatory data. No LLM is involved.
* A status of VERIFIED AGAINST SOURCE is only possible when the matched entry is
  authoritative (verified source + verified entry + edition in force). Otherwise the
  final status is NOT VERIFIED - HUMAN REVIEW REQUIRED and the computed outcome is
  shown as a *provisional* assessment.
* IMDG and IATA are separate rule sets. Data from one is never used to verify the other;
  UN Model Regulations data is shown only as reference.
* Absence of a match never implies "not dangerous goods".
"""
from __future__ import annotations

import datetime as dt
import difflib
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import DGEntry, RegulatorySource
from . import textutil as tu
from .provenance import effective_status, entry_evidence, entry_is_authoritative, source_record

VERIFIED = "VERIFIED AGAINST SOURCE"
MATCH_COND = "MATCH WITH CONDITIONS"
DISCREPANCY = "DISCREPANCY FOUND"
INSUFFICIENT = "INSUFFICIENT INFORMATION"
NOT_VERIFIED = "NOT VERIFIED — HUMAN REVIEW REQUIRED"

MODES = ("IMDG", "IATA", "UN_MODEL")
MODE_LABEL = {"IMDG": "IMDG Code (sea)", "IATA": "IATA DGR (air)", "UN_MODEL": "UN Model Regulations (reference)"}

GENERAL_LIMITATION = ("A matching UN number alone is not proof of compliance. This check covers identification "
                      "fields only; packaging, quantity limits, marking, labelling, documentation, stowage, "
                      "segregation and operator/State acceptance must be verified separately by qualified personnel.")


# ---------------------------------------------------------------------------------------------
def _entries_for(db: Session, un: str | None = None, rule_set: str | None = None) -> list[DGEntry]:
    q = select(DGEntry).join(RegulatorySource).options(selectinload(DGEntry.source))
    if un:
        q = q.where(DGEntry.un_number == un)
    if rule_set:
        q = q.where(RegulatorySource.rule_set == rule_set)
    return list(db.execute(q).scalars())


def mode_coverage(db: Session, mode: str, today: dt.date | None = None) -> dict:
    """Which datasets back a given mode right now."""
    srcs = db.execute(select(RegulatorySource).where(RegulatorySource.rule_set == mode)).scalars().all()
    recs = []
    for s in srcs:
        r = source_record(s, today=today)
        r["content_loaded"] = s.content_loaded
        recs.append(r)
    usable = [r for r in recs if r["content_loaded"] and r["source_status"] == "current"]
    return {"mode": mode, "sources": recs, "content_available": bool(usable),
            "authoritative_content_available": any(r["source_verification_status"] == "verified" for r in usable)}


def labels_for(entry: DGEntry, mode: str) -> dict:
    """Hazard labels follow from primary + subsidiary hazards. Shown as derived, to be confirmed."""
    labels = [f"Class/Division {entry.hazard_class} hazard label"]
    labels += [f"Class/Division {s} subsidiary hazard label" for s in entry.subsidiary_hazards]
    marks = [f"{entry.un_number} and Proper Shipping Name"]
    if mode == "IMDG":
        if entry.marine_pollutant is None:
            marks.append("Marine pollutant mark: STATUS NOT LOADED — determine from DGL / classification criteria")
        elif entry.marine_pollutant == "P":
            marks.append("Marine pollutant mark")
    if mode == "IATA":
        marks.append("Cargo Aircraft Only label: DEPENDS on packing instruction/quantity — IATA data not loaded")
    return {"labels": labels, "marks": marks,
            "placards": "For CTUs (sea): placards corresponding to the hazard labels, subject to applicable provisions"
            if mode == "IMDG" else None,
            "basis": "Derived from class and subsidiary hazards (rule-based). Exemptions (e.g. limited/excepted "
                     "quantities) and special provisions can change requirements — confirm against applicable rules."}


def entry_view(entry: DGEntry, mode: str | None = None) -> dict:
    ok, reasons = entry_is_authoritative(entry)
    v = {
        "id": entry.id, "un_number": entry.un_number, "variant": entry.variant,
        "proper_shipping_name": entry.proper_shipping_name, "hazard_class": entry.hazard_class,
        "subsidiary_hazards": entry.subsidiary_hazards,
        "packing_groups": entry.packing_groups,
        "packing_group_applicable": bool(entry.packing_groups),
        "special_provisions": entry.special_provisions,
        "special_provisions_loaded": entry.special_provisions is not None,
        "marine_pollutant": entry.marine_pollutant, "mode_data": entry.mode_data,
        "synonyms": entry.synonyms, "cas_numbers": entry.cas_numbers,
        "rule_set": entry.source.rule_set, "authoritative": ok, "limitations": reasons,
        "evidence": entry_evidence(entry),
    }
    if mode:
        v["labelling"] = labels_for(entry, mode)
    return v


# ---------------------------------------------------------------------------------------------
@dataclass
class Check:
    field: str
    result: str  # match | condition | discrepancy | insufficient
    declared: object = None
    reference: object = None
    message: str = ""

    def as_dict(self):
        return self.__dict__


@dataclass
class _Acc:
    checks: list[Check] = field(default_factory=list)

    def add(self, *a, **k):
        self.checks.append(Check(*a, **k))

    def status(self) -> str:
        results = {c.result for c in self.checks}
        if "discrepancy" in results:
            return DISCREPANCY
        if "insufficient" in results:
            return INSUFFICIENT
        if "condition" in results:
            return MATCH_COND
        return VERIFIED


def compare_psn(declared: str | None, entry: DGEntry) -> Check:
    if not declared:
        return Check("proper_shipping_name", "insufficient", None, entry.proper_shipping_name,
                     "Proper Shipping Name not declared.")
    core_decl, tech = tu.strip_technical_name(declared)
    d = tu.norm_text(core_decl)
    alts = tu.psn_alternatives(entry.proper_shipping_name)
    full = tu.norm_text(entry.proper_shipping_name)
    nos = any("N.O.S" in a for a in alts)
    if d in alts or d == full:
        if nos and not tech:
            return Check("proper_shipping_name", "condition", declared, entry.proper_shipping_name,
                         "Generic / N.O.S. entry: a technical name in parentheses may be required. "
                         "Classification criteria for generic entries must be confirmed.")
        if nos:
            return Check("proper_shipping_name", "condition", declared, entry.proper_shipping_name,
                         f"Generic / N.O.S. entry with technical name '{tech}': confirm the technical name and "
                         "that the generic entry is the most specific applicable entry.")
        return Check("proper_shipping_name", "match", declared, entry.proper_shipping_name,
                     "Declared name matches an authorised name in the entry.")
    canon_alts = [tu.canonical_spelling(a) for a in alts]
    if tu.canonical_spelling(core_decl) in canon_alts:
        return Check("proper_shipping_name", "condition", declared, entry.proper_shipping_name,
                     "Matches apart from a spelling variant (e.g. sulfur/sulphur). Confirm the variant is "
                     "acceptable under the applicable rules.")
    for a in alts:
        if d.startswith(a + " ") or d.startswith(a + ", "):
            return Check("proper_shipping_name", "condition", declared, entry.proper_shipping_name,
                         f"Declared name begins with the authorised name '{a}' followed by additional text. "
                         "Confirm the additional text is permitted (e.g. qualifying description).")
    best = max(difflib.SequenceMatcher(None, d, a).ratio() for a in alts)
    msg = "Declared name does not match the Proper Shipping Name for this UN number."
    if best >= 0.8:
        msg += f" Very similar (similarity {best:.2f}) — possible misspelling or OCR error."
    return Check("proper_shipping_name", "discrepancy", declared, entry.proper_shipping_name, msg)


def _compare_entry(decl: dict, entry: DGEntry, mode: str) -> _Acc:
    acc = _Acc()
    acc.checks.append(compare_psn(decl.get("proper_shipping_name"), entry))

    dc = tu.normalize_class(decl.get("hazard_class"))
    if dc is None:
        acc.add("hazard_class", "insufficient", None, entry.hazard_class, "Hazard class/division not declared.")
    elif dc == entry.hazard_class:
        acc.add("hazard_class", "match", dc, entry.hazard_class, "Primary hazard class matches.")
    elif dc in entry.subsidiary_hazards:
        acc.add("hazard_class", "discrepancy", dc, entry.hazard_class,
                f"Declared class {dc} is a SUBSIDIARY hazard of this entry; primary hazard is {entry.hazard_class}.")
    else:
        acc.add("hazard_class", "discrepancy", dc, entry.hazard_class, "Primary hazard class does not match.")

    ds = decl.get("subsidiary_hazards")
    if ds is None:
        if entry.subsidiary_hazards:
            acc.add("subsidiary_hazards", "insufficient", None, entry.subsidiary_hazards,
                    "Subsidiary hazards not declared but the entry has subsidiary hazard(s).")
        else:
            acc.add("subsidiary_hazards", "match", None, [], "No subsidiary hazard in entry; none declared.")
    else:
        dset = {tu.normalize_class(x) for x in ds if x}
        eset = set(entry.subsidiary_hazards)
        if dset == eset:
            acc.add("subsidiary_hazards", "match", sorted(dset), sorted(eset), "Subsidiary hazards match.")
        else:
            missing, extra = sorted(eset - dset), sorted(dset - eset)
            acc.add("subsidiary_hazards", "discrepancy", sorted(dset), sorted(eset),
                    f"Subsidiary hazards differ. Missing: {missing or 'none'}; not in entry: {extra or 'none'}.")

    raw_pg = decl.get("packing_group")
    dpg = tu.normalize_pg(raw_pg)
    if raw_pg and dpg is None and str(raw_pg).strip().upper() not in ("-", "N/A", "NA", "NONE"):
        acc.add("packing_group", "discrepancy", raw_pg, entry.packing_groups, f"'{raw_pg}' is not a valid packing group.")
    elif not entry.packing_groups:
        if dpg:
            acc.add("packing_group", "discrepancy", dpg, None,
                    "A packing group is declared but this entry has no packing group assigned.")
        else:
            acc.add("packing_group", "match", None, None, "No packing group applicable to this entry; none declared.")
    elif dpg is None:
        acc.add("packing_group", "insufficient", None, entry.packing_groups,
                f"Packing group required (entry permits {', '.join(entry.packing_groups)}) but not declared.")
    elif dpg not in entry.packing_groups:
        acc.add("packing_group", "discrepancy", dpg, entry.packing_groups,
                f"Packing group {dpg} is not available for this entry (permits {', '.join(entry.packing_groups)}).")
    elif len(entry.packing_groups) > 1:
        acc.add("packing_group", "condition", dpg, entry.packing_groups,
                "Packing group is permitted, but the entry has several; the assignment depends on classification "
                "criteria (e.g. flash point / boiling point / toxicity data). Confirm from test data or SDS.")
    else:
        acc.add("packing_group", "match", dpg, entry.packing_groups, "Packing group matches.")

    if entry.special_provisions is None:
        acc.add("special_provisions", "condition", None, None,
                "Special provisions are NOT LOADED for this entry; they cannot be evaluated.")
    elif entry.special_provisions:
        acc.add("special_provisions", "condition", None, entry.special_provisions,
                "Entry carries special provisions; each must be reviewed for applicability.")

    if mode == "IMDG":
        dmp = decl.get("marine_pollutant")
        if entry.marine_pollutant is None:
            acc.add("marine_pollutant", "condition", dmp, None,
                    "Marine pollutant status not loaded for this entry; determine from DGL and classification criteria.")
        elif dmp is None:
            acc.add("marine_pollutant", "insufficient", None, entry.marine_pollutant, "Marine pollutant status not declared.")
        elif bool(dmp) != (entry.marine_pollutant == "P"):
            acc.add("marine_pollutant", "discrepancy", dmp, entry.marine_pollutant, "Marine pollutant status differs.")
        else:
            acc.add("marine_pollutant", "match", dmp, entry.marine_pollutant, "Marine pollutant status matches.")
    return acc


DOC_FIELDS = ("un_number", "proper_shipping_name", "hazard_class", "packing_group")


def cross_check_documents(docs: list[dict]) -> list[dict]:
    """Compare SDS / declaration / package marks / manifest against each other."""
    findings = []
    norm = {
        "un_number": lambda v: tu.normalize_un(v)[0] if v else None,
        "proper_shipping_name": lambda v: tu.canonical_spelling(tu.strip_technical_name(v)[0]) if v else None,
        "hazard_class": tu.normalize_class,
        "packing_group": tu.normalize_pg,
    }
    for f in DOC_FIELDS:
        vals = {}
        for d in docs:
            v = d.get(f)
            if v not in (None, ""):
                vals[d.get("document_type", "document")] = (v, norm[f](v))
        distinct = {nv for _, nv in vals.values()}
        if len(distinct) > 1:
            findings.append({"field": f, "result": "discrepancy",
                             "values": {k: raw for k, (raw, _) in vals.items()},
                             "message": f"{f.replace('_', ' ').title()} is inconsistent between documents — "
                                        "possible misdeclaration or document error."})
    for d in docs:
        missing = [f for f in DOC_FIELDS if not d.get(f)]
        if missing:
            findings.append({"field": ",".join(missing), "result": "insufficient", "document": d.get("document_type"),
                             "message": f"{d.get('document_type', 'Document')} does not state: {', '.join(missing)}."})
    return findings


def verify(db: Session, declared: dict, mode: str, documents: list[dict] | None = None,
           today: dt.date | None = None) -> dict:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    corrective: list[str] = []
    notes: list[str] = []
    un, un_notes = tu.normalize_un(declared.get("un_number"))
    notes += un_notes
    coverage = mode_coverage(db, mode, today)
    result = {"mode": mode, "mode_label": MODE_LABEL[mode], "declared": declared, "normalized_un": un,
              "coverage": coverage, "general_limitation": GENERAL_LIMITATION, "notes": notes,
              "requires_human_approval": True, "decision": "NOT APPROVED — assistance only; requires authorised review"}

    if not un:
        result.update(status=INSUFFICIENT, provisional_status=INSUFFICIENT, checks=[],
                      corrective_actions=["Provide a valid UN/ID number (format UNnnnn) from the shipping documents."])
        return result

    mode_entries = [e for e in _entries_for(db, un, mode) if effective_status(e.source, today) == "current"]
    superseded = [e for e in _entries_for(db, un, mode) if effective_status(e.source, today) != "current"]
    reference = [] if mode == "UN_MODEL" else [e for e in _entries_for(db, un, "UN_MODEL")
                                               if effective_status(e.source, today) == "current"]
    if superseded:
        notes.append(f"{len(superseded)} entr(y/ies) for {un} exist only in superseded or not-yet-effective "
                     "editions and were NOT used.")

    candidates = mode_entries or reference
    basis = "mode" if mode_entries else "reference_only"
    if not candidates:
        result.update(status=NOT_VERIFIED, provisional_status=INSUFFICIENT, checks=[], matched_entry=None,
                      corrective_actions=[f"No {MODE_LABEL[mode]} entry for {un} is loaded. Verify manually against "
                                          "the applicable authoritative edition, or load the licensed dataset.",
                                          "Do NOT treat the absence of data as evidence that the goods are not dangerous."])
        return result

    # Choose the best-matching variant; report conflicts between current sources.
    scored = []
    for e in candidates:
        acc = _compare_entry(declared, e, mode)
        score = sum(1 for c in acc.checks if c.result == "match") - 2 * sum(1 for c in acc.checks if c.result == "discrepancy")
        scored.append((score, e, acc))
    scored.sort(key=lambda t: -t[0])
    _, entry, acc = scored[0]

    conflicts = []
    by_source = {}
    for e in candidates:
        by_source.setdefault(e.source.code, []).append(e)
    if len(by_source) > 1:
        sigs = {(e.hazard_class, tuple(sorted(e.subsidiary_hazards)), tuple(e.packing_groups),
                 tu.norm_text(e.proper_shipping_name)) for e in candidates if e.variant == entry.variant}
        if len(sigs) > 1:
            conflicts = [entry_view(e) for e in candidates]
            notes.append("CONFLICT: current sources disagree on this entry. Qualified review required.")

    provisional = acc.status()
    authoritative, limitations = entry_is_authoritative(entry, today)
    if basis == "reference_only":
        limitations = [f"No {MODE_LABEL[mode]} data loaded for {un}. The comparison used UN Model Regulations "
                       "reference data only; mode-specific provisions may differ."] + limitations
        authoritative = False
    final = provisional if (authoritative and not conflicts) else NOT_VERIFIED

    for c in acc.checks:
        if c.result == "discrepancy":
            corrective.append(f"Correct or justify {c.field.replace('_', ' ')}: declared '{c.declared}', "
                              f"reference '{c.reference}'. {c.message}")
        elif c.result == "insufficient":
            corrective.append(f"Provide {c.field.replace('_', ' ')}. {c.message}")
    doc_findings = cross_check_documents(documents) if documents else []
    for f in doc_findings:
        if f["result"] == "discrepancy":
            corrective.append(f"Reconcile {f['field']} across documents: {f['values']}")
            if final == VERIFIED or final == MATCH_COND:
                final = DISCREPANCY
            if provisional in (VERIFIED, MATCH_COND):
                provisional = DISCREPANCY
    if not authoritative:
        corrective.append("Have a qualified DG professional verify this entry against the applicable authoritative edition.")

    result.update(
        status=final, provisional_status=provisional, basis=basis,
        matched_entry=entry_view(entry, mode), checks=[c.as_dict() for c in acc.checks],
        alternatives=[entry_view(e) for _, e, _ in scored[1:]], conflicts=conflicts,
        document_findings=doc_findings, data_limitations=limitations, corrective_actions=corrective,
        evidence=[entry_evidence(entry, today)],
    )
    return result


# ---------------------------------------------------------------------------------------------
CATEGORIES = {
    "CONFIRMED": "Confirmed classification based on an authoritative, applicable source.",
    "CANDIDATE": "Candidate classification — more information or qualified verification required.",
    "NON_DG": "Not dangerous goods under a specified rule set (only by recorded qualified determination).",
    "NOT_REGULATED": "Not regulated under a specific provision or exemption (only by recorded qualified determination).",
    "UNKNOWN": "Unknown or unverified classification.",
}


def identify(db: Session, name: str | None = None, un: str | None = None, cas: str | None = None,
             text: str | None = None, mode: str = "IMDG", context: dict | None = None) -> dict:
    context = context or {}
    entries = [e for e in _entries_for(db) if effective_status(e.source) == "current"]
    hits: dict[int, dict] = {}
    notes: list[str] = []

    def hit(e: DGEntry, reason: str, weight: int):
        h = hits.setdefault(e.id, {"entry": e, "reasons": [], "score": 0})
        h["reasons"].append(reason)
        h["score"] += weight

    uns = []
    if un:
        n, nn = tu.normalize_un(un)
        notes += nn
        if n:
            uns.append(n)
        else:
            notes.append(f"Supplied UN number '{un}' is invalid.")
    if text:
        for n, nn in tu.find_un_numbers(text):
            uns.append(n)
            notes += nn
    cas_list = []
    if cas:
        cas_list.append({"cas": cas.strip(), "checksum_valid": tu.cas_checksum_ok(cas)})
    if text:
        cas_list += tu.find_cas_numbers(text)
    for c in cas_list:
        if not c["checksum_valid"]:
            notes.append(f"CAS {c['cas']} fails the CAS check-digit test — likely a typing/OCR error. Not used.")

    for e in entries:
        if e.un_number in uns:
            hit(e, f"UN number {e.un_number} supplied/extracted", 5)
        for c in cas_list:
            if c["checksum_valid"] and c["cas"] in e.cas_numbers:
                hit(e, f"CAS {c['cas']} associated with this entry (concentration/form not confirmed)", 3)
        if name:
            q = tu.norm_text(name)
            names = tu.psn_alternatives(e.proper_shipping_name) + [tu.norm_text(s) for s in e.synonyms]
            if q in names:
                hit(e, f"Name '{name}' matches entry name/synonym", 4)
            else:
                r = max((difflib.SequenceMatcher(None, q, n).ratio() for n in names), default=0)
                if r >= 0.82:
                    hit(e, f"Name '{name}' is similar to entry name (similarity {r:.2f})", 2)

    results = []
    for h in sorted(hits.values(), key=lambda h: -h["score"]):
        e = h["entry"]
        ok, lim = entry_is_authoritative(e)
        mode_ok = e.source.rule_set == mode
        strong = len(h["reasons"]) >= 2 and h["score"] >= 7
        category = "CONFIRMED" if (ok and mode_ok and strong) else "CANDIDATE"
        confidence = "high" if strong else ("medium" if h["score"] >= 4 else "low")
        if not ok:
            confidence = f"{confidence} (identity match) — data NOT authoritative"
        results.append({"category": category, "category_description": CATEGORIES[category],
                        "confidence": confidence, "match_reasons": h["reasons"],
                        "rule_set_of_data": e.source.rule_set,
                        "mode_specific": mode_ok,
                        "entry": entry_view(e, mode), "limitations": lim})

    missing = []
    for k, label in [("concentration", "concentration / composition"), ("physical_state", "physical state"),
                     ("quantity", "quantity per package"), ("packaging", "packaging type"),
                     ("flash_point", "flash point / classification test data")]:
        if not context.get(k):
            missing.append(label)
    if not results:
        overall = {"category": "UNKNOWN", "category_description": CATEGORIES["UNKNOWN"],
                   "message": "No match in the loaded datasets. This does NOT mean the product is non-dangerous. "
                              "Obtain the SDS (Section 14), composition and test data and refer to a qualified "
                              "DG professional."}
    else:
        overall = {"category": results[0]["category"], "category_description": results[0]["category_description"]}
    ghs_note = None
    if text and re.search(r"\bH[2-4]\d{2}\b", text):
        ghs_note = ("GHS hazard statements detected. GHS (workplace/supply) classification is distinct from "
                    "transport classification: a product may be GHS-hazardous without being regulated for a given "
                    "transport mode, and vice versa.")
    return {"mode": mode, "overall": overall, "candidates": results, "extracted_un_numbers": uns,
            "extracted_cas": cas_list, "notes": notes, "missing_information": missing, "ghs_note": ghs_note,
            "categories": CATEGORIES, "requires_human_review": True}
