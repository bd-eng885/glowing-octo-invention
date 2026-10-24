# Regulatory data management

## Principles
1. **IMDG Code and IATA DGR are licensed publications.** This software ships with no licensed content and does not scrape, bypass or reproduce paid content. Organisations load data they are licensed to use: from their own authorised copy, a licensed data service, or an authorised API.
2. Web search results, general chemical databases, SDSs and LLM knowledge are **never** treated as authoritative substitutes.
3. Nothing is authoritative until a qualified person has verified it in the application, with a recorded reference.

## Data model
* **`regulatory_sources`**: publisher, title, edition, amendment, publication / effective / expiry dates, licence, authorised usage, location, ingestion date, `verification_status` (`unverified` | `verified` | `demo_seed` | `test_fixture`), stored `status` (`current` | `superseded` | `not_yet_effective` | `catalogue_only`), `content_loaded`.
* **`dg_entries`**: one DGL row per source and edition: UN number, variant, PSN, class, subsidiary hazards, packing groups (`[]` means not applicable), special provisions (`null` means **not loaded**, `[]` means none), marine pollutant (`null` means not loaded), `mode_data` JSON (e.g. `ems`, `stowage`, `segregation_codes`, `pax_pi`, `cao_pi`), section reference, synonyms, CAS, entry verification (who, when, reference).
* **`rule_tables`**: deterministic tables (segregation table, IATA pairs) with source, section ref, `complete` flag and verification.

**Effective status** is computed at query time from the stored status and the dates. A source past its expiry date is treated as superseded automatically, and one before its effective date as not yet effective. Only `current` sources are used by the engines. Superseded matches are reported in `notes`.

## Controlled update procedure (new edition)
1. An **admin** registers the new source in the Source Library (edition, amendment, effective date, licence, location).
2. The admin imports the dataset (CSV or JSON). Rows are validated (UN format, PSN, class) and the whole file is rejected if any row is invalid. All imported entries start **unverified**.
3. A **DGSA approver** verifies the source record, then each entry, against the source text, recording the exact reference (edition, volume, DGL row). Admins cannot verify (segregation of duties). Demo and test data can never be verified.
4. When the new edition's effective date arrives, it becomes current automatically. Set the old edition's expiry date, or mark it `superseded`.
5. Every step is in the audit log.

### CSV import format
`un_number, variant, proper_shipping_name, hazard_class, subsidiary_hazards, packing_groups, special_provisions, marine_pollutant, section_ref, synonyms, cas_numbers, mode_data`
* List fields are `|`-separated, e.g. `subsidiary_hazards=5.1|8`.
* `special_provisions`: blank means NOT LOADED (the engine then reports "cannot be evaluated"), and `-` means none assigned.
* `mode_data`: JSON, e.g. `{"ems": "...", "segregation_codes": ["..."]}`. The values must come from the licensed source.

## Bundled demonstration data
| File | Content | Why it cannot produce verified results |
|---|---|---|
| `backend/app/data/seed/un_entries_demo.json` | 39 common entries: UN number, PSN, class, subsidiary, PG, synonyms, CAS | Source `DEMO-UN-SEED` is `demo_seed`. Compiled from general knowledge and **not** transcribed from or checked against any edition. SP, EmS, marine pollutant and quantity data are deliberately omitted. |
| `imdg_segregation_table_demo.json` | General class-versus-class segregation table | `demo_seed`, transcribed from general knowledge. Every cell must be checked against the applicable edition. |
| `iata_segregation_demo.json` | 3 segregation pairs, plus manual-check items | `demo_seed`, partial (`complete=false`) |

Catalogue-only records (no content) exist for IMDG 2024 Ed. (Amdt 42-24), the superseded IMDG Amdt 41-22, IATA DGR 67th (2026) and 68th (2027), and UN Model Regulations Rev.24. The organisation's data steward must confirm their dates.

## Test fixtures
`backend/tests/conftest.py` creates **synthetic** entries (UN9001 to UN9005, UN9100) in `test_fixture` sources. They test engine logic only (matching, status composition, edition control, conflicts) and assert no regulatory outcome for any real substance. `DG_TEST_MODE` lets fixtures exercise verified code paths and must never be set in a deployment.
