-- Route cost, layer 3: obstacles and time of day. Both are evaluated live in find_route() (nothing is stored in
-- routing_graph for them), so a closure reported a minute ago and a night-time rating added now change routes at once.
--
-- OBSTACLES. Each active obstacle (valid_until empty or in the future) is attached, per profile, to the nearest edge
-- that profile may use, within 50 m (the radius the API uses to pick the obstacle's segment). Effect on that edge:
--   closure -> the edge cannot be used (cost -1, both directions)      accident -> travel time x3
--   roadwork -> x2                                                       pothole  -> x1.25      other -> x1.2
-- Several obstacles on one edge: closed if any is a closure, otherwise the largest factor. The factor also lengthens
-- the time find_route() reports. An obstacle sits on one edge, so on a long edge it affects the whole edge.
--
-- TIME OF DAY (morning / day / evening / night, docs/CONTRACT.md section 3). Scores of a segment for that band are the
-- ratings given in the band (segment_stats_by_time) blended with the all-day score (segment_scores):
--   blended = (n * band_average + K * all_day_score) / (n + K),  n = ratings in the band, K = 3
-- so one night rating does not overrule a well-known segment, and a segment nobody rated at that time keeps its
-- all-day score. Without a time of day (null) the all-day scores are used.

-- ---------------------------------------------------------------------------------------------------------------
-- Time-of-day scores
-- ---------------------------------------------------------------------------------------------------------------

create function public.blend_score(p_n integer, p_band real, p_base real, p_k real default 3)
returns real
language sql immutable parallel safe
set search_path = ''
as $$
  select case when p_band is null or p_n is null or p_n <= 0 then p_base
              else (p_n * p_band + p_k * coalesce(p_base, p_band)) / (p_n + p_k) end::real
$$;
revoke execute on function public.blend_score(integer, real, real, real) from public, anon, authenticated;

-- Scores of every scored segment for a time of day (null = all day): the one place that defines the blend,
-- used by the backend for the scores it reports. find_route() applies the same blend inside its cost.
create function public.segment_scores_for_time(p_time_of_day public.time_of_day)
returns table (segment_id integer, surface real, views real, safety real, traffic real, parking real)
language sql stable
set search_path = public
as $$
  select s.segment_id,
    public.blend_score(t.ratings_count, t.surface, s.surface),
    public.blend_score(t.ratings_count, t.views, s.views),
    public.blend_score(t.ratings_count, t.safety, s.safety),
    public.blend_score(t.ratings_count, t.traffic, s.traffic),
    public.blend_score(t.ratings_count, t.parking, s.parking)
  from public.segment_scores s
  left join public.segment_stats_by_time t on t.segment_id = s.segment_id and t.time_of_day = p_time_of_day
$$;
revoke execute on function public.segment_scores_for_time(public.time_of_day) from public, anon, authenticated;

-- routing_graph needs the edge's segment to find its time-of-day ratings: recreated with one more column
-- (a materialized view cannot be altered; nothing depends on it).
drop materialized view public.routing_graph;
create materialized view public.routing_graph as
select e.id, e.segment_id, e.source, e.target, e.length_m, e.cx, e.cy, e.x1, e.y1, e.x2, e.y2,
  e.car_dir, e.bike_dir, e.foot_dir,
  case when e.car_dir <> 'none' then e.length_m / (greatest(coalesce(e.car_speed_kmh, 30), 5) / 3.6) end::real as car_t,
  case when e.bike_dir <> 'none' then e.length_m / (greatest(coalesce(e.bike_speed_kmh, 15), 5) / 3.6) end::real as bike_t,
  case when e.foot_dir <> 'none' then e.length_m / (greatest(coalesce(e.foot_speed_kmh, 5), 3) / 3.6) end::real as foot_t,
  d.surface, d.views, d.safety, d.traffic, d.parking, d.rated
from public.routing_edges e
join public.routing_edge_dims d on d.edge_id = e.id;
create unique index routing_graph_pk on public.routing_graph (id);
revoke all on public.routing_graph from anon, authenticated;

-- ---------------------------------------------------------------------------------------------------------------
-- Obstacles on edges
-- ---------------------------------------------------------------------------------------------------------------

create view public.routing_edge_obstacles with (security_invoker = true) as
select edge_id, pf, bool_or(type = 'closure') as closed,
  max(case type when 'accident' then 3.0 when 'roadwork' then 2.0 when 'pothole' then 1.25
                when 'other' then 1.2 else 1.0 end)::double precision as factor
from (
  select o.type::text as type, 'car'::text as pf, ce.id as edge_id
  from public.obstacles o
  cross join lateral (
    select e.id from public.routing_edges e
    where e.car_dir <> 'none' and e.geom && st_expand(o.geom, 0.001)
      and st_dwithin(e.geom::geography, o.geom::geography, 50)
    order by e.geom <-> o.geom limit 1
  ) ce
  where o.valid_until is null or o.valid_until > now()
  union all
  select o.type::text, 'bike', be.id
  from public.obstacles o
  cross join lateral (
    select e.id from public.routing_edges e
    where e.bike_dir <> 'none' and e.geom && st_expand(o.geom, 0.001)
      and st_dwithin(e.geom::geography, o.geom::geography, 50)
    order by e.geom <-> o.geom limit 1
  ) be
  where o.valid_until is null or o.valid_until > now()
  union all
  select o.type::text, 'foot', fe.id
  from public.obstacles o
  cross join lateral (
    select e.id from public.routing_edges e
    where e.foot_dir <> 'none' and e.geom && st_expand(o.geom, 0.001)
      and st_dwithin(e.geom::geography, o.geom::geography, 50)
    order by e.geom <-> o.geom limit 1
  ) fe
  where o.valid_until is null or o.valid_until > now()
) n
group by edge_id, pf;
revoke all on public.routing_edge_obstacles from anon, authenticated;

-- ---------------------------------------------------------------------------------------------------------------
-- find_route with obstacles and time of day (a new parameter: the old function is replaced)
-- ---------------------------------------------------------------------------------------------------------------

drop function public.find_route(text, double precision, double precision, double precision, double precision,
  integer, integer, integer, integer, integer, double precision);

create function public.find_route(
  p_profile text,
  p_from_lon double precision, p_from_lat double precision,
  p_to_lon double precision, p_to_lat double precision,
  p_w_surface integer default 0, p_w_views integer default 0, p_w_safety integer default 0,
  p_w_traffic integer default 0, p_w_parking integer default 0,
  p_strength double precision default null,   -- null: 8 for cars, 3 for bikes and pedestrians
  p_time_of_day text default null             -- morning | day | evening | night; null: all-day scores
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
  v_tjoin text;
  v_surface text := 'g.surface';
  v_views text := 'g.views';
  v_safety text := 'g.safety';
  v_traffic text := 'g.traffic';
  v_parking text := 'g.parking';
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
  if p_time_of_day is not null and p_time_of_day not in ('morning', 'day', 'evening', 'night') then
    raise exception 'unsupported time of day: %', p_time_of_day using errcode = '22023';
  end if;

  -- With a time of day the edge's segment ratings for that band are blended into every dimension.
  if p_time_of_day is null then
    v_tjoin := 'on false';
  else
    v_tjoin := format('on t.segment_id = g.segment_id and t.time_of_day = %L::public.time_of_day', p_time_of_day);
    v_surface := 'public.blend_score(t.ratings_count, t.surface, g.surface)';
    v_views := 'public.blend_score(t.ratings_count, t.views, g.views)';
    v_safety := 'public.blend_score(t.ratings_count, t.safety, g.safety)';
    v_traffic := 'public.blend_score(t.ratings_count, t.traffic, g.traffic)';
    v_parking := 'public.blend_score(t.ratings_count, t.parking, g.parking)';
  end if;

  v_wsum := w_s + w_v + w_f + w_t + w_p;
  v_wmax := greatest(w_s, w_v, w_f, w_t, w_p);
  if v_wsum = 0 then
    v_mult := '1.0';
  else
    v_mult := format(
      '(1 + %s::float8 * %s::float8 * (%s * greatest(0, least(1, (5 - %s) / 4.0)) + %s * greatest(0, least(1, (5 - %s) / 4.0))'
      ' + %s * greatest(0, least(1, (5 - %s) / 4.0)) + %s * greatest(0, least(1, (5 - %s) / 4.0))'
      ' + %s * greatest(0, least(1, (5 - %s) / 4.0))) / %s::float8)',
      v_strength, v_wmax / 3.0,
      w_s, v_surface, w_v, v_views, w_f, v_safety, w_t, v_traffic, w_p, v_parking, v_wsum);
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
      'select g.id, g.source, g.target,
         case when g.%1$s_dir in (''both'', ''forward'') and not coalesce(ob.closed, false)
           then g.%1$s_t * %2$s * coalesce(ob.factor, 1) else -1 end as cost,
         case when g.%1$s_dir in (''both'', ''backward'') and not coalesce(ob.closed, false)
           then g.%1$s_t * %2$s * coalesce(ob.factor, 1) else -1 end as reverse_cost
       from public.routing_graph g
       left join public.routing_edge_obstacles ob on ob.edge_id = g.id and ob.pf = %1$L
       left join public.segment_stats_by_time t %4$s
       where g.%1$s_dir <> ''none'' %3$s',
      v_pf, v_mult,
      case when v_attempt = 1 then format(
        'and g.cx between %s and %s and g.cy between %s and %s',
        least(p_from_lon, p_to_lon) - v_margin, greatest(p_from_lon, p_to_lon) + v_margin,
        least(p_from_lat, p_to_lat) - v_margin, greatest(p_from_lat, p_to_lat) + v_margin)
      else '' end,
      v_tjoin);

    return query
    select r.path_seq::integer, e.id, e.way_id, e.segment_id, (r.node = e.source),
      e.length_m,
      (case v_pf when 'car' then g.car_t when 'bike' then g.bike_t else g.foot_t end)::double precision
        * coalesce(ob.factor, 1),
      g.surface, g.views, g.safety, g.traffic, g.parking, g.rated,
      case when r.node = e.source then e.geom else st_reverse(e.geom) end
    from extensions.pgr_bddijkstra(v_sql, v_src, v_dst, true) r
    join public.routing_edges e on e.id = r.edge
    join public.routing_graph g on g.id = r.edge
    left join public.routing_edge_obstacles ob on ob.edge_id = e.id and ob.pf = v_pf
    where r.edge <> -1
    order by r.path_seq;

    if found then
      return;
    end if;
  end loop;
end;
$$;
revoke execute on function public.find_route(text, double precision, double precision, double precision,
  double precision, integer, integer, integer, integer, integer, double precision, text) from public, anon, authenticated;
