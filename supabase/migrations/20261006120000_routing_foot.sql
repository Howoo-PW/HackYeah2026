-- Pedestrians in the own routing graph ('foot-walking'), on the road network (sidewalks are not modelled).
--
-- Same design as cars and bikes: per-profile direction (`foot_dir`, always both ways unless tagged) and speed on
-- osm_ways -> routing_edges, travel time `foot_t` in routing_graph, the largest strongly connected component
-- `foot_main` in routing_nodes, and the profile in find_route() / routing_snap(). The tag rules live in
-- backend/app/osm_access.py (foot_direction); scripts/load_osm_foot.py fills foot_dir for the ways already in
-- osm_ways and adds the pedestrian streets that cars and bikes do not use. After both: select * from rebuild_routing();

alter table public.osm_ways
  add column foot_dir text not null default 'none' check (foot_dir in ('both', 'forward', 'backward', 'none')),
  add column foot_speed_kmh smallint;
create index osm_ways_foot_idx on public.osm_ways (way_id) where foot_dir <> 'none';

alter table public.routing_edges
  add column foot_dir text not null default 'none' check (foot_dir in ('both', 'forward', 'backward', 'none')),
  add column foot_speed_kmh smallint;

alter table public.routing_nodes add column foot_main boolean not null default false;
create index routing_nodes_foot_idx on public.routing_nodes using gist (geom) where foot_main;

-- routing_graph gets two columns: a materialized view cannot be altered, so it is recreated (nothing depends on it).
drop materialized view public.routing_graph;
create materialized view public.routing_graph as
select e.id, e.source, e.target, e.length_m, e.cx, e.cy, e.x1, e.y1, e.x2, e.y2,
  e.car_dir, e.bike_dir, e.foot_dir,
  case when e.car_dir <> 'none' then e.length_m / (greatest(coalesce(e.car_speed_kmh, 30), 5) / 3.6) end::real as car_t,
  case when e.bike_dir <> 'none' then e.length_m / (greatest(coalesce(e.bike_speed_kmh, 15), 5) / 3.6) end::real as bike_t,
  case when e.foot_dir <> 'none' then e.length_m / (greatest(coalesce(e.foot_speed_kmh, 5), 3) / 3.6) end::real as foot_t,
  d.surface, d.views, d.safety, d.traffic, d.parking, d.rated
from public.routing_edges e
join public.routing_edge_dims d on d.edge_id = e.id;
create unique index routing_graph_pk on public.routing_graph (id);
revoke all on public.routing_graph from anon, authenticated;

-- Topology build with the third profile. The result gets a column, so both functions are recreated.
drop function public.rebuild_routing();
drop function public.rebuild_routing_graph();

create function public.rebuild_routing_graph()
returns table (edges bigint, nodes bigint, car_main_share numeric, bike_main_share numeric, foot_main_share numeric)
language plpgsql
set search_path = public, extensions
as $$
declare
  v_profile text;
