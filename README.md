# US Graduate Recommender

A U.S.-only graduate-school information and recommendation platform. Full
product and engineering context lives in [docs/FULL_HANDOFF.md](docs/FULL_HANDOFF.md) —
read it before working on this repo. Agent-facing instructions are in
[docs/PRIMARY_AGENT_PROMPT.md](docs/PRIMARY_AGENT_PROMPT.md) and
[docs/REVIEW_AGENT_PROMPT.md](docs/REVIEW_AGENT_PROMPT.md); the working
process (branching, review) is in [CONTRIBUTING.md](CONTRIBUTING.md).

## Status

Implemented so far:

- Institution schema (`universities`, `university_aliases`) — see
  `src/us_grad_recommender/models/university.py`.
- An idempotent importer for two IPEDS survey components:
  - `HD` (institutional characteristics) — identity, location, sector,
    highest degree offered, a master's-granting heuristic, aliases, and the
    2021 Carnegie Basic Classification + Size & Setting Classification
    (both are columns embedded directly in the HD file, so no separate
    Carnegie importer or data source is needed).
  - `EF`, component A (fall enrollment) — total / graduate / international
    graduate enrollment counts.
- A read-only institution search/detail API (FastAPI) — see
  `src/us_grad_recommender/api/`.
- Program/catalog schema (Phase 2.1 — schema only, no crawler yet): see
  `src/us_grad_recommender/models/catalog.py` and
  `docs/PHASE_2_CATALOG_DESIGN.md`. `academic_units`, `degree_types`,
  `programs`, `program_aliases`, `program_tracks`,
  `program_track_deadlines`, `program_concentrations`,
  `admission_requirements`, `evidence_sources`, `source_snapshots`.
- Review/provenance pipeline schema (Phase 2.2A — schema only): see
  `src/us_grad_recommender/models/review.py`. `parsed_documents`,
  `data_review_tasks`, `data_conflicts`.
- A minimal read-only frontend (`web/`) — institution search + detail
  pages over the API above. No program/funding/recommendation UI; see
  "Running the frontend" below.

All of the schema/data items above are currently empty; nothing populates them until the
adapter framework and parser pipeline are built (Phase 2.2B+) and the
pilot runs (Phase 2.3).

Not yet implemented: catalog adapters, parser pipeline, HTML/PDF parsing,
network fetching, a review UI, automatic verification-status transitions,
funding, community data ingestion, image parsing, recommendation logic.
See `docs/FULL_HANDOFF.md` §20–21 and `docs/PHASE_2_CATALOG_DESIGN.md` for
the roadmap.

## Requirements

- Python >= 3.9 (developed and CI-tested against 3.9 and 3.12; prefer 3.12+
  for new environments — 3.9 is past upstream end-of-life and is only kept
  as the floor because it's what's available in some deployment targets)
- PostgreSQL (developed against Postgres 18 locally; CI runs against
  `postgres:16`). SQLite is not supported — the importer relies on
  Postgres-native `INSERT ... ON CONFLICT` upserts and `ENUM` types.

## Setup

```bash
python3 -m pip install -e ".[dev]"
cp .env.example .env   # edit DATABASE_URL to point at your local Postgres
createdb us_grad_recommender_dev
alembic upgrade head
```

## Running the importer

Download the IPEDS files you need from the
[IPEDS Data Center](https://nces.ed.gov/ipeds/datacenter/data/) (e.g.
`HD2023.zip`, `EF2023A.zip`), unzip them, then:

```bash
# Institutional characteristics — creates/updates universities + aliases.
# Only imports master's-granting institutions by default; pass
# --include-all to import every institution in the file.
import-ipeds hd --file /path/to/hd2023.csv --year 2023

# Fall enrollment — backfills total/graduate/international-graduate
# enrollment on institutions already imported via `hd`.
import-ipeds ef --file /path/to/ef2023a.csv --year 2023
```

Both commands are idempotent: re-running with the same file is a no-op,
and re-running with a newer year's file refreshes the data in place.

## Running the API

```bash
uvicorn us_grad_recommender.api.app:app --reload
```

Interactive docs at `http://127.0.0.1:8000/docs`. Endpoints:

- `GET /universities?q=&state=&sector=&masters_granting=&limit=&offset=` —
  search by name or alias (case-insensitive substring), with optional exact
  filters; returns `{total, limit, offset, results}`.
- `GET /universities/{unitid}` — full detail including aliases; 404 if not
  found.
- `GET /healthz` — liveness check.

CORS is enabled for `http://localhost:3000` / `http://127.0.0.1:3000` (the
Next.js dev server default) so `web/` can call this API directly in local
dev.

## Running the frontend

A minimal read-only frontend (`web/`, Next.js + TypeScript + Tailwind) over
the institution search/detail API — search box + institution detail page.
No program/funding/outcome UI exists yet; this only surfaces what Phase 1
(the institution index) actually has.

```bash
cd web
npm install
cp .env.local.example .env.local   # points at http://localhost:8000 by default
npm run dev
```

Requires the API (above) to be running separately. Open
`http://localhost:3000`.

Frontend checks (CI runs the same — see the `web` job in
`.github/workflows/ci.yml`):

```bash
cd web
npx tsc --noEmit
npx eslint .
npm test
npm run build
```

`tests/test_frontend_contract.py` (in the main pytest suite) guards
against `web/src/lib/api.ts`'s hand-maintained types drifting from
`api/schemas.py`/`models/university.py` — run it as part of `pytest -q`
below, not from `web/`.

## Development checks

Run these before opening a PR (CI runs the same checks — see
`.github/workflows/ci.yml`):

```bash
ruff check .
mypy src
alembic upgrade head
pytest -q
```

Tests run against a separate Postgres database
(`TEST_DATABASE_URL`, defaults to `us_grad_recommender_test`) so they never
touch your dev data:

```bash
createdb us_grad_recommender_test
pytest -q
```

## Project layout

```
src/us_grad_recommender/
  models/            SQLAlchemy models: university.py (institution index),
                      catalog.py (program/catalog schema, Phase 2.1),
                      review.py (review/provenance pipeline, Phase 2.2A),
                      common.py (shared provenance enums)
  importers/ipeds/    IPEDS HD/EF parsing, mapping tables, upsert, CLI
  api/                FastAPI app: institution search/detail (read-only)
  db.py, config.py    Engine/session setup, DATABASE_URL loading
migrations/           Alembic migrations
tests/                 pytest suite (Postgres-backed, transactional isolation)
docs/                  Product handoff and agent prompts
web/                   Next.js frontend — institution search/detail UI only
                       (see "Running the frontend" above)
```
