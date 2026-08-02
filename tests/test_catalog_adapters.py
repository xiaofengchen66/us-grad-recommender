from __future__ import annotations

from pathlib import Path

import pytest

from us_grad_recommender.catalog_adapters import (
    AdapterRegistry,
    CourseLeafAdapter,
    RawDegreeCandidate,
    RawProgramCandidate,
)

FIXTURES = Path(__file__).parent / "fixtures" / "courseleaf"

LISTING_URL = "https://catalog.utexas.edu/graduate/areas-of-study/natural-sciences/"
PROGRAM_URL = "https://catalog.utexas.edu/graduate/areas-of-study/natural-sciences/computer-science/"
REQUIREMENTS_URL = (
    "https://catalog.utexas.edu/graduate/areas-of-study/natural-sciences/"
    "computer-science/degree-requirements/"
)


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture()
def listing_html() -> bytes:
    return _load("ut_austin_natural_sciences_listing.html")


@pytest.fixture()
def program_html() -> bytes:
    return _load("ut_austin_computer_science_program.html")


@pytest.fixture()
def requirements_html() -> bytes:
    return _load("ut_austin_computer_science_degree_requirements.html")


def test_detect_matches_real_courseleaf_markup(listing_html):
    assert CourseLeafAdapter().detect(LISTING_URL, listing_html) is True


def test_detect_rejects_non_courseleaf_html():
    assert CourseLeafAdapter().detect("https://example.edu/", b"<html></html>") is False


def test_extract_programs_from_real_listing_page(listing_html):
    candidates = CourseLeafAdapter().extract_programs(LISTING_URL, listing_html)

    assert RawProgramCandidate(
        name="Computer Science",
        program_url="https://catalog.utexas.edu/graduate/areas-of-study/natural-sciences/computer-science/",
        source_url=LISTING_URL,
    ) in candidates
    names = {c.name for c in candidates}
    assert "Data Science" in names
    assert "Artificial Intelligence" in names


def test_extract_programs_excludes_non_program_entries(listing_html):
    candidates = CourseLeafAdapter().extract_programs(LISTING_URL, listing_html)
    names = {c.name for c in candidates}
    # The real listing page includes a trailing "Courses" link alongside
    # actual programs — it must not be surfaced as a program candidate.
    assert "Courses" not in names


def test_extract_programs_returns_empty_list_when_no_textcontainer():
    candidates = CourseLeafAdapter().extract_programs(
        "https://example.edu/", b"<html><body></body></html>"
    )
    assert candidates == []


def test_extract_degrees_from_real_program_page(program_html):
    candidates = CourseLeafAdapter().extract_degrees(PROGRAM_URL, program_html)

    assert candidates == [
        RawDegreeCandidate(
            raw_degree_name="Master of Science in Computer Science", source_url=PROGRAM_URL
        ),
        RawDegreeCandidate(raw_degree_name="Doctor of Philosophy", source_url=PROGRAM_URL),
    ]


def test_extract_degrees_tolerates_style_attribute_formatting_variants():
    html = b"""
    <div id="textcontainer" class="page_content">
    <p style="text-align: center;"><em>Master of Arts in Testing</em></p>
    </div>
    """
    candidates = CourseLeafAdapter().extract_degrees("https://example.edu/", html)
    assert candidates == [
        RawDegreeCandidate(raw_degree_name="Master of Arts in Testing", source_url="https://example.edu/")
    ]


def test_extract_requirements_splits_on_headings(requirements_html):
    candidates = CourseLeafAdapter().extract_requirements(REQUIREMENTS_URL, requirements_html)

    labels = [c.section_label for c in candidates]
    assert labels == ["Master of Science", "Doctor of Philosophy"]

    ms = next(c for c in candidates if c.section_label == "Master of Science")
    assert "On-Campus." in ms.raw_text
    assert "Online." in ms.raw_text
    assert ms.source_url == REQUIREMENTS_URL

    phd = next(c for c in candidates if c.section_label == "Doctor of Philosophy")
    assert "grade point average of at least 3.00" in phd.raw_text


def test_extract_requirements_on_program_page_captures_multiple_sections(program_html):
    candidates = CourseLeafAdapter().extract_requirements(PROGRAM_URL, program_html)
    labels = [c.section_label for c in candidates]
    assert labels == ["For More Information", "Admission Requirements"]


