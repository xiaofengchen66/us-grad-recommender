from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from us_grad_recommender.models.university import CoverageTier, Sector, University, UniversityAlias


def make_university(**overrides) -> University:
    defaults = dict(
        unitid=999999,
        canonical_name="Test University",
        sector=Sector.PUBLIC,
        masters_granting=True,
        active=True,
        coverage_tier=CoverageTier.INDEXED,
        ipeds_year=2023,
        source_dataset="IPEDS HD2023",
        last_verified_at=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return University(**defaults)


def test_university_round_trip(db_session):
    db_session.add(make_university())
    db_session.commit()

    fetched = db_session.get(University, 999999)
    assert fetched is not None
    assert fetched.canonical_name == "Test University"
    assert fetched.sector == Sector.PUBLIC
    assert fetched.coverage_tier == CoverageTier.INDEXED


def test_alias_cascade_delete(db_session):
    university = make_university()
    university.aliases.append(
        UniversityAlias(alias="Test U", alias_type="ipeds_alias", source="IPEDS HD2023")
    )
    db_session.add(university)
    db_session.commit()

    assert db_session.query(UniversityAlias).count() == 1

    db_session.delete(university)
    db_session.commit()

    assert db_session.query(UniversityAlias).count() == 0


def test_alias_unique_per_university(db_session):
    university = make_university()
    db_session.add(university)
    db_session.flush()

    alias_kwargs = dict(unitid=999999, alias="Dup", alias_type="ipeds_alias", source="x")
    db_session.add(UniversityAlias(**alias_kwargs))
    db_session.flush()
    db_session.add(UniversityAlias(**alias_kwargs))

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
