from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from us_grad_recommender.catalog_adapters import (
    CourseLeafAdapter,
    PdfCatalogAdapter,
    RawDegreeCandidate,
    RawProgramCandidate,
)
from us_grad_recommender.models.catalog import AcademicUnit, DegreeType, Program, UnitType
from us_grad_recommender.models.review import CatalogEntityType, ReviewReason
from us_grad_recommender.models.university import Sector, University
from us_grad_recommender.parser_pipeline import ingest_program_degrees

TODAY = date(2026, 8, 3)

COURSELEAF_FIXTURES = Path(__file__).parent / "fixtures" / "courseleaf"
PDF_FIXTURES = Path(__file__).parent / "fixtures" / "pdf"

UT_PROGRAM_URL = "https://catalog.utexas.edu/graduate/areas-of-study/natural-sciences/computer-science/"
AAMU_CATALOG_URL = (
    "https://www.aamu.edu/academics/catalogs/_documents/graduate-catalogs/"
    "graduate-catalog-2026-2027.pdf"
)


@pytest.fixture()
def academic_unit(db_session) -> AcademicUnit:
    university = University(
        unitid=900201,
        canonical_name="Test University",
        sector=Sector.PUBLIC,
        masters_granting=True,
        active=True,
        ipeds_year=2023,
        source_dataset="IPEDS HD2023",
        last_verified_at=TODAY,
    )
    db_session.add(university)
    db_session.flush()

    unit = AcademicUnit(
        unitid=900201,
        unit_type=UnitType.DEPARTMENT,
        name="Department of Computer Science",
        last_verified_at=TODAY,
    )
    db_session.add(unit)
    db_session.commit()
    return unit


def test_ingest_real_courseleaf_program_creates_one_row_per_degree(db_session, academic_unit):
    # Real fixture, real adapter output — not hand-constructed. UT
    # Austin's CS program page declares two degrees (MS and PhD) on one
    # page, exercising the "one Program row per matched degree" design.
    content = (COURSELEAF_FIXTURES / "ut_austin_computer_science_program.html").read_bytes()
    degrees = CourseLeafAdapter().extract_degrees(UT_PROGRAM_URL, content)
    assert [d.raw_degree_name for d in degrees] == [
        "Master of Science in Computer Science",
        "Doctor of Philosophy",
    ]
    program = RawProgramCandidate(
        name="Computer Science", program_url=UT_PROGRAM_URL, source_url=UT_PROGRAM_URL
    )

    outcomes = ingest_program_degrees(
        db_session,
        academic_unit_id=academic_unit.id,
        program=program,
        degrees=degrees,
        last_verified_at=TODAY,
    )

    assert len(outcomes) == 2
    ms_outcome, phd_outcome = outcomes

    assert ms_outcome.program is not None
    assert ms_outcome.program.degree_type_code == "MS"
    assert ms_outcome.program.canonical_name == "Computer Science"
    assert ms_outcome.program.raw_degree_name == "Master of Science in Computer Science"
    assert ms_outcome.program.verification_status.value == "parsed"
    assert ms_outcome.review_task is not None
    assert ms_outcome.review_task.reason == ReviewReason.FIRST_SEEN
    assert ms_outcome.review_task.entity_id == ms_outcome.program.id

    assert phd_outcome.program is not None
    assert phd_outcome.program.degree_type_code == "PHD"
    assert phd_outcome.program.canonical_name == "Computer Science"

    # Both degrees, same subject -> two distinct Program rows (this is
    # exactly what uq_program_identity's degree_type_code column is for).
    assert ms_outcome.program.id != phd_outcome.program.id


