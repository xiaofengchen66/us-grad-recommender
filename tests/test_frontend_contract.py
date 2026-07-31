"""Contract test between the backend API shapes and the hand-maintained
TypeScript mirror in web/src/lib/api.ts.

There is no OpenAPI codegen step (see the header comment in api.ts) — the
frontend types are kept in sync by hand, which is exactly the kind of
thing that silently drifts (see PR #6's Sector.UNKNOWN omission, caught
only by manual review). These tests parse api.ts with a small
regex-based extractor tailored to its own hand-written formatting — not a
real TypeScript parser. If a legitimate reformatting of api.ts breaks
these, either restore the original formatting or extend the extractor;
don't weaken the assertions.
"""

from __future__ import annotations

import re
from pathlib import Path

from us_grad_recommender.api.schemas import (
    AliasOut,
    UniversityDetail,
    UniversityListResponse,
    UniversitySummary,
)
from us_grad_recommender.models.university import AliasType, CoverageTier, Sector

API_TS_PATH = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "api.ts"


def _read_api_ts() -> str:
    return API_TS_PATH.read_text()


def _ts_interface_fields(source: str, interface_name: str) -> set[str]:
    match = re.search(rf"export interface {interface_name} \{{(.*?)\n\}}", source, re.S)
    assert match, f"could not find `export interface {interface_name}` in api.ts"
    fields: set[str] = set()
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        field_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\??:", line)
        if field_match:
            fields.add(field_match.group(1))
    return fields


def _ts_union_members(source: str, type_name: str) -> set[str]:
    match = re.search(rf'export type {type_name} =\s*((?:\s*\|\s*"[^"]+")+)', source)
    assert match, f"could not find `export type {type_name}` union in api.ts"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def test_sector_enum_matches_frontend():
    backend = {member.value for member in Sector}
    frontend = _ts_union_members(_read_api_ts(), "Sector")
    assert backend == frontend


def test_coverage_tier_enum_matches_frontend():
    backend = {member.value for member in CoverageTier}
    frontend = _ts_union_members(_read_api_ts(), "CoverageTier")
    assert backend == frontend


def test_alias_type_enum_matches_frontend():
    backend = {member.value for member in AliasType}
    frontend = _ts_union_members(_read_api_ts(), "AliasType")
    assert backend == frontend


def test_university_summary_fields_match_frontend():
    backend = set(UniversitySummary.model_fields.keys())
    frontend = _ts_interface_fields(_read_api_ts(), "UniversitySummary")
    assert backend == frontend


def test_university_detail_fields_match_frontend():
    backend = set(UniversityDetail.model_fields.keys())
    frontend = _ts_interface_fields(_read_api_ts(), "UniversityDetail")
    assert backend == frontend


def test_university_list_response_fields_match_frontend():
    backend = set(UniversityListResponse.model_fields.keys())
    frontend = _ts_interface_fields(_read_api_ts(), "UniversityListResponse")
    assert backend == frontend


def test_alias_out_fields_match_frontend_university_alias():
    # Named AliasOut in Python, UniversityAlias in TypeScript — deliberately
    # different names (see api.ts), so this pairing is asserted explicitly
    # rather than by matching identical names.
    backend = set(AliasOut.model_fields.keys())
    frontend = _ts_interface_fields(_read_api_ts(), "UniversityAlias")
    assert backend == frontend
