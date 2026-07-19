"""Idempotent importer for the IPEDS HD (institutional characteristics) file.

Source: https://nces.ed.gov/ipeds/datacenter/data/HD<year>.zip (hd<year>.csv).

Parsing is deliberately conservative: a row that is missing UNITID or the
institution name is skipped and reported rather than guessed at, per the
mandatory rule to never invent institutional facts.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date
from typing import IO, Iterable, Iterator, List, Optional

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from us_grad_recommender.importers.ipeds.mappings import (
    CONTROL_TO_SECTOR,
    CYACTIVE_IS_ACTIVE,
    DEGGRANT_IS_DEGREE_GRANTING,
    GROFFER_OFFERS_GRADUATE,
    HLOFFER_LABELS,
    MASTERS_GRANTING_BASIS,
    MASTERS_OR_ABOVE_HLOFFER_CODES,
)
from us_grad_recommender.models.university import CoverageTier, Sector, University, UniversityAlias

# Batch size for the chunked upsert. HD files run ~6,000 rows; this keeps
# each statement well under Postgres's parameter limit while avoiding one
# round trip per row.
UPSERT_CHUNK_SIZE = 500


@dataclass
class ParsedInstitution:
    unitid: int
    canonical_name: str
    website: Optional[str]
    city: Optional[str]
    state: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    sector: Sector
    highest_degree_level: Optional[int]
    highest_degree_label: Optional[str]
    masters_granting: bool
    masters_granting_basis: Optional[str]
    degree_granting: Optional[bool]
    active: bool
    aliases: List[str] = field(default_factory=list)


@dataclass
class RowIssue:
    line_number: int
    unitid_raw: str
    reason: str


@dataclass
class HdImportSummary:
    rows_read: int = 0
    universities_upserted: int = 0
    universities_skipped_not_masters_granting: int = 0
    universities_skipped_invalid: int = 0
    aliases_upserted: int = 0
    issues: List[RowIssue] = field(default_factory=list)


def _clean_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_int(value: Optional[str]) -> Optional[int]:
    value = _clean_str(value)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float(value: Optional[str]) -> Optional[float]:
    value = _clean_str(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


# HD.IALIAS is documented by NCES only as "a character string field that
# contains aliases" with no stated delimiter. Empirically, runs of two or
# more spaces separate distinct self-submitted alias strings (confirmed
# against the real HD2023 release: 88 institutions carry multiple aliases
# this way). A single run of spaces is not treated as a separator since
# ordinary institution names contain single spaces.
_ALIAS_SPLIT_RE = re.compile(r"\s{2,}")


def _split_aliases(raw: Optional[str]) -> List[str]:
    value = _clean_str(raw)
    if not value:
        return []
    parts = [part.strip() for part in _ALIAS_SPLIT_RE.split(value) if part.strip()]
    seen = set()
    deduped = []
    for part in parts:
        if part not in seen:
            seen.add(part)
            deduped.append(part)
    return deduped


def compute_masters_granting(
    cyactive: Optional[int], deggrant: Optional[int], groffer: Optional[int], hloffer: Optional[int]
) -> bool:
    """See mappings.MASTERS_GRANTING_BASIS for the exact rule and its source."""
    return (
        cyactive == CYACTIVE_IS_ACTIVE
        and deggrant == DEGGRANT_IS_DEGREE_GRANTING
        and groffer == GROFFER_OFFERS_GRADUATE
        and hloffer in MASTERS_OR_ABOVE_HLOFFER_CODES
    )


def parse_hd_row(row: dict) -> ParsedInstitution | RowIssue:
    line_unitid_raw = row.get("UNITID", "")
    unitid = _parse_int(row.get("UNITID"))
    canonical_name = _clean_str(row.get("INSTNM"))

    if unitid is None:
        return RowIssue(
            line_number=-1, unitid_raw=line_unitid_raw, reason="missing or non-numeric UNITID"
        )
    if canonical_name is None:
        return RowIssue(line_number=-1, unitid_raw=line_unitid_raw, reason="missing INSTNM")

    control = _parse_int(row.get("CONTROL"))
    sector = (
        CONTROL_TO_SECTOR.get(control, Sector.UNKNOWN) if control is not None else Sector.UNKNOWN
    )

    hloffer = _parse_int(row.get("HLOFFER"))
    highest_degree_label = HLOFFER_LABELS.get(hloffer) if hloffer is not None else None

    cyactive = _parse_int(row.get("CYACTIVE"))
    deggrant = _parse_int(row.get("DEGGRANT"))
    groffer = _parse_int(row.get("GROFFER"))

    masters_granting = compute_masters_granting(cyactive, deggrant, groffer, hloffer)

    aliases = _split_aliases(row.get("IALIAS"))

    return ParsedInstitution(
        unitid=unitid,
        canonical_name=canonical_name,
        website=_clean_str(row.get("WEBADDR")),
        city=_clean_str(row.get("CITY")),
        state=_clean_str(row.get("STABBR")),
        latitude=_parse_float(row.get("LATITUDE")),
        longitude=_parse_float(row.get("LONGITUD")),
        sector=sector,
        highest_degree_level=hloffer,
        highest_degree_label=highest_degree_label,
        masters_granting=masters_granting,
        masters_granting_basis=MASTERS_GRANTING_BASIS if masters_granting else None,
        degree_granting=(deggrant == DEGGRANT_IS_DEGREE_GRANTING) if deggrant is not None else None,
        active=(cyactive == CYACTIVE_IS_ACTIVE),
        aliases=aliases,
    )


def read_hd_rows(f: IO[str]) -> Iterator[dict]:
    return iter(csv.DictReader(f))


def _chunks(items: List, size: int) -> Iterator[List]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _upsert_universities(
    session: Session, institutions: List[ParsedInstitution], ipeds_year: int, run_date: date
) -> int:
    if not institutions:
        return 0

    rows = [
        {
            "unitid": inst.unitid,
            "canonical_name": inst.canonical_name,
            "website": inst.website,
            "city": inst.city,
            "state": inst.state,
            "latitude": inst.latitude,
            "longitude": inst.longitude,
            "sector": inst.sector,
            "highest_degree_level": inst.highest_degree_level,
            "highest_degree_label": inst.highest_degree_label,
            "masters_granting": inst.masters_granting,
            "masters_granting_basis": inst.masters_granting_basis,
            "degree_granting": inst.degree_granting,
            "active": inst.active,
            "coverage_tier": CoverageTier.INDEXED,
            "ipeds_year": ipeds_year,
            "source_dataset": f"IPEDS HD{ipeds_year}",
            "last_verified_at": run_date,
        }
        for inst in institutions
    ]

    update_columns = {
        "canonical_name",
        "website",
        "city",
        "state",
        "latitude",
        "longitude",
        "sector",
        "highest_degree_level",
        "highest_degree_label",
        "masters_granting",
        "masters_granting_basis",
        "degree_granting",
        "active",
        "ipeds_year",
        "source_dataset",
        "last_verified_at",
    }

    # coverage_tier and created_at are intentionally excluded from the update
    # set so a re-import never regresses coverage progress made by later
    # phases (program discovery, enrichment) or overwrites the original
    # insert timestamp.
    total = 0
    for chunk in _chunks(rows, UPSERT_CHUNK_SIZE):
        stmt = pg_insert(University).values(chunk)
        set_ = {col: getattr(stmt.excluded, col) for col in update_columns}
        set_["updated_at"] = func.now()
        stmt = stmt.on_conflict_do_update(
            index_elements=["unitid"],
            set_=set_,
            where=(stmt.excluded.ipeds_year >= University.ipeds_year),
        )
        session.execute(stmt)
        total += len(chunk)
    return total


def _upsert_aliases(
    session: Session, institutions: List[ParsedInstitution], ipeds_year: int
) -> int:
    alias_rows = [
        {
            "unitid": inst.unitid,
            "alias": alias,
            "alias_type": "ipeds_alias",
            "source": f"IPEDS HD{ipeds_year}",
        }
        for inst in institutions
        for alias in inst.aliases
    ]
    if not alias_rows:
        return 0

    total = 0
    for chunk in _chunks(alias_rows, UPSERT_CHUNK_SIZE):
        stmt = pg_insert(UniversityAlias).values(chunk)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_university_alias")
        session.execute(stmt)
        total += len(chunk)
    return total


def import_hd_file(
    session: Session,
    rows: Iterable[dict],
    ipeds_year: int,
    masters_only: bool = True,
    run_date: Optional[date] = None,
) -> HdImportSummary:
    """Idempotently upsert institutions from a parsed IPEDS HD CSV.

    Safe to call repeatedly with the same (or a newer) ipeds_year: existing
    rows are updated in place by UNITID, never duplicated. Calling with an
    older ipeds_year than what is already stored for a given institution is
    a no-op for that institution's identity fields (see the WHERE guard in
    _upsert_universities), so replaying an older extract cannot silently
    regress newer data.
    """
    run_date = run_date or date.today()
    summary = HdImportSummary()
    accepted: List[ParsedInstitution] = []

    for line_number, row in enumerate(rows, start=2):  # header is line 1
        summary.rows_read += 1
        parsed = parse_hd_row(row)
        if isinstance(parsed, RowIssue):
            parsed.line_number = line_number
            summary.issues.append(parsed)
            summary.universities_skipped_invalid += 1
            continue
        if masters_only and not parsed.masters_granting:
            summary.universities_skipped_not_masters_granting += 1
            continue
        accepted.append(parsed)

    summary.universities_upserted = _upsert_universities(session, accepted, ipeds_year, run_date)
    summary.aliases_upserted = _upsert_aliases(session, accepted, ipeds_year)
    return summary
