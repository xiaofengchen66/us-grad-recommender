from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class RawProgramCandidate:
    """A program name discovered on a listing page, not yet canonicalized.

    Mirrors ``Program.raw_degree_name``/``canonical_name``'s raw/normalized
    split (``models/catalog.py``) — canonicalization and duplicate
    detection (§11) happen later in the pipeline, not in the adapter.
    """

    name: str
    program_url: str
    source_url: str


@dataclass(frozen=True)
class RawDegreeCandidate:
    raw_degree_name: str
    source_url: str


@dataclass(frozen=True)
class RawRequirementCandidate:
    """One raw-text block tied to a section heading, not yet classified
    into a ``RequirementType`` (``models/catalog.py``) — that
    classification, along with sanity-bound validation, is the
    parser-pipeline's job (§9), not the adapter's.
    """

    section_label: str
    raw_text: str
    source_url: str


@runtime_checkable
class CatalogAdapter(Protocol):
    """Expands ``FULL_HANDOFF.md`` §5 / ``PHASE_2_CATALOG_DESIGN.md`` §9.

    §9's sketch takes ``html: str`` for the ``extract_*`` methods; this
    takes ``url`` too (added in the CourseLeafAdapter PR — every
    ``Raw*Candidate`` needs a ``source_url`` per §0's provenance
    principle, and relative links can't be resolved without the page URL)
    and ``content: bytes`` instead of ``html: str`` (added here, for
    ``PdfCatalogAdapter``). §14 decision 4 describes ``PdfCatalogAdapter``
    as itself "attempting text-layer extraction" from a PDF — that only
    works if the adapter receives the raw fetched bytes, not a pre-decoded
    string. HTML-based adapters (``CourseLeafAdapter``) just decode bytes
    to text as their first step; nothing about their parsing logic changes.
    """

    name: str

    def detect(self, url: str, content: bytes) -> bool: ...

    def extract_programs(self, url: str, content: bytes) -> List[RawProgramCandidate]: ...

    def extract_degrees(self, url: str, content: bytes) -> List[RawDegreeCandidate]: ...

    def extract_requirements(self, url: str, content: bytes) -> List[RawRequirementCandidate]: ...


class AdapterRegistry:
    """Tries adapters in order; the first ``detect()`` match wins (§9)."""

    def __init__(self, adapters: List[CatalogAdapter]):
        self._adapters = adapters

    def detect(self, url: str, content: bytes) -> Optional[CatalogAdapter]:
        for adapter in self._adapters:
            if adapter.detect(url, content):
                return adapter
        return None
