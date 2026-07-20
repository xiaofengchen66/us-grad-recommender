from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from us_grad_recommender.models.catalog import (
    AcademicUnit,
    AdmissionRequirement,
    DegreeLevel,
    DegreeType,
    EntityStatus,
    EvidenceSource,
    GrePolicy,
    Modality,
    Program,
    ProgramAlias,
    ProgramAliasType,
    ProgramConcentration,
    ProgramTrack,
    ProgramTrackDeadline,
    RequirementType,
    SourceSnapshot,
    SourceType,
    TrackType,
    UnitType,
)
from us_grad_recommender.models.common import VerificationStatus
from us_grad_recommender.models.university import Sector, University

TODAY = date(2026, 7, 20)


def make_university(unitid: int = 900001, **overrides) -> University:
    defaults = dict(
        unitid=unitid,
        canonical_name="Test University",
        sector=Sector.PUBLIC,
        masters_granting=True,
        active=True,
        ipeds_year=2023,
        source_dataset="IPEDS HD2023",
        last_verified_at=TODAY,
    )
    defaults.update(overrides)
    return University(**defaults)


def make_academic_unit(unitid: int = 900001, **overrides) -> AcademicUnit:
    defaults = dict(
        unitid=unitid,
        unit_type=UnitType.DEPARTMENT,
        name="Department of Computer Science",
        last_verified_at=TODAY,
    )
    defaults.update(overrides)
    return AcademicUnit(**defaults)


def make_degree_type(code: str = "MS", **overrides) -> DegreeType:
    defaults = dict(code=code, label="Master of Science", level=DegreeLevel.MASTERS)
    defaults.update(overrides)
    return DegreeType(**defaults)


def make_program(academic_unit: AcademicUnit, degree_type: DegreeType, **overrides) -> Program:
    defaults = dict(
        academic_unit=academic_unit,
        degree_type=degree_type,
        raw_degree_name="M.S.",
        canonical_name="Computer Science",
        last_verified_at=TODAY,
    )
    defaults.update(overrides)
    return Program(**defaults)


def make_track(program: Program, **overrides) -> ProgramTrack:
    defaults = dict(
        program=program,
        track_name="Thesis Option",
        track_type=TrackType.THESIS,
        last_verified_at=TODAY,
    )
    defaults.update(overrides)
    return ProgramTrack(**defaults)


@pytest.fixture()
def base_chain(db_session):
    """A University -> AcademicUnit -> DegreeType -> Program -> ProgramTrack
    chain, committed, for tests that just need something to attach to."""
    # University and AcademicUnit are linked only by a raw matching unitid
    # (no ORM relationship — see catalog.py's module docstring for why),
    # so unit-of-work has no dependency edge to order them by; the
    # university must be flushed first explicitly.
    university = make_university()
    db_session.add(university)
    db_session.flush()

    unit = make_academic_unit()
    degree_type = make_degree_type()
    program = make_program(unit, degree_type)
    track = make_track(program)

    db_session.add_all([unit, degree_type, program, track])
    db_session.commit()
    return {
        "university": university,
        "unit": unit,
        "degree_type": degree_type,
        "program": program,
        "track": track,
    }


# --- basic round trips -------------------------------------------------


def test_full_chain_round_trip(db_session, base_chain):
    track_id = base_chain["track"].id
    db_session.expire_all()

    track = db_session.get(ProgramTrack, track_id)
    assert track.track_name == "Thesis Option"
    assert track.program.canonical_name == "Computer Science"
    assert track.program.academic_unit.name == "Department of Computer Science"
    assert track.program.degree_type.code == "MS"


