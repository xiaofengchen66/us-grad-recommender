from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from us_grad_recommender.models.university import AliasType, CoverageTier, Sector


class AliasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alias: str
    alias_type: AliasType
    source: str


class UniversitySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unitid: int
    canonical_name: str
    city: Optional[str]
    state: Optional[str]
    sector: Sector
    masters_granting: bool
    coverage_tier: CoverageTier


class UniversityDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unitid: int
    canonical_name: str
    website: Optional[str]
    city: Optional[str]
    state: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    sector: Sector
    highest_degree_level: Optional[int]
    highest_degree_label: Optional[str]
    carnegie_classification: Optional[int]
    carnegie_classification_label: Optional[str]
    campus_setting: Optional[int]
    campus_setting_label: Optional[str]
    masters_granting: bool
    masters_granting_basis: Optional[str]
    degree_granting: Optional[bool]
    active: bool
    total_enrollment: Optional[int]
    graduate_enrollment: Optional[int]
    international_graduate_enrollment: Optional[int]
    enrollment_year: Optional[int]
    coverage_tier: CoverageTier
    ipeds_year: int
    source_dataset: str
    last_verified_at: date
    updated_at: datetime
    aliases: List[AliasOut]


class UniversityListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    results: List[UniversitySummary]
