from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from us_grad_recommender.models.catalog import DegreeLevel
from us_grad_recommender.models.university import AliasType, CoverageTier, Sector
from us_grad_recommender.recommendation import (
    DataConfidence,
    GradingScale,
    PriorityPreset,
    ProgramAvailability,
    ProgramCategory,
    RecommendationCategory,
    expected_degree_level,
)


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


# --- Map (Phase 3.0, docs/MAP_RECOMMENDER_DESIGN.md §6.3) ---------------


class MapFeatureGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    # GeoJSON coordinate order is [longitude, latitude] — the opposite of
    # the common "lat, lon" convention. Getting this backwards is a real,
    # easy-to-make bug (MapLibre/GeoJSON consumers all expect this order).
    coordinates: Tuple[float, float]


class MapFeatureProperties(BaseModel):
    unitid: int
    canonical_name: str
    city: Optional[str]
    state: Optional[str]
    sector: Sector
    carnegie_classification: Optional[int]


class MapFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: MapFeatureGeometry
    properties: MapFeatureProperties


class MapFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[MapFeature]


# --- Recommendations (Phase 3.0, docs/MAP_RECOMMENDER_DESIGN.md §5) -----


class RecommendationProfileIn(BaseModel):
    """v1 scoring inputs only — see recommendation.RecommendationProfile's
    docstring for why test scores/school-type preference aren't accepted
    here yet (not wired into scoring, so not collected-and-ignored)."""

    degree_level: DegreeLevel
    program_category: ProgramCategory
    program_name: str = Field(min_length=1, max_length=255)
    gpa: float = Field(ge=0, le=110, description="Raw GPA on gpa_scale's scale, not normalized")
    gpa_scale: GradingScale = Field(
        description=(
            "Required alongside gpa (FULL_HANDOFF.md §9) — only SCALE_4_0 is "
            "compared against program GPA requirements today; any other scale "
            "falls back to a neutral, unscored academic_fit rather than an "
            "invented cross-scale conversion (§0/§23)."
        )
    )
    priority: PriorityPreset = PriorityPreset.BALANCED
    budget_max_usd: Optional[float] = Field(default=None, ge=0)
    preferred_states: Optional[List[str]] = Field(
        default=None,
        min_length=1,
        description=(
            "Hard filter, not a soft preference — set means the shortlist is "
            "restricted to these states only; unset means nationwide."
        ),
    )

    @model_validator(mode="after")
    def _check_degree_level_matches_category(self) -> RecommendationProfileIn:
        implied = expected_degree_level(self.program_category)
        if implied is not None and implied != self.degree_level:
            raise ValueError(
                f"program_category={self.program_category.value!r} implies "
                f"degree_level={implied.value!r}, got {self.degree_level.value!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_gpa_plausible_for_scale(self) -> RecommendationProfileIn:
        # Real bug this guards against: {"gpa": 95, "gpa_scale": "scale_4_0"}
        # would previously pass validation and reach _score_academic_fit
        # (which only checks gpa_scale, not gpa's actual magnitude),
        # reproducing the same "near-perfect academic_fit" failure mode the
        # BLOCKING gpa_scale fix was written to close in the first place.
        # 4.3 covers the (uncommon but real) A+ = 4.3 scale.
        if self.gpa_scale == GradingScale.SCALE_4_0 and self.gpa > 4.3:
            raise ValueError(
                f"gpa={self.gpa!r} is not plausible for gpa_scale='scale_4_0' "
                "(expected roughly 0-4.3); if this GPA is on a different "
                "scale (e.g. a 100-point system), set gpa_scale='other'"
            )
        return self


class ScoredInstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unitid: int
    program_id: Optional[int]
    rank: int = Field(ge=1, le=20)
    match_score: int = Field(
        ge=0, le=100, description="Match/relevance score. Never an admission probability."
    )
    data_confidence: DataConfidence
    category: RecommendationCategory
    is_primary_shortlist: bool = Field(
        description="True for rank 1-15 (default shortlist); false for rank 16-20 (alternatives)."
    )
    program_availability: ProgramAvailability
    component_scores: Dict[str, Optional[float]]
    positive_reasons: List[str]
    warnings: List[str]
    unknown_facts: List[str]


class RecommendationResponse(BaseModel):
    results: List[ScoredInstitutionOut]
