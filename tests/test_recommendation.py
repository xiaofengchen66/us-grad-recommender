from __future__ import annotations

from datetime import date

from us_grad_recommender.models.catalog import (
    AcademicUnit,
    DegreeLevel,
    DegreeType,
    EntityStatus,
    Program,
    ProgramTrack,
    UnitType,
)
from us_grad_recommender.models.common import VerificationStatus
from us_grad_recommender.models.university import Sector, University
from us_grad_recommender.recommendation import (
    DataConfidence,
    GradingScale,
    ProgramAvailability,
    ProgramCategory,
    RecommendationCategory,
    RecommendationProfile,
    _load_catalog_by_unitid,
    recommend,
    score_university,
)

TODAY = date(2026, 9, 10)


def make_university(unitid: int, **overrides) -> University:
    defaults = dict(
        unitid=unitid,
        canonical_name=f"Test University {unitid}",
        state="NY",
        sector=Sector.PUBLIC,
        masters_granting=True,
        carnegie_classification=15,  # Doctoral Universities: Highest Research Activity
        active=True,
        ipeds_year=2023,
        source_dataset="IPEDS HD2023",
        last_verified_at=TODAY,
    )
    defaults.update(overrides)
    return University(**defaults)


def make_academic_unit(
    unitid: int, name: str = "Department of Computer Science"
) -> AcademicUnit:
    return AcademicUnit(
        unitid=unitid, unit_type=UnitType.DEPARTMENT, name=name, last_verified_at=TODAY
    )


def make_degree_type(code: str = "MS", level: DegreeLevel = DegreeLevel.MASTERS) -> DegreeType:
    return DegreeType(code=code, label="Master of Science", level=level)


def base_profile(**overrides) -> RecommendationProfile:
    defaults = dict(
        degree_level=DegreeLevel.MASTERS,
        program_category=ProgramCategory.CS_MASTERS,
        program_name="Computer Science",
        gpa=3.6,
        gpa_scale=GradingScale.SCALE_4_0,
    )
    defaults.update(overrides)
    return RecommendationProfile(**defaults)


def test_confirmed_program_scores_higher_than_unknown(db_session):
    confirmed_unitid, unknown_unitid = 910001, 910002
    university_confirmed = make_university(confirmed_unitid)
    university_unknown = make_university(unknown_unitid)
    db_session.add_all([university_confirmed, university_unknown])
    db_session.flush()

    unit = make_academic_unit(confirmed_unitid)
    degree_type = make_degree_type()
    program = Program(
        academic_unit=unit,
        degree_type=degree_type,
        raw_degree_name="M.S.",
        canonical_name="Computer Science",
        status=EntityStatus.ACTIVE,
        verification_status=VerificationStatus.DOCUMENT_VERIFIED,
        last_verified_at=TODAY,
    )
    track = ProgramTrack(
        program=program,
        track_name="Thesis",
        min_gpa=3.0,
        verification_status=VerificationStatus.DOCUMENT_VERIFIED,
        last_verified_at=TODAY,
    )
    db_session.add_all([unit, degree_type, program, track])
    db_session.commit()

    catalog = _load_catalog_by_unitid(db_session)
    profile = base_profile()

    confirmed_result = score_university(catalog, university_confirmed, profile)
    unknown_result = score_university(catalog, university_unknown, profile)

    assert confirmed_result.program_availability == ProgramAvailability.CONFIRMED
    assert confirmed_result.program_id == program.id
    assert unknown_result.program_availability == ProgramAvailability.UNKNOWN
    assert unknown_result.program_id is None
    assert confirmed_result.match_score > unknown_result.match_score


def test_discontinued_program_never_matches_as_confirmed(db_session):
    """Regression for a real HIGH finding: a DISCONTINUED (or PAUSED)
    program — the real lifecycle state PHASE_2_CATALOG_DESIGN.md §6/§12
    describes for a program that repeatedly 404s on re-crawl — must never
    be recommended as CONFIRMED. UNVERIFIED (the realistic default for
    most real data) is deliberately NOT excluded by the same fix — only
    genuinely known-gone states are."""
    unitid = 910015
    university = make_university(unitid)
    db_session.add(university)
    db_session.flush()
    unit = make_academic_unit(unitid)
    degree_type = make_degree_type()
    program = Program(
        academic_unit=unit,
        degree_type=degree_type,
        raw_degree_name="M.S.",
        canonical_name="Computer Science",
        status=EntityStatus.DISCONTINUED,
        last_verified_at=TODAY,
    )
    db_session.add_all([unit, degree_type, program])
    db_session.commit()

    catalog = _load_catalog_by_unitid(db_session)
    result = score_university(catalog, university, base_profile())

    assert result.program_availability != ProgramAvailability.CONFIRMED
    assert "confirmed" not in " ".join(result.positive_reasons).lower()


