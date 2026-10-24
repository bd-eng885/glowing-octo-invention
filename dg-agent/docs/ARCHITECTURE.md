# Architecture

```
 Browser (React + TypeScript SPA, EN/AR RTL, mobile responsive)
        │  JSON over HTTPS, JWT bearer
        ▼
 FastAPI application (backend/app)
   routers/     auth_users · sources · analysis · reports        ← RBAC on every endpoint
   engines/     dg (identify/verify) · segregation · compat · spill · erp · inspection
                risk · templates · documents (PDF/OCR/SDS) · provenance · textutil
   llm/         provider abstraction + citation guard (optional, explanation only)
   exports/     PDF (reportlab) · DOCX (python-docx) · XLSX (openpyxl) · CSV
   audit.py     hash-chained, append-only audit log
        │ SQLAlchemy 2
        ▼
 PostgreSQL (SQLite for local evaluation)        File storage (STORAGE_DIR volume)
   regulatory_sources, dg_entries, rule_tables   uploaded SDS / photos (sha256 recorded)
   reports, approvals, corrective_actions
   risk_matrices, users, stored_files, audit_log (UPDATE/DELETE blocked by trigger)
```

## Stack choices and trade-offs

| Choice | Why | Trade-off |
|---|---|---|
| **FastAPI + Python** | The Python ecosystem covers PDF, OCR, DOCX, XLSX and PDF generation. It has typed request models, and engines can be unit-tested without HTTP. | A Python runtime on the server |
| **Deterministic rule engines** | Regulatory logic must be reproducible, testable and explainable. The LLM never decides anything. | Every rule must be encoded and verified explicitly; nothing is "inferred" |
| **React + Vite SPA** (not Next.js) | One static bundle served by the API, a single deployable, no Node runtime in production, and simple offline or air-gapped deployment for terminals | No server-side rendering (not needed for an authenticated internal tool) |
| **PostgreSQL** (SQLite fallback) | Transactional integrity, triggers for the append-only audit, JSON columns for mode-specific data | SQLite has no concurrent writers, so use it for evaluation only |
| **JWT + PBKDF2** | Stateless and dependency-light | No refresh or revocation list yet; integrate with company SSO for production |
| **Tesseract OCR (eng+ara)** | Open source, runs on premises, so confidential SDSs and manifests never leave the site | Lower accuracy than commercial OCR on poor scans. The output is always flagged "verify against original". |
| **Model-independent LLM layer** | Optional plain-language explanations. The `LLMProvider` protocol lets you swap providers. The default is `none`. | Explanations are withheld whenever they cite anything absent from the engine output |

## Safety design (how the requirements are enforced in code)

| Requirement | Implementation |
|---|---|
| Traceable evidence | Every entry and rule table belongs to a `RegulatorySource` (edition, amendment, dates, licence, section ref). Results embed `evidence[]` records with `retrieved_at`. |
| Separate facts, interpretation and recommendation | Engine `checks` are facts compared against data. `conditions` and `limitations` are interpretation. `corrective_actions` are recommendations. LLM output is labelled `AI INTERPRETATION`. |
| No fabricated citations | Seed data carries no section references ("Demo seed (no authoritative section reference)"). The LLM citation guard rejects unsupported UN, paragraph, table, SP and class references. |
| Fail safe | `NOT VERIFIED — HUMAN REVIEW REQUIRED` unless the source and entry are verified and the edition is in force (`engines/provenance.py`). `HOLD — MANUAL VERIFICATION REQUIRED` for missing data, demo tables, partial tables and unloaded DGL provisions. Spill containment is `WITHHELD` for unknown materials or untrained responders. |
| No auto-approval | Every result carries `requires_human_approval: true`. Approval needs the `approve` permission, a comment, and a different user from the creator. |
| IMDG ≠ IATA | `dg.verify` queries only the selected rule set's sources. UN Model data is used only as "reference_only" and can never produce a verified status. The segregation engine loads mode-specific tables. |
| Absence ≠ non-DG | `identify` returns UNKNOWN with an explicit warning. `NON_DG` and `NOT_REGULATED` are never produced automatically. |
| Edition control | `effective_status()` applies effective and expiry dates, superseded and not-yet-effective entries are excluded and reported, and conflicting current sources produce NOT VERIFIED with both shown. |
| Upload safety | Size limit, magic-byte type sniffing (a spoofed type gets a 415), files stored under random names, sha256 recorded, and prompt-injection-like text detected and reported. Document text is never executed or used as instructions. |
| Tamper-evident audit | SHA-256 hash chain over every action, plus database triggers that block UPDATE and DELETE on `audit_log`. `/api/audit/verify` recomputes the chain. |
| Secrets | Secrets come only from the environment (`.env.example`). The frontend holds only the user's session JWT. |

## Status vocabulary
* Verification: `VERIFIED AGAINST SOURCE`, `MATCH WITH CONDITIONS`, `DISCREPANCY FOUND`, `INSUFFICIENT INFORMATION`, `NOT VERIFIED — HUMAN REVIEW REQUIRED`. The `provisional_status` field shows the outcome computed against non-authoritative data.
* Segregation: `CONFLICT IDENTIFIED — DO NOT LOAD/STOW AS PROPOSED`, `HOLD — MANUAL VERIFICATION REQUIRED`, `NO CONFLICT IDENTIFIED BY ENGINE — QUALIFIED REVIEW REQUIRED`.
* Identification categories: `CONFIRMED`, `CANDIDATE`, `NON_DG`, `NOT_REGULATED` (the last two are recorded only by qualified determination), `UNKNOWN`.

## API surface (OpenAPI at `/docs`)
`/api/auth/*`, `/api/users`, `/api/sources` (+ `/coverage`, `/entries`, `/{id}/import`, `/{id}/verify`, `/rule-tables`), `/api/dg/identify`, `/api/dg/verify`, `/api/dg/entries/{un}`, `/api/documents/upload`, `/api/segregation/check`, `/api/compatibility/screen`, `/api/spill/assess`, `/api/erp/*`, `/api/inspection/*`, `/api/risk/matrices`, `/api/reports/*` (+ `submit`, `review`, `approve`, `reject`, `export/{pdf|docx|xlsx|csv}`), `/api/capa`, `/api/audit`, `/api/audit/verify`, `/api/ai/explain`.
