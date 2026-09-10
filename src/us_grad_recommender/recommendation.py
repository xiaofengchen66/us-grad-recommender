"""Recommendation engine — Phase 3.0 (deterministic v1).

Design: docs/MAP_RECOMMENDER_DESIGN.md §5. The rules that matter most,
restated at the call sites below rather than only in the doc:

- `match_score` is never, and must never be treated as, an admission
  probability (§5.0). It is a match/relevance score against the
  student's stated profile and preferences, nothing else.
- A component the user didn't ask about (no budget given) is excluded
  from the scoring denominator entirely — see `_weighted_average` and
  the `None` sentinel used throughout. A component the user did ask
  about but where the institution-side fact is unverified stays active,
  using a neutral fallback, and lowers `data_confidence` instead (§5.2).
- Geographic preference (`preferred_states`) is a hard filter on the
  candidate pool, not a scoring component (§5.4, revised 2026-09-11) —
  if a student says "only NY and CA," nothing outside those states can
  appear no matter how well it scores. There is deliberately no
  `location_fit` component.
- Program existence at an institution is tracked separately
  (`ProgramAvailability`) from how well it scores (§5.3) — an
  institution with no program data on file is never presented as if a
  program were confirmed there.
- Deterministic, no ML/LLM in the ranking path (§5.1).
- Output is a ranked top-20 shortlist (§5.8, revised 2026-09-11), not a
  broad percentile-tiered spread — `recommend()` returns only the top
  `TOP_N` results; `category` (`top_fit`/`good_fit`/`explore`) and
  `is_primary_shortlist` are assigned by rank position within that
  set, never by a score/confidence threshold. `data_confidence` stays
  independent of rank — a top-ranked result can still carry Low
  confidence and must still show it as such.
- A comfortable-fit floor (§5.9, added 2026-09-11) guarantees at least
  `MIN_COMFORTABLE_FIT_COUNT` results with a verified, comfortably-met
  GPA requirement in the shortlist — answering FULL_HANDOFF.md §8's
  "minimum safety count" using only data we actually have, with no
  admission-probability judgment involved.
"""

from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from us_grad_recommender.models.catalog import (
    AcademicUnit,
    DegreeLevel,
    DegreeType,
    Program,
    ProgramTrack,
)
from us_grad_recommender.models.common import VerificationStatus
from us_grad_recommender.models.university import University

# --- Enums (request/response vocabulary; not persisted) -----------------


class ProgramCategory(str, enum.Enum):
    """The eight deep-coverage categories (§9.1) get program-level
    official links; GENERAL gets the institution's graduate-admissions
    entry point. Link tier is independent of scoring (§9.3) — GENERAL
    picks still score normally off the free-text program name.
    """

    JD = "jd"
    LLM = "llm"
    MD = "md"
    DDS_DMD = "dds_dmd"
    CS_MASTERS = "cs_masters"
    CS_PHD = "cs_phd"
    BSN = "bsn"
    ABSN = "absn"
    GENERAL = "general"


class PriorityPreset(str, enum.Enum):
    RANKING = "ranking"
    AFFORDABILITY = "affordability"
    ADMISSION_FIT = "admission_fit"
    BALANCED = "balanced"


