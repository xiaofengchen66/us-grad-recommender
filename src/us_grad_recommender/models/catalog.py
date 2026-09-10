"""Program/catalog schema — Phase 2.1.

Schema only, per docs/PHASE_2_CATALOG_DESIGN.md (design-reviewed and
approved 2026-07-20, decisions in §12). No adapters, no crawling: this
module defines the tables that Phase 2.2 (catalog adapter framework) and
Phase 2.3 (pilot) will populate.

Table -> design-doc entity mapping, and what's deliberately deferred to
Phase 2.2: `parsed_documents`, `data_review_tasks`, and `data_conflicts`
are adapter-pipeline mechanics (§5, §9), not core catalog structure, and
are built alongside the adapter framework / verification queue instead.

Provenance is tracked per §12 decision 1 (simplified): every content row
carries `last_seen_snapshot_id` + `verification_status` + `last_verified_at`
(entity-level), plus plain `*_raw` sibling columns on the handful of
fields that are genuinely interpreted rather than copied (§4). There is no
separate field-level provenance table.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from us_grad_recommender.models.base import Base
from us_grad_recommender.models.common import EntityStatus, VerificationStatus


class UnitType(str, enum.Enum):
    COLLEGE = "college"
    SCHOOL = "school"
    DEPARTMENT = "department"
    DIVISION = "division"
    INSTITUTE = "institute"
    OTHER = "other"


class DegreeLevel(str, enum.Enum):
    MASTERS = "masters"
    DOCTORAL = "doctoral"
    CERTIFICATE = "certificate"
    OTHER = "other"


class ProgramAliasType(str, enum.Enum):
    CATALOG_ALIAS = "catalog_alias"
    FORMER_NAME = "former_name"
    COMMON_ABBREVIATION = "common_abbreviation"
    OTHER = "other"


class TrackType(str, enum.Enum):
    THESIS = "thesis"
    NON_THESIS = "non_thesis"
    PROJECT = "project"
    COURSEWORK = "coursework"
    UNSPECIFIED = "unspecified"


class Modality(str, enum.Enum):
    IN_PERSON = "in_person"
    ONLINE = "online"
    HYBRID = "hybrid"
    UNSPECIFIED = "unspecified"


class GrePolicy(str, enum.Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    WAIVED = "waived"
    NOT_ACCEPTED = "not_accepted"
    UNSPECIFIED = "unspecified"


class RequirementType(str, enum.Enum):
    GPA = "gpa"
    TEST_SCORE = "test_score"
    PREREQUISITE_COURSE = "prerequisite_course"
    RECOMMENDATION_LETTERS = "recommendation_letters"
    DOCUMENT = "document"
    FUNDING = "funding"
    OTHER = "other"


class CredentialStatus(str, enum.Enum):
    """Is this an official, credit-bearing degree at all, or a
    certificate/non-credit/executive-education offering? See
    docs/PHASE_2_CATALOG_DESIGN.md §8/§8.1 — deliberately distinct from
    both delivery modality and visa eligibility, which are independent
    facts and must not be inferred from each other.
    """

    DEGREE = "degree"
    CERTIFICATE = "certificate"
    NON_CREDIT_CERTIFICATE = "non_credit_certificate"
    EXECUTIVE_EDUCATION = "executive_education"
    MICROCREDENTIAL = "microcredential"
    UNKNOWN = "unknown"


class VisaSupportStatus(str, enum.Enum):
    """Can this specific offering support an F-1 student's I-20 and,
    downstream, OPT? See docs/PHASE_2_CATALOG_DESIGN.md §8/§8.1 — modeled
    at program level (narrowest applicable scope) with an optional
    track-level override, never as a university-level fact.
    """

    I20_ELIGIBLE = "i20_eligible"
    NO_I20_ONLINE_ONLY = "no_i20_online_only"
    NO_I20_NON_DEGREE = "no_i20_non_degree"
    I20_DEPENDS_ON_CAMPUS_OR_TRACK = "i20_depends_on_campus_or_track"
    I20_ELIGIBILITY_UNCLEAR = "i20_eligibility_unclear"
    NOT_APPLICABLE = "not_applicable"


class SourceType(str, enum.Enum):
    ACADEMIC_CATALOG = "academic_catalog"
    DEPARTMENT_PAGE = "department_page"
    GRADUATE_SCHOOL_PAGE = "graduate_school_page"
    INTERNATIONAL_OFFICE = "international_office"
    INSTITUTIONAL_REPORT = "institutional_report"
    RANKING_PUBLISHER = "ranking_publisher"


class EvidenceSource(Base):
    """A page/document source we track for a given institution (or a
    non-institution-specific source, e.g. a ranking publisher)."""

    __tablename__ = "evidence_sources"
    __table_args__ = (UniqueConstraint("unitid", "base_url", name="uq_evidence_source_unitid_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unitid: Mapped[Optional[int]] = mapped_column(
        ForeignKey("universities.unitid"), nullable=True, index=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type"), nullable=False
    )
    base_url: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    snapshots: Mapped[List[SourceSnapshot]] = relationship(back_populates="evidence_source")

    def __repr__(self) -> str:  # pragma: no cover
        return f"EvidenceSource(id={self.id!r}, base_url={self.base_url!r})"


class SourceSnapshot(Base):
    """A single fetch of a page/document at a point in time. Immutable —
    never updated after creation, only superseded by a newer snapshot of
    the same URL. This is the "raw snapshot" that every content row's
    last_seen_snapshot_id ultimately points back to.
    """

    __tablename__ = "source_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_source_id: Mapped[int] = mapped_column(
        ForeignKey("evidence_sources.id"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[Optional[int]] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    fetch_method: Mapped[Optional[str]] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    evidence_source: Mapped[EvidenceSource] = relationship(back_populates="snapshots")

    def __repr__(self) -> str:  # pragma: no cover
        return f"SourceSnapshot(id={self.id!r}, url={self.url!r})"


class AcademicUnit(Base):
    """College/school/department, or any level in between. Self-referencing
    because real institutional org structures nest to varying depths — see
    docs/PHASE_2_CATALOG_DESIGN.md §2.1.
    """

    __tablename__ = "academic_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unitid: Mapped[int] = mapped_column(
        ForeignKey("universities.unitid"), nullable=False, index=True
    )
    parent_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("academic_units.id"), nullable=True, index=True
    )
    unit_type: Mapped[UnitType] = mapped_column(Enum(UnitType, name="unit_type"), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    official_url: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, name="entity_status"), nullable=False, default=EntityStatus.UNVERIFIED
    )

    last_seen_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"),
        nullable=False,
        default=VerificationStatus.RAW,
    )
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    parent: Mapped[Optional[AcademicUnit]] = relationship(
        remote_side=[id], back_populates="children"
    )
    children: Mapped[List[AcademicUnit]] = relationship(back_populates="parent")
    programs: Mapped[List[Program]] = relationship(back_populates="academic_unit")

    def __repr__(self) -> str:  # pragma: no cover
        return f"AcademicUnit(id={self.id!r}, name={self.name!r})"


class DegreeType(Base):
    """Controlled but extensible degree vocabulary — a lookup table, not an
    enum, since real degree-name vocabulary grows over time and adding a
    row shouldn't require a migration.
    """

    __tablename__ = "degree_types"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[DegreeLevel] = mapped_column(
        Enum(DegreeLevel, name="degree_level"), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"DegreeType(code={self.code!r})"


class Program(Base):
    """The stable program_id FULL_HANDOFF.md §5 asks for."""

    __tablename__ = "programs"
    __table_args__ = (
        UniqueConstraint(
            "academic_unit_id", "degree_type_code", "canonical_name", name="uq_program_identity"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    academic_unit_id: Mapped[int] = mapped_column(
        ForeignKey("academic_units.id"), nullable=False, index=True
    )
    degree_type_code: Mapped[str] = mapped_column(ForeignKey("degree_types.code"), nullable=False)
    raw_degree_name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    cip_code: Mapped[Optional[str]] = mapped_column(String(20))
    program_url: Mapped[Optional[str]] = mapped_column(Text)
    stem_designated: Mapped[Optional[bool]] = mapped_column(Boolean)
    credential_status: Mapped[CredentialStatus] = mapped_column(
        Enum(CredentialStatus, name="credential_status"),
        nullable=False,
        default=CredentialStatus.UNKNOWN,
    )
    visa_support_status: Mapped[VisaSupportStatus] = mapped_column(
        Enum(VisaSupportStatus, name="visa_support_status"),
        nullable=False,
        default=VisaSupportStatus.I20_ELIGIBILITY_UNCLEAR,
    )
    visa_support_status_raw_text: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, name="entity_status"), nullable=False, default=EntityStatus.UNVERIFIED
    )

    last_seen_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"),
        nullable=False,
        default=VerificationStatus.RAW,
    )
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    academic_unit: Mapped[AcademicUnit] = relationship(back_populates="programs")
    degree_type: Mapped[DegreeType] = relationship()
    aliases: Mapped[List[ProgramAlias]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )
    tracks: Mapped[List[ProgramTrack]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )
    concentrations: Mapped[List[ProgramConcentration]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"Program(id={self.id!r}, canonical_name={self.canonical_name!r})"


class ProgramAlias(Base):
    __tablename__ = "program_aliases"
    __table_args__ = (UniqueConstraint("program_id", "alias", name="uq_program_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    alias_type: Mapped[ProgramAliasType] = mapped_column(
        Enum(ProgramAliasType, name="program_alias_type"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    program: Mapped[Program] = relationship(back_populates="aliases")

    def __repr__(self) -> str:  # pragma: no cover
        return f"ProgramAlias(program_id={self.program_id!r}, alias={self.alias!r})"


class ProgramTrack(Base):
    """The "smallest meaningful unit" per FULL_HANDOFF.md §5: university +
    college + department + degree + program + track.
    """

    __tablename__ = "program_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"), nullable=False, index=True)
    track_name: Mapped[str] = mapped_column(String(255), nullable=False)
    track_type: Mapped[TrackType] = mapped_column(
        Enum(TrackType, name="track_type"), nullable=False, default=TrackType.UNSPECIFIED
    )
    modality: Mapped[Modality] = mapped_column(
        Enum(Modality, name="modality"), nullable=False, default=Modality.UNSPECIFIED
    )
    campus_name: Mapped[Optional[str]] = mapped_column(String(255))

    credits_required: Mapped[Optional[int]] = mapped_column(Integer)
    expected_duration_months: Mapped[Optional[int]] = mapped_column(Integer)

    min_gpa: Mapped[Optional[float]] = mapped_column(Numeric(3, 2))
    min_gpa_raw: Mapped[Optional[str]] = mapped_column(String(255))
    toefl_min: Mapped[Optional[int]] = mapped_column(Integer)
    ielts_min: Mapped[Optional[int]] = mapped_column(Integer)
    gre_policy: Mapped[GrePolicy] = mapped_column(
        Enum(GrePolicy, name="gre_policy"), nullable=False, default=GrePolicy.UNSPECIFIED
    )
    cohort_size: Mapped[Optional[int]] = mapped_column(Integer)
    international_share: Mapped[Optional[float]] = mapped_column(Numeric(4, 3))

    estimated_annual_cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    estimated_annual_cost_raw: Mapped[Optional[str]] = mapped_column(Text)

    # Program.visa_support_status is the default; set only when this
    # track's eligibility genuinely differs from the program-level fact
    # (see docs/PHASE_2_CATALOG_DESIGN.md §8.1 — e.g. an online track of
    # an otherwise I-20-eligible program). Null means "no override, use
    # the program-level value."
    visa_support_status_override: Mapped[Optional[VisaSupportStatus]] = mapped_column(
        Enum(VisaSupportStatus, name="visa_support_status"), nullable=True
    )
    visa_support_status_override_raw_text: Mapped[Optional[str]] = mapped_column(Text)

    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, name="entity_status"), nullable=False, default=EntityStatus.UNVERIFIED
    )
    last_seen_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"),
        nullable=False,
        default=VerificationStatus.RAW,
    )
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    program: Mapped[Program] = relationship(back_populates="tracks")
    deadlines: Mapped[List[ProgramTrackDeadline]] = relationship(
        back_populates="track", cascade="all, delete-orphan"
    )
    admission_requirements: Mapped[List[AdmissionRequirement]] = relationship(
        back_populates="track", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"ProgramTrack(id={self.id!r}, track_name={self.track_name!r})"


class ProgramTrackDeadline(Base):
    __tablename__ = "program_track_deadlines"
    __table_args__ = (
        UniqueConstraint("program_track_id", "intake_term", name="uq_track_deadline_intake_term"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_track_id: Mapped[int] = mapped_column(
        ForeignKey("program_tracks.id"), nullable=False, index=True
    )
    intake_term: Mapped[str] = mapped_column(String(50), nullable=False)
    application_deadline: Mapped[Optional[date]] = mapped_column(Date)
    priority_funding_deadline: Mapped[Optional[date]] = mapped_column(Date)
    is_rolling: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deadline_raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    last_seen_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"),
        nullable=False,
        default=VerificationStatus.RAW,
    )
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    track: Mapped[ProgramTrack] = relationship(back_populates="deadlines")

    def __repr__(self) -> str:  # pragma: no cover
        return f"ProgramTrackDeadline(intake_term={self.intake_term!r})"


class ProgramConcentration(Base):
    __tablename__ = "program_concentrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"), nullable=False, index=True)
    program_track_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("program_tracks.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description_raw: Mapped[Optional[str]] = mapped_column(Text)

    last_seen_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"),
        nullable=False,
        default=VerificationStatus.RAW,
    )
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    program: Mapped[Program] = relationship(back_populates="concentrations")
    track: Mapped[Optional[ProgramTrack]] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"ProgramConcentration(id={self.id!r}, name={self.name!r})"


class AdmissionRequirement(Base):
    """Anchored at program_track_id, not program_id — see
    docs/PHASE_2_CATALOG_DESIGN.md §7.4/§12 decision 2 for why (decided:
    accept some duplication across tracks rather than add
    program-level-with-track-override resolution logic).
    """

    __tablename__ = "admission_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program_track_id: Mapped[int] = mapped_column(
        ForeignKey("program_tracks.id"), nullable=False, index=True
    )
    requirement_type: Mapped[RequirementType] = mapped_column(
        Enum(RequirementType, name="requirement_type"), nullable=False
    )
    structured_value: Mapped[Optional[dict]] = mapped_column(JSONB)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)

    last_seen_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("source_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"),
        nullable=False,
        default=VerificationStatus.RAW,
    )
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    track: Mapped[ProgramTrack] = relationship(back_populates="admission_requirements")

    def __repr__(self) -> str:  # pragma: no cover
        return f"AdmissionRequirement(id={self.id!r}, requirement_type={self.requirement_type!r})"
