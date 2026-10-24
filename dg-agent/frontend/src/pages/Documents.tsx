import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Json } from "../api";
import { Badge, Bullets, Card, ErrorBox, Field, SavedNote, useRunner, Value } from "../components";
import { useI18n } from "../i18n";

export function SdsPage() {
  const { t } = useI18n();
  const nav = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [purpose, setPurpose] = useState("sds");
  const [res, setRes] = useState<Json>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function upload() {
    if (!file) return;
    setBusy(true); setError(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("purpose", purpose);
    try { setRes(await api.upload("/api/documents/upload", fd)); } catch (e) { setError(e); }
    setBusy(false);
  }
  const sds = res?.extraction?.sds;
  const f = sds?.fields;
  return (
    <div className="page">
      <Card title={t("sds")}>
        <p className="muted">Upload an SDS (PDF text or scanned), a label photo or a transport document. Text-layer extraction is used first, then OCR (English + Arabic). Uploaded content is treated as data only — never as instructions.</p>
        <div className="grid">
          <Field label="Document type"><select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            <option value="sds">Safety Data Sheet</option><option value="label">Label / placard photo</option><option value="document">DG declaration / manifest</option></select></Field>
          <Field label="File (PDF, PNG, JPEG, WEBP, TIFF, TXT)"><input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.txt" onChange={(e) => setFile(e.target.files?.[0] || null)} /></Field>
        </div>
        <button disabled={!file || busy} onClick={upload}>{busy ? t("loading") : t("upload")}</button>
        <ErrorBox error={error} />
      </Card>
      {res && (
        <Card title={`${res.name} — sha256 ${res.sha256.slice(0, 12)}…`}>
          <p className="small">Extraction method: <b>{res.extraction.method || "none"}</b> · characters: {res.extraction.characters} · OCR available: {String(res.extraction.ocr_available)}</p>
          {res.extraction.security_flags && <div className="alert bad">Text resembling instructions to an AI system was found and ignored: {res.extraction.security_flags.prompt_injection_like_text.join("; ")}</div>}
          <Bullets title="Extraction warnings" items={res.extraction.warnings} tone="warn" />
          {sds && (
            <>
              <div className="alert warn small">{sds.extraction_disclaimer}</div>
              <Value v={{ product_name: f.product_name, manufacturer: f.manufacturer, un_numbers: f.un_numbers,
                proper_shipping_name: f.proper_shipping_name, hazard_class: f.hazard_class, subsidiary_hazards: f.subsidiary_hazards,
                packing_group: f.packing_group, marine_pollutant: f.marine_pollutant, flash_point: f.flash_point,
                cas_numbers: f.cas_numbers.map((c: Json) => `${c.cas}${c.checksum_valid ? "" : " (INVALID check digit)"}`),
                ghs_h_statements: f.h_statements, states_not_regulated: f.states_not_regulated, revision_date: f.revision_date,
                sections_found: sds.sections_found, contains_arabic: sds.contains_arabic }} />
              <Bullets title="Findings" items={sds.findings.map((x: Json) => `${x.severity.toUpperCase()}: ${x.finding}`)} tone="bad" />
              {f.un_numbers.length > 0 && (
                <div className="row">{f.un_numbers.map((u: string) => (
                  <button key={u} className="ghost" onClick={() => nav("/verify", { state: { prefill: { un_number: u,
                    proper_shipping_name: f.proper_shipping_name || "", hazard_class: f.hazard_class || "",
                    subsidiary: (f.subsidiary_hazards || []).join(", "), packing_group: f.packing_group || "" } } })}>
                    Verify {u} with extracted values →</button>
                ))}</div>
              )}
            </>
          )}
          {res.extraction.un_numbers && <Bullets title="UN numbers detected" items={res.extraction.un_numbers.map((u: Json) => `${u.un} ${u.notes.join(" ")}`)} />}
          <details><summary>Extracted text preview</summary><pre className="pre">{res.extraction.text_preview}</pre></details>
        </Card>
      )}
    </div>
  );
}

export function InspectionPage() {
  const { t } = useI18n();
  const [list, setList] = useState<Json[]>([]);
  const [header, setHeader] = useState({ container_no: "", seal_no: "", location: "", inspector: "", date: new Date().toISOString().slice(0, 10) });
  const [items, setItems] = useState<Record<string, Json>>({});
  const [photos, setPhotos] = useState<Json[]>([]);
  const { result: r, error, busy, run, controls } = useRunner("/api/inspection/evaluate");
  useEffect(() => { api.get("/api/inspection/checklist").then(setList).catch(() => {}); }, []);
  const upd = (k: string, patch: Json) => setItems({ ...items, [k]: { key: k, result: "not_checked", ...items[k], ...patch } });
  async function addPhoto(fl: FileList | null) {
    for (const file of Array.from(fl || [])) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("purpose", "photo");
      try { const p = await api.upload("/api/documents/upload", fd); setPhotos((ps) => [...ps, p]); } catch (e) { alert(String(e)); }
    }
  }
  return (
    <div className="page">
      <Card title={t("inspection")}>
        <div className="grid">{Object.entries(header).map(([k, v]) => (
          <Field key={k} label={k.replace(/_/g, " ")}><input value={v} onChange={(e) => setHeader({ ...header, [k]: e.target.value })} /></Field>
        ))}</div>
        <div className="scroll"><table className="table edit">
          <thead><tr><th>Check</th><th>Result</th><th>Evidence</th><th>Comment</th><th>Corrective action</th><th>Responsible</th><th>Photos</th></tr></thead>
          <tbody>{list.map((c) => {
            const it = items[c.key] || {};
            return (
              <tr key={c.key}>
                <td>{c.label}<div className="small muted">{c.category}</div></td>
                <td><select value={it.result || "not_checked"} onChange={(e) => upd(c.key, { result: e.target.value })}>
                  <option value="not_checked">not checked</option><option value="ok">OK</option><option value="observation">observation</option>
                  <option value="nonconformity">non-conformity</option><option value="na">n/a</option></select></td>
                <td><select value={it.evidence_type || "visual_observation"} onChange={(e) => upd(c.key, { evidence_type: e.target.value })}>
                  <option value="visual_observation">visual / photo</option><option value="document_verified">document verified</option>
                  <option value="measurement">measurement</option></select></td>
                <td><input value={it.comment || ""} onChange={(e) => upd(c.key, { comment: e.target.value })} /></td>
                <td><input value={it.corrective_action || ""} onChange={(e) => upd(c.key, { corrective_action: e.target.value })} /></td>
                <td><input value={it.responsible || ""} onChange={(e) => upd(c.key, { responsible: e.target.value })} /></td>
                <td><select multiple value={(it.photo_ids || []).map(String)} onChange={(e) => upd(c.key, { photo_ids: Array.from(e.target.selectedOptions).map((o) => Number(o.value)) })}>
                  {photos.map((p) => <option key={p.id} value={p.id}>#{p.id} {p.name}</option>)}</select></td>
              </tr>
            );
          })}</tbody></table></div>
        <Field label="Attach photos (supporting evidence only)"><input type="file" multiple accept="image/*" onChange={(e) => addPhoto(e.target.files)} /></Field>
        {photos.length > 0 && <p className="small">Uploaded: {photos.map((p) => `#${p.id} ${p.name}`).join(", ")}</p>}
        {controls}
        <button disabled={busy} onClick={() => run({ header, items: list.map((c) => items[c.key] || { key: c.key, result: "not_checked" }) })}>{busy ? t("loading") : t("run")}</button>
        <ErrorBox error={error} />
      </Card>
      {r && (
        <Card title={<>Overall: <Badge s={r.overall} /></>}>
          <SavedNote id={r.report_id} />
          <table className="table"><thead><tr><th>Check</th><th>Classification</th><th>Evidence</th><th>Risk</th><th>Comment</th></tr></thead>
            <tbody>{r.rows.map((x: Json) => (
              <tr key={x.key}><td>{x.label}</td><td><Badge s={x.classification} /></td><td>{x.evidence_type}</td>
                <td>{x.risk ? <span className="badge" style={{ background: x.risk.color, color: "#fff" }}>{x.risk.band} ({x.risk.score})</span> : "—"}</td><td>{x.comment}</td></tr>
            ))}</tbody></table>
          <Bullets title={t("corrective")} items={r.corrective_actions.map((a: Json) => `${a.description} — ${a.responsible}${a.due_date ? ` (due ${a.due_date})` : ""}`)} tone="warn" />
          <Bullets title="Not covered" items={r.not_covered} />
          <Bullets title={t("limitations")} items={r.limitations} />
        </Card>
      )}
    </div>
  );
}
