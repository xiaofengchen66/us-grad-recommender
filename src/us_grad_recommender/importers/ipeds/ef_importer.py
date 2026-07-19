"""Idempotent importer for the IPEDS EF (fall enrollment) file, component A.

Source: https://nces.ed.gov/ipeds/datacenter/data/EF<year>A.zip (ef<year>a.csv).

EF is a "long" file: each institution contributes multiple rows, one per
(EFALEVEL, ...) combination. We only need two rows per institution:

  EFALEVEL=1  ("All students total")     -> EFTOTLT = total_enrollment
  EFALEVEL=12 ("All students, Graduate") -> EFTOTLT = graduate_enrollment
                                             EFNRALT = international_graduate_enrollment
                                             (EFNRALT = nonresident alien total)

This importer only updates institutions that already exist (i.e. were
already imported from an HD file) — EF alone carries no institution
identity fields, so it must never be used to create a University row.
Institutions present in the EF file but absent from the database are
counted as skipped and reported, not silently dropped.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import IO, Dict, Iterable, Iterator, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from us_grad_recommender.importers.ipeds.mappings import (
    EFALEVEL_ALL_STUDENTS_GRADUATE,
    EFALEVEL_ALL_STUDENTS_TOTAL,
)
from us_grad_recommender.models.university import University

RELEVANT_EFALEVELS = {EFALEVEL_ALL_STUDENTS_TOTAL, EFALEVEL_ALL_STUDENTS_GRADUATE}

UPSERT_CHUNK_SIZE = 500


@dataclass
class EnrollmentFacts:
    total_enrollment: Optional[int] = None
    graduate_enrollment: Optional[int] = None
    international_graduate_enrollment: Optional[int] = None


@dataclass
class EfImportSummary:
    rows_read: int = 0
    institutions_updated: int = 0
    institutions_skipped_not_found: int = 0
    skipped_unitids: List[int] = field(default_factory=list)


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


def read_ef_rows(f: IO[str]) -> Iterator[dict]:
    return iter(csv.DictReader(f))


def collect_enrollment_facts(rows: Iterable[dict]) -> Dict[int, EnrollmentFacts]:
    """Reduce the long EF file down to one EnrollmentFacts per UNITID."""
    facts: Dict[int, EnrollmentFacts] = {}

    for row in rows:
        unitid = _parse_int(row.get("UNITID"))
        efalevel = _parse_int(row.get("EFALEVEL"))
        if unitid is None or efalevel not in RELEVANT_EFALEVELS:
            continue

        entry = facts.setdefault(unitid, EnrollmentFacts())
        eftotlt = _parse_int(row.get("EFTOTLT"))
        efnralt = _parse_int(row.get("EFNRALT"))

        if efalevel == EFALEVEL_ALL_STUDENTS_TOTAL:
            entry.total_enrollment = eftotlt
        elif efalevel == EFALEVEL_ALL_STUDENTS_GRADUATE:
            entry.graduate_enrollment = eftotlt
            entry.international_graduate_enrollment = efnralt

    return facts


def _chunks(items: List, size: int) -> Iterator[List]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def import_ef_file(
    session: Session,
    rows: Iterable[dict],
    ef_year: int,
) -> EfImportSummary:
    """Idempotently update enrollment fields on existing University rows.

    Safe to call repeatedly: each run recomputes and overwrites the same
    three enrollment fields (plus enrollment_year) from the source file,
    so re-running with the same file is a no-op and re-running with a
    newer year's file simply refreshes the figures.
    """
    summary = EfImportSummary()
    row_list = list(rows)
    summary.rows_read = len(row_list)

    facts_by_unitid = collect_enrollment_facts(row_list)
    if not facts_by_unitid:
        return summary

    unitids = list(facts_by_unitid.keys())
    existing_unitids: set = set()
    for chunk in _chunks(unitids, UPSERT_CHUNK_SIZE):
        found = session.execute(
            select(University.unitid).where(University.unitid.in_(chunk))
        ).scalars()
        existing_unitids.update(found)

    for unitid, entry in facts_by_unitid.items():
        if unitid not in existing_unitids:
            summary.institutions_skipped_not_found += 1
            summary.skipped_unitids.append(unitid)
            continue

        university = session.get(University, unitid)
        assert university is not None  # guaranteed by the existing_unitids check above
        university.total_enrollment = entry.total_enrollment
        university.graduate_enrollment = entry.graduate_enrollment
        university.international_graduate_enrollment = entry.international_graduate_enrollment
        university.enrollment_year = ef_year
        summary.institutions_updated += 1

    return summary