begin
  perform set_config('statement_timeout', '0', true);
  truncate public.routing_edges restart identity;
  truncate public.routing_nodes;

  insert into public.routing_edges
    (way_id, source, target, highway, surface, smoothness, lit, car_dir, bike_dir, foot_dir,
     car_speed_kmh, bike_speed_kmh, foot_speed_kmh, length_m, geom)
  with pts as (
    select w.way_id, u.node_id, u.n
    from public.osm_ways w, unnest(w.node_ids) with ordinality as u(node_id, n)
  ), junction as (
    select node_id from pts group by node_id having count(distinct way_id) > 1
  ), cuts as (
    select p.way_id, p.n, p.node_id
    from pts p
    join public.osm_ways w on w.way_id = p.way_id
    where p.n = 1 or p.n = cardinality(w.node_ids) or p.node_id in (select node_id from junction)
  ), pairs as (
    select way_id, node_id as source, n as n1,
      lead(node_id) over (partition by way_id order by n) as target,
      lead(n) over (partition by way_id order by n) as n2
    from cuts
  )
  select w.way_id, p.source, p.target, w.highway, w.surface, w.smoothness, w.lit, w.car_dir, w.bike_dir, w.foot_dir,
    w.car_speed_kmh, w.bike_speed_kmh, w.foot_speed_kmh,
    st_length(g.geom::geography)::real, g.geom
  from pairs p
  join public.osm_ways w on w.way_id = p.way_id
  cross join lateral (
    select st_makeline(array_agg(st_pointn(w.geom, i) order by i)) as geom
    from generate_series(p.n1::integer, p.n2::integer) as i
  ) g
  where p.target is not null and p.source <> p.target
    and (w.car_dir <> 'none' or w.bike_dir <> 'none' or w.foot_dir <> 'none');

  update public.routing_edges e
  set segment_id = (
    select s.id from public.segments s
    where s.osm_way_id = e.way_id
    order by s.geom <-> st_lineinterpolatepoint(e.geom, 0.5)
    limit 1
  );

  insert into public.routing_nodes (id, geom)
  select distinct on (id) id, geom from (
    select source as id, st_startpoint(geom) as geom from public.routing_edges
    union all
    select target, st_endpoint(geom) from public.routing_edges
  ) x;

  -- Largest strongly connected component per profile: the nodes find_route() may snap to.
  foreach v_profile in array array['car', 'bike', 'foot'] loop
    execute format($q$
      update public.routing_nodes n set %1$s_main = true
      where n.id in (
        with comp as (
          select * from extensions.pgr_strongcomponents(
            'select id, source, target,
               case when %1$s_dir in (''both'', ''forward'') then 1 else -1 end as cost,
               case when %1$s_dir in (''both'', ''backward'') then 1 else -1 end as reverse_cost
             from public.routing_edges where %1$s_dir <> ''none'''
          )
        ), big as (
          select component from comp group by component order by count(*) desc limit 1
        )
        select node from comp where component in (select component from big)
      )$q$, v_profile);
  end loop;

  analyze public.routing_edges;
  analyze public.routing_nodes;

  return query
  select (select count(*) from public.routing_edges),
    (select count(*) from public.routing_nodes),
    round((100 * coalesce(sum(e.length_m) filter (where e.car_dir <> 'none' and sn.car_main), 0)
      / nullif(sum(e.length_m) filter (where e.car_dir <> 'none'), 0))::numeric, 1),
    round((100 * coalesce(sum(e.length_m) filter (where e.bike_dir <> 'none' and sn.bike_main), 0)
      / nullif(sum(e.length_m) filter (where e.bike_dir <> 'none'), 0))::numeric, 1),
    round((100 * coalesce(sum(e.length_m) filter (where e.foot_dir <> 'none' and sn.foot_main), 0)
      / nullif(sum(e.length_m) filter (where e.foot_dir <> 'none'), 0))::numeric, 1)
  from public.routing_edges e
  join public.routing_nodes sn on sn.id = e.source;
end;
$$;
revoke execute on function public.rebuild_routing_graph() from public, anon, authenticated;

create function public.rebuild_routing()
returns table (edges bigint, nodes bigint, car_main_share numeric, bike_main_share numeric, foot_main_share numeric)
language plpgsql
set search_path = public, extensions
as $$
begin
  perform set_config('statement_timeout', '0', true);
  return query select * from public.rebuild_routing_graph();
  perform public.routing_prepare_edges();
  refresh materialized view public.routing_graph;
end;
$$;
revoke execute on function public.rebuild_routing() from public, anon, authenticated;

-- 'foot-walking' next to the two other profiles.
create or replace function public.routing_snap(p_profile text, p_lon double precision, p_lat double precision)
returns table (node_id bigint, distance_m double precision)
language plpgsql stable
set search_path = public, extensions
as $$
declare
  v_pf text;
  v_pt extensions.geometry := st_setsrid(st_makepoint(p_lon, p_lat), 4326);
begin
  if p_profile = 'driving-car' then v_pf := 'car';
  elsif p_profile = 'cycling-regular' then v_pf := 'bike';
  elsif p_profile = 'foot-walking' then v_pf := 'foot';
  else raise exception 'unsupported profile: %', p_profile using errcode = '22023';
  end if;

  return query execute format(
    'select id, st_distance(geom::geography, $1::geography) from public.routing_nodes
     where %s_main order by geom <-> $1 limit 1', v_pf)
    using v_pt;
end;
$$;

create or replace function public.find_route(
  p_profile text,
  p_from_lon double precision, p_from_lat double precision,
  p_to_lon double precision, p_to_lat double precision,
  p_w_surface integer default 0, p_w_views integer default 0, p_w_safety integer default 0,
  p_w_traffic integer default 0, p_w_parking integer default 0,
  p_strength double precision default null   -- null: 8 for cars, 3 for bikes and pedestrians
)
returns table (
  seq integer, edge_id bigint, way_id bigint, segment_id integer, forward boolean,
  length_m real, time_s double precision,
  surface real, views real, safety real, traffic real, parking real, rated boolean,
  geom extensions.geometry(LineString, 4326)
)
language plpgsql stable
set search_path = public, extensions
as $$
declare
  v_pf text;
  w_s integer := greatest(0, least(3, coalesce(p_w_surface, 0)));
  w_v integer := greatest(0, least(3, coalesce(p_w_views, 0)));
  w_f integer := greatest(0, least(3, coalesce(p_w_safety, 0)));
  w_t integer := greatest(0, least(3, coalesce(p_w_traffic, 0)));
  w_p integer := greatest(0, least(3, coalesce(p_w_parking, 0)));
  v_wsum integer;
  v_wmax integer;
  v_mult text;
  v_src bigint;
  v_dst bigint;
  v_from extensions.geometry := st_setsrid(st_makepoint(p_from_lon, p_from_lat), 4326);
  v_to extensions.geometry := st_setsrid(st_makepoint(p_to_lon, p_to_lat), 4326);
  v_margin double precision;
  v_sql text;
  v_attempt integer;
  v_strength double precision;
begin
  if p_profile = 'driving-car' then v_pf := 'car'; v_strength := coalesce(p_strength, 8);
  elsif p_profile = 'cycling-regular' then v_pf := 'bike'; v_strength := coalesce(p_strength, 3);
  elsif p_profile = 'foot-walking' then v_pf := 'foot'; v_strength := coalesce(p_strength, 3);
  else raise exception 'unsupported profile: %', p_profile using errcode = '22023';
  end if;

  v_wsum := w_s + w_v + w_f + w_t + w_p;
  v_wmax := greatest(w_s, w_v, w_f, w_t, w_p);
  if v_wsum = 0 then
    v_mult := '1.0';
  else
    v_mult := format(
      '(1 + %s::float8 * %s::float8 * (%s * greatest(0, least(1, (5 - surface) / 4.0)) + %s * greatest(0, least(1, (5 - views) / 4.0))'
      ' + %s * greatest(0, least(1, (5 - safety) / 4.0)) + %s * greatest(0, least(1, (5 - traffic) / 4.0))'
      ' + %s * greatest(0, least(1, (5 - parking) / 4.0))) / %s::float8)',
      v_strength, v_wmax / 3.0, w_s, w_v, w_f, w_t, w_p, v_wsum);
  end if;

  execute format('select id from public.routing_nodes where %s_main order by geom <-> $1 limit 1', v_pf)
    into v_src using v_from;
  execute format('select id from public.routing_nodes where %s_main order by geom <-> $1 limit 1', v_pf)
    into v_dst using v_to;
  if v_src is null or v_dst is null or v_src = v_dst then
    return;
  end if;

  v_margin := greatest(0.015, 0.5 * greatest(abs(p_from_lon - p_to_lon), abs(p_from_lat - p_to_lat)));

  -- Attempt 1 searches a corridor around the two points (fast); attempt 2 the whole network.
  for v_attempt in 1..2 loop
    v_sql := format(
      'select id, source, target,
         case when %1$s_dir in (''both'', ''forward'') then %1$s_t * %2$s else -1 end as cost,
         case when %1$s_dir in (''both'', ''backward'') then %1$s_t * %2$s else -1 end as reverse_cost
       from public.routing_graph
       where %1$s_dir <> ''none'' %3$s',
      v_pf, v_mult,
      case when v_attempt = 1 then format(
        'and cx between %s and %s and cy between %s and %s',
        least(p_from_lon, p_to_lon) - v_margin, greatest(p_from_lon, p_to_lon) + v_margin,
        least(p_from_lat, p_to_lat) - v_margin, greatest(p_from_lat, p_to_lat) + v_margin)
      else '' end);

    return query
    select r.path_seq::integer, e.id, e.way_id, e.segment_id, (r.node = e.source),
      e.length_m,
      (case v_pf when 'car' then g.car_t when 'bike' then g.bike_t else g.foot_t end)::double precision,
      g.surface, g.views, g.safety, g.traffic, g.parking, g.rated,
      case when r.node = e.source then e.geom else st_reverse(e.geom) end
    from extensions.pgr_bddijkstra(v_sql, v_src, v_dst, true) r
    join public.routing_edges e on e.id = r.edge
    join public.routing_graph g on g.id = r.edge
    where r.edge <> -1
    order by r.path_seq;

    if found then
      return;
    end if;
  end loop;
end;
$$;
