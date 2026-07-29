"""Review/provenance pipeline schema — Phase 2.2A.

Schema only, per docs/PHASE_2_CATALOG_DESIGN.md §5: `parsed_documents`,
`data_review_tasks`, `data_conflicts` — explicitly deferred out of Phase
2.1 since they are adapter-pipeline mechanics, not core catalog structure.

Not implemented here, by design (Phase 2.2A scope only): adapter
interfaces, the parser pipeline, HTML/PDF parsing, network fetching, a
review UI, or any code that automatically transitions a `verification_status`.
This module defines only the tables that future work will read from and
write to.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from us_grad_recommender.models.base import Base
from us_grad_recommender.models.catalog import SourceSnapshot
from us_grad_recommender.models.common import VerificationStatus


class CatalogEntityType(str, enum.Enum):
    """The six catalog tables that carry `verification_status` (see
    docs/PHASE_2_CATALOG_DESIGN.md §2) — the only entities a review task or
    conflict can point at. `entity_id` is a plain integer, not a real FK:
    which table it references depends on this value, so the database
    cannot enforce it directly (see docs/PHASE_2_CATALOG_DESIGN.md §5).
    """

    ACADEMIC_UNIT = "academic_unit"
    PROGRAM = "program"
    PROGRAM_TRACK = "program_track"
    PROGRAM_TRACK_DEADLINE = "program_track_deadline"
    PROGRAM_CONCENTRATION = "program_concentration"
    ADMISSION_REQUIREMENT = "admission_requirement"


class ReviewReason(str, enum.Enum):
    LOW_CONFIDENCE = "low_confidence"
    FIRST_SEEN = "first_seen"
    CONFLICTS_WITH_EXISTING = "conflicts_with_existing"
    ADAPTER_FALLBACK_USED = "adapter_fallback_used"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    REPORTED_BY_USER = "reported_by_user"


class ReviewTaskStatus(str, enum.Enum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ConflictStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED_KEPT_CURRENT = "resolved_kept_current"
    RESOLVED_TOOK_PROPOSED = "resolved_took_proposed"


class ParsedDocument(Base):
    """The structured output of one adapter run against one SourceSnapshot,
    before any human review. Append-only like SourceSnapshot itself — a
    snapshot may be parsed more than once (e.g. an adapter fix), and each
    attempt gets its own row rather than overwriting a prior one, so no
    uniqueness constraint is placed on (source_snapshot_id, adapter_name).

    `source_snapshot_id` is nullable with ON DELETE SET NULL, consistent
    with every other snapshot reference in this schema (see
    docs/PHASE_2_CATALOG_DESIGN.md §5.1) — snapshots are not deleted in
    normal operation, so this only matters for the same rare
    test/compliance/admin cleanup paths described there.
    """

    __tablename__ = "parsed_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    adapter_name: Mapped[str] = mapped_column(String(100), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(50), nullable=False)
    parsed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    extraction_confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3))
    raw_extraction: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source_snapshot: Mapped[Optional[SourceSnapshot]] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"ParsedDocument(id={self.id!r}, adapter_name={self.adapter_name!r})"


class DataReviewTask(Base):
    """A queued item for human review, per
    docs/PHASE_2_CATALOG_DESIGN.md §10/§11. Nothing in this codebase yet
    creates these rows or acts on them — that's the adapter pipeline and
    review UI, both out of scope for Phase 2.2A.
    """

    __tablename__ = "data_review_tasks"
    __table_args__ = (Index("ix_data_review_tasks_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[CatalogEntityType] = mapped_column(
        Enum(CatalogEntityType, name="catalog_entity_type"), nullable=False
    )
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[Optional[str]] = mapped_column(String(100))
    reason: Mapped[ReviewReason] = mapped_column(
        Enum(ReviewReason, name="review_reason"), nullable=False
    )
    status: Mapped[ReviewTaskStatus] = mapped_column(
        Enum(ReviewTaskStatus, name="review_task_status"),
        nullable=False,
        default=ReviewTaskStatus.OPEN,
        index=True,
    )
    assigned_to: Mapped[Optional[str]] = mapped_column(String(255))
    # Populated when status becomes RESOLVED *or* DISMISSED — both are
    # terminal states for a task (it stops being open/in_review either way),
    # so this marks "when did this task stop being active," not specifically
    # "when was it resolved with a fix applied."
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"DataReviewTask(id={self.id!r}, entity_type={self.entity_type!r})"


class DataConflict(Base):
    """A detected disagreement between a currently-stored value and a newly
    proposed one, raised instead of silently overwriting — the
    non-regression rule in docs/PHASE_2_CATALOG_DESIGN.md §6. Creating and
    resolving these rows is future adapter/review-pipeline work; this is
    only the structure they'll use.
    """

    __tablename__ = "data_conflicts"
    __table_args__ = (Index("ix_data_conflicts_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[CatalogEntityType] = mapped_column(
        Enum(CatalogEntityType, name="catalog_entity_type"), nullable=False
    )
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)

    current_value: Mapped[Optional[str]] = mapped_column(Text)
    current_verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"), nullable=False
    )
    proposed_value: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_source_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[ConflictStatus] = mapped_column(
        Enum(ConflictStatus, name="conflict_status"),
        nullable=False,
        default=ConflictStatus.OPEN,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    proposed_source_snapshot: Mapped[Optional[SourceSnapshot]] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"DataConflict(id={self.id!r}, field_name={self.field_name!r})"
