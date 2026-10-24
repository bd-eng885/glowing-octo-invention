# Validation report — 2026-10-24

Validation run of the existing MVP: start-up with the documented commands, the existing acceptance tests, independent workflow tests against the live application, a regulatory data audit, defect fixes, and a full re-test.

**Environment:** Linux; Python 3.13; Node 22; PostgreSQL 16; Tesseract 5.3.4 (eng+ara); Chromium (Playwright).

## 1. Test results (after fixes)

| Suite | Command | Result |
|---|---|---|
| Backend acceptance + regression, SQLite | `cd backend && python -m pytest -q` | **43 passed**, 0 failed |
| Same suite, PostgreSQL 16 | `TEST_DATABASE_URL=postgresql+psycopg://… python -m pytest -q` | **43 passed**, 0 failed |
| Frontend typecheck and build | `npm run typecheck && npm run build` | No errors |
| Browser end-to-end through the Vite dev server (`e2e/ui_smoke.js`) | `node ui_smoke.js` | **40 PASS**, 0 FAIL |
| Live API workflow probe (`e2e/api_probe.py`) | `python3 api_probe.py` | Ran workflows A–I; outputs reviewed manually (Section 4) |

* Before the fixes, the original 32 acceptance tests passed on both databases.
* The 11 new regression tests (`tests/test_regressions.py`) cover defects 1–8. Nine of them were run against the original code with the fixes stashed, and all nine failed there. The other two (defects 7 and 8) were written after their fix, so they have only been seen passing.
* The test data is synthetic: UN9xxx fixtures, generated SDS text, PDFs and images. No test asserts the real-world regulatory classification of any substance.

## 2. Defects found and fixed

| # | Defect (how it was found) | Fix |
|---|---|---|
| 1 | SDS Section 14: the PSN, class and packing group were **silently lost** when a value sat on the next line (the EU "14.2. UN proper shipping name" layout), had no colon, or carried a "(IMDG)" qualifier. OCR misread "II" as "Il", and the PG was dropped. *(Live probe with a scanned PDF.)* | Label patterns accept an optional qualifier, separator and next-line value. OCR "Il/ll/1I" is repaired, with a warning. New findings flag any PSN, class or PG that can't be extracted, and the parser no longer reads "1" from a following "14.4" heading. |
| 2 | Identification: an extracted UN number with no loaded data (UN1992 mixture) was hidden behind pure-substance CAS candidates (UN1230 methanol), and the overall result was CANDIDATE. *(Live probe.)* | The overall result becomes UNKNOWN, with `unmatched_un_numbers` listed and a pure-substance/mixture caveat. |
| 3 | Segregation: an acid and an alkali of the same class (HCl and NaOH, both class 8) were shown as "no general requirement", with no flag unless the user typed segregation groups. *(Live probe.)* | Non-regulatory compatibility screening now runs on every IMDG and IATA pair. A high-severity flag raises the pair to HOLD, labelled "NON-REGULATORY screening". |
| 4 | ERP: the plan **assumed trained hazmat responders**, had no input for response capabilities, never pulled references from the source library, and had two `[REQUIRED INPUT]` items that could never be cleared. *(Live probe.)* | Added a `capabilities` input (an unknown capability means site staff do not contain), ERT, external-support and fire-response fields, a level-1 criteria field, and legislation and SDS-register fields. Section 18 lists the library sources with their real verification state and the substance data used. |
| 5 | The audit log, including login emails, was readable by the viewer and operator roles. *(Role probe.)* | New `view_audit` permission (reviewer, approver and admin only), and the UI hides the panel for other roles. |
| 6 | The JWT-secret warning was never printed because logging wasn't configured. | `logging.basicConfig` added in `main.py`. |
| 7 | The dashboard and verify page reported IMDG and IATA "content available / DEMO" because a demo segregation table existed, although **0 IMDG/IATA DGL entries are loaded**. *(Regulatory audit.)* | Coverage reports DGL entries and rule tables separately (`dgl_state`, `rule_table_state`). |
| 8 | Spill-incident and drill templates inserted `[REQUIRED INPUT]` placeholders without listing them as missing information. *(Template probe.)* | Placeholders are now listed under `missing_information`. |
| — | Arabic text in PDF exports rendered as empty boxes (Helvetica has no Arabic glyphs). | The PDF embeds DejaVu Sans and shapes Arabic (arabic-reshaper + python-bidi), and warns if no font is found. `fonts-dejavu-core` was added to the Dockerfile. |

