from __future__ import annotations

import io
import re
from typing import Iterator, List, Optional, Tuple

from pypdf import PasswordType, PdfReader
from pypdf.errors import PdfReadError

from us_grad_recommender.catalog_adapters.base import (
    RawDegreeCandidate,
    RawProgramCandidate,
    RawRequirementCandidate,
)

# The real file signature every PDF starts with (ISO 32000-1 §7.5.2) —
# unlike CourseLeafAdapter's vendor CSS/JS markers, this is a universal,
# format-level signal, not institution-specific.
_PDF_MAGIC = b"%PDF-"

# --- Everything below this line is grounded in exactly one real PDF catalog
# (Alabama A&M University's 2026-2027 graduate catalog, 209 pages, fetched
# directly from aamu.edu — see tests/fixtures/pdf/ for the extracted
# single-page fixtures this is tested against) — not a general "how PDF
# catalogs are formatted" standard. Unlike CourseLeaf, there is no shared
# vendor template across institutions' self-authored PDF catalogs, so
# detect() below only checks "is this a real PDF" (universal); the
# structural patterns extract_*() rely on are AAMU-specific authoring
# conventions and are expected to need generalizing once a second real PDF
# catalog is inspected. Documented here rather than silently assumed to
# generalize.

# A program-overview page's degree line, verified against all ~27 real
# programs in the AAMU catalog (e.g. "Master of Science",
# "Master of Business Administration", "Doctor of Philosophy",
# "Education Specialist", "Master of Science Electrical Engineering").
# Anchored to the *whole* line deliberately — a laxer prefix match
# (`^Master of`) false-positived on ordinary prose that happened to start a
# line with "Master of Science degrees, 18 credit hours..." (page 30 of the
# real PDF, a mid-sentence line wrap).
_DEGREE_LINE = re.compile(r"^(Master of [A-Za-z ]+|Doctor of Philosophy|Education Specialist)$")

# AAMU repeats this running header/footer on every page, e.g. "DEPT OF
# BIOLOGICAL SCIENCES, CALNS, AAMU Graduate Catalog, 2026-2027 ~ 41 ~". Used
# to detect (and reject) the case where the line immediately before a
# degree line is actually this header, not a real program name — confirmed
# on the real "Food Science" PhD page, which has no program-name line at
# all before "Doctor of Philosophy". Better to skip that candidate than
# emit a fabricated program name.
_RUNNING_HEADER_MARKER = "AAMU Graduate Catalog"

# All-caps section headings on real program-overview pages ("MISSION
# STATEMENT", "PROGRAM DESCRIPTION", "ADMISSION REQUIREMENTS", "POLICY
# STATEMENT", "DEGREE REQUIREMENTS"). The real PDF text layer sometimes
# renders a double space mid-heading (font-kerning artifact of the source
# PDF, not a typo introduced here) — the regex tolerates any run of spaces.
_HEADING_LINE = re.compile(r"^[A-Z][A-Z ]{2,40}$")