def test_parsed_verification_does_not_count_as_comfortable_fit(db_session):
    """Regression for a real MEDIUM finding: PHASE_2_CATALOG_DESIGN.md §10
    excludes PARSED (human-unreviewed) from "Verified" — an
    adapter-extracted, unreviewed min_gpa must not be sufficient basis for
    §5.9's comfortable-fit safety claim, even though PARSED is loose
    enough to still count toward the broader data_confidence bucket."""
    unitid = 910016
    university = make_university(unitid)
    db_session.add(university)
    db_session.flush()
    unit = make_academic_unit(unitid)
    degree_type = make_degree_type()
    program = Program(
        academic_unit=unit,
        degree_type=degree_type,
        raw_degree_name="M.S.",
        canonical_name="Computer Science",
        status=EntityStatus.ACTIVE,
        last_verified_at=TODAY,
    )
    track = ProgramTrack(
        program=program,
        track_name="Thesis",
        min_gpa=2.5,  # would otherwise comfortably clear gpa=3.6
        verification_status=VerificationStatus.PARSED,
        last_verified_at=TODAY,
    )
    db_session.add_all([unit, degree_type, program, track])
    db_session.commit()

    catalog = _load_catalog_by_unitid(db_session)
    result = score_university(catalog, university, base_profile())

    assert result.component_scores["academic_fit"] == 90.0  # PARSED still scores it
    assert result.is_comfortable_fit is False  # but doesn't count as comfortable-fit


def test_non_4_0_gpa_scale_falls_back_neutrally_not_naive_subtraction(db_session):
    """Regression for a real BLOCKING bug caught by PR #17's automated
    review: comparing a raw GPA on an unstated/non-4.0 scale directly
    against a 0-4-normalized min_gpa (e.g. 86 - 3.0 = 83 -> "best possible
    fit") is exactly the naive cross-scale conversion FULL_HANDOFF.md
    §0/§9/§23 forbid. A GPA reported on any scale other than SCALE_4_0
    must fall back to the neutral academic_fit value instead of being
    compared."""
    unitid = 910010
    university = make_university(unitid)
    db_session.add(university)
    db_session.flush()
    unit = make_academic_unit(unitid)
    degree_type = make_degree_type()
    program = Program(
        academic_unit=unit,
        degree_type=degree_type,
        raw_degree_name="M.S.",
        canonical_name="Computer Science",
        status=EntityStatus.ACTIVE,
        last_verified_at=TODAY,
    )
    track = ProgramTrack(program=program, track_name="Thesis", min_gpa=3.0, last_verified_at=TODAY)
    db_session.add_all([unit, degree_type, program, track])
    db_session.commit()
    catalog = _load_catalog_by_unitid(db_session)

    # A 100-point-scale GPA of 86 subtracted naively from min_gpa=3.0
    # would previously read as "83 above the requirement" -> max score.
    other_scale_result = score_university(
        catalog, university, base_profile(gpa=86.0, gpa_scale=GradingScale.OTHER)
    )
    scale_4_0_result = score_university(
        catalog, university, base_profile(gpa=3.6, gpa_scale=GradingScale.SCALE_4_0)
    )

    assert other_scale_result.component_scores["academic_fit"] == 60.0
    assert scale_4_0_result.component_scores["academic_fit"] != 60.0
    assert scale_4_0_result.component_scores["academic_fit"] == 90.0


def test_partial_availability_when_unit_exists_but_no_program(db_session):
    unitid = 910003
    university = make_university(unitid)
    db_session.add(university)
    db_session.flush()
    unit = make_academic_unit(unitid, name="School of Computer Science and Engineering")
    db_session.add(unit)
    db_session.commit()

    catalog = _load_catalog_by_unitid(db_session)
    result = score_university(catalog, university, base_profile())

    assert result.program_availability == ProgramAvailability.PARTIAL
    assert result.program_id is None


