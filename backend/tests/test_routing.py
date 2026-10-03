"""POST /route: mock provider end to end, ORS client against a fake transport, and scoring."""

import httpx
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import LineString

from app.errors import AppError
from app.main import app
from app.routing.providers import OrsProvider
from app.routing.schemas import Point, RouteOut, Scores, Weights
from app.routing.scoring import coverage, dimension_scores, overall_score, rank
from app.routing.segments import InMemorySegmentSource, SegmentMatch

client = TestClient(app)

RYNEK = {"lat": 50.0617, "lon": 19.9373}
WAWEL = {"lat": 50.0540, "lon": 19.9353}


def route(weights=None, **overrides):
    body = {"from": RYNEK, "to": WAWEL, "profile": "driving-car", "weights": weights or {}, **overrides}
    return client.post("/api/v1/route", json=body)


# --- endpoint, mock provider + sample segments ---------------------------------------------------

def test_without_weights_fastest_route_wins():
    res = route()
    assert res.status_code == 200
    routes = res.json()["routes"]
    assert [r["rank"] for r in routes] == [1, 2, 3]
    assert routes[0]["duration_s"] == min(r["duration_s"] for r in routes)
    assert set(routes[0]) == {"rank", "geometry", "distance_m", "duration_s", "score", "scores", "coverage", "segment_ids"}


def test_views_weight_prefers_scenic_east_variant():
    top = route({"views": 3}).json()["routes"][0]
    assert top["segment_ids"] == [9003, 9004]
    assert top["scores"]["views"] == 5.0


def test_traffic_weight_prefers_west_variant():
    top = route({"traffic": 3}).json()["routes"][0]
    assert top["segment_ids"] == [9005, 9006]


def test_unrated_dimension_is_null_not_zero():
    west = next(r for r in route().json()["routes"] if r["segment_ids"] == [9005, 9006])
    assert west["scores"]["parking"] is None


def test_coverage_is_share_of_route_on_rated_segments():
    for r in route().json()["routes"]:
        assert 0.9 <= r["coverage"] <= 1.0


def test_geometry_is_lon_lat_linestring():
    geometry = route().json()["routes"][0]["geometry"]
    assert geometry["type"] == "LineString"
    lon, lat = geometry["coordinates"][0]
    assert 19 < lon < 21 and 49 < lat < 51


@pytest.mark.parametrize("field", ["from", "to"])
def test_point_outside_krakow_is_rejected(field):
    res = route(**{field: {"lat": 52.23, "lon": 21.01}})  # Warsaw
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "OUT_OF_AREA"
    assert res.json()["error"]["details"]["field"] == field


def test_weight_above_three_is_rejected():
    res = route({"surface": 4})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_profile_is_rejected():
    assert route(profile="flying-carpet").status_code == 422


# --- ORS client ----------------------------------------------------------------------------------

ORS_OK = {
    "features": [
        {"geometry": {"coordinates": [[19.9373, 50.0617], [19.9353, 50.0540]]},
         "properties": {"summary": {"distance": 900.5, "duration": 130.2}}},
    ]
}


def ors(handler):
    client_ = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OrsProvider("secret-key", "https://ors.test/", client=client_)


async def test_ors_request_and_parsing():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["Authorization"], request.content
        return httpx.Response(200, json=ORS_OK)

    routes = await ors(handler).routes(Point(**RYNEK), Point(**WAWEL), "cycling-regular")
    assert seen["url"] == "https://ors.test/v2/directions/cycling-regular/geojson"
    assert seen["auth"] == "secret-key"
    assert b'"alternative_routes"' in seen["body"] and b"[19.9373,50.0617]" in seen["body"].replace(b" ", b"")
    assert routes[0].distance_m == 900.5 and routes[0].coordinates[0] == [19.9373, 50.0617]


