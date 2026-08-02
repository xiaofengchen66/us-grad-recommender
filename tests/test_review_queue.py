from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from us_grad_recommender.models.catalog import (
    AcademicUnit,
    DegreeLevel,
    DegreeType,
    Program,
    UnitType,
)
from us_grad_recommender.models.common import VerificationStatus
from us_grad_recommender.models.review import (
    CatalogEntityType,
    ConflictStatus,
    ReviewReason,
    ReviewTaskStatus,
)
from us_grad_recommender.models.university import Sector, University
from us_grad_recommender.review_queue import (
    DataConflictAlreadyResolvedError,
    DataConflictNotFoundError,
    ReviewTaskAlreadyResolvedError,
    ReviewTaskNotFoundError,
    create_data_conflict,
    create_review_task,
    list_data_conflicts,
    list_review_tasks,
    resolve_data_conflict,
    resolve_review_task,
)

TODAY = date(2026, 8, 2)


@pytest.fixture()
def program(db_session) -> Program:
    """A minimal University -> AcademicUnit -> DegreeType -> Program chain,
    committed, so review rows have a real entity_id to point at — same
    pattern tests/test_review_models.py uses for the same schema area.
    """
    university = University(
        unitid=900101,
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
        unitid=900101,
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


# --- DataReviewTask ------------------------------------------------------


def test_create_review_task_defaults_to_open(db_session, program):
    task = create_review_task(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        reason=ReviewReason.FIRST_SEEN,
    )
    assert task.id is not None
    assert task.status == ReviewTaskStatus.OPEN
    assert task.resolved_at is None


def test_list_review_tasks_defaults_to_open_and_in_review(db_session, program):
    open_task = create_review_task(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        reason=ReviewReason.FIRST_SEEN,
    )
    resolved_task = create_review_task(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        reason=ReviewReason.LOW_CONFIDENCE,
    )
    resolve_review_task(db_session, resolved_task.id, status=ReviewTaskStatus.RESOLVED)

    tasks = list_review_tasks(db_session)
    assert [t.id for t in tasks] == [open_task.id]


def test_list_review_tasks_filters_by_entity_type_and_reason(db_session, program):
    match = create_review_task(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        reason=ReviewReason.POSSIBLE_DUPLICATE,
    )
    create_review_task(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        reason=ReviewReason.FIRST_SEEN,
    )
    create_review_task(
        db_session,
        entity_type=CatalogEntityType.ACADEMIC_UNIT,
        entity_id=program.academic_unit_id,
        reason=ReviewReason.POSSIBLE_DUPLICATE,
    )

    tasks = list_review_tasks(
        db_session, entity_type=CatalogEntityType.PROGRAM, reason=ReviewReason.POSSIBLE_DUPLICATE
    )
    assert [t.id for t in tasks] == [match.id]


def test_list_review_tasks_with_explicit_status_sees_resolved(db_session, program):
    task = create_review_task(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        reason=ReviewReason.FIRST_SEEN,
    )
    resolve_review_task(db_session, task.id, status=ReviewTaskStatus.DISMISSED)

    tasks = list_review_tasks(db_session, status=[ReviewTaskStatus.DISMISSED])
    assert [t.id for t in tasks] == [task.id]


def test_resolve_review_task_sets_status_and_resolved_at(db_session, program):
    task = create_review_task(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        reason=ReviewReason.FIRST_SEEN,
    )
    fixed_time = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)

    resolved = resolve_review_task(
        db_session, task.id, status=ReviewTaskStatus.RESOLVED, resolved_at=fixed_time
    )
    assert resolved.status == ReviewTaskStatus.RESOLVED
    assert resolved.resolved_at == fixed_time


def test_resolve_review_task_rejects_non_terminal_status(db_session, program):
    task = create_review_task(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        reason=ReviewReason.FIRST_SEEN,
    )
    with pytest.raises(ValueError):
        resolve_review_task(db_session, task.id, status=ReviewTaskStatus.IN_REVIEW)


