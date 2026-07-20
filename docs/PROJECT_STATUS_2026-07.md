# Project Status — 2026-07

Snapshot of what exists on `main` as of commit `454499a`, before starting
Phase 2 (program/catalog). Written as a checkpoint for review before
committing to a schema that's expensive to change later.

---

## 1. Running the API locally, with real examples

```bash
python3 -m pip install -e ".[dev]"
cp .env.example .env        # point DATABASE_URL at your local Postgres
createdb us_grad_recommender_dev
alembic upgrade head
import-ipeds hd --file /path/to/hd2023.csv --year 2023
import-ipeds ef --file /path/to/ef2023a.csv --year 2023
uvicorn us_grad_recommender.api.app:app --reload
```

Docs UI at `http://127.0.0.1:8000/docs`. All examples below were run
against the real dev database (2,113 institutions) — output is real, not
illustrative.

### School name search

```bash
curl "http://127.0.0.1:8000/universities?q=Louisiana%20State"
```
```json
{
  "total": 4,
  "limit": 25,
  "offset": 0,
  "results": [
    {"unitid": 159391, "canonical_name": "Louisiana State University and Agricultural & Mechanical College", "city": "Baton Rouge", "state": "LA", "sector": "public", "masters_granting": true, "coverage_tier": "INDEXED"},
    {"unitid": 159373, "canonical_name": "Louisiana State University Health Sciences Center-New Orleans", "city": "New Orleans", "state": "LA", "sector": "public", "masters_granting": true, "coverage_tier": "INDEXED"},
    {"unitid": 435000, "canonical_name": "Louisiana State University Health Sciences Center-Shreveport", "city": "Shreveport", "state": "LA", "sector": "public", "masters_granting": true, "coverage_tier": "INDEXED"},
    {"unitid": 159416, "canonical_name": "Louisiana State University-Shreveport", "city": "Shreveport", "state": "LA", "sector": "public", "masters_granting": true, "coverage_tier": "INDEXED"}
  ]
}
```
(LSU is one of the "overlooked institution" examples named in `docs/FULL_HANDOFF.md` §2 — confirms it's actually indexed and searchable.)

### Alias search

```bash
curl "http://127.0.0.1:8000/universities?q=AAMU"
```
```json
{
  "total": 1,
  "limit": 25,
  "offset": 0,
  "results": [
    {"unitid": 100654, "canonical_name": "Alabama A & M University", "city": "Normal", "state": "AL", "sector": "public", "masters_granting": true, "coverage_tier": "INDEXED"}
  ]
}
```
`AAMU` is not a substring of the canonical name — this matches through the
`university_aliases` table (sourced from IPEDS `HD.IALIAS`).

### Filter by state

```bash
curl "http://127.0.0.1:8000/universities?state=tx&limit=3"
```
Returns institutions with `state = 'TX'` (the API uppercases the input).

### Filter by sector

```bash
curl "http://127.0.0.1:8000/universities?sector=private_for_profit&limit=3"
```
```json
{
  "total": 192,
  "limit": 3,
  "offset": 0,
  "results": [
    {"unitid": 488031, "canonical_name": "Abraham Lincoln University", "city": "Glendale", "state": "CA", "sector": "private_for_profit", "masters_granting": true, "coverage_tier": "INDEXED"},
    {"unitid": 108232, "canonical_name": "Academy of Art University", "city": "San Francisco", "state": "CA", "sector": "private_for_profit", "masters_granting": true, "coverage_tier": "INDEXED"},
    {"unitid": 439969, "canonical_name": "Acupuncture and Massage College", "city": "Miami", "state": "FL", "sector": "private_for_profit", "masters_granting": true, "coverage_tier": "INDEXED"}
  ]
}
```
Valid `sector` values: `public`, `private_nonprofit`, `private_for_profit`, `unknown`.

### Filter by `masters_granting`

```bash
curl "http://127.0.0.1:8000/universities?state=al&masters_granting=true&limit=3"
```
```json
{
  "total": 34,
  "limit": 3,
  "offset": 0,
  "results": [
    {"unitid": 100654, "canonical_name": "Alabama A & M University", "city": "Normal", "state": "AL", "sector": "public", "masters_granting": true, "coverage_tier": "INDEXED"},
    {"unitid": 483975, "canonical_name": "Alabama College of Osteopathic Medicine", "city": "Dothan", "state": "AL", "sector": "private_nonprofit", "masters_granting": true, "coverage_tier": "INDEXED"},
    {"unitid": 100724, "canonical_name": "Alabama State University", "city": "Montgomery", "state": "AL", "sector": "public", "masters_granting": true, "coverage_tier": "INDEXED"}
  ]
}
```
Currently every imported row has `masters_granting = true` since the
importer filters to master's-granting institutions by default (see §4
below) — this filter becomes meaningful once `--include-all` imports are
added to the mix.

