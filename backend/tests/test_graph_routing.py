"""POST /route for cars and bikes: the own graph. Database access is replaced by fakes, so these tests prove the
request/response logic (weights, ranking, scores, coverage, errors, limits); the SQL itself is exercised against
the real database by test_graph_db.py (opt-in)."""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app import main
from app.errors import AppError
from app.main import app
from app.routing.graph import (MAX_SNAP_M, EdgeStep, PostgresGraphSource, Snap, build_route, graph_routes,
                               step_scores, stitch)
from app.routing.router import get_graph_source
from app.routing.schemas import Point, Weights

client = TestClient(app)

RYNEK = {"lat": 50.0617, "lon": 19.9373}
PODGORZE = {"lat": 50.0470, "lon": 19.9440}
NONE = {d: None for d in ("surface", "views", "safety", "traffic", "parking")}


def step(edge_id, length=100.0, time=10.0, segment=None, rated=False, coords=None, **scores):
    return EdgeStep(
        edge_id=edge_id, segment_id=segment, length_m=length, time_s=time, rated=rated,
        scores={**NONE, **scores},
        coordinates=coords or [[19.0 + edge_id / 1000, 50.0], [19.0 + (edge_id + 1) / 1000, 50.0]],
    )


class FakeGraph:
    """Returns canned paths: the first for the user's weights, the second for the fastest route."""

    def __init__(self, weighted, fastest=None, snap=10.0):
        self.paths = [weighted] + ([fastest] if fastest is not None else [])
        self.snap_m = snap
        self.calls = []

    def snap(self, profile, point):
        # distinct points snap to distinct nodes, identical points to the same one
        return None if self.snap_m is None else Snap(hash((point.lat, point.lon)), self.snap_m)

    def find(self, profile, legs, variants):
        self.calls.append((profile, legs, variants))
        return self.paths[: len(variants)]


def use(graph):
    app.dependency_overrides[get_graph_source] = lambda: graph
    return graph


def route(weights=None, profile="driving-car", **overrides):
    body = {"from": RYNEK, "to": PODGORZE, "profile": profile, "weights": weights or {}, **overrides}
    return client.post("/api/v1/route", json=body)


SCENIC = [step(1, 200, 30, segment=11, rated=True, views=5.0, traffic=4.0),
          step(2, 300, 60, segment=12, rated=True, views=4.0, traffic=2.0)]
FAST = [step(3, 400, 40, segment=13, rated=True, views=1.0, traffic=1.0),
        step(4, 100, 10)]


# --- pure helpers ----------------------------------------------------------------------------------------------

def test_stitch_keeps_the_shared_junction_point_once():
    a = step(1, coords=[[1.0, 1.0], [2.0, 2.0]])
    b = step(2, coords=[[2.0, 2.0], [3.0, 3.0]])
    c = step(3, coords=[[9.0, 9.0], [10.0, 10.0]])  # does not touch b: nothing is dropped
    assert stitch([a, b]) == [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]
    assert stitch([b, c]) == [[2.0, 2.0], [3.0, 3.0], [9.0, 9.0], [10.0, 10.0]]
    assert stitch([]) == []


def test_step_scores_are_length_weighted_over_rated_dimensions_only():
    steps = [step(1, 300, surface=5.0), step(2, 100, surface=1.0, views=4.0), step(3, 500)]
    scores = step_scores(steps)
    assert scores["surface"] == 4.0  # (300*5 + 100*1) / 400, the unrated edge does not count
    assert scores["views"] == 4.0
    assert scores["parking"] is None  # nobody rated it: null, not a made-up number


def test_build_route_fields():
    steps = [step(1, 200.04, 30.04, segment=7, rated=True, surface=4.0),
             step(2, 100.0, 20.0, segment=7), step(3, 100.0, 10.0, segment=5, rated=True, surface=2.0)]
    out = build_route(steps, Weights(surface=3))
    assert out.distance_m == 400.0 and out.duration_s == 60.0
    assert out.segment_ids == [5, 7]  # unique, sorted, includes the unrated edge's segment
    assert out.coverage == 0.75  # 300 of 400 m on rated segments
    assert out.scores.surface == 3.33  # (200*4 + 100*2) / 300, the unrated 100 m edge does not count
    assert out.score == 3.33  # only the weighted dimension counts
    assert out.scores.parking is None


def test_route_without_any_ratings_has_null_score_and_zero_coverage():
    out = build_route([step(1), step(2)], Weights(surface=3))
    assert out.score is None and out.coverage == 0.0 and out.segment_ids == []


