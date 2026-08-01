from __future__ import annotations

from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from us_grad_recommender.catalog_adapters.base import (
    RawDegreeCandidate,
    RawProgramCandidate,
    RawRequirementCandidate,
)

# Confirmed against real UT Austin catalog pages fetched directly during
# Phase 2.2B pilot scoping (see tests/fixtures/courseleaf/ and this PR's
# description for the underlying evidence — not carried by citation to a
# sibling PR/doc that may not exist in this tree): every self-hosted
# CourseLeaf catalog (catalog.<school>.edu) references these two vendor
# assets.
_DETECT_MARKERS = ("courseleaf.css", "courseleaf.js")

# Non-program entries observed in real CourseLeaf "sitemap" listing pages
# (catalog.utexas.edu/graduate/areas-of-study/natural-sciences/ lists
# "Courses" alongside real programs; a program's own page links back to
# "Degree Requirements" the same way, see tests/fixtures/courseleaf/). Only
# extend this list against further real examples, not by guessing — do not
# add slugs (e.g. "faculty") without a fixture that actually exercises them.
_NON_PROGRAM_SLUGS = {"courses", "degree-requirements"}


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
                href = str(link["href"])
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
            "p",
            style=lambda value: bool(value) and "text-align:center" in value.replace(" ", ""),
        )
        if banner is None:
            return []
        emphasis = banner.find("em")
        if not isinstance(emphasis, Tag):
            return []
        lines = emphasis.get_text(separator="\n").split("\n")
        return [
            RawDegreeCandidate(raw_degree_name=line.strip(), source_url=url)
            for line in lines
            if line.strip()
        ]

    def extract_requirements(self, url: str, html: str) -> List[RawRequirementCandidate]:
        # Content in #textcontainer before the first <h2> (e.g. a graduate-
        # handbook disclaimer paragraph — see
        # ut_austin_computer_science_degree_requirements.html) is
        # intentionally dropped: a RawRequirementCandidate must carry a
        # section_label, and that intro text isn't tied to any heading.
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
                # A trailing "sitemap" div (a nav list of child-page links,
                # e.g. "Degree Requirements" on the program page fixture)
                # is boilerplate navigation, not requirement prose — same
                # exclusion extract_programs() applies. Without this, its
                # link text bleeds into raw_text and breaks the
                # verbatim-raw-text guarantee §0/§4 depend on.
                if isinstance(sibling, Tag) and "sitemap" in (sibling.get("class") or []):
                    continue
                if isinstance(sibling, Tag) and sibling.name == "table":
                    # CourseLeaf degree-requirement pages commonly present
                    # course-list requirements as a <table> between two
                    # <h2> headings. Flattening it with a single
                    # get_text(" ") run would merge row/column boundaries
                    # into one undifferentiated string, destroying the
                    # "raw text preserved in full" guarantee (§0/§4) —
                    # not because characters go missing, but because which
                    # cell/row they belonged to becomes unrecoverable.
                    # raw_text is still a plain string (the schema column
                    # is Text, not JSONB), so structure is kept via plain
                    # delimiters: " | " between cells, newline between rows.
                    text = self._table_to_text(sibling)
                else:
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
    def _textcontainer(html: str) -> Optional[Tag]:
        soup = BeautifulSoup(html, "html.parser")
        result = soup.find(id="textcontainer")
        return result if isinstance(result, Tag) else None

    @staticmethod
    def _table_to_text(table: Tag) -> str:
        rows = []
        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append(" | ".join(cells))
        return "\n".join(rows)
