"""Segment groups and effective scores.

OSM cuts roads at every junction, so half of the segments are shorter than 100 m and nobody
rates them. Two pure helpers fix that without touching segment ids or stored ratings:

- `build_groups` merges consecutive segments of one street into groups of about GROUP_TARGET_M
  (offline, run by scripts/build_segment_groups.py; its output is the seed in supabase/seed/).
- `effective_scores` gives every segment a score even when only its neighbours were rated, by
  shrinking its own ratings toward the group mean and the group mean toward the road-type mean.
"""

from collections import defaultdict
from dataclasses import dataclass

DIMENSIONS = ("surface", "views", "safety", "traffic", "parking")

GROUP_TARGET_M = 500.0
# A group is cut at junction-free segment borders into n = round(total / target) equal parts.

K_SEGMENT = 2.0  # own ratings needed to weigh as much as the group mean
K_GROUP = 3.0    # group ratings needed to weigh as much as the road-type mean

HIGHWAY_RANK = {"primary": 0, "secondary": 1, "tertiary": 2, "unclassified": 3, "residential": 4, "cycleway": 5}


@dataclass(frozen=True)
class SegmentRow:
    id: int
    osm_way_id: int
    name: str | None
    highway: str
    length_m: float
    start: tuple[float, float]  # rounded lon, lat
    end: tuple[float, float]


@dataclass
class Group:
    id: int
    name: str | None
    highway: str
    length_m: float
    segment_ids: list[int]
    from_street: str | None
    to_street: str | None


def _same_street(a: SegmentRow, b: SegmentRow, pieces_at_node: int) -> bool:
    """Named segments belong to one street when name and road type match.

    Unnamed ones (connectors, cycleways) merge within one OSM way, or across ways when nothing
    else meets at the node: a plain continuation of the same road type.
    """
    if a.name or b.name:
        return a.name == b.name and a.highway == b.highway
    return a.osm_way_id == b.osm_way_id or (a.highway == b.highway and pieces_at_node == 2)


def _links(segs: list[SegmentRow]):
    """Link two segments at a node when each is the only same-street neighbour of the other there.

    A node with two or more same-street neighbours (dual carriageways, a street forking) is a
    real junction of that street and is never merged across.
    """
    at_node: dict[tuple, list[int]] = defaultdict(list)
    for s in segs:
        at_node[s.start].append(s.id)
        at_node[s.end].append(s.id)
    by_id = {s.id: s for s in segs}
    link: dict[tuple[int, tuple], int] = {}
    for node, ids in at_node.items():
        if len(ids) != len(set(ids)):  # a closed loop touches the node twice: leave it alone
            continue
        same = {i: [j for j in ids if j != i and _same_street(by_id[i], by_id[j], len(ids))] for i in ids}
        for i, others in same.items():
            if len(others) == 1 and same[others[0]] == [i]:
                link[(i, node)] = others[0]
    return at_node, link


def _chains(segs: list[SegmentRow], link):
    """Order linked segments into paths; yields (segments in order, node sequence along the path)."""
    by_id = {s.id: s for s in segs}
    seen: set[int] = set()

    def walk(first: SegmentRow, entry, exit_):
        order, nodes, cur, node = [first], [entry, exit_], first, exit_
        seen.add(first.id)
        while (cur.id, node) in link:
            nxt = by_id[link[(cur.id, node)]]
            if nxt.id in seen:
                break
            seen.add(nxt.id)
            other = nxt.end if nxt.start == node else nxt.start
            order.append(nxt)
            nodes.append(other)
            cur, node = nxt, other
        return order, nodes

    def degree(s):
        return ((s.id, s.start) in link) + ((s.id, s.end) in link)

    for s in sorted(segs, key=lambda s: (degree(s), s.id)):  # path ends first, cycles last
        if s.id in seen:
            continue
        ls, le = (s.id, s.start) in link, (s.id, s.end) in link
        entry, exit_ = (s.end, s.start) if ls and not le else (s.start, s.end)
        yield walk(s, entry, exit_)


def _street_at(node, owner: SegmentRow, at_node, by_id) -> str | None:
    """Name of the most important other street meeting at `node`."""
    others = [by_id[i] for i in at_node[node] if i != owner.id and by_id[i].name and by_id[i].name != owner.name]
    if not others:
        return None
    best = min(others, key=lambda o: (HIGHWAY_RANK.get(o.highway, 9), o.name))
    return best.name