def test_partial_scores_higher_than_unknown_for_program_fit(db_session):
    """Regression for a real BLOCKING bug: PARTIAL previously scored 55
    while UNKNOWN's neutral fallback was 60 — the exact inverse of the
    documented CONFIRMED > PARTIAL > UNKNOWN ordering (§5.3), meaning a
    university with real (if circumstantial) evidence of the program
    ranked *worse* than one with zero catalog data at all."""
    partial_unitid, unknown_unitid = 910012, 910013
    partial_university = make_university(partial_unitid)
    unknown_university = make_university(unknown_unitid)
    db_session.add_all([partial_university, unknown_university])
    db_session.flush()
    unit = make_academic_unit(partial_unitid, name="School of Computer Science and Engineering")
    db_session.add(unit)
    db_session.commit()

    catalog = _load_catalog_by_unitid(db_session)
    partial_result = score_university(catalog, partial_university, base_profile())
    unknown_result = score_university(catalog, unknown_university, base_profile())

    assert partial_result.program_availability == ProgramAvailability.PARTIAL
    assert unknown_result.program_availability == ProgramAvailability.UNKNOWN
    assert (
        partial_result.component_scores["program_fit"]
        > unknown_result.component_scores["program_fit"]
    )


def test_missing_optional_preference_excluded_not_zeroed(db_session):
    """The core correctness rule from the design doc §5.2: not providing
    an optional preference like budget must exclude that component from
    the score entirely, not silently score it as 0."""
    unitid = 910004
    university = make_university(unitid)
    db_session.add(university)
    db_session.commit()
    catalog = _load_catalog_by_unitid(db_session)

    no_budget = score_university(catalog, university, base_profile(budget_max_usd=None))
    assert no_budget.component_scores["cost_fit"] is None

    # Excluding a component must not be equivalent to scoring it 0 — the
    # overall score with cost excluded should differ from (generally be
    # higher than) the same profile with an obviously-unaffordable budget.
    with_bad_budget = score_university(
        catalog, university, base_profile(budget_max_usd=1.0)
    )
    assert with_bad_budget.component_scores["cost_fit"] is not None
    assert with_bad_budget.match_score < no_budget.match_score


def test_no_location_fit_component_geography_is_a_filter_not_a_score(db_session):
    """§5.4 (revised 2026-09-11): geographic preference is a hard filter
    on the candidate pool, not a scoring component — there is no
    location_fit key at all, regardless of whether preferred_states is
    set."""
    unitid = 910011
    university = make_university(unitid, state="TX")
    db_session.add(university)
    db_session.commit()
    catalog = _load_catalog_by_unitid(db_session)

    without_pref = score_university(catalog, university, base_profile(preferred_states=None))
    with_pref = score_university(
        catalog, university, base_profile(preferred_states=("TX",))
    )
    assert "location_fit" not in without_pref.component_scores
    assert "location_fit" not in with_pref.component_scores


def test_unverified_institution_side_fact_lowers_confidence_not_excluded(db_session):
    """Distinguish §5.2(a) (user didn't ask -> excluded) from §5.2(b) (user
    did ask, institution data unverified -> stays active, neutral
    fallback, confidence hit)."""
    unitid = 910005
    university = make_university(unitid, carnegie_classification=None)
    db_session.add(university)
    db_session.commit()
    catalog = _load_catalog_by_unitid(db_session)

    result = score_university(catalog, university, base_profile())

    # reputation_fit is always active (§5.4), but with no carnegie data it
    # must fall back neutrally rather than being excluded like an
    # unprovided optional preference.
    assert result.component_scores["reputation_fit"] is not None
    assert result.component_scores["reputation_fit"] == 60.0


def test_carnegie_not_applicable_sentinel_treated_as_unknown(db_session):
    """IPEDS uses -2 for 'not in the Carnegie universe' (real, ~95 rows in
    the dev DB) — this must fall back neutrally like a missing value, not
    be scored as if it were a real classification bucket."""
    unitid = 910009
    university = make_university(unitid, carnegie_classification=-2)
    db_session.add(university)
    db_session.commit()
    catalog = _load_catalog_by_unitid(db_session)

    result = score_university(catalog, university, base_profile())

    assert result.component_scores["reputation_fit"] == 60.0


