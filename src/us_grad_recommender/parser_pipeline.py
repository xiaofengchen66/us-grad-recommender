"""Wires catalog-adapter output (``catalog_adapters.Raw*Candidate``) into
``programs`` table writes — the "parse → write" half of §9's pipeline
diagram. Deliberately narrow first version:

- Only ``RawProgramCandidate``/``RawDegreeCandidate`` -> ``Program`` rows.
  ``ProgramTrack``/``AdmissionRequirement`` writing is a separate,
  later piece — it needs its own judgment call (what counts as a
  "track") that this PR doesn't make.
- The caller supplies ``academic_unit_id``. This module does not try to
  resolve which ``AcademicUnit`` a listing/program page belongs to —
  that's a real, separate matching problem.
- Canonicalization is whitespace normalization only. No case changes, no
  abbreviation expansion — both real adapters already produce clean
  names, so anything fancier would be an unevidenced guess.
- Degree-type mapping uses a small, closed, evidence-only table (see
  ``_DEGREE_TYPE_TABLE``) built from real strings seen in the
  CourseLeaf/UT Austin and PDF/AAMU fixtures — nothing stripped or
  guessed for an unfamiliar phrase. A degree that doesn't match gets no
  ``Program`` row; it gets a ``data_review_task`` anchored to the real
  ``AcademicUnit`` instead (there's no ``Program`` row to anchor to yet
  — see ``ingest_program_degrees``'s docstring for why that, not a fake
  id, is what this points at).
- Duplicate handling relies on the existing ``uq_program_identity``
  unique constraint (no new migration, no pg_trgm fuzzy matching yet —
  that needs its own migration to enable the Postgres extension, kept as
  a separate, explicitly-flagged future step). A collision — checked
  proactively, with a catch of the unique-constraint IntegrityError as a
  defensive fallback for a genuine race — is turned into a
  ``data_review_task`` anchored to the *real, already-existing* colliding
  ``Program`` row (§11 point 3's explicit requirement: a raw constraint
  violation must never bubble up as an unhandled error).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from us_grad_recommender.catalog_adapters import RawDegreeCandidate, RawProgramCandidate
from us_grad_recommender.models.catalog import DegreeLevel, DegreeType, Program
from us_grad_recommender.models.common import VerificationStatus
from us_grad_recommender.models.review import CatalogEntityType, DataReviewTask, ReviewReason
from us_grad_recommender.review_queue import create_review_task

# (prefix, code, label, level) — every entry is a literal degree-name
# string actually seen in tests/fixtures/courseleaf/ or tests/fixtures/pdf/
# during Phase 2.2B, not a guessed/generalized pattern. Matched as a
# *prefix* (not exact-string) so CourseLeaf's subject-suffixed form
# ("Master of Science in Computer Science") and AAMU's plain form
# ("Master of Science") both map to the same MS code — the subject is
# already captured separately in Program.canonical_name.
#
# Order only matters if one real string were itself a prefix of another;
# checked directly against this exact list and none of them are (e.g.
# "Master of Science" is not a prefix of "Master of Social Work" — they
# diverge at the 11th character).
_DEGREE_TYPE_TABLE: list[tuple[str, str, str, DegreeLevel]] = [
    ("Doctor of Philosophy", "PHD", "Doctor of Philosophy", DegreeLevel.DOCTORAL),
    ("Master of Science", "MS", "Master of Science", DegreeLevel.MASTERS),
    (
        "Master of Business Administration",
        "MBA",
        "Master of Business Administration",
        DegreeLevel.MASTERS,
    ),
    ("Master of Education", "MED", "Master of Education", DegreeLevel.MASTERS),
    ("Master of Arts", "MA", "Master of Arts", DegreeLevel.MASTERS),
    (
        "Master of Public Administration",
        "MPA",
        "Master of Public Administration",
        DegreeLevel.MASTERS,
    ),
    ("Master of Social Work", "MSW", "Master of Social Work", DegreeLevel.MASTERS),
    ("Master of Engineering", "MENG", "Master of Engineering", DegreeLevel.MASTERS),
    (
        "Master of Urban and Regional Planning",
        "MURP",
        "Master of Urban and Regional Planning",
        DegreeLevel.MASTERS,
    ),
    # Ed.S. is a real post-master's, pre-doctoral credential — not a
    # "certificate" in the usual (short, non-degree) sense, so OTHER is
    # the honest fit among DegreeLevel's four values, not CERTIFICATE.
    ("Education Specialist", "EDS", "Education Specialist", DegreeLevel.OTHER),
]


def _match_degree_type(raw_degree_name: str) -> tuple[str, str, DegreeLevel] | None:
    for prefix, code, label, level in _DEGREE_TYPE_TABLE:
        if raw_degree_name.startswith(prefix):
            return code, label, level
    return None


def _get_degree_type(session: Session, code: str) -> DegreeType | None:
    return session.get(DegreeType, code)


def _get_or_create_degree_type(
    session: Session, code: str, label: str, level: DegreeLevel
) -> DegreeType:
    degree_type = _get_degree_type(session, code)
    if degree_type is not None:
        return degree_type
    try:
        with session.begin_nested():
            degree_type = DegreeType(code=code, label=label, level=level)
            session.add(degree_type)
            session.flush()
    except IntegrityError:
        # Same concurrent-first-creation race Program's insert path
        # guards against (§11 point 3's "never bubble up unhandled"
        # applies just as much to this table) — a second caller creating
        # the same code for the first time between our get() and our
        # insert. Re-fetch the real row rather than raising.
        degree_type = _get_degree_type(session, code)
        if degree_type is None:
            raise RuntimeError(
                f"IntegrityError on DegreeType insert but no row found for code={code!r}"
            ) from None
    return degree_type


def _canonicalize(name: str) -> str:
    return " ".join(name.split())


# Program.raw_degree_name/canonical_name column limits (models/catalog.py).
# An input exceeding these isn't just "too long to store" — it's a real
# signal of likely garbled/concatenated extraction (this project's PDF
# adapter fixtures document that failure mode directly), so it's routed
# to review rather than silently truncated and written as plausible-
# looking-but-wrong data.
_MAX_RAW_DEGREE_NAME_LENGTH = 255
_MAX_CANONICAL_NAME_LENGTH = 500


def _find_existing_program(
    session: Session, *, academic_unit_id: int, degree_type_code: str, canonical_name: str
) -> Program | None:
    """Matches on identity only — does not filter by ``Program.status``.
    A discontinued program (§12's status-based retirement model) is
    matched and flagged ``POSSIBLE_DUPLICATE`` the same as an active one,
    rather than being considered for revival. §12 doesn't resolve what
    "rediscovering a discontinued program" should do, so this doesn't
    either — disclosed here rather than silently assumed away.
    """
    stmt = select(Program).where(
        Program.academic_unit_id == academic_unit_id,
        Program.degree_type_code == degree_type_code,
        Program.canonical_name == canonical_name,
    )
    return session.execute(stmt).scalar_one_or_none()


@dataclass(frozen=True)
class ProgramIngestOutcome:
    """One outcome per input ``RawDegreeCandidate``. ``review_task`` is
    always set — every path, including a successful insert, creates one
    (§10's no-auto-promotion rule: even a brand-new row needs a
    ``FIRST_SEEN`` task before it can move past ``PARSED``).
    ``program`` is set only when a row was actually written; on any
    review-routed path (unmapped degree type, name too long, duplicate)
    it's ``None``. Do not assume ``review_task`` implies ``program`` is
    ``None`` — that only holds for the review-routed paths, not the
    success path.
    """

    degree: RawDegreeCandidate
    program: Program | None
    review_task: DataReviewTask | None


def ingest_program_degrees(
    session: Session,
    *,
    academic_unit_id: int,
    program: RawProgramCandidate,
    degrees: list[RawDegreeCandidate],
    last_verified_at: date,
    source_snapshot_id: int | None = None,
    verification_status: VerificationStatus = VerificationStatus.PARSED,
) -> list[ProgramIngestOutcome]:
    """One ``Program`` row per matched degree — a department page
    declaring both an MS and a PhD for the same subject genuinely needs
    two rows, since ``uq_program_identity`` includes ``degree_type_code``.
    This is grounded in a real case, not hypothetical: UT Austin's own
    CS program page declares both "Master of Science in Computer
    Science" and "Doctor of Philosophy" (see
    tests/fixtures/courseleaf/ut_austin_computer_science_program.html,
    exercised directly in
    tests/test_parser_pipeline.py::test_ingest_real_courseleaf_program_creates_one_row_per_degree).
    (Earlier revisions of this docstring cited catalog_adapters.pdf's
    "Food Science" note for this same claim — that was wrong. That note
    documents a *different* real finding, a PhD line with no program-name
    line before it, so the candidate is skipped entirely rather than
    paired with anything.)

    ``verification_status`` defaults to PARSED because every real caller
    today (``CourseLeafAdapter``, ``PdfCatalogAdapter``) is a
    deterministic adapter. Per §9/§10, LLM-fallback output must always
    land at NEEDS_REVIEW, never PARSED — this parameter exists so a
    future caller wiring an LLM-fallback adapter through this same
    function has to consciously override the default rather than
    silently inheriting deterministic-confidence status for
    non-deterministic output.

    ``source_snapshot_id`` is accepted and threaded onto
    ``Program.last_seen_snapshot_id`` even though no caller can supply a
    real one yet (no live fetch layer exists) — the parameter exists so
    that gap is visible in this function's shape rather than silently
    baked in by omission. Pass ``None`` until a real snapshot pipeline
    exists.

    This function is insert-only: calling it again for a program already
    in the table (e.g. a routine re-crawl per §6, not just "an adapter
    re-running without proper idempotency") creates a fresh
    ``POSSIBLE_DUPLICATE`` review task every time rather than refreshing
    ``last_seen_snapshot_id``/``last_verified_at`` on the existing row.
    Wiring this into a recurring re-crawl job needs that refresh path
    added first — not safe to reuse as-is for §6's workflow.

    Every review task this creates points at a real, already-existing
    row — never a fabricated id. An unmapped degree type has no
    ``Program`` row to anchor to (none was written), so it's anchored to
    the caller-supplied ``academic_unit_id`` instead, which does exist;
    ``field_name`` carries the raw degree text and program name a
    reviewer needs to act on it. A duplicate collision is anchored to the
    real, already-existing colliding ``Program`` row, found by a
    proactive lookup (with the unique-constraint ``IntegrityError``
    caught as a defensive fallback for a genuine race, not the primary
    mechanism).

    Both non-duplicate review cases (unmapped degree type, name too long
    to store) use ``ReviewReason.LOW_CONFIDENCE`` — none of the six
    reasons in §5 is a perfect fit for "no mapping exists"/"looks
    garbled," and LOW_CONFIDENCE is the closest: both signal "don't trust
    this extraction as-is," which is the property a reviewer scanning by
    reason actually cares about.
    """
    canonical_name = _canonicalize(program.name)
    outcomes = []
    for degree in degrees:
        match = _match_degree_type(degree.raw_degree_name)
        if match is None:
            # field_name is String(100) — truncate defensively so an
            # unusually long raw degree/program string can't turn into
            # an insert error on the review task itself. Degree text
            # goes first since it's the more important piece for a
            # reviewer deciding whether the mapping table needs a new
            # entry; the program name is context for *which* page.
            field_name = f"unmapped_degree_type:{degree.raw_degree_name} program={program.name}"[
                :100
            ]
            task = create_review_task(
                session,
                entity_type=CatalogEntityType.ACADEMIC_UNIT,
                entity_id=academic_unit_id,
                reason=ReviewReason.LOW_CONFIDENCE,
                field_name=field_name,
            )
            outcomes.append(ProgramIngestOutcome(degree=degree, program=None, review_task=task))
            continue

        if (
            len(degree.raw_degree_name) > _MAX_RAW_DEGREE_NAME_LENGTH
            or len(canonical_name) > _MAX_CANONICAL_NAME_LENGTH
        ):
            # Checked before _get_or_create_degree_type() below —
            # deliberately not doing get-or-create work for a row that's
            # about to be rejected anyway.
            field_name = f"name_too_long:{degree.raw_degree_name} program={program.name}"[:100]
            task = create_review_task(
                session,
                entity_type=CatalogEntityType.ACADEMIC_UNIT,
                entity_id=academic_unit_id,
                reason=ReviewReason.LOW_CONFIDENCE,
                field_name=field_name,
            )
            outcomes.append(ProgramIngestOutcome(degree=degree, program=None, review_task=task))
            continue

        code, label, level = match
        degree_type = _get_or_create_degree_type(session, code, label, level)

        existing = _find_existing_program(
            session,
            academic_unit_id=academic_unit_id,
            degree_type_code=degree_type.code,
            canonical_name=canonical_name,
        )
        if existing is not None:
            task = create_review_task(
                session,
                entity_type=CatalogEntityType.PROGRAM,
                entity_id=existing.id,
                reason=ReviewReason.POSSIBLE_DUPLICATE,
            )
            outcomes.append(ProgramIngestOutcome(degree=degree, program=None, review_task=task))
            continue

        new_program = Program(
            academic_unit_id=academic_unit_id,
            degree_type_code=degree_type.code,
            raw_degree_name=degree.raw_degree_name,
            canonical_name=canonical_name,
            program_url=program.program_url,
            verification_status=verification_status,
            last_verified_at=last_verified_at,
            last_seen_snapshot_id=source_snapshot_id,
        )
        try:
            with session.begin_nested():
                session.add(new_program)
                session.flush()
        except IntegrityError:
            # Defensive fallback for a genuine race the proactive check
            # above didn't catch (a row created concurrently between our
            # check and our insert) — re-query for the real colliding row
            # rather than losing the reference.
            existing = _find_existing_program(
                session,
                academic_unit_id=academic_unit_id,
                degree_type_code=degree_type.code,
                canonical_name=canonical_name,
            )
            if existing is None:
                # The IntegrityError guarantees a real collision exists;
                # if we can't find it, something more fundamental than
                # this duplicate-handling path is wrong. A plain
                # assert would be stripped under -O — raise explicitly.
                raise RuntimeError(
                    "IntegrityError on Program insert but no colliding row found for "
                    f"academic_unit_id={academic_unit_id}, degree_type_code={degree_type.code}, "
                    f"canonical_name={canonical_name!r}"
                ) from None
            task = create_review_task(
                session,
                entity_type=CatalogEntityType.PROGRAM,
                entity_id=existing.id,
                reason=ReviewReason.POSSIBLE_DUPLICATE,
            )
            outcomes.append(ProgramIngestOutcome(degree=degree, program=None, review_task=task))
            continue

        review_task = create_review_task(
            session,
            entity_type=CatalogEntityType.PROGRAM,
            entity_id=new_program.id,
            reason=ReviewReason.FIRST_SEEN,
        )
        outcomes.append(
            ProgramIngestOutcome(degree=degree, program=new_program, review_task=review_task)
        )
    return outcomes
