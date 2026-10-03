-- Raw routing network from OSM for cars and bikes: every way either profile may use, with the
-- direction each may travel it, speeds, and the OSM node ids. It is the input of the graph
-- (B2 cuts ways into edges at shared nodes); public.segments stays as it is, because ratings
-- and groups hang on its ids. Join with segments through segments.osm_way_id = osm_ways.way_id.
-- Loaded by scripts/load_osm_routing.py (not committed as a seed: tens of MB).

create table public.osm_ways (
  way_id bigint primary key,
  highway text not null,
  name text,
  oneway text,                 -- raw tag
  junction text,               -- raw tag, e.g. roundabout
  car_dir text not null check (car_dir in ('both', 'forward', 'backward', 'none')),
  bike_dir text not null check (bike_dir in ('both', 'forward', 'backward', 'none')),
  -- forward = along geom, backward = against it
  car_speed_kmh smallint,
  bike_speed_kmh smallint,
  maxspeed smallint,
  surface text,
  smoothness text,
  lit boolean,
  bridge boolean not null default false,
  tunnel boolean not null default false,
  layer smallint,
  node_ids bigint[] not null,  -- OSM node id of every vertex of geom, same order
  geom extensions.geometry(LineString, 4326) not null,
  length_m real not null,
  tags jsonb not null          -- all raw OSM tags, for anything not modelled above
);
create index osm_ways_geom_idx on public.osm_ways using gist (geom);
create index osm_ways_highway_idx on public.osm_ways (highway);
create index osm_ways_car_idx on public.osm_ways (way_id) where car_dir <> 'none';
create index osm_ways_bike_idx on public.osm_ways (way_id) where bike_dir <> 'none';

-- Internal input data: no access through the public API (the backend and B2 use the postgres role).
alter table public.osm_ways enable row level security;
revoke all on public.osm_ways from anon, authenticated;
