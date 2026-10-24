import { useEffect, useState } from "react";
import { api, type Json } from "../api";
import { Badge, Bullets, Card, ErrorBox, Field, Value } from "../components";
import { useI18n } from "../i18n";
import { useUser } from "../user";

export function ReportsPage() {
  const { t } = useI18n();
  const user = useUser();
  const [list, setList] = useState<Json[]>([]);
  const [sel, setSel] = useState<Json>(null);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [auditRows, setAudit] = useState<Json[]>([]);
  const [chain, setChain] = useState<Json>(null);
  const [capa, setCapa] = useState<Json[]>([]);
  const [capaNew, setCapaNew] = useState({ description: "", responsible: "", due_date: "", action_type: "corrective" });
  const can = (p: string) => user?.permissions.includes(p);
  const load = () => {
    api.get("/api/reports").then(setList).catch(setError);
    api.get("/api/capa").then(setCapa).catch(() => {});
    if (user?.permissions.includes("view_audit")) api.get("/api/audit?limit=100").then(setAudit).catch(() => {});
  };
  useEffect(load, []);
  async function act(action: string) {
    setError(null);
    try { await api.post(`/api/reports/${sel.id}/${action}`, { comment }); setComment(""); setSel(await api.get(`/api/reports/${sel.id}`)); load(); }
    catch (e) { setError(e); }
  }
  return (
    <div className="page">
      <Card title={t("reports")} actions={<button className="ghost" onClick={load}>↻</button>}>
        <div className="scroll"><table className="table">
          <thead><tr><th>#</th><th>Type</th><th>Title</th><th>Review status</th><th>Created</th></tr></thead>
          <tbody>{list.map((r) => (
            <tr key={r.id} className="clickable" onClick={async () => setSel(await api.get(`/api/reports/${r.id}`))}>
              <td>{r.id}</td><td>{r.kind}</td><td>{r.title}</td><td><Badge s={r.status.toUpperCase().replace("_", " ")} /></td><td className="small">{r.created_at?.slice(0, 16)}</td></tr>
          ))}</tbody></table></div>
      </Card>
      {sel && (
        <Card title={<>#{sel.id} {sel.title} <Badge s={sel.status.toUpperCase().replace("_", " ")} /></>}>
          <p className="small">Criticality: {sel.criticality} — approval requires a different, authorised DGSA approver. Approval records a qualified person's decision; it is not a system certification.</p>
          <div className="row">
            {["pdf", "docx", "xlsx", "csv"].map((f) => <button key={f} className="ghost" onClick={() => api.download(`/api/reports/${sel.id}/export/${f}`, `dg-report-${sel.id}.${f}`)}>{t("export")} {f.toUpperCase()}</button>)}
          </div>
          <div className="row">
            <input placeholder={t("comment")} value={comment} onChange={(e) => setComment(e.target.value)} style={{ flex: 1 }} />
            {can("submit_review") && ["draft", "rejected"].includes(sel.status) && <button onClick={() => act("submit")}>{t("submit")}</button>}
            {can("review") && sel.status === "pending_review" && <button className="ghost" onClick={() => act("review")}>{t("review")}</button>}
            {sel.status === "pending_review" && <button onClick={() => act("approve")} title={can("approve") ? "" : "Your role cannot approve"}>{t("approve")}</button>}
            {can("review") && sel.status === "pending_review" && <button className="danger" onClick={() => act("reject")}>{t("reject")}</button>}
          </div>
          <ErrorBox error={error} />
          <Bullets title="Approval history" items={sel.approvals.map((a: Json) => `${a.created_at.slice(0, 16)} — ${a.decision.toUpperCase()} by user #${a.user_id} ${a.qualification ? `(${a.qualification})` : ""}: ${a.comment}`)} />
          <details><summary>Content</summary><Value v={sel.content} /></details>
          <details><summary>Inputs</summary><Value v={sel.inputs} /></details>
        </Card>
      )}
      <Card title="Corrective & preventive action register (CAPA)">
        <div className="grid">
          <Field label="Description"><input value={capaNew.description} onChange={(e) => setCapaNew({ ...capaNew, description: e.target.value })} /></Field>
          <Field label="Type"><select value={capaNew.action_type} onChange={(e) => setCapaNew({ ...capaNew, action_type: e.target.value })}><option>corrective</option><option>preventive</option></select></Field>
          <Field label="Responsible"><input value={capaNew.responsible} onChange={(e) => setCapaNew({ ...capaNew, responsible: e.target.value })} /></Field>
          <Field label="Due date"><input type="date" value={capaNew.due_date} onChange={(e) => setCapaNew({ ...capaNew, due_date: e.target.value })} /></Field>
        </div>
        <button disabled={!capaNew.description} onClick={async () => { try { await api.post("/api/capa", { ...capaNew, due_date: capaNew.due_date || null, report_id: sel?.id ?? null }); setCapaNew({ ...capaNew, description: "" }); load(); } catch (e) { setError(e); } }}>{t("add")}</button>
        <div className="scroll"><table className="table"><thead><tr><th>#</th><th>Report</th><th>Description</th><th>Responsible</th><th>Due</th><th>Status</th><th /></tr></thead>
          <tbody>{capa.map((c) => (
            <tr key={c.id}><td>{c.id}</td><td>{c.report_id ?? "—"}</td><td>{c.description}</td><td>{c.responsible}</td><td>{c.due_date ?? "—"}</td><td><Badge s={c.status.toUpperCase()} /></td>
              <td>{c.status !== "closed" && <button className="ghost" onClick={async () => {
                const note = prompt("Closure evidence / note"); if (!note) return;
                try { await api.patch(`/api/capa/${c.id}`, { status: "closed", closure_note: note }); load(); } catch (e) { setError(e); }
              }}>Close</button>}</td></tr>))}</tbody></table></div>
      </Card>
      {can("view_audit") && <Card title="Audit trail (tamper-evident, append-only)" actions={<button className="ghost" onClick={async () => setChain(await api.get("/api/audit/verify"))}>Verify hash chain</button>}>
        {chain && <div className={`alert ${chain.valid ? "info" : "bad"}`}>{chain.valid ? `Chain valid — ${chain.checked} records verified.` : `CHAIN BROKEN at record ${chain.broken_at_id}`}</div>}
        <div className="scroll"><table className="table small"><thead><tr><th>#</th><th>Time</th><th>User</th><th>Action</th><th>Entity</th><th>Hash</th></tr></thead>
          <tbody>{auditRows.map((a) => <tr key={a.id}><td>{a.id}</td><td>{a.ts.slice(0, 19)}</td><td>{a.user_email || "system"}</td><td>{a.action}</td><td>{a.entity} {a.entity_id}</td><td><code>{a.hash}</code></td></tr>)}</tbody></table></div>
      </Card>}
    </div>
  );
}

export function SourcesPage() {
  const { t } = useI18n();
  const user = useUser();
  const [sources, setSources] = useState<Json[]>([]);
  const [tables, setTables] = useState<Json[]>([]);
  const [q, setQ] = useState("");
  const [entries, setEntries] = useState<Json[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [msg, setMsg] = useState<string>("");
  const [newSrc, setNewSrc] = useState({ code: "", rule_set: "IMDG", publisher: "", title: "", edition: "", amendment: "", effective_date: "", licence: "", location: "" });
  const can = (p: string) => user?.permissions.includes(p);
  const load = () => { api.get("/api/sources").then(setSources).catch(setError); api.get("/api/sources/rule-tables").then(setTables).catch(() => {}); };
  useEffect(load, []);
  const search = async () => setEntries(await api.get(`/api/sources/entries?q=${encodeURIComponent(q)}`));
  return (
    <div className="page">
      <Card title={t("sources")}>
        <p className="muted">Version-controlled regulatory data. An engine conclusion is authoritative only when the source AND entry are verified and the edition is in force. Licensed IMDG/IATA content must be ingested from lawfully obtained copies or authorised data services.</p>
        <div className="scroll"><table className="table small">
          <thead><tr><th>Code</th><th>Rule set</th><th>Title / edition</th><th>Effective</th><th>Edition status</th><th>Verification</th><th>Content</th><th>Entries</th><th>Licence</th><th /></tr></thead>
          <tbody>{sources.map((s) => (
            <tr key={s.id}><td><code>{s.code}</code></td><td>{s.rule_set}</td><td>{s.title}<div className="muted">{s.edition} {s.amendment}</div></td>
              <td>{s.effective_date || "—"}{s.expiry_date ? ` → ${s.expiry_date}` : ""}</td><td><Badge s={s.effective_status.toUpperCase()} /></td>
              <td><Badge s={s.verification_status.toUpperCase()} /></td><td>{s.content_loaded ? "loaded" : "not loaded"}</td><td>{s.entry_count}</td>
              <td className="small">{s.licence}</td>
              <td>{can("manage_sources") && <label className="ghost small">Import CSV/JSON<input type="file" hidden accept=".csv,.json" onChange={async (e) => {
                const f = e.target.files?.[0]; if (!f) return; const fd = new FormData(); fd.append("file", f);
                try { const r = await api.upload(`/api/sources/${s.id}/import`, fd); setMsg(`Imported ${r.imported} entries (UNVERIFIED). ${r.next_step}`); load(); } catch (er) { setError(er); }
              }} /></label>}</td></tr>))}</tbody></table></div>
        {msg && <div className="alert info">{msg}</div>}
        <ErrorBox error={error} />
        {can("manage_sources") && (
          <details><summary>Register a new source / edition</summary>
            <div className="grid">{Object.keys(newSrc).map((k) => (
              <Field key={k} label={k.replace(/_/g, " ")}>{k === "rule_set" ? <select value={newSrc.rule_set} onChange={(e) => setNewSrc({ ...newSrc, rule_set: e.target.value })}><option>IMDG</option><option>IATA</option><option>UN_MODEL</option><option>SITE</option></select>
                : <input type={k === "effective_date" ? "date" : "text"} value={(newSrc as Json)[k]} onChange={(e) => setNewSrc({ ...newSrc, [k]: e.target.value })} />}</Field>))}</div>
            <button onClick={async () => { try { await api.post("/api/sources", { ...newSrc, effective_date: newSrc.effective_date || null }); load(); } catch (e) { setError(e); } }}>{t("add")}</button>
            <p className="small muted">CSV columns: un_number, variant, proper_shipping_name, hazard_class, subsidiary_hazards (| separated), packing_groups (|), special_provisions (| ; blank = not loaded, '-' = none), marine_pollutant (P or -), section_ref, synonyms (|), cas_numbers (|), mode_data (JSON).</p>
          </details>
        )}
      </Card>
      <Card title="Rule tables">
        {tables.map((tb) => (
          <details key={tb.id}><summary><code>{tb.code}</code> {tb.name} — <Badge s={tb.verification_status.toUpperCase()} /> {tb.complete ? "" : "(partial)"} · authoritative: {tb.authoritative ? "yes" : "NO"}</summary>
            <Bullets title={t("limitations")} items={tb.limitations} />
            {tb.data.matrix && (<div className="scroll"><table className="matrix small"><thead><tr><th />{tb.data.classes.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{tb.data.matrix.map((row: string[], i: number) => <tr key={i}><th>{tb.data.classes[i]}</th>{row.map((c, j) => <td key={j} className={`cell ${c === "X" ? "info" : c === "*" ? "neutral" : Number(c) >= 3 ? "bad" : "warn"}`}>{c}</td>)}</tr>)}</tbody></table>
              <Value v={tb.data.codes} /></div>)}
            {tb.data.pairs && <Value v={tb.data} />}
          </details>))}
      </Card>
      <Card title="Dangerous goods entries">
        <div className="row"><input placeholder="UN number or name" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} /><button onClick={search}>Search</button></div>
        <div className="scroll"><table className="table small"><thead><tr><th>UN</th><th>PSN</th><th>Class</th><th>Sub</th><th>PG</th><th>SP</th><th>Source</th><th>Entry status</th><th /></tr></thead>
          <tbody>{entries.map((e) => (
            <tr key={e.id}><td>{e.un_number}</td><td>{e.proper_shipping_name}</td><td>{e.hazard_class}</td><td>{e.subsidiary_hazards.join(", ")}</td><td>{e.packing_groups.join("/") || "—"}</td>
              <td>{e.special_provisions_loaded ? e.special_provisions.join(", ") || "none" : "not loaded"}</td><td><code>{e.evidence.source_code}</code></td><td><Badge s={e.evidence.entry_verification_status.toUpperCase()} /></td>
              <td>{can("verify_regulatory_data") && e.evidence.entry_verification_status !== "verified" && <button className="ghost" onClick={async () => {
                const ref = prompt("Verification reference — what exact source text (edition, volume, DGL row) did you check?"); if (!ref) return;
                try { await api.post(`/api/sources/entries/${e.id}/verify`, { verification_ref: ref }); search(); } catch (er) { setError(er); }
              }}>Verify</button>}</td></tr>))}</tbody></table></div>
      </Card>
    </div>
  );
}

export function UsersPage() {
  const { t } = useI18n();
  const [users, setUsers] = useState<Json[]>([]);
  const [roles, setRoles] = useState<Record<string, string[]>>({});
  const [n, setN] = useState({ email: "", full_name: "", role: "operator", qualification: "", password: "" });
  const [error, setError] = useState<unknown>(null);
  const load = () => { api.get("/api/users").then(setUsers).catch(setError); api.get("/api/roles").then(setRoles).catch(() => {}); };
  useEffect(load, []);
  return (
    <div className="page">
      <Card title={t("users")}>
        <ErrorBox error={error} />
        <div className="scroll"><table className="table"><thead><tr><th>Email</th><th>Name</th><th>Role</th><th>Qualification</th><th>Active</th></tr></thead>
          <tbody>{users.map((u) => (
            <tr key={u.id}><td>{u.email}</td><td>{u.full_name}</td>
              <td><select value={u.role} onChange={async (e) => { try { await api.patch(`/api/users/${u.id}`, { role: e.target.value }); load(); } catch (er) { setError(er); } }}>
                {Object.keys(roles).map((r) => <option key={r}>{r}</option>)}</select></td>
              <td>{u.qualification}</td>
              <td><input type="checkbox" checked={u.is_active} onChange={async (e) => { try { await api.patch(`/api/users/${u.id}`, { is_active: e.target.checked }); load(); } catch (er) { setError(er); } }} /></td></tr>))}</tbody></table></div>
        <h4>Add user</h4>
        <div className="grid">{Object.keys(n).map((k) => (
          <Field key={k} label={k.replace(/_/g, " ")}>{k === "role" ? <select value={n.role} onChange={(e) => setN({ ...n, role: e.target.value })}>{Object.keys(roles).map((r) => <option key={r}>{r}</option>)}</select>
            : <input type={k === "password" ? "password" : "text"} value={(n as Json)[k]} onChange={(e) => setN({ ...n, [k]: e.target.value })} />}</Field>))}</div>
        <button onClick={async () => { try { await api.post("/api/users", n); setN({ ...n, email: "", password: "" }); load(); } catch (e) { setError(e); } }}>{t("add")}</button>
      </Card>
      <Card title="Role permissions (segregation of duties)">
        <Value v={Object.fromEntries(Object.entries(roles).map(([r, p]) => [r, p.join(", ")]))} />
        <p className="small muted">Administrators manage users and data imports but cannot approve DG decisions or verify regulatory data. Approvers cannot approve their own reports.</p>
      </Card>
    </div>
  );
}
