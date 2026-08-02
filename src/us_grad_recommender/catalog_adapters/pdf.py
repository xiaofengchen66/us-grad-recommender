from __future__ import annotations

import io
import re
from typing import Iterator, List, Optional, Tuple

from pypdf import PasswordType, PdfReader

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

        Checks every page, not a fixed-size sample: any() short-circuits
        on the first page with real text, so this is only O(all pages) in
        the true no-usable-text-layer case — exactly the case this method
        exists to detect accurately, so scanning fewer pages to save time
        there would trade away the one thing that matters. A fixed
        early-page sample (an earlier version checked only the first 5)
        would wrongly report "no text layer" for a real catalog with a
        graphical cover/seal/TOC in its first few pages followed by
        genuine text-layer content later — a plausible layout this
        adapter has no evidence ruling out.
        """
        return any(lines for _page_index, lines in self._iter_pages(content))

    def extract_programs(self, url: str, content: bytes) -> List[RawProgramCandidate]:
        numbered_lines = list(self._iter_lines(content))
        return [
            RawProgramCandidate(
                name=name_line,
                program_url=f"{url}#page={page_index + 1}",
                source_url=f"{url}#page={page_index + 1}",
            )
            for page_index, name_line, _degree_line in self._find_programs_and_degrees(
                numbered_lines
            )
        ]

    def extract_degrees(self, url: str, content: bytes) -> List[RawDegreeCandidate]:
        numbered_lines = list(self._iter_lines(content))
        return [
            RawDegreeCandidate(
                raw_degree_name=degree_line, source_url=f"{url}#page={page_index + 1}"
            )
            for page_index, _name_line, degree_line in self._find_programs_and_degrees(
                numbered_lines
            )
        ]

    @staticmethod
    def _find_programs_and_degrees(
        numbered_lines: List[Tuple[int, str]],
    ) -> List[Tuple[int, str, str]]:
        """Scans the *whole document's* flattened (page_index, line)
        stream — not one page at a time — for the real, verified pattern:
        a degree name on its own line, immediately preceded by the
        program name. Scanning across page boundaries (rather than
        resetting per page) matters because nothing about a PDF's layout
        guarantees a program's name/degree pair can't be split by a page
        break, even though zero such splits exist in the real 209-page
        AAMU catalog this is verified against (checked directly, not
        assumed safe). Returns every match found, not just the first per
        page — nothing guarantees exactly one program per page either
        (§7.4 covers departments offering more than one degree level),
        even though no real AAMU page currently has more than one. Skips
        a match where the preceding line is the running header rather
        than a real program name (the "Food Science" PhD case — see
        module docstring) instead of emitting a fabricated program name.
        """
        found = []
        for i in range(1, len(numbered_lines)):
            page_index, line = numbered_lines[i]
            if not _DEGREE_LINE.match(line):
                continue
            _prev_page_index, name_line = numbered_lines[i - 1]
            if _RUNNING_HEADER_MARKER in name_line:
                continue
            found.append((page_index, name_line, line))
        return found

    def extract_requirements(self, url: str, content: bytes) -> List[RawRequirementCandidate]:
        """Splits each page into raw text blocks by ALL-CAPS heading line
        (mirrors CourseLeafAdapter's split-by-<h2>). section_label is
        whitespace-normalized only (the real PDF text layer sometimes
        renders a double space mid-heading) — case is left as authored
        (all-caps), not title-cased, since that would be interpreting the
        source rather than preserving it, unlike CourseLeafAdapter's
        headings, which really are mixed-case in the HTML.
        """
        candidates: List[RawRequirementCandidate] = []
        for page_index, lines in self._iter_pages(content):
            current_label: Optional[str] = None
            current_parts: List[str] = []
            for line in lines:
                if _HEADING_LINE.match(line) and len(line.split()) <= 5:
                    section = self._section_or_none(current_label, current_parts, url, page_index)
                    if section is not None:
                        candidates.append(section)
                    current_label = line
                    current_parts = []
                elif current_label is not None:
                    current_parts.append(line)
            section = self._section_or_none(current_label, current_parts, url, page_index)
            if section is not None:
                candidates.append(section)
        return candidates

    @staticmethod
    def _section_or_none(
        label: Optional[str], parts: List[str], url: str, page_index: int
    ) -> Optional[RawRequirementCandidate]:
        if label is None or not parts:
            return None
        return RawRequirementCandidate(
            section_label=" ".join(label.split()),
            raw_text="\n".join(parts),
            source_url=f"{url}#page={page_index + 1}",
        )

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
        except Exception:
            # Broad on purpose, same "fail gracefully, never crash the
            # caller" contract already applied to page.extract_text() in
            # _iter_pages() below. PdfReader() construction and decrypt()
            # are exposed to the same class of malformed/truncated
            # real-world PDFs (plausible once a live fetch layer exists —
            # network truncation, a non-standard xref table), and pypdf
            # doesn't guarantee every such failure surfaces as
            # PdfReadError/ValueError specifically rather than some other
            # internal exception.
            return None

    def _iter_pages(self, content: bytes) -> Iterator[Tuple[int, List[str]]]:
        reader = self._reader(content)
        if reader is None:
            return
        for page_index, page in enumerate(reader.pages):
            try:
                text = page.extract_text()
            except Exception:
                # pypdf is documented to occasionally raise on a
                # malformed content stream or unusual embedded font on a
                # single page. One bad page must not crash extraction of
                # the whole document — same "fail the unit, not the
                # batch" spirit as the decrypt() handling above, just
                # with the page as the unit instead of the whole PDF.
                continue
            lines = [ln.strip() for ln in text.split("\n")]
            lines = [ln for ln in lines if ln]
            if lines:
                yield page_index, lines

    def _iter_lines(self, content: bytes) -> Iterator[Tuple[int, str]]:
        for page_index, lines in self._iter_pages(content):
            for line in lines:
                yield page_index, line
