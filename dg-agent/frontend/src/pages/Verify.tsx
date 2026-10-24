import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, type Json } from "../api";
import { AiExplain, Badge, Bullets, Card, ErrorBox, Evidence, Field, SavedNote, splitList, useRunner, Value } from "../components";
import { useI18n } from "../i18n";

const MODE_INFO: Record<string, string> = {
  IMDG: "Sea transport — verified only against IMDG Code data. Never substituted with IATA data.",
  IATA: "Air transport — verified only against IATA DGR data. Never substituted with IMDG data.",
  UN_MODEL: "UN Model Regulations — foundational reference; not a modal rule set.",
};

type Doc = { document_type: string; un_number: string; proper_shipping_name: string; hazard_class: string; packing_group: string };
const emptyDoc = (t: string): Doc => ({ document_type: t, un_number: "", proper_shipping_name: "", hazard_class: "", packing_group: "" });

export function VerifyPage({ fixedMode }: { fixedMode?: string }) {
  const { t } = useI18n();
  const loc = useLocation();
  const prefill = (loc.state as Json)?.prefill || {};
  const [mode, setMode] = useState(fixedMode || "IMDG");
  const [d, setD] = useState({ un_number: "", proper_shipping_name: "", hazard_class: "", subsidiary: "", packing_group: "",
                               marine_pollutant: "", ...prefill });
  const [docs, setDocs] = useState<Doc[]>([]);
  const [coverage, setCoverage] = useState<Json>(null);
  const { result, error, busy, run, controls } = useRunner("/api/dg/verify");
  useEffect(() => { if (fixedMode) setMode(fixedMode); }, [fixedMode]);
  useEffect(() => { api.get("/api/sources/coverage").then(setCoverage).catch(() => {}); }, []);
  const set = (k: string) => (e: Json) => setD({ ...d, [k]: e.target.value });
  const cov = coverage?.[mode];

  function submit() {
    const declared: Json = { un_number: d.un_number, proper_shipping_name: d.proper_shipping_name || null,
      hazard_class: d.hazard_class || null, packing_group: d.packing_group || null,
      subsidiary_hazards: d.subsidiary.trim() === "" ? null : d.subsidiary.trim() === "-" ? [] : splitList(d.subsidiary) };
    if (mode === "IMDG" && d.marine_pollutant !== "") declared.marine_pollutant = d.marine_pollutant === "yes";
    run({ mode, declared, documents: docs.filter((x) => x.un_number || x.proper_shipping_name) });
  }

  return (
    <div className="page">
      <Card title={fixedMode ? t(fixedMode === "IMDG" ? "imdg" : "iata") : t("verify")}>
        <p className="muted">{MODE_INFO[mode]}</p>
        {cov && (
          <div className={`alert ${cov.authoritative_content_available ? "info" : "warn"}`}>
            {mode} Dangerous Goods List: <b>{cov.dgl_state}</b> ({cov.dgl_entries} entries). Sources: {cov.sources.map((s: Json) => `${s.source_code} (${s.source_status}, ${s.source_verification_status}, ${s.dgl_entries} entries${s.rule_tables.length ? ", rule tables " + s.rule_tables.join("/") : ""})`).join(" · ") || "none"}.
            {!cov.authoritative_content_available && " No verified, in-force dataset — results will be NOT VERIFIED."}
          </div>
        )}
        <div className="grid">
          {!fixedMode && (
            <Field label={t("mode")}>
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="IMDG">IMDG (sea)</option><option value="IATA">IATA DGR (air)</option>
                <option value="UN_MODEL">UN Model Regulations (reference)</option>
              </select>
            </Field>
          )}
          <Field label={t("unNumber")}><input value={d.un_number} onChange={set("un_number")} placeholder="UN1203" /></Field>
          <Field label={t("psn")}><input value={d.proper_shipping_name} onChange={set("proper_shipping_name")} /></Field>
          <Field label={t("hazardClass")}><input value={d.hazard_class} onChange={set("hazard_class")} placeholder="3" /></Field>
          <Field label={t("subsidiary") + " ('-' = none)"}><input value={d.subsidiary} onChange={set("subsidiary")} placeholder="6.1" /></Field>
          <Field label={t("pg")}>
            <select value={d.packing_group} onChange={set("packing_group")}>
              <option value="">— not declared / not applicable —</option><option>I</option><option>II</option><option>III</option>
            </select>
          </Field>
          {mode === "IMDG" && (
            <Field label={t("mp")}>
              <select value={d.marine_pollutant} onChange={set("marine_pollutant")}>
                <option value="">— not declared —</option><option value="yes">Yes</option><option value="no">No</option>
              </select>
            </Field>
          )}
        </div>
        <details>
          <summary>Cross-check documents (SDS, DG Declaration, package marks, manifest) — {docs.length}</summary>
          {docs.map((doc, i) => (
            <div className="grid doc-row" key={i}>
              {(Object.keys(doc) as (keyof Doc)[]).map((k) => (
                <Field key={k} label={k.replace(/_/g, " ")}>
                  <input value={doc[k]} onChange={(e) => setDocs(docs.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))} />
                </Field>
              ))}
              <button className="ghost" onClick={() => setDocs(docs.filter((_, j) => j !== i))}>{t("remove")}</button>
            </div>
          ))}
          <div className="row">
            {["SDS", "DG Declaration", "Package marks", "Manifest"].map((n) => (
              <button key={n} className="ghost" onClick={() => setDocs([...docs, emptyDoc(n)])}>+ {n}</button>
            ))}
          </div>
        </details>
        {controls}
        <button disabled={busy || !d.un_number} onClick={submit}>{busy ? t("loading") : t("run")}</button>
        <ErrorBox error={error} />
      </Card>
      {result && <VerifyResult r={result} />}
    </div>
  );
}