## 3. Regulatory data audit (the live system state, read from `/api/sources`)

| Source code | Publisher / title | Edition | Effective | Edition status | Content | Verification | Used by engines |
|---|---|---|---|---|---|---|---|
| `DEMO-UN-SEED` | DEMONSTRATION DATA (software vendor) | not an authoritative edition | — | current | **39 entries** (identity fields only) | demo_seed | Identification, verification (reference only), segregation and spill lookups |
| `DEMO-IMDG-SEG-SEED` | DEMONSTRATION DATA | not an authoritative edition | — | current | 1 rule table (class × class) | demo_seed | IMDG segregation |
| `DEMO-IATA-SEG-SEED` | DEMONSTRATION DATA | not an authoritative edition | — | current | 1 partial rule table (3 pairs) | demo_seed | IATA segregation |
| `IMDG-42-24` | IMO — IMDG Code | 2024 Ed., Amdt 42-24 | 2026-01-01* | catalogue only | **not loaded (0 entries)** | unverified | Not used |
| `IMDG-41-22` | IMO — IMDG Code | 2022 Ed., Amdt 41-22 | 2024-01-01 → 2025-12-31* | superseded | not loaded | unverified | Not used (excluded) |
| `IATA-DGR-67` | IATA — Dangerous Goods Regulations | 67th Ed. (2026) | 2026-01-01 → 2026-12-31* | catalogue only | **not loaded (0 entries)** | unverified | Not used |
| `IATA-DGR-68` | IATA — DGR | 68th Ed. (2027) | 2027-01-01* | not yet effective | not loaded | unverified | Not used |
| `UN-MR-REV24` | UN — Model Regulations | Rev.24 | — | catalogue only | not loaded | unverified | Not used |

\* These dates were entered from general knowledge, and each record is marked "to be confirmed by the data steward". They are catalogue metadata, not loaded regulatory text.

**What every lookup returns today:**
* **Source and title:** always present in `evidence[]`. Today it is always `DEMO-UN-SEED` or a demo rule table.
* **Edition and effective date:** "Not an authoritative edition" and none.
* **Table, section or entry:** `"Demo seed (no authoritative section reference)"`. No paragraph or table number is cited, because none was transcribed.
* **Data present?** UN Model demo identity fields: yes. IMDG DGL: **no**. IATA DGR: **no**.
* **Verified or provisional?** Every live result is **`NOT VERIFIED — HUMAN REVIEW REQUIRED`**, with the computed outcome shown as `provisional_status`. Verification against IMDG or IATA returns `basis: reference_only`.

**Conclusion:** no regulatory conclusion produced by this installation is verified against authoritative IMDG or IATA data. The "VERIFIED AGAINST SOURCE" path has been exercised only with synthetic test fixtures under `DG_TEST_MODE`.

## 4. Workflow results (live application, demonstration data)

