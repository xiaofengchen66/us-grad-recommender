from __future__ import annotations

from datetime import date

from us_grad_recommender.importers.ipeds.ef_importer import collect_enrollment_facts, import_ef_file
from us_grad_recommender.importers.ipeds.hd_importer import import_hd_file
from us_grad_recommender.models.university import University

MASTERS_ROW = {
    "UNITID": "100654",
    "INSTNM": "Alabama A & M University",
    "IALIAS": "",
    "WEBADDR": "",
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


def ef_row(unitid: str, efalevel: str, eftotlt: str, efnralt: str = "0") -> dict:
    return {"UNITID": unitid, "EFALEVEL": efalevel, "EFTOTLT": eftotlt, "EFNRALT": efnralt}


TOTAL_ROW = ef_row("100654", "1", "6614")
GRAD_ROW = ef_row("100654", "12", "769", "64")
IRRELEVANT_ROW = ef_row("100654", "32", "300")  # full-time graduate, not needed


def test_collect_enrollment_facts_reduces_long_file_to_one_entry_per_unitid():
    facts = collect_enrollment_facts([TOTAL_ROW, GRAD_ROW, IRRELEVANT_ROW])
    assert set(facts.keys()) == {100654}
    entry = facts[100654]
    assert entry.total_enrollment == 6614
    assert entry.graduate_enrollment == 769
    assert entry.international_graduate_enrollment == 64


def test_import_ef_file_updates_existing_institution(db_session):
    import_hd_file(db_session, [MASTERS_ROW], ipeds_year=2023, run_date=date(2026, 1, 1))
    db_session.commit()

    summary = import_ef_file(db_session, [TOTAL_ROW, GRAD_ROW], ef_year=2023)
    db_session.commit()

    assert summary.institutions_updated == 1
    assert summary.institutions_skipped_not_found == 0

    university = db_session.get(University, 100654)
    assert university.total_enrollment == 6614
    assert university.graduate_enrollment == 769
    assert university.international_graduate_enrollment == 64
    assert university.enrollment_year == 2023


def test_import_ef_file_skips_unknown_institution(db_session):
    summary = import_ef_file(db_session, [ef_row("999999", "1", "100")], ef_year=2023)
    db_session.commit()

    assert summary.institutions_updated == 0
    assert summary.institutions_skipped_not_found == 1
    assert 999999 in summary.skipped_unitids


def test_reimport_ef_is_idempotent(db_session):
    import_hd_file(db_session, [MASTERS_ROW], ipeds_year=2023)
    db_session.commit()

    import_ef_file(db_session, [TOTAL_ROW, GRAD_ROW], ef_year=2023)
    db_session.commit()
    import_ef_file(db_session, [TOTAL_ROW, GRAD_ROW], ef_year=2023)
    db_session.commit()

    university = db_session.get(University, 100654)
    assert university.total_enrollment == 6614
    assert university.graduate_enrollment == 769


def test_reimport_ef_refreshes_changed_figures(db_session):
    import_hd_file(db_session, [MASTERS_ROW], ipeds_year=2023)
    db_session.commit()

    import_ef_file(db_session, [TOTAL_ROW, GRAD_ROW], ef_year=2023)
    db_session.commit()

    updated_total = ef_row("100654", "1", "7000")
    updated_grad = ef_row("100654", "12", "800", "70")
    import_ef_file(db_session, [updated_total, updated_grad], ef_year=2024)
    db_session.commit()

    university = db_session.get(University, 100654)
    assert university.total_enrollment == 7000
    assert university.graduate_enrollment == 800
    assert university.international_graduate_enrollment == 70
    assert university.enrollment_year == 2024
