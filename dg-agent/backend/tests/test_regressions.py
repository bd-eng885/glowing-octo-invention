"""Regression tests for defects found in the Phase 1–3 validation run.

As in test_acceptance.py, these check engine/application behaviour. Synthetic text and
demo/fixture data are used; nothing here asserts a real-world regulatory classification.
"""
from __future__ import annotations

import re
import subprocess

from app.engines import documents

from .conftest import login


# Defect 1: Section 14 values on the next line / without a colon were silently dropped.
LAYOUTS = {
    "eu_next_line": "SECTION 14: Transport information\n14.1. UN number or ID number\nUN 1090\n14.2. UN proper shipping name\n"
                    "ACETONE\n14.3. Transport hazard class(es)\n3\n14.4. Packing group\nII\n",
    "no_colon": "14. TRANSPORT INFORMATION\nUN-No. UN1090\nProper shipping name ACETONE\nTransport hazard class 3\nPacking group II\n",
    "mode_qualifier": "SECTION 14 Transport information\nUN number (IMDG): 1090\nProper shipping name (IMDG): ACETONE\n"
                      "Transport hazard class(es) (IMDG): 3\nPacking group (IMDG): II\n",
}


def test_sds_section14_layouts():
    for name, text in LAYOUTS.items():
        f = documents.parse_sds(text)["fields"]
        assert (f["un_numbers"], f["proper_shipping_name"], f["hazard_class"], f["packing_group"]) == \
            (["UN1090"], "ACETONE", "3", "II"), name


def test_sds_subsidiary_and_no_false_class_from_next_heading():
    f = documents.parse_sds("SECTION 14: Transport information\nUN number: UN1992\nTransport hazard class(es): 3 (6.1)\n"
                            "Packing group: II\n")["fields"]
    assert f["hazard_class"] == "3" and f["subsidiary_hazards"] == ["6.1"]
    r = documents.parse_sds("SECTION 14: Transport information\n14.1 UN number\nUN1090\n14.3 Transport hazard class(es)\n"
                            "14.4 Packing group\nII\n")
    assert r["fields"]["hazard_class"] is None  # must not read "1" from the "14.4" heading
    msgs = " ".join(x["finding"] for x in r["findings"])
    assert "Proper Shipping Name could not be extracted" in msgs and "transport hazard class could not be extracted" in msgs


def test_sds_ocr_packing_group_confusion():
    r = documents.parse_sds("SECTION 14: Transport information\nUN number: UN1090\nPacking group: Il\n")
    assert r["fields"]["packing_group"] == "II"
    assert any("OCR" in w for w in r["warnings"])


