# Map-First Recommendation System — Design Proposal (Phase 3)

Status: **approved 2026-09-10, ranking model revised 2026-09-11
(§5.8 — top-20 shortlist replacing the original broad percentile-tier
output; §5.9 — comfortable-fit floor added to answer FULL_HANDOFF.md
§8's minimum-safety-count requirement; §5.4 — geographic preference
reworked from a soft score into a hard candidate-pool filter).** PR #14
(`feature/recommend-wizard-mock-data`, the 4-step wizard + mock
results page) has been **closed**, not reworked — it is superseded by
this design. Implementation proceeds per the phase
breakdown in §16, starting with Phase 3.0.

This document is the required design-before-code artifact for the
product pivot described in chat on 2026-09-10: from a linear
"fill out a form → see a results list" wizard to a persistent,
map-first recommendation dashboard. It answers the 17 sections asked
for, plus the target-user/program-depth model and infra plan worked out
in the same conversation, grounded in what's actually in this repo
today (not assumed).

---

## 0. What changes, what doesn't

**Changes:**
- UI paradigm: wizard-then-results-page → persistent map + left profile
  panel + right detail drawer, all on one screen, updating live.
- Recommendation philosophy: narrow "10 best programs" → a ranked
  **top-20 shortlist** (primary 15 + 5 alternatives, §5.8, revised
  2026-09-11 from an earlier broader/percentile-tiered draft) — still
  far more exploratory than a rigid top-10, but a real shortlist
  rather than a "here are 2,000 schools, go compare them yourself"
  spread. The map still shows the full IPEDS baseline as neutral
  background; only the top 20 are highlighted.
- Score semantics: no admission-probability language anywhere. A
  `match_score` (0–100) + separate `data_confidence` (High/Medium/Low),
  never combined into a single misleading number.
- Program-URL depth: two tiers by field (§9) — a short list of
  high-value fields (JD, LLM, MD, DDS/DMD, CS Master's, CS PhD) get
  deep, program-level official links; everything else gets the
  school's general graduate-admissions entry point. Program *name*
  is still always collected for scoring regardless of tier (§9.2).
- New institution-level fact under investigation: SEVP/I-20
  certification, from an actual DHS source (§8.3) — separate from, and
  must never be conflated with, the existing program-level
  `Program.visa_support_status` (§8 of `PHASE_2_CATALOG_DESIGN.md`).

**Does NOT change** (reused as-is):
- `universities` table and the IPEDS HD/EF importer — already has real
  `latitude`/`longitude` for all 2,113 rows (verified live, §6.1),
  Carnegie classification, sector, enrollment.
- `academic_units` / `programs` / `program_tracks` /
  `admission_requirements` / `program_track_deadlines` schema (Phase
  2.1) — including the cost/funding/visa fields just added in PR #16
  (`ProgramTrack.estimated_annual_cost_usd`, `RequirementType.FUNDING`,
  `Program.credential_status`/`visa_support_status`). These map
  directly onto the detail-drawer "why this school" fields the new
  design asks for (§11) — no rework needed, just population.
- `evidence_sources` / `source_snapshots` / entity-level provenance
  (`verification_status`, `last_verified_at`, `last_seen_snapshot_id`)
  — this *is* the "Verified / Partial / Not yet verified" system the
  new design asks for (§10). Already built, already the right shape.
- `CatalogAdapter` framework, `parser_pipeline.ingest_program_degrees()`,
  `review_queue.py` — all still the path from a real page to a real DB
  row with provenance. Nothing here needs to change to support the map.
- FastAPI backend structure (`api/app.py`, `api/routes.py`,
  `api/schemas.py`) — extended with new endpoints (§6.2), not replaced.

**PR #14 disposition: closed 2026-09-10, per your decision.** Its
`/recommend` wizard UI, `mock-programs.ts`, and step components are a
different information architecture end to end (linear steps vs.
persistent map+panel) and its mock-data approach was already the thing
that got it BLOCKed. Nothing in it survives as UI code. The new work
reuses the same `/recommend` route (decision 2 below).

---

## 1. Proposed user journey

1. User lands on `/recommend` (or a new route — TBD in §13). Map fills
   the viewport, showing all ~2,113 institutions as small, uniform
   neutral-colored dots (§4, §11) — the "baseline universe" from real
   `universities` rows, no recommendation applied yet.
2. Left panel shows a compact profile form: degree level, program
   category (§9.1), program name (§9.2), GPA, background — all
   required, all fast to fill (a few taps/keystrokes, no page
   transitions).
3. As soon as the four required fields are filled, a "Generate
   Recommendations" button activates. Optional fields (test scores,
   budget, region, priorities) are available via progressive
   disclosure ("Add preferences") but never block the first
   recommendation pass.
4. On clicking "Generate Recommendations": map markers re-color into
   the 3-tier system (§11), the left panel swaps from "Profile" to
   "Results" (a scrollable list synced to the map, §16), and the map
   auto-fits bounds to the recommended set.
5. Hover a marker → tooltip (name, city/state, type, Carnegie, category).
   Click a marker or a result-list row → right drawer opens with the
   "why this school" explanation (§11.2), verified facts with status
   badges, and official links (deep or generic per §9).
6. User adjusts any profile/preference field → map, list, and drawer
   (if open) update in place, live, no re-click needed. No restart, no
   step navigation.
7. Mobile: same state machine, profile becomes a bottom sheet, map
   stays primary and full-bleed, detail drawer becomes a bottom sheet
   (§12).

## 2. Page layout / wireframe (text)

```
Desktop (>= 1024px):
┌─────────────┬───────────────────────────────────────┬──────────────┐
│ LEFT PANEL   │              MAP (MapLibre)            │ RIGHT DRAWER │
│ 320–380px    │        flex-1, full height             │ (conditional,│
│              │                                         │  ~380–420px, │
│ [Profile] or │  - legend, bottom-left                 │  slides in   │
│ [Results]    │  - "all schools / recommended only"    │  over map,   │
│ tab state    │    toggle, top-right                   │  not beside  │
│              │  - zoom controls, bottom-right          │  it)         │
└─────────────┴───────────────────────────────────────┴──────────────┘

Mobile (< 1024px):
┌───────────────────────────────────┐
│              MAP                   │  <- full screen, primary
│                                     │
├─────────────────────────────────────┤
│ collapsed bottom sheet (profile     │  <- drag up for full profile
│ summary / result count)             │     form or result list
└─────────────────────────────────────┘
Tapping a marker opens a separate bottom sheet (detail drawer content),
stacked above the profile sheet, dismissible independently.
```

