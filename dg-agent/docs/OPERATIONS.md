# Operations

## Deployment
1. `cp .env.example .env`, then set `JWT_SECRET`, `INITIAL_ADMIN_EMAIL` and `INITIAL_ADMIN_PASSWORD`, and set `SEED_DEMO_DATA=false` for production.
2. `POSTGRES_PASSWORD=<strong> docker compose up -d --build`. The app listens on port 8000 and serves both the API and the UI.
3. Put a TLS-terminating reverse proxy in front (nginx, Traefik or a cloud load balancer). Do not expose port 8000 directly.
4. Sign in as the initial admin, create users with appropriate roles, and record approver qualifications.
5. Load licensed regulatory data per [REGULATORY_DATA.md](REGULATORY_DATA.md) and have it verified.

The tables and audit triggers are created automatically on startup. The schema for DBA review is in `docs/schema.postgres.sql`. Alembic migrations are planned (Phase 3), so until then schema changes need a manual migration.

## Configuration
All configuration comes from environment variables (see `.env.example`). No secrets live in the code, the frontend, prompts or source control. `ANTHROPIC_API_KEY` is read by the SDK only when `LLM_PROVIDER=anthropic`.

## Security checklist
- [ ] Strong `JWT_SECRET`; HTTPS only; restrict `CORS_ORIGINS`.
- [ ] `STORAGE_DIR` on an encrypted volume with restricted permissions; back it up together with the database.
- [ ] Database backups (e.g. daily `pg_dump`, plus WAL archiving) with tested restores. The audit hash chain lets you verify integrity after a restore (`GET /api/audit/verify`).
- [ ] Demo users disabled (`DEMO_USERS_PASSWORD` empty, `SEED_DEMO_DATA=false`).
- [ ] Least-privilege roles; review user access quarterly.
- [ ] If enabling AI explanations, check that sending engine output to the LLM provider is acceptable under the confidentiality obligations for customer documents. Engine output can contain product names from uploaded SDSs.
- [ ] `DG_TEST_MODE` must be unset.

## Operating procedures
* **Verification workflow:** the operator runs the check and saves it as a report, then submits it. A reviewer reviews it, and an authorised DGSA approver (not the creator) approves or rejects it with a comment. The export records the review state and approval history.
* **HOLD / NOT VERIFIED results:** resolve manually against the authoritative publication. Record the outcome as a report comment or approval note; never override the engine status by editing data.
* **Incidents:** the Spill Response Assistant supports, and never replaces, the site ERP and the emergency services. Raise the alarm first.
* **Audit:** run `GET /api/audit/verify` periodically (and after any restore). A broken chain is a security incident.

## Running tests
```bash
cd backend && python -m pytest -q                       # SQLite
TEST_DATABASE_URL=postgresql+psycopg://user:pw@host/db python -m pytest -q   # PostgreSQL
cd ../frontend && npm run typecheck && npm run build
```
