import { useEffect, useState } from "react";
import { HashRouter, Link, NavLink, Route, Routes } from "react-router-dom";
import { api, auth, type Json } from "./api";
import { Badge, Card, ErrorBox, Field } from "./components";
import { useI18n, type Key } from "./i18n";
import { ReportsPage, SourcesPage, UsersPage } from "./pages/Admin";
import { InspectionPage, SdsPage } from "./pages/Documents";
import { ErpPage, RiskPage, SpillPage } from "./pages/Emergency";
import { CompatPage, SegregationPage } from "./pages/Segregation";
import { IdentifyPage, VerifyPage } from "./pages/Verify";
import { UserCtx, type User } from "./user";

const NAV: { path: string; key: Key; icon: string; perm?: string }[] = [
  { path: "/", key: "dashboard", icon: "▦" },
  { path: "/identify", key: "identify", icon: "⌕" },
  { path: "/verify", key: "verify", icon: "✓" },
  { path: "/imdg", key: "imdg", icon: "⚓" },
  { path: "/iata", key: "iata", icon: "✈" },
  { path: "/segregation", key: "segregation", icon: "▤" },
  { path: "/compat", key: "compat", icon: "⚗" },
  { path: "/sds", key: "sds", icon: "▣" },
  { path: "/spill", key: "spill", icon: "⚠" },
  { path: "/erp", key: "erp", icon: "☰" },
  { path: "/inspection", key: "inspection", icon: "◫" },
  { path: "/risk", key: "risk", icon: "◬" },
  { path: "/reports", key: "reports", icon: "⎘" },
  { path: "/sources", key: "sources", icon: "§" },
  { path: "/users", key: "users", icon: "☺", perm: "manage_users" },
];

function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const { t, toggle } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  return (
    <div className="login">
      <Card title={t("app")} actions={<button className="ghost" onClick={toggle}>{t("language")}</button>}>
        <p className="muted">{t("tagline")}</p>
        <form onSubmit={async (e) => {
          e.preventDefault();
          try { const r = await api.post("/api/auth/login", { email, password }); auth.set(r.access_token); onLogin(r.user); }
          catch (er) { setError(er); }
        }}>
          <Field label={t("email")}><input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></Field>
          <Field label={t("password")}><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></Field>
          <button type="submit">{t("login")}</button>
        </form>
        <ErrorBox error={error} />
      </Card>
    </div>
  );
}

function Dashboard() {
  const { t } = useI18n();
  const [health, setHealth] = useState<Json>(null);
  const [cov, setCov] = useState<Json>(null);
  const [reports, setReports] = useState<Json[]>([]);
  useEffect(() => {
    api.get("/api/health").then(setHealth).catch(() => {});
    api.get("/api/sources/coverage").then(setCov).catch(() => {});
    api.get("/api/reports").then(setReports).catch(() => {});
  }, []);
  const pending = reports.filter((r) => r.status === "pending_review").length;
  return (
    <div className="page">
      <div className="tiles">
        {cov && Object.values(cov).map((c: Json) => (
          <div key={c.mode} className="tile">
            <div className="tile-label">{c.mode} dangerous goods list</div>
            <Badge s={c.dgl_state} />
            <div className="small muted">{c.dgl_entries} entries · rule tables: {c.rule_table_state.toLowerCase()} · {c.sources.length} source record(s)</div>
          </div>
        ))}
        <div className="tile"><div className="tile-label">Pending review</div><div className="big">{pending}</div></div>
        <div className="tile"><div className="tile-label">OCR</div><Badge s={health?.ocr_available ? "AVAILABLE" : "UNAVAILABLE"} /></div>
        <div className="tile"><div className="tile-label">AI explanations</div><Badge s={health?.llm_provider === "none" ? "DISABLED" : health?.llm_provider?.toUpperCase()} /></div>
      </div>
      <div className="modules">
        {NAV.slice(1).map((n) => (
          <Link key={n.path} to={n.path} className="module"><span className="icon">{n.icon}</span>{t(n.key)}</Link>
        ))}
      </div>
      <Card title="Operating principles">
        <ul>
          <li>Every conclusion is traced to a source, edition and verification status. Demo/unverified data never yields a verified result.</li>
          <li>IMDG and IATA are separate rule sets; one is never used to verify the other.</li>
          <li>Missing or unverifiable information produces HOLD / REVIEW REQUIRED — never a silent pass.</li>
          <li>The system never approves shipment, loading, storage or release. Authorised qualified personnel decide.</li>
        </ul>
      </Card>
    </div>
  );
}

export default function App() {
  const { t, toggle } = useI18n();
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);
  const [menu, setMenu] = useState(false);
  useEffect(() => {
    if (auth.token) api.get("/api/auth/me").then(setUser).catch(() => auth.set(null)).finally(() => setChecked(true));
    else setChecked(true);
    const out = () => setUser(null);
    window.addEventListener("dg-logout", out);
    return () => window.removeEventListener("dg-logout", out);
  }, []);
  if (!checked) return null;
  if (!user) return <Login onLogin={setUser} />;
  return (
    <UserCtx.Provider value={user}>
      <HashRouter>
        <div className="shell">
          <header className="top">
            <button className="ghost menu-btn" onClick={() => setMenu(!menu)} aria-label="menu">☰</button>
            <div className="brand"><b>{t("app")}</b><span className="small muted">{t("tagline")}</span></div>
            <div className="who"><span className="small">{user.email} · <b>{user.role}</b></span>
              <button className="ghost" onClick={toggle}>{t("language")}</button>
              <button className="ghost" onClick={() => { auth.set(null); setUser(null); }}>{t("logout")}</button></div>
          </header>
          <div className="demo-banner">{t("demoBanner")}</div>
          <div className="body">
            <nav className={menu ? "open" : ""} onClick={() => setMenu(false)}>
              {NAV.filter((n) => !n.perm || user.permissions.includes(n.perm)).map((n) => (
                <NavLink key={n.path} to={n.path} end={n.path === "/"}><span className="icon">{n.icon}</span>{t(n.key)}</NavLink>
              ))}
            </nav>
            <main>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/identify" element={<IdentifyPage />} />
                <Route path="/verify" element={<VerifyPage />} />
                <Route path="/imdg" element={<VerifyPage fixedMode="IMDG" />} />
                <Route path="/iata" element={<VerifyPage fixedMode="IATA" />} />
                <Route path="/segregation" element={<SegregationPage />} />
                <Route path="/compat" element={<CompatPage />} />
                <Route path="/sds" element={<SdsPage />} />
                <Route path="/spill" element={<SpillPage />} />
                <Route path="/erp" element={<ErpPage />} />
                <Route path="/inspection" element={<InspectionPage />} />
                <Route path="/risk" element={<RiskPage />} />
                <Route path="/reports" element={<ReportsPage />} />
                <Route path="/sources" element={<SourcesPage />} />
                <Route path="/users" element={<UsersPage />} />
              </Routes>
            </main>
          </div>
        </div>
      </HashRouter>
    </UserCtx.Provider>
  );
}
