import { useState } from "react";
import type { Json } from "../api";
import { Badge, Bullets, Card, ErrorBox, Evidence, Field, SavedNote, splitList, useRunner } from "../components";
import { useI18n } from "../i18n";

type Item = { id: string; name: string; un_number: string; hazard_class: string; subsidiary: string; packing_group: string;
              quantity: string; package: string; location: string; segregation_groups: string };
const blank = (n: number): Item => ({ id: `item${n}`, name: "", un_number: "", hazard_class: "", subsidiary: "", packing_group: "",
                                      quantity: "", package: "", location: "", segregation_groups: "" });
const COLS: [keyof Item, string][] = [["id", "ID"], ["name", "Name"], ["un_number", "UN no."], ["hazard_class", "Class"],
  ["subsidiary", "Subsidiary"], ["packing_group", "PG"], ["quantity", "Quantity"], ["package", "Package"],
  ["location", "Location"], ["segregation_groups", "Seg. groups"]];

function toPayload(items: Item[]) {
  return items.map((i) => ({ id: i.id, name: i.name || undefined, un_number: i.un_number || undefined,
    hazard_class: i.hazard_class || undefined, subsidiary_hazards: splitList(i.subsidiary), packing_group: i.packing_group || undefined,
    quantity: i.quantity || undefined, package: i.package || undefined, location: i.location || undefined,
    segregation_groups: splitList(i.segregation_groups) }));
}

function ItemsEditor({ items, setItems }: { items: Item[]; setItems: (i: Item[]) => void }) {
  const { t } = useI18n();
  return (
    <div className="scroll">
      <table className="table edit">
        <thead><tr>{COLS.map(([, l]) => <th key={l}>{l}</th>)}<th /></tr></thead>
        <tbody>{items.map((it, i) => (
          <tr key={i}>{COLS.map(([k]) => (
            <td key={k}><input value={it[k]} onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))} /></td>
          ))}<td><button className="ghost" onClick={() => setItems(items.filter((_, j) => j !== i))}>×</button></td></tr>
        ))}</tbody>
      </table>
      <button className="ghost" onClick={() => setItems([...items, blank(items.length + 1)])}>+ {t("add")}</button>
    </div>
  );
}

const CELL: Record<string, string> = { conflict: "bad", requirement: "warn", hold: "neutral", no_general_requirement: "info",
  no_pair_in_loaded_subset: "neutral" };

