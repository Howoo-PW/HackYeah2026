"""OSM tags -> routing attributes for cars, bikes and pedestrians (pure functions, no I/O).

Used by scripts/load_osm_routing.py to fill public.osm_ways. For each way it answers, per
profile, in which direction the way may be travelled and how fast, following the common OSM
routing conventions (access hierarchy, oneway, roundabouts, bike contraflow; pedestrians walk
the road network in both directions and sidewalks are not modelled). Anything this
does not model (turn restrictions, barriers, time-based access) is left out on purpose and
can be derived later from the raw `tags` column.
"""

FORWARD, BACKWARD, BOTH, NONE = "forward", "backward", "both", "none"

CAR_HIGHWAYS = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
    "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street", "service",
}
# Roads a bike may use unless tagged otherwise.
BIKE_HIGHWAYS = {
    "primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "cycleway", "path", "track",
}
# Only with an explicit bicycle=yes|designated|permissive.
BIKE_IF_ALLOWED = {"trunk", "trunk_link", "footway", "pedestrian"}

# Pedestrians are routed on the road network, not on sidewalks (a team decision): any ordinary road, pedestrian
# street, path or track, unless tagged otherwise.
FOOT_HIGHWAYS = {
    "primary", "primary_link", "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "pedestrian", "path", "track", "footway",
}
# Only with an explicit foot=yes|designated|permissive (a bike path shared with pedestrians; a trunk road with a footpath).
FOOT_IF_ALLOWED = {"cycleway", "trunk", "trunk_link"}
# Sidewalks and crossings are not modelled: the road they belong to stands for them.
NOT_MODELLED_FOOTWAYS = {"sidewalk", "crossing"}
FOOT_SPEED_KMH = 5

BLOCKING = {"no", "private", "customers", "delivery", "agricultural", "forestry", "military", "permit"}
ALLOWING = {"yes", "designated", "permissive", "destination"}
SKIPPED_SERVICE = {"parking_aisle", "driveway", "emergency_access", "drive-through"}

CAR_SPEED = {
    "motorway": 100, "motorway_link": 50, "trunk": 70, "trunk_link": 50, "primary": 50, "primary_link": 40,
    "secondary": 50, "secondary_link": 40, "tertiary": 40, "tertiary_link": 30, "unclassified": 40,
    "residential": 30, "living_street": 10, "service": 20,
}
BIKE_SPEED = {"cycleway": 18, "path": 12, "track": 12, "footway": 8, "pedestrian": 8}
BIKE_DEFAULT_SPEED = 15


def _access(tags: dict, keys: tuple[str, ...]) -> bool:
    """Most specific access tag wins; no tag means open."""
    for key in keys:
        value = tags.get(key)
        if value in ALLOWING:
            return True
        if value in BLOCKING or value == "dismount":
            return False
    return True


def _oneway(tags: dict, key: str = "oneway") -> str | None:
    value = tags.get(key)
    if value in ("yes", "true", "1"):
        return FORWARD
    if value in ("-1", "reverse"):
        return BACKWARD
    if value in ("no", "false", "0"):
        return BOTH
    if value in ("reversible", "alternating"):
        return NONE  # direction depends on the time of day: not routable
    return None


def _default_direction(tags: dict) -> str:
    """Implied direction when oneway is not tagged."""
    if tags.get("junction") in ("roundabout", "circular") or tags.get("highway") in ("motorway", "motorway_link"):
        return FORWARD
    return BOTH


def car_direction(tags: dict) -> str:
    highway = tags.get("highway")
    if highway not in CAR_HIGHWAYS or tags.get("area") == "yes":
        return NONE
    if highway == "service" and tags.get("service") in SKIPPED_SERVICE:
        return NONE
    if not _access(tags, ("motorcar", "motor_vehicle", "vehicle", "access")):
        return NONE
    return _oneway(tags) or _default_direction(tags)