# --- graph_routes ----------------------------------------------------------------------------------------------

def test_without_weights_only_the_fastest_route_is_asked_for():
    graph = FakeGraph(FAST)
    routes = graph_routes(graph, "driving-car", Point(**RYNEK), Point(**PODGORZE), Weights())
    assert [r.rank for r in routes] == [1]
    assert graph.calls[0][2] == [Weights()]


def test_with_weights_rank_1_is_the_users_route_and_rank_2_the_fastest():
    graph = FakeGraph(SCENIC, FAST)
    weights = Weights(views=3, traffic=1)
    routes = graph_routes(graph, "cycling-regular", Point(**RYNEK), Point(**PODGORZE), weights)
    assert graph.calls[0][2] == [weights, Weights()]
    assert [r.rank for r in routes] == [1, 2]
    assert routes[0].segment_ids == [11, 12] and routes[1].segment_ids == [13]
    assert routes[0].duration_s == 90.0 and routes[1].duration_s == 50.0
    # both routes are scored with the user's weights, so they can be compared
    assert routes[0].score > routes[1].score


def test_identical_user_and_fastest_routes_are_returned_once():
    routes = graph_routes(FakeGraph(FAST, FAST), "driving-car", Point(**RYNEK), Point(**PODGORZE), Weights(views=3))
    assert len(routes) == 1 and routes[0].rank == 1


@pytest.mark.parametrize("snap", [None, MAX_SNAP_M + 1])
def test_point_far_from_any_road_is_not_found(snap):
    with pytest.raises(AppError) as err:
        graph_routes(FakeGraph(FAST, snap=snap), "driving-car", Point(**RYNEK), Point(**PODGORZE), Weights())
    assert (err.value.status, err.value.code) == (404, "NOT_FOUND")
    assert err.value.details == {"profile": "driving-car", "field": "from"}


VIA = Point(lat=50.0540, lon=19.9353)


def test_via_stops_split_the_route_into_legs_in_order():
    graph = FakeGraph(SCENIC)
    other = Point(lat=50.0500, lon=19.9400)
    graph_routes(graph, "driving-car", Point(**RYNEK), Point(**PODGORZE), Weights(), via=[VIA, other])
    legs = graph.calls[0][1]
    assert legs == [(Point(**RYNEK), VIA), (VIA, other), (other, Point(**PODGORZE))]


def test_via_on_top_of_the_previous_stop_adds_no_leg():
    graph = FakeGraph(SCENIC)
    graph_routes(graph, "driving-car", Point(**RYNEK), Point(**PODGORZE), Weights(), via=[Point(**RYNEK)])
    assert graph.calls[0][1] == [(Point(**RYNEK), Point(**PODGORZE))]


def test_far_via_is_reported_with_its_index():
    class FarVia(FakeGraph):
        def snap(self, profile, point):
            return Snap(1 if point == VIA else hash((point.lat, point.lon)), 5000.0 if point == VIA else 5.0)

    with pytest.raises(AppError) as err:
        graph_routes(FarVia(SCENIC), "driving-car", Point(**RYNEK), Point(**PODGORZE), Weights(), via=[VIA])
    assert (err.value.status, err.value.details) == (404, {"profile": "driving-car", "field": "via[0]"})


def test_same_start_and_destination_without_via_is_not_found():
    with pytest.raises(AppError) as err:
        graph_routes(FakeGraph(SCENIC), "driving-car", Point(**RYNEK), Point(**RYNEK), Weights())
    assert err.value.status == 404


def test_empty_path_is_not_found():
    with pytest.raises(AppError) as err:
        graph_routes(FakeGraph([]), "driving-car", Point(**RYNEK), Point(**PODGORZE), Weights())
    assert (err.value.status, err.value.code) == (404, "NOT_FOUND")


def test_graph_refuses_a_walking_profile():
    with pytest.raises(AppError) as err:
        graph_routes(FakeGraph(FAST), "foot-walking", Point(**RYNEK), Point(**PODGORZE), Weights())
    assert err.value.status == 422


# --- endpoint --------------------------------------------------------------------------------------------------

def test_endpoint_returns_contract_fields_for_cars():
    graph = use(FakeGraph(SCENIC, FAST))
    res = route({"views": 3})
    assert res.status_code == 200
    routes = res.json()["routes"]
    assert [r["rank"] for r in routes] == [1, 2]
    assert set(routes[0]) == {"rank", "geometry", "distance_m", "duration_s", "score", "scores", "coverage", "segment_ids"}
    assert routes[0]["geometry"]["type"] == "LineString"
    assert routes[0]["scores"]["parking"] is None
    assert graph.calls[0][0] == "driving-car"