export function SegregationPage() {
  const { t } = useI18n();
  const [mode, setMode] = useState("IMDG");
  const [arr, setArr] = useState("same_ctu");
  const [items, setItems] = useState<Item[]>([
    { ...blank(1), name: "Petrol", un_number: "UN1203", quantity: "4 x 200 L", package: "steel drums" },
    { ...blank(2), name: "Hydrogen peroxide 35%", un_number: "UN2014", quantity: "10 x 25 L", package: "plastic jerricans" },
    { ...blank(3), name: "Caustic soda", un_number: "UN1823", quantity: "20 x 25 kg", package: "bags" },
  ]);
  const { result: r, error, busy, run, controls } = useRunner("/api/segregation/check");
  const ids: string[] = r?.items?.map((i: Json) => i.id) || [];
  return (
    <div className="page">
      <Card title={t("segregation")}>
        <p className="muted">Deterministic rule engine. Every pair is evaluated using primary and subsidiary hazards (most stringent applies). The engine never approves a stowage plan.</p>
        <div className="grid">
          <Field label={t("mode")}><select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="IMDG">IMDG (sea)</option><option value="IATA">IATA DGR (air)</option><option value="WAREHOUSE">Warehouse storage</option></select></Field>
          <Field label="Arrangement"><select value={arr} onChange={(e) => setArr(e.target.value)}>
            <option value="same_ctu">Same CTU (container/vehicle)</option><option value="same_hold">Same hold, separate CTUs</option>
            <option value="separate_ctus">Separate CTUs (positions unknown)</option><option value="same_uld">Same ULD / aircraft hold</option>
            <option value="same_storage_area">Same storage area</option><option value="adjacent_storage">Adjacent storage</option></select></Field>
        </div>
        <ItemsEditor items={items} setItems={setItems} />
        {controls}
        <button disabled={busy || items.length < 2} onClick={() => run({ mode, arrangement: arr, items: toPayload(items) })}>{busy ? t("loading") : t("run")}</button>
        <ErrorBox error={error} />
      </Card>
      {r && (
        <Card title={<>Decision: <Badge s={r.decision} /></>}>
          <SavedNote id={r.report_id} />
          {r.rule_table && <p className="small">Rule table: <code>{r.rule_table.code}</code> {r.rule_table.name} — verification {r.rule_table.verification_status}, authoritative: <b>{r.rule_table.authoritative ? "yes" : "NO"}</b></p>}
          {r.matrix && ids.length > 0 && (
            <div className="scroll">
              <h4>Segregation matrix / compatibility map</h4>
              <table className="matrix"><thead><tr><th />{ids.map((i) => <th key={i}>{i}</th>)}</tr></thead>
                <tbody>{ids.map((a) => (
                  <tr key={a}><th>{a}</th>{ids.map((b) => {
                    const c = r.matrix[a]?.[b];
                    return <td key={b} className={a === b ? "diag" : `cell ${CELL[c?.status] || ""}`}>{a === b ? "" : c ? `${c.code ?? "?"}` : ""}<div className="small">{a === b ? "" : c?.status?.replace(/_/g, " ")}</div></td>;
                  })}</tr>
                ))}</tbody></table>
              <p className="small legend"><span className="cell bad">conflict</span> <span className="cell warn">requirement to verify</span> <span className="cell neutral">hold / manual</span> <span className="cell info">no general table requirement (not a clearance)</span></p>
            </div>
          )}
          {r.pairs?.map((p: Json, i: number) => (
            <div key={i} className="candidate">
              <div className="row"><b>{p.a} ↔ {p.b}</b> <Badge s={(p.status || p.result || "").toUpperCase().replace(/_/g, " ")} /> {p.label || ""}{p.governing_combination ? ` (governing: ${p.governing_combination.join(" vs ")})` : ""}</div>
              <Bullets title="Findings" items={p.issues || p.flags?.map((f: Json) => `${f.severity}: ${f.reason}`)} tone="bad" />
              <Bullets title="Conditions / manual checks" items={p.conditions} />
            </div>
          ))}
          <Bullets title="Alternative arrangement (for qualified review)" items={r.alternative_arrangement} tone="info" />
          <Bullets title="Manual checks" items={r.manual_checks} />
          <Bullets title={t("missing")} items={r.missing_information} tone="warn" />
          <Bullets title={t("notes")} items={r.notes} />
          <Bullets title="Assumptions" items={r.assumptions} />
          <Bullets title={t("limitations")} items={r.limitations} />
          {r.screening && <Bullets title="Screening limitations" items={r.screening.limitations} />}
          {r.rule_table?.source && <Evidence items={[r.rule_table.source]} />}
        </Card>
      )}
    </div>
  );
}

export function CompatPage() {
  const { t } = useI18n();
  const [items, setItems] = useState<Item[]>([
    { ...blank(1), name: "Sodium hypochlorite solution", un_number: "UN1791" },
    { ...blank(2), name: "Hydrochloric acid", un_number: "UN1789" },
  ]);
  const { result: r, error, busy, run, controls } = useRunner("/api/compatibility/screen");
  return (
    <div className="page">
      <Card title={t("compat")}>
        <div className="alert warn">Screening only — general reactive-chemistry rules. Not a regulatory segregation rule set and never a basis for approval. Check SDS Sections 7 & 10, local fire code and the site risk assessment.</div>
        <ItemsEditor items={items} setItems={setItems} />
        {controls}
        <button disabled={busy || items.length < 2} onClick={() => run({ items: toPayload(items) })}>{busy ? t("loading") : t("run")}</button>
        <ErrorBox error={error} />
      </Card>
      {r && (
        <Card title={<>Result: <Badge s={r.decision} /></>}>
          <SavedNote id={r.report_id} />
          <table className="table"><thead><tr><th>Item</th><th>Reactive groups</th><th>Data origin</th></tr></thead>
            <tbody>{r.items.map((i: Json) => <tr key={i.id}><td>{i.id} {i.name}</td><td>{i.groups.join(", ") || "— no data —"}</td><td className="small">{i.data_origin}</td></tr>)}</tbody></table>
          {r.pairs.map((p: Json, i: number) => (
            <div key={i} className="candidate"><b>{p.a} ↔ {p.b}</b> <Badge s={p.result} />
              <Bullets title="Flags" items={p.flags.map((f: Json) => `${f.severity.toUpperCase()}: ${f.reason}`)} tone="bad" /></div>
          ))}
          <Bullets title={t("notes")} items={r.notes} />
          <Bullets title={t("limitations")} items={r.limitations} />
        </Card>
      )}
    </div>
  );
}