def test_ingest_real_pdf_program_creates_program_row(db_session, academic_unit):
    content = (PDF_FIXTURES / "aamu_biology_program.pdf").read_bytes()
    degrees = PdfCatalogAdapter().extract_degrees(AAMU_CATALOG_URL, content)
    assert [d.raw_degree_name for d in degrees] == ["Master of Science"]
    program = RawProgramCandidate(
        name="Biology", program_url=f"{AAMU_CATALOG_URL}#page=1", source_url=AAMU_CATALOG_URL
    )

    outcomes = ingest_program_degrees(
        db_session,
        academic_unit_id=academic_unit.id,
        program=program,
        degrees=degrees,
        last_verified_at=TODAY,
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.program is not None
    assert outcome.program.degree_type_code == "MS"
    assert outcome.program.canonical_name == "Biology"
    assert outcome.program.program_url == f"{AAMU_CATALOG_URL}#page=1"


def test_ingest_reuses_existing_degree_type_row(db_session, academic_unit):
    program_a = RawProgramCandidate(name="Biology", program_url=None, source_url="https://x/")
    program_b = RawProgramCandidate(name="Chemistry", program_url=None, source_url="https://x/")
    degrees = [RawDegreeCandidate(raw_degree_name="Master of Science", source_url="https://x/")]

    ingest_program_degrees(
        db_session,
        academic_unit_id=academic_unit.id,
        program=program_a,
        degrees=degrees,
        last_verified_at=TODAY,
    )
    ingest_program_degrees(
        db_session,
        academic_unit_id=academic_unit.id,
        program=program_b,
        degrees=degrees,
        last_verified_at=TODAY,
    )

    ms_rows = db_session.query(DegreeType).filter_by(code="MS").all()
    assert len(ms_rows) == 1


def test_ingest_canonicalizes_whitespace_only(db_session, academic_unit):
    program = RawProgramCandidate(
        name="  Computer   Science  ", program_url=None, source_url="https://x/"
    )
    degrees = [RawDegreeCandidate(raw_degree_name="Master of Science", source_url="https://x/")]

    outcomes = ingest_program_degrees(
        db_session,
        academic_unit_id=academic_unit.id,
        program=program,
        degrees=degrees,
        last_verified_at=TODAY,
    )
    assert outcomes[0].program is not None
    assert outcomes[0].program.canonical_name == "Computer Science"


def test_ingest_unmapped_degree_type_creates_no_program_row(db_session, academic_unit):
    # "Juris Doctor" is a real degree name, just not one of the 10 in
    # _DEGREE_TYPE_TABLE (none of the real fixtures inspected during
    # Phase 2.2B pilot scoping happened to include a J.D. program) — the
    # exact case this design is meant to route to review rather than
    # guess at.
    program = RawProgramCandidate(name="Law", program_url=None, source_url="https://x/")
    degrees = [RawDegreeCandidate(raw_degree_name="Juris Doctor", source_url="https://x/")]

    outcomes = ingest_program_degrees(
        db_session,
        academic_unit_id=academic_unit.id,
        program=program,
        degrees=degrees,
        last_verified_at=TODAY,
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.program is None
    assert outcome.review_task is not None
    assert outcome.review_task.reason == ReviewReason.LOW_CONFIDENCE
    assert outcome.review_task.entity_type == CatalogEntityType.ACADEMIC_UNIT
    assert outcome.review_task.entity_id == academic_unit.id
    assert outcome.review_task.field_name == "unmapped_degree_type:Juris Doctor"

    assert db_session.query(Program).count() == 0


def test_ingest_duplicate_program_creates_review_task_pointing_at_existing_row(
    db_session, academic_unit
):
    program = RawProgramCandidate(name="Biology", program_url=None, source_url="https://x/")
    degrees = [RawDegreeCandidate(raw_degree_name="Master of Science", source_url="https://x/")]

    first_outcomes = ingest_program_degrees(
        db_session,
        academic_unit_id=academic_unit.id,
        program=program,
        degrees=degrees,
        last_verified_at=TODAY,
    )
    original_program = first_outcomes[0].program
    assert original_program is not None

    second_outcomes = ingest_program_degrees(
        db_session,
        academic_unit_id=academic_unit.id,
        program=program,
        degrees=degrees,
        last_verified_at=TODAY,
    )

    assert len(second_outcomes) == 1
    outcome = second_outcomes[0]
    assert outcome.program is None
    assert outcome.review_task is not None
    assert outcome.review_task.reason == ReviewReason.POSSIBLE_DUPLICATE
    assert outcome.review_task.entity_type == CatalogEntityType.PROGRAM
    assert outcome.review_task.entity_id == original_program.id

    # Only one Program row exists — the duplicate attempt did not insert
    # a second one.
    assert db_session.query(Program).count() == 1


def test_ingest_two_degrees_for_same_program_do_not_collide_with_each_other(
    db_session, academic_unit
):
    # Regression guard: MS and PhD for the same subject share
    # academic_unit_id + canonical_name but differ on degree_type_code,
    # so uq_program_identity must not treat them as duplicates of each
    # other.
    program = RawProgramCandidate(name="Physics", program_url=None, source_url="https://x/")
    degrees = [
        RawDegreeCandidate(raw_degree_name="Master of Science", source_url="https://x/"),
        RawDegreeCandidate(raw_degree_name="Doctor of Philosophy", source_url="https://x/"),
    ]

    outcomes = ingest_program_degrees(
        db_session,
        academic_unit_id=academic_unit.id,
        program=program,
        degrees=degrees,
        last_verified_at=TODAY,
    )
    assert all(o.program is not None for o in outcomes)
    assert db_session.query(Program).count() == 2
