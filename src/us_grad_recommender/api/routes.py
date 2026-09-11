from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from us_grad_recommender.api.deps import get_db
from us_grad_recommender.api.schemas import (
    MapFeature,
    MapFeatureCollection,
    MapFeatureGeometry,
    MapFeatureProperties,
    RecommendationProfileIn,
    RecommendationResponse,
    ScoredInstitutionOut,
    UniversityDetail,
    UniversityListResponse,
    UniversitySummary,
)
from us_grad_recommender.models.university import Sector, University, UniversityAlias
from us_grad_recommender.recommendation import (
    RecommendationProfile,
    normalize_carnegie_classification,
    recommend,
)

router = APIRouter(prefix="/universities", tags=["universities"])
recommendations_router = APIRouter(tags=["recommendations"])

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def _apply_filters(
    stmt,
    q: Optional[str],
    state: Optional[str],
    sector: Optional[Sector],
    masters_granting: Optional[bool],
):
    if q:
        pattern = f"%{q}%"
        alias_match = (
            select(UniversityAlias.unitid)
            .where(UniversityAlias.unitid == University.unitid)
            .where(UniversityAlias.alias.ilike(pattern))
            .exists()
        )
        stmt = stmt.where(University.canonical_name.ilike(pattern) | alias_match)
    if state:
        stmt = stmt.where(University.state == state.upper())
    if sector:
        stmt = stmt.where(University.sector == sector)
    if masters_granting is not None:
        stmt = stmt.where(University.masters_granting == masters_granting)
    return stmt


@router.get("", response_model=UniversityListResponse)
def search_universities(
    q: Optional[str] = Query(None, description="Case-insensitive match against name or alias"),
    state: Optional[str] = Query(None, min_length=2, max_length=2),
    sector: Optional[Sector] = Query(None),
    masters_granting: Optional[bool] = Query(None),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> UniversityListResponse:
    base_stmt = _apply_filters(select(University), q, state, sector, masters_granting)

    count_stmt = _apply_filters(
        select(func.count()).select_from(University), q, state, sector, masters_granting
    )
    total = db.execute(count_stmt).scalar_one()

    rows = (
        db.execute(base_stmt.order_by(University.canonical_name).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    results = [UniversitySummary.model_validate(row) for row in rows]

    return UniversityListResponse(total=total, limit=limit, offset=offset, results=results)


@router.get("/map", response_model=MapFeatureCollection)
def get_universities_map(db: Session = Depends(get_db)) -> MapFeatureCollection:
    """Bulk GeoJSON feed for the map's baseline layer (docs/MAP_RECOMMENDER_DESIGN.md
    §6.3) — deliberately lighter than UniversitySummary/UniversityDetail,
    and returns every active institution, not a paginated slice: the map
    needs the whole baseline universe up front (§0/decision 5), not a
    page at a time.

    Registered before /{unitid} — an int path param wouldn't match "map"
    anyway, but the ordering keeps that obvious rather than relying on it.
    """
    rows = db.execute(
        select(University).where(
            University.active.is_(True),
            University.latitude.is_not(None),
            University.longitude.is_not(None),
        )
    ).scalars().all()
    features = []
    for row in rows:
        # The WHERE clause above already excludes null coordinates; a
        # runtime check (not `assert`, which is stripped under `python
        # -O`) makes that guarantee robust in a production request path,
        # not just visible to mypy.
        if row.latitude is None or row.longitude is None:
            raise RuntimeError(
                f"University {row.unitid} matched the non-null coordinate filter "
                "but has a null latitude/longitude — this should be unreachable."
            )
        features.append(
            MapFeature(
                geometry=MapFeatureGeometry(coordinates=(row.longitude, row.latitude)),
                properties=MapFeatureProperties(
                    unitid=row.unitid,
                    canonical_name=row.canonical_name,
                    city=row.city,
                    state=row.state,
                    sector=row.sector,
                    carnegie_classification=normalize_carnegie_classification(
                        row.carnegie_classification
                    ),
                ),
            )
        )
    return MapFeatureCollection(features=features)


@router.get("/{unitid}", response_model=UniversityDetail)
def get_university(unitid: int, db: Session = Depends(get_db)) -> University:
    university = db.get(University, unitid)
    if university is None:
        raise HTTPException(status_code=404, detail=f"No university with UNITID {unitid}")
    return university


@recommendations_router.post("/recommendations", response_model=RecommendationResponse)
def post_recommendations(
    profile_in: RecommendationProfileIn, db: Session = Depends(get_db)
) -> RecommendationResponse:
    """Deterministic v1 scoring (docs/MAP_RECOMMENDER_DESIGN.md §5) — read-only,
    stateless, no persisted recommendation log. See recommendation.py's
    module docstring for the rules this must never violate (match_score is
    never an admission probability; missing optional preferences are
    excluded from scoring, not zeroed; program existence is tracked
    separately from how well it scores)."""
    profile = RecommendationProfile(
        degree_level=profile_in.degree_level,
        program_category=profile_in.program_category,
        program_name=profile_in.program_name,
        gpa=profile_in.gpa,
        gpa_scale=profile_in.gpa_scale,
        priority=profile_in.priority,
        budget_max_usd=profile_in.budget_max_usd,
        preferred_states=(
            tuple(profile_in.preferred_states) if profile_in.preferred_states else None
        ),
    )
    results = recommend(db, profile)
    return RecommendationResponse(
        results=[ScoredInstitutionOut.model_validate(r) for r in results]
    )
