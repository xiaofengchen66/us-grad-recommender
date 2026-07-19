from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from us_grad_recommender.api.app import app
from us_grad_recommender.api.deps import get_db
from us_grad_recommender.importers.ipeds.hd_importer import import_hd_file

ALABAMA_AM = {
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
    "C21BASIC": "18",
    "C21SZSET": "14",
}

UT_AUSTIN = {
    "UNITID": "228778",
    "INSTNM": "The University of Texas at Austin",
    "IALIAS": "UT Austin  UT",
    "WEBADDR": "www.utexas.edu/",
    "CITY": "Austin",
    "STABBR": "TX",
    "LATITUDE": "30.285026",
    "LONGITUD": "-97.733585",
    "CONTROL": "1",
    "HLOFFER": "9",
    "GROFFER": "1",
    "DEGGRANT": "1",
    "CYACTIVE": "1",
    "C21BASIC": "15",
    "C21SZSET": "15",
}

BACHELORS_ONLY = {
    **ALABAMA_AM,
    "UNITID": "999001",
    "INSTNM": "Bachelors Only College",
    "IALIAS": "",
    "STABBR": "AL",
    "HLOFFER": "5",
}


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        return db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def seeded(db_session):
    import_hd_file(db_session, [ALABAMA_AM, UT_AUSTIN], ipeds_year=2023, masters_only=False)
    import_hd_file(db_session, [BACHELORS_ONLY], ipeds_year=2023, masters_only=False)
    db_session.commit()


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_by_name(client, seeded):
    response = client.get("/universities", params={"q": "Alabama A & M"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["unitid"] == 100654


def test_search_is_case_insensitive(client, seeded):
    response = client.get("/universities", params={"q": "alabama a & m"})
    assert response.json()["total"] == 1


def test_search_matches_alias(client, seeded):
    response = client.get("/universities", params={"q": "AAMU"})
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["unitid"] == 100654


def test_search_matches_multi_value_alias(client, seeded):
    # UT_AUSTIN's IALIAS is "UT Austin  UT" (double-space-delimited, like the
    # real HD file) — the importer splits this into two separate aliases.
    response = client.get("/universities", params={"q": "UT Austin"})
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["unitid"] == 228778


def test_search_by_state_filter(client, seeded):
    response = client.get("/universities", params={"state": "tx"})
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["unitid"] == 228778


def test_search_by_sector_filter(client, seeded):
    response = client.get("/universities", params={"sector": "public"})
    body = response.json()
    assert body["total"] == 3  # all three seeded institutions are public


def test_search_by_masters_granting_filter(client, seeded):
    response = client.get("/universities", params={"masters_granting": "true"})
    body = response.json()
    unitids = {r["unitid"] for r in body["results"]}
    assert unitids == {100654, 228778}
    assert body["total"] == 2


def test_search_no_results(client, seeded):
    response = client.get("/universities", params={"q": "Nonexistent Institution Name"})
    assert response.json() == {"total": 0, "limit": 25, "offset": 0, "results": []}


def test_search_pagination(client, seeded):
    first_page = client.get("/universities", params={"limit": 1, "offset": 0}).json()
    second_page = client.get("/universities", params={"limit": 1, "offset": 1}).json()
    assert first_page["total"] == 3
    assert second_page["total"] == 3
    assert first_page["results"][0]["unitid"] != second_page["results"][0]["unitid"]


def test_search_rejects_limit_over_max(client, seeded):
    response = client.get("/universities", params={"limit": 101})
    assert response.status_code == 422


def test_get_university_detail(client, seeded):
    response = client.get("/universities/100654")
    assert response.status_code == 200
    body = response.json()
    assert body["canonical_name"] == "Alabama A & M University"
    assert body["carnegie_classification_label"] == (
        "Master's Colleges & Universities: Larger Programs"
    )
    assert body["aliases"] == [
        {"alias": "AAMU", "alias_type": "ipeds_alias", "source": "IPEDS HD2023"}
    ]


def test_get_university_not_found(client, seeded):
    response = client.get("/universities/1")
    assert response.status_code == 404