def build_groups(segs: list[SegmentRow], target_m: float = GROUP_TARGET_M) -> list[Group]:
    """Deterministic grouping: same input, same ids."""
    at_node, link = _links(segs)
    by_id = {s.id: s for s in segs}
    pieces: list[Group] = []
    for order, nodes in _chains(segs, link):
        total = sum(s.length_m for s in order)
        n = max(1, round(total / target_m))
        size, done = total / n, 0.0
        parts: list[list[int]] = [[] for _ in range(n)]
        for i, s in enumerate(order):
            parts[min(n - 1, int((done + s.length_m / 2) / size))].append(i)
            done += s.length_m
        for idx in (p for p in parts if p):
            first, last = order[idx[0]], order[idx[-1]]
            pieces.append(Group(
                id=0, name=first.name, highway=first.highway,
                length_m=round(sum(order[i].length_m for i in idx), 1),
                segment_ids=[order[i].id for i in idx],
                from_street=_street_at(nodes[idx[0]], first, at_node, by_id),
                to_street=_street_at(nodes[idx[-1] + 1], last, at_node, by_id),
            ))
    pieces.sort(key=lambda g: min(g.segment_ids))
    for gid, g in enumerate(pieces, start=1):
        g.id = gid
    return pieces


# --- fragments: rating units of 300-700 m ------------------------------------------------------

IMPORTANT_HIGHWAYS = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link",
}
FRAGMENT_MIN_M = 300.0        # shorter pieces are merged into a neighbour
FRAGMENT_MAX_M = 700.0        # a street is cut at the latest here, important junction or not
FRAGMENT_MERGE_MAX_M = 900.0  # a merge never creates a fragment longer than this


def _split_chain(order, nodes, important_at, min_m, max_m):
    """(lo, hi) index ranges of one chain's pieces.

    A chain is cut at a junction with an *important* road (primary, secondary, tertiary) once the
    piece has min_m, so fragments end where a driver would say the street changes character;
    minor side streets never cut. A piece is also cut when adding the next segment would pass max_m.
    """
    chain_ids = {s.id for s in order}
    pieces, lo, cur = [], 0, 0.0
    for i, s in enumerate(order):
        if i > lo:
            important_here = bool(important_at.get(nodes[i], set()) - chain_ids)
            if (cur >= min_m and important_here) or cur + s.length_m > max_m:
                pieces.append((lo, i))
                lo, cur = i, 0.0
        cur += s.length_m
    pieces.append((lo, len(order)))
    return pieces


def _dominant(segs, key):
    """The value of `key` carrying the most road length; named streets win over unnamed ones."""
    weight: dict = defaultdict(float)
    for s in segs:
        weight[key(s)] += s.length_m
    named = {k: w for k, w in weight.items() if k is not None}
    pool = named or weight
    return max(sorted(pool, key=lambda k: str(k)), key=lambda k: pool[k])


