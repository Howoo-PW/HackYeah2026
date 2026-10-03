-- Makes find_route() fast: everything static or slowly changing is precomputed in
-- public.routing_graph (materialized view, refreshed with the ratings every 2 minutes), so a
-- request only builds the per-user cost from it. Measured on the free Supabase instance:
-- about 0.4 s for a typical car route, about 1.1 s for a bike route across the whole city
-- (was 2.8 s and 8.4 s with the plain view). Bidirectional Dijkstra is exact; bidirectional A*
-- returned a different (shorter) path in a test, so it is not used.

alter table public.routing_edges
  add column x1 double precision, add column y1 double precision,
  add column x2 double precision, add column y2 double precision,   -- EPSG:2180, metres (for A*-style tools)
  add column cx double precision, add column cy double precision;   -- edge middle, lon/lat (corridor filter)

create function public.routing_prepare_edges()
returns void
language sql
set search_path = public, extensions
as $$
  update public.routing_edges e set
    x1 = st_x(st_transform(st_startpoint(e.geom), 2180)), y1 = st_y(st_transform(st_startpoint(e.geom), 2180)),
    x2 = st_x(st_transform(st_endpoint(e.geom), 2180)), y2 = st_y(st_transform(st_endpoint(e.geom), 2180)),
    cx = st_x(st_lineinterpolatepoint(e.geom, 0.5)), cy = st_y(st_lineinterpolatepoint(e.geom, 0.5));
$$;
revoke execute on function public.routing_prepare_edges() from public, anon, authenticated;

select public.routing_prepare_edges();

create materialized view public.routing_graph as
select e.id, e.source, e.target, e.length_m, e.cx, e.cy, e.x1, e.y1, e.x2, e.y2,
  e.car_dir, e.bike_dir,
  case when e.car_dir <> 'none' then e.length_m / (greatest(coalesce(e.car_speed_kmh, 30), 5) / 3.6) end::real as car_t,
  case when e.bike_dir <> 'none' then e.length_m / (greatest(coalesce(e.bike_speed_kmh, 15), 5) / 3.6) end::real as bike_t,
  d.surface, d.views, d.safety, d.traffic, d.parking, d.rated
from public.routing_edges e
join public.routing_edge_dims d on d.edge_id = e.id;
create unique index routing_graph_pk on public.routing_graph (id);
revoke all on public.routing_graph from anon, authenticated;

-- Ratings changed -> routing_graph follows (the cron job calls this every 2 minutes).
create or replace function public.refresh_segment_stats()
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  refresh materialized view concurrently public.segment_stats;
  refresh materialized view concurrently public.segment_stats_by_time;
  refresh materialized view concurrently public.segment_scores;
  refresh materialized view concurrently public.routing_graph;
end;
$$;

-- Full rebuild after reloading osm_ways / segments: topology + helper columns + routing_graph.
create function public.rebuild_routing()
returns table (edges bigint, nodes bigint, car_main_share numeric, bike_main_share numeric)
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

create or replace function public.find_route(
  p_profile text,
  p_from_lon double precision, p_from_lat double precision,
  p_to_lon double precision, p_to_lat double precision,
  p_w_surface integer default 0, p_w_views integer default 0, p_w_safety integer default 0,
  p_w_traffic integer default 0, p_w_parking integer default 0,
  p_strength double precision default null   -- null: 8 for cars, 3 for bikes
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
      (case when v_pf = 'car' then g.car_t else g.bike_t end)::double precision,
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
