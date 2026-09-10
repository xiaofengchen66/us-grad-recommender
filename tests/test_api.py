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


def test_cors_allows_frontend_dev_origin(client):
    response = client.get("/healthz", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_rejects_other_origins(client):
    response = client.get("/healthz", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_universities_map_returns_geojson(client, seeded):
    response = client.get("/universities/map")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    # all 3 seeded institutions have real coordinates from the fixtures
    assert len(body["features"]) == 3
    feature = next(f for f in body["features"] if f["properties"]["unitid"] == 100654)
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    # GeoJSON coordinate order is [longitude, latitude] — Alabama A&M's
    # fixture longitude (-86.568502) is negative, latitude (34.783368) is
    # positive, so this also catches an accidental lat/lon swap.
    lon, lat = feature["geometry"]["coordinates"]
    assert lon == pytest.approx(-86.568502)
    assert lat == pytest.approx(34.783368)


def test_universities_map_normalizes_carnegie_not_applicable_sentinel(client, db_session):
    """Regression for a real MEDIUM finding: the map endpoint passed IPEDS's
    -2 ("not in the Carnegie universe") sentinel straight through, while
    recommendation.py's scoring treats it as "no classification" — a
    frontend coloring markers by the raw field would render those
    institutions as if -2 were a real tier."""
    not_applicable = {**ALABAMA_AM, "UNITID": "999002", "C21BASIC": "-2", "IALIAS": ""}
    import_hd_file(db_session, [not_applicable], ipeds_year=2023, masters_only=False)
    db_session.commit()

    response = client.get("/universities/map")

    feature = next(f for f in response.json()["features"] if f["properties"]["unitid"] == 999002)
    assert feature["properties"]["carnegie_classification"] is None


def test_universities_map_registered_before_unitid_route(client, seeded):
    # /universities/map must not be swallowed by /universities/{unitid}
    response = client.get("/universities/map")
    assert response.status_code == 200
    assert response.json()["type"] == "FeatureCollection"


def test_recommendations_minimal_profile(client, seeded):
    response = client.post(
        "/recommendations",
        json={
            "degree_level": "masters",
            "program_category": "cs_masters",
            "program_name": "Computer Science",
            "gpa": 3.6,
            "gpa_scale": "scale_4_0",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) == 2  # only the 2 masters-granting seeded institutions
    for result in body["results"]:
        assert 0 <= result["match_score"] <= 100
        assert "admission_probability" not in result
        assert "location_fit" not in result["component_scores"]  # hard filter, not a score
        assert result["component_scores"]["cost_fit"] is None  # no budget provided


def test_recommendations_preferred_states_hard_filters_out_other_states(client, seeded):
    """UT Austin (TX) and Alabama A&M (AL) are both masters-granting in the
    seeded fixture — restricting to TX must exclude Alabama A&M entirely,
    not just deprioritize it."""
    response = client.post(
        "/recommendations",
        json={
            "degree_level": "masters",
            "program_category": "general",
            "program_name": "Public Administration",
            "gpa": 3.2,
            "gpa_scale": "scale_4_0",
            "budget_max_usd": 30000,
            "preferred_states": ["TX"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    unitids = {r["unitid"] for r in body["results"]}
    assert unitids == {228778}


def test_recommendations_rejects_missing_required_field(client, seeded):
    response = client.post(
        "/recommendations",
        json={"degree_level": "masters", "program_category": "general", "gpa": 3.2},
    )
    assert response.status_code == 422


def test_recommendations_rejects_degree_level_category_mismatch(client, seeded):
    """Regression for a real MEDIUM finding: program_category=cs_phd
    implies degree_level=doctoral, but nothing previously stopped a
    request from claiming degree_level=masters at the same time."""
    response = client.post(
        "/recommendations",
        json={
            "degree_level": "masters",
            "program_category": "cs_phd",
            "program_name": "Computer Science",
            "gpa": 3.6,
            "gpa_scale": "scale_4_0",
        },
    )
    assert response.status_code == 422


def test_recommendations_non_4_0_gpa_scale_accepted_and_neutral(client, seeded):
    """A GPA on a non-4.0 scale (e.g. 100-point) must be accepted, not
    naively compared — see test_recommendation.py's scoring-level
    regression test for the underlying bug this guards."""
    response = client.post(
        "/recommendations",
        json={
            "degree_level": "masters",
            "program_category": "general",
            "program_name": "Computer Science",
            "gpa": 86,
            "gpa_scale": "other",
        },
    )
    assert response.status_code == 200
    body = response.json()
    for result in body["results"]:
        assert result["component_scores"]["academic_fit"] == 60.0


def test_recommendations_rejects_implausible_gpa_for_4_0_scale(client, seeded):
    """Regression for a real MEDIUM finding: {"gpa": 95, "gpa_scale":
    "scale_4_0"} previously passed validation and would have reproduced
    the exact near-perfect-score bug the BLOCKING gpa_scale fix closed."""
    response = client.post(
        "/recommendations",
        json={
            "degree_level": "masters",
            "program_category": "general",
            "program_name": "Computer Science",
            "gpa": 95,
            "gpa_scale": "scale_4_0",
        },
    )
    assert response.status_code == 422


def test_cors_allows_post_for_recommendations(client):
    response = client.options(
        "/recommendations",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