### Pagination

```bash
curl "http://127.0.0.1:8000/universities?state=CA&limit=2&offset=2"
```
```json
{
  "total": 218,
  "limit": 2,
  "offset": 2,
  "results": [
    {"unitid": 108232, "canonical_name": "Academy of Art University", "city": "San Francisco", "state": "CA", "sector": "private_for_profit", "masters_granting": true, "coverage_tier": "INDEXED"},
    {"unitid": 108269, "canonical_name": "Academy of Chinese Culture and Health Sciences", "city": "Oakland", "state": "CA", "sector": "private_nonprofit", "masters_granting": true, "coverage_tier": "INDEXED"}
  ]
}
```
`limit` is capped at 100 server-side (requesting more returns `422`).

### Institution detail

```bash
curl "http://127.0.0.1:8000/universities/100654"
```
```json
{
  "unitid": 100654,
  "canonical_name": "Alabama A & M University",
  "website": "www.aamu.edu/",
  "city": "Normal",
  "state": "AL",
  "latitude": 34.783368,
  "longitude": -86.568502,
  "sector": "public",
  "highest_degree_level": 9,
  "highest_degree_label": "Doctor's degree",
  "carnegie_classification": 18,
  "carnegie_classification_label": "Master's Colleges & Universities: Larger Programs",
  "campus_setting": 14,
  "campus_setting_label": "Four-year, medium, highly residential",
  "masters_granting": true,
  "masters_granting_basis": "IPEDS HD: CYACTIVE=1 AND DEGGRANT=1 AND GROFFER=1 AND HLOFFER>=7 (highest offering is master's degree or above). This is an offering-capability heuristic, not a verified count of active master's programs — see FULL_HANDOFF.md §4.",
  "degree_granting": true,
  "active": true,
  "total_enrollment": 6614,
  "graduate_enrollment": 769,
  "international_graduate_enrollment": 64,
  "enrollment_year": 2023,
  "coverage_tier": "INDEXED",
  "ipeds_year": 2023,
  "source_dataset": "IPEDS HD2023",
  "last_verified_at": "2026-07-19",
  "updated_at": "2026-07-19T14:49:43.739909-04:00",
  "aliases": [
    {"alias": "AAMU", "alias_type": "ipeds_alias", "source": "IPEDS HD2023"}
  ]
}
```

### 404 example

