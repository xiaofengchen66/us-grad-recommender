from __future__ import annotations

from pathlib import Path

import pytest

from us_grad_recommender.catalog_adapters import (
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
        RawDegreeCandidate(raw_degree_name="Master of Science", source_url=CATALOG_URL)
    ]


def test_extract_degrees_returns_empty_for_ordinary_prose_page(policy_prose_page):
    assert PdfCatalogAdapter().extract_degrees(CATALOG_URL, policy_prose_page) == []


def test_extract_requirements_splits_real_biology_page_into_sections(biology_page):
    candidates = PdfCatalogAdapter().extract_requirements(CATALOG_URL, biology_page)
    labels = [c.section_label for c in candidates]
    assert labels == [
        "Mission Statement",
        "Admission Requirements",
        "Policy Statement",
        "Degree Requirements",
    ]

    admission = next(c for c in candidates if c.section_label == "Admission Requirements")
    assert "Clear evidence of scholastic competence" in admission.raw_text
    assert admission.source_url == f"{CATALOG_URL}#page=1"

    degree = next(c for c in candidates if c.section_label == "Degree Requirements")
    assert "30/36 semester hour program" in degree.raw_text


def test_extract_requirements_handles_program_description_heading(computer_science_page):
    # The CS page uses "PROGRAM DESCRIPTION" instead of "MISSION
    # STATEMENT" as its opening section — real AAMU pages aren't fully
    # uniform in heading choice, and the extractor must not assume a fixed
    # heading set (mirrors CourseLeafAdapter's split-by-any-<h2> approach).
    candidates = PdfCatalogAdapter().extract_requirements(CATALOG_URL, computer_science_page)
    labels = [c.section_label for c in candidates]
    assert "Program Description" in labels
    assert "Admission Requirements" in labels


def test_extract_requirements_returns_empty_for_ordinary_prose_page(policy_prose_page):
    assert PdfCatalogAdapter().extract_requirements(CATALOG_URL, policy_prose_page) == []


def test_extract_requirements_returns_empty_for_blank_pdf(blank_pdf):
    assert PdfCatalogAdapter().extract_requirements(CATALOG_URL, blank_pdf) == []