def test_defaults_are_unverified_and_raw(db_session, base_chain):
    db_session.expire_all()
    program = db_session.get(Program, base_chain["program"].id)
    assert program.status == EntityStatus.UNVERIFIED
    assert program.verification_status == VerificationStatus.RAW

    track = db_session.get(ProgramTrack, base_chain["track"].id)
    assert track.status == EntityStatus.UNVERIFIED
    assert track.verification_status == VerificationStatus.RAW
    assert track.modality == Modality.UNSPECIFIED
    assert track.gre_policy == GrePolicy.UNSPECIFIED


# --- self-referencing academic_units hierarchy --------------------------


def test_academic_unit_self_referencing_hierarchy(db_session):
    university = make_university()
    db_session.add(university)
    db_session.flush()

    college = make_academic_unit(
        unitid=900001, unit_type=UnitType.COLLEGE, name="College of Engineering"
    )
    db_session.add(college)
    db_session.flush()

    department = make_academic_unit(
        unitid=900001,
        unit_type=UnitType.DEPARTMENT,
        name="Department of Computer Science",
        parent_unit_id=college.id,
    )
    db_session.add(department)
    db_session.commit()
    db_session.expire_all()

    department = db_session.get(AcademicUnit, department.id)
    assert department.parent.name == "College of Engineering"

    college = db_session.get(AcademicUnit, college.id)
    assert [c.name for c in college.children] == ["Department of Computer Science"]


# --- program-level children: aliases, tracks, concentrations ------------


def test_program_alias(db_session, base_chain):
    program = base_chain["program"]
    program.aliases.append(
        ProgramAlias(
            alias="MSCS", alias_type=ProgramAliasType.COMMON_ABBREVIATION, source="catalog"
        )
    )
    db_session.commit()
    db_session.expire_all()

    program = db_session.get(Program, program.id)
    assert [a.alias for a in program.aliases] == ["MSCS"]


def test_program_concentration_optionally_scoped_to_track(db_session, base_chain):
    program = base_chain["program"]
    track = base_chain["track"]

    unscoped = ProgramConcentration(
        program_id=program.id, name="Machine Learning", last_verified_at=TODAY
    )
    scoped = ProgramConcentration(
        program_id=program.id, program_track_id=track.id, name="Systems", last_verified_at=TODAY
    )
    db_session.add_all([unscoped, scoped])
    db_session.commit()
    db_session.expire_all()

    program = db_session.get(Program, program.id)
    by_name = {c.name: c for c in program.concentrations}
    assert by_name["Machine Learning"].program_track_id is None
    assert by_name["Systems"].program_track_id == track.id


def test_program_track_deadline_and_admission_requirement(db_session, base_chain):
    track = base_chain["track"]

    deadline = ProgramTrackDeadline(
        track=track,
        intake_term="Fall 2027",
        application_deadline=date(2026, 12, 1),
        deadline_raw_text="Applications due December 1 for Fall 2027 admission.",
        last_verified_at=TODAY,
    )
    requirement = AdmissionRequirement(
        track=track,
        requirement_type=RequirementType.GPA,
        structured_value={"min": 3.0, "scale": 4.0},
        raw_text="Minimum GPA of 3.0 on a 4.0 scale.",
        last_verified_at=TODAY,
    )
    db_session.add_all([deadline, requirement])
    db_session.commit()
    db_session.expire_all()

    track = db_session.get(ProgramTrack, track.id)
    assert track.deadlines[0].intake_term == "Fall 2027"
    assert track.admission_requirements[0].structured_value == {"min": 3.0, "scale": 4.0}


# --- cascade deletes ------------------------------------------------------


def test_deleting_program_cascades_to_tracks_aliases_concentrations(db_session, base_chain):
    program = base_chain["program"]
    track = base_chain["track"]
    program.aliases.append(
        ProgramAlias(
            alias="MSCS", alias_type=ProgramAliasType.COMMON_ABBREVIATION, source="catalog"
        )
    )
    db_session.add(
        ProgramConcentration(program=program, name="Machine Learning", last_verified_at=TODAY)
    )
    db_session.commit()

    track_id = track.id
    db_session.delete(program)
    db_session.commit()

    assert db_session.get(ProgramTrack, track_id) is None
    assert db_session.query(ProgramAlias).count() == 0
    assert db_session.query(ProgramConcentration).count() == 0