def test_scanned_pdf_sds_end_to_end(client, op):
    from PIL import Image, ImageDraw, ImageFont
    import io

    lines = ["SECTION 1: Identification", "Product name: Synthetic Test Solvent", "SECTION 3: Composition",
             "CAS 67-56-1", "SECTION 14: Transport information", "UN number: UN1230",
             "UN proper shipping name: METHANOL", "Transport hazard class(es): 3 (6.1)", "Packing group: II"]
    img = Image.new("RGB", (1400, 700), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("DejaVuSans.ttf", 34)
    for i, line in enumerate(lines):
        d.text((30, 30 + i * 60), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=150)
    r = client.post("/api/documents/upload", files={"file": ("scan.pdf", buf.getvalue(), "application/pdf")},
                    data={"purpose": "sds"}, headers=op).json()
    f = r["extraction"]["sds"]["fields"]
    assert r["extraction"]["method"] == "ocr"
    assert f["un_numbers"] == ["UN1230"] and f["hazard_class"] == "3" and f["subsidiary_hazards"] == ["6.1"]
    assert f["packing_group"] == "II" and f["cas_numbers"][0] == {"cas": "67-56-1", "checksum_valid": True}


# Defect 2: unmatched extracted UN number was hidden behind CAS-based pure-substance candidates.
def test_identify_unmatched_un_is_unknown(client, op):
    r = client.post("/api/dg/identify", json={"text": "UN1992 mixture CAS 67-56-1 CAS 108-88-3"}, headers=op).json()
    assert r["unmatched_un_numbers"] == ["UN1992"]
    assert r["overall"]["category"] == "UNKNOWN"
    assert any("pure substance" in n for n in r["notes"])


# Defect 3: acid + alkali of the same class were shown as "no general requirement" with no flag.
def test_segregation_flags_acid_alkali_same_class(client, op):
    items = [{"id": "acid", "un_number": "UN1789", "hazard_class": "8", "quantity": "200 L", "package": "drum"},
             {"id": "alkali", "un_number": "UN1823", "hazard_class": "8", "quantity": "500 kg", "package": "bags"}]
    r = client.post("/api/segregation/check", json={"mode": "IMDG", "arrangement": "same_ctu", "items": items},
                    headers=op).json()
    p = r["pairs"][0]
    assert p["code"] == "X" and p["status"] == "hold"
    assert any("NON-REGULATORY" in c for c in p["conditions"])
    assert r["matrix"]["acid"]["alkali"]["status"] == "hold"
    assert r["decision"].startswith("HOLD")


# Defect 4: ERP assumed trained responders and could not take capabilities or real source references.
SITE = {k: f"SITE-{k}" for k in [
    "site_name", "address", "description", "scope_areas", "max_inventory", "receptors", "scenario_assumptions",
    "incident_controller", "deputy_controller", "ert_leader", "dgsa", "hse_officer", "alarm_method", "radio_channels",
    "muster_points", "shelter_locations", "competency_standard", "ppe_inventory", "spill_equipment", "fire_systems",
    "drain_isolation", "medical_facility", "eyewash_locations", "notification_obligations", "waste_contractor",
    "level1_criteria", "ert_capability", "external_support", "fire_response_time", "legislation", "sds_register"]}


def test_erp_uses_supplied_details_capabilities_and_sources(client, op):
    contacts = [{"role": "Emergency services", "name": "Test Fire Service", "phone": "000"}]
    body = {"scenario": "toxic_gas_release", "site": SITE, "contacts": contacts,
            "capabilities": {"trained_hazmat_team": "no"},
            "substances": [{"un_number": "UN1017", "chemical_name": "Chlorine", "max_quantity": 900}]}
    r = client.post("/api/erp/generate", json=body, headers=op).json()
    text = str(r)
    assert r["required_inputs_missing"] == [] and "REQUIRED INPUT" not in text
    assert "Test Fire Service" in text and "SITE-muster_points" in text
    strategy = r["sections"][9]["content"][0]
    assert strategy.startswith("NO on-site trained hazmat team")
    refs = r["sections"][17]["content"]
    by_code = {s["source_code"]: s for s in refs["regulatory_sources_in_library"]}
    assert by_code["IMDG-42-24"]["content_loaded"] is False
    assert by_code["IMDG-42-24"]["use_in_this_plan"].startswith("Reference only")
    assert "IMDG-41-22" not in by_code  # superseded editions are not offered as references
    assert any("DEMO-UN-SEED" in s and "authoritative: NO" in s for s in refs["substance_data_used"])
    # Capability not stated -> never assumed
    r2 = client.post("/api/erp/generate", json={**body, "capabilities": {}}, headers=op).json()
    assert any("hazmat response capability" in m for m in r2["required_inputs_missing"])
    assert "do NOT perform containment" in r2["sections"][9]["content"][0]


# Defect 5: audit log readable by viewer/operator roles.
def test_audit_log_restricted(client):
    for who, code in (("viewer", 403), ("operator", 403), ("reviewer", 200), ("approver", 200), ("admin", 200)):
        assert client.get("/api/audit", headers=login(client, who)).status_code == code, who


# Arabic content must render in PDF exports (shaped glyphs in an embedded Unicode font).
def test_pdf_export_renders_arabic(client, op):
    r = client.post("/api/erp/generate", json={"scenario": "chemical_spill", "save": True,
                                               "site": {"site_name": "ميناء الاختبار"}}, headers=op).json()
    pdf = client.get(f"/api/reports/{r['report_id']}/export/pdf", headers=op).content
    assert pdf.startswith(b"%PDF") and b"DejaVuSans" in pdf
    txt = subprocess.run(["pdftotext", "-", "-"], input=pdf, capture_output=True).stdout.decode("utf-8", "replace")
    assert re.search(r"[؀-ۿﹰ-﻿]", txt)


# Defect 7: coverage reported IMDG/IATA "content available" when only a demo rule table existed.
def test_coverage_separates_dgl_entries_from_rule_tables(client, op):
    cov = client.get("/api/sources/coverage", headers=op).json()
    un = cov["UN_MODEL"]
    assert un["dgl_entries"] >= 39 and un["dgl_state"] == "DEMO / UNVERIFIED ONLY"
    imdg = {s["source_code"]: s for s in cov["IMDG"]["sources"]}
    assert imdg["DEMO-IMDG-SEG-SEED"]["dgl_entries"] == 0 and imdg["DEMO-IMDG-SEG-SEED"]["rule_tables"] == ["IMDG-SEG-DEMO"]
    assert imdg["IMDG-42-24"]["dgl_entries"] == 0 and imdg["IMDG-42-24"]["content_loaded"] is False


# Defect 8: templates inserted [REQUIRED INPUT] placeholders without listing them as missing information.
def test_templates_list_all_required_inputs(client, op):
    for kind, data in (("spill_incident", {"activity": "Yard", "date_time": "2026-10-01"}),
                       ("drill_evaluation", {"activity": "Terminal", "scenario": "release", "objectives": ["x"]})):
        r = client.post("/api/reports/build", json={"kind": kind, "data": data}, headers=op).json()
        placeholders = str({k: v for k, v in r.items() if k != "missing_information"}).count("REQUIRED INPUT")
        assert placeholders > 0 and r["missing_information"], kind
    r = client.post("/api/reports/build", json={"kind": "spill_incident", "data": {"activity": "Yard"}}, headers=op).json()
    assert "location" in r["missing_information"] and "date time" in r["missing_information"]
