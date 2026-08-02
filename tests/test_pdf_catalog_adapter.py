from __future__ import annotations

from pathlib import Path

import pytest
from pypdf._page import PageObject

from us_grad_recommender.catalog_adapters import (
    AdapterRegistry,
    CourseLeafAdapter,
    PdfCatalogAdapter,
    RawDegreeCandidate,
    RawProgramCandidate,
)

FIXTURES = Path(__file__).parent / "fixtures" / "pdf"

# Real URL of the source document these fixture pages were extracted from —
# aamu.edu/academics/catalogs/graduate-catalog.html, confirmed PDF-only
# (no browsable HTML catalog) during Phase 2.2B pilot scoping.
CATALOG_URL = (
    "https://www.aamu.edu/academics/catalogs/_documents/graduate-catalogs/"
    "graduate-catalog-2026-2027.pdf"
)


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture()
def biology_page() -> bytes:
    # Single real page (page 41 of the 209-page catalog) extracted
    # unmodified via pypdf — not retyped or paraphrased.
    return _load("aamu_biology_program.pdf")


@pytest.fixture()
def computer_science_page() -> bytes:
    return _load("aamu_computer_science_program.pdf")


@pytest.fixture()
def policy_prose_page() -> bytes:
    # Page 31 of the real catalog: ordinary academic-policy prose, no
    # program/degree declaration. Exists specifically to guard against a
    # real false positive this adapter's design hit during development —
    # a laxer "starts with Master of" regex matched the mid-sentence line
    # "Master of Science degrees, 18 credit hours of the total 30 consist".
    return _load("aamu_policy_prose_page.pdf")


@pytest.fixture()
def encrypted_biology_page() -> bytes:
    # Same real page as biology_page, re-saved with empty-user-password
    # encryption — mirrors how AAMU's actual live PDF is protected.
    return _load("aamu_biology_program_encrypted.pdf")


@pytest.fixture()
def two_program_pages() -> bytes:
    # Real 2-page PDF: Biology (page 41) followed by Computer Science
    # (page 50) of the actual 209-page catalog, concatenated. Exists to
    # prove page-level provenance and list-position pairing actually work
    # across multiple pages in one document — single-page fixtures can't
    # catch a bug like "extract_degrees() forgot the #page= anchor" (found
    # in review) since page_index is always 0 there.
    return _load("aamu_two_program_pages.pdf")


@pytest.fixture()
def wrong_password_biology_page() -> bytes:
    # Same real page again, but encrypted with a real, non-empty password
    # this adapter's decrypt("") attempt cannot satisfy — a plausible
    # real-world case for a second institution's PDF (this module's own
    # top comment says extract_*() heuristics are AAMU-specific and
    # unverified beyond it). Regression fixture for the found-in-review
    # bug where an unchecked decrypt() result let a still-encrypted
    # reader through to extract_text(), which raises
    # FileNotDecryptedError instead of failing gracefully.
    return _load("aamu_biology_program_wrong_password.pdf")


@pytest.fixture()
def blank_pdf() -> bytes:
    # Synthetic — a genuinely blank PDF page, not from any institution.
    # Exists only to exercise the no-usable-text-layer path (§14
    # decision 4's scanned-image case).
    return _load("synthetic_blank_no_text_layer.pdf")


def test_detect_matches_pdf_magic_bytes(biology_page):
    assert PdfCatalogAdapter().detect(CATALOG_URL, biology_page) is True


def test_detect_rejects_non_pdf_content():
    assert PdfCatalogAdapter().detect(CATALOG_URL, b"<html></html>") is False


def test_has_usable_text_layer_true_for_real_pdf(biology_page):
    assert PdfCatalogAdapter().has_usable_text_layer(biology_page) is True


def test_has_usable_text_layer_false_for_blank_pdf(blank_pdf):
    assert PdfCatalogAdapter().has_usable_text_layer(blank_pdf) is False


def test_extract_programs_from_real_biology_page(biology_page):
    candidates = PdfCatalogAdapter().extract_programs(CATALOG_URL, biology_page)
    assert candidates == [
        RawProgramCandidate(
            name="Biology",
            program_url=f"{CATALOG_URL}#page=1",
            source_url=CATALOG_URL,
        )
    ]


