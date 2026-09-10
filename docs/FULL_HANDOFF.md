# US Graduate Recommender — Full Product and Engineering Handoff

## 1. Executive Summary

Build a U.S.-only graduate-school information and recommendation platform. It initially serves applicants from China, but the underlying schema must support applicants from India and other countries later.

> **Amendment, 2026-09-11 (Phase 3 v1 scope, not a reversal of this section's goal):** the deliberate 10-program reach/target/safety portfolio below remains the product's long-term target. The first shipped recommendation engine (`docs/MAP_RECOMMENDER_DESIGN.md` §5, Phase 3.0) does **not** implement it yet — it ranks a top-20 shortlist and guarantees a minimum "comfortable-fit" floor (§5.9) instead of reach/target/safety quotas, admission-safety-vs-funding-safety-vs-financial-safety distinctions, or diversity/correlated-risk constraints. This was a deliberate, approved scope decision (map-first UX prioritized for v1; the fuller portfolio model needs real program/funding data — `admission_requirements` `FUNDING` rows, populated `ProgramTrack.estimated_annual_cost_usd` — that doesn't exist yet, per PR #16/#17), not an abandonment of this section. See `MAP_RECOMMENDER_DESIGN.md` §5.8/§5.9 for exactly what v1 does instead and why, and §14 there for what's explicitly deferred.

The product is not merely a scholarship search engine, ranking list, or directory returning hundreds of results. Its core promise is:

> Build a comprehensive U.S. master's-program database, then use official program data, recent admission/funding outcomes, and user preferences to recommend a deliberate portfolio of 10 programs.

Default portfolio:

- 3 reach
- 4 target
- 3 safety
- Never fewer than 2 safety programs by default
- Users may choose conservative, balanced, or aggressive strategies

Primary modes:

1. **Prestige Mode** — ranking, program quality, career, geography, and brand first; self-funding may be acceptable.
2. **Funding Mode** — assistantship, tuition waiver, stipend, and in-study affordability first.
3. **Balanced Mode** — combines ranking, admission realism, funding, cost, employment, and research fit.

The platform should avoid returning 300 loosely filtered programs. It should select 10 programs and explain why each is included, what evidence supports it, and what the main risk is.

---

## 2. Product Mission

Many applicants from China know only a small subset of U.S. universities. They often focus on famous schools, agency-promoted programs, rankings, and expensive professional master's programs, while overlooking:

- Regional public universities
- Smaller research universities
- Research Colleges and Universities
- Departments with formal GA/TA/RA systems
- Thesis-based master's programs
- Lower-cost institutions in less popular states

Examples of the type of overlooked institutions to investigate include Louisiana State University, University of Alaska Fairbanks, and University of Mississippi. These are examples only; funding must always be verified at the specific program/track level.

Mission:

> Help applicants discover U.S. master's opportunities that fit their academic profile, budget, ranking preference, and long-term goals using recent evidence rather than incomplete lists or subjective agency advice.

Potential homepage line:

> We do not give you 300 search results. We give you the 10 U.S. master's programs actually worth applying to.

---

## 3. Scope

### Destination

- United States only

### Applicant origin

- Phase 1: China
- Phase 2: India
- Future: other international applicants

China-specific fields must be optional enrichment, not hard-coded assumptions in the core model.

### Degree level

- Master's first

### Initial disciplines

- Computer Science
- Data Science
- Statistics

Possible later fields include engineering, business analytics, economics, mathematics, natural sciences, geography, environmental science, English, applied linguistics, communication, public administration, higher education, and agricultural science.

### Historical window

Use the most recent five admission cycles as the primary analytical window. Apply recency weighting, for example:

- Current cycle: 1.00
- One year old: 0.85
- Two years old: 0.70
- Three years old: 0.55
- Four years old: 0.40

Older data may remain for historical context but should not strongly drive current recommendations.

---

## 4. University Coverage Strategy

### Full institution index first

The first major engineering goal should be a comprehensive institutional and master's-program database. Users will trust the recommendation system only if they can search a school and find it.

A working estimate discussed was approximately 1,931 U.S. institutions offering master's-level programs, including public, private nonprofit, and private for-profit institutions. This number and its breakdown must be recalculated from the relevant IPEDS release before being treated as a production fact.

The full database should include all relevant master's-granting institutions, but enrichment depth can vary.

### R1/R2 are not enough

R1 and R2 institutions are important, but the platform should also consider:

- Research Colleges and Universities
- Regional public universities
- Institutions with doctoral programs but not R1/R2
- Universities with formal Graduate Assistant systems
- Thesis/research master's programs
- Lower-cost public universities
- Departments with meaningful teaching assistantships

Carnegie classification is a research-environment feature, not a funding guarantee. Some R1 professional master's programs are expensive and unfunded; some regional institutions may offer better master's assistantship opportunities.

### Coverage levels

Suggested statuses:

1. `INDEXED` — basic institution metadata exists
2. `PROGRAMS_DISCOVERED` — most master's programs identified
3. `PROGRAMS_VERIFIED` — program names, degree types, URLs, active status verified
4. `ADMISSION_ENRICHED` — requirements, deadlines, tuition, prerequisites, tracks available
5. `FUNDING_ENRICHED` — assistantships, waivers, scholarships, stipends available
6. `OUTCOME_ENRICHED` — recent admission/funding cases available

Suggested recommendation eligibility:

- `NOT_EVALUATED`
- `ELIGIBLE`
- `LIMITED_DATA`
- `OUT_OF_SCOPE`
- `INACTIVE`

---

## 5. Institutional and Program Database

### Institution-level fields

- Canonical name
- Aliases and historical names
- IPEDS UNITID
- Official website
- State, city, latitude/longitude
- Public/private nonprofit/private for-profit
- Accreditation and operating status
- Highest degree
- Carnegie classification
- Campus setting
- Graduate enrollment
- International graduate enrollment
- Total enrollment
- Basic tuition information
- International-student eligibility/F-1 capability where reliably available
- Primarily online status
- Last verification date

### Program-level fields

The smallest meaningful unit is:

> university + college/school + department + degree + program + track

Each program should include:

- University, college, department
- Official name and aliases
- Degree type
- CIP code
- Program URL
- Online/in-person/hybrid
- STEM designation
- Thesis/non-thesis/project/coursework tracks
- Credits and expected duration
- Intake terms
- Application and priority-funding deadlines
- Minimum GPA
- TOEFL/IELTS requirements
- GRE policy
- Prerequisites
- Cohort size and international share when available
- Program status
- Last verification date

### Source hierarchy

1. IPEDS — institution identity, enrollment, completions, sector, tuition
2. Carnegie — research/institutional classification
3. Academic catalog — main source for program discovery and degree structure
4. Graduate School pages — graduate-wide admission/funding policy
5. Department/program pages — specific requirements, tracks, deadlines, faculty, funding
6. International office — English and international-student rules
7. Institutional reports — cohort, enrollment, outcomes, annual reports
8. Ranking publishers — rank, year, type, methodology

### Catalog adapters

Build reusable adapters such as:

- `AcalogAdapter`
- `CourseLeafAdapter`
- `ModernCampusAdapter`
- `PdfCatalogAdapter`
- `GenericHtmlAdapter`
- `LLMFallbackAdapter`

Suggested interface:

```python
class CatalogAdapter:
    def detect(self, url): ...
    def extract_programs(self, html): ...
    def extract_degrees(self, html): ...
    def extract_requirements(self, html): ...
```

Preferred pipeline:

```text
download page
→ clean HTML
→ detect catalog system
→ extract candidate program links
→ deterministic parsing
→ LLM only for ambiguous content
→ validation
→ human sampling/review
```

### Canonical entities and aliases

Use:

- IPEDS UNITID as institution ID
- Internal `program_id` as stable program ID
- CIP code as classification aid
- Alias tables for institution and program names

---

## 6. User Modes

### Prestige Mode

Optimize for:

- Admission fit
- School/program ranking
- Program quality
- Employment outcomes
- Location
- Research quality
- Brand and return on investment

### Funding Mode

Optimize for:

- Any-funding likelihood
- Full tuition waiver likelihood
- Stipend likelihood
- Stipend versus local living cost
- Funding timing
- Renewal conditions
- Master's eligibility
- International eligibility
- Admission fit

### Balanced Mode

Allow user-controlled weights across:

- Prestige
- Admission fit
- Funding
- In-study cost
- Employment/location
- Research fit

---

## 7. Cost Definition

The following are outside the recommendation objective and assumed to be paid by the student:

- Application fees
- Credential evaluation
- TOEFL/IELTS/GRE
- SEVIS fee
- Visa fee
- Airfare
- Initial housing deposit
- First-month startup expenses

The platform evaluates costs during study:

```text
annual_in_study_out_of_pocket =
tuition
+ mandatory fees
+ required insurance
+ basic local living cost
- tuition waiver
- scholarship
- assistantship stipend
```

Funding categories:

1. Financially sustainable funding — tuition largely waived and stipend covers most basic living costs
2. Full tuition funding — tuition covered, living costs remain
3. Partial funding — some support, substantial self-funding remains
4. Competitive opportunity only — funding exists but is not guaranteed
5. Insufficient/unclear evidence

---

## 8. Recommendation Portfolio

> **Not yet implemented as of Phase 3.0 — see the amendment in §1.** The
> shipped v1 engine (`recommendation.py`) does a ranked top-20 shortlist
> with a comfortable-fit floor (`MAP_RECOMMENDER_DESIGN.md` §5.9), not
> this section's reach/target/safety quota model, admission/funding/
> financial safety distinction, or portfolio-optimization constraints
> (diversity, anti-correlation, "no allowlist"). This section still
> describes the intended eventual behavior; it is not superseded, just
> not yet built.

### Default structure

- Balanced: 3 reach / 4 target / 3 safety
- Conservative: 2 / 4 / 4
- Aggressive: 5 / 3 / 2

Never fewer than two safety programs by default.

### Separate safety concepts

- Admission Safety
- Funding Safety
- Financial Safety

A program may be easy to enter but impossible to afford. For funding-oriented users, an unfunded admission safety is not a true safety.

### Provisional buckets

- Reach: estimated 10–35%
- Target: estimated 35–70%
- Safety: above 70%

These are starting ranges only and must be calibrated by discipline and data quality.

Avoid false precision. Prefer ranges, low/medium/high, comparable-case position, and confidence level rather than values such as 68.43%.

### Portfolio optimization

Do not simply select the top 10 independent scores. Use constrained portfolio optimization:

- Reach/target/safety quotas
- Minimum safety count
- Diversity across institutions and funding mechanisms
- Avoid correlated failure risk
- Avoid all programs depending on one professor
- Penalize stale or low-confidence data
- Respect geography, duration, thesis, career, and budget preferences

Prestige objective:

> Maximize admission-adjusted program value while preserving realistic safeties.

Funding objective:

> Maximize the probability of at least one financially sustainable funded offer.

---

## 9. Applicant Profile

Core fields:

- Origin country
- Undergraduate institution and major
- Original GPA and grading scale
- Class rank and major GPA
- Relevant coursework
- TOEFL/IELTS and speaking score
- GRE total/quant/verbal
- Research and publications
- Thesis
- Internship and employment
- Teaching/tutoring
- Technical skills
- Target field
- Geography, ranking, funding, thesis, PhD, and risk preferences

### Do not over-weight Chinese institution tiers

China is the first market, but the model should not be built around 985/211/Double First Class labels. These may be auxiliary features. Many U.S. master's programs primarily evaluate GPA, prerequisites, coursework, research, tests, recommendations, statement quality, and program fit.

Use a general schema:

```text
origin_country
undergraduate_institution_id
grading_system
gpa_original
class_rank
institution_context
major_strength
coursework_features
research_features
```

China-specific enrichment may include former 985/211, Double First Class, discipline strength, and selectivity band.

India-specific enrichment may include CGPA scale, institution type, backlogs, degree duration, and class/division.

Never apply naive linear GPA conversion across countries.

---

## 10. Admission and Funding Prediction

### Separate targets

Estimate independently:

- `P(admission)`
- `P(any funding)`
- `P(full tuition waiver)`
- `P(stipend)`
- `P(funding with admission)`
- `P(funding renewal)`
- Expected annual in-study out-of-pocket cost

### Comparable-case retrieval

Early versions should prioritize interpretable similar-case retrieval.

Similarity features:

- Country
- Undergraduate institution and major
- Original grading context
- GPA and class rank
- English scores, especially speaking for TA
- GRE
- Research/publications
- Teaching
- Work/internships
- Technical skills
- Thesis intention
- Faculty/research match
- Application timing
- Cycle recency

Display:

- Comparable-case count
- Admit/reject/waitlist outcomes
- Funding/no-funding outcomes
- Median/range of major features
- Missing-data warnings
- Selection-bias warning

### Model evolution

Early:

- Hard filters
- Rules
- Weighted nearest neighbors
- Interpretable scorecards

Later:

- Logistic regression
- Calibrated gradient boosting
- Hierarchical Bayesian models
- Learning to rank
- Program/year effects
- Time-aware calibration

Data quality matters more than model complexity.

---

## 11. Funding Data

Separate funding types:

- TA
- RA
- GA
- Fellowship
- Scholarship
- Tuition waiver
- Nonresident tuition waiver
- Department assistantship
- Faculty-funded assistantship
- Post-enrollment campus assistantship

Fields:

- Master's eligible
- International eligible
- Guaranteed
- Automatic consideration
- Separate application
- Faculty dependent
- Post-enrollment only
- Tuition coverage
- Stipend and period
- Work hours
- Insurance
- Fees not covered
- Renewal conditions
- Typical duration
- Priority deadline
- Source and verification date

Do not treat these as equivalent:

- “Assistantships available”
- “All admitted students are funded”
- “Most full-time students receive funding”
- “Students may apply”
- “Funding is competitive”
- “Priority is given to PhD students”

---

## 12. Historical Admission and Funding Cases

Collect all outcomes, not only successful offers:

- Admission
- Rejection
- Waitlist
- Waitlist then admission/rejection
- Withdrawn
- No decision
- Admission without funding
- Partial funding
- Full funding
- Funding after enrollment
- Final destination

Success-only data produces survivorship bias.

Suggested case structure:

```json
{
  "cycle": "Fall 2026",
  "origin_country": "China",
  "undergraduate_university": "Example University",
  "undergraduate_major": "Computer Science",
  "gpa_original": "86.2/100",
  "class_rank_percentile": 15,
  "toefl_total": 103,
  "toefl_speaking": 23,
  "gre_total": 323,
  "research_experience": 2,
  "publication_level": "none",
  "internship_level": "medium",
  "teaching_experience": true,
  "target_university": "Example University",
  "target_program": "MS Computer Science",
  "target_track": "Thesis",
  "initial_result": "waitlisted",
  "final_result": "admitted",
  "funding_result": "TA",
  "tuition_waiver": "full",
  "stipend": 19000,
  "funding_with_admission": true,
  "source_platform": "user_submission",
  "verification_level": "offer_verified"
}
```

---

## 13. Community Data Sources

Potential sources:

- Xiaohongshu
- 1Point3Acres
- Reddit
- TheGradCafe
- Public blogs/forums
- User submissions

Useful content may be in:

- Background posts
- School-selection posts
- Admission summaries
- Scholarship details
- Final destination posts
- Author comments
- Screenshots
- Separate posts by the same applicant

### Collection boundaries

Do not implement:

- Pretending automation is a human
- CAPTCHA bypass
- Anti-bot evasion
- Browser fingerprint deception
- Account rotation
- Hidden scraping
- Rate-limit bypass
- Login/access-control bypass

Before collection:

- Review terms and access rules
- Use official APIs where available
- Avoid unnecessary personal data
- Preserve provenance
- Provide deletion/correction
- Maintain fallback sources

### Recommended cold-start method

Use human browsing plus semi-automated import:

1. Researcher/user opens a relevant post normally.
2. Browser extension imports the current page or screenshots.
3. System extracts text/images.
4. System identifies background and outcomes.
5. Human confirms fields.
6. Case is anonymized and stored.

### Long-term data moat

The strongest source is users of the platform itself.

Ideal loop:

```text
public historical cases
→ initial recommendations
→ users track applications
→ users upload complete outcomes
→ database improves
→ future recommendations improve
```

Build an application tracker containing program, submission, interview, waitlist, admission, rejection, funding, scholarship, and final destination.

---

## 14. Image and Screenshot Parsing

Many social posts contain important data only in images. Support:

- Chinese/English mixed text
- School/program abbreviations
- Checkmarks, crosses, arrows
- Waitlist transitions
- Scholarship amounts
- Notes-app screenshots
- Comments containing applicant background
- Multiple images and long screenshots
- Background in another post

Interpretation rules:

- `wl → admitted` must preserve both initial and final result
- `withdraw` must not count as rejection
- Inferred rejection must remain uncertain, not verified
- Scholarship strings such as `6w`, `1.5w`, or `8k` must preserve raw text and require currency/period confirmation
- Program abbreviations require canonical alias mapping

### Cost-controlled image pipeline

1. Local preprocessing
   - Deduplication
   - Perceptual hashing
   - Crop empty space
   - Resize
   - Segment long screenshots
   - Basic OCR

2. Cheap classification
   - Background
   - Admission outcomes
   - Funding
   - Official offer
   - Irrelevant

3. Multimodal structured extraction

```json
{
  "cycle": "Fall 2025",
  "profile": {},
  "applications": [],
  "funding": [],
  "uncertain_fields": []
}
```

4. Localized re-check of ambiguous regions
5. Human confirmation

Every extracted field should retain raw text, normalized value, source image, image region, confidence, and verification status.

### Case bundles

One applicant may have a background post, early results, final results, final destination, and author comments. Store these as an anonymized case bundle. The system may suggest likely matches, but a human should confirm merging. Do not automatically crawl an author's entire account.

---

## 15. Data Quality, Verification, and Privacy

### Evidence levels

5. Current official source or verified formal offer
4. Multiple verified recent outcomes
3. One verified recent outcome
2. Unverified community report
1. Old, ambiguous, or inferred information

Keep evidence confidence separate from model confidence.

### Case states

- `raw`
- `parsed`
- `needs_review`
- `user_confirmed`
- `document_verified`
- `rejected_as_invalid`

### Duplicate/fraud controls

- File hash
- Perceptual image hash
- Text similarity
- Program-list similarity
- Cycle matching
- Anonymous author hash
- Offer-template checks
- Human sampling
- Suspicious-account detection

### Privacy

Separate PII from model data. Redact or avoid storing:

- Name
- Address
- Student ID
- Email
- Birth date
- Application number
- Username/avatar
- Phone number

Requirements:

- Explicit consent
- Separate model-training consent
- Deletion and correction support
- Aggregate public display
- Minimal raw-content retention
- Screenshot retention policy

---

## 16. Ranking and Trends

Ranking is optional and user-controlled. Store publisher, ranking type, year, rank, methodology, source, and update date. Never store a single permanent rank.

Potential sources:

- U.S. News overall
- U.S. News graduate field
- QS subject
- Research output
- Employment/value rankings

Detect trends rather than assume them:

- Cohort expansion
- Selectivity change
- Tuition growth
- Funding-rate decline
- International enrollment growth
- Thesis/non-thesis changes
- Faculty changes
- Program pauses
- GRE policy changes
- Professional/cash-cow orientation

---

## 17. Recommendation Card

Each recommended program should show:

- University, department, program, track
- Reach/target/safety
- Admission match range
- Funding match range
- Estimated annual in-study out-of-pocket cost
- Similar-case count
- Evidence confidence
- Model confidence
- Ranking and year
- Why recommended
- Main risk
- Funding structure and timing
- Master's/international eligibility
- Official source
- Last verification date

---

## 18. Suggested Database Tables

```text
universities
university_aliases
departments
programs
program_aliases
program_tracks
rankings
institution_statistics

funding_opportunities
funding_policies
assistantship_positions
faculty
faculty_grants

applicant_profiles
applicant_country_features
applications
application_outcomes
funding_outcomes
final_destinations

evidence_sources
source_snapshots
parsed_documents
verified_documents
community_reports
case_bundles

cost_of_attendance
local_living_costs

recommendation_runs
recommendation_items
prediction_explanations

data_review_tasks
data_conflicts
data_quality_scores
```

Preserve provenance and verification metadata. Do not store everything in one unstructured JSON column.

---

## 19. Engineering Architecture

Suggested stack:

- Frontend: Next.js, TypeScript, Tailwind
- Backend: FastAPI or typed TypeScript backend
- Database: PostgreSQL, optionally pgvector
- Ingestion: Python, approved Playwright workflows, BeautifulSoup/lxml, catalog adapters, PDF parsing, OCR, multimodal extraction
- Async jobs: Celery/Dramatiq/queue service
- Deployment: Vercel + managed API/database infrastructure
- Observability: job logs, fetch logs, parsing confidence, review queue, model version, cost tracking

---

## 20. Roadmap

### Phase 0 — Repository and standards

- Monorepo
- CI
- Linting
- Type checking
- Tests
- Migrations
- Agent instructions

### Phase 1 — Complete institution index

- Import master's-granting institutions
- Institution search/detail
- IPEDS identifiers
- Carnegie classification
- Coverage tiers

### Phase 2 — Program discovery

- Catalog adapters
- Program canonicalization
- Program aliases/status/URLs/tracks
- Manual review dashboard

### Phase 3 — Admission enrichment

Start with CS, Data Science, Statistics. Add GPA, tests, deadlines, prerequisites, tuition, STEM, thesis, duration.

### Phase 4 — Funding enrichment

Add TA/RA/GA, fellowships, waivers, stipends, insurance, eligibility, timing, renewal.

### Phase 5 — Community outcomes

- Screenshot upload/import
- Image parsing
- Human confirmation
- Case bundles
- Deduplication
- Verification

### Phase 6 — Applicant questionnaire

- Academic profile
- Tests
- Research/work/teaching
- Preferences
- Risk strategy

### Phase 7 — Recommendation

- Hard filters
- Comparable cases
- Confidence
- Prestige/Funding/Balanced modes
- 3/4/3 portfolio

### Phase 8 — User application tracker

- Saved programs
- Decisions
- Funding
- Final destination
- Contributor incentives

---

## 21. First Engineering Issues

1. Initialize monorepo
2. Institution schema and IPEDS importer
3. Program/catalog schema
4. Catalog adapter framework
5. Manual review dashboard
6. Funding schema
7. Screenshot ingestion and extraction
8. Case bundle/outcome schema
9. Applicant questionnaire
10. Recommendation constraints

The immediate recommended first task is:

> Build the university schema and an idempotent importer for the selected IPEDS year, with aliases, sector, location, highest degree, master's-granting status, enrollment fields, and coverage tier.

Then add Carnegie classification, institution search/detail, and program discovery adapters.

---

## 22. Claude Code and Codex Workflow

Use both tools, but do not let them freely edit the same branch.

Suggested split:

- Primary agent: implementation
- Secondary agent: architecture, privacy, data-quality, and test review
- Human: approves product assumptions and major schema changes

Practical option:

- Codex: implementation, migrations, APIs, tests, bug fixes
- Claude Code: long-context review, architecture, edge cases, privacy/data review

Either may be primary.

Git workflow:

- `main`
- `feature/<issue>`
- `review/<issue>`

Process:

1. Human gives one issue with acceptance criteria.
2. Primary implements on feature branch.
3. Primary runs lint, typecheck, tests, migrations.
4. Reviewer reads specs, issue, diff, and test output.
5. Reviewer returns blocking/high/medium/test-gap findings.
6. Primary fixes accepted findings.
7. Human merges.

Do not ask an agent to “build the entire platform.” Give small, reviewable tasks.

---

## 23. Mandatory Agent Rules

- Never invent university, ranking, admission, or funding facts.
- Preserve source provenance, scope, date, and verification status.
- Model funding at program/track level.
- Never apply PhD funding to master's students without evidence.
- Never assume international eligibility.
- Separate admission safety, funding safety, and financial safety.
- Use recent five-cycle data with recency weighting.
- Preserve original grading systems.
- Include rejection and no-funding cases.
- Avoid false precision.
- Do not implement stealth scraping, CAPTCHA bypass, account rotation, anti-detection evasion, or access-control bypass.
- Respect privacy, consent, correction, and deletion.
- Use migrations and tests.
- Report assumptions and limitations.

---

## 24. Primary Agent Prompt

You are the primary engineer for an evidence-based U.S. master's information and recommendation platform.

Read this entire handoff before editing code.

The product must first build a comprehensive database of U.S. master's-granting institutions and programs. It later adds admission requirements, funding, recent historical outcomes, comparable-case retrieval, and a ten-program recommendation portfolio.

The platform initially serves applicants from China but must use a general international schema. China-specific school labels are optional enrichment, not the core model.

The product serves Prestige, Funding, and Balanced users. The default portfolio is 3 reach, 4 target, and 3 safety, with no fewer than two safeties by default.

Official facts must retain source provenance, scope, retrieval date, and verification status. Do not invent exact admission or funding probabilities. Do not implement stealth scraping or access-control bypass.

Work on one issue at a time. For each issue:

1. Restate acceptance criteria.
2. Inspect the repository.
3. Propose the smallest coherent design.
4. Implement.
5. Add tests.
6. Run lint, type checks, tests, and migrations.
7. Report files changed, design decisions, tests, assumptions, limitations, and follow-up issues.

Begin only with the issue explicitly provided by the human.

---

## 25. Review Agent Prompt

Act as a strict reviewer.

Read the full handoff, issue, diff, and test output.

Check for:

- Product-spec violations
- Institution facts incorrectly applied to programs
- PhD funding incorrectly applied to master's students
- International eligibility mistakes
- Missing provenance or verification dates
- False precision
- Incorrect five-cycle logic
- Survivorship bias
- Missing rejection/no-funding outcomes
- Incorrect portfolio constraints
- Admission safety confused with funding safety
- Privacy/deletion/consent issues
- Unsafe scraping assumptions
- Migration risks
- Missing tests
- Broken type contracts
- Hallucinated data

Return findings in this order:

1. Blocking
2. High priority
3. Medium priority
4. Test gaps
5. Optional improvements

For every finding, cite the file and code location. Do not rewrite the entire project unless requested.

---

## 26. Core Long-Term Moat

The moat is not the UI or the LLM alone.

It is:

> A comprehensive, current, source-grounded U.S. master's-program database connected to recent applicant outcomes and an explainable recommendation engine.