| Workflow | What was executed | Observed |
|---|---|---|
| A. UN/PSN verification | UN1090 with the correct PSN, a misspelt PSN ("ACETON"), UN1230 declared as class 6.1, the same UN under IATA and UN Model, and UN1992 (not loaded) | Correct field results: match, misspelling discrepancy (0.92 similarity), subsidiary-versus-primary discrepancy. Final status NOT VERIFIED in all cases; IMDG and IATA basis `reference_only`; UN1992 gives "no entry" plus "absence ≠ non-DG". |
| B. SDS upload and extraction | Synthetic SDS as a text PDF, a scanned image-only PDF (OCR) and a PNG; Arabic text SDS; 6 Section 14 layouts | All three files: product, UN1992, PSN, class 3, subsidiary 6.1, PG II, MP No, both CAS numbers (check digits valid), H225/H301, revision date. OCR flagged "verify against original". |
| C. IMDG segregation | 6 materials (UN1203, 2014, 1823, 1017, 1789, 3480) in the same CTU, same hold, and unspecified arrangements | 15 pairs. Conflicts: 3/5.1, 3/2.3, 5.1/8, and 2.3(5.1, 8) pairs. Acid/alkali raised to HOLD (after fix). Same CTU gives CONFLICT; other arrangements give HOLD. Table is demo, so not authoritative. |
| D. IATA | Verify UN3480; segregate 3, 5.1 and 1.4S in the same ULD | NOT VERIFIED (no IATA data); CAO label "depends — IATA data not loaded"; 3/5.1 conflict; other pairs "not in loaded subset"; 7 manual checks listed. **No IATA restrictions (packing instructions, quantity limits, passenger/CAO, variations) can be evaluated.** |
| E. Multi-material segregation | As C, plus a class-1 item without a division | Every pair evaluated; an unmappable class gives HOLD with the reason. |
| F. Unknown spill | No identity, 50 L, vapour release | MAJOR → external services. First actions: protect life and alarm, isolate and cordon, no contact, call services. Containment WITHHELD; PPE not specified. |
| G. ERP | All 31 site fields, 2 contacts, chlorine, trained team = yes/no/unstated | 18 sections, 0 `[REQUIRED INPUT]` remaining, contacts included, strategy follows the stated capability, library sources listed with their true state (IMDG-42-24 "content not loaded"). |
| H. Arabic / English | UI toggle; Arabic SDS text; Arabic PDF export | `dir=rtl`, `lang=ar`; navigation 14/14 translated; **spill page form labels 4/20 translated**; Arabic SDS fields parsed; Arabic renders in PDF (pdftotext confirms). |
| I. Auth, roles, audit, exports | Wrong password; no token; viewer, operator, reviewer, admin and approver actions; self-approval; deactivated user; exports of 8 report types × 4 formats | 401, 401 and 403 as designed. Only the approver can approve, and never their own report. Audit chain valid (71 records); UPDATE/DELETE blocked. 32/32 exports returned 200. The ERP exports were also opened and checked with pdftotext, python-docx, openpyxl and the csv reader; the other 7 types were checked for HTTP 200 and file signature only. |

## 5. Module status

Software status means whether the function works and is tested. Regulatory status means whether its conclusions are backed by authoritative data.

| Module | Software | Regulatory | Notes |
|---|---|---|---|
| Login, auth, sessions | **PASS** | n/a | JWT, PBKDF2, deactivation, 401 on bad or absent token |
| Navigation / UI shell | **PASS** | n/a | 15 routes, no page errors, mobile at 390 px |
| DG Identification | **PASS** | **NOT VERIFIED** | Demo identity data only |
| UN Number Verification | **PASS** | **NOT VERIFIED** | The verified path is proven only with test fixtures |
| IMDG Compliance | **PARTIAL** | **NOT VERIFIED** | Identity fields only; no IMDG DGL, EmS, stowage, SP, LQ/EQ or packaging data |
| IATA DGR Compliance | **PARTIAL** | **NOT VERIFIED** | No packing instructions, quantity limits, passenger/CAO or variations |
| Segregation Checker | **PARTIAL** | **NOT VERIFIED** | General table only (demo); DGL SG codes, segregation groups, Class 1 and stowage geometry are manual |
| Chemical Compatibility | **PASS** | n/a (screening) | Labelled non-regulatory |
| SDS Analyzer | **PARTIAL** | n/a | Works on synthetic EN/AR text, PDF, scanned PDF and PNG; **not tested on a corpus of real manufacturer SDSs** |
| Spill Response Assistant | **PASS** (fail-safe workflow) | **NOT VERIFIED** | Hazard considerations are generic built-in text; no EmS or ERG data loaded |
| ERP Generator | **PASS** | References reflect real library state | Content still needs site and legal review |
| Container Inspection | **PASS** | n/a | Visual observations kept separate from verified non-compliance |
| Risk Assessment | **PASS** | n/a | 7 templates, configurable matrix |
| Reports and Audit Trail | **PASS** | n/a | Workflow, CAPA, 4 export formats, hash chain |
| Regulatory Source Library | **PASS** | n/a | Import, edition control and per-entry verification tested |
| User and Role Management | **PASS** | n/a | Create, validate, role change, deactivate, self-demote guard |
| Arabic interface | **PARTIAL** | n/a | Navigation and common labels only |
| AI explanations | **NOT VERIFIED** | n/a | Citation guard tested with a fake provider; no live model call |
| Docker deployment | **NOT VERIFIED** | n/a | Not built (no Docker daemon in this environment) |
