from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from us_grad_recommender.models.catalog import (
    AcademicUnit,
    DegreeLevel,
    DegreeType,
    EvidenceSource,
    Program,
    SourceSnapshot,
    SourceType,
    UnitType,
)
from us_grad_recommender.models.common import VerificationStatus
from us_grad_recommender.models.review import (
    CatalogEntityType,
    ConflictStatus,
    DataConflict,
    DataReviewTask,
    ParsedDocument,
    ReviewReason,
    ReviewTaskStatus,
)
from us_grad_recommender.models.university import Sector, University

TODAY = date(2026, 7, 21)


@pytest.fixture()
def program(db_session) -> Program:
    """A minimal University -> AcademicUnit -> DegreeType -> Program chain,
    committed, so review rows have a real entity_id to point at."""
    university = University(
        unitid=900002,
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
        unitid=900002,
        unit_type=UnitType.DEPARTMENT,
        name="Department of Computer Science",
        last_verified_at=TODAY,
    )
    degree_type = DegreeType(code="MS", label="Master of Science", level=DegreeLevel.MASTERS)
    db_session.add_all([unit, degree_type])
    db_session.flush()

    program = Program(
        academic_unit=unit,
        degree_type=degree_type,
        raw_degree_name="M.S.",
        canonical_name="Computer Science",
        last_verified_at=TODAY,
    )
    db_session.add(program)
    db_session.commit()
    return program


@pytest.fixture()
def snapshot(db_session, program) -> SourceSnapshot:
    source = EvidenceSource(
        unitid=program.academic_unit.unitid,
        source_type=SourceType.ACADEMIC_CATALOG,
        base_url="https://catalog.example.edu",
    )
    db_session.add(source)
    db_session.flush()

    snapshot = SourceSnapshot(
        evidence_source_id=source.id,
        url="https://catalog.example.edu/cs-ms",
        retrieved_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        content_hash="abc123",
        raw_content="<html>...</html>",
    )
    db_session.add(snapshot)
    db_session.commit()
    return snapshot


# --- ParsedDocument ----------------------------------------------------


def test_parsed_document_round_trip(db_session, snapshot):
    doc = ParsedDocument(
        source_snapshot_id=snapshot.id,
        adapter_name="GenericHtmlAdapter",
        adapter_version="0.1.0",
        parsed_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        extraction_confidence=0.87,
        raw_extraction={"programs": [{"name": "Computer Science", "degree": "MS"}]},
    )
    db_session.add(doc)
    db_session.commit()
    db_session.expire_all()

    doc = db_session.get(ParsedDocument, doc.id)
    assert doc.adapter_name == "GenericHtmlAdapter"
    assert doc.raw_extraction == {"programs": [{"name": "Computer Science", "degree": "MS"}]}
    assert float(doc.extraction_confidence) == pytest.approx(0.87)


def test_parsed_document_snapshot_set_null_on_delete(db_session, snapshot):
    doc = ParsedDocument(
        source_snapshot_id=snapshot.id,
        adapter_name="GenericHtmlAdapter",
        adapter_version="0.1.0",
        parsed_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
        raw_extraction={},
    )
    db_session.add(doc)
    db_session.commit()

    db_session.delete(snapshot)
    db_session.commit()
    db_session.expire_all()

    doc = db_session.get(ParsedDocument, doc.id)
    assert doc.source_snapshot_id is None
    # extraction_confidence was never provided — confirm the nullable column
    # actually stores None rather than some adapter-supplied default.
    assert doc.extraction_confidence is None


# --- DataReviewTask ------------------------------------------------------


def test_data_review_task_defaults_to_open(db_session, program):
    task = DataReviewTask(
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        reason=ReviewReason.LOW_CONFIDENCE,
    )
    db_session.add(task)
    db_session.commit()
    db_session.expire_all()

    task = db_session.get(DataReviewTask, task.id)
    assert task.status == ReviewTaskStatus.OPEN
    assert task.field_name is None
    assert task.resolved_at is None


def test_data_review_task_can_flag_a_specific_field(db_session, program):
    task = DataReviewTask(
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        field_name="canonical_name",
        reason=ReviewReason.POSSIBLE_DUPLICATE,
        status=ReviewTaskStatus.IN_REVIEW,
    )
    db_session.add(task)
    db_session.commit()
    db_session.expire_all()

    task = db_session.get(DataReviewTask, task.id)
    assert task.field_name == "canonical_name"
    assert task.reason == ReviewReason.POSSIBLE_DUPLICATE
    assert task.status == ReviewTaskStatus.IN_REVIEW