@pytest.mark.parametrize(
    ("response", "status", "code"),
    [
        (httpx.Response(429), 429, "RATE_LIMITED"),
        (httpx.Response(500), 502, "UPSTREAM_ERROR"),
        (httpx.Response(200, json={"unexpected": True}), 502, "UPSTREAM_ERROR"),
    ],
)
async def test_ors_errors_use_contract_codes(response, status, code):
    with pytest.raises(AppError) as err:
        await ors(lambda _: response).routes(Point(**RYNEK), Point(**WAWEL), "driving-car")
    assert (err.value.status, err.value.code) == (status, code)


async def test_ors_unroutable_point_is_not_found_with_provider_code():
    body = {"error": {"code": 2010, "message": "Could not find routable point within a radius of 350.0 meters"}}
    with pytest.raises(AppError) as err:
        await ors(lambda _: httpx.Response(404, json=body)).routes(Point(**RYNEK), Point(**WAWEL), "driving-car")
    assert (err.value.status, err.value.code) == (404, "NOT_FOUND")
    assert err.value.details == {"profile": "driving-car", "provider_code": 2010}


async def test_ors_network_failure_is_upstream_error():
    def boom(_):
        raise httpx.ConnectError("down")

    with pytest.raises(AppError) as err:
        await ors(boom).routes(Point(**RYNEK), Point(**WAWEL), "driving-car")
    assert err.value.code == "UPSTREAM_ERROR"


# --- scoring -------------------------------------------------------------------------------------

def match(seg_id, overlap, **scores):
    return SegmentMatch(seg_id, overlap, {d: scores.get(d) for d in ("surface", "views", "safety", "traffic", "parking")})


def test_dimension_scores_are_length_weighted():
    scores = dimension_scores([match(1, 300, surface=5.0), match(2, 100, surface=1.0, views=4.0)])
    assert scores["surface"] == 4.0  # (300*5 + 100*1) / 400
    assert scores["views"] == 4.0  # only the segment that has a rating counts
    assert scores["parking"] is None


def test_overall_score_uses_only_weighted_dimensions():
    scores = {"surface": 4.0, "views": 2.0, "safety": None, "traffic": None, "parking": None}
    assert overall_score(scores, Weights(surface=3, views=1)) == 3.5  # (4*3 + 2*1) / 4
    assert overall_score(scores, Weights(surface=3)) == 4.0
    assert overall_score(scores, Weights()) == 3.0  # no weights: plain mean of rated dimensions
    assert overall_score({d: None for d in scores}, Weights(surface=3)) is None


def test_coverage_is_capped_at_one():
    assert coverage([match(1, 600), match(2, 600)], 1000) == 1.0
    assert coverage([], 1000) == 0.0
    assert coverage([match(1, 250)], 0) == 0.0


def make_route(duration, score):
    return RouteOut(rank=0, geometry={"coordinates": []}, distance_m=1, duration_s=duration, score=score,
                    scores=Scores(), coverage=1, segment_ids=[])


def test_rank_puts_unrated_routes_last_and_breaks_ties_by_time():
    routes = [make_route(100, None), make_route(300, 4.0), make_route(200, 4.0), make_route(50, 3.0)]
    ranked = rank(routes, Weights(surface=1))
    assert [(r.rank, r.duration_s) for r in ranked] == [(1, 200), (2, 300), (3, 50), (4, 100)]


def test_in_memory_source_ignores_far_segments():
    source = InMemorySegmentSource.from_file()
    far = LineString([[19.99, 50.10], [20.00, 50.11]])
    assert source.matches(far, 15.0, 0.5) == []


def test_segment_only_touching_the_route_is_dropped():
    source = InMemorySegmentSource.from_file()
    # diverges from 9001 and 9005 at a shallow angle, so it stays within 15 m of them for ~35 m at the start
    east = LineString([[19.9373, 50.0617], [19.9393, 50.05785], [19.9353, 50.0540]])
    assert sorted(m.id for m in source.matches(east, 15.0, 0.5)) == [9003, 9004]