def test_resolve_review_task_raises_on_missing_task(db_session):
    with pytest.raises(ReviewTaskNotFoundError):
        resolve_review_task(db_session, 999999, status=ReviewTaskStatus.RESOLVED)


def test_resolve_review_task_raises_on_double_resolve(db_session, program):
    task = create_review_task(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        reason=ReviewReason.FIRST_SEEN,
    )
    resolve_review_task(db_session, task.id, status=ReviewTaskStatus.RESOLVED)
    with pytest.raises(ReviewTaskAlreadyResolvedError):
        resolve_review_task(db_session, task.id, status=ReviewTaskStatus.DISMISSED)


# --- DataConflict ----------------------------------------------------


def test_create_data_conflict_defaults_to_open(db_session, program):
    conflict = create_data_conflict(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        field_name="canonical_name",
        current_value="Computer Science",
        current_verification_status=VerificationStatus.USER_CONFIRMED,
        proposed_value="Computer Science and Engineering",
    )
    assert conflict.id is not None
    assert conflict.status == ConflictStatus.OPEN
    assert conflict.resolved_at is None


def test_list_data_conflicts_defaults_to_open_only(db_session, program):
    open_conflict = create_data_conflict(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        field_name="canonical_name",
        current_value="Computer Science",
        current_verification_status=VerificationStatus.USER_CONFIRMED,
        proposed_value="Computer Science and Engineering",
    )
    resolved_conflict = create_data_conflict(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        field_name="canonical_name",
        current_value="Computer Science",
        current_verification_status=VerificationStatus.USER_CONFIRMED,
        proposed_value="CS",
    )
    resolve_data_conflict(
        db_session, resolved_conflict.id, status=ConflictStatus.RESOLVED_KEPT_CURRENT
    )

    conflicts = list_data_conflicts(db_session)
    assert [c.id for c in conflicts] == [open_conflict.id]


def test_resolve_data_conflict_kept_current(db_session, program):
    conflict = create_data_conflict(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        field_name="canonical_name",
        current_value="Computer Science",
        current_verification_status=VerificationStatus.USER_CONFIRMED,
        proposed_value="Computer Science and Engineering",
    )
    resolved = resolve_data_conflict(
        db_session, conflict.id, status=ConflictStatus.RESOLVED_KEPT_CURRENT
    )
    assert resolved.status == ConflictStatus.RESOLVED_KEPT_CURRENT
    assert resolved.resolved_at is not None


def test_resolve_data_conflict_rejects_open_status(db_session, program):
    conflict = create_data_conflict(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        field_name="canonical_name",
        current_value="Computer Science",
        current_verification_status=VerificationStatus.USER_CONFIRMED,
        proposed_value="Computer Science and Engineering",
    )
    with pytest.raises(ValueError):
        resolve_data_conflict(db_session, conflict.id, status=ConflictStatus.OPEN)


def test_resolve_data_conflict_raises_on_missing_conflict(db_session):
    with pytest.raises(DataConflictNotFoundError):
        resolve_data_conflict(db_session, 999999, status=ConflictStatus.RESOLVED_KEPT_CURRENT)


def test_resolve_data_conflict_raises_on_double_resolve(db_session, program):
    conflict = create_data_conflict(
        db_session,
        entity_type=CatalogEntityType.PROGRAM,
        entity_id=program.id,
        field_name="canonical_name",
        current_value="Computer Science",
        current_verification_status=VerificationStatus.USER_CONFIRMED,
        proposed_value="Computer Science and Engineering",
    )
    resolve_data_conflict(db_session, conflict.id, status=ConflictStatus.RESOLVED_KEPT_CURRENT)
    with pytest.raises(DataConflictAlreadyResolvedError):
        resolve_data_conflict(db_session, conflict.id, status=ConflictStatus.RESOLVED_TOOK_PROPOSED)
