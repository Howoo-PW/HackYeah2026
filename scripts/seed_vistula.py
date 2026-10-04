"""Seed demo ratings and comments for the roads along the Vistula (the "Bulwar ..." paths and Bulwarowa).

  python scripts/seed_vistula.py --dry-run   # what would be written
  python scripts/seed_vistula.py --apply     # replace this seed's rows (one transaction)
  python scripts/seed_vistula.py --remove    # delete this seed's rows

The riverside is found in the database itself: segments of the OSM ways named "Bulwar ..." (the embankment paths)
plus Bulwarowa, Do Wisły, Na Zakolu Wisły and the streets that run right by the embankment (Podgórska, Konopnickiej, ...). People like it: very nice views, calm, good surface, safe, hardly any
parking. Rows are tagged (ratings.seed_tag, comments.seed_tag), so they never touch real data, and running --apply again
replaces the previous batch. Needs SUPABASE_DB_URL (.env or environment). Deterministic (fixed random seed).
"""

import argparse
import datetime as dt
import random
from zoneinfo import ZoneInfo

import psycopg

from _common import database_url
from seed_zones import DIMS, clip, refresh

TAG = "vistula-2026-10"
SEED = 20261008
WARSAW = ZoneInfo("Europe/Warsaw")
MEANS = {"surface": 3.9, "views": 4.8, "safety": 4.0, "traffic": 4.6, "parking": 2.0}
SDS = {"surface": 0.6, "views": 0.3, "safety": 0.5, "traffic": 0.4, "parking": 0.6}
RATER_SD = 0.5
RATINGS_PER_SEGMENT = (2, 4)
COMMENT_SHARE = 0.45  # share of riverside segments that get a comment
BANDS = {"morning": (6, 10), "day": (10, 16), "evening": (16, 22)}
BAND_WEIGHTS = (2, 4, 4)

COMMENTS = [
    "Fajna droga wzdłuż Wisły, spokojnie i widok na wodę.",
    "Super miejsce na rower, prawie bez samochodów i ładnie nad rzeką.",
    "Najprzyjemniejszy odcinek w okolicy: woda, zieleń i cisza.",
    "Polecam wieczorem, zachód słońca nad Wisłą robi robotę.",
    "Równa nawierzchnia, jedzie się wygodnie, a widoki nad rzeką świetne.",
    "Fajny spacer wzdłuż rzeki, dużo ludzi z psami i rowerzystów, ale bez tłoku.",
    "Wzdłuż Wisły jest najładniej, szkoda tylko, że brakuje tu miejsc do zaparkowania.",
    "Bardzo spokojnie, można odpocząć od ruchu w centrum. Widok na Wawel z bulwaru jest super.",
    "Dobra trasa na poranny bieg, płasko i nad wodą.",
    "Trochę nierówności na kostce, ale cały odcinek nad rzeką wynagradza widokami.",
    "Rano prawie pusto, wieczorem robi się tłoczniej, ale nadal przyjemnie.",
    "Jedna z moich ulubionych tras rowerowych w Krakowie, zawsze wzdłuż Wisły.",
    "Czuję się tu bezpiecznie, jest jasno i dużo spacerowiczów.",
    "Ładna droga przy rzece, dobra na rodzinną przejażdżkę.",
    "Widoki na rzekę są najlepsze w mieście, polecam każdemu.",
    "W upalne dni tu jest najprzyjemniej, od wody wieje chłodniej.",
]

CORRIDOR_SQL = """
with bank as (
  select geom from public.osm_ways where name ilike 'Bulwar %%' and coalesce(bridge, 'no') = 'no'
), near as (  -- segments within ~25 m (0.0003 deg) and ~120 m (0.0015 deg) of the embankment paths, using the GiST index
  select s.id, s.name, s.highway, s.osm_way_id, st_centroid(s.geom) c,
         exists (select 1 from bank b where st_dwithin(s.geom, b.geom, 0.0003)) close_by,
         exists (select 1 from bank b where st_dwithin(s.geom, b.geom, 0.0015)) around
  from public.segments s
)
select id, st_x(c), st_y(c) from near
where name in ('Bulwarowa', 'Do Wisły', 'Na Zakolu Wisły')
   or osm_way_id in (select way_id from public.osm_ways where name ilike 'Bulwar %%' and coalesce(bridge, 'no') = 'no')
   or (close_by and coalesce(highway, '') in ('path', 'footway', 'cycleway', 'pedestrian', 'track', 'living_street'))
   or (around and name in ('Podgórska', 'Marii Konopnickiej', 'Nadwiślańska', 'Rybaki', 'Józefa Dietla'))
order by id
"""