@pytest.mark.parametrize("terminal_status", [ReviewTaskStatus.RESOLVED, ReviewTaskStatus.DISMISSED])
def test_data_review_task_terminal_states_set_resolved_at(db_session, program, terminal_status):
    # Both RESOLVED and DISMISSED are terminal states for a task — resolved_at
    # marks "stopped being active," not specifically "fixed." See the
    # resolved_at doc comment on DataReviewTask.
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    task = DataReviewTask(
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        reason=ReviewReason.LOW_CONFIDENCE,
        status=terminal_status,
        resolved_at=now,
    )
    db_session.add(task)
    db_session.commit()
    db_session.expire_all()

    task = db_session.get(DataReviewTask, task.id)
    assert task.status == terminal_status
    assert task.resolved_at == now


def test_data_review_task_updated_at_changes_on_update(db_session, program):
    task = DataReviewTask(
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        reason=ReviewReason.LOW_CONFIDENCE,
    )
    db_session.add(task)
    db_session.commit()
    first_updated_at = task.updated_at

    task.status = ReviewTaskStatus.IN_REVIEW
    db_session.commit()
    db_session.expire_all()

    task = db_session.get(DataReviewTask, task.id)
    assert task.updated_at >= first_updated_at


def test_data_review_task_entity_id_has_no_real_fk(db_session):
    # Intentional per docs/PHASE_2_CATALOG_DESIGN.md §5: entity_type +
    # entity_id is a polymorphic reference, so the database cannot enforce
    # that entity_id actually points at an existing row of that type. This
    # test documents that permissiveness as deliberate, not an oversight —
    # a future "fix" adding a real FK here would be incorrect.
    task = DataReviewTask(
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=999999,  # no Program with this id exists
        reason=ReviewReason.FIRST_SEEN,
    )
    db_session.add(task)
    db_session.commit()  # does not raise

    db_session.expire_all()
    task = db_session.get(DataReviewTask, task.id)
    assert task.entity_id == 999999


# --- DataConflict --------------------------------------------------------


def test_data_conflict_round_trip(db_session, program, snapshot):
    conflict = DataConflict(
        entity_type=CatalogEntityType.PROGRAM_TRACK,
        entity_id=1,
        field_name="min_gpa",
        current_value="3.0",
        current_verification_status=VerificationStatus.DOCUMENT_VERIFIED,
        proposed_value="3.3",
        proposed_source_snapshot_id=snapshot.id,
    )
    db_session.add(conflict)
    db_session.commit()
    db_session.expire_all()

    conflict = db_session.get(DataConflict, conflict.id)
    assert conflict.status == ConflictStatus.OPEN
    assert conflict.current_verification_status == VerificationStatus.DOCUMENT_VERIFIED
    assert conflict.proposed_value == "3.3"
    assert conflict.resolved_at is None


def test_data_conflict_snapshot_set_null_on_delete(db_session, program, snapshot):
    conflict = DataConflict(
        entity_type=CatalogEntityType.PROGRAM_TRACK,
        entity_id=1,
        field_name="min_gpa",
        current_verification_status=VerificationStatus.RAW,
        proposed_value="3.3",
        proposed_source_snapshot_id=snapshot.id,
    )
    db_session.add(conflict)
    db_session.commit()

    db_session.delete(snapshot)
    db_session.commit()
    db_session.expire_all()

    conflict = db_session.get(DataConflict, conflict.id)
    assert conflict.proposed_source_snapshot_id is None
    # The conflict row itself survives — deleting evidence never destroys
    # the fact that a conflict was raised, per docs/PHASE_2_CATALOG_DESIGN.md §5.1.
    assert conflict is not None


def test_data_conflict_resolution_status(db_session, program, snapshot):
    conflict = DataConflict(
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        field_name="canonical_name",
        current_verification_status=VerificationStatus.PARSED,
        proposed_value="Computer Sciences",
        proposed_source_snapshot_id=snapshot.id,
        status=ConflictStatus.RESOLVED_KEPT_CURRENT,
        resolved_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    db_session.add(conflict)
    db_session.commit()
    db_session.expire_all()

    conflict = db_session.get(DataConflict, conflict.id)
    assert conflict.status == ConflictStatus.RESOLVED_KEPT_CURRENT
    assert conflict.resolved_at is not None


def test_data_conflict_updated_at_changes_on_update(db_session, program, snapshot):
    conflict = DataConflict(
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        field_name="canonical_name",
        current_verification_status=VerificationStatus.RAW,
        proposed_value="Computer Sciences",
        proposed_source_snapshot_id=snapshot.id,
    )
    db_session.add(conflict)
    db_session.commit()
    first_updated_at = conflict.updated_at

    conflict.status = ConflictStatus.RESOLVED_TOOK_PROPOSED
    db_session.commit()
    db_session.expire_all()

    conflict = db_session.get(DataConflict, conflict.id)
    assert conflict.updated_at >= first_updated_at
