import { useState, type ReactNode } from "react";
import { api, type Json } from "./api";
import { useI18n } from "./i18n";

export function statusTone(s?: string): string {
  const v = (s || "").toUpperCase();
  if (/CONFLICT|DISCREPANCY|STOP|MAJOR|INCOMPATIBLE|REJECTED|VERIFIED NON-COMPLIANCE|EXTREME|HIGH/.test(v)) return "bad";
  if (/HOLD|NOT VERIFIED|INSUFFICIENT|REQUIRED|SUSPECTED|CAUTION|INCOMPLETE|PENDING|UNKNOWN|CANDIDATE|MEDIUM|DRAFT/.test(v)) return "warn";
  if (/WITH CONDITIONS|NO SCREENING FLAG|NO CONFLICT|NO DEFECTS|NO GENERAL/.test(v)) return "info";
  if (/^VERIFIED AGAINST SOURCE|APPROVED|CONFIRMED|LOW|SITE EMERGENCY/.test(v)) return "good";
  return "neutral";
}

export const Badge = ({ s }: { s?: string }) => <span className={`badge ${statusTone(s)}`}>{s || "—"}</span>;

export function Card({ title, children, actions }: { title?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && <div className="card-head"><h3>{title}</h3><div>{actions}</div></div>}
      {children}
    </section>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="field"><span>{label}</span>{children}</label>;
}

export function Bullets({ title, items, tone }: { title: string; items?: Json[]; tone?: string }) {
  if (!items || !items.length) return null;
  return (
    <div className={`bullets ${tone || ""}`}>
      <h4>{title}</h4>
      <ul>{items.map((i, n) => <li key={n}>{typeof i === "string" ? i : <Value v={i} />}</li>)}</ul>
    </div>
  );
}

export function Value({ v }: { v: Json }): JSX.Element {
  if (v === null || v === undefined || v === "") return <span className="muted">—</span>;
  if (Array.isArray(v)) {
    if (v.every((x) => typeof x !== "object" || x === null)) return <span>{v.join(", ") || "—"}</span>;
    return <div>{v.map((x, i) => <div key={i} className="nested"><Value v={x} /></div>)}</div>;
  }
  if (typeof v === "object") {
    return (
      <table className="kv"><tbody>
        {Object.entries(v).map(([k, val]) => (
          <tr key={k}><th>{k.replace(/_/g, " ")}</th><td><Value v={val} /></td></tr>
        ))}
      </tbody></table>
    );
  }
  if (typeof v === "boolean") return <span>{v ? "yes" : "no"}</span>;
  return <span>{String(v)}</span>;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <div className="alert bad">{error instanceof Error ? error.message : String(error)}</div>;
}

export function Evidence({ items }: { items?: Json[] }) {
  const { t } = useI18n();
  if (!items || !items.length) return null;
  return (
    <details className="evidence"><summary>{t("evidence")} ({items.length})</summary>
      {items.map((e, i) => (
        <div key={i} className="ev">
          <b>{e.title}</b> — {e.edition} {e.amendment} <code>{e.source_code}</code>
          <div className="small">rule set: {e.rule_set} · section: {e.section_ref || "—"} · source verification:{" "}
            <Badge s={e.source_verification_status} /> · edition status: {e.source_status} · entry:{" "}
            {e.entry_verification_status || "—"} · authoritative: <b>{e.authoritative ? "yes" : "NO"}</b> · retrieved {e.retrieved_at}</div>
          {e.limitations?.length ? <ul className="small">{e.limitations.map((l: string, j: number) => <li key={j}>{l}</li>)}</ul> : null}
        </div>
      ))}
    </details>
  );
}

/** Save-as-report controls + submit wrapper shared by every analysis page. */
export function useRunner<T = Json>(path: string) {
  const [result, setResult] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [save, setSave] = useState(false);
  const [title, setTitle] = useState("");
  async function run(body: Json) {
    setBusy(true); setError(null);
    try { setResult(await api.post(path, { ...body, save, title: title || undefined })); }
    catch (e) { setError(e); setResult(null); }
    finally { setBusy(false); }
  }
  const { t } = useI18n();
  const controls = (
    <div className="row save-row">
      <label className="check"><input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} /> {t("save")}</label>
      {save && <input placeholder={t("title")} value={title} onChange={(e) => setTitle(e.target.value)} />}
    </div>
  );
  return { result, setResult, error, busy, run, controls };
}

export function SavedNote({ id }: { id?: number }) {
  if (!id) return null;
  return <div className="alert info">Saved as report #{id}. Submit it for qualified review in Reports & Audit Trail.</div>;
}

export function AiExplain({ result }: { result: Json }) {
  const { t } = useI18n();
  const [out, setOut] = useState<Json>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="ai">
      <button className="ghost" disabled={busy} onClick={async () => {
        setBusy(true);
        try { setOut(await api.post("/api/ai/explain", { result })); } catch (e) { setOut({ message: String(e) }); }
        setBusy(false);
      }}>{t("aiExplain")}</button>
      {out && (
        <div className={`alert ${out.available ? "info" : "warn"}`}>
          <b>{out.label || "AI INTERPRETATION"}</b>
          {out.text ? <p style={{ whiteSpace: "pre-wrap" }}>{out.text}</p> : <p>{out.message}</p>}
          {out.unsupported_references && <p className="small">Unsupported: {out.unsupported_references.join("; ")}</p>}
        </div>
      )}
    </div>
  );
}

export const splitList = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
