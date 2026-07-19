from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from us_grad_recommender.models.base import Base


class Sector(str, enum.Enum):
    """Derived from IPEDS HD.CONTROL. See §5 institution-level fields."""

    PUBLIC = "public"
    PRIVATE_NONPROFIT = "private_nonprofit"
    PRIVATE_FOR_PROFIT = "private_for_profit"
    UNKNOWN = "unknown"


class CoverageTier(str, enum.Enum):
    """§4 coverage levels, in ascending order of enrichment depth."""

    INDEXED = "INDEXED"
    PROGRAMS_DISCOVERED = "PROGRAMS_DISCOVERED"
    PROGRAMS_VERIFIED = "PROGRAMS_VERIFIED"
    ADMISSION_ENRICHED = "ADMISSION_ENRICHED"
    FUNDING_ENRICHED = "FUNDING_ENRICHED"
    OUTCOME_ENRICHED = "OUTCOME_ENRICHED"


class AliasType(str, enum.Enum):
    IPEDS_ALIAS = "ipeds_alias"
    FORMER_NAME = "former_name"
    COMMON_ABBREVIATION = "common_abbreviation"
    OTHER = "other"


class University(Base):
    """A single U.S. institution, keyed by its IPEDS UNITID.

    Per §5 ("Canonical entities and aliases"), UNITID is used directly as the
    institution identifier rather than introducing a separate surrogate key.
    """

    __tablename__ = "universities"

    unitid: Mapped[int] = mapped_column(Integer, primary_key=True)

    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    website: Mapped[Optional[str]] = mapped_column(String(500))

    city: Mapped[Optional[str]] = mapped_column(String(255))
    state: Mapped[Optional[str]] = mapped_column(String(2), index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)

    sector: Mapped[Sector] = mapped_column(
        Enum(Sector, name="sector"), nullable=False, default=Sector.UNKNOWN
    )

    # Raw IPEDS HD.HLOFFER code and its dictionary label, kept side by side so
    # the derived label can be traced back to the source code. See
    # importers/ipeds/mappings.py for the code -> label table, sourced from
    # the official HD dictionary (not invented).
    highest_degree_level: Mapped[Optional[int]] = mapped_column(Integer)
    highest_degree_label: Mapped[Optional[str]] = mapped_column(String(100))

    # Raw IPEDS HD.C21BASIC / HD.C21SZSET codes and labels. Note: Carnegie
    # classifications are a time-specific snapshot (2021 update, based on
    # 2019-20 data per ACE's own methodology docs) republished into each
    # year's HD file — the vintage is NOT the same as ipeds_year. This is
    # the "R1/R2" signal referenced in FULL_HANDOFF.md §4, and the source
    # for the "Campus setting" field listed in §5.
    carnegie_classification: Mapped[Optional[int]] = mapped_column(Integer)
    carnegie_classification_label: Mapped[Optional[str]] = mapped_column(String(100))
    campus_setting: Mapped[Optional[int]] = mapped_column(Integer)
    campus_setting_label: Mapped[Optional[str]] = mapped_column(String(100))

    # Heuristic: HD.GROFFER == 1 AND HD.HLOFFER >= 7 AND HD.DEGGRANT == 1.
    # This is an offering-capability signal, not a confirmed program count —
    # see masters_granting_basis and FULL_HANDOFF.md §4 "R1/R2 are not enough".
    masters_granting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    masters_granting_basis: Mapped[Optional[str]] = mapped_column(String(255))

    degree_granting: Mapped[Optional[bool]] = mapped_column(Boolean)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Enrollment fields sourced from IPEDS EF (fall enrollment), not HD.
    # Left null until an EF file has been imported for this institution.
    total_enrollment: Mapped[Optional[int]] = mapped_column(Integer)
    graduate_enrollment: Mapped[Optional[int]] = mapped_column(Integer)
    international_graduate_enrollment: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_year: Mapped[Optional[int]] = mapped_column(Integer)

    coverage_tier: Mapped[CoverageTier] = mapped_column(
        Enum(CoverageTier, name="coverage_tier"),
        nullable=False,
        default=CoverageTier.INDEXED,
    )

    # Provenance (§15, §23: every fact must carry source + retrieval date).
    ipeds_year: Mapped[int] = mapped_column(Integer, nullable=False)
    source_dataset: Mapped[str] = mapped_column(String(50), nullable=False, default="IPEDS HD")
    last_verified_at: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    aliases: Mapped[list[UniversityAlias]] = relationship(
        back_populates="university", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"University(unitid={self.unitid!r}, canonical_name={self.canonical_name!r})"


class UniversityAlias(Base):
    __tablename__ = "university_aliases"
    __table_args__ = (UniqueConstraint("unitid", "alias", name="uq_university_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unitid: Mapped[int] = mapped_column(
        ForeignKey("universities.unitid"), nullable=False, index=True
    )
    # 500 chars, not 255: real IPEDS HD.IALIAS entries run past 255 for some
    # institutions (e.g. long self-submitted alias strings) — see hd_importer.
    alias: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    alias_type: Mapped[AliasType] = mapped_column(
        Enum(AliasType, name="alias_type"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    university: Mapped[University] = relationship(back_populates="aliases")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"UniversityAlias(unitid={self.unitid!r}, alias={self.alias!r})"
