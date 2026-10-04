"""OSM tag interpretation for car, bike and pedestrian routing."""

import pytest

from app.osm_access import (BACKWARD, BOTH, FORWARD, NONE, bike_direction, car_direction, classify, foot_direction,
                            parse_maxspeed)


def way(highway="residential", **tags):
    return {"highway": highway, **{k.replace("__", ":"): v for k, v in tags.items()}}


@pytest.mark.parametrize("tags,expected", [
    (way(), BOTH),
    (way(oneway="yes"), FORWARD),
    (way(oneway="-1"), BACKWARD),
    (way(oneway="no"), BOTH),
    (way(oneway="reversible"), NONE),
    (way("motorway"), FORWARD),                       # implied one-way
    (way(junction="roundabout"), FORWARD),
    (way(junction="roundabout", oneway="no"), BOTH),
])
def test_car_direction(tags, expected):
    assert car_direction(tags) == expected


@pytest.mark.parametrize("tags", [
    way("footway"), way(access="no"), way(motorcar="private"),
    way("service", service="parking_aisle"), way(area="yes"),
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
    (way(oneway="yes"), FORWARD),                                        # bikes follow the street ...
    (way(oneway="yes", oneway__bicycle="no"), BOTH),                     # ... unless explicitly exempt
    (way(oneway="yes", cycleway="opposite_lane"), BOTH),                 # contraflow lane
    (way(oneway="yes", cycleway__right="lane"), FORWARD),                # an ordinary lane is not contraflow
    (way(junction="roundabout"), FORWARD),
    (way("path", bicycle="designated"), BOTH),
])
def test_bike_direction(tags, expected):
    assert bike_direction(tags) == expected


@pytest.mark.parametrize("tags", [
    way("motorway"), way("steps"), way("footway"),
    way(bicycle="no"), way(bicycle="dismount"), way(access="no"),
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
    ("50", 50), ("PL:urban", 50), ("walk", 5), ("none", None),
    ("50 mph", None), ("20;30", 20), ("", None), (None, None), ("500", 140), ("1", 5),
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
    assert classify(way("footway", footway="sidewalk")) is None  # sidewalks are not modelled
    assert classify(way("footway", footway="crossing")) is None
    assert classify(way(access="no", highway="service")) is None
    assert classify(way("service", service="parking_aisle")) is None


# --- pedestrians ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("tags", [
    way(), way("primary"), way("pedestrian"), way("path"), way("footway"),
    way(oneway="yes"), way(oneway="-1"), way(junction="roundabout"),  # one-way streets and roundabouts do not bind walkers
])
def test_pedestrians_walk_roads_in_both_directions(tags):
    assert foot_direction(tags) == BOTH


@pytest.mark.parametrize("tags,expected", [
    (way(oneway__foot="yes"), FORWARD), (way(oneway__foot="no", oneway="yes"), BOTH),
])
def test_explicit_foot_oneway_is_respected(tags, expected):
    assert foot_direction(tags) == expected


@pytest.mark.parametrize("tags", [
    way("motorway"), way("cycleway"), way("steps"), way(foot="no"), way(access="private"),
    way("footway", footway="sidewalk"), way("footway", footway="crossing"),
    way("service", service="parking_aisle"), way(area="yes"),
])
def test_pedestrians_cannot_use(tags):
    assert foot_direction(tags) == NONE


def test_foot_exceptions_to_the_defaults():
    assert foot_direction(way("cycleway", foot="designated")) == BOTH   # a bike path shared with walkers
    assert foot_direction(way("cycleway", foot="yes")) == BOTH
    assert foot_direction(way("trunk", foot="yes")) == BOTH
    assert foot_direction(way(access="no", foot="yes")) == BOTH          # the specific tag beats the general one
    assert foot_direction(way(access="yes", foot="no")) == NONE
    assert foot_direction(way("motorway", foot="yes")) == NONE           # never


def test_classify_gives_pedestrian_attributes():
    street = classify(way("residential", oneway="yes", maxspeed="30"))
    assert street["foot_dir"] == BOTH and street["foot_speed_kmh"] == 5 and street["car_dir"] == FORWARD
    bike_path = classify(way("cycleway"))
    assert bike_path["foot_dir"] == NONE and bike_path["foot_speed_kmh"] is None
    alley = classify(way("footway"))  # only pedestrians: a way that cars and bikes may not use is still kept
    assert (alley["car_dir"], alley["bike_dir"], alley["foot_dir"], alley["foot_speed_kmh"]) == (NONE, NONE, BOTH, 5)
    motorway = classify(way("motorway"))
    assert motorway["car_dir"] == FORWARD and motorway["foot_dir"] == NONE


def test_default_car_speed_is_used_without_maxspeed():
    assert classify(way("primary"))["car_speed_kmh"] == 50
    assert classify(way("living_street"))["car_speed_kmh"] == 10
    assert classify(way("residential", maxspeed="none"))["car_speed_kmh"] == 30
