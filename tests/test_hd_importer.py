from __future__ import annotations

from datetime import date

from us_grad_recommender.importers.ipeds.hd_importer import (
    ParsedInstitution,
    RowIssue,
    compute_masters_granting,
    import_hd_file,
    parse_hd_row,
)
from us_grad_recommender.models.university import Sector, University, UniversityAlias

MASTERS_ROW = {
    "UNITID": "100654",
    "INSTNM": "Alabama A & M University",
    "IALIAS": "AAMU",
    "WEBADDR": "www.aamu.edu/",
    "CITY": "Normal",
    "STABBR": "AL",
    "LATITUDE": "34.783368",
    "LONGITUD": "-86.568502",
    "CONTROL": "1",
    "HLOFFER": "9",
    "GROFFER": "1",
    "DEGGRANT": "1",
    "CYACTIVE": "1",
}

BACHELORS_ONLY_ROW = {
    **MASTERS_ROW,
    "UNITID": "100001",
    "INSTNM": "Bachelor's Only College",
    "IALIAS": "",
    "HLOFFER": "5",  # Bachelor's degree, not master's-granting
}


def row(**overrides) -> dict:
    base = dict(MASTERS_ROW)
    base.update(overrides)
    return base


# --- pure parsing -----------------------------------------------------------


def test_compute_masters_granting_true_when_all_conditions_met():
    assert compute_masters_granting(cyactive=1, deggrant=1, groffer=1, hloffer=7) is True
    assert compute_masters_granting(cyactive=1, deggrant=1, groffer=1, hloffer=9) is True


def test_compute_masters_granting_false_if_highest_offering_below_masters():
    assert compute_masters_granting(cyactive=1, deggrant=1, groffer=1, hloffer=5) is False


def test_compute_masters_granting_false_if_inactive():
    assert compute_masters_granting(cyactive=3, deggrant=1, groffer=1, hloffer=9) is False


def test_compute_masters_granting_false_if_no_graduate_offering():
    assert compute_masters_granting(cyactive=1, deggrant=1, groffer=2, hloffer=9) is False


def test_parse_hd_row_valid_masters_institution():
    parsed = parse_hd_row(MASTERS_ROW)
    assert isinstance(parsed, ParsedInstitution)
    assert parsed.unitid == 100654
    assert parsed.canonical_name == "Alabama A & M University"
    assert parsed.sector == Sector.PUBLIC
    assert parsed.masters_granting is True
    assert parsed.highest_degree_label == "Doctor's degree"
    assert parsed.aliases == ["AAMU"]


def test_parse_hd_row_missing_unitid_is_reported_not_guessed():
    result = parse_hd_row(row(UNITID=""))
    assert isinstance(result, RowIssue)
    assert "UNITID" in result.reason


def test_parse_hd_row_missing_name_is_reported_not_guessed():
    result = parse_hd_row(row(INSTNM=""))
    assert isinstance(result, RowIssue)
    assert "INSTNM" in result.reason


def test_parse_hd_row_splits_multi_value_ialias_on_double_space():
    parsed = parse_hd_row(row(IALIAS="UAH  University of Alabama Huntsville"))
    assert parsed.aliases == ["UAH", "University of Alabama Huntsville"]


def test_parse_hd_row_does_not_split_single_space_names():
    parsed = parse_hd_row(row(IALIAS="University of Alabama Huntsville"))
    assert parsed.aliases == ["University of Alabama Huntsville"]


def test_parse_hd_row_no_alias_when_ialias_blank():
    parsed = parse_hd_row(row(IALIAS=""))
    assert parsed.aliases == []


# --- import_hd_file (integration against Postgres) --------------------------


def test_import_creates_masters_granting_institution(db_session):
    summary = import_hd_file(db_session, [MASTERS_ROW], ipeds_year=2023, run_date=date(2026, 1, 1))
    db_session.commit()

    assert summary.universities_upserted == 1
    university = db_session.get(University, 100654)
    assert university.canonical_name == "Alabama A & M University"
    assert university.masters_granting is True
    assert university.ipeds_year == 2023
    assert university.last_verified_at == date(2026, 1, 1)

    aliases = db_session.query(UniversityAlias).filter_by(unitid=100654).all()
    assert [a.alias for a in aliases] == ["AAMU"]


def test_masters_only_filter_excludes_non_masters_institution_by_default(db_session):
    summary = import_hd_file(db_session, [BACHELORS_ONLY_ROW], ipeds_year=2023)
    db_session.commit()

    assert summary.universities_upserted == 0
    assert summary.universities_skipped_not_masters_granting == 1
    assert db_session.get(University, 100001) is None


def test_include_all_imports_non_masters_institution(db_session):
    summary = import_hd_file(
        db_session, [BACHELORS_ONLY_ROW], ipeds_year=2023, masters_only=False
    )
    db_session.commit()

    assert summary.universities_upserted == 1
    university = db_session.get(University, 100001)
    assert university is not None
    assert university.masters_granting is False


def test_reimport_same_year_is_idempotent(db_session):
    import_hd_file(db_session, [MASTERS_ROW], ipeds_year=2023, run_date=date(2026, 1, 1))
    db_session.commit()

    import_hd_file(db_session, [MASTERS_ROW], ipeds_year=2023, run_date=date(2026, 6, 1))
    db_session.commit()

    assert db_session.query(University).filter_by(unitid=100654).count() == 1
    assert db_session.query(UniversityAlias).filter_by(unitid=100654).count() == 1
    university = db_session.get(University, 100654)
    # last_verified_at should reflect the most recent import run.
    assert university.last_verified_at == date(2026, 6, 1)


def test_reimport_picks_up_changed_fields(db_session):
    import_hd_file(db_session, [MASTERS_ROW], ipeds_year=2023)
    db_session.commit()

    renamed = row(INSTNM="Alabama A&M University (Renamed)")
    import_hd_file(db_session, [renamed], ipeds_year=2023)
    db_session.commit()

    university = db_session.get(University, 100654)
    assert university.canonical_name == "Alabama A&M University (Renamed)"


def test_older_year_reimport_does_not_regress_identity_fields(db_session):
    import_hd_file(db_session, [MASTERS_ROW], ipeds_year=2023)
    db_session.commit()

    stale = row(INSTNM="Stale Old Name")
    import_hd_file(db_session, [stale], ipeds_year=2020)
    db_session.commit()

    university = db_session.get(University, 100654)
    assert university.canonical_name == "Alabama A & M University"
    assert university.ipeds_year == 2023


def test_coverage_tier_not_regressed_on_reimport(db_session):
    import_hd_file(db_session, [MASTERS_ROW], ipeds_year=2023)
    db_session.commit()

    university = db_session.get(University, 100654)
    university.coverage_tier = "PROGRAMS_DISCOVERED"
    db_session.commit()

    import_hd_file(db_session, [MASTERS_ROW], ipeds_year=2023)
    db_session.commit()

    university = db_session.get(University, 100654)
    assert university.coverage_tier.value == "PROGRAMS_DISCOVERED"


def test_invalid_rows_are_reported_and_skipped(db_session):
    summary = import_hd_file(
        db_session,
        [MASTERS_ROW, row(UNITID="", INSTNM="No ID College")],
        ipeds_year=2023,
    )
    db_session.commit()

    assert summary.rows_read == 2
    assert summary.universities_upserted == 1
    assert summary.universities_skipped_invalid == 1
    assert len(summary.issues) == 1
    assert summary.issues[0].reason == "missing or non-numeric UNITID"