class PdfCatalogAdapter:
    """Adapter for PDF-only catalogs (§9's adapter registry).

    §14 decision 4: text-layer extraction only. If a PDF has no usable
    text layer (a scanned image), extract_*() return empty lists rather
    than attempting OCR — routing that case to manual review is a
    pipeline-level decision (§10), not this adapter's job, since this PR
    doesn't build the pipeline/review-task-creation step.
    """

    name = "pdf"

    def detect(self, url: str, content: bytes) -> bool:
        return content.startswith(_PDF_MAGIC)

    def has_usable_text_layer(self, content: bytes) -> bool:
        """Not part of CatalogAdapter — an extra capability the (not yet
        built) ingestion pipeline can call to decide whether a PDF needs a
        manual-entry review task per §14 decision 4, instead of every
        adapter needing its own ad hoc way to signal "found nothing".
        """
        reader = self._reader(content)
        if reader is None:
            return False
        sample = reader.pages[: min(5, len(reader.pages))]
        return any(page.extract_text().strip() for page in sample)

    def extract_programs(self, url: str, content: bytes) -> List[RawProgramCandidate]:
        candidates: List[RawProgramCandidate] = []
        for page_index, lines in self._iter_pages(content):
            found = self._find_program_and_degree(lines)
            if found is None:
                continue
            name_line, _degree_line = found
            candidates.append(
                RawProgramCandidate(
                    name=name_line,
                    program_url=f"{url}#page={page_index + 1}",
                    source_url=url,
                )
            )
        return candidates

    def extract_degrees(self, url: str, content: bytes) -> List[RawDegreeCandidate]:
        candidates: List[RawDegreeCandidate] = []
        for _page_index, lines in self._iter_pages(content):
            found = self._find_program_and_degree(lines)
            if found is None:
                continue
            _name_line, degree_line = found
            candidates.append(RawDegreeCandidate(raw_degree_name=degree_line, source_url=url))
        return candidates

    @staticmethod
    def _find_program_and_degree(lines: List[str]) -> Optional[Tuple[str, str]]:
        """Scans one page's lines for the real, verified pattern: a degree
        name on its own line, immediately preceded by the program name.
        Returns None if no degree line is found, or if the preceding line
        is the running header rather than a real program name (the "Food
        Science" PhD case — see module docstring).
        """
        for i in range(1, len(lines)):
            if not _DEGREE_LINE.match(lines[i]):
                continue
            name_line = lines[i - 1]
            if _RUNNING_HEADER_MARKER in name_line:
                continue
            return name_line, lines[i]
        return None

    def extract_requirements(self, url: str, content: bytes) -> List[RawRequirementCandidate]:
        candidates: List[RawRequirementCandidate] = []
        for page_index, lines in self._iter_pages(content):
            current_label: Optional[str] = None
            current_parts: List[str] = []
            for line in lines:
                if _HEADING_LINE.match(line) and len(line.split()) <= 5:
                    if current_label is not None and current_parts:
                        candidates.append(
                            RawRequirementCandidate(
                                section_label=" ".join(current_label.split()).title(),
                                raw_text="\n".join(current_parts),
                                source_url=f"{url}#page={page_index + 1}",
                            )
                        )
                    current_label = line
                    current_parts = []
                elif current_label is not None:
                    current_parts.append(line)
            if current_label is not None and current_parts:
                candidates.append(
                    RawRequirementCandidate(
                        section_label=" ".join(current_label.split()).title(),
                        raw_text="\n".join(current_parts),
                        source_url=f"{url}#page={page_index + 1}",
                    )
                )
        return candidates

    @staticmethod
    def _reader(content: bytes) -> Optional[PdfReader]:
        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                # Every real PDF checked so far (AAMU's live catalog) is
                # encrypted with an empty user password — a common
                # copy-restriction pattern that still allows normal
                # reading. This is a no-op on a non-encrypted PDF.
                #
                # decrypt()'s return value must be checked: a PDF
                # encrypted with a real, unknown password (plausible for
                # a second real institution — see this module's top
                # comment on generalizing beyond AAMU) leaves the reader
                # still encrypted. Every downstream .extract_text() call
                # raises FileNotDecryptedError in that case, which is not
                # caught here — so an unchecked decrypt() would crash the
                # caller instead of the documented "return empty/False"
                # fallback behavior.
                if reader.decrypt("") == PasswordType.NOT_DECRYPTED:
                    return None
            return reader
        except (PdfReadError, ValueError):
            return None

    def _iter_pages(self, content: bytes) -> Iterator[Tuple[int, List[str]]]:
        reader = self._reader(content)
        if reader is None:
            return
        for page_index, page in enumerate(reader.pages):
            text = page.extract_text()
            lines = [ln.strip() for ln in text.split("\n")]
            lines = [ln for ln in lines if ln]
            if lines:
                yield page_index, lines
