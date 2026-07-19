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

Not yet implemented: institution search/detail, program discovery, funding,
community data ingestion, image parsing, recommendation logic. See
`docs/FULL_HANDOFF.md` §20–21 for the roadmap.

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
  models/            SQLAlchemy models (universities, university_aliases)
  importers/ipeds/    IPEDS HD/EF parsing, mapping tables, upsert, CLI
  db.py, config.py    Engine/session setup, DATABASE_URL loading
migrations/           Alembic migrations
tests/                 pytest suite (Postgres-backed, transactional isolation)
docs/                  Product handoff and agent prompts
```
