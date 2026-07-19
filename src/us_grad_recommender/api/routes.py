from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from us_grad_recommender.api.deps import get_db
from us_grad_recommender.api.schemas import (
    UniversityDetail,
    UniversityListResponse,
    UniversitySummary,
)
from us_grad_recommender.models.university import Sector, University, UniversityAlias

router = APIRouter(prefix="/universities", tags=["universities"])

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


@router.get("/{unitid}", response_model=UniversityDetail)
def get_university(unitid: int, db: Session = Depends(get_db)) -> University:
    university = db.get(University, unitid)
    if university is None:
        raise HTTPException(status_code=404, detail=f"No university with UNITID {unitid}")
    return university