```bash
curl -i "http://127.0.0.1:8000/universities/1"
```
```
HTTP/1.1 404 Not Found
{"detail":"No university with UNITID 1"}
```
(UNITID `1` isn't a real IPEDS identifier — real ones are 6-digit codes.)

---

## 2. Current database schema

Two tables, one migration chain (`757e5ed4e214` → `898842b69b84`):

```
universities
  unitid                 PK, IPEDS UNITID (not a surrogate key)
  canonical_name, website, city, state, latitude, longitude
  sector                 enum: public / private_nonprofit / private_for_profit / unknown
  highest_degree_level    int   — raw IPEDS HD.HLOFFER code
  highest_degree_label     text  — dictionary label for that code
  carnegie_classification       int   — raw IPEDS HD.C21BASIC code
  carnegie_classification_label  text  — dictionary label for that code
  campus_setting                int   — raw IPEDS HD.C21SZSET code
  campus_setting_label            text  — dictionary label for that code
  masters_granting        bool
  masters_granting_basis   text  — the exact rule used to compute it (see §4)
  degree_granting          bool  (nullable)
  active                   bool
  total_enrollment, graduate_enrollment, international_graduate_enrollment  int (nullable, from EF)
  enrollment_year          int (nullable)
  coverage_tier            enum: INDEXED / PROGRAMS_DISCOVERED / PROGRAMS_VERIFIED / ADMISSION_ENRICHED / FUNDING_ENRICHED / OUTCOME_ENRICHED
  ipeds_year, source_dataset, last_verified_at   — provenance
  created_at, updated_at

university_aliases
  id            PK
  unitid        FK -> universities
  alias         text
  alias_type    enum: ipeds_alias / former_name / common_abbreviation / other
  source        text
  UNIQUE(unitid, alias)
```

### How Carnegie classification is stored

It is **not** a separate data source or importer. The IPEDS `HD` survey
file itself embeds two Carnegie Foundation/ACE classification codes as
columns:

- **`HD.C21BASIC`** → `carnegie_classification` / `carnegie_classification_label`
  — the 2021 Carnegie Basic Classification (33 categories: e.g. "Doctoral
  Universities: Highest Research Activity" — this is what "R1" means in the
  handoff's "R1/R2 are not enough" framing).
- **`HD.C21SZSET`** → `campus_setting` / `campus_setting_label` — the 2021
  Carnegie Size & Setting Classification (18 categories, e.g. "Four-year,
  medium, highly residential"). This is the source for the "Campus
  setting" field listed in `FULL_HANDOFF.md` §5.

Both label sets are hard-coded lookup tables in
`src/us_grad_recommender/importers/ipeds/mappings.py`
(`CARNEGIE_BASIC_LABELS`, `CAMPUS_SETTING_LABELS`), transcribed from the
official IPEDS `HD2023` data dictionary — not reconstructed from memory.

One caveat worth flagging: per the dictionary's own description, Carnegie
classifications are "a time-specific snapshot... based on 2019-20 data,"
republished into each year's HD file. So a HD2023-derived
`carnegie_classification` reflects the 2021 Carnegie update methodology,
not necessarily 2023 conditions — this is noted in a code comment on the
model but is easy to miss when reading query results.

Real examples from the current data:
| Institution | `carnegie_classification_label` |
|---|---|
| The University of Texas at Austin | Doctoral Universities: Highest Research Activity |
| University of Mississippi | Doctoral Universities: Highest Research Activity |
| University of Alaska Fairbanks | Doctoral Universities: Higher Research Activity |
| Alabama A & M University | Master's Colleges & Universities: Larger Programs |

---

## 3. Commits on `main`

| Commit | What it did |
|---|---|
| `3f14c96` | Institution schema (`universities`, `university_aliases`) + idempotent importer for IPEDS `HD` (identity/location/sector/highest-degree/master's-granting/aliases) and `EF` component A (enrollment). Found and fixed a real bug during this: `HD.IALIAS` packs multiple aliases separated by 2+ spaces, not one alias per field. |
| `8ee0926` | Phase 0 infrastructure: `README.md`, `CONTRIBUTING.md`, GitHub Actions CI (lint/typecheck/migrations/tests against a real Postgres service, matrix over Python 3.9 and 3.12), copied the product handoff docs into `docs/`. |
| `ae9edae` | Bumped `actions/checkout` and `actions/setup-python` to clear a Node.js-20-deprecation warning surfaced by the first real CI run. |
| `0d1ebcd` | Added Carnegie Basic Classification and Size & Setting Classification to the institution schema, by extending the existing HD importer (see §2 above) rather than building a new one. |
| `454499a` | Read-only institution search/detail API (FastAPI): `GET /universities` (name/alias search, state/sector/masters_granting filters, pagination) and `GET /universities/{unitid}` (full detail + aliases), plus `/healthz`. |

Every commit was pushed and its GitHub Actions run watched to a real green
before moving to the next one — nothing was merged on the strength of
local checks alone.

---

## 4. Data source and coverage

**Files imported**, downloaded directly from
`https://nces.ed.gov/ipeds/datacenter/data/`:
- `HD2023.zip` → `hd2023.csv` — institutional characteristics
- `EF2023A.zip` → `ef2023a.csv` — fall enrollment, component A

**IPEDS year**: 2023 (the `HD2023`/`EF2023A` release — IPEDS's Fall 2023
data collection, i.e. institutional characteristics and enrollment as
reported for the 2023-24 academic year).

**Why 2,113 institutions, not the full ~6,163 in the HD file**: the
importer defaults to importing only institutions matching a
master's-granting filter (an `--include-all` flag exists to import
everything). The exact filter, applied to real HD2023 data:

```
CYACTIVE = 1   (active in the current IPEDS universe)
AND DEGGRANT = 1   (degree-granting)
AND GROFFER = 1    (offers at least one graduate degree or certificate)
AND HLOFFER >= 7   (highest degree offered is Master's, Post-master's
                     certificate, or Doctor's — i.e. master's or above)
```

Running this filter against the real HD2023 file gives exactly 2,113 rows
— which is why the dev database has 2,113 institutions. It's in the same
ballpark as `FULL_HANDOFF.md`'s rough "~1,931" estimate (different IPEDS
year and not necessarily an identical filter definition — the handoff
itself says that number "must be recalculated... before being treated as
a production fact," which is what this filter does, from real 2023 data).

**Is "2,113 institutions" the same as "2,113 institutions confirmed to
currently grant master's degrees"? No.** This is explicitly an
*offering-capability heuristic* derived from IPEDS's own coded fields, not
a verified count of institutions with an active, currently-enrolling
master's program. Concretely:

- `HLOFFER >= 7` means the institution's **highest** level of offering is
  at least a master's degree — it does not mean every field/department
  there grants master's degrees, just that the institution as a whole
  does at least one.
- None of this is program-level. An institution can pass this filter while
  having zero master's programs in Computer Science, Data Science, or
  Statistics specifically — program-level truth is exactly what Phase 2
  (program/catalog) is for.
- Every row's `masters_granting_basis` field spells out the exact rule
  used, and the code comment in `mappings.py` explicitly says this is "an
  offering-capability heuristic, not a verified count of active master's
  programs" — this phrasing is intentional, per `FULL_HANDOFF.md` §23's
  "never invent... facts" / "avoid false precision" rules.