FRONTEND_REQUEST = {  # what the frontend sends: an optional intermediate stop
    "from": {"lat": 50.06686331811255, "lon": 19.93412799209031},
    "to": {"lat": 50.06705043002839, "lon": 19.930265608621056},
    "via": [{"lat": 50.06549504004241, "lon": 19.93070285958069}],
    "profile": "driving-car",
    "weights": {"surface": 2, "views": 0, "safety": 0, "traffic": 0, "parking": 0},
}


def test_endpoint_accepts_the_frontend_request_with_via():
    graph = use(FakeGraph(SCENIC, FAST))
    res = client.post("/api/v1/route", json=FRONTEND_REQUEST)
    assert res.status_code == 200
    assert [r["rank"] for r in res.json()["routes"]] == [1, 2]
    profile, legs, variants = graph.calls[0]
    assert len(legs) == 2 and legs[0][1] == legs[1][0]  # from -> via, via -> to
    assert variants[0] == Weights(surface=2)


def test_via_is_optional():
    use(FakeGraph(FAST))
    body = {k: v for k, v in FRONTEND_REQUEST.items() if k != "via"}
    assert client.post("/api/v1/route", json=body).status_code == 200


def test_via_outside_krakow_is_rejected_with_its_index():
    graph = use(FakeGraph(FAST))
    res = client.post("/api/v1/route", json={**FRONTEND_REQUEST, "via": [{"lat": 52.23, "lon": 21.01}]})
    assert res.status_code == 422 and res.json()["error"]["code"] == "OUT_OF_AREA"
    assert res.json()["error"]["details"]["field"] == "via[0]" and graph.calls == []


def test_too_many_via_stops_are_rejected():
    use(FakeGraph(FAST))
    stops = [{"lat": 50.06, "lon": 19.94}] * 6
    res = client.post("/api/v1/route", json={**FRONTEND_REQUEST, "via": stops})
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_pedestrian_route_goes_through_the_via_stops():
    res = client.post("/api/v1/route", json={**FRONTEND_REQUEST, "profile": "foot-walking"})
    assert res.status_code == 200
    routes = res.json()["routes"]
    assert len(routes) == 1  # a route with stops is a single route
    assert [19.93070285958069, 50.06549504004241] in routes[0]["geometry"]["coordinates"]


def test_endpoint_serves_bikes_from_the_graph_too():
    graph = use(FakeGraph(FAST))
    assert route(profile="cycling-regular").status_code == 200
    assert graph.calls[0][0] == "cycling-regular"


def test_pedestrians_do_not_touch_the_graph():
    graph = use(FakeGraph(FAST))
    res = route(profile="foot-walking")
    assert res.status_code == 200 and graph.calls == []
    assert len(res.json()["routes"]) == 3  # mock provider's alternatives


def test_pedestrians_work_without_a_database():
    assert route(profile="foot-walking").status_code == 200  # no graph override, no pool


def test_cars_without_database_configuration_get_a_clean_error():
    res = route()  # default dependency: the application has no pool in tests
    assert res.status_code == 500
    assert res.json()["error"]["code"] == "INTERNAL_ERROR"


def test_outside_krakow_is_rejected_before_the_graph_is_used():
    graph = use(FakeGraph(FAST))
    res = route(**{"to": {"lat": 52.23, "lon": 21.01}})
    assert res.status_code == 422 and res.json()["error"]["code"] == "OUT_OF_AREA"
    assert graph.calls == []


def test_route_limit_is_30_per_minute_per_ip():
    use(FakeGraph(FAST))
    assert all(route().status_code == 200 for _ in range(30))
    res = route()
    assert res.status_code == 429 and res.json()["error"]["code"] == "RATE_LIMITED"


# --- PostgresGraphSource against a fake pool -----------------------------------------------------------------------

class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, find_rows, score_rows, snap_rows):
        self.find_rows, self.score_rows, self.snap_rows = find_rows, score_rows, snap_rows
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "routing_snap" in sql:
            return FakeResult(self.snap_rows)
        if "find_route" in sql:
            return FakeResult(self.find_rows.pop(0))
        return FakeResult(self.score_rows)


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def connection(self):
        yield self.conn