def test_low_confidence_result_can_still_rank_but_shows_low_confidence(db_session):
    """§5.8 (revised): rank/category are about standing among candidates,
    not a claim about data quality — a low-confidence result isn't forced
    into a special category, but data_confidence must still say Low."""
    unitid = 910006
    university = make_university(unitid, carnegie_classification=None)
    db_session.add(university)
    db_session.commit()
    catalog = _load_catalog_by_unitid(db_session)

    result = score_university(catalog, university, base_profile())

    assert result.data_confidence == DataConfidence.LOW
    # score_university() alone doesn't know rank/category yet (§5.8's
    # docstring) — those are only meaningful after recommend() sorts.
    assert result.rank == 0


def test_recommend_caps_at_top_20_and_assigns_rank_based_category(db_session):
    for i in range(25):
        db_session.add(make_university(940000 + i, canonical_name=f"Rank Uni {i}"))
    db_session.commit()

    results = recommend(db_session, base_profile())

    assert len(results) == 20
    ranks = [r.rank for r in results]
    assert ranks == list(range(1, 21))
    for r in results:
        if r.rank <= 5:
            assert r.category == RecommendationCategory.TOP_FIT
        elif r.rank <= 12:
            assert r.category == RecommendationCategory.GOOD_FIT
        else:
            assert r.category == RecommendationCategory.EXPLORE


def test_recommend_primary_shortlist_is_top_15(db_session):
    for i in range(25):
        db_session.add(make_university(950000 + i, canonical_name=f"Shortlist Uni {i}"))
    db_session.commit()

    results = recommend(db_session, base_profile())

    for r in results:
        if r.rank <= 15:
            assert r.is_primary_shortlist is True
        else:
            assert r.is_primary_shortlist is False
    assert sum(1 for r in results if r.is_primary_shortlist) == 15
    assert sum(1 for r in results if not r.is_primary_shortlist) == 5


def test_recommend_with_fewer_than_20_eligible_returns_all(db_session):
    for i in range(5):
        db_session.add(make_university(960000 + i, canonical_name=f"Small Uni {i}"))
    db_session.commit()

    results = recommend(db_session, base_profile())

    assert len(results) == 5
    assert [r.rank for r in results] == [1, 2, 3, 4, 5]
    # A set smaller than both cutoffs (15 primary, 20 total) must still
    # get correct per-rank category/shortlist values, not some
    # small-set special case.
    assert [r.category for r in results] == [RecommendationCategory.TOP_FIT] * 5
    assert all(r.is_primary_shortlist for r in results)


def test_general_category_matches_free_text_program_name(db_session):
    unitid = 910007
    university = make_university(unitid)
    db_session.add(university)
    db_session.flush()
    unit = make_academic_unit(unitid, name="Department of Psychology")
    degree_type = make_degree_type(code="MA", level=DegreeLevel.MASTERS)
    program = Program(
        academic_unit=unit,
        degree_type=degree_type,
        raw_degree_name="M.A.",
        canonical_name="Psychology",
        status=EntityStatus.ACTIVE,
        last_verified_at=TODAY,
    )
    db_session.add_all([unit, degree_type, program])
    db_session.commit()

    catalog = _load_catalog_by_unitid(db_session)
    profile = base_profile(program_category=ProgramCategory.GENERAL, program_name="Psychology")
    result = score_university(catalog, university, profile)

    assert result.program_availability == ProgramAvailability.CONFIRMED
    assert result.program_id == program.id


def test_recommend_is_deterministic_and_sorted(db_session):
    for i in range(5):
        db_session.add(make_university(920000 + i, canonical_name=f"Uni {i}"))
    db_session.commit()

    profile = base_profile()
    first_pass = recommend(db_session, profile)
    second_pass = recommend(db_session, profile)

    assert [r.unitid for r in first_pass] == [r.unitid for r in second_pass]
    assert [r.match_score for r in first_pass] == [r.match_score for r in second_pass]
    scores = [r.match_score for r in first_pass]
    assert scores == sorted(scores, reverse=True)