def test_extract_requirements_excludes_trailing_sitemap_nav_text(program_html):
    # The real "Admission Requirements" section on this fixture is followed
    # by a <div class="sitemap"> nav link ("Degree Requirements") before
    # the next heading (there isn't one — it's the last section). That nav
    # text must not bleed into raw_text and corrupt the verbatim-source
    # guarantee.
    candidates = CourseLeafAdapter().extract_requirements(PROGRAM_URL, program_html)
    admission = next(c for c in candidates if c.section_label == "Admission Requirements")
    assert admission.raw_text == (
        "Most entering graduate students have degrees in computer science. "
        "Students with degrees in other areas may be considered for admission; "
        "if admitted, they may be required to take undergraduate courses in "
        "computer science, without credit toward a graduate degree, to satisfy "
        "background requirements."
    )
    assert "Degree Requirements" not in admission.raw_text


def test_extract_requirements_drops_content_before_first_heading(requirements_html):
    # ut_austin_computer_science_degree_requirements.html opens with a
    # graduate-handbook disclaimer paragraph before the first <h2> — it has
    # no section_label to attach to, so it's intentionally not surfaced as
    # a RawRequirementCandidate.
    candidates = CourseLeafAdapter().extract_requirements(REQUIREMENTS_URL, requirements_html)
    combined = "\n".join(c.raw_text for c in candidates)
    assert "Graduate handbook information" not in combined


def test_extract_requirements_preserves_table_row_and_cell_boundaries():
    # Synthetic fixture — not from any real institution's page. It exists
    # only to exercise a real CourseLeaf structural pattern (a <table> of
    # course/credit-hour rows between two <h2> headings, the same shape as
    # the real "Graduate Studies Committee" table trimmed out of
    # ut_austin_computer_science_program.html) without asserting anything
    # about an actual school's curriculum.
    html = b"""
    <div id="textcontainer" class="page_content">
    <h2 name="text">Required Courses</h2>
    <table class="cldatatable">
      <tr><th>Code</th><th>Title</th><th>Credit Hours</th></tr>
      <tr><td>CS 601</td><td>Foundations of Testing</td><td>3</td></tr>
      <tr><td>CS 602</td><td>Advanced Fixtures</td><td>3</td></tr>
    </table>
    </div>
    """
    candidates = CourseLeafAdapter().extract_requirements("https://example.edu/", html)
    assert len(candidates) == 1
    assert candidates[0].raw_text == (
        "Code | Title | Credit Hours\nCS 601 | Foundations of Testing | 3\n"
        "CS 602 | Advanced Fixtures | 3"
    )


def test_extract_degrees_returns_empty_list_when_no_textcontainer():
    candidates = CourseLeafAdapter().extract_degrees(
        "https://example.edu/", b"<html><body></body></html>"
    )
    assert candidates == []


def test_extract_degrees_returns_empty_list_when_no_centered_banner():
    html = b'<div id="textcontainer" class="page_content"><p>No banner here.</p></div>'
    assert CourseLeafAdapter().extract_degrees("https://example.edu/", html) == []


def test_extract_degrees_returns_empty_list_when_banner_has_no_em():
    html = (
        b'<div id="textcontainer" class="page_content">'
        b'<p style="text-align:center">No emphasis tag here.</p></div>'
    )
    assert CourseLeafAdapter().extract_degrees("https://example.edu/", html) == []


def test_extract_requirements_returns_empty_list_when_no_textcontainer():
    candidates = CourseLeafAdapter().extract_requirements(
        "https://example.edu/", b"<html><body></body></html>"
    )
    assert candidates == []


def test_adapter_registry_detects_courseleaf_first_match(listing_html):
    registry = AdapterRegistry([CourseLeafAdapter()])
    adapter = registry.detect(LISTING_URL, listing_html)
    assert adapter is not None
    assert adapter.name == "courseleaf"


def test_adapter_registry_returns_none_when_nothing_matches():
    registry = AdapterRegistry([CourseLeafAdapter()])
    assert registry.detect("https://example.edu/", b"<html></html>") is None


class _AlwaysMatchStubAdapter:
    """Minimal stand-in adapter that matches everything — used only to
    prove AdapterRegistry honors list order rather than happening to work
    with a single real adapter.
    """

    name = "always-match-stub"

    def detect(self, url: str, content: bytes) -> bool:
        return True

    def extract_programs(self, url: str, content: bytes):
        return []

    def extract_degrees(self, url: str, content: bytes):
        return []

    def extract_requirements(self, url: str, content: bytes):
        return []


def test_adapter_registry_honors_order_first_match_wins(listing_html):
    registry = AdapterRegistry([CourseLeafAdapter(), _AlwaysMatchStubAdapter()])
    adapter = registry.detect(LISTING_URL, listing_html)
    assert adapter is not None
    assert adapter.name == "courseleaf"

    reordered = AdapterRegistry([_AlwaysMatchStubAdapter(), CourseLeafAdapter()])
    adapter = reordered.detect(LISTING_URL, listing_html)
    assert adapter is not None
    assert adapter.name == "always-match-stub"