class DataConfidence(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecommendationCategory(str, enum.Enum):
    """Rank-based, not score/confidence-threshold-based (§5.8, revised
    2026-09-11) — assigned only by `recommend()` after sorting the full
    eligible set, based on position within the top 20. Deliberately named
    to read as "how well it matches what you asked for," never as
    admission difficulty (same reasoning that ruled out
    strong_match/target/reach in the first place)."""

    TOP_FIT = "top_fit"
    GOOD_FIT = "good_fit"
    EXPLORE = "explore"


class ProgramAvailability(str, enum.Enum):
    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class GradingScale(str, enum.Enum):
    """FULL_HANDOFF.md §9 lists "Original GPA and grading scale" as a core
    applicant-profile field for exactly this reason: `ProgramTrack.min_gpa`
    is normalized to a 0-4 scale (PHASE_2_CATALOG_DESIGN.md §2.1/§4), and
    comparing a differently-scaled GPA to it directly is only valid on a
    0-4 scale. §0/§23 explicitly forbid inventing a linear conversion
    (e.g. 86/100 -> 3.44/4.0) across grading systems, so anything other
    than SCALE_4_0 must fall back neutrally in scoring (§5.2b) rather than
    being compared — see `_score_academic_fit`.
    """

    SCALE_4_0 = "scale_4_0"
    OTHER = "other"  # 100-point, 4.3/5.0-max, or any non-4.0 system


# Keyword fragments used to match a category against Program.canonical_name
# / AcademicUnit.name (case-insensitive substring). Deliberately small and
# literal for v1 — same "narrow, evidence-shaped heuristic over a clever
# general one" approach already used for _DEGREE_TYPE_TABLE in
# parser_pipeline.py. Revisit with real pilot-school evidence, not
# hypothetical categories, per that module's own documented lesson.
_CATEGORY_KEYWORDS: dict[ProgramCategory, tuple[str, ...]] = {
    ProgramCategory.JD: ("juris doctor", "j.d.", " jd"),
    ProgramCategory.LLM: ("llm", "master of laws", "l.l.m."),
    ProgramCategory.MD: ("doctor of medicine", "m.d.", " md "),
    ProgramCategory.DDS_DMD: ("d.d.s.", "d.m.d.", "doctor of dental"),
    ProgramCategory.CS_MASTERS: ("computer science",),
    ProgramCategory.CS_PHD: ("computer science",),
    ProgramCategory.BSN: ("nursing",),
    ProgramCategory.ABSN: ("nursing",),
}

_CATEGORY_DEGREE_LEVEL: dict[ProgramCategory, DegreeLevel] = {
    ProgramCategory.JD: DegreeLevel.DOCTORAL,
    ProgramCategory.LLM: DegreeLevel.MASTERS,
    ProgramCategory.MD: DegreeLevel.DOCTORAL,
    ProgramCategory.DDS_DMD: DegreeLevel.DOCTORAL,
    ProgramCategory.CS_MASTERS: DegreeLevel.MASTERS,
    ProgramCategory.CS_PHD: DegreeLevel.DOCTORAL,
    ProgramCategory.BSN: DegreeLevel.MASTERS,
    ProgramCategory.ABSN: DegreeLevel.MASTERS,
}


def expected_degree_level(category: ProgramCategory) -> Optional[DegreeLevel]:
    """The degree level a deep-coverage category implies (e.g. CS_PHD ->
    DOCTORAL), or None for GENERAL, which has no fixed implied level.
    Public so RecommendationProfileIn (api/schemas.py) can validate that a
    request's degree_level and program_category agree, instead of
    silently accepting a mismatch like degree_level=masters with
    program_category=cs_phd."""
    return _CATEGORY_DEGREE_LEVEL.get(category)

# Real HD.C21BASIC codes (importers/ipeds/mappings.py) grouped into a
# research-intensity proxy — not a ranking (§8.4/§0/§23: no US News, no
# invented prestige). 15/16 = Doctoral Universities (Highest/Higher
# Research Activity); 17 = Doctoral/Professional; 18-20 = Master's
# Colleges & Universities; 21-23 = Baccalaureate-focused.
_RESEARCH_INTENSIVE_CARNEGIE_CODES = frozenset({15, 16, 17})
_MASTERS_FOCUSED_CARNEGIE_CODES = frozenset({18, 19, 20})
_BACCALAUREATE_CARNEGIE_CODES = frozenset({21, 22, 23})

_NEUTRAL_FALLBACK = 60.0
_VERIFIED_STATUSES = frozenset(
    {
        VerificationStatus.USER_CONFIRMED,
        VerificationStatus.DOCUMENT_VERIFIED,
        VerificationStatus.PARSED,
    }
)

_PRESET_WEIGHTS: dict[PriorityPreset, dict[str, float]] = {
    PriorityPreset.RANKING: {
        "academic_fit": 1.0,
        "cost_fit": 1.0,
        "reputation_fit": 2.0,
        "program_fit": 1.5,
    },
    PriorityPreset.AFFORDABILITY: {
        "academic_fit": 1.0,
        "cost_fit": 2.5,
        "reputation_fit": 0.5,
        "program_fit": 1.5,
    },
    PriorityPreset.ADMISSION_FIT: {
        "academic_fit": 2.5,
        "cost_fit": 1.0,
        "reputation_fit": 0.5,
        "program_fit": 1.5,
    },
    PriorityPreset.BALANCED: {
        "academic_fit": 1.0,
        "cost_fit": 1.0,
        "reputation_fit": 1.0,
        "program_fit": 1.0,
    },
}


@dataclass(frozen=True)
class RecommendationProfile:
    """v1 scoring inputs only (§5.4's required/optional split). Test
    scores, GRE, and school-type preference are collected by the wider
    product profile (design doc §9) but not yet wired into scoring —
    deliberately left off this dataclass rather than accepted-and-ignored,
    so the engine's contract stays honest about what it actually uses.

    `preferred_states` is a hard filter on the candidate pool (§5.4,
    revised 2026-09-11), not a scoring component — if a student says "only
    NY and CA," a school outside those states must never appear in the
    shortlist no matter how well it scores otherwise. There is no
    `location_fit` component for exactly this reason: once the candidate
    pool is already restricted to preferred states, a soft "is this in a
    preferred state" score would be redundant (true for every remaining
    candidate) or, worse, would let an out-of-preference school back in
    via a high overall score. When `preferred_states` is unset, the
    candidate pool is unrestricted (nationwide) and there is still no
    location-based scoring, since there is no stated preference to score
    against.
    """

    degree_level: DegreeLevel
    program_category: ProgramCategory
    program_name: str
    gpa: float
    gpa_scale: GradingScale
    priority: PriorityPreset = PriorityPreset.BALANCED
    budget_max_usd: Optional[float] = None
    preferred_states: Optional[tuple[str, ...]] = None


@dataclass(frozen=True)
class ComponentScore:
    value: Optional[float]  # None means excluded from the denominator (§5.2a)
    verified: bool = False  # False means neutral fallback was used (§5.2b)


@dataclass(frozen=True)
class ScoredInstitution:
    """`rank`, `category`, and `is_primary_shortlist` are only meaningful
    once this has gone through `recommend()` — `score_university()` (used
    directly by tests and by `recommend()` before sorting) sets them to
    placeholder defaults (`rank=0`, `category=EXPLORE`,
    `is_primary_shortlist=False`) since a single institution's rank
    depends on the full ranked set, not on that institution alone (§5.8).
    """

    unitid: int
    program_id: Optional[int]
    match_score: int
    data_confidence: DataConfidence
    program_availability: ProgramAvailability
    component_scores: dict[str, Optional[float]]
    is_comfortable_fit: bool
    rank: int = 0
    category: RecommendationCategory = RecommendationCategory.EXPLORE
    is_primary_shortlist: bool = False
    positive_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unknown_facts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ProgramMatch:
    availability: ProgramAvailability
    program_id: Optional[int]
    min_gpa: Optional[float]
    min_gpa_verified: bool
    estimated_annual_cost_usd: Optional[float]
    cost_verified: bool


def _score_academic_fit(
    gpa: float, gpa_scale: GradingScale, match: _ProgramMatch
) -> ComponentScore:
    if match.min_gpa is None:
        return ComponentScore(_NEUTRAL_FALLBACK, verified=False)
    if gpa_scale != GradingScale.SCALE_4_0:
        # ProgramTrack.min_gpa is normalized to a 0-4 scale; comparing a
        # GPA reported on any other scale (100-point, 4.3-max, etc.)
        # directly against it would require inventing a linear
        # conversion, which FULL_HANDOFF.md §0/§9/§23 explicitly forbid.
        # Fall back neutrally rather than guess at a conversion.
        return ComponentScore(_NEUTRAL_FALLBACK, verified=False)
    diff = gpa - float(match.min_gpa)
    if diff >= 0.3:
        value = 90.0
    elif diff >= 0.0:
        value = 75.0
    elif diff >= -0.2:
        value = 50.0
    else:
        value = 25.0
    return ComponentScore(value, verified=match.min_gpa_verified)


def _score_cost_fit(budget_max_usd: Optional[float], match: _ProgramMatch) -> ComponentScore:
    if budget_max_usd is None:
        return ComponentScore(None)  # user didn't ask — excluded, not zeroed (§5.2a)
    if match.estimated_annual_cost_usd is None:
        return ComponentScore(_NEUTRAL_FALLBACK, verified=False)
    cost = float(match.estimated_annual_cost_usd)
    if cost <= budget_max_usd:
        value = 90.0
    elif cost <= budget_max_usd * 1.15:
        value = 55.0
    else:
        value = 20.0
    return ComponentScore(value, verified=match.cost_verified)


def normalize_carnegie_classification(carnegie_classification: Optional[int]) -> Optional[int]:
    """IPEDS uses -2 as "not applicable / not in the Carnegie universe"
    (see importers/ipeds/mappings.py's CARNEGIE_BASIC_LABELS comment) — a
    real institution can have this on file, but it's a "no classification"
    signal, not a real tier. Confirmed against the dev DB: 95 real
    institutions carry this exact sentinel. Public and shared by
    `_score_reputation_fit` and `GET /universities/map` (api/routes.py) so
    both treat the sentinel the same way — a map that colored/legended
    markers by the raw field would otherwise render those 95 institutions
    as if -2 were a real Carnegie tier.
    """
    if carnegie_classification is None or carnegie_classification < 0:
        return None
    return carnegie_classification


def _score_reputation_fit(carnegie_classification: Optional[int]) -> ComponentScore:
    carnegie_classification = normalize_carnegie_classification(carnegie_classification)
    if carnegie_classification is None:
        return ComponentScore(_NEUTRAL_FALLBACK, verified=False)
    if carnegie_classification in _RESEARCH_INTENSIVE_CARNEGIE_CODES:
        value = 80.0
    elif carnegie_classification in _MASTERS_FOCUSED_CARNEGIE_CODES:
        value = 65.0
    elif carnegie_classification in _BACCALAUREATE_CARNEGIE_CODES:
        value = 50.0
    else:
        value = 55.0
    return ComponentScore(value, verified=True)


def _score_program_fit(match: _ProgramMatch) -> ComponentScore:
    # Ordering must be CONFIRMED > PARTIAL > UNKNOWN (§5.3) — PARTIAL is
    # real, if circumstantial, evidence the program likely exists and
    # must score above UNKNOWN's "we have nothing on file" neutral
    # fallback (_NEUTRAL_FALLBACK), not below it.
    if match.availability == ProgramAvailability.CONFIRMED:
        return ComponentScore(85.0, verified=True)
    if match.availability == ProgramAvailability.PARTIAL:
        return ComponentScore(_NEUTRAL_FALLBACK + 10.0, verified=False)
    return ComponentScore(_NEUTRAL_FALLBACK, verified=False)


def _weighted_average(components: dict[str, ComponentScore], weights: dict[str, float]) -> float:
    numerator = 0.0
    denominator = 0.0
    for name, component in components.items():
        if component.value is None:
            continue
        w = weights[name]
        numerator += w * component.value
        denominator += w
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _data_confidence(components: dict[str, ComponentScore]) -> DataConfidence:
    active = [c for c in components.values() if c.value is not None]
    if not active:
        return DataConfidence.LOW
    verified_fraction = sum(1 for c in active if c.verified) / len(active)
    if verified_fraction >= 0.75:
        return DataConfidence.HIGH
    if verified_fraction >= 0.35:
        return DataConfidence.MEDIUM
    return DataConfidence.LOW


TOP_N = 20
PRIMARY_SHORTLIST_SIZE = 15
_TOP_FIT_CUTOFF = 5  # rank 1-5
_GOOD_FIT_CUTOFF = 12  # rank 6-12; rank 13-20 -> EXPLORE

# Comfortable-fit floor (§5.9, added 2026-09-11 to answer FULL_HANDOFF.md
# §8's "minimum safety count" requirement without inventing an admission
# probability): reuses §8's own Balanced-portfolio safety count (3) rather
# than a new number.
MIN_COMFORTABLE_FIT_COUNT = 3
_COMFORTABLE_FIT_ACADEMIC_THRESHOLD = 75.0


def _category_for_rank(rank: int) -> RecommendationCategory:
    """Rank-based, not score/confidence-based (§5.8) — see
    RecommendationCategory's docstring for why."""
    if rank <= _TOP_FIT_CUTOFF:
        return RecommendationCategory.TOP_FIT
    if rank <= _GOOD_FIT_CUTOFF:
        return RecommendationCategory.GOOD_FIT
    return RecommendationCategory.EXPLORE


def _build_reasons(
    profile: RecommendationProfile,
    match: _ProgramMatch,
    components: dict[str, ComponentScore],
) -> tuple[list[str], list[str], list[str]]:
    positive: list[str] = []
    warnings: list[str] = []
    unknown: list[str] = []

    if match.availability == ProgramAvailability.CONFIRMED:
        positive.append(f"Has a confirmed {profile.program_name} program")
    elif match.availability == ProgramAvailability.PARTIAL:
        warnings.append(
            f"{profile.program_name}-related department found, program not yet confirmed"
        )
    else:
        unknown.append("Program offerings not yet verified")

    academic = components["academic_fit"]
    if academic.value is not None:
        if academic.verified and academic.value >= 75:
            positive.append("GPA is within a plausible range for this program's requirements")
        elif not academic.verified:
            unknown.append("GPA requirement not yet verified")

    cost = components["cost_fit"]
    if cost.value is not None:
        if cost.verified and cost.value >= 75:
            positive.append("Estimated cost is within your budget")
        elif cost.verified:
            warnings.append("Estimated cost may exceed your budget")
        else:
            unknown.append("Tuition/cost not yet verified")

    # No location_fit reason here by design: when preferred_states is set,
    # every candidate this function ever sees is already in a preferred
    # state (hard-filtered in recommend(), §5.4) — restating that on every
    # single result would be constant, undifferentiating noise, not a
    # useful "why."

    return positive, warnings, unknown


@dataclass(frozen=True)
class _CatalogRow:
    unit_name: str
    program_canonical_name: str
    program_id: int
    degree_level: DegreeLevel
    min_gpa: Optional[float]
    min_gpa_verified: bool
    estimated_annual_cost_usd: Optional[float]
    cost_verified: bool


def _load_catalog_by_unitid(session: Session) -> dict[int, list[_CatalogRow]]:
    """One bulk fetch of every AcademicUnit/Program/ProgramTrack/DegreeType
    row, grouped by the owning university's unitid, so `recommend()` scores
    all universities with 2 queries total instead of 2 per university.
    Cheap today (program data is still sparse — only pilot schools have
    any) and the right shape to keep cheap as coverage grows, since it's a
    single indexed join rather than N+1.
    """
    unit_rows = session.execute(
        select(AcademicUnit.id, AcademicUnit.unitid, AcademicUnit.name)
    ).all()
    unit_name_by_id = {r.id: r.name for r in unit_rows}
    units_by_unitid: dict[int, list[int]] = {}
    for r in unit_rows:
        units_by_unitid.setdefault(r.unitid, []).append(r.id)

    # Explicit ORDER BY, not incidental Postgres row order: when a Program
    # has more than one ProgramTrack (e.g. thesis vs. non-thesis with
    # different min_gpa/cost), _match_program takes the first row it
    # matches — without a defined order, which track "wins" would be
    # unspecified, contradicting §5.1's "100% deterministic" requirement.
    # v1 deliberately picks the lowest-id (first-created) track
    # consistently rather than implementing per-track selection logic.
    program_rows = session.execute(
        select(Program, ProgramTrack, DegreeType)
        .join(DegreeType, Program.degree_type_code == DegreeType.code)
        .outerjoin(ProgramTrack, ProgramTrack.program_id == Program.id)
        .order_by(Program.id, ProgramTrack.id)
    ).all()
    rows_by_unit_id: dict[int, list[_CatalogRow]] = {}
    for program, track, degree_type in program_rows:
        rows_by_unit_id.setdefault(program.academic_unit_id, []).append(
            _CatalogRow(
                unit_name=unit_name_by_id.get(program.academic_unit_id, ""),
                program_canonical_name=program.canonical_name,
                program_id=program.id,
                degree_level=degree_type.level,
                min_gpa=(
                    float(track.min_gpa)
                    if track is not None and track.min_gpa is not None
                    else None
                ),
                min_gpa_verified=track is not None
                and track.verification_status in _VERIFIED_STATUSES,
                estimated_annual_cost_usd=float(track.estimated_annual_cost_usd)
                if track is not None and track.estimated_annual_cost_usd is not None
                else None,
                cost_verified=track is not None and track.verification_status in _VERIFIED_STATUSES,
            )
        )

    catalog_by_unitid: dict[int, list[_CatalogRow]] = {}
    for unitid, unit_ids in units_by_unitid.items():
        rows: list[_CatalogRow] = []
        for unit_id in unit_ids:
            rows.extend(rows_by_unit_id.get(unit_id, []))
        # Universities with an AcademicUnit but zero Program rows still
        # need to be distinguishable from PARTIAL/UNKNOWN below, so keep
        # unit names available even with no program rows.
        if not rows:
            rows = [
                _CatalogRow(
                    unit_name=unit_name_by_id.get(uid, ""),
                    program_canonical_name="",
                    program_id=-1,
                    degree_level=DegreeLevel.OTHER,
                    min_gpa=None,
                    min_gpa_verified=False,
                    estimated_annual_cost_usd=None,
                    cost_verified=False,
                )
                for uid in unit_ids
            ]
        catalog_by_unitid[unitid] = rows
    return catalog_by_unitid


def _match_program(
    catalog_by_unitid: dict[int, list[_CatalogRow]], unitid: int, profile: RecommendationProfile
) -> _ProgramMatch:
    """Best-effort match of the requested category/program name against
    this university's catalog data. Deliberately conservative: absence of
    a Program row means UNKNOWN, never CONFIRMED-by-default (§5.3) — the
    large majority of universities will resolve UNKNOWN today, since only
    a handful of pilot schools have any Phase 2 catalog data yet. That's
    expected, not a bug.
    """
    rows = catalog_by_unitid.get(unitid)
    if not rows:
        return _ProgramMatch(ProgramAvailability.UNKNOWN, None, None, False, None, False)

    wanted_level = _CATEGORY_DEGREE_LEVEL.get(profile.program_category)
    keywords = _CATEGORY_KEYWORDS.get(profile.program_category)
    if profile.program_category == ProgramCategory.GENERAL or keywords is None:
        keywords = (profile.program_name.lower(),) if profile.program_name else ()

    for row in rows:
        if row.program_id == -1:
            continue  # placeholder for "unit exists, no programs at all"
        name = row.program_canonical_name.lower()
        if not any(kw in name for kw in keywords if kw):
            continue
        if wanted_level is not None and row.degree_level != wanted_level:
            continue
        return _ProgramMatch(
            availability=ProgramAvailability.CONFIRMED,
            program_id=row.program_id,
            min_gpa=row.min_gpa,
            min_gpa_verified=row.min_gpa_verified,
            estimated_annual_cost_usd=row.estimated_annual_cost_usd,
            cost_verified=row.cost_verified,
        )

    # No direct Program match, but the university has *some* catalog
    # presence (at least one AcademicUnit on file) — a plausibly-related
    # department name is enough for PARTIAL, otherwise it's UNKNOWN in
    # substance even though a unit row exists.
    related = any(any(kw in row.unit_name.lower() for kw in keywords if kw) for row in rows)
    if related:
        return _ProgramMatch(ProgramAvailability.PARTIAL, None, None, False, None, False)
    return _ProgramMatch(ProgramAvailability.UNKNOWN, None, None, False, None, False)


def score_university(
    catalog_by_unitid: dict[int, list[_CatalogRow]],
    university: University,
    profile: RecommendationProfile,
) -> ScoredInstitution:
    match = _match_program(catalog_by_unitid, university.unitid, profile)

    components = {
        "academic_fit": _score_academic_fit(profile.gpa, profile.gpa_scale, match),
        "cost_fit": _score_cost_fit(profile.budget_max_usd, match),
        "reputation_fit": _score_reputation_fit(university.carnegie_classification),
        "program_fit": _score_program_fit(match),
    }
    weights = _PRESET_WEIGHTS[profile.priority]
    overall = _weighted_average(components, weights)
    confidence = _data_confidence(components)
    positive, warnings, unknown = _build_reasons(profile, match, components)

    # "Comfortable fit" (§5.9): GPA comfortably clears a *verified*
    # requirement — not an admission-probability judgment, just whether
    # the academic_fit component landed in its highest bucket on real,
    # sourced data rather than a neutral fallback guess.
    academic = components["academic_fit"]
    is_comfortable_fit = (
        academic.value is not None
        and academic.value >= _COMFORTABLE_FIT_ACADEMIC_THRESHOLD
        and academic.verified
    )

    # rank/category/is_primary_shortlist are placeholders here — only
    # recommend() knows an institution's position in the full ranked set
    # (§5.8); it fills these in via dataclasses.replace() after sorting.
    return ScoredInstitution(
        unitid=university.unitid,
        program_id=match.program_id,
        match_score=round(overall),
        data_confidence=confidence,
        program_availability=match.availability,
        component_scores={name: c.value for name, c in components.items()},
        is_comfortable_fit=is_comfortable_fit,
        positive_reasons=positive,
        warnings=warnings,
        unknown_facts=unknown,
    )


def _degree_level_eligible(university: University, degree_level: DegreeLevel) -> bool:
    """Hard institution-level pre-filter, distinct from program_availability
    (§5.3): whether a specific CS program exists is genuinely uncertain for
    most of the database today (UNKNOWN is fine, still recommendable), but
    whether an institution grants graduate degrees *at all* is a real,
    IPEDS-sourced fact, not an unknown — a bachelor's-only college should
    never be recommended for a master's request. Uses the same
    already-vetted `masters_granting` heuristic and `highest_degree_level`
    (HLOFFER) fields documented in models/university.py, not new logic.
    """
    if degree_level == DegreeLevel.MASTERS:
        return university.masters_granting
    if degree_level == DegreeLevel.DOCTORAL:
        return university.highest_degree_level == 9  # HLOFFER 9 = "Doctor's degree"
    return True  # certificate/other: no institution-level signal to filter on yet


def _geography_eligible(
    university: University, preferred_states: Optional[tuple[str, ...]]
) -> bool:
    """Hard filter, not a scoring signal (§5.4, revised 2026-09-11): if a
    student states preferred states, a school outside them must never
    appear in the shortlist, no matter its score on every other axis.
    Unset `preferred_states` means nationwide, no filtering. A university
    with no recorded state is excluded when a preference is stated —
    state is essentially always populated in this dataset (real IPEDS
    data), so treating "we don't even know the state" as satisfying an
    explicit hard geographic requirement would be the wrong direction to
    err in for a stated constraint, unlike the softer §5.2(b) tolerance
    for genuinely sparse program-level facts.
    """
    if not preferred_states:
        return True
    if not university.state:
        return False
    wanted = {s.upper() for s in preferred_states}
    return university.state.upper() in wanted


def _apply_comfortable_fit_floor(
    scored: list[ScoredInstitution], limit: int
) -> list[ScoredInstitution]:
    """§5.9: guarantee at least MIN_COMFORTABLE_FIT_COUNT comfortable-fit
    results (§5.9's definition — verified GPA comfortably clears a real
    requirement) in the shortlist, answering FULL_HANDOFF.md §8's
    "minimum safety count" without any admission-probability judgment.
    `scored` must already be sorted by match_score descending.
    """
    top = list(scored[:limit])
    comfortable_count = sum(1 for s in top if s.is_comfortable_fit)
    if comfortable_count >= MIN_COMFORTABLE_FIT_COUNT:
        return top

    need = MIN_COMFORTABLE_FIT_COUNT - comfortable_count
    top_unitids = {s.unitid for s in top}
    # `scored` is already sorted, so this yields the next-best
    # comfortable-fit candidates outside the naive top, best first.
    backfill_candidates = [
        s for s in scored if s.unitid not in top_unitids and s.is_comfortable_fit
    ]
    # Worst-ranked non-comfortable entries in `top` are displaced first —
    # rank 1 is never bumped for this.
    displaceable = sorted((s for s in top if not s.is_comfortable_fit), key=lambda s: s.match_score)

    result = list(top)
    for candidate in backfill_candidates:
        if need <= 0 or not displaceable:
            break
        to_remove = displaceable.pop(0)
        result = [s for s in result if s.unitid != to_remove.unitid]
        result.append(
            dataclasses.replace(
                candidate,
                positive_reasons=[
                    *candidate.positive_reasons,
                    "Included to ensure your shortlist has comfortably-verified options",
                ],
            )
        )
        need -= 1
    return result


def recommend(
    session: Session,
    profile: RecommendationProfile,
    *,
    limit: int = TOP_N,
) -> list[ScoredInstitution]:
    """A ranked top-`limit` shortlist (§5.8, revised 2026-09-11), not a
    broad percentile spread — everything outside the top `limit` is not
    part of the response at all (it still exists on the map as a neutral
    background marker via GET /universities/map, unaffected by this).
    Within the returned set, `category` is assigned by rank position
    (top_fit/good_fit/explore) and `is_primary_shortlist` marks rank 1-15
    vs. the 16-20 "alternatives" band — both independent of
    `data_confidence`, which stays a per-result honesty signal, not a
    ranking or inclusion criterion (§10). A comfortable-fit floor (§5.9)
    may swap a small number of lower-ranked, non-comfortable entries for
    higher-confidence ones outside the naive top; every swapped-in entry
    is tagged in its own `positive_reasons`, never a silent reorder.
    """
    universities = (
        session.execute(select(University).where(University.active.is_(True))).scalars().all()
    )
    universities = [u for u in universities if _geography_eligible(u, profile.preferred_states)]
    eligible = [u for u in universities if _degree_level_eligible(u, profile.degree_level)]
    catalog_by_unitid = _load_catalog_by_unitid(session)
    scored = [score_university(catalog_by_unitid, u, profile) for u in eligible]
    scored.sort(key=lambda s: s.match_score, reverse=True)

    final_set = _apply_comfortable_fit_floor(scored, limit)
    final_set.sort(key=lambda s: s.match_score, reverse=True)

    return [
        dataclasses.replace(
            result,
            rank=i,
            category=_category_for_rank(i),
            is_primary_shortlist=i <= PRIMARY_SHORTLIST_SIZE,
        )
        for i, result in enumerate(final_set, start=1)
    ]