def test_recommend_excludes_institutions_below_requested_degree_level(db_session):
    """A real, IPEDS-sourced fact (masters_granting=False) must exclude an
    institution outright — this is not the same kind of "unknown" as
    ProgramAvailability.UNKNOWN, it's actual evidence of ineligibility."""
    bachelors_only = make_university(930001, masters_granting=False)
    masters_granting = make_university(930002, masters_granting=True)
    db_session.add_all([bachelors_only, masters_granting])
    db_session.commit()

    results = recommend(db_session, base_profile())

    unitids = {r.unitid for r in results}
    assert 930002 in unitids
    assert 930001 not in unitids


def test_recommend_excludes_inactive_universities(db_session):
    inactive = make_university(931001, active=False)
    active = make_university(931002, active=True)
    db_session.add_all([inactive, active])
    db_session.commit()

    results = recommend(db_session, base_profile())

    unitids = {r.unitid for r in results}
    assert 931002 in unitids
    assert 931001 not in unitids


def test_multi_track_program_scoring_is_deterministic(db_session):
    """Regression for a real MEDIUM finding: without an explicit ORDER BY,
    which ProgramTrack "wins" when a Program has more than one was
    unspecified DB row order, contradicting §5.1's determinism
    requirement. Two tracks with different min_gpa must consistently
    resolve to the same one across repeated calls."""
    unitid = 910014
    university = make_university(unitid)
    db_session.add(university)
    db_session.flush()
    unit = make_academic_unit(unitid)
    degree_type = make_degree_type()
    program = Program(
        academic_unit=unit,
        degree_type=degree_type,
        raw_degree_name="M.S.",
        canonical_name="Computer Science",
        status=EntityStatus.ACTIVE,
        last_verified_at=TODAY,
    )
    db_session.add_all([unit, degree_type, program])
    db_session.flush()
    track_a = ProgramTrack(
        program=program, track_name="Thesis", min_gpa=3.0, last_verified_at=TODAY
    )
    track_b = ProgramTrack(
        program=program, track_name="Non-Thesis", min_gpa=3.8, last_verified_at=TODAY
    )
    db_session.add_all([track_a, track_b])
    db_session.commit()

    first = score_university(_load_catalog_by_unitid(db_session), university, base_profile())
    second = score_university(_load_catalog_by_unitid(db_session), university, base_profile())

    assert first.component_scores["academic_fit"] == second.component_scores["academic_fit"]


def test_preferred_states_is_a_hard_filter_not_a_soft_preference(db_session):
    """The exact scenario that motivated this design: a student who says
    "only NY and CA" must never see an out-of-state school, even one that
    would otherwise outscore everything in-state on every other axis."""
    in_state = make_university(970001, state="CA", carnegie_classification=15)
    out_of_state = make_university(970002, state="WA", carnegie_classification=15)
    db_session.add_all([in_state, out_of_state])
    db_session.commit()

    results = recommend(db_session, base_profile(preferred_states=("CA", "NY")))

    unitids = {r.unitid for r in results}
    assert 970001 in unitids
    assert 970002 not in unitids


def test_preferred_states_excludes_unknown_state_institutions(db_session):
    """A hard, explicitly-stated geographic requirement should err toward
    strictness on a field (state) that's essentially always populated in
    this dataset — unlike the softer tolerance for genuinely sparse
    program-level facts elsewhere in the engine."""
    unknown_state = make_university(970003, state=None)
    db_session.add(unknown_state)
    db_session.commit()

    results = recommend(db_session, base_profile(preferred_states=("CA",)))

    assert 970003 not in {r.unitid for r in results}


