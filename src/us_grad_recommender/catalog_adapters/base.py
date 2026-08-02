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

    §9's sketch takes only ``html`` for the ``extract_*`` methods; here
    they also take ``url``, since every ``Raw*Candidate`` must carry a
    ``source_url`` (§0's raw-evidence-traceable-to-source principle) and
    relative links on a listing page can't be resolved to absolute program
    URLs without knowing the page they came from.
    """

    name: str

    def detect(self, url: str, html: str) -> bool: ...

    def extract_programs(self, url: str, html: str) -> List[RawProgramCandidate]: ...

    def extract_degrees(self, url: str, html: str) -> List[RawDegreeCandidate]: ...

    def extract_requirements(self, url: str, html: str) -> List[RawRequirementCandidate]: ...


class AdapterRegistry:
    """Tries adapters in order; the first ``detect()`` match wins (§9)."""

    def __init__(self, adapters: List[CatalogAdapter]):
        self._adapters = adapters

    def detect(self, url: str, html: str) -> Optional[CatalogAdapter]:
        for adapter in self._adapters:
            if adapter.detect(url, html):
                return adapter
        return None