def test_deleting_track_cascades_to_deadlines_and_requirements(db_session, base_chain):
    track = base_chain["track"]
    db_session.add(
        ProgramTrackDeadline(
            track=track,
            intake_term="Fall 2027",
            deadline_raw_text="Rolling admission.",
            is_rolling=True,
            last_verified_at=TODAY,
        )
    )
    db_session.add(
        AdmissionRequirement(
            track=track,
            requirement_type=RequirementType.GPA,
            raw_text="3.0 minimum.",
            last_verified_at=TODAY,
        )
    )
    db_session.commit()

    db_session.delete(track)
    db_session.commit()

    assert db_session.query(ProgramTrackDeadline).count() == 0
    assert db_session.query(AdmissionRequirement).count() == 0


# --- unique constraints ----------------------------------------------------


def test_duplicate_program_identity_rejected(db_session, base_chain):
    unit = base_chain["unit"]
    degree_type = base_chain["degree_type"]
    db_session.add(make_program(unit, degree_type))  # exact duplicate of base_chain's program

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_program_alias_rejected(db_session, base_chain):
    program = base_chain["program"]
    db_session.add(
        ProgramAlias(
            program_id=program.id, alias="MSCS", alias_type=ProgramAliasType.OTHER, source="x"
        )
    )
    db_session.commit()

    db_session.add(
        ProgramAlias(
            program_id=program.id, alias="MSCS", alias_type=ProgramAliasType.OTHER, source="y"
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_track_deadline_intake_term_rejected(db_session, base_chain):
    track = base_chain["track"]
    db_session.add(
        ProgramTrackDeadline(
            track=track, intake_term="Fall 2027", deadline_raw_text="a", last_verified_at=TODAY
        )
    )
    db_session.commit()

    db_session.add(
        ProgramTrackDeadline(
            track=track, intake_term="Fall 2027", deadline_raw_text="b", last_verified_at=TODAY
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_evidence_source_rejected(db_session):
    university = make_university()
    db_session.add(university)
    db_session.flush()

    db_session.add(
        EvidenceSource(
            unitid=university.unitid,
            source_type=SourceType.ACADEMIC_CATALOG,
            base_url="https://catalog.example.edu",
        )
    )
    db_session.commit()

    db_session.add(
        EvidenceSource(
            unitid=university.unitid,
            source_type=SourceType.DEPARTMENT_PAGE,
            base_url="https://catalog.example.edu",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --- FK enforcement ---------------------------------------------------------


def test_academic_unit_requires_valid_unitid(db_session):
    db_session.add(make_academic_unit(unitid=999999999))  # no such university
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --- source_snapshots: immutable capture + ON DELETE SET NULL -------------


def test_source_snapshot_and_last_seen_set_null_on_delete(db_session, base_chain):
    university = base_chain["university"]
    source = EvidenceSource(
        unitid=university.unitid,
        source_type=SourceType.ACADEMIC_CATALOG,
        base_url="https://catalog.example.edu",
    )
    db_session.add(source)
    db_session.flush()

    snapshot = SourceSnapshot(
        evidence_source_id=source.id,
        url="https://catalog.example.edu/cs-ms",
        retrieved_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        content_hash="abc123",
        raw_content="<html>...</html>",
    )
    db_session.add(snapshot)
    db_session.flush()

    program = base_chain["program"]
    program.last_seen_snapshot_id = snapshot.id
    db_session.commit()

    snapshot_id = snapshot.id
    db_session.delete(snapshot)
    db_session.commit()
    db_session.expire_all()

    program = db_session.get(Program, program.id)
    assert program.last_seen_snapshot_id is None
    assert db_session.get(SourceSnapshot, snapshot_id) is None