def build_fragments(
    segs: list[SegmentRow],
    neighbors: dict[int, set[int]],
    important_at: dict[tuple, set[int]],
    min_m: float = FRAGMENT_MIN_M,
    max_m: float = FRAGMENT_MAX_M,
    merge_max_m: float = FRAGMENT_MERGE_MAX_M,
) -> list[Group]:
    """Group segments into rating fragments of min_m..max_m.

    1. Chains of one street (same name and road type) are cut at important junctions.
    2. Every fragment shorter than min_m is merged into an adjacent fragment, preferring the same
       road type and then the shortest neighbour, as long as the result stays below merge_max_m.
    `neighbors` maps a segment to the segments it touches (an end of one lies on the other);
    `important_at` maps a node to the ids of important-road segments passing through it.
    Fragments with nothing to merge into (isolated short roads) stay short.
    """
    at_node, link = _links(segs)
    by_id = {s.id: s for s in segs}
    pieces: list[dict] = []
    for order, nodes in _chains(segs, link):
        for lo, hi in _split_chain(order, nodes, important_at, min_m, max_m):
            members = order[lo:hi]
            pieces.append({
                "segs": list(members), "len": sum(s.length_m for s in members),
                "from": _street_at(nodes[lo], members[0], at_node, by_id),
                "to": _street_at(nodes[hi], members[-1], at_node, by_id),
            })

    piece_of = {s.id: k for k, p in enumerate(pieces) for s in p["segs"]}
    alive = set(range(len(pieces)))

    def touching(k):
        return {piece_of[j] for s in pieces[k]["segs"] for j in neighbors.get(s.id, ()) if j in piece_of} - {k}

    def highway(k):
        return _dominant(pieces[k]["segs"], lambda s: s.highway)

    def street(k):
        return _dominant(pieces[k]["segs"], lambda s: s.name), highway(k)

    # Two passes: first only a neighbour that is the same street (so the tail of a street goes
    # back to its own street), then any neighbour. Otherwise a foreign stub could take the room.
    for same_street_only in (True, False):
        changed = True
        while changed:
            changed = False
            for k in sorted((k for k in alive if pieces[k]["len"] < min_m), key=lambda k: (pieces[k]["len"], k)):
                if k not in alive or pieces[k]["len"] >= min_m:
                    continue
                candidates = [n for n in touching(k) if pieces[n]["len"] + pieces[k]["len"] <= merge_max_m]
                if same_street_only:
                    name_k, hw_k = street(k)
                    candidates = [n for n in candidates if name_k is not None and street(n) == (name_k, hw_k)]
                if not candidates:
                    continue
                hw = highway(k)
                best = min(candidates, key=lambda n: (highway(n) != hw, pieces[n]["len"], n))
                pieces[best]["segs"] += pieces[k]["segs"]
                pieces[best]["len"] += pieces[k]["len"]
                pieces[best]["from"] = pieces[best]["to"] = None  # a merged fragment has no single start and end
                for s in pieces[k]["segs"]:
                    piece_of[s.id] = best
                alive.discard(k)
                changed = True

    groups = []
    for k in sorted(alive):
        p = pieces[k]
        segs_k = p["segs"]
        groups.append(Group(
            id=0, name=_dominant(segs_k, lambda s: s.name), highway=_dominant(segs_k, lambda s: s.highway),
            length_m=round(p["len"], 1), segment_ids=sorted(s.id for s in segs_k),
            from_street=p["from"], to_street=p["to"],
        ))
    groups.sort(key=lambda g: min(g.segment_ids))
    for gid, g in enumerate(groups, start=1):
        g.id = gid
    return groups


# --- effective scores -------------------------------------------------------------------------

Agg = dict  # {dimension: (count, sum)}


def _mean(count: int, total: float) -> float | None:
    return total / count if count else None


def group_scores(group: Agg, highway: Agg) -> dict[str, float | None]:
    """Group mean per dimension, pulled toward the road-type mean while the group has few ratings."""
    out: dict[str, float | None] = {}
    for d in DIMENSIONS:
        gn, gs = group.get(d, (0, 0.0))
        prior = _mean(*highway.get(d, (0, 0.0)))
        if not gn:
            out[d] = None
        elif prior is None:
            out[d] = round(gs / gn, 2)
        else:
            out[d] = round((gs + K_GROUP * prior) / (gn + K_GROUP), 2)
    return out


def effective_scores(own: Agg, group: Agg, highway: Agg):
    """Return (scores, source, confidence) for one segment.

    own/group/highway map a dimension to (ratings count, sum of ratings); `group` includes the
    segment's own ratings, which are taken out so they are not counted twice.
    """
    scores: dict[str, float | None] = {}
    evidence = 0.0
    has_own = False
    for d in DIMENSIONS:
        on, os_ = own.get(d, (0, 0.0))
        gn, gs = group.get(d, (0, 0.0))
        rest_n, rest_s = max(gn - on, 0), max(gs - os_, 0.0)
        prior = _mean(*highway.get(d, (0, 0.0)))
        rest_mean = None
        if rest_n:
            rest_mean = (rest_s + K_GROUP * prior) / (rest_n + K_GROUP) if prior is not None else rest_s / rest_n
        if on:
            has_own = True
            base = rest_mean if rest_mean is not None else (prior if prior is not None else os_ / on)
            scores[d] = round((os_ + K_SEGMENT * base) / (on + K_SEGMENT), 2)
        else:
            scores[d] = round(rest_mean, 2) if rest_mean is not None else None
        evidence = max(evidence, on + 0.5 * rest_n)
    if all(v is None for v in scores.values()):
        return scores, "none", "none"
    confidence = "high" if evidence >= 5 else "medium" if evidence >= 2 else "low"
    return scores, "own" if has_own else "group", confidence
