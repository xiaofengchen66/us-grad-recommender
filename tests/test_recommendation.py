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


def test_missing_optional_preference_excluded_not_zeroed(db_session):
    """The core correctness rule from the design doc §5.2: not providing
    budget/location must exclude that component from the score entirely,
    not silently score it as 0."""
    unitid = 910004
    university = make_university(unitid)
    db_session.add(university)
    db_session.commit()
    catalog = _load_catalog_by_unitid(db_session)

    no_budget = score_university(catalog, university, base_profile(budget_max_usd=None))
    assert no_budget.component_scores["cost_fit"] is None

    no_location = score_university(catalog, university, base_profile(preferred_states=None))
    assert no_location.component_scores["location_fit"] is None

    # Excluding a component must not be equivalent to scoring it 0 — the
    # overall score with cost excluded should differ from (generally be
    # higher than) the same profile with an obviously-unaffordable budget.
    with_bad_budget = score_university(
        catalog, university, base_profile(budget_max_usd=1.0)
    )
    assert with_bad_budget.component_scores["cost_fit"] is not None
    assert with_bad_budget.match_score < no_budget.match_score


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


def test_low_confidence_forces_insufficient_data_category(db_session):
    unitid = 910006
    university = make_university(unitid, carnegie_classification=None)
    db_session.add(university)
    db_session.commit()
    catalog = _load_catalog_by_unitid(db_session)

    result = score_university(catalog, university, base_profile())

    assert result.data_confidence == DataConfidence.LOW
    assert result.category == RecommendationCategory.INSUFFICIENT_DATA


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