def test_extract_programs_from_real_computer_science_page(computer_science_page):
    candidates = PdfCatalogAdapter().extract_programs(CATALOG_URL, computer_science_page)
    assert candidates == [
        RawProgramCandidate(
            name="Computer Science",
            program_url=f"{CATALOG_URL}#page=1",
            source_url=CATALOG_URL,
        )
    ]


def test_extract_programs_returns_empty_for_ordinary_prose_page(policy_prose_page):
    # Regression test for the real false positive found during
    # development: this page contains "Master of Science degrees, 18
    # credit hours..." mid-sentence, which must NOT be mistaken for a
    # program's degree-declaration line.
    assert PdfCatalogAdapter().extract_programs(CATALOG_URL, policy_prose_page) == []


def test_extract_programs_works_on_encrypted_pdf(encrypted_biology_page):
    candidates = PdfCatalogAdapter().extract_programs(CATALOG_URL, encrypted_biology_page)
    assert candidates == [
        RawProgramCandidate(
            name="Biology",
            program_url=f"{CATALOG_URL}#page=1",
            source_url=CATALOG_URL,
        )
    ]


def test_extract_programs_returns_empty_for_wrong_password_pdf(wrong_password_biology_page):
    # Must fail gracefully (empty list), not raise FileNotDecryptedError.
    assert PdfCatalogAdapter().extract_programs(CATALOG_URL, wrong_password_biology_page) == []


def test_extract_degrees_returns_empty_for_wrong_password_pdf(wrong_password_biology_page):
    assert PdfCatalogAdapter().extract_degrees(CATALOG_URL, wrong_password_biology_page) == []


def test_extract_requirements_returns_empty_for_wrong_password_pdf(wrong_password_biology_page):
    assert (
        PdfCatalogAdapter().extract_requirements(CATALOG_URL, wrong_password_biology_page) == []
    )


def test_has_usable_text_layer_false_for_wrong_password_pdf(wrong_password_biology_page):
    assert PdfCatalogAdapter().has_usable_text_layer(wrong_password_biology_page) is False


def test_extract_programs_returns_empty_for_non_pdf_bytes():
    assert PdfCatalogAdapter().extract_programs(CATALOG_URL, b"not a pdf") == []


def test_extract_degrees_from_real_biology_page(biology_page):
    candidates = PdfCatalogAdapter().extract_degrees(CATALOG_URL, biology_page)
    assert candidates == [
        RawDegreeCandidate(
            raw_degree_name="Master of Science", source_url=f"{CATALOG_URL}#page=1"
        )
    ]


def test_extract_degrees_returns_empty_for_ordinary_prose_page(policy_prose_page):
    assert PdfCatalogAdapter().extract_degrees(CATALOG_URL, policy_prose_page) == []


def test_extract_requirements_splits_real_biology_page_into_sections(biology_page):
    candidates = PdfCatalogAdapter().extract_requirements(CATALOG_URL, biology_page)
    labels = [c.section_label for c in candidates]
    # section_label preserves the real PDF's authored all-caps case rather
    # than title-casing it — case is presentation, not something this
    # adapter should be interpreting (see extract_requirements()'s
    # docstring).
    assert labels == [
        "MISSION STATEMENT",
        "ADMISSION REQUIREMENTS",
        "POLICY STATEMENT",
        "DEGREE REQUIREMENTS",
    ]

    admission = next(c for c in candidates if c.section_label == "ADMISSION REQUIREMENTS")
    assert "Clear evidence of scholastic competence" in admission.raw_text
    assert admission.source_url == f"{CATALOG_URL}#page=1"

    degree = next(c for c in candidates if c.section_label == "DEGREE REQUIREMENTS")
    assert "30/36 semester hour program" in degree.raw_text


def test_extract_requirements_handles_program_description_heading(computer_science_page):
    # The CS page uses "PROGRAM DESCRIPTION" instead of "MISSION
    # STATEMENT" as its opening section — real AAMU pages aren't fully
    # uniform in heading choice, and the extractor must not assume a fixed
    # heading set (mirrors CourseLeafAdapter's split-by-any-<h2> approach).
    candidates = PdfCatalogAdapter().extract_requirements(CATALOG_URL, computer_science_page)
    labels = [c.section_label for c in candidates]
    assert "PROGRAM DESCRIPTION" in labels
    assert "ADMISSION REQUIREMENTS" in labels


def test_extract_requirements_returns_empty_for_ordinary_prose_page(policy_prose_page):
    assert PdfCatalogAdapter().extract_requirements(CATALOG_URL, policy_prose_page) == []


