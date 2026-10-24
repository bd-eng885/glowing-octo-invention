import { useEffect, useState } from "react";
import { api, type Json } from "../api";
import { Badge, Bullets, Card, ErrorBox, Evidence, Field, SavedNote, splitList, useRunner, Value } from "../components";
import { useI18n } from "../i18n";

const FLAGS: [string, string][] = [["fire", "Fire present / imminent"], ["vapour_release", "Vapour / gas release"],
  ["injuries_or_exposure", "Injury or exposure"], ["reaction_observed", "Reaction observed (heat, fumes, bubbling)"],
  ["drains_nearby", "Drains nearby"], ["waterway_nearby", "Waterway nearby"], ["personnel_nearby", "Personnel nearby"],
  ["container_damaged", "Container / package damaged"], ["pressure_receptacle_involved", "Pressure receptacle involved"],
  ["trained_responders_available", "Trained hazmat responders available"], ["sds_available", "SDS available"]];

export function SpillPage() {
  const { t } = useI18n();
  const [d, setD] = useState<Json>({ chemical_name: "", un_number: "", hazard_class: "", quantity_estimate: "",
    physical_state: "liquid", location: "", indoor: "outdoor", equipment: "" });
  const { result: r, error, busy, run, controls } = useRunner("/api/spill/assess");
  const set = (k: string) => (e: Json) => setD({ ...d, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  return (
    <div className="page">
      <Card title={t("spill")}>
        <div className="alert bad">In an emergency: protect life, raise the alarm, isolate the area and call the site emergency team / emergency services FIRST. This tool supports — it does not replace — the approved site ERP, the SDS and specialist responders.</div>
        <div className="grid">
          <Field label={t("name")}><input value={d.chemical_name} onChange={set("chemical_name")} placeholder="leave blank if unknown" /></Field>
          <Field label={t("unNumber")}><input value={d.un_number} onChange={set("un_number")} /></Field>
          <Field label={t("hazardClass")}><input value={d.hazard_class} onChange={set("hazard_class")} /></Field>
          <Field label="Estimated quantity (L or kg)"><input type="number" value={d.quantity_estimate} onChange={set("quantity_estimate")} /></Field>
          <Field label="Physical state"><select value={d.physical_state} onChange={set("physical_state")}><option>liquid</option><option>solid</option><option>gas</option><option>unknown</option></select></Field>
          <Field label="Location"><input value={d.location} onChange={set("location")} placeholder="berth / warehouse bay / truck" /></Field>
          <Field label="Indoor / outdoor"><select value={d.indoor} onChange={set("indoor")}><option>outdoor</option><option>indoor</option></select></Field>
          <Field label="Available equipment"><input value={d.equipment} onChange={set("equipment")} /></Field>
        </div>
        <div className="checks">{FLAGS.map(([k, l]) => (
          <label key={k} className="check"><input type="checkbox" checked={!!d[k]} onChange={set(k)} /> {l}</label>))}</div>
        {controls}
        <button disabled={busy} onClick={() => run({ data: { ...d, quantity_estimate: d.quantity_estimate === "" ? null : Number(d.quantity_estimate) } })}>{busy ? t("loading") : t("run")}</button>
        <ErrorBox error={error} />
      </Card>
      {r && (
        <Card title={<Badge s={r.response_level} />}>
          <SavedNote id={r.report_id} />
          <Bullets title="Escalation triggers" items={r.escalation_triggers} tone="bad" />
          <Bullets title="A. Immediate priorities" items={r.immediate_priorities} tone="bad" />
          <h4>B. Hazard assessment</h4>
          {r.hazard_assessment.length ? r.hazard_assessment.map((h: Json, i: number) => (
            <Bullets key={i} title={`${h.hazard} — ${h.name}${h.role ? ` (${h.role})` : ""}`} items={h.considerations} />)) : <p className="muted">No hazard data — treat as unknown.</p>}
          <Bullets title="Incompatible material groups (screening)" items={r.incompatible_material_groups} />
          <Bullets title="Precautions — do NOT" items={r.precautions_do_not} tone="warn" />
          <Bullets title="C. Response references" items={r.response_references} />
          <Bullets title="Containment" items={r.containment} tone="warn" />
          <Bullets title="PPE" items={[r.ppe]} />
          <Bullets title="Medical & exposure" items={r.medical} />
          <Bullets title="Waste" items={r.waste} />
          <Bullets title="Notifications" items={r.notifications} />
          <Bullets title={t("notes")} items={r.data_notes} />
          <Bullets title="D. Limitations" items={r.limitations} />
          <Evidence items={r.evidence} />
        </Card>
      )}
    </div>
  );
}

const SITE_FIELDS = ["site_name", "address", "description", "scope_areas", "max_inventory", "receptors", "scenario_assumptions",
  "incident_controller", "deputy_controller", "ert_leader", "dgsa", "hse_officer", "alarm_method", "radio_channels",
  "muster_points", "shelter_locations", "competency_standard", "ppe_inventory", "spill_equipment", "fire_systems",
  "drain_isolation", "medical_facility", "eyewash_locations", "notification_obligations", "waste_contractor",
  "level1_criteria", "ert_capability", "external_support", "fire_response_time", "legislation", "sds_register"];

export function ErpPage() {
  const { t } = useI18n();
  const [scenarios, setScenarios] = useState<Record<string, string>>({});
  const [scenario, setScenario] = useState("chemical_spill");
  const [site, setSite] = useState<Record<string, string>>({});
  const [subs, setSubs] = useState("UN1830:Sulphuric acid:2000");
  const [trained, setTrained] = useState("");
  const [contacts, setContacts] = useState("Emergency services:Civil Defence:998");
  const { result: r, error, busy, run, controls } = useRunner("/api/erp/generate");
  useEffect(() => { api.get("/api/erp/scenarios").then(setScenarios).catch(() => {}); }, []);
  return (
    <div className="page">
      <Card title={t("erp")}>
        <p className="muted">Editable template. Any site detail not supplied is marked [REQUIRED INPUT] — never invented.</p>
        <Field label="Scenario"><select value={scenario} onChange={(e) => setScenario(e.target.value)}>
          {Object.entries(scenarios).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="Substances (UN:name:max quantity, separated by commas)"><input value={subs} onChange={(e) => setSubs(e.target.value)} /></Field>
        <Field label="On-site trained hazmat response team?"><select value={trained} onChange={(e) => setTrained(e.target.value)}>
          <option value="">— not stated (plan assumes NO containment by site staff) —</option><option value="yes">Yes</option><option value="no">No</option></select></Field>
        <Field label="Emergency contacts (role:name:phone, separated by commas)"><input value={contacts} onChange={(e) => setContacts(e.target.value)} /></Field>
        <details><summary>Site details ({Object.values(site).filter(Boolean).length}/{SITE_FIELDS.length} completed)</summary>
          <div className="grid">{SITE_FIELDS.map((k) => (
            <Field key={k} label={k.replace(/_/g, " ")}><input value={site[k] || ""} onChange={(e) => setSite({ ...site, [k]: e.target.value })} /></Field>))}</div>
        </details>
        {controls}
        <button disabled={busy} onClick={() => run({ scenario, site, capabilities: { trained_hazmat_team: trained },
          contacts: splitList(contacts).map((c) => { const [role, name, phone] = c.split(":"); return { role, name, phone }; }), substances: splitList(subs).map((s) => {
          const [un, name, q] = s.split(":"); return { un_number: un, chemical_name: name, max_quantity: q ? Number(q) : null };
        }) })}>{busy ? t("loading") : t("generate")}</button>
        <ErrorBox error={error} />
      </Card>
      {r && (
        <Card title={<>{r.title} <Badge s={r.status} /></>}>
          <SavedNote id={r.report_id} />
          {r.report_id && <p className="small">Download PDF/Word from Reports &amp; Audit Trail (report #{r.report_id}).</p>}
          <Bullets title="Required inputs still missing" items={r.required_inputs_missing} tone="warn" />
          {r.sections.map((s: Json) => (
            <details key={s.number} open={s.number <= 3}><summary><b>{s.number}. {s.title}</b></summary>
              <div className="erp-sec"><Value v={s.content} /></div></details>
          ))}
          <p className="small muted">{r.disclaimer}</p>
        </Card>
      )}
    </div>
  );
}

export function RiskPage() {
  const { t } = useI18n();
  const [types, setTypes] = useState<Record<string, string>>({});
  const [matrices, setMatrices] = useState<Json[]>([]);
  const [kind, setKind] = useState("hira");
  const [matrixId, setMatrixId] = useState<number | "">("");
  const [activity, setActivity] = useState("");
  const [rows, setRows] = useState<Json[]>([{ hazard: "Leaking drum during unloading", consequence: "Chemical burns", controls: "", likelihood: 3, severity: 4, additional_controls: "", residual_likelihood: 2, residual_severity: 4 }]);
  const [extra, setExtra] = useState("{}");
  const { result: r, error, busy, run, controls } = useRunner("/api/reports/build");
  useEffect(() => {
    api.get("/api/reports/templates").then(setTypes).catch(() => {});
    api.get("/api/risk/matrices").then(setMatrices).catch(() => {});
  }, []);
  const matrix = matrices.find((m) => m.id === matrixId) || matrices.find((m) => m.is_default);
  const rowKinds = ["hira", "chemical_ra", "jsa"];
  function submit() {
    let data: Json = {};
    try { data = JSON.parse(extra || "{}"); } catch { alert("Additional fields must be valid JSON"); return; }
    data.activity = activity;
    if (kind === "jsa") data.steps = rows.map((x) => ({ step: x.hazard, ...x }));
    else if (rowKinds.includes(kind)) data.rows = rows;
    run({ kind, data, matrix_id: matrixId || null });
  }
  return (
    <div className="page">
      <Card title={t("risk")}>
        <div className="grid">
          <Field label="Report type"><select value={kind} onChange={(e) => setKind(e.target.value)}>
            {Object.entries(types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Risk matrix (configurable)"><select value={matrixId} onChange={(e) => setMatrixId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Default</option>{matrices.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></Field>
          <Field label="Activity / location"><input value={activity} onChange={(e) => setActivity(e.target.value)} /></Field>
        </div>
        {matrix && <p className="small muted">Likelihood: {matrix.config.likelihood.map((l: string, i: number) => `${i + 1}=${l}`).join(", ")} · Severity: {matrix.config.severity.map((l: string, i: number) => `${i + 1}=${l}`).join(", ")}</p>}
        {rowKinds.includes(kind) && (
          <div className="scroll"><table className="table edit">
            <thead><tr>{Object.keys(rows[0]).map((k) => <th key={k}>{k.replace(/_/g, " ")}</th>)}<th /></tr></thead>
            <tbody>{rows.map((row, i) => (
              <tr key={i}>{Object.keys(rows[0]).map((k) => (
                <td key={k}><input value={row[k]} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))} /></td>))}
                <td><button className="ghost" onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button></td></tr>))}</tbody>
          </table><button className="ghost" onClick={() => setRows([...rows, { ...rows[0], hazard: "", consequence: "" }])}>+ {t("add")}</button></div>
        )}
        <Field label="Additional fields (JSON, e.g. {&quot;incident_summary&quot;: &quot;…&quot;, &quot;un_number&quot;: &quot;UN1830&quot;})"><textarea rows={3} value={extra} onChange={(e) => setExtra(e.target.value)} /></Field>
        {controls}
        <button disabled={busy} onClick={submit}>{busy ? t("loading") : t("generate")}</button>
        <ErrorBox error={error} />
      </Card>
      {r && (
        <Card title={r.title}>
          <SavedNote id={r.report_id} />
          <Bullets title={t("missing")} items={r.missing_information} tone="warn" />
          {(r.rows || r.steps) && (
            <table className="table"><thead><tr><th>Hazard / step</th><th>Initial</th><th>Residual</th></tr></thead>
              <tbody>{(r.rows || r.steps).map((x: Json, i: number) => (
                <tr key={i}><td>{x.hazard || x.step}</td>
                  <td>{(x.initial_rating || x.rating) && <span className="badge" style={{ background: (x.initial_rating || x.rating).color, color: "#fff" }}>{(x.initial_rating || x.rating).band} {(x.initial_rating || x.rating).score}</span>}</td>
                  <td>{x.residual_rating && <span className="badge" style={{ background: x.residual_rating.color, color: "#fff" }}>{x.residual_rating.band} {x.residual_rating.score}</span>}</td></tr>))}</tbody></table>
          )}
          <details><summary>Full content</summary><Value v={Object.fromEntries(Object.entries(r).filter(([k]) => !["rows", "steps", "matrix"].includes(k)))} /></details>
        </Card>
      )}
    </div>
  );
}
