"""OSM tag interpretation for car and bike routing."""

import pytest

from app.osm_access import BACKWARD, BOTH, FORWARD, NONE, bike_direction, car_direction, classify, parse_maxspeed


def way(highway="residential", **tags):
    return {"highway": highway, **{k.replace("__", ":"): v for k, v in tags.items()}}


@pytest.mark.parametrize("tags,expected", [
    (way(), BOTH),
    (way(oneway="yes"), FORWARD),
    (way(oneway="true"), FORWARD),
    (way(oneway="-1"), BACKWARD),
    (way(oneway="no"), BOTH),
    (way(oneway="reversible"), NONE),
    (way("motorway"), FORWARD),                       # implied one-way
    (way("motorway", oneway="no"), BOTH),
    (way(junction="roundabout"), FORWARD),
    (way(junction="roundabout", oneway="no"), BOTH),
])
def test_car_direction(tags, expected):
    assert car_direction(tags) == expected


@pytest.mark.parametrize("tags", [
    way("footway"), way("steps"), way("cycleway"), way("path"), way("track"), way("pedestrian"),
    way(access="no"), way(access="private"), way(motor_vehicle="no"), way(motorcar="private"),
    way("service", service="parking_aisle"), way("service", service="driveway"), way(area="yes"),
])
def test_car_cannot_use(tags):
    assert car_direction(tags) == NONE


def test_car_specific_access_overrides_general():
    assert car_direction(way(access="no", motor_vehicle="yes")) == BOTH
    assert car_direction(way(access="yes", motor_vehicle="no")) == NONE
    assert car_direction(way(access="destination")) == BOTH  # destination traffic is allowed through


@pytest.mark.parametrize("tags,expected", [
    (way("cycleway"), BOTH),
    (way("cycleway", oneway="yes"), FORWARD),
    (way(), BOTH),
    (way(oneway="yes"), FORWARD),                                        # bikes follow the street ...
    (way(oneway="yes", oneway__bicycle="no"), BOTH),                     # ... unless explicitly exempt
    (way(oneway="yes", cycleway="opposite_lane"), BOTH),                 # contraflow lane
    (way(oneway="yes", cycleway__left="opposite_track"), BOTH),
    (way(oneway="yes", cycleway__right="lane"), FORWARD),                # an ordinary lane is not contraflow
    (way(oneway="-1", cycleway="opposite"), BOTH),
    (way(oneway__bicycle="yes"), FORWARD),
    (way(junction="roundabout"), FORWARD),
    (way("track"), BOTH),
    (way("path", bicycle="designated"), BOTH),
])
def test_bike_direction(tags, expected):
    assert bike_direction(tags) == expected


@pytest.mark.parametrize("tags", [
    way("motorway"), way("motorway_link"), way("trunk"), way("steps"), way("footway"), way("pedestrian"),
    way(bicycle="no"), way(bicycle="dismount"), way(access="no"), way(vehicle="no"),
    way("service", service="parking_aisle"),
])
def test_bike_cannot_use(tags):
    assert bike_direction(tags) == NONE


def test_bike_exceptions_to_the_defaults():
    assert bike_direction(way("footway", bicycle="yes")) == BOTH
    assert bike_direction(way("pedestrian", bicycle="designated")) == BOTH
    assert bike_direction(way("trunk", bicycle="yes")) == BOTH
    assert bike_direction(way(access="no", bicycle="yes")) == BOTH
    assert bike_direction(way("motorway", bicycle="yes")) == NONE  # never


@pytest.mark.parametrize("raw,expected", [
    ("50", 50), ("30", 30), ("PL:urban", 50), ("PL:rural", 90), ("walk", 5), ("none", None),
    ("signals", None), ("50 mph", None), ("20;30", 20), ("", None), (None, None), ("500", 140), ("1", 5),
])
def test_parse_maxspeed(raw, expected):
    assert parse_maxspeed(raw) == expected


def test_classify_returns_per_profile_attributes():
    c = classify(way("residential", name="Długa", oneway="yes", cycleway="opposite", maxspeed="30",
                     surface="asphalt", lit="yes", layer="1", bridge="yes"))
    assert c["car_dir"] == FORWARD and c["bike_dir"] == BOTH
    assert c["car_speed_kmh"] == 30 and c["bike_speed_kmh"] == 15
    assert (c["name"], c["surface"], c["lit"], c["layer"], c["bridge"], c["tunnel"]) == ("Długa", "asphalt", True, 1, True, False)


def test_classify_car_only_and_bike_only_ways():
    motorway = classify(way("motorway"))
    assert motorway["car_dir"] == FORWARD and motorway["bike_dir"] == NONE and motorway["bike_speed_kmh"] is None
    cycleway = classify(way("cycleway"))
    assert cycleway["car_dir"] == NONE and cycleway["car_speed_kmh"] is None and cycleway["bike_speed_kmh"] == 18


def test_classify_drops_ways_nobody_may_use():
    assert classify(way("steps")) is None
    assert classify(way("footway")) is None
    assert classify(way(access="no", highway="service")) is None
    assert classify(way("service", service="parking_aisle")) is None


def test_default_car_speed_is_used_without_maxspeed():
    assert classify(way("primary"))["car_speed_kmh"] == 50
    assert classify(way("living_street"))["car_speed_kmh"] == 10
    assert classify(way("residential", maxspeed="none"))["car_speed_kmh"] == 30