INSERT_RATING = """
insert into public.ratings (segment_id, user_id, surface, views, safety, traffic, parking, time_of_day, rated_on, created_at, seed_tag)
values (%(segment_id)s, %(user_id)s, %(surface)s, %(views)s, %(safety)s, %(traffic)s, %(parking)s,
        %(time_of_day)s::public.time_of_day, %(rated_on)s, %(created_at)s, %(seed_tag)s)
on conflict (user_id, segment_id, rated_on) do nothing
"""

INSERT_COMMENT = """
insert into public.comments (segment_id, user_id, text, created_at, seed_tag)
values (%(segment_id)s, %(user_id)s, %(text)s, %(created_at)s, %(seed_tag)s)
"""


def plan(segments, user_ids, taken=frozenset()):
    """Ratings and comments for the riverside segments. `taken`: (user, segment) pairs with a real rating (skipped)."""
    rng = random.Random(SEED)
    today = dt.date(2026, 10, 8)
    ratings, comments = [], []
    texts = COMMENTS[:]
    for sid, _lon, _lat in segments:
        character = {d: rng.gauss(0, SDS[d]) for d in DIMS}
        free = [u for u in user_ids if (u, sid) not in taken]
        raters = rng.sample(free, min(len(free), rng.randint(*RATINGS_PER_SEGMENT)))
        for user in raters:
            band = rng.choices(list(BANDS), weights=BAND_WEIGHTS)[0]
            day = today - dt.timedelta(days=rng.randint(0, 30))
            h0, h1 = BANDS[band]
            local = dt.datetime.combine(day, dt.time(0), WARSAW) + dt.timedelta(hours=rng.uniform(h0, h1))
            dims = list(DIMS) if rng.random() < 0.75 else rng.sample(DIMS, rng.randint(2, 4))
            row = {d: clip(MEANS[d] + character[d] + rng.gauss(0, RATER_SD)) if d in dims else None for d in DIMS}
            ratings.append({"segment_id": sid, "user_id": user, **row, "time_of_day": band, "rated_on": local.date(), "created_at": local, "seed_tag": TAG})
        if raters and rng.random() < COMMENT_SHARE:
            if not texts:
                texts = COMMENTS[:]
            text = texts.pop(rng.randrange(len(texts)))
            local = dt.datetime.combine(today - dt.timedelta(days=rng.randint(0, 30)), dt.time(rng.randint(8, 21), rng.randint(0, 59)), WARSAW)
            comments.append({"segment_id": sid, "user_id": rng.choice(raters), "text": text, "created_at": local, "seed_tag": TAG})
    return ratings, comments


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--remove", action="store_true")
    args = parser.parse_args()
    url = database_url()
    with psycopg.connect(url, connect_timeout=15, autocommit=False) as conn:
        conn.execute("set local statement_timeout = '600s'")
        conn.execute("set local search_path = public, extensions")
        if args.remove:
            n_r = conn.execute("delete from public.ratings where seed_tag = %s", (TAG,)).rowcount
            n_c = conn.execute("delete from public.comments where seed_tag = %s", (TAG,)).rowcount
            refresh(conn)
            conn.commit()
            print(f"removed {n_r} ratings and {n_c} comments")
            return
        segments = conn.execute(CORRIDOR_SQL).fetchall()
        users = [r[0] for r in conn.execute("select id from public.profiles order by id")]
        taken = {(r[0], r[1]) for r in conn.execute("select user_id, segment_id from public.ratings where seed_tag is null")}
        ratings, comments = plan(segments, users, taken)
        print(f"riverside segments: {len(segments)}; planned: {len(ratings)} ratings, {len(comments)} comments")
        for c in comments[:5]:
            print(f"  e.g. segment {c['segment_id']}: {c['text']}")
        if not args.apply:
            return
        real_before = conn.execute("select (select count(*) from public.ratings where seed_tag is null), (select count(*) from public.comments where seed_tag is null)").fetchone()
        conn.execute("delete from public.ratings where seed_tag = %s", (TAG,))
        conn.execute("delete from public.comments where seed_tag = %s", (TAG,))
        with conn.cursor() as cur:
            cur.executemany(INSERT_RATING, ratings)
            cur.executemany(INSERT_COMMENT, comments)
        real_after = conn.execute("select (select count(*) from public.ratings where seed_tag is null), (select count(*) from public.comments where seed_tag is null)").fetchone()
        assert real_before == real_after, "real ratings and comments must not change"
        refresh(conn)
        conn.commit()
        n_r = conn.execute("select count(*) from public.ratings where seed_tag = %s", (TAG,)).fetchone()[0]
        print(f"committed: {n_r} ratings, {len(comments)} comments; real data untouched")


if __name__ == "__main__":
    main()