## 3. Component hierarchy

```
RecommendPage (route: TBD §13)
├── RecommendProvider (context: profile state, results, selected school,
│   view mode "all"|"recommended") — client-side state; no server
│   round-trip needed for local UI state like hover/selection
├── LeftPanel
│   ├── ProfileForm (visible when no results yet, or via "Edit profile")
│   │   ├── DegreeLevelSelect
│   │   ├── ProgramCategorySelect (§9.1 — deep-coverage list + General)
│   │   ├── ProgramNameInput (§9.2 — always shown; autofilled+lockable
│   │   │   for deep-coverage categories, free-text for General)
│   │   ├── GpaInput
│   │   ├── BackgroundFields (country, institution, optional strength
│   │   │   bucket — see §9 required-fields note)
│   │   └── PreferencesDisclosure (collapsed by default)
│   │       ├── TestScoresFields (GRE optional-in, TOEFL/IELTS/Duolingo)
│   │       ├── BudgetRangeInput
│   │       ├── RegionMultiSelect
│   │       └── PriorityPicker ("what matters most" chips, §5.7)
│   └── ResultsList (visible after first recommendation pass)
│       └── ResultRow × N (university, program, category badge, short
│           reason, cost indicator, verification badge)
├── MapView
│   ├── MapLibreMap (react wrapper around maplibre-gl, §4)
│   ├── InstitutionMarkerLayer (GeoJSON source; neutral vs. tiered
│   │   styling driven by a `category` property per feature, §11)
│   ├── ClusterLayer (zoomed-out clustering, native MapLibre
│   │   `cluster: true` on the GeoJSON source — no extra library)
│   ├── MapLegend
│   ├── ViewToggle ("All schools" / "Recommended only")
│   └── MapTooltip (hover)
└── DetailDrawer (conditional)
    ├── WhyThisSchool (§11.2 — checklist of match reasons)
    ├── FactList (institution/program/degree/location/cost/GRE/
    │   English/funding/visa — each row carries a verification badge,
    │   §10)
    └── OfficialLinksList (tiered per §9 — deep links or generic
        grad-admissions link, each with its own provenance)
```

## 4. Map technology recommendation

**Explicit distinction, restated per your note: MapLibre GL JS is a
rendering library, not a hosted map/tile service.** Choosing MapLibre
answers "what draws the map in the browser," not "where do the map
tiles come from" — those are two separate decisions, and §4 below
answers both explicitly rather than treating "we use MapLibre" as if
it implied free tiles came with it.

**Rendering library: MapLibre GL JS**, not Google Maps or Mapbox GL — confirmed as the
right call for the reasons already laid out in the conversation:
open-source (BSD-2), API-compatible enough with Mapbox GL that most
GL-style docs/examples transfer directly, and critically: **no
per-load/per-tile billing risk.** Google Maps JS API and Mapbox GL both
meter map loads; MapLibre has no metering because there's no vendor
behind it charging for the library itself — cost lives entirely in
*tile hosting*, which we control.

**Tiles: start with a free public vector basemap, defer
self-hosting.** Two real options, in order of effort:
1. **Now (MVP):** a free-tier vector tile source compatible with
   MapLibre's style spec — e.g. MapTiler's free tier (100k tile loads/
   month) or OpenFreeMap (genuinely free, no key, no request cap as of
   this writing — verify current terms before committing). Either
   works as a drop-in `style.json` URL; zero infrastructure to stand
   up.
2. **Later, if traffic justifies it:** self-hosted PMTiles (Protomaps
   format) on object storage (Cloudflare R2 or Supabase Storage),
   served directly to the browser via HTTP range requests — no tile
   server process needed at all, genuinely near-zero marginal cost.
   This is the right move once free-tier limits become a real
   constraint, not before — don't build tile infrastructure for a
   product with no users yet.

**Markers, not raster tiles, for institutions.** All 2,113 (or a
filtered subset) institution points render as a MapLibre GeoJSON
source with a symbol/circle layer — not individual DOM markers (which
don't scale past a few hundred) and not server-rendered tiles (way
more infrastructure than 2,000 points need). Native `cluster: true`
handles zoomed-out aggregation with no extra library.

## 5. Recommendation scoring design

### 5.0 Non-negotiable framing (locked in 2026-09-10, before any code)

**`match_score` is never admission probability, and must never be
interpreted as one internally either** — not just a copy/labeling
issue. A GPA of 3.6 does not, by itself, imply "30% at Stanford, 75% at
UB" or anything resembling a calibrated probability. The score is
purely "how well does this institution/program match what the student
asked for," computed from stated profile + preferences vs. known
institution/program facts. No admission-outcome data (historical
acceptance rates, yield, etc.) is an input to v1 at all — there's
nothing in the model that *could* produce a probability-shaped number
even if we wanted one. `match_score` and `data_confidence` are two
independent output fields, never collapsed into one number:

```
Match Score: 84       (how well it fits — a match/relevance score)
Data Confidence: Medium (how much verified data backs that judgment)
```

### 5.1 Deterministic v1 model — not ML, and not LLM-ranked

```
overall_score =
    ( Σ over ACTIVE components: w_i * fit_i )
  / ( Σ over ACTIVE components: w_i )
```

i.e. a weighted average **renormalized over only the components that
actually apply to this request** — see §5.4 for exactly what "active"
means. `overall_score ∈ [0, 100]`.

- Weights (`w_*`) come from the user's priority selection (§5.7) — a
  small number of named presets (e.g. "Ranking-first" skews
  `w_reputation`/`w_academic` up; "Affordability-first" skews `w_cost`
  up; "Admission-fit-first" skews `w_academic` up and dampens
  `w_reputation`) rather than free-form sliders for v1, per the
  "doesn't have to be complicated sliders at first" guidance. A
  "Customize priorities" escape hatch can expose raw weight sliders
  later (§14 — deferred, not MVP).