def bike_direction(tags: dict) -> str:
    highway = tags.get("highway")
    bicycle_allowed = tags.get("bicycle") in ALLOWING
    if highway not in BIKE_HIGHWAYS and not (highway in BIKE_IF_ALLOWED and bicycle_allowed):
        return NONE
    if tags.get("area") == "yes":
        return NONE
    if highway == "service" and tags.get("service") in SKIPPED_SERVICE:
        return NONE
    if not _access(tags, ("bicycle", "vehicle", "access")):
        return NONE
    explicit = _oneway(tags, "oneway:bicycle")
    if explicit is not None:
        return explicit
    direction = _oneway(tags) or _default_direction(tags)
    opposite = any(str(tags.get(k, "")).startswith("opposite") for k in
                   ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both"))
    if direction in (FORWARD, BACKWARD) and opposite:
        return BOTH  # bikes may ride against a one-way street
    return direction


def foot_direction(tags: dict) -> str:
    """Direction a pedestrian may walk a way. One-way streets do not bind pedestrians, so it is BOTH unless
    `oneway:foot` says otherwise; ways closed to pedestrians (foot=no, private access) and ways that are
    sidewalks or crossings are NONE."""
    highway = tags.get("highway")
    foot_allowed = tags.get("foot") in ALLOWING
    if highway not in FOOT_HIGHWAYS and not (highway in FOOT_IF_ALLOWED and foot_allowed):
        return NONE
    if tags.get("area") == "yes":
        return NONE
    if highway == "footway" and tags.get("footway") in NOT_MODELLED_FOOTWAYS:
        return NONE
    if highway == "service" and tags.get("service") in SKIPPED_SERVICE:
        return NONE
    if not _access(tags, ("foot", "access")):
        return NONE
    return _oneway(tags, "oneway:foot") or BOTH


def parse_maxspeed(raw: str | None) -> int | None:
    """km/h from a maxspeed tag; conditional and symbolic values (none, signals) give None."""
    if not raw:
        return None
    raw = raw.strip().lower()
    symbolic = {"pl:urban": 50, "pl:rural": 90, "pl:motorway": 140, "pl:expressway": 120, "walk": 5}
    if raw in symbolic:
        return symbolic[raw]
    digits = raw.split(";")[0].split(" ")[0]
    if digits.isdigit() and "mph" not in raw:
        return min(max(int(digits), 5), 140)
    return None


def _flag(tags: dict, key: str) -> bool:
    return tags.get(key) not in (None, "no")


def _int(value) -> int | None:
    try:
        return int(str(value).split(";")[0])
    except (TypeError, ValueError):
        return None


def classify(tags: dict) -> dict | None:
    """Routing attributes of one way, or None when no profile (car, bike, foot) may use it."""
    car, bike, foot = car_direction(tags), bike_direction(tags), foot_direction(tags)
    if car == NONE and bike == NONE and foot == NONE:
        return None
    highway = tags["highway"]
    maxspeed = parse_maxspeed(tags.get("maxspeed"))
    return {
        "highway": highway,
        "name": tags.get("name"),
        "oneway": tags.get("oneway"),
        "junction": tags.get("junction"),
        "car_dir": car,
        "bike_dir": bike,
        "car_speed_kmh": None if car == NONE else (maxspeed or CAR_SPEED[highway]),
        "bike_speed_kmh": None if bike == NONE else BIKE_SPEED.get(highway, BIKE_DEFAULT_SPEED),
        "foot_dir": foot,
        "foot_speed_kmh": None if foot == NONE else FOOT_SPEED_KMH,
        "maxspeed": maxspeed,
        "surface": tags.get("surface"),
        "smoothness": tags.get("smoothness"),
        "lit": {"yes": True, "no": False}.get(tags.get("lit")),
        "bridge": _flag(tags, "bridge"),
        "tunnel": _flag(tags, "tunnel"),
        "layer": _int(tags.get("layer")),
    }