def test_extract_requirements_returns_empty_for_blank_pdf(blank_pdf):
    assert PdfCatalogAdapter().extract_requirements(CATALOG_URL, blank_pdf) == []


def test_extract_programs_and_degrees_carry_correct_page_anchor_across_pages(two_program_pages):
    # Regression test for the found-in-review bug where extract_degrees()
    # had no page anchor at all — real proof, not just single-page-fixture
    # proof, since page_index differs per page here.
    adapter = PdfCatalogAdapter()
    programs = adapter.extract_programs(CATALOG_URL, two_program_pages)
    degrees = adapter.extract_degrees(CATALOG_URL, two_program_pages)

    assert [p.name for p in programs] == ["Biology", "Computer Science"]
    assert [p.program_url for p in programs] == [
        f"{CATALOG_URL}#page=1",
        f"{CATALOG_URL}#page=2",
    ]
    assert [d.raw_degree_name for d in degrees] == ["Master of Science", "Master of Science"]
    assert [d.source_url for d in degrees] == [
        f"{CATALOG_URL}#page=1",
        f"{CATALOG_URL}#page=2",
    ]


def test_find_programs_and_degrees_returns_every_match_on_a_page():
    # Synthetic — not from any real institution's page. No page in the
    # real 209-page AAMU catalog currently has more than one degree
    # declaration, but nothing about the real pattern this is grounded in
    # guarantees that (a department can offer both an MS and a PhD), and
    # silently keeping only the first match would be a real, undetected
    # data-loss bug once such a page is encountered.
    numbered_lines = [
        (98, "DEPT OF EXAMPLE, AAMU Graduate Catalog, 2026-2027 ~ 99 ~"),
        (98, "Example Studies"),
        (98, "Master of Arts"),
        (98, "Dr. Example, Program Coordinator"),
        (98, "Example Studies"),
        (98, "Doctor of Philosophy"),
        (98, "Dr. Example, Program Coordinator"),
    ]
    found = PdfCatalogAdapter._find_programs_and_degrees(numbered_lines)
    assert found == [
        (98, "Example Studies", "Master of Arts"),
        (98, "Example Studies", "Doctor of Philosophy"),
    ]


def test_find_programs_and_degrees_matches_across_a_page_boundary():
    # Synthetic — exercises the real gap found in review: a program's
    # name/degree pair split by a page break (name on the last line of
    # one page, degree as the first line of the next) must still match.
    # Not observed in the real AAMU document (verified directly: zero
    # such splits across all 209 pages), but nothing about a PDF's layout
    # guarantees it can't happen, e.g. in a different institution's PDF.
    numbered_lines = [
        (5, "Example Studies"),
        (6, "Master of Arts"),
    ]
    found = PdfCatalogAdapter._find_programs_and_degrees(numbered_lines)
    assert found == [(6, "Example Studies", "Master of Arts")]


def test_extraction_survives_a_page_that_fails_to_extract_text(biology_page, monkeypatch):
    # pypdf is documented to occasionally raise on a malformed content
    # stream or unusual embedded font on a single page. Simulated via
    # monkeypatch rather than a hand-corrupted PDF fixture, since reliably
    # constructing bytes that pass PdfReader() construction but fail only
    # on extract_text() isn't something to fabricate a claim about being
    # "real" — this tests the defensive code path directly.
    def _raise(self, *args, **kwargs):
        raise RuntimeError("simulated malformed content stream")

    monkeypatch.setattr(PageObject, "extract_text", _raise)

    adapter = PdfCatalogAdapter()
    assert adapter.extract_programs(CATALOG_URL, biology_page) == []
    assert adapter.extract_degrees(CATALOG_URL, biology_page) == []
    assert adapter.extract_requirements(CATALOG_URL, biology_page) == []
    assert adapter.has_usable_text_layer(biology_page) is False


def test_pdf_adapter_through_registry_matches_pdf_not_html(biology_page):
    registry = AdapterRegistry([CourseLeafAdapter(), PdfCatalogAdapter()])
    adapter = registry.detect(CATALOG_URL, biology_page)
    assert adapter is not None
    assert adapter.name == "pdf"

    html_adapter = registry.detect(
        "https://catalog.utexas.edu/", b'<html><script src="/js/courseleaf.js"></script></html>'
    )
    assert html_adapter is not None
    assert html_adapter.name == "courseleaf"