- Ranking is 100% deterministic and testable — no ML, no LLM in the
  scoring path. An LLM may eventually help *explain* a result in
  natural language, but never determines or adjusts the score itself
  (locked in explicitly, not just a v1-convenience default). Every sort
  in the ranking pipeline uses an explicit tie-break (`unitid`
  ascending, after `match_score` descending) — with today's sparse
  program data, many institutions collapse to an identical score, and
  without a defined secondary key, which ones land in the top 20 would
  depend on unspecified database row order rather than being
  reproducible across calls.
- Every response includes both the aggregate score/confidence *and*
  the per-component breakdown (`academic_fit`, `cost_fit`, etc.),
  plus structured explanation lists — see §5.5's full response shape.
  This is what powers the "why this school" checklist (§11.2).
- v1 is **not blocked on complete GRE/tuition/funding/SEVP/program
  data.** It must work meaningfully today, against a database where
  most institutions have zero Phase-2 program rows yet, and get more
  precise as Phase 3.2/3.4 populate more facts — that's a design
  requirement, not an aspiration.

### 5.2 Two distinct kinds of "missing," handled differently

This distinction is the most important correctness rule in the whole
model — conflating them is exactly the "optional preference secretly
penalizes the user" bug to avoid:

**(a) User didn't provide an optional preference** (budget, region,
ranking/reputation weighting, school-type preference) → **that
component is excluded from the denominator entirely, not scored as 0.**
It does not appear in either the numerator or denominator sum in
§5.1's formula, so it has literally no effect on `overall_score` — not
a small effect, none. Example: no budget provided → `cost_fit` is
`null` in the response and contributes nothing to the average; the
remaining active components (say academic/reputation/program) are
reweighted to sum to 1 on their own.