def find_row(seq, edge_id, segment_id, length_m, rated, coords):
    return {"seq": seq, "edge_id": edge_id, "segment_id": segment_id, "length_m": length_m, "time_s": length_m / 10,
            "rated": rated, "geometry": {"type": "LineString", "coordinates": coords}}


def test_postgres_source_maps_rows_and_scores():
    rows = [find_row(1, 10, 100, 200.0, True, [[19.9, 50.0], [19.91, 50.0]]),
            find_row(2, 11, 101, 50.0, False, [[19.91, 50.0], [19.92, 50.0]])]
    conn = FakeConnection([rows, rows], [{"segment_id": 100, "surface": 4.5, "views": None, "safety": 3.0,
                                            "traffic": None, "parking": None}], [{"node_id": 77, "distance_m": 12.5}])
    source = PostgresGraphSource(FakePool(conn))

    assert source.snap("driving-car", Point(**RYNEK)) == Snap(77, 12.5)
    paths = source.find("driving-car", [(Point(**RYNEK), Point(**PODGORZE))],
                        [Weights(surface=2, traffic=1), Weights()])

    assert len(paths) == 2 and [s.edge_id for s in paths[0]] == [10, 11]
    assert paths[0][0].scores["surface"] == 4.5 and paths[0][0].scores["views"] is None
    assert paths[0][1].scores == NONE  # segment 101 has no score row
    assert paths[0][0].rated and not paths[0][1].rated
    find_calls = [p for sql, p in conn.executed if "find_route" in sql]
    assert find_calls[0] == {"profile": "driving-car", "from_lon": 19.9373, "from_lat": 50.0617, "to_lon": 19.944,
                             "to_lat": 50.047, "surface": 2, "views": 0, "safety": 0, "traffic": 1, "parking": 0}
    score_calls = [p for sql, p in conn.executed if "segment_scores" in sql]
    assert score_calls == [([100, 101],)]  # one query for both variants, each segment once


def test_postgres_source_without_pool_raises_a_clean_error():
    with pytest.raises(AppError) as err:
        PostgresGraphSource(None).snap("driving-car", Point(**RYNEK))
    assert (err.value.status, err.value.code) == (500, "INTERNAL_ERROR")


def test_postgres_source_with_no_rows_returns_empty_paths_and_skips_the_scores_query():
    conn = FakeConnection([[]], [], [])
    source = PostgresGraphSource(FakePool(conn))
    assert source.find("driving-car", [(Point(**RYNEK), Point(**PODGORZE))], [Weights()]) == [[]]
    assert not any("segment_scores" in sql for sql, _ in conn.executed)
    assert source.snap("driving-car", Point(**RYNEK)) is None


def test_postgres_source_joins_the_legs_in_order_and_gives_up_when_one_has_no_route():
    first = [find_row(1, 10, None, 100.0, False, [[19.90, 50.0], [19.91, 50.0]])]
    second = [find_row(1, 20, None, 100.0, False, [[19.91, 50.0], [19.92, 50.0]])]
    via = Point(lat=50.0540, lon=19.9353)
    legs = [(Point(**RYNEK), via), (via, Point(**PODGORZE))]

    joined = PostgresGraphSource(FakePool(FakeConnection([first, second], [], []))).find("driving-car", legs, [Weights()])
    assert [s.edge_id for s in joined[0]] == [10, 20]
    assert stitch(joined[0]) == [[19.90, 50.0], [19.91, 50.0], [19.92, 50.0]]

    conn = FakeConnection([first, [], first, second], [], [])  # variant 1: second leg unreachable
    paths = PostgresGraphSource(FakePool(conn)).find("driving-car", legs, [Weights(surface=1), Weights()])
    assert paths[0] == [] and [s.edge_id for s in paths[1]] == [10, 20]


# --- health ------------------------------------------------------------------------------------------------------

class HealthConnection:
    def __init__(self, ready=True, fail=False):
        self.ready, self.fail = ready, fail

    def execute(self, sql, params=None):
        if self.fail:
            raise RuntimeError("down")
        return FakeResult([{"ready": self.ready}])


@pytest.mark.parametrize(
    ("pool", "expected"),
    [(None, "not_configured"), (FakePool(HealthConnection(ready=False)), "error"),
     (FakePool(HealthConnection(fail=True)), "error"), (FakePool(HealthConnection()), "ok")],
)
def test_routing_health_requires_a_built_graph(monkeypatch, pool, expected):
    monkeypatch.setattr(app.state, "db_pool", pool, raising=False)
    monkeypatch.setattr(main.settings, "routing_provider", "mock")
    assert main._check_routing() == expected
