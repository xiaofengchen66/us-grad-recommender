from __future__ import annotations

from typing import List
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from us_grad_recommender.catalog_adapters.base import (
    RawDegreeCandidate,
    RawProgramCandidate,
    RawRequirementCandidate,
)

# Confirmed against real catalog pages during Phase 2.2B pilot scoping
# (docs/PHASE_2_CATALOG_DESIGN.md §13.1, docs/evidence/phase-2.2b-pilot-
# scoping-2026-07-31.md): every self-hosted CourseLeaf catalog
# (catalog.<school>.edu) references these two vendor assets.
_DETECT_MARKERS = ("courseleaf.css", "courseleaf.js")

# Non-program entries observed in real CourseLeaf "sitemap" listing pages
# (catalog.utexas.edu/graduate/areas-of-study/natural-sciences/ lists
# "Courses" alongside real programs; a program's own page links back to
# "Degree Requirements" the same way, see tests/fixtures/courseleaf/). Only
# extend this list against further real examples, not by guessing.
_NON_PROGRAM_SLUGS = {"courses", "degree-requirements", "faculty"}


class CourseLeafAdapter:
    """Adapter for CourseLeaf-hosted catalogs (§9's adapter registry).

    Structural assumptions below are all grounded in real fetched pages,
    not invented — see the fixtures this is tested against and the pilot
    evidence log referenced above.
    """

    name = "courseleaf"

    def detect(self, url: str, html: str) -> bool:
        return any(marker in html for marker in _DETECT_MARKERS)

    def extract_programs(self, url: str, html: str) -> List[RawProgramCandidate]:
        container = self._textcontainer(html)
        if container is None:
            return []
        candidates: List[RawProgramCandidate] = []
        for sitemap in container.find_all("div", class_="sitemap"):
            for link in sitemap.find_all("a", href=True):
                href = link["href"]
                slug = href.rstrip("/").rsplit("/", 1)[-1]
                if slug in _NON_PROGRAM_SLUGS:
                    continue
                name = link.get_text(strip=True)
                if not name:
                    continue
                candidates.append(
                    RawProgramCandidate(
                        name=name,
                        program_url=urljoin(url, href),
                        source_url=url,
                    )
                )
        return candidates

    def extract_degrees(self, url: str, html: str) -> List[RawDegreeCandidate]:
        container = self._textcontainer(html)
        if container is None:
            return []
        # CourseLeaf program pages declare the degree(s) offered as a
        # centered <em> block, one degree per line (<br/>-separated), near
        # the top of #textcontainer — confirmed against
        # catalog.utexas.edu/graduate/areas-of-study/natural-sciences/computer-science/.
        banner = container.find(
            "p", style=lambda value: bool(value) and "text-align:center" in value
        )
        if banner is None:
            return []
        emphasis = banner.find("em")
        if emphasis is None:
            return []
        lines = emphasis.get_text(separator="\n").split("\n")
        return [
            RawDegreeCandidate(raw_degree_name=line.strip(), source_url=url)
            for line in lines
            if line.strip()
        ]

    def extract_requirements(self, url: str, html: str) -> List[RawRequirementCandidate]:
        container = self._textcontainer(html)
        if container is None:
            return []
        candidates: List[RawRequirementCandidate] = []
        for heading in container.find_all("h2"):
            label = heading.get_text(strip=True)
            if not label:
                continue
            text_parts: List[str] = []
            for sibling in heading.find_next_siblings():
                if sibling.name == "h2":
                    break
                text = sibling.get_text(" ", strip=True)
                if text:
                    text_parts.append(text)
            raw_text = "\n".join(text_parts)
            if not raw_text:
                continue
            candidates.append(
                RawRequirementCandidate(section_label=label, raw_text=raw_text, source_url=url)
            )
        return candidates

    @staticmethod
    def _textcontainer(html: str):
        soup = BeautifulSoup(html, "html.parser")
        return soup.find(id="textcontainer")