**(b) The user provided (or the field is required, like GPA/program),
but the institution/program-side fact is unverified or missing** →
that component **stays active** (the user did ask this question, we
just don't have a confident answer), uses a neutral fallback value,
and **lowers `data_confidence`**, not `match_score` directly beyond
the fallback's own neutrality. Example: student provides GPA, but the
matched program's `min_gpa` is null → `academic_fit` uses a neutral
midpoint (e.g. 60, not 0 and not 100) and the response marks that
specific fact as unverified, which factors into the overall
`data_confidence` bucket (§5.6).

**Never conflate these.** "User didn't ask about location" and
"we don't know if this university is in a good location" are different
facts and must never collapse into the same score effect.

### 5.3 Program availability is tracked separately from program_fit

**Institution existing on the map ≠ the requested program existing at
that institution ≠ we've verified its requirements.** Three different,
independently-true-or-false facts. `program_availability` is returned
as its own explicit tri-state field, never silently folded into
`program_fit` alone:

- `CONFIRMED` — a real `Program` row exists at this university that
  matches the requested category/name (via `Program.canonical_name`/
  `ProgramAlias`, scoped by `DegreeType.level` for the requested degree
  level).
- `PARTIAL` — no specific `Program` match, but plausible circumstantial
  evidence exists (e.g. a relevant `AcademicUnit` — a CS department —
  is on record at this university, or the university's
  `highest_degree_label`/`masters_granting` flag indicates
  graduate-level offerings in general) — i.e., "probably, unconfirmed,"
  never presented as equivalent to `CONFIRMED`.
- `UNKNOWN` — no program-level data exists for this university at all
  (the realistic default for the large majority of the 2,113
  institutions today, since only a handful of pilot schools have any
  Phase-2 catalog data yet). **This is expected, honest v1 behavior,
  not a bug** — the institution still appears on the map and in
  results; it is never presented as if the program were confirmed.

`program_fit` (the numeric component) is influenced by this tri-state
(`CONFIRMED` scores higher than `PARTIAL` scores higher than
`UNKNOWN`'s neutral-low fallback) but `program_availability` itself is
always surfaced as its own field so the frontend/copy never has to
reverse-engineer "was this actually confirmed?" from a single number.

### 5.4 What's active by default vs. only when provided

| Component | Active when |
|---|---|
| `academic_fit` | always (GPA is required input) |
| `program_fit` | always (program category/name is required input) |
| `reputation_fit` | always (Carnegie/institution-type data exists for essentially every row; falls back neutrally per §5.2(b) on the rare null) |
| `cost_fit` | only if the user provided a budget |

**Geographic preference is not a scoring component at all — revised
2026-09-11.** The original design treated `preferred_states` like the
other optional preferences (excluded from the denominator when unset,
soft-scored when set, via a `location_fit` component). Real-world
counterexample that changed this: a student who says *"I only want
schools in New York and California"* means exactly that — a school
outside those states must never appear in the shortlist, no matter how
well it scores on every other axis. A soft `location_fit` bonus would
let a high-scoring out-of-state school back in, directly contradicting
a stated hard requirement. So:

- `preferred_states` set → the candidate pool is hard-filtered to those
  states **before** scoring/ranking even begins (`recommend()`,
  `_geography_eligible()`). An institution with no recorded state is
  excluded too when a preference is stated — state is essentially
  always populated in this dataset (real IPEDS data), so this hard,
  explicitly-stated requirement errs toward strictness rather than the
  softer §5.2(b) tolerance used for genuinely sparse program-level
  facts.
- `preferred_states` unset → nationwide, unrestricted, and still no
  location-based scoring (there's no stated preference to score
  against).
- There is no `location_fit` component in either case — it would be
  either redundant (true for every remaining candidate post-filter) or
  actively wrong (letting an excluded school's high score buy it back
  in). Budget remains a *soft* preference (§5.2), deliberately not
  filtered the same way, since a school slightly over budget is a much
  more continuous, less binary judgment than being in the wrong state
  entirely.

### 5.5 Full response shape per scored institution

Structured explanation is first-class backend output — the frontend
must never reverse-engineer *why* a recommendation happened from a
bare number:

```json
{
  "unitid": 12345,
  "program_id": 678,
  "rank": 6,
  "match_score": 84,
  "data_confidence": "medium",
  "category": "good_fit",
  "is_primary_shortlist": true,
  "is_comfortable_fit": true,
  "program_availability": "confirmed",
  "component_scores": {
    "academic_fit": 78,
    "cost_fit": null,
    "reputation_fit": 65,
    "program_fit": 88
  },
  "positive_reasons": [
    "Has the requested CS graduate program"
  ],
  "warnings": [
    "GRE information not verified"
  ],
  "unknown_facts": [
    "Tuition not yet verified"
  ]
}
```
`component_scores` entries are `null` (not `0`) when excluded per
§5.2(a) — the frontend renders `null` components as simply absent from
the "why" checklist, not as a negative signal.

### 5.6 `data_confidence`

Computed independently from `match_score`: over the components that
are *active* (§5.4) for this request, what fraction are backed by real
verified/parsed data (`VerificationStatus` in `{USER_CONFIRMED,
DOCUMENT_VERIFIED, PARSED}`) vs. a §5.2(b) neutral fallback (`RAW` or
no row at all)? Reuses the existing `VerificationStatus` enum
(`common.py`) already on every catalog row — no new provenance concept.
Bucketed to High/Medium/Low for display.

**Never surface `match_score` as an admission probability anywhere** —
not in API field names, not in frontend copy, not in log/debug output.
`match_score` and `category`, never `admission_probability`.

### 5.7 Priority presets (v1)

| Preset | Effect (illustrative, exact weights tuned during implementation) |
|---|---|
| Ranking / reputation | ↑ `w_reputation`, ↑ `w_academic` |
| Affordability | ↑ `w_cost` |
| Admission Fit | ↑ `w_academic`, ↓ `w_reputation` — **naming note**: this weights how closely the student's academic profile matches the program's stated requirements more heavily; it does not compute or imply an admission probability (§5.0) |
| Balanced (default) | equal weights |

### 5.8 Top-20 shortlist, not a percentile spread (revised 2026-09-11)

**Superseded the original score-threshold categories** (`strong_match`/
`target`/`reach`/`insufficient_data` applied across a broad 20–50-result
set) after review: if the product's actual promise is "a shortlist
worth applying to," painting 2,000+ map markers into four buckets
undercuts that promise more than it serves it — most real institutions
land in a narrow score band anyway given how sparse verified program
data still is (confirmed empirically against the dev DB during PR #17:
2,018 of 2,113 landed as `target`, one bucket, with no real
differentiation). A cleaner shortlist gives a stronger, more honest
recommendation feel than a mostly-flat four-way split.

**New model:**
1. Rank all degree-level-eligible institutions by `match_score`
   (unchanged scoring/ranking logic from §5.1–§5.7).
2. Return the **top 20 only** — everything beyond rank 20 is not part
   of the recommendation response at all (it still exists on the map
   as a neutral background marker via `GET /universities/map`, §6.3 —
   this endpoint is untouched, still returns the full baseline
   universe).
3. Within that top 20, assign category **by rank position**, not by a
   score/confidence threshold:
   - `top_fit`: rank 1–5
   - `good_fit`: rank 6–12
   - `explore`: rank 13–20
4. Separately, `is_primary_shortlist` is `true` for rank 1–15 and
   `false` for rank 16–20 — this drives the frontend's default
   "Recommended shortlist: 15 programs" + "+5 alternatives" framing
   (§13), independent of the 3-tier color/label above (rank 13–15 is
   simultaneously `explore`-tier *and* part of the primary shortlist;
   rank 16–20 is `explore`-tier and an alternative — both facts are
   exposed, neither is hidden).

**`data_confidence` is unchanged and still shown per result** — a
result's rank/tier position is about how it compares to other
candidates, not a claim about how well-verified its facts are. A
`top_fit` result can still carry Low confidence, and the frontend must
still show that plainly (§10, §11.2) — dropping the `insufficient_data`
*category* does not relax the underlying honesty rule, it just moves
where that signal lives (a per-result confidence badge, not a bucket
name that risked being misread as an admission-difficulty judgment —
the same reasoning that ruled out `strong_match`/`target`/`reach` in
the first place, restated more strongly this round: the new label set
(`top_fit`/`good_fit`/`explore`) was deliberately chosen to read as
"how well it matches what you asked for," never as "how hard it is to
get in").

### 5.9 Comfortable-fit floor (added 2026-09-11)

`FULL_HANDOFF.md` §1/§8 are amended (2026-09-11) with pointers back to
this section, so the two documents don't silently disagree — §8's full
portfolio model is not superseded, just not yet built; this section is
the honest v1 partial answer.

**Why this exists:** `FULL_HANDOFF.md` §8 ("Recommendation Portfolio")
mandates constrained portfolio optimization — reach/target/safety
quotas, a minimum safety count, diversity, avoiding correlated failure
risk — and explicitly forbids "simply select the top N independent
scores." A pure top-20-by-`match_score` ranking (§5.8 as first
implemented) is exactly that forbidden pattern. §8's own
reach/target/safety buckets are themselves admission-probability
ranges (10–35% / 35–70% / >70%), which directly conflicts with §5.0's
no-admission-probability rule — that conflict is resolved by this
section using only real data already in the schema, not by resurrecting
probability language.

**Definition — "comfortable fit," not "safety":** an institution/program
is comfortable-fit if and only if its `academic_fit` component is
`>= 75` (the highest defined bucket — GPA is 0.3+ above the stated
minimum) **and** that comparison rests on a *strictly* verified
`ProgramTrack.min_gpa`. "Strictly" matters here and is worth being
explicit about, since §5.6 uses "verified" more loosely elsewhere in
this same document: the floor requires `VerificationStatus` in
`{USER_CONFIRMED, DOCUMENT_VERIFIED}` only — **not** `PARSED`, even
though `PARSED` is loose enough to count toward the general
`data_confidence` bucketing in §5.6. `PHASE_2_CATALOG_DESIGN.md` §10 is
explicit that `PARSED` means an automated, human-*unreviewed*
extraction ("no auto-promotion allowlist... every automated
extraction... goes through `data_review_tasks` before it can reach
`user_confirmed`/`document_verified`") — not a strong enough basis for
a "comfortably-verified" *safety* claim specifically, even though it's
fine as one signal among several for a general confidence bucket. This
is a statement about "your GPA comfortably clears a real, reviewed
requirement" — it says nothing about competition, applicant volume, or
actual admission odds, and is exposed as its own field
(`is_comfortable_fit: bool`), never folded silently into `match_score`.

**The floor:** at least `MIN_COMFORTABLE_FIT_COUNT` (3, reusing §8's own
Balanced-portfolio safety count rather than inventing a new number)
comfortable-fit results must appear in the top 20. If the naive
top-20-by-score already has 3+, nothing changes. Otherwise, the
highest-`match_score` comfortable-fit candidates *outside* the naive
top 20 are swapped in, displacing only the **lowest-ranked
non-comfortable** entries already there (rank 1 is never displaced).
If fewer than 3 comfortable-fit candidates exist in the whole eligible
pool, the floor includes as many as actually exist — it never
fabricates comfortable options that aren't real.

**Explainability:** every swapped-in entry gets an explicit line
appended to its own `positive_reasons` (e.g. *"Included to ensure your
shortlist has comfortably-verified options"*) — never a silent reorder
the user has to infer.

**What this does *not* cover, on purpose:** diversity across
institutions/funding mechanisms, and avoiding correlated failure risk
(§8's other portfolio requirements) are **explicitly deferred**, not
built here. A geography-based diversity cap was considered and
rejected: if a student states a geographic preference at all (§5.4),
it's a hard filter already — e.g. a student who genuinely wants
California-only should get every good California match, not have some
arbitrarily removed by a "max N per state" rule fighting their actual
stated intent. True funding-mechanism diversity and single-point-of-
failure detection (e.g. a program depending on one professor) need
program/funding-level data that exists as schema (`admission_requirements`
`FUNDING` type, PR #16) but is still unpopulated — building a diversity
rule on top of data we don't have yet would be exactly the kind of
false precision this whole design has tried to avoid. Revisit once
Phase 2.3/3.4 populate real funding facts.

## 6. Institution/program data model changes

### 6.1 What already exists (verified live against the dev DB, not assumed)

- `universities.latitude`/`longitude`: **populated for all 2,113
  rows**, sourced directly from IPEDS `HD.LATITUDE`/`HD.LONGITUD`
  (`hd_importer.py:188-189`). No enrichment work needed for the map's
  core requirement.
- Carnegie classification, sector, masters-granting flag, enrollment:
  already on `University`.
- Program-level cost/funding/visa fields: already on
  `Program`/`ProgramTrack` as of PR #16 (this session) — schema exists,
  population is the pilot's job (unchanged from before this proposal).

### 6.2 New, additive schema needed

1. **`University.sevp_certified` / `sevp_certified_as_of` /
   `sevp_source_url`** (nullable) — institution-level I-20/SEVP
   certification flag, sourced from the real DHS Study in the States
   "Download Certified School List" (studyinthestates.dhs.gov/school-search
   — confirmed to exist as a real, official, downloadable dataset;
   exact file format/fields not yet inspected, see §8.3). **This is
   institution-level only and must never be used as, or displayed as, a
   proxy for `Program.visa_support_status`** — `PHASE_2_CATALOG_DESIGN.md`
   §8 already establishes this exact rule ("University-level I-20
   capability must never be used as a proxy for program- or
   track-level eligibility") for a good reason: an SEVP-certified
   university can still have individual online-only programs that
   don't support F-1/I-20. Per the confirmed baseline-universe decision
   above, this field drives an **optional "F-1 / I-20 eligible" filter
   layered on top of the full IPEDS baseline map** — it never
   restricts which institutions appear on the map, and it is not
   available until Phase 3.2 actually populates it. The detail drawer
   must keep showing `Program.visa_support_status` as its own,
   separately provenanced fact, defaulting to "not yet verified"
   independent of the university-level flag.
2. **A recommendation-request/response shape** — not new persisted
   tables, just new Pydantic schemas in `api/schemas.py` for the
   profile payload and the scored-institution response (§6.3). No DB
   table needed for v1 since scoring is computed on read, not stored;
   revisit only if caching/analytics needs a persisted recommendation
   log later (explicitly deferred, §14).
3. **`ProgramCategory` reference table or enum** for the eight
   deep-coverage categories (§9.1) plus `GENERAL` — used to decide link
   tier (§9.3) and to help `program_fit` scoring recognize a known
   category vs. a free-text `General` program name. Small, static,
   lookup-table style like `DegreeType` (`catalog.py`), not a new
   subsystem.

### 6.3 New API endpoints (additive, existing `routes.py` extended)

- `GET /universities/map` — lightweight bulk endpoint returning
  `{unitid, canonical_name, city, state, latitude, longitude, sector,
  carnegie_classification}` for the baseline map layer (Phase 3.0
  fields only — `sevp_certified` is added to this response in Phase
  3.2 once it exists, not before). Deliberately excludes the heavier
  `UniversityDetail` fields. Returns pre-shaped GeoJSON
  (`FeatureCollection`) directly, matching MapLibre's native input
  format and avoiding a client-side transform step.
- `POST /recommendations` — takes the profile payload, returns a list
  of scored institutions in the full shape specified in §5.5
  (`match_score`, `data_confidence`, `category`, `program_availability`,
  `component_scores`, `positive_reasons`/`warnings`/`unknown_facts`),
  computed live against `programs`/`program_tracks`/
  `admission_requirements`. Read-only, stateless, no new table.
- `GET /programs/{id}/links` — resolves the tiered official-link set
  (§9.3) for a given program: deep-coverage categories return
  program/admissions/requirements/tuition/funding/international-office
  links where present; `GENERAL`-category programs return the
  institution's graduate-admissions entry point.

## 7. Existing backend pieces reused as-is

Explicitly, so nothing here gets rebuilt by accident:
- IPEDS HD/EF importer and CLI (`import-ipeds`) — untouched.
- `CatalogAdapter` protocol, `CourseLeafAdapter`, `PdfCatalogAdapter`.
- `parser_pipeline.ingest_program_degrees()`.
- `review_queue.py` (create/list/resolve review tasks and conflicts).
- `evidence_sources`/`source_snapshots`/provenance columns across every
  catalog table.
- `Program`/`ProgramTrack`/`AdmissionRequirement` schema including the
  cost/funding/visa fields from PR #16.
- FastAPI app structure, existing `/universities` search/detail
  endpoints (kept as-is for the existing `/universities/[unitid]` page,
  which is orthogonal to this redesign and doesn't need to change).

## 8. Data-source plan

### 8.1 Institution baseline (already solved)
IPEDS HD (already imported, 2,113 institutions, real coordinates) is
the baseline universe. No new source needed here.

### 8.2 Program-level facts (unchanged from existing roadmap)
`CatalogAdapter` framework + `parser_pipeline` + human review queue,
per `PHASE_2_CATALOG_DESIGN.md` — this proposal doesn't change that
plan, it changes what consumes the output (map instead of a wizard
results page).

### 8.3 SEVP/I-20 certification — investigated, not yet integrated
Confirmed via web search: DHS's **Study in the States**
(studyinthestates.dhs.gov/school-search) is the real, official SEVP
school-search tool and explicitly offers a "Download Certified School
List" export — this is a legitimate, authoritative, non-scraped data
source (see chat sources below). What's **not yet confirmed** (needs
actual inspection during implementation, not assumed here): the exact
export format/field names, update cadence, and whether it's
keyed/matchable to IPEDS UNITID directly or needs name/address
fuzzy-matching (like the existing alias-matching pattern already used
for IPEDS name variants). **This is real, unfabricated groundwork
still needed before `sevp_certified` can be populated — flagged as
Phase 3.2 work (§15), not assumed done.**

Sources consulted: [Study in the States — School Search](https://studyinthestates.dhs.gov/school-search), [ICE SEVP](https://www.ice.gov/sevis/schools).

### 8.4 Rankings — explicitly not a foundation
No US News or other ranking data is scraped, licensed, or fabricated.
`reputation_fit` (§5.1) is computed from Carnegie classification +
research-intensity signals + institution type already in `universities`,
consistent with the existing project rule (`FULL_HANDOFF.md` §0/§23).
Ranking data remains an explicitly optional, later enrichment layer —
not built in this phase.

### 8.5 College Scorecard — noted, not adopted for v1
Mentioned as a possible source in the original ask. Not needed for
v1: IPEDS already covers the institution-level baseline this design
needs, and Scorecard's main added value (cost/outcomes data) overlaps
with what the existing `PHASE_2_CATALOG_DESIGN.md` pipeline is already
scoped to collect with proper program-level provenance. Revisit only
if a specific gap shows up that IPEDS/the existing pipeline can't fill.

## 9. Target user / program-depth model

### 9.1 Two-tier program category system

**Deep-coverage categories** (get program-level official links —
program homepage, admissions, requirements, tuition, funding,
international-office pages, each independently provenanced):

| Category | Notes |
|---|---|
| JD | Juris Doctor |
| LLM | frequently the international-student entry point to US law |
| MD | |
| DDS / DMD | dentistry |
| CS Master's | |
| CS PhD | |

**BSN/ABSN deferred, not built (added 2026-09-11).** Both were
originally scoped in (ABSN specifically to cover the "career-changer
into nursing" segment named in the target-user description), but
review caught them mapped to `DegreeLevel.MASTERS` — wrong, since BSN
(and its accelerated ABSN variant) are bachelor's-level credentials,
and the schema's `DegreeLevel` enum has no `BACHELORS` value at all.
Adding one is a real migration (same shape as `RequirementType.FUNDING`
in PR #16), which doesn't belong in a routine, schema-free PR under the
current self-merge policy; shipping a known-wrong mapping instead
isn't acceptable either. **Follow-up, not scoped to a specific PR yet:**
add `DegreeLevel.BACHELORS` via its own migration PR, then reinstate
`ProgramCategory.BSN`/`ABSN` in `recommendation.py`.

**General / Other:** everything else. Gets the institution's graduate
school admissions entry point, not a program-specific deep link.

Rationale (already agreed in chat, restated for the record): these
eight categories are where (a) the application process is commonly
run by a separate school/office rather than the central graduate
admissions office, and (b) this product's actual target users
(mainland-Chinese-undergrad applicants, plus the career-changer-into-
nursing segment) cluster most heavily. Building deep per-program
scraping/adapters for every possible field is not worth the cost;
these eight are.

### 9.2 Program name is always collected, regardless of tier

Confirmed in chat: even when the user picks `General`, a free-text
program-name field (e.g. "Psychology," "Public Health") is still
required input — it feeds `program_fit`/`academic_fit` scoring
regardless of link tier. Link depth and scoring input are independent:
a General-category pick never degrades match quality, only link
specificity.

- Deep-coverage pick → program name is pre-filled from the category
  (e.g. picking "CS Master's" implies "Computer Science," with room
  for a sub-specialization like Data Science) and confirmable/editable.
- `General` pick → free-text/searchable input, required.

### 9.3 Link tier is independent of scoring

| | Deep-coverage category | General category |
|---|---|---|
| Scoring input (`program_fit`) | program name (implied by category) | program name (free text) |
| Official links shown | program site, admissions, requirements, tuition, funding, international-office — each a separate provenanced fact | graduate-admissions entry point only |

## 10. Handling missing/uncertain data

Directly reuses the existing `VerificationStatus` enum
(`RAW`/`PARSED`/`NEEDS_REVIEW`/`USER_CONFIRMED`/`DOCUMENT_VERIFIED`/
`REJECTED_AS_INVALID`) already on every catalog row — no new concept
needed, just consistent surfacing in the UI:

- Map/list: a school is never hidden or excluded from the baseline map
  for having unverified fields. The top-20 shortlist (§5.8) is a
  ranking cutoff, not a data-quality exclusion — a result can rank in
  the top 20 with Low `data_confidence`, and the UI must still show
  that confidence plainly rather than implying the ranking itself is
  equally trustworthy everywhere.
- Drawer: every fact renders with a status badge derived from its
  row's `verification_status`. Collapse the six-value enum to three
  user-facing labels for the badge (internal value kept for
  filtering/scoring):
  - `Verified` ← `USER_CONFIRMED` or `DOCUMENT_VERIFIED`
  - `Reported, not yet verified` ← `RAW` or `PARSED`
  - `Not yet available` ← no row exists for that fact at all
- **"Unknown" copy must never read as "no."** E.g. GRE with no
  `admission_requirements` row renders as "GRE policy: not yet
  verified" — never "GRE not required" and never silently omitted.
  This is a copy-review item for implementation, not just a data rule.

## 11. Color/category system

### 11.1 Marker states

| State | When | Visual treatment (exact tokens TBD in implementation, `dataviz` skill governs the actual palette) |
|---|---|---|
| Neutral (background) | any institution not in the top 20 (§5.8) — the large majority of the map at all times | small, low-saturation neutral dot, unchanged before/after "Generate Recommendations" |
| Top Fit | `category == top_fit` (rank 1–5) | most prominent tier color, largest/boldest marker |
| Good Fit | `category == good_fit` (rank 6–12) | second tier color |
| Explore | `category == explore` (rank 13–20) | third tier color |
| Hover | any | subtle elevation/halo, tooltip appears |
| Selected | clicked, or corresponding result-list row hovered/clicked | strongest visual emphasis, drawer opens |

Every top-20 marker (regardless of tier) still carries its own
`data_confidence` — surfaced via the tooltip/drawer, not a 4th marker
color, per §10's point above.

Three semantic tiers (`top_fit`/`good_fit`/`explore`) plus one shared
neutral background state, not a rainbow palette, per the explicit
"colors must have semantic meaning" requirement. Deliberately named to
read as "how well it matches what you asked for," never as "how hard
it is to get in" — the same concern that ruled out admission-adjacent
naming throughout §5. Exact hex values are an implementation-time
decision, to be built following this repo's `dataviz` skill (palette
validator, light/dark handling) rather than picked ad hoc here.

### 11.2 "Why this school" — detail drawer content

Directly from `component_scores` (§5.1) plus fact-level verification
status (§10):
```
Why it matches you
✓ GPA is within a plausible range          (academic_fit component high, GPA verified)
✓ Offers an MS in Computer Science          (program exists, verified)
✓ Tuition is within your selected budget    (cost_fit component high, cost verified)
△ GRE policy not yet verified               (component used neutral fallback, §5.1)
```
(No "located in your preferred region" line — geography is a hard
filter now, §5.4: every result the user sees already satisfies it, so
restating it on every card would be constant, undifferentiating noise.)
Checkmarks (✓) only for verified-and-favorable components;
triangles (△) for anything driven by a fallback/unverified value —
this is the concrete mechanism that keeps the confidence system honest
in the UI, not just in the API response.

## 12. Desktop and mobile interaction behavior

Desktop: as in §2. Left panel and map both always visible; drawer
overlays the map's right edge rather than pushing it, so the map never
resizes/reflows when a school is selected.

Mobile (< 1024px breakpoint, matching the existing Tailwind v4 setup
already in `web/`):
- Map is full-bleed, always the primary surface.
- Profile/results panel collapses to a bottom sheet (peek height shows
  a one-line summary + result count; drag up for the full form/list).
- Detail drawer becomes its own bottom sheet, stacked above the
  profile sheet, independently dismissible (matching the explicit
  instruction not to shrink the desktop sidebar into an unusable
  column).
- All interactions (hover states) degrade to tap-only; no
  hover-dependent information should be mobile-inaccessible — the
  tooltip content must also be reachable via tap→drawer.

## 13. MVP scope

**In scope for v1:**
- Map with all 2,113 institutions as neutral markers, real coordinates,
  clustering at low zoom.
- Left panel: required profile fields (degree level, program category,
  program name, GPA, background) + the four preset priority chips
  (§5.7). Optional fields present but genuinely optional.
- `POST /recommendations` computing the v1 deterministic score and
  returning the ranked top 20 (§5.8): primary shortlist (rank 1–15) +
  alternatives (rank 16–20).
- 3-tier rank-based color system (`top_fit`/`good_fit`/`explore`) on
  the map, synced with a results list (§16); everything outside the
  top 20 stays neutral background.
- Detail drawer: why-this-school checklist, fact list with
  verification badges, and tiered official links (§9) — populated only
  where the existing schema already has data (i.e., can legitimately be
  empty/mostly-"not yet verified" for most schools at launch; that's
  expected and honest, not a bug).
- Mobile bottom-sheet layout.

**Resolved implementation details** (see Decisions section at the end):
route is `/recommend`; first recommendation pass is triggered by an
explicit "Generate Recommendations" button, with live updates on
subsequent filter/preference changes; no auth/session/saved-search in
v1; baseline map is the full IPEDS universe, not R1/R2-restricted.

## 14. Explicitly deferred scope

- Minor follow-ups noted during PR #17 review, non-blocking (correctness
  unaffected either way): `ScoredInstitutionOut.rank`'s `le=20` bound
  (api/schemas.py) is a duplicated literal of `recommendation.TOP_N`
  rather than deriving from it — would silently drift if `TOP_N` is ever
  changed without a matching schema edit; and §6.3 below lists
  `GET /programs/{id}/links` as if it were Phase 3.0 scope, while §16's
  phase breakdown (accurately) doesn't include it — wording only, worth
  tightening later.
- ML-based scoring (v1 is deterministic, per explicit instruction).
- Persisted recommendation history / saved searches / accounts.
- Raw weight-slider priority customization (v1 ships presets only).
- Self-hosted PMTiles/Protomaps tile infrastructure (v1 uses a free
  hosted vector tile source, §4).
- Full `annual_in_study_out_of_pocket` cost decomposition
  (tuition/fees/insurance/living cost minus waiver/stipend, per
  `FULL_HANDOFF.md` §7) — v1 keeps PR #16's single combined
  `estimated_annual_cost_usd` figure. This is the same gap PR #16's own
  review flagged as OPTIONAL/non-blocking; decomposing it is real
  future work, not silently dropped.
- Rankings as a scoring input.
- `ProgramCategory.BSN`/`ABSN` (added 2026-09-11, see §9.1) — needs
  `DegreeLevel.BACHELORS`, which doesn't exist yet and requires its own
  migration PR.
- No further baseline-universe expansion planned: confirmed the full
  IPEDS set (liberal arts colleges included, since IPEDS already
  covers them) is the v1 baseline — nothing to add here.
- SEVP data integration beyond a first institution-level pass (§8.3) —
  exact file inspection and matching logic is real work, scoped to
  Phase 3.2 (§15), not MVP.

## 15. Migration requirements

One additive Alembic migration, same pattern as PR #16:
`University.sevp_certified` (`Boolean`, nullable, default `NULL` = not
yet checked — deliberately not defaulting to `False`, since `False`
would misleadingly assert "confirmed not certified" rather than
"unknown," per §10's unknown-≠-no rule) +
`sevp_certified_as_of`/`sevp_source_url`. No changes to existing
tables' constraints; no data backfill required at migration time
(population is separate ingestion work, §8.3). `ProgramCategory`
lookup table/enum (§6.2.3) — small additive table, same style as
`DegreeType`.

## 16. Implementation phases

1. **Phase 3.0 — Backend scoring + map data endpoint.**
   `GET /universities/map`, `POST /recommendations` with the v1
   deterministic model against existing schema (no SEVP dependency).
   Testable in isolation with existing test-fixture data; no frontend
   needed yet to validate scoring logic.
2. **Phase 3.1 — Map + panel frontend, backend-driven.**
   MapLibre integration, left panel, results list, detail drawer,
   consuming Phase 3.0's endpoints. This is the bulk of the visible
   product.
3. **Phase 3.2 — SEVP data integration.**
   Actually fetch/inspect the DHS Study in the States export, design
   the real ingestion (matching to UNITID, provenance), migrate
   `sevp_certified`, wire into the map's baseline layer and legend.
   Explicitly gated on real data inspection, not started blind.
4. **Phase 3.3 — Mobile layout.**
   Bottom-sheet behavior, touch interaction polish.
5. **Phase 3.4 (ongoing, overlaps with existing Phase 2.3 pilot) —
   Program-level fact population.** Unchanged from the existing
   roadmap: pick pilot schools, run adapters, populate the already-built
   cost/funding/visa/GPA/GRE fields that the drawer already knows how
   to render.

## 17. Testing strategy

- Backend: scoring function is pure/deterministic → straightforward
  unit tests per component (`academic_fit`, `cost_fit`, etc.) with
  hand-built fixture rows covering verified, unverified, and missing
  data per field, following the existing `tests/` pattern (real
  Postgres-backed, transactional isolation, no mocking).
- `GET /universities/map`: assert GeoJSON shape, assert count matches
  DB row count, assert every feature has non-null coordinates (already
  true today, but worth a regression test given how much the map
  depends on it).
- Frontend: component tests for marker color-state mapping (given a
  `category`, does the right visual state render) and for the
  why-this-school checklist (given `component_scores`, does the
  right ✓/△ set render) — pure function tests, no live map needed.
- No visual/E2E map testing in CI (matches this session's precedent
  of using a real local Chrome browser only for manual verification,
  not as a CI dependency) — manual browser verification before each
  phase's PR, same as prior frontend work in this repo.
- Migration: same upgrade/downgrade/upgrade-on-fresh-and-existing-DB
  cycle used for PR #16, applied to the `sevp_certified` migration.

---

## Infra / hosting plan

This project has **no existing deployment** (verified: no
Procfile/fly.toml/render.yaml/deploy workflow anywhere in the repo) —
this is a first-deployment decision, not a migration off something
already running.

Adopting the cost-conscious plan from chat, with one correction flagged
below:

| Layer | Choice | Why |
|---|---|---|
| Map tiles | Free hosted vector tiles now; self-hosted PMTiles/R2 later if needed | §4 — avoid building tile infra for zero users |
| Frontend hosting | Cloudflare Pages | generous free tier, no surprise metered billing like Vercel |
| Database | Supabase free tier (500MB) | **this is just managed Postgres** — the existing SQLAlchemy models, Alembic migrations, and `DATABASE_URL`-based config need zero code changes to point at it |
| Backend API | **Correction: not Cloudflare Workers.** Workers run JS/TS, not Python — moving the existing FastAPI app there would mean a full rewrite, not a hosting swap. Recommend a Python-friendly free/cheap tier instead — Railway or Render free tier (already the READMEs's own implicit assumption of "a Python process"), accepting the cold-start tradeoff at prototype scale | reuses 100% of the existing FastAPI/SQLAlchemy code (§7) |
| Geocoding | None needed — already solved via IPEDS (§6.1) | zero ongoing cost |
| Domain | Cloudflare Registrar | at-cost pricing |
| SSL | Cloudflare/host default | free by default everywhere considered |

One-line summary, corrected: **swap metered-by-usage services (map
tiles, geocoding, scraping proxies) for one-time-processing +
self-hosted-storage wherever possible; keep the existing Python
backend on a Python-capable free tier rather than rewriting it for an
edge-JS runtime.** Expected cost at prototype/small-scale: still
$0–10/month, just with the backend on Railway/Render instead of
Workers.

---

## Decisions (confirmed 2026-09-10)

1. **PR #14: closed**, not reworked (§0).
2. **Route: `/recommend`**, reused from the closed PR (§13).
3. **Recommendation trigger: explicit "Generate Recommendations"
   button for v1**, not live-debounced. After the first result set
   exists, changing filters/preferences updates the map/list
   interactively in place — no re-click, no restart of the flow. (This
   refines §1 step 3 and §13's open question: the *first* pass is
   button-triggered; *subsequent* refinements are live.)
4. **No accounts, login, or saved searches in v1** — confirmed (§14).
5. **Baseline map universe: the full IPEDS set (2,113 institutions),
   not R1/R2-only.** All institutions render as subtle/neutral markers
   from the start; recommended ones are visually emphasized after
   scoring. SEVP/I-20 data, once integrated (§8.3/§15/Phase 3.2), adds
   an **"F-1 / I-20 eligible" filter/toggle on top of this baseline**
   — it does not restrict which institutions appear on the map at all.
   This updates §6.2's `sevp_certified` field description: it drives a
   filter, not a baseline-inclusion gate.

Standing constraints restated for implementation (not new, but worth
keeping visible): don't optimize for data completeness before
shipping — missing program-level facts render as "not yet verified,"
never exclude a school (§10); recommendation output is a ranked top-20
shortlist (15 primary + 5 alternatives), not a strict top-10 and not
an unbounded percentile spread (§5.8, revised 2026-09-11); reuse
existing backend/pipeline code, no rewrites of working infrastructure
(§7).
