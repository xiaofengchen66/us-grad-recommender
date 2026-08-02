"""Service layer over the Phase 2.2A review/provenance schema
(``models/review.py``): ``data_review_tasks`` and ``data_conflicts``.

Per §10/§11, every automated extraction goes through this queue before
reaching ``user_confirmed``/``document_verified`` — no auto-promotion
allowlist. Nothing here creates tasks/conflicts automatically from adapter
output; that wiring (the parser pipeline) doesn't exist yet. This module
only provides the create/list/resolve operations the pipeline and a future
review UI will both need, against the schema that already exists.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from us_grad_recommender.models.common import VerificationStatus
from us_grad_recommender.models.review import (
    CatalogEntityType,
    ConflictStatus,
    DataConflict,
    DataReviewTask,
    ReviewReason,
    ReviewTaskStatus,
)

_OPEN_TASK_STATUSES = (ReviewTaskStatus.OPEN, ReviewTaskStatus.IN_REVIEW)
_TERMINAL_TASK_STATUSES = (ReviewTaskStatus.RESOLVED, ReviewTaskStatus.DISMISSED)

_OPEN_CONFLICT_STATUS = ConflictStatus.OPEN
_TERMINAL_CONFLICT_STATUSES = (
    ConflictStatus.RESOLVED_KEPT_CURRENT,
    ConflictStatus.RESOLVED_TOOK_PROPOSED,
)


class ReviewTaskNotFoundError(LookupError):
    pass


class ReviewTaskAlreadyResolvedError(ValueError):
    pass


class DataConflictNotFoundError(LookupError):
    pass


class DataConflictAlreadyResolvedError(ValueError):
    pass


def create_review_task(
    session: Session,
    *,
    entity_type: CatalogEntityType,
    entity_id: int,
    reason: ReviewReason,
    field_name: Optional[str] = None,
    assigned_to: Optional[str] = None,
) -> DataReviewTask:
    task = DataReviewTask(
        entity_type=entity_type,
        entity_id=entity_id,
        reason=reason,
        field_name=field_name,
        assigned_to=assigned_to,
        status=ReviewTaskStatus.OPEN,
    )
    session.add(task)
    session.flush()
    return task


def list_review_tasks(
    session: Session,
    *,
    status: Optional[List[ReviewTaskStatus]] = None,
    entity_type: Optional[CatalogEntityType] = None,
    reason: Optional[ReviewReason] = None,
) -> List[DataReviewTask]:
    """Defaults to open work (OPEN + IN_REVIEW) — pass an explicit
    ``status`` list (e.g. ``[ReviewTaskStatus.RESOLVED]``) to see anything
    else, including a fully unfiltered query via every status value.
    """
    statuses = status if status is not None else list(_OPEN_TASK_STATUSES)
    stmt = select(DataReviewTask).where(DataReviewTask.status.in_(statuses))
    if entity_type is not None:
        stmt = stmt.where(DataReviewTask.entity_type == entity_type)
    if reason is not None:
        stmt = stmt.where(DataReviewTask.reason == reason)
    stmt = stmt.order_by(DataReviewTask.created_at)
    return list(session.scalars(stmt))


def resolve_review_task(
    session: Session,
    task_id: int,
    *,
    status: ReviewTaskStatus,
    resolved_at: Optional[datetime] = None,
) -> DataReviewTask:
    """``status`` must be RESOLVED or DISMISSED — both are terminal (see
    ``DataReviewTask.resolved_at``'s docstring in ``models/review.py``).
    Resolving an already-terminal task raises rather than silently
    re-resolving it, since a second resolution attempt on the same task
    almost always signals a caller bug (double-submit, stale task list)
    rather than an intentional action.

    Takes a row lock (``SELECT ... FOR UPDATE``) before checking status:
    without it, two concurrent callers resolving the same task (e.g. two
    reviewers double-clicking "resolve" in a future review UI) could both
    read a non-terminal status under READ COMMITTED and both proceed,
    silently defeating the not-a-caller-bug guarantee this function's
    docstring advertises. No concurrent caller exists yet, but this is
    cheap to get right now rather than revisit later.
    """
    if status not in _TERMINAL_TASK_STATUSES:
        raise ValueError(
            "resolve_review_task() requires a terminal status "
            f"(RESOLVED or DISMISSED), got {status!r}"
        )
    task = session.get(DataReviewTask, task_id, with_for_update=True)
    if task is None:
        raise ReviewTaskNotFoundError(f"No DataReviewTask with id={task_id}")
    if task.status in _TERMINAL_TASK_STATUSES:
        raise ReviewTaskAlreadyResolvedError(
            f"DataReviewTask {task_id} is already {task.status.value}"
        )
    task.status = status
    task.resolved_at = resolved_at or datetime.now(timezone.utc)
    session.flush()
    return task


def create_data_conflict(
    session: Session,
    *,
    entity_type: CatalogEntityType,
    entity_id: int,
    field_name: str,
    current_value: Optional[str],
    current_verification_status: VerificationStatus,
    proposed_value: str,
    proposed_source_snapshot_id: Optional[int] = None,
) -> DataConflict:
    conflict = DataConflict(
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field_name,
        current_value=current_value,
        current_verification_status=current_verification_status,
        proposed_value=proposed_value,
        proposed_source_snapshot_id=proposed_source_snapshot_id,
        status=ConflictStatus.OPEN,
    )
    session.add(conflict)
    session.flush()
    return conflict


def list_data_conflicts(
    session: Session,
    *,
    status: Optional[List[ConflictStatus]] = None,
    entity_type: Optional[CatalogEntityType] = None,
) -> List[DataConflict]:
    """Defaults to open conflicts only — pass an explicit ``status`` list
    to see resolved ones too.
    """
    statuses = status if status is not None else [_OPEN_CONFLICT_STATUS]
    stmt = select(DataConflict).where(DataConflict.status.in_(statuses))
    if entity_type is not None:
        stmt = stmt.where(DataConflict.entity_type == entity_type)
    stmt = stmt.order_by(DataConflict.created_at)
    return list(session.scalars(stmt))


def resolve_data_conflict(
    session: Session,
    conflict_id: int,
    *,
    status: ConflictStatus,
    resolved_at: Optional[datetime] = None,
) -> DataConflict:
    """``status`` must be RESOLVED_KEPT_CURRENT or RESOLVED_TOOK_PROPOSED
    — the two terminal outcomes §6's non-regression rule allows. This
    function only records which outcome was chosen; actually writing the
    proposed value onto the target entity (when TOOK_PROPOSED) is the
    caller's responsibility — this module doesn't know how to interpret
    ``field_name``/``proposed_value`` for the six different entity types
    in ``CatalogEntityType``, that's the parser pipeline's job.

    Takes a row lock (``SELECT ... FOR UPDATE``) before checking status —
    same concurrent-double-resolve concern and rationale as
    ``resolve_review_task``.
    """
    if status not in _TERMINAL_CONFLICT_STATUSES:
        raise ValueError(
            "resolve_data_conflict() requires a terminal status "
            f"(RESOLVED_KEPT_CURRENT or RESOLVED_TOOK_PROPOSED), got {status!r}"
        )
    conflict = session.get(DataConflict, conflict_id, with_for_update=True)
    if conflict is None:
        raise DataConflictNotFoundError(f"No DataConflict with id={conflict_id}")
    if conflict.status in _TERMINAL_CONFLICT_STATUSES:
        raise DataConflictAlreadyResolvedError(
            f"DataConflict {conflict_id} is already {conflict.status.value}"
        )
    conflict.status = status
    conflict.resolved_at = resolved_at or datetime.now(timezone.utc)
    session.flush()
    return conflict