export function VerifyResult({ r }: { r: Json }) {
  const { t } = useI18n();
  return (
    <Card title={<>{t("status")}: <Badge s={r.status} /></>}>
      <SavedNote id={r.report_id} />
      {r.provisional_status && r.provisional_status !== r.status && (
        <p>{t("provisional")}: <Badge s={r.provisional_status} /></p>
      )}
      <p className="alert warn small">{r.decision} · {r.general_limitation}</p>
      {r.checks?.length > 0 && (
        <table className="table">
          <thead><tr><th>Field</th><th>Result</th><th>Declared</th><th>Reference</th><th>Explanation</th></tr></thead>
          <tbody>{r.checks.map((c: Json, i: number) => (
            <tr key={i}><td>{c.field.replace(/_/g, " ")}</td><td><Badge s={c.result.toUpperCase()} /></td>
              <td><Value v={c.declared} /></td><td><Value v={c.reference} /></td><td>{c.message}</td></tr>
          ))}</tbody>
        </table>
      )}
      {r.matched_entry && (
        <details><summary>Matched entry ({r.basis === "reference_only" ? "REFERENCE ONLY — not mode data" : r.matched_entry.rule_set})</summary>
          <Value v={{ un_number: r.matched_entry.un_number, proper_shipping_name: r.matched_entry.proper_shipping_name,
                      class: r.matched_entry.hazard_class, subsidiary: r.matched_entry.subsidiary_hazards,
                      packing_groups: r.matched_entry.packing_groups, special_provisions: r.matched_entry.special_provisions_loaded ? r.matched_entry.special_provisions : "NOT LOADED",
                      labelling: r.matched_entry.labelling }} />
        </details>
      )}
      {r.conflicts?.length > 0 && <Bullets title="Conflicting sources" tone="bad" items={r.conflicts.map((c: Json) => `${c.evidence.source_code}: class ${c.hazard_class}, PG ${c.packing_groups.join("/") || "—"}`)} />}
      {r.document_findings?.length > 0 && <Bullets title="Document cross-check" items={r.document_findings.map((f: Json) => `${f.result.toUpperCase()}: ${f.message} ${f.values ? JSON.stringify(f.values) : ""}`)} />}
      <Bullets title={t("corrective")} items={r.corrective_actions} tone="warn" />
      <Bullets title={t("limitations")} items={r.data_limitations} />
      <Bullets title={t("notes")} items={r.notes} />
      <Evidence items={r.evidence} />
      <AiExplain result={r} />
    </Card>
  );
}

