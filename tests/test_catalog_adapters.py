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


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture()
def listing_html() -> str:
    return _load("ut_austin_natural_sciences_listing.html")


@pytest.fixture()
def program_html() -> str:
    return _load("ut_austin_computer_science_program.html")


@pytest.fixture()
def requirements_html() -> str:
    return _load("ut_austin_computer_science_degree_requirements.html")


def test_detect_matches_real_courseleaf_markup(listing_html):
    assert CourseLeafAdapter().detect(LISTING_URL, listing_html) is True


def test_detect_rejects_non_courseleaf_html():
    assert CourseLeafAdapter().detect("https://example.edu/", "<html></html>") is False


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
        "https://example.edu/", "<html><body></body></html>"
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


def test_adapter_registry_detects_courseleaf_first_match(listing_html):
    registry = AdapterRegistry([CourseLeafAdapter()])
    adapter = registry.detect(LISTING_URL, listing_html)
    assert adapter is not None
    assert adapter.name == "courseleaf"


def test_adapter_registry_returns_none_when_nothing_matches():
    registry = AdapterRegistry([CourseLeafAdapter()])
    assert registry.detect("https://example.edu/", "<html></html>") is None
