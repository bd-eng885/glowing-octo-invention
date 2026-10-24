# API workflow probe against a running instance. Prints raw outcomes for workflows A-I.
# Usage: python3 make_docs.py && python3 api_probe.py   (env BASE_URL, DEMO_USERS_PASSWORD)
import httpx, json, sys
import os
B = os.getenv("BASE_URL", "http://127.0.0.1:5173")
c = httpx.Client(base_url=B, timeout=120)
def login(u):
    r = c.post("/api/auth/login", json={"email": f"{u}@demo.local", "password": os.getenv("DEMO_USERS_PASSWORD", "choose-a-password")})
    return {"Authorization": "Bearer " + r.json()["access_token"]} if r.status_code == 200 else r
op, ap, ad, vw, rv = (login(x) for x in ("operator", "approver", "admin", "viewer", "reviewer"))
P = lambda *a: print(*a, flush=True)
def post(p, j, h=op): r = c.post(p, json=j, headers=h); return r.status_code, (r.json() if "json" in r.headers.get("content-type","") else r.text)

P("=== A. UN/PSN verification (live, demo data)")
for mode, d in [("IMDG", dict(un_number="UN1090", proper_shipping_name="ACETONE", hazard_class="3", packing_group="II", marine_pollutant=False)),
                ("IMDG", dict(un_number="UN1090", proper_shipping_name="ACETON", hazard_class="3", packing_group="II")),
                ("IMDG", dict(un_number="UN1230", proper_shipping_name="METHANOL", hazard_class="6.1", packing_group="II")),
                ("IATA", dict(un_number="UN1090", proper_shipping_name="ACETONE", hazard_class="3", packing_group="II")),
                ("UN_MODEL", dict(un_number="UN1090", proper_shipping_name="ACETONE", hazard_class="3", packing_group="II")),
                ("IMDG", dict(un_number="UN1992", proper_shipping_name="FLAMMABLE LIQUID, TOXIC, N.O.S.", hazard_class="3"))]:
    s, r = post("/api/dg/verify", {"mode": mode, "declared": d})
    P(mode, d["un_number"], d["proper_shipping_name"], "->", s, r.get("status"), "| provisional:", r.get("provisional_status"), "| basis:", r.get("basis"))
    for ch in r.get("checks", []):
        if ch["result"] != "match": P("    ", ch["field"], ch["result"], "-", ch["message"][:110])
    ev = (r.get("evidence") or [{}])[0]
    P("    evidence:", ev.get("source_code"), "|", ev.get("publisher"), "|", ev.get("edition"), "| effective:", ev.get("effective_date"), "| section:", ev.get("section_ref"), "| authoritative:", ev.get("authoritative"))

P("\n=== B. SDS upload & extraction")
for fn, ct, purpose in [("sds_text.pdf", "application/pdf", "sds"), ("sds_scanned.pdf", "application/pdf", "sds"), ("scan.png", "image/png", "sds")]:
    r = c.post("/api/documents/upload", files={"file": (fn, open(fn, "rb"), ct)}, data={"purpose": purpose}, headers=op)
    j = r.json(); e = j.get("extraction", {}); s = e.get("sds", {}); f = s.get("fields", {})
    P(fn, r.status_code, "method:", e.get("method"), "| product:", f.get("product_name"), "| UN:", f.get("un_numbers"), "| PSN:", f.get("proper_shipping_name"),
      "| class:", f.get("hazard_class"), "| sub:", f.get("subsidiary_hazards"), "| PG:", f.get("packing_group"), "| MP:", f.get("marine_pollutant"),
      "| CAS:", [x["cas"] + ("" if x["checksum_valid"] else "!") for x in f.get("cas_numbers", [])], "| H:", f.get("h_statements"), "| rev:", f.get("revision_date"))
    P("    findings:", [x["finding"][:70] for x in s.get("findings", [])], "| warnings:", e.get("warnings"))
s, r = post("/api/dg/identify", {"name": "methanol", "cas": "67-56-1", "mode": "IMDG"})
P("identify methanol ->", r["overall"]["category"], [(x["entry"]["un_number"], x["category"], x["confidence"]) for x in r["candidates"]])
s, r = post("/api/dg/identify", {"text": open("sds_text.pdf","rb") and "UN1992 CAS 67-56-1 CAS 108-88-3 H225", "mode": "IMDG"})
P("identify SDS text ->", r["overall"], [(x["entry"]["un_number"], x["category"]) for x in r["candidates"]], r["ghs_note"] is not None)

P("\n=== C/E. IMDG segregation, multi-material")
items = [{"id":"petrol","un_number":"UN1203","quantity":"800 L","package":"drums"},
         {"id":"h2o2","un_number":"UN2014","quantity":"250 L","package":"IBC"},
         {"id":"naoh","un_number":"UN1823","quantity":"500 kg","package":"bags"},
         {"id":"cl2","un_number":"UN1017","quantity":"1 cyl","package":"cylinder"},
         {"id":"hcl","un_number":"UN1789","quantity":"200 L","package":"drum","hazard_class":"8"},
         {"id":"liion","un_number":"UN3480","quantity":"10 kg","package":"box"}]
for arr in ("same_ctu", "same_hold", None):
    s, r = post("/api/segregation/check", {"mode":"IMDG","arrangement":arr,"items":items})
    P("IMDG", arr, s, r["decision"], "| table:", r["rule_table"]["code"], "authoritative:", r["rule_table"]["authoritative"], "| pairs:", len(r["pairs"]))
    if arr == "same_ctu":
        for p in r["pairs"]: P("   ", p["a"], p["b"], p["status"], p["code"], p.get("governing_combination"))