def test_comfortable_fit_floor_backfills_when_naturally_absent(db_session):
    """§5.9: if fewer than MIN_COMFORTABLE_FIT_COUNT of the naive top 20
    are comfortable-fit, the engine must pull in verified-GPA candidates
    from outside the naive top rather than leaving the shortlist without
    any comfortable options.

    academic_fit and program_fit are coupled (both depend on finding a
    matched Program/ProgramTrack), so to make 20 "distractor" schools
    genuinely outscore one comfortable-fit school without themselves
    becoming comfortable-fit, distractors win on cost_fit instead:
    verified low cost, but no min_gpa on file (academic_fit stays
    neutral/unverified, so distractors never qualify as comfortable-fit).
    """
    degree_type = make_degree_type()
    db_session.add(degree_type)
    db_session.flush()

    for i in range(20):
        unitid = 980000 + i
        university = make_university(unitid, carnegie_classification=15)
        db_session.add(university)
        db_session.flush()
        unit = make_academic_unit(unitid)
        program = Program(
            academic_unit=unit,
            degree_type=degree_type,
            raw_degree_name="M.S.",
            canonical_name="Computer Science",
            status=EntityStatus.ACTIVE,
            last_verified_at=TODAY,
        )
        track = ProgramTrack(
            program=program,
            track_name="Thesis",
            estimated_annual_cost_usd=5000,  # well under the 30000 budget below
            verification_status=VerificationStatus.DOCUMENT_VERIFIED,
            last_verified_at=TODAY,
        )
        db_session.add_all([unit, program, track])

    # One additional university with a real, verified, comfortably-clearable
    # GPA requirement but no cost data, weaker reputation, and a lower
    # overall score than every distractor above.
    comfortable_uid = 981000
    comfortable_university = make_university(comfortable_uid, carnegie_classification=None)
    db_session.add(comfortable_university)
    db_session.flush()
    unit = make_academic_unit(comfortable_uid)
    program = Program(
        academic_unit=unit,
        degree_type=degree_type,
        raw_degree_name="M.S.",
        canonical_name="Computer Science",
        status=EntityStatus.ACTIVE,
        last_verified_at=TODAY,
    )
    track = ProgramTrack(
        program=program,
        track_name="Thesis",
        min_gpa=2.5,  # comfortably below profile's gpa=3.6 -> diff >= 0.3
        verification_status=VerificationStatus.DOCUMENT_VERIFIED,
        last_verified_at=TODAY,
    )
    db_session.add_all([unit, program, track])
    db_session.commit()

    profile = base_profile(budget_max_usd=30000)
    scored_without_floor = score_university(
        _load_catalog_by_unitid(db_session), comfortable_university, profile
    )
    distractor_score = score_university(
        _load_catalog_by_unitid(db_session),
        db_session.get(University, 980000),
        profile,
    ).match_score
    # Sanity-check the setup actually exercises the floor (comfortable
    # school ranks below the distractors on raw score alone) rather than
    # accidentally passing because it topped the naive ranking anyway.
    assert scored_without_floor.match_score < distractor_score

    results = recommend(db_session, profile)

    result = next(r for r in results if r.unitid == comfortable_uid)
    assert result.is_comfortable_fit is True
    assert any("comfortably-verified" in reason for reason in result.positive_reasons)
    # This test's data only provides one comfortable-fit candidate total,
    # so the floor can only backfill up to what actually exists — it
    # should include exactly that one, not fabricate more.
    assert len([r for r in results if r.is_comfortable_fit]) == 1


def test_comfortable_fit_floor_no_op_when_already_satisfied(db_session):
    """When the naive top 20 already has enough comfortable-fit results,
    the floor must not reorder or tag anything."""
    for i in range(5):
        unitid = 982000 + i
        university = make_university(unitid, carnegie_classification=None)
        db_session.add(university)
        db_session.flush()
        unit = make_academic_unit(unitid)
        degree_type = make_degree_type(code=f"MS{i}")
        program = Program(
            academic_unit=unit,
            degree_type=degree_type,
            raw_degree_name="M.S.",
            canonical_name="Computer Science",
            status=EntityStatus.ACTIVE,
            last_verified_at=TODAY,
        )
        track = ProgramTrack(
            program=program,
            track_name="Thesis",
            min_gpa=2.5,
            verification_status=VerificationStatus.DOCUMENT_VERIFIED,
            last_verified_at=TODAY,
        )
        db_session.add_all([unit, degree_type, program, track])
    db_session.commit()

    results = recommend(db_session, base_profile())

    assert all(
        "comfortably-verified" not in " ".join(r.positive_reasons) for r in results
    )


def test_match_score_never_framed_as_probability(db_session):
    """Structural guard, not just a copy check: the response shape has no
    admission-probability-style field at all."""
    unitid = 910008
    university = make_university(unitid)
    db_session.add(university)
    db_session.commit()
    catalog = _load_catalog_by_unitid(db_session)

    result = score_university(catalog, university, base_profile())

    field_names = set(result.__dataclass_fields__.keys())
    assert "admission_probability" not in field_names
    assert "match_score" in field_names
    assert "data_confidence" in field_names
    assert 0 <= result.match_score <= 100
