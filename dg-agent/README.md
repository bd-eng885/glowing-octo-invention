# DG Compliance, Segregation & Emergency Response Assistant (MVP)

A decision-support platform for port DGSA, HSE, terminal, warehouse and freight teams. It identifies and verifies dangerous goods, checks segregation, supports spill response, and generates ERPs, inspection reports and risk assessments. Every conclusion is traced to its evidence, and every output passes through an approval workflow.

> **This is not an approval system.** It never approves goods for shipment, loading, storage or release. Every result requires review by an authorised, qualified person. **No licensed IMDG Code or IATA DGR content is included.** The bundled data is clearly labelled DEMONSTRATION data, so the engines can never return `VERIFIED AGAINST SOURCE` from it.

## Quick start (local evaluation)

```bash
# Backend (Python 3.11+; Tesseract with eng+ara language packs for OCR)
cd backend
pip install -r requirements.txt
DEMO_USERS_PASSWORD='choose-a-password' JWT_SECRET='dev-only' uvicorn app.main:app --port 8000

# Frontend (Node 20+)
cd ../frontend
npm ci
npm run dev        # http://localhost:5173 (proxies /api to :8000)
# or: npm run build  -> the backend then serves the UI at http://localhost:8000
```

The demo users are `admin@`, `approver@`, `reviewer@`, `operator@` and `viewer@demo.local`, all with the password from `DEMO_USERS_PASSWORD`.

**Production (Docker):** `cp .env.example .env`, set the secrets, then run `POSTGRES_PASSWORD=... docker compose up --build`. See [docs/OPERATIONS.md](docs/OPERATIONS.md).

**Tests:** `cd backend && python -m pytest -q`, which runs 32 tests on SQLite. For PostgreSQL, set `TEST_DATABASE_URL=postgresql+psycopg://...`.

## Documentation

| Document | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture, stack choices and trade-offs, module map, safety design |
| [docs/REGULATORY_DATA.md](docs/REGULATORY_DATA.md) | Data model, edition control, licensing, import and verification procedure |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Deployment, configuration, security, backup, operating procedures |
| [docs/schema.postgres.sql](docs/schema.postgres.sql) | Database schema (PostgreSQL) |
| `backend/tests/test_acceptance.py` | Acceptance tests mapped to the 17 required scenarios |

## Phase 1 status

### Functional (implemented and tested)
| Module | What works |
|---|---|
| DG Identification | Lookup by name, synonym, UN number, CAS or free text. Results are categorised CONFIRMED, CANDIDATE or UNKNOWN. CAS check-digit validation, a GHS-versus-transport note, a missing-information list, and derived labels and marks. |
| UN / IMDG / IATA verification | Field-by-field PSN, class, subsidiary, PG, SP and marine-pollutant checks. N.O.S. technical-name checks and spelling-variant handling. Cross-checks between documents (SDS, DGD, marks, manifest). Five statuses, with the final status capped by data authority. IMDG and IATA are strictly separate. Conflicting-source and superseded-edition handling. |
| Segregation checker | Deterministic engine that evaluates every pair, applies the most stringent primary or subsidiary hazard, and handles same-CTU and arrangement logic. Produces a matrix and colour map, records assumptions, and returns HOLD or CONFLICT decisions. Separate IMDG, IATA and warehouse paths. |
| Chemical compatibility | Reactive-group screening (acid/base, hypochlorite, oxidiser/flammable, water-reactive and others), labelled screening only |
| SDS analyzer | PDF text layer → pdftotext → OCR (English and Arabic) fallback, plus image OCR. Parses the 16-section structure, Section 14, CAS and H-statements. Flags contradictions, missing sections and prompt-injection text. Upload validation by file signature. |
| Spill response | Escalation triggers, immediate priorities, hazard assessment by class, "do NOT" precautions, references, containment withheld when unsafe, PPE, medical, waste and notifications |
| ERP generator | All 18 required sections. Missing site data is marked `[REQUIRED INPUT]`. Exports to PDF and Word. |
| Container inspection | 13-point checklist, photo upload, visual observations kept separate from verified non-compliance, risk rating, corrective actions, and STOP / HOLD outcomes |
| Risk assessment | Configurable risk matrices (validated). HIRA, JSA, chemical RA, RCA, toolbox talk, drill evaluation and spill incident templates. |
| Reports & audit | Save any result as a report. Submit → review → approve/reject, with no self-approval, a required approval comment and role checks. CAPA register. Exports to PDF, DOCX, XLSX and CSV. Hash-chained audit log, made append-only by database triggers. |
| Source library | Source catalogue with edition, licence, effective and expiry dates and computed in-force status. Controlled CSV/JSON import (imported entries start unverified). Per-entry verification with a recorded reference, by DGSA approvers only. |
| Users & roles | viewer, operator, dg_reviewer, dgsa_approver and admin, with segregation of duties: an admin cannot approve or verify data. JWT auth with PBKDF2 password hashing. |
| UI | Responsive React app covering all 14 modules, with English and Arabic (RTL) navigation and a persistent DEMO DATA banner |

### Incomplete or not yet built
- **No licensed regulatory content.** The IMDG Dangerous Goods List, EmS, stowage and segregation codes (column 16b), IATA packing instructions, quantity limits, and State and operator variations must be lawfully supplied and verified.
- The IMDG engine covers the general class-versus-class table only. Individual DGL segregation codes, segregation-group rules, Class 1 compatibility, and container-ship stowage geometry are listed as manual checks.
- The IATA segregation seed is a 3-pair partial subset, so every IATA result is HOLD.
- Arabic covers navigation and common labels. Module body text and the PDF exports are English (Word exports support Arabic text). Arabic OCR quality has not been benchmarked.
- AI explanations (optional, off by default) are implemented behind a citation guard but have not been exercised against a live model in this environment.
- Docker images were written but not built here (no Docker daemon available). Not yet built: object storage, encryption at rest, SSO/MFA, refresh tokens, rate limiting, Alembic migrations, and background OCR jobs for large scans.

### Regulatory datasets connected
| Source | Status |
|---|---|
| `DEMO-UN-SEED`: 39 common UN entries (identity fields only) | **DEMONSTRATION DATA**, not authoritative |
| `DEMO-IMDG-SEG-SEED`: general segregation table | **DEMONSTRATION DATA**, transcribed from general knowledge and not authoritative |
| `DEMO-IATA-SEG-SEED`: 3 segregation pairs | **DEMONSTRATION DATA**, partial |
| IMDG Code 2024 Ed. (Amdt 42-24), IATA DGR 67th / 68th, UN Model Regs Rev.24 | Catalogue records only, with **no content loaded** (licensed) |

### Must be validated by a qualified DG professional before operational use
1. Every regulatory entry and rule table loaded from the licensed source, verified in the app per entry with a reference.
2. The segregation engine's logic on subsidiary hazards, same-CTU handling and arrangement interpretation, against the applicable IMDG edition (and IATA rules for air).
3. The spill-response escalation triggers, thresholds (the default site threshold is 200 L/kg) and generic hazard-class considerations, against the site ERP and local emergency procedures.
4. The inspection checklist, risk matrices and ERP template content, against company procedures and national legislation.
5. Role assignments and approver qualifications.