s, r = post("/api/segregation/check", {"mode":"IMDG","items":[{"id":"x","hazard_class":"1"},{"id":"y","hazard_class":"3"}]})
P("class '1' without division ->", r["pairs"][0]["status"], r["pairs"][0]["issues"])

P("\n=== D. IATA")
s, r = post("/api/dg/verify", {"mode":"IATA","declared":{"un_number":"UN3480","proper_shipping_name":"LITHIUM ION BATTERIES","hazard_class":"9"}})
P("IATA verify UN3480 ->", r["status"], "| basis:", r.get("basis"), "| limitations:", r.get("data_limitations", [])[:1])
P("    labelling:", r.get("matched_entry", {}).get("labelling", {}).get("marks"))
s, r = post("/api/segregation/check", {"mode":"IATA","arrangement":"same_uld","items":[{"id":"a","hazard_class":"3","quantity":"1","package":"x"},{"id":"b","hazard_class":"5.1","quantity":"1","package":"x"},{"id":"c","hazard_class":"1.4","explosive_compat_group":"S","quantity":"1","package":"x"}]})
P("IATA seg ->", r["decision"], [(p["a"],p["b"],p["status"]) for p in r["pairs"]], "| manual checks:", len(r["manual_checks"]))

P("\n=== F. Unknown spill")
s, r = post("/api/spill/assess", {"data": {"physical_state":"liquid","quantity_estimate":50,"vapour_release":True,"trained_responders_available":True,"sds_available":False}})
P(r["response_level"]); P("  triggers:", r["escalation_triggers"]); P("  first 4 priorities:", r["immediate_priorities"][:4]); P("  containment:", r["containment"]); P("  ppe:", r["ppe"][:80])

P("\n=== G. ERP with site details")
site = {k: f"SITE-{k}" for k in ["site_name","address","description","scope_areas","max_inventory","receptors","scenario_assumptions","incident_controller","deputy_controller","ert_leader","dgsa","hse_officer","alarm_method","radio_channels","muster_points","shelter_locations","competency_standard","ppe_inventory","spill_equipment","fire_systems","drain_isolation","medical_facility","eyewash_locations","notification_obligations","waste_contractor","level1_criteria","ert_capability","external_support","fire_response_time","legislation","sds_register"]}
contacts = [{"role":"Emergency services","name":"Civil Defence","phone":"998"},{"role":"DGSA","name":"Probe DGSA","phone":"+000"}]
s, r = post("/api/erp/generate", {"scenario":"toxic_gas_release","site":site,"substances":[{"un_number":"UN1017","chemical_name":"Chlorine","max_quantity":900}],"contacts":contacts,"capabilities":{"trained_hazmat_team":"yes"},"save":True,"title":"ERP probe"})
P("ERP", s, "sections:", len(r["sections"]), "| missing:", r["required_inputs_missing"], "| report:", r.get("report_id"))
txt = json.dumps(r); P("  REQUIRED INPUT occurrences:", txt.count("REQUIRED INPUT"), "| contacts present:", "Civil Defence" in txt)
P("  section 18:", json.dumps(r["sections"][17]["content"])[:400])
P("  section 8 substance:", json.dumps(r["sections"][7]["content"])[:300])
erp_id = r.get("report_id")

P("\n=== I. Auth / roles / audit / exports")
P("bad password:", c.post("/api/auth/login", json={"email":"operator@demo.local","password":"x"}).status_code)
P("no token:", c.get("/api/reports").status_code, "| viewer analyze:", post("/api/dg/verify", {"mode":"IMDG","declared":{"un_number":"UN1090"}}, vw)[0])
P("viewer upload:", c.post("/api/documents/upload", files={"file":("a.txt",b"hello world text","text/plain")}, data={"purpose":"sds"}, headers=vw).status_code)
P("operator users list:", c.get("/api/users", headers=op).status_code, "| admin users list:", c.get("/api/users", headers=ad).status_code)
P("submit:", post(f"/api/reports/{erp_id}/submit", {"comment":"probe"})[0])
P("operator approve:", post(f"/api/reports/{erp_id}/approve", {"comment":"x"})[0], "| admin approve:", post(f"/api/reports/{erp_id}/approve", {"comment":"x"}, ad)[0],
  "| reviewer approve:", post(f"/api/reports/{erp_id}/approve", {"comment":"x"}, rv)[0], "| reviewer review:", post(f"/api/reports/{erp_id}/review", {"comment":"ok"}, rv)[0],
  "| approver approve:", post(f"/api/reports/{erp_id}/approve", {"comment":"probe approval"}, ap)[0])
for fmt in ("pdf","docx","xlsx","csv"):
    r = c.get(f"/api/reports/{erp_id}/export/{fmt}", headers=op); P("export", fmt, r.status_code, r.headers.get("content-type"), len(r.content), r.content[:4])
    open(f"erp.{fmt}","wb").write(r.content)
P("operator audit:", c.get("/api/audit", headers=op).status_code); a = c.get("/api/audit?limit=500", headers=rv).json(); acts = {}
for x in a: acts[x["action"]] = acts.get(x["action"],0)+1
P("audit actions:", acts); P("chain:", c.get("/api/audit/verify", headers=rv).json())
P("viewer audit:", c.get("/api/audit", headers=vw).status_code)