export function IdentifyPage() {
  const { t } = useI18n();
  const [f, setF] = useState({ name: "", un_number: "", cas: "", text: "", mode: "IMDG", concentration: "", physical_state: "", quantity: "", packaging: "" });
  const { result: r, error, busy, run, controls } = useRunner("/api/dg/identify");
  const set = (k: string) => (e: Json) => setF({ ...f, [k]: e.target.value });
  return (
    <div className="page">
      <Card title={t("identify")}>
        <p className="muted">Enter any combination of identifiers. Matches are candidates until verified by a qualified person against authoritative data.</p>
        <div className="grid">
          <Field label={t("name")}><input value={f.name} onChange={set("name")} /></Field>
          <Field label={t("unNumber")}><input value={f.un_number} onChange={set("un_number")} /></Field>
          <Field label={t("cas")}><input value={f.cas} onChange={set("cas")} placeholder="67-64-1" /></Field>
          <Field label={t("mode")}><select value={f.mode} onChange={set("mode")}><option>IMDG</option><option>IATA</option></select></Field>
          <Field label="Concentration"><input value={f.concentration} onChange={set("concentration")} /></Field>
          <Field label="Physical state"><input value={f.physical_state} onChange={set("physical_state")} /></Field>
          <Field label="Quantity"><input value={f.quantity} onChange={set("quantity")} /></Field>
          <Field label="Packaging"><input value={f.packaging} onChange={set("packaging")} /></Field>
        </div>
        <Field label={t("text")}><textarea rows={3} value={f.text} onChange={set("text")} /></Field>
        {controls}
        <button disabled={busy} onClick={() => run({ name: f.name || null, un_number: f.un_number || null, cas: f.cas || null,
          text: f.text || null, mode: f.mode, context: { concentration: f.concentration, physical_state: f.physical_state, quantity: f.quantity, packaging: f.packaging } })}>
          {busy ? t("loading") : t("run")}</button>
        <ErrorBox error={error} />
      </Card>
      {r && (
        <Card title={<>Overall: <Badge s={r.overall.category} /></>}>
          <SavedNote id={r.report_id} />
          <p>{r.overall.category_description} {r.overall.message}</p>
          {r.unmatched_un_numbers?.length > 0 && <div className="alert warn">No loaded data for: {r.unmatched_un_numbers.join(", ")}</div>}
          {r.ghs_note && <div className="alert info">{r.ghs_note}</div>}
          {r.candidates.map((c: Json, i: number) => (
            <div key={i} className="candidate">
              <div className="row"><Badge s={c.category} /> <b>{c.entry.un_number}</b> {c.entry.proper_shipping_name}
                <span className="muted"> · class {c.entry.hazard_class}{c.entry.subsidiary_hazards.length ? ` (${c.entry.subsidiary_hazards.join(", ")})` : ""} · PG {c.entry.packing_groups.join("/") || "n/a"} · confidence: {c.confidence} · data rule set: {c.rule_set_of_data}{c.mode_specific ? "" : " (not mode-specific)"}</span></div>
              <Bullets title="Why" items={c.match_reasons} />
              <Bullets title="Labels & marks (derived)" items={[...c.entry.labelling.labels, ...c.entry.labelling.marks, c.entry.labelling.basis]} />
              <Bullets title={t("limitations")} items={c.limitations} />
            </div>
          ))}
          <Bullets title={t("missing")} items={r.missing_information} tone="warn" />
          <Bullets title={t("notes")} items={r.notes} />
        </Card>
      )}
    </div>
  );
}
